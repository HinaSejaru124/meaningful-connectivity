import os
import random

BASE = "simulation/htdocs/agent_tasks"

# Cibles divisées par ~2 par rapport à la première tentative : le débit
# TCP EFFECTIF sous latence/gigue élevées est souvent très inférieur au
# débit nominal (même phénomène documenté sur le scénario vidéo — voir
# l'enquête sur l'effondrement de la fenêtre de congestion TCP). Se caler
# sur 5 Mbit/s nominal était trop optimiste.
BURST_TARGET = 300_000     # ~2.4 Mbit/s effectif × 1.0s (moitié de BURST_DEADLINE_S=2.0)
WRITE_TARGET = 750_000      # ~2.4 Mbit/s effectif × 2.5s (moitié de WRITE_DEADLINE_S=5.0)

def make_file(path, size_bytes):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(os.urandom(size_bytes))

def varied_size(target, factor):
    # Variance réduite (±15% au lieu de ±40%) pour que les paliers de
    # difficulté restent bien ordonnés entre eux, sans chevauchement.
    base = int(target * factor)
    return max(1024, int(base * random.uniform(0.85, 1.15)))

random.seed(42)

# Trois paliers seulement (au lieu de 6) : suffisant pour cerner la
# frontière une fois qu'on a une meilleure idée de la bonne cible, et
# plus simple à lire.
tasks = {
    "task_light_a": 0.25,
    "task_light_b": 0.25,
    "task_target_a": 0.4,
    "task_target_b": 0.4,
    "task_heavy_a": 0.6,
    "task_heavy_b": 0.6,
}

for task_name, difficulty in tasks.items():
    task_dir = os.path.join(BASE, task_name)

    for i in range(3):
        size = varied_size(BURST_TARGET, difficulty)
        make_file(os.path.join(task_dir, "01_read_burst", f"file{i+1}.bin"), size)

    size = varied_size(WRITE_TARGET, difficulty)
    make_file(os.path.join(task_dir, "02_write.bin"), size)

    for i in range(2):
        size = varied_size(BURST_TARGET, difficulty)
        make_file(os.path.join(task_dir, "03_read_burst", f"file{i+1}.bin"), size)

    size = varied_size(WRITE_TARGET, difficulty)
    make_file(os.path.join(task_dir, "04_write.bin"), size)

print("Ressources agent_tasks recalibrées (v2).")