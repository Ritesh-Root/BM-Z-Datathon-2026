#!/usr/bin/env bash
# Start (or restart) the VitalWatch dashboard inside IBM's container on LinuxONE.
# Usage: scripts/run_vm.sh [physionet|synthetic]
set -euo pipefail

SOURCE="${1:-physionet}"
CONTAINER="${CONTAINER:-notebook}"
PORT="${PORT:-38080}"
HOST_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CDIR="${CDIR:-/home/ibm-user/shared/$(basename "$HOST_DIR")}"

docker exec "$CONTAINER" bash -lc "pkill -f 'vitalwatch (serve|demo)' || true"
docker exec -d "$CONTAINER" bash -lc "cd '$CDIR' && mkdir -p logs && set -a && { [ -f .env ] && . ./.env; } ; set +a && \
  python -m vitalwatch demo --source $SOURCE --port $PORT > logs/serve.log 2>&1"

echo "Starting (the first run builds the demo scenario) ..."
for _ in $(seq 1 60); do
  sleep 2
  if docker exec "$CONTAINER" bash -lc "grep -q 'VitalWatch dashboard' '$CDIR/logs/serve.log'" 2>/dev/null; then break; fi
done
URL="$(docker exec "$CONTAINER" bash -lc "grep -m1 -o 'http://[^ ]*' '$CDIR/logs/serve.log'" | tr -d '\r')"
IP="$(curl -s -m 5 https://api.ipify.org || hostname -I | awk '{print $1}')"
echo "Dashboard: ${URL/localhost/$IP}"
echo "Logs:      docker exec $CONTAINER tail -f $CDIR/logs/serve.log"
