#!/bin/bash
# Make the recommended config delta as a patch against the project's src/config.json, from the
# config.json of a finished fx copy. The patch is written; it is NOT applied to src/.
# usage: make_patch.sh <fx tag> <out.patch>
set -euo pipefail
TAG="$1"; OUT="$2"
P="/Users/samuelzhang/Desktop/2B ECE/attention_head_gf"
cd "$P"
diff -u --label a/src/config.json --label b/src/config.json src/config.json \
    "/Users/samuelzhang/ttharden/fx_$TAG/src/config.json" > "$OUT" || true
echo "wrote $OUT ($(grep -c '^[+-][^+-]' "$OUT") changed lines)"
