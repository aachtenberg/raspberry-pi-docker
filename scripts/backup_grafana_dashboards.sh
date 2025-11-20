#\!/bin/bash

#
# Automated Grafana Dashboard Backup Script
# Exports dashboards and commits to Git
#

# Configuration
DOCKER_DIR="/home/aachten/docker"
LOG_FILE="$DOCKER_DIR/logs/grafana_backup.log"
DATE=$(date +"%Y-%m-%d %H:%M:%S")

# Create logs directory if it doesnt exist
mkdir -p "$DOCKER_DIR/logs"

# Function to log messages
log() {
    echo "[$DATE] $1" | tee -a "$LOG_FILE"
}

log "Starting Grafana dashboard backup..."

# Change to docker directory
cd "$DOCKER_DIR" || {
    log "ERROR: Failed to change to $DOCKER_DIR"
    exit 1
}

# Load environment variables
if [ -f .env ]; then
    export $(grep -v '^#' .env | grep -v '^$' | xargs)
fi

# Export dashboards
log "Exporting dashboards..."
if ./scripts/export_grafana_dashboards.sh >> "$LOG_FILE" 2>&1; then
    log "Dashboards exported successfully"
else
    log "ERROR: Failed to export dashboards"
    exit 1
fi

# Check if there are changes to commit
if git diff --quiet grafana/dashboards/; then
    log "No changes to commit - dashboards unchanged"
    exit 0
fi

# Add changes
log "Adding changes to git..."
git add grafana/dashboards/

# Commit changes
log "Committing changes..."
if git commit -m "chore: automated dashboard backup - $(date +%Y-%m-%d)" >> "$LOG_FILE" 2>&1; then
    log "Changes committed successfully"
else
    log "ERROR: Failed to commit changes"
    exit 1
fi

# Push to remote
log "Pushing to remote..."
if git push >> "$LOG_FILE" 2>&1; then
    log "Changes pushed successfully"
else
    log "ERROR: Failed to push changes"
    exit 1
fi

log "Backup completed successfully"
exit 0
