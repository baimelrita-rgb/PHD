#!/usr/bin/env bash
# Download Sherlock 03-Rural (owner approved, ~1.9 GB), verify md5, extract selectively
# (no pcaps, no control-center notifications, no host logs: not used by this project).
set -euo pipefail
cd "$(dirname "$0")/.."
URL="https://zenodo.org/api/records/18467070/files/03-Rural.zip/content"
EXPECTED="0cc7807bd5a76ea5bc85a1da6fd6c061"
OUT="data/raw/03-Rural.zip"
mkdir -p data/raw
if [ ! -f "$OUT" ] || [ "$(md5sum "$OUT" | cut -d' ' -f1)" != "$EXPECTED" ]; then
  curl -sS -L --retry 6 --retry-delay 10 -C - -o "$OUT" "$URL" || curl -sS -L --retry 6 -C - -o "$OUT" "$URL"
fi
GOT="$(md5sum "$OUT" | cut -d' ' -f1)"
echo "md5 expected=$EXPECTED got=$GOT"
if [ "$GOT" != "$EXPECTED" ]; then echo "MD5 MISMATCH: stop and report" >&2; exit 2; fi
mkdir -p data/raw/03-Rural
if [ -z "$(ls -A data/raw/03-Rural)" ]; then
  unzip -q "$OUT" -d data/raw/03-Rural -x "*/pcap/*" "*control-center.zip" "*/log/*" "__MACOSX/*"
fi
echo "done"
