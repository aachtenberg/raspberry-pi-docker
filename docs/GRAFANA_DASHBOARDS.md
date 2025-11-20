
## Grafana Dashboard Management

### Export Dashboards to Version Control

Export all Grafana dashboards as JSON files for backup and version control:

```bash
cd ~/docker

# Export dashboards (will prompt for password)
GRAFANA_PASSWORD=your_grafana_password ./scripts/export_grafana_dashboards.sh

# Dashboards will be saved to grafana/dashboards/*.json
```

**Commit to Git:**
```bash
git add grafana/dashboards/
git commit -m "chore: export Grafana dashboards"
git push
```

### Import Dashboards

To restore or share dashboards:

1. **Via Grafana UI**:
   - Go to Dashboards → Import
   - Upload JSON file from `grafana/dashboards/`
   - Click Import

2. **Via API** (automated):
   ```bash
   for file in grafana/dashboards/*.json; do
     curl -X POST -H "Content-Type: application/json" \
       -u admin:your_password \
       -d @"$file" \
       http://localhost:3000/api/dashboards/db
   done
   ```

### Dashboard Files

Exported dashboards include metadata:
- Export timestamp
- Dashboard title and UID
- Folder location
- Version number

Perfect for:
- 📦 Backing up dashboard configurations
- 🔄 Sharing dashboards between Grafana instances
- 📝 Version controlling dashboard changes
- 🚀 Automating dashboard deployment
