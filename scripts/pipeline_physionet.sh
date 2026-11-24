#!/usr/bin/env bash
# Full real-data pipeline: download PhysioNet 2019, train, evaluate, verify the model,
# and (on LinuxONE) benchmark incl. IBM Telum NNPA and load-test.
#
# Two modes, chosen automatically (override with PIPELINE_MODE=docker|local):
#   docker  IBM LinuxONE (s390x). Run on the VM as linux1 after scripts/vm_setup.sh; every
#           step runs inside the JupyterLab container. This is the original behaviour.
#   local   Any other machine (x86 / ARM laptop or server). Runs in the current Python
#           environment (PYTHON=... to choose one; default .venv/bin/python, else python3).
#           Skips the benchmark and load test, which are measurements of the machine, not of
#           the data (RUN_BENCH=1 to include them).
set -euo pipefail

HOST_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MODE="${PIPELINE_MODE:-$([ "$(uname -m)" = s390x ] && echo docker || echo local)}"
step() { printf '\n== %s  [%s]\n' "$*" "$(date -u +%H:%M:%S)"; }

if [ "$MODE" = docker ]; then
  CONTAINER="${CONTAINER:-notebook}"
  CDIR="${CDIR:-/home/ibm-user/shared/$(basename "$HOST_DIR")}"
  vw() { docker exec "$CONTAINER" bash -lc "cd '$CDIR' && set -a && { [ -f .env ] && . ./.env; } ; set +a && python -m vitalwatch $*"; }
  RUN_BENCH="${RUN_BENCH:-1}"
else
  PY="${PYTHON:-$([ -x "$HOST_DIR/.venv/bin/python" ] && echo "$HOST_DIR/.venv/bin/python" || command -v python3)}"
  cd "$HOST_DIR"
  if [ "$(uname -s)" = Darwin ]; then
    # XGBoost's macOS wheel needs libomp. Use the copy that scikit-learn's wheel ships if
    # Homebrew's is absent, so no system install is needed.
    skl="$("$PY" -c 'import os, sklearn; print(os.path.join(os.path.dirname(sklearn.__file__), ".dylibs"))' 2>/dev/null || true)"
    if [ -d "$skl" ]; then export DYLD_FALLBACK_LIBRARY_PATH="$skl${DYLD_FALLBACK_LIBRARY_PATH:+:$DYLD_FALLBACK_LIBRARY_PATH}"; fi
  fi
  vw() { "$PY" -m vitalwatch "$@"; }
  RUN_BENCH="${RUN_BENCH:-0}"
fi

step "Download PhysioNet 2019 (host side)"
bash "$HOST_DIR/scripts/download_physionet.sh" "$HOST_DIR/data/physionet"
if [ "$MODE" = docker ]; then sudo chown -R 1000:1000 "$HOST_DIR/data" 2>/dev/null || true; fi

step "Ingest";            vw ingest --source physionet --raw data/physionet
step "Split";             vw split --source physionet
step "Train";             vw train --source physionet
step "Evaluate";          vw evaluate --source physionet
step "Charts";            vw charts --source physionet
step "Golden check";      vw verify-artifacts || true
if [ "$RUN_BENCH" = 1 ]; then
  step "Benchmark";       vw bench --source physionet
  step "Load test";       vw loadtest --source physionet
fi

echo
echo "Done. Commit the results so they appear in the README and deck:"
echo "  python -m vitalwatch report && git add artifacts results scenarios README.md && git commit -m 'Real-data results (PhysioNet 2019)' && git push"
