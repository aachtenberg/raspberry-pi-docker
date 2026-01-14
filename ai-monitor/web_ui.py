#!/usr/bin/env python3
"""
Flask web UI for AI Monitor
Provides incident browsing, live status, and manual controls
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from flask import Flask, render_template, jsonify, request, Response
import requests
from prometheus_client import parser as prom_parser
import threading

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='{"ts": "%(asctime)s", "level": "%(levelname)s", "msg": "%(message)s"}',
    datefmt="%Y-%m-%dT%H:%M:%S%z"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
INCIDENTS_DIR = Path(os.getenv("INCIDENTS_DIR", "/app/incidents"))
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
METRICS_PORT = int(os.getenv("METRICS_PORT", "8000"))
STATE_FILE = INCIDENTS_DIR / "incidents_state.json"
state_lock = threading.Lock()

class IncidentState:
    """Manage incident state (read, dismissed)"""
    
    @staticmethod
    def load_state() -> Dict:
        """Load incident state from file"""
        if not STATE_FILE.exists():
            return {}
        try:
            with state_lock:
                return json.loads(STATE_FILE.read_text())
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            return {}
    
    @staticmethod
    def save_state(state: Dict):
        """Save incident state to file"""
        try:
            with state_lock:
                STATE_FILE.write_text(json.dumps(state, indent=2))
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
    
    @staticmethod
    def mark_as_read(filename: str):
        """Mark incident as read"""
        state = IncidentState.load_state()
        if filename not in state:
            state[filename] = {}
        state[filename]["read"] = True
        state[filename]["read_at"] = datetime.utcnow().isoformat() + "Z"
        IncidentState.save_state(state)
    
    @staticmethod
    def is_read(filename: str) -> bool:
        """Check if incident is marked as read"""
        state = IncidentState.load_state()
        return state.get(filename, {}).get("read", False)
    
    @staticmethod
    def dismiss(filename: str):
        """Dismiss (hide) incident"""
        state = IncidentState.load_state()
        if filename not in state:
            state[filename] = {}
        state[filename]["dismissed"] = True
        state[filename]["dismissed_at"] = datetime.utcnow().isoformat() + "Z"
        IncidentState.save_state(state)
    
    @staticmethod
    def is_dismissed(filename: str) -> bool:
        """Check if incident is dismissed"""
        state = IncidentState.load_state()
        return state.get(filename, {}).get("dismissed", False)
    
    @staticmethod
    def get_preference(key: str, default=None):
        """Get a preference value"""
        state = IncidentState.load_state()
        return state.get("_preferences", {}).get(key, default)
    
    @staticmethod
    def set_preference(key: str, value):
        """Set a preference value"""
        state = IncidentState.load_state()
        if "_preferences" not in state:
            state["_preferences"] = {}
        state["_preferences"][key] = value
        IncidentState.save_state(state)

class IncidentBrowser:
    """Browse and parse incident reports"""
    
    @staticmethod
    def list_incidents(limit: Optional[int] = None, include_dismissed: bool = False) -> List[Dict]:
        """List all incidents, newest first"""
        if not INCIDENTS_DIR.exists():
            return []
        
        incidents = []
        for file in sorted(INCIDENTS_DIR.glob("incident_*.md"), reverse=True):
            try:
                # Skip dismissed incidents unless explicitly requested
                if not include_dismissed and IncidentState.is_dismissed(file.name):
                    continue
                
                content = file.read_text()
                metadata = IncidentBrowser._parse_metadata(content)
                incidents.append({
                    "filename": file.name,
                    "timestamp": metadata.get("timestamp", file.stem.replace("incident_", "")),
                    "severity": metadata.get("severity", "unknown"),
                    "confidence": metadata.get("confidence", 0.0),
                    "summary": metadata.get("summary", "No summary"),
                    "path": str(file),
                    "read": IncidentState.is_read(file.name),
                    "dismissed": IncidentState.is_dismissed(file.name)
                })
            except Exception as e:
                logger.warning(f"Failed to parse {file.name}: {e}")
                continue
        
        if limit:
            incidents = incidents[:limit]
        
        return incidents
    
    @staticmethod
    def _parse_metadata(content: str) -> Dict:
        """Extract metadata from incident markdown"""
        lines = content.split("\n")
        metadata = {}
        in_summary_section = False
        summary_lines = []
        
        for i, line in enumerate(lines):
            # Handle field formats: "**Time:**", "**Severity:**", "**Confidence:**"
            if line.startswith("**Time:**") or line.startswith("**Timestamp:**"):
                metadata["timestamp"] = line.split(":", 1)[1].strip()
            elif line.startswith("**Severity:**"):
                # Split on ":" and clean up any markdown and whitespace
                severity = line.split(":", 1)[1].strip()
                # Remove any trailing markdown asterisks
                severity = severity.replace("**", "").strip()
                metadata["severity"] = severity.lower()
            elif line.startswith("**Confidence:**"):
                try:
                    # Handle formats like "80%" or "0.8"
                    conf_str = line.split(":", 1)[1].strip().replace("%", "").replace("**", "")
                    conf_val = float(conf_str)
                    # Normalize to 0-1 range
                    metadata["confidence"] = conf_val / 100.0 if conf_val > 1 else conf_val
                except (ValueError, AttributeError):
                    metadata["confidence"] = 0.0
            
            # Handle "## Summary" section
            elif line.startswith("## Summary"):
                in_summary_section = True
                continue
            elif in_summary_section:
                # Stop at next section header or empty line after content
                if line.startswith("##") or (line.strip() == "" and summary_lines):
                    break
                elif line.strip():
                    summary_lines.append(line.strip())
        
        # Join summary lines and truncate if needed
        if summary_lines:
            metadata["summary"] = " ".join(summary_lines)
            # Truncate to reasonable length for display
            if len(metadata["summary"]) > 200:
                metadata["summary"] = metadata["summary"][:197] + "..."
        
        return metadata
    
    @staticmethod
    def get_incident(filename: str) -> Optional[Dict]:
        """Get full incident report"""
        file_path = INCIDENTS_DIR / filename
        if not file_path.exists() or not file_path.is_file():
            return None
        
        try:
            content = file_path.read_text()
            metadata = IncidentBrowser._parse_metadata(content)
            return {
                "filename": filename,
                "content": content,
                **metadata
            }
        except Exception as e:
            logger.error(f"Failed to read {filename}: {e}")
            return None

class StatusMonitor:
    """Query current system status"""
    
    @staticmethod
    def get_prometheus_status() -> Dict:
        """Get Prometheus health"""
        try:
            resp = requests.get(f"{PROMETHEUS_URL}/-/healthy", timeout=5)
            return {
                "healthy": resp.status_code == 200,
                "url": PROMETHEUS_URL
            }
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e),
                "url": PROMETHEUS_URL
            }
    
    @staticmethod
    def get_scrape_targets() -> List[Dict]:
        """Get Prometheus scrape target status"""
        try:
            resp = requests.get(f"{PROMETHEUS_URL}/api/v1/targets", timeout=5)
            data = resp.json()
            
            if data.get("status") != "success":
                return []
            
            targets = []
            for target in data.get("data", {}).get("activeTargets", []):
                targets.append({
                    "job": target.get("labels", {}).get("job", "unknown"),
                    "instance": target.get("labels", {}).get("instance", "unknown"),
                    "health": target.get("health", "unknown"),
                    "last_scrape": target.get("lastScrape"),
                    "last_error": target.get("lastError", "")
                })
            
            return targets
        except Exception as e:
            logger.error(f"Failed to fetch scrape targets: {e}")
            return []
    
    @staticmethod
    def get_ai_monitor_metrics() -> Dict:
        """Get metrics from AI monitor's own metrics endpoint"""
        try:
            resp = requests.get(f"http://localhost:{METRICS_PORT}/metrics", timeout=5)
            metrics_text = resp.text
            
            # Parse Prometheus metrics
            metrics = {}
            for family in prom_parser.text_string_to_metric_families(metrics_text):
                for sample in family.samples:
                    key = f"{sample.name}"
                    if sample.labels:
                        key += f"{{{','.join([f'{k}={v}' for k, v in sample.labels.items()])}}}"
                    metrics[key] = sample.value
            
            return metrics
        except Exception as e:
            logger.error(f"Failed to fetch AI monitor metrics: {e}")
            return {}

# Routes

@app.route("/")
def index():
    """Main dashboard"""
    return render_template("dashboard.html")

@app.route("/incidents")
def incidents_page():
    """Incident browser page"""
    return render_template("incidents.html")

@app.route("/tool-calls")
def tool_calls_page():
    """Tool call history page"""
    return render_template("tool_calls.html")

@app.route("/api/incidents")
def api_incidents():
    """API: List incidents"""
    limit = request.args.get("limit", type=int)
    incidents = IncidentBrowser.list_incidents(limit=limit)
    return jsonify(incidents)

@app.route("/api/incidents/<filename>")
def api_incident_detail(filename):
    """API: Get incident detail"""
    incident = IncidentBrowser.get_incident(filename)
    if not incident:
        return jsonify({"error": "Incident not found"}), 404
    return jsonify(incident)

@app.route("/api/status")
def api_status():
    """API: Get current system status"""
    return jsonify({
        "prometheus": StatusMonitor.get_prometheus_status(),
        "scrape_targets": StatusMonitor.get_scrape_targets(),
        "ai_metrics": StatusMonitor.get_ai_monitor_metrics(),
        "timestamp": datetime.utcnow().isoformat() + "Z"
    })

@app.route("/api/health")
def api_health():
    """API: Get infrastructure health metrics from telemetry collector"""
    try:
        # Query Prometheus for infra health metrics
        queries = {
            "backup_age": "infra_backup_age_seconds",
            "backup_stale": "infra_backup_stale",
            "disk_usage": "infra_disk_usage_percent",
            "disk_critical": "infra_disk_critical",
            "service_health": "infra_service_healthy",
            "data_stale": "infra_data_stale"
        }
        
        health_data = {}
        for name, query in queries.items():
            resp = requests.get(
                f"{PROMETHEUS_URL}/api/v1/query",
                params={"query": query},
                timeout=5
            )
            if resp.status_code == 200:
                result = resp.json().get("data", {}).get("result", [])
                health_data[name] = result
            else:
                health_data[name] = []
        
        # Calculate summary stats
        services_up = sum(1 for r in health_data.get("service_health", []) if float(r["value"][1]) == 1.0)
        services_total = len(health_data.get("service_health", []))
        
        backup_age_hours = 0
        if health_data.get("backup_age"):
            backup_age_hours = float(health_data["backup_age"][0]["value"][1]) / 3600
        
        disk_usage = 0
        if health_data.get("disk_usage"):
            disk_usage = int(float(health_data["disk_usage"][0]["value"][1]))
        
        return jsonify({
            "summary": {
                "services_healthy": f"{services_up}/{services_total}",
                "backup_age_hours": round(backup_age_hours, 1),
                "backup_status": "healthy" if backup_age_hours < 24 else "stale",
                "disk_usage_percent": disk_usage,
                "disk_status": "critical" if disk_usage > 85 else "healthy"
            },
            "metrics": health_data,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        })
    except Exception as e:
        logger.error(f"Failed to fetch health metrics: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/llm/config")
def api_llm_config():
    """API: Get current LLM configuration"""
    claude_available = bool(os.getenv("CLAUDE_API_KEY"))
    gemini_available = bool(os.getenv("GEMINI_API_KEY"))
    
    # Check monitor's actual backend from recent logs or state
    preferred_backend = IncidentState.get_preference("llm_backend", "auto")
    
    # Determine current backend (Claude takes priority if both available)
    if preferred_backend == "claude" and claude_available:
        current_backend = "claude"
        current_model = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
    elif preferred_backend == "gemini" and gemini_available:
        current_backend = "gemini"
        current_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")
    elif preferred_backend == "auto":
        if claude_available:
            current_backend = "claude"
            current_model = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
        elif gemini_available:
            current_backend = "gemini"
            current_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")
        else:
            current_backend = "none"
            current_model = "none"
    else:
        current_backend = "none"
        current_model = "none"
    
    return jsonify({
        "available_backends": {
            "claude": claude_available,
            "gemini": gemini_available
        },
        "preferred_backend": preferred_backend,
        "current_backend": current_backend,
        "model": current_model,
        "models": {
            "claude": os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022"),
            "gemini": os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")
        },
        "restart_required": True  # Backend changes require restart
    })

@app.route("/api/llm/backend", methods=["POST"])
def api_set_backend():
    """API: Set preferred LLM backend"""
    try:
        data = request.get_json()
        backend = data.get("backend", "auto")
        
        if backend not in ["auto", "claude", "gemini"]:
            return jsonify({"error": "Invalid backend. Must be 'auto', 'claude', or 'gemini'"}), 400
        
        IncidentState.set_preference("llm_backend", backend)
        
        return jsonify({
            "success": True,
            "backend": backend,
            "message": "Backend preference saved. Restart container to apply."
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/tool-calls")
def api_tool_calls():
    """API: Get recent tool call history"""
    try:
        # Import from agent_monitor to access history
        import sys
        sys.path.insert(0, os.path.dirname(__file__))
        from agent_monitor import TOOL_CALL_HISTORY, TOOL_CALL_HISTORY_LOCK
        
        limit = request.args.get("limit", default=50, type=int)
        limit = min(limit, 200)  # Cap at 200
        
        with TOOL_CALL_HISTORY_LOCK:
            history = list(TOOL_CALL_HISTORY[-limit:])
        
        # Reverse to show most recent first
        history.reverse()
        
        # Calculate stats
        total_calls = len(TOOL_CALL_HISTORY)
        successful = sum(1 for h in TOOL_CALL_HISTORY if h.get("success"))
        failed = total_calls - successful
        
        # Tool usage breakdown
        tool_counts = {}
        for h in TOOL_CALL_HISTORY:
            tool = h.get("tool_name", "unknown")
            tool_counts[tool] = tool_counts.get(tool, 0) + 1
        
        return jsonify({
            "tool_calls": history,
            "stats": {
                "total_calls": total_calls,
                "successful": successful,
                "failed": failed,
                "success_rate": round(successful / total_calls * 100, 1) if total_calls > 0 else 0,
                "tool_usage": tool_counts
            },
            "timestamp": datetime.utcnow().isoformat() + "Z"
        })
    except Exception as e:
        logger.error(f"Failed to fetch tool call history: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/stats")
def api_stats():
    """API: Get aggregate statistics"""
    incidents = IncidentBrowser.list_incidents()
    
    severity_counts = {}
    unread_count = 0
    for inc in incidents:
        sev = inc.get("severity", "unknown")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        if not inc.get("read", False):
            unread_count += 1
    
    return jsonify({
        "total_incidents": len(incidents),
        "unread_count": unread_count,
        "by_severity": severity_counts,
        "recent_incidents": incidents[:5]
    })

@app.route("/api/incidents/<filename>/read", methods=["POST"])
def api_mark_read(filename):
    """API: Mark incident as read"""
    try:
        IncidentState.mark_as_read(filename)
        return jsonify({"success": True, "filename": filename})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/incidents/bulk/read", methods=["POST"])
def api_bulk_mark_read():
    """API: Mark multiple incidents as read"""
    try:
        data = request.get_json()
        filenames = data.get("filenames", [])
        
        if not filenames:
            return jsonify({"error": "No filenames provided"}), 400
        
        for filename in filenames:
            IncidentState.mark_as_read(filename)
        
        return jsonify({"success": True, "count": len(filenames)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/incidents/<filename>/dismiss", methods=["POST", "DELETE"])
def api_dismiss_incident(filename):
    """API: Dismiss (hide) incident"""
    try:
        IncidentState.dismiss(filename)
        return jsonify({"success": True, "filename": filename})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/incidents/<filename>", methods=["DELETE"])
def api_delete_incident(filename):
    """API: Permanently delete incident file"""
    try:
        file_path = INCIDENTS_DIR / filename
        if not file_path.exists() or not file_path.is_file():
            return jsonify({"error": "Incident not found"}), 404
        
        # Remove from state file
        state = IncidentState.load_state()
        if filename in state:
            del state[filename]
            IncidentState.save_state(state)
        
        # Delete the file
        file_path.unlink()
        
        return jsonify({"success": True, "filename": filename})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/incidents/bulk/dismiss", methods=["POST"])
def api_bulk_dismiss():
    """API: Dismiss multiple incidents"""
    try:
        data = request.get_json()
        filenames = data.get("filenames", [])
        
        if not filenames:
            return jsonify({"error": "No filenames provided"}), 400
        
        for filename in filenames:
            IncidentState.dismiss(filename)
        
        return jsonify({"success": True, "count": len(filenames)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/incidents/bulk/delete", methods=["POST", "DELETE"])
def api_bulk_delete():
    """API: Delete multiple incident files"""
    try:
        data = request.get_json()
        filenames = data.get("filenames", [])
        
        if not filenames:
            return jsonify({"error": "No filenames provided"}), 400
        
        deleted = []
        errors = []
        
        for filename in filenames:
            try:
                file_path = INCIDENTS_DIR / filename
                if file_path.exists() and file_path.is_file():
                    # Remove from state
                    state = IncidentState.load_state()
                    if filename in state:
                        del state[filename]
                        IncidentState.save_state(state)
                    
                    # Delete file
                    file_path.unlink()
                    deleted.append(filename)
                else:
                    errors.append(f"{filename}: not found")
            except Exception as e:
                errors.append(f"{filename}: {str(e)}")
        
        return jsonify({
            "success": True,
            "deleted": len(deleted),
            "errors": errors if errors else None
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/health")
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "ai-monitor-ui"})

if __name__ == "__main__":
    logger.info(f"Starting AI Monitor Web UI on port 8001")
    logger.info(f"Incidents directory: {INCIDENTS_DIR}")
    logger.info(f"Prometheus URL: {PROMETHEUS_URL}")
    
    # Ensure incidents directory exists
    INCIDENTS_DIR.mkdir(parents=True, exist_ok=True)
    
    app.run(host="0.0.0.0", port=8001, debug=False)
