#!/usr/bin/env bash
# Download the PhysioNet/CinC Challenge 2019 sepsis data (open access, ODC-By 1.0).
# Usage: scripts/download_physionet.sh [target_dir]   (default: data/physionet)
# Cite: Reyna MA et al., Crit Care Med 2020;48(2):210-217.
set -euo pipefail

TARGET="${1:-data/physionet}"
BASE="https://physionet.org/files/challenge-2019/1.0.0"
mkdir -p "$TARGET"
cd "$TARGET"

count() { find . -name '*.psv' | wc -l; }

if [ "$(count)" -ge 40000 ]; then
  echo "Already have $(count) patient files in $TARGET"
  exit 0
fi

echo "Trying the single ZIP archive first ..."
if wget -q --show-progress -c -O challenge-2019.zip "https://physionet.org/content/challenge-2019/get-zip/1.0.0/"; then
  unzip -q -o challenge-2019.zip && rm -f challenge-2019.zip
  # The archive unpacks into a long folder name; move the training sets up.
  found="$(find . -type d -name training_setA | head -n 1)"
  if [ -n "$found" ]; then
    mkdir -p training
    mv "$(dirname "$found")"/training_set* training/ 2>/dev/null || true
  fi
fi

if [ "$(count)" -lt 40000 ]; then
  echo "Falling back to recursive download (about 40,000 small files; this can take a while) ..."
  wget -r -N -c -np -nH --cut-dirs=4 -q --show-progress "$BASE/training/" || true
fi

n="$(count)"
echo "Patient files: $n"
if [ "$n" -lt 40000 ]; then
  echo "Download incomplete. Re-run this script, or download on a laptop and copy with scp." >&2
  exit 1
fi
echo "Done. Next: python -m vitalwatch ingest --source physionet --raw $TARGET"
