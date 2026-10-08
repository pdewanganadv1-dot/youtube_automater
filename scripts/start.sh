#!/usr/bin/env bash
# Start the worker (makes and uploads videos) and the dashboard together. Ctrl+C stops both.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m ytauto.worker &
WORKER=$!
trap 'kill $WORKER 2>/dev/null' EXIT
streamlit run app.py --server.headless true
