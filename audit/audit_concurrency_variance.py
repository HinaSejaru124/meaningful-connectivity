#!/usr/bin/env python3
"""
audit_concurrency_variance.py

Audite les sessions déjà générées pour vérifier empiriquement que la
concurrence (concurrent_users > 1) produit une variance mesurable entre
clients partageant la même ressource et la même config réseau.

Scanne automatiquement TOUT le dataset (dataset.csv + tous les
logs/session_*/metrics.json présents), quel que soit le nombre de
sessions déjà générées.

Pour chaque session à plusieurs clients :
    - désaccord de label (meaningful différent entre clients) ;
    - dispersion de download_time / rebuffer_ratio (temps ou taux de
      rebuffering) — attention : dans les sessions où le transfert
      échoue, download_time est souvent plafonné par curl --max-time
      et ne reflète PAS la contention réelle (tous les clients qui
      timeout se retrouvent avec un download_time quasi identique,
      quel que soit ce qu'ils ont réellement reçu) ;
    - dispersion de downloaded_size_bytes, la métrique qui reste
      informative dans ce régime d'échec : le nombre d'octets reçus
      avant le timeout varie bien avec la contention, même quand le
      temps, lui, est artificiellement plafonné.

Usage :
    python3 audit_concurrency_variance.py --dataset-dir dataset
"""

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


def load_dataset_rows(dataset_csv: Path) -> list[dict]:
    if not dataset_csv.exists():
        raise SystemExit(f"Introuvable : {dataset_csv}")

    with dataset_csv.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_metrics(logs_dir: Path, session_id: str) -> dict | None:
    path = logs_dir / session_id / "metrics.json"

    if not path.exists():
        return None

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def timing_metric_for_sample(sample: dict) -> float | None:
    """
    download_time (pdf/quiz/audio/webpage/upload sous le nom
    upload_time), rebuffer_ratio (video_streaming) ou late_ratio
    (quiz_interactive). Ignore les valeurs infinies (curl sans
    sortie, parsing raté).
    """

    for key in ("download_time", "upload_time", "rebuffer_ratio", "late_ratio"):
        value = sample.get(key)

        if value is not None and math.isfinite(value):
            return value

    return None


def size_metric_for_sample(sample: dict) -> float | None:
    """
    downloaded_size_bytes ou uploaded_size_bytes, quand disponible.
    Reste informatif même quand le temps est plafonné par
    curl --max-time dans les sessions en échec.
    """

    for key in ("downloaded_size_bytes", "uploaded_size_bytes"):
        value = sample.get(key)

        if value is not None and math.isfinite(value):
            return float(value)

    return None


def dispersion(values: list[float]) -> tuple[float, float] | tuple[None, None]:
    if len(values) < 2:
        return None, None

    return statistics.pstdev(values), max(values) - min(values)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-dir",
        default="dataset",
        help="Répertoire du dataset (défaut : dataset)",
    )
    args = parser.parse_args()

    dataset_dir = Path(args.dataset_dir)
    dataset_csv = dataset_dir / "dataset.csv"
    logs_dir = dataset_dir / "logs"

    rows = load_dataset_rows(dataset_csv)

    sessions = defaultdict(list)
    for row in rows:
        sessions[row["session_id"]].append(row)

    multi_client_sessions = {
        sid: rs for sid, rs in sessions.items() if len(rs) > 1
    }

    print("=" * 70)
    print("AUDIT DE LA VARIANCE INTRA-SESSION (CONCURRENCE)")
    print("=" * 70)
    print()
    print(f"Sessions totales dans le CSV  : {len(sessions)}")
    print(f"Observations totales           : {len(rows)}")
    print(f"Sessions avec >1 observation    : {len(multi_client_sessions)}")
    print()

    if not multi_client_sessions:
        print(
            "Aucune session avec plus d'une observation dans ce dataset. "
            "Rien à auditer (concurrent_users était probablement à 1 sur "
            "toutes les sessions générées jusqu'ici)."
        )
        return

    per_scenario_disagree = defaultdict(int)
    per_scenario_total = defaultdict(int)
    per_scenario_timing_stds = defaultdict(list)
    per_scenario_timing_ranges = defaultdict(list)
    per_scenario_size_stds = defaultdict(list)
    per_scenario_size_ranges = defaultdict(list)
    missing_metrics = []

    detail_lines = []

    for session_id, rs in sorted(multi_client_sessions.items()):
        service_type = rs[0]["service_type"]
        concurrent_users = rs[0]["concurrent_users"]

        labels = [int(r["meaningful"]) for r in rs]
        disagreement = len(set(labels)) > 1

        per_scenario_total[service_type] += 1
        if disagreement:
            per_scenario_disagree[service_type] += 1

        metrics = load_metrics(logs_dir, session_id)
        timing_std = timing_range = size_std = size_range = None

        if metrics is None:
            missing_metrics.append(session_id)
        else:
            samples = metrics.get("samples", [])

            timing_values = [
                v for v in (timing_metric_for_sample(s) for s in samples)
                if v is not None
            ]
            timing_std, timing_range = dispersion(timing_values)
            if timing_std is not None:
                per_scenario_timing_stds[service_type].append(timing_std)
                per_scenario_timing_ranges[service_type].append(timing_range)

            size_values = [
                v for v in (size_metric_for_sample(s) for s in samples)
                if v is not None
            ]
            size_std, size_range = dispersion(size_values)
            if size_std is not None:
                per_scenario_size_stds[service_type].append(size_std)
                per_scenario_size_ranges[service_type].append(size_range)

        flag = "⚠ DÉSACCORD" if disagreement else ""
        t_txt = f"t_std={timing_std:.4f}" if timing_std is not None else ""
        s_txt = f"size_range={size_range:.0f}o" if size_range is not None else ""

        detail_lines.append(
            f"{session_id:16s} {service_type:16s} "
            f"n={len(rs):2d} (concurrent_users={concurrent_users:>3s}) "
            f"labels={labels} {flag} {t_txt} {s_txt}"
        )

    print("Détail par session :")
    print("-" * 70)
    for line in detail_lines:
        print(line)

    print()
    print("=" * 70)
    print("RÉSUMÉ PAR SCÉNARIO")
    print("=" * 70)

    for service_type in sorted(per_scenario_total):
        total = per_scenario_total[service_type]
        disagree = per_scenario_disagree[service_type]
        pct = 100 * disagree / total if total else 0.0

        t_stds = per_scenario_timing_stds[service_type]
        t_ranges = per_scenario_timing_ranges[service_type]
        sz_stds = per_scenario_size_stds[service_type]
        sz_ranges = per_scenario_size_ranges[service_type]

        print()
        print(f"[{service_type}]")
        print(f"  Sessions multi-clients             : {total}")
        print(f"  Sessions avec désaccord de label   : {disagree} ({pct:.1f}%)")

        if t_stds:
            print(
                f"  Dispersion temporelle (download_time/rebuffer_ratio) : "
                f"std moyen={statistics.mean(t_stds):.4f}, "
                f"std médian={statistics.median(t_stds):.4f}"
            )
        if sz_stds:
            print(
                f"  Dispersion en octets reçus (downloaded_size_bytes)    : "
                f"std moyen={statistics.mean(sz_stds):.0f}o, "
                f"range moyen={statistics.mean(sz_ranges):.0f}o"
            )

        if total and disagree == 0 and not t_stds and not sz_stds:
            print(
                "  ⚠ Aucune donnée de variance disponible "
                "(metrics.json manquants ?) et aucun désaccord de label."
            )

    if missing_metrics:
        print()
        print(
            f"⚠ metrics.json introuvable pour {len(missing_metrics)} "
            f"session(s) multi-clients (dispersion non calculée pour "
            f"celles-ci, seul le désaccord de label a pu être évalué) :"
        )
        for sid in missing_metrics:
            print(f"    - {sid}")

    print()
    print("=" * 70)
    print(
        "Interprétation :\n"
        "- Un taux de désaccord de label élevé et/ou une dispersion\n"
        "  temporelle non négligeable dans les sessions RÉUSSIES\n"
        "  confirment un effet mesurable de la concurrence.\n"
        "- Dans les sessions en ÉCHEC massif, une dispersion temporelle\n"
        "  quasi nulle est normale : download_time y est souvent\n"
        "  plafonné par curl --max-time, pas par le réseau. Regarder\n"
        "  plutôt downloaded_size_bytes, qui reste informatif dans ce\n"
        "  régime."
    )


if __name__ == "__main__":
    main()
