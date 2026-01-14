#!/bin/bash
# Entrypoint script to run both monitor and web UI

set -e

# Start web UI in background
python -u web_ui.py &
WEB_PID=$!

# Start monitor in foreground
python -u monitor.py &
MONITOR_PID=$!

# Wait for both processes
wait $WEB_PID $MONITOR_PID
