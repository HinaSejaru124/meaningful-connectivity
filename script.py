import json
from pathlib import Path

logs_dir = Path("dataset_video_debug/logs")

for candidate_duration in [1.0, 1.5, 2.0, 3.0]:
    for candidate_ratio in [0.05, 0.10, 0.20]:
        total = 0
        meaningful = 0
        for session_dir in logs_dir.glob("session_*"):
            metrics = json.loads((session_dir / "metrics.json").read_text())
            for sample in metrics["samples"]:
                times = sample["segment_times"]
                if not times:
                    continue
                total += 1
                rebuffer = sum(1 for t in times if t > candidate_duration) / len(times)
                if rebuffer <= candidate_ratio:
                    meaningful += 1
        pct = 100 * meaningful / total if total else 0
        print(f"duration={candidate_duration}s ratio={candidate_ratio} -> {meaningful}/{total} meaningful ({pct:.1f}%)")
