#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

echo "Creating virtual environment..."
python3.13 -m venv .venv
source .venv/bin/activate

echo "Installing dependencies..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "Checking ONNX model artifacts..."
python - <<'PY'
from medical_redactor_onnx.paths import hubert_ner_dir, tableformer_dir

print(f"TableFormer: {tableformer_dir(require=True)}")
print(f"HuBERT NER:  {hubert_ner_dir(require=True)}")
PY

echo "Checking runtime dependency hygiene..."
python - <<'PY'
import importlib.metadata as metadata

installed = {dist.metadata["Name"].lower() for dist in metadata.distributions()}
banned = sorted(
    name
    for name in installed
    if name in {"torch", "torchvision", "triton"} or name.startswith("nvidia-")
)
if banned:
    raise SystemExit(f"Runtime venv is not torch-free: {', '.join(banned)}")
print("No torch/triton/nvidia runtime packages found.")
PY

echo ""
echo "Setup complete. Run the app with:"
echo "  cd $(pwd)"
echo "  source .venv/bin/activate"
echo "  python main.py"
