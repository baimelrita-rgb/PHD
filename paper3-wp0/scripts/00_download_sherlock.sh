#!/usr/bin/env bash
# Download Sherlock 01-Basic (approved, ~703 MB) and verify md5. Stops on mismatch.
set -euo pipefail
cd "$(dirname "$0")/.."
URL="https://zenodo.org/api/records/18467070/files/01-Basic.zip/content"
EXPECTED="c482e0dc7e56b063b357d8b03be5cce6"
OUT="data/raw/01-Basic.zip"
mkdir -p data/raw
if [ ! -f "$OUT" ] || [ "$(md5sum "$OUT" | cut -d' ' -f1)" != "$EXPECTED" ]; then
  curl -sS -L --retry 4 --retry-delay 5 -C - -o "$OUT" "$URL" || curl -sS -L --retry 4 -o "$OUT" "$URL"
fi
GOT="$(md5sum "$OUT" | cut -d' ' -f1)"
echo "md5 expected=$EXPECTED got=$GOT"
if [ "$GOT" != "$EXPECTED" ]; then echo "MD5 MISMATCH: stop and report" >&2; exit 2; fi
# also fetch the dataset paper (small) for documentation
curl -sS -L -o data/raw/paper.pdf "https://zenodo.org/api/records/18467070/files/paper.pdf/content"
mkdir -p data/raw/01-Basic
if [ -z "$(ls -A data/raw/01-Basic)" ]; then unzip -q "$OUT" -d data/raw/01-Basic; fi
echo "done"
