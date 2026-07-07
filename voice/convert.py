import os
import torch
from infer.modules.vc.modules import VC

# ===== CONFIG =====
DEVICE = "cpu"   # change to "cuda" if GPU available

MODEL_PATH = "models/polar.pth"
INDEX_PATH = "models/polar.index"

INPUT_FILES = [
    "test.mp3",
]

OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ===== INIT VC =====
vc = VC(DEVICE)

print("Loading Polar model...")
vc.load_model(MODEL_PATH)

print("Starting conversion...")

for input_path in INPUT_FILES:
    filename = os.path.basename(input_path)
    output_path = os.path.join(OUTPUT_DIR, f"polar_{filename}")

    print(f"Converting {filename}...")

    vc.infer(
        input_path,
        output_path,
        index_path=INDEX_PATH,
        f0_method="rmvpe",      # BEST for singing
        index_rate=0.75,        # recommended for Polar
        filter_radius=3,
        protect=0.33,
        transpose=0             # adjust if pitch mismatch
    )

print("All conversions complete!")