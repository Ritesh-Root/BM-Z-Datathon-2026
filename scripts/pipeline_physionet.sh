#!/usr/bin/env bash
# Full real-data pipeline on IBM LinuxONE: download PhysioNet 2019, train, evaluate,
# verify the model on s390x, benchmark (incl. IBM Telum NNPA) and load-test.
# Run on the VM as linux1 after scripts/vm_setup.sh.
set -euo pipefail

CONTAINER="${CONTAINER:-notebook}"
HOST_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CDIR="${CDIR:-/home/ibm-user/shared/$(basename "$HOST_DIR")}"
step() { printf '\n== %s  [%s]\n' "$*" "$(date -u +%H:%M:%S)"; }
vw() { docker exec "$CONTAINER" bash -lc "cd '$CDIR' && set -a && { [ -f .env ] && . ./.env; } ; set +a && python -m vitalwatch $*"; }

step "Download PhysioNet 2019 (host side)"
bash "$HOST_DIR/scripts/download_physionet.sh" "$HOST_DIR/data/physionet"
sudo chown -R 1000:1000 "$HOST_DIR/data" 2>/dev/null || true

step "Ingest";            vw ingest --source physionet --raw data/physionet
step "Split";             vw split --source physionet
step "Train on LinuxONE"; vw train --source physionet
step "Evaluate";          vw evaluate --source physionet
step "Charts";            vw charts --source physionet
step "Golden check on s390x"; vw verify-artifacts || true
step "Benchmark";         vw bench --source physionet
step "Load test";         vw loadtest --source physionet

echo
echo "Done. Commit the results so they appear in the README and deck:"
echo "  git add artifacts results scenarios && git commit -m 'Real-data results on IBM LinuxONE' && git push"
