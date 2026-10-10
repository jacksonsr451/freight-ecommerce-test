#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$(command -v python3 || command -v python || true)"
if [[ -z "$PYTHON" ]]; then
  printf '%s\n' 'Python 3.11+ was not found. Install Python and Poetry, then retry.' >&2
  exit 1
fi
exec "$PYTHON" "$SCRIPT_DIR/dev.py" "$@"
