#!/usr/bin/env bash
# Download the PhysioNet/CinC Challenge 2019 sepsis data (open access).
# Licence and terms: https://physionet.org/content/challenge-2019/1.0.0/ (see its LICENSE.txt).
# Usage: scripts/download_physionet.sh [target_dir]   (default: data/physionet)
# Cite: Reyna MA et al., Crit Care Med 2020;48(2):210-217.
#
# PhysioNet v1.0.0 publishes the data as 40,336 individual .psv files (about 255 MB in
# total), not as one ZIP. Two ways to fetch them:
#   1. curl (any platform): list each training set from its PhysioNet directory page and
#      fetch the files in parallel from the public S3 mirror that physionet.org itself
#      redirects to. Used on macOS/x86/ARM, where wget is usually missing.
#      Set JOBS=N to change the parallelism (default 16).
#   2. wget recursive download: the original method, kept as the fallback for the
#      IBM LinuxONE container and for machines without curl.
set -euo pipefail

TARGET="${1:-data/physionet}"
BASE="https://physionet.org/files/challenge-2019/1.0.0"
MIRROR="https://physionet-open.s3.amazonaws.com/challenge-2019/1.0.0"
PAGE="https://physionet.org/content/challenge-2019/1.0.0/training"
JOBS="${JOBS:-16}"
mkdir -p "$TARGET"
cd "$TARGET"

count() { find . -name '*.psv' -size +0 | wc -l | tr -d ' '; }
EXPECT_A=20336
EXPECT_B=20000
EXPECT=$((EXPECT_A + EXPECT_B))

if [ "$(count)" -ge "$EXPECT" ]; then
  echo "Already have $(count) patient files in $TARGET"
  exit 0
fi

fetch_set_curl() {   # fetch_set_curl training_setA 20336
  local set="$1" want="$2" dir="training/$1"
  mkdir -p "$dir"
  curl -fsSL --retry 3 "$PAGE/$set/" | grep -oE 'p[0-9]{6}\.psv' | sort -u > "$set.list"
  local listed; listed="$(wc -l < "$set.list" | tr -d ' ')"
  if [ "$listed" -ne "$want" ]; then
    echo "$set: directory page lists $listed files, expected $want" >&2
    return 1
  fi
  # Only fetch what is missing or empty, so an interrupted run resumes cheaply.
  find "$dir" -name '*.psv' -size 0 -delete
  while read -r f; do [ -s "$dir/$f" ] || printf 'url = "%s/%s/%s"\noutput = "%s/%s"\n' "$MIRROR" "$dir" "$f" "$dir" "$f"; done \
    < "$set.list" > "$set.curl"
  local todo; todo=$(( $(wc -l < "$set.curl" | tr -d ' ') / 2 ))
  echo "$set: $todo of $listed files to fetch"
  if [ "$todo" -gt 0 ]; then
    # --fail: never keep an HTTP error page as a data file; --parallel reuses connections.
    curl -sS -Z --parallel-max "$JOBS" --fail --connect-timeout 20 --retry 3 --retry-delay 2 -K "$set.curl" || true
    find "$dir" -name '*.psv' -size 0 -delete
  fi
  rm -f "$set.list" "$set.curl"
}

if command -v curl >/dev/null 2>&1; then
  echo "Fetching with curl ($JOBS parallel transfers) ..."
  for pass in 1 2; do
    [ "$(count)" -ge "$EXPECT" ] && break
    [ "$pass" -gt 1 ] && echo "Retrying files that failed ..."
    fetch_set_curl training_setA "$EXPECT_A" || true
    fetch_set_curl training_setB "$EXPECT_B" || true
  done
fi

if [ "$(count)" -lt "$EXPECT" ] && command -v wget >/dev/null 2>&1; then
  echo "Falling back to recursive wget download (about 40,000 small files; this can take a while) ..."
  wget -r -N -c -np -nH --cut-dirs=4 -q --show-progress "$BASE/training/" || true
fi

n="$(count)"
echo "Patient files: $n (expected $EXPECT)"
if [ "$n" -lt "$EXPECT" ]; then
  echo "Download incomplete. Re-run this script, or download on a laptop and copy with scp." >&2
  exit 1
fi
echo "Done. Next: python -m vitalwatch ingest --source physionet --raw $TARGET"
