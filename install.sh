#!/bin/sh
# Installs the equity-research-analyst subagent and its toolkit for Claude Code.
set -e

SRC="$(cd "$(dirname "$0")" && pwd)"
AGENTS="$HOME/.claude/agents"
TOOLS="$HOME/.claude/tools/equity-research"
PY="${PYTHON:-python3}"

command -v "$PY" >/dev/null 2>&1 || { echo "Python 3 is required (set PYTHON=/path/to/python3)."; exit 1; }

mkdir -p "$AGENTS" "$TOOLS"
cp "$SRC/agents/equity-research-analyst.md" "$AGENTS/"
cp "$SRC/tools/equity-research/eqr" "$SRC/tools/equity-research/eqr.py" \
   "$SRC/tools/equity-research/requirements.txt" "$TOOLS/"
chmod +x "$TOOLS/eqr"

if [ ! -x "$TOOLS/.venv/bin/python" ]; then
  echo "Creating Python environment in $TOOLS/.venv"
  "$PY" -m venv "$TOOLS/.venv"
fi
"$TOOLS/.venv/bin/pip" install -q --upgrade pip
"$TOOLS/.venv/bin/pip" install -q -r "$TOOLS/requirements.txt"

echo "Installed. Check the toolkit with:"
echo "  $TOOLS/eqr risk SPY --years 1"
echo "Then start a new Claude Code session and ask it to use the equity-research-analyst agent."
