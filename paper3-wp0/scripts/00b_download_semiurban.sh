#!/usr/bin/env bash
# Download Sherlock 02-Semiurban (owner approved, ~6.4 GB), verify md5, extract selectively
# (no pcaps, no control-center notifications, no host logs: not used by this project).
set -euo pipefail
cd "$(dirname "$0")/.."
URL="https://zenodo.org/api/records/18467070/files/02-Semiurban.zip/content"
EXPECTED="0f7d3eb61e478d05f4b431ae99d45564"
OUT="data/raw/02-Semiurban.zip"
mkdir -p data/raw
if [ ! -f "$OUT" ] || [ "$(md5sum "$OUT" | cut -d' ' -f1)" != "$EXPECTED" ]; then
  curl -sS -L --retry 6 --retry-delay 10 -C - -o "$OUT" "$URL" || curl -sS -L --retry 6 -C - -o "$OUT" "$URL"
fi
GOT="$(md5sum "$OUT" | cut -d' ' -f1)"
echo "md5 expected=$EXPECTED got=$GOT"
if [ "$GOT" != "$EXPECTED" ]; then echo "MD5 MISMATCH: stop and report" >&2; exit 2; fi
mkdir -p data/raw/02-Semiurban
if [ -z "$(ls -A data/raw/02-Semiurban)" ]; then
  unzip -q "$OUT" -d data/raw/02-Semiurban -x "*/pcap/*" "*control-center.zip" "*/log/*" "__MACOSX/*"
fi
echo "done"
