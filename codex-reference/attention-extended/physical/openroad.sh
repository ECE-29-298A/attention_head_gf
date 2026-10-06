#!/bin/bash
set -e
R="$(cd "$(dirname "$0")" && pwd)"
export LD_LIBRARY_PATH="$R/tools/deps/usr/lib/x86_64-linux-gnu:$R/tools/openroad/opt/or-tools/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export TCL_LIBRARY="$R/tools/deps/usr/share/tcltk/tcl8.6"
exec "$R/tools/openroad/usr/bin/openroad" "$@"
