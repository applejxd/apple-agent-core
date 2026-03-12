#!/bin/sh
# entrypoint.sh: place context engineering templates and start the agent

set -e

WORKSPACE="${WORKSPACE_DIR:-/workspace}"

# Place AGENTS.md template if not already present
if [ ! -f "$WORKSPACE/AGENTS.md" ]; then
    echo "[entrypoint] Placing AGENTS.md template in $WORKSPACE"
    cp /app/templates/AGENTS.md "$WORKSPACE/AGENTS.md"
fi

echo "[entrypoint] Starting agent in $WORKSPACE"
cd "$WORKSPACE"

# UI_MODE=1 or --ui flag → launch web UI server
if [ "${UI_MODE}" = "1" ] || echo "$@" | grep -q "\-\-ui"; then
    exec uv run --project /app agent-ui
fi

exec uv run --project /app python -m my_agent_core "$@"
