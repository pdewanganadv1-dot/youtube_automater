#!/usr/bin/env bash
# Free local narrator voices: Piper TTS + the LibriTTS-R multi-speaker English model (CC BY 4.0).
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .voices
.voices/bin/pip install --quiet "piper-tts>=1.3" numpy
mkdir -p data/voices
BASE=https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/libritts_r/medium
for f in en_US-libritts_r-medium.onnx en_US-libritts_r-medium.onnx.json; do
  [ -f "data/voices/$f" ] || curl -L --fail -o "data/voices/$f" "$BASE/$f"
done
echo '{"cmd":"calibrate","model":"data/voices/en_US-libritts_r-medium.onnx","out":"data/voices/speakers.json","samples":60}' \
  | .voices/bin/python tools/piper_tts.py
echo "Piper voices ready."
