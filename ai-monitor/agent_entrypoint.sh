#!/bin/bash
set -e

# Start web UI in background
python web_ui.py &
WEB_PID=$!

# Start agent monitor in foreground
python agent_monitor.py &
AGENT_PID=$!

# Wait for both processes
wait -n $WEB_PID $AGENT_PID

# If either exits, kill the other and exit
kill $WEB_PID $AGENT_PID 2>/dev/null || true
exit $?
