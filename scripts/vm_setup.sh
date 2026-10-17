#!/usr/bin/env bash
# One-time setup on the IBM LinuxONE Community Cloud VM (run as linux1 on the VM).
#
# Prerequisite: IBM's JupyterLab ML container is running, as in
# https://github.com/linuxone-community-cloud/jupyter-lab-ml (container name "notebook",
# started with --network host and ~/shared mounted at /home/ibm-user/shared).
# This repository must be cloned inside ~/shared so the container can see it.
set -euo pipefail

CONTAINER="${CONTAINER:-notebook}"
PORT="${PORT:-38080}"
HOST_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_NAME="$(basename "$HOST_DIR")"
CDIR="${CDIR:-/home/ibm-user/shared/$REPO_NAME}"

step() { printf '\n== %s\n' "$*"; }
inbox() { docker exec "$CONTAINER" bash -lc "$*"; }

step "Machine"
echo "architecture: $(uname -m)"
if grep -q -m1 -w nnpa /proc/cpuinfo; then
  echo "IBM Telum on-chip AI accelerator (NNPA) is visible to this VM"
else
  echo "NNPA flag not visible to this VM (VitalWatch will report CPU scoring honestly)"
fi
grep -m1 'machine =' /proc/cpuinfo || true
nproc; free -g | head -2; df -h "$HOST_DIR" | tail -1

step "Container"
if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "Container '$CONTAINER' is not running. Start IBM's JupyterLab container first:" >&2
  echo "  docker run --network host --name notebook -v /home/linux1/shared:/home/ibm-user/shared -d registry.linuxone.cloud.marist.edu/l1cc/jupyterlab-image-s390x:latest" >&2
  exit 1
fi
case "$HOST_DIR" in
  "$HOME"/shared/*) ;;
  *) echo "Clone the repository inside ~/shared (found $HOST_DIR)" >&2; exit 1 ;;
esac
sudo chown -R 1000:1000 "$HOST_DIR" 2>/dev/null || true
inbox "test -d '$CDIR'" || { echo "Container cannot see $CDIR" >&2; exit 1; }

step "Python packages inside the container (Flask, IBM Snap ML)"
inbox "cd '$CDIR' && (python -m pip install -q -r requirements-vm.txt || python -m pip install -q --user -r requirements-vm.txt)"
inbox "python -c 'import flask, snapml; print(\"flask\", flask.__version__, \"| snapml\", snapml.__version__)'"

step "IBM zDNN library for Snap ML"
ZDNN="$(inbox "python -c 'import ctypes.util; print(ctypes.util.find_library(\"zdnn\") or \"\")'" | tr -d '\r')"
if [ -z "$ZDNN" ]; then
  ZDNN="$(inbox "find / -name 'libzdnn.so*' -not -path '*/proc/*' 2>/dev/null | head -n 1" | tr -d '\r' || true)"
fi
echo "libzdnn: ${ZDNN:-not found}"

step "IBM Granite model bundled in the container"
GGUF="$(inbox "cd ~ && python -c 'from loan_demo.rag_utils import MODEL_PATH; print(MODEL_PATH)' 2>/dev/null" | tr -d '\r' || true)"
if [ -z "$GGUF" ] || ! inbox "test -f '$GGUF'"; then
  GGUF="$(inbox "find / -name '*granite*.gguf' -not -path '*/proc/*' 2>/dev/null | head -n 1" | tr -d '\r' || true)"
fi
echo "granite: ${GGUF:-not found (template notes will be used)}"

step "Writing .env"
{
  echo "# written by scripts/vm_setup.sh"
  [ -n "$ZDNN" ] && echo "SNAPML_ZDNN_LIB=$ZDNN"
  [ -n "$GGUF" ] && echo "VW_GRANITE_GGUF=$GGUF"
  echo "VW_SERVER_PORT=$PORT"
} > "$HOST_DIR/.env"
cat "$HOST_DIR/.env"

step "Firewall: open TCP $PORT for the dashboard"
sudo iptables -C INPUT -p tcp --dport "$PORT" -j ACCEPT 2>/dev/null || sudo iptables -I INPUT -p tcp --dport "$PORT" -j ACCEPT
echo "port $PORT open"

step "VitalWatch doctor (inside the container)"
inbox "cd '$CDIR' && set -a && . ./.env && set +a && python -m vitalwatch doctor"

echo
echo "Setup complete. Next:"
echo "  scripts/pipeline_physionet.sh   # real data: download, train, evaluate, benchmark (about 30-60 min)"
echo "  scripts/run_vm.sh               # start the live dashboard on port $PORT"
