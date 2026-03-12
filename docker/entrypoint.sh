#!/bin/sh
# entrypoint.sh: place context engineering templates and start the agent

set -e

# The agent now handles workspace/session setup and template copying internally via main.py.
# We just need to ensure we are in the app directory to run the module correctly.
cd /app

# UI_MODE=1 or --ui flag → launch web UI server
if [ "${UI_MODE}" = "1" ] || echo "$@" | grep -q "\-\-ui"; then
    exec uv run --project /app agent-ui
fi

exec uv run --project /app agent "$@"
