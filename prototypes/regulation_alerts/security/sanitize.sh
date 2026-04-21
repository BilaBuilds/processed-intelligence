#!/usr/bin/env bash
# sanitize.sh - thin wrapper; delegates to clawshield.sh sanitize
# Usage: echo "text" | bash sanitize.sh
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$SCRIPT_DIR/clawshield.sh" sanitize "$@"
