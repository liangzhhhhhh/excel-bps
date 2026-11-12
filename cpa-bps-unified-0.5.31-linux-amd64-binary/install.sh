#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
for tool in python3 docker sh; do
    command -v "$tool" >/dev/null 2>&1 || { echo "Required command missing: $tool" >&2; exit 1; }
done
test -s BINARY.json || { echo 'Missing BINARY.json' >&2; exit 1; }
exec python3 plugin/scripts/install-unified.py "$@"
