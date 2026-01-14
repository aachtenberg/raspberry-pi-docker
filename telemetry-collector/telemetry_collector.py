"""
Telemetry Collector - Export infrastructure health metrics for AI agent investigation.

This service runs continuously and exports health signals to Prometheus:
- Backup freshness and status
- Disk space and NAS availability  
- Data freshness (InfluxDB, MQTT flow)
- Service health checks
- Container restart counts

The AI agent queries these metrics to proactively investigate issues.
"""

import os
import time
import json
from datetime import datetime
from typing import Dict, Any, Optional
import requests
import docker
from prometheus_client import Gauge, start_http_server, Counter, Info

# ================================ Configuration ================================

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
INFLUXDB3_URL = os.getenv("INFLUXDB3_URL", "http://influxdb3-core:8181")
INFLUXDB3_TOKEN = os.getenv("INFLUXDB3_ADMIN_TOKEN", "")
COLLECTION_INTERVAL = int(os.getenv("TELEMETRY_COLLECTION_INTERVAL", "60"))  # seconds
METRICS_PORT = int(os.getenv("TELEMETRY_METRICS_PORT", "9101"))

# ================================ Prometheus Metrics ===========================

# Backup health
backup_age_seconds = Gauge(
    "infra_backup_age_seconds",
    "Time since last successful backup",
    ["hostname"]
)
backup_stale = Gauge(
    "infra_backup_stale", 
    "Backup is stale (>24h old)",
    ["hostname"]
)

# Disk health
disk_usage_percent = Gauge(
    "infra_disk_usage_percent",
    "Disk usage percentage",
    ["mountpoint", "hostname"]
)
disk_critical = Gauge(
    "infra_disk_critical",
    "Disk usage critical (>85%)",
    ["mountpoint", "hostname"]
)

# Data freshness
data_age_seconds = Gauge(
    "infra_data_age_seconds",
    "Time since last data write",
    ["database", "measurement", "hostname"]
)
data_stale = Gauge(
    "infra_data_stale",
    "Data is stale (>1h old)",
    ["database", "measurement", "hostname"]
)

# Service health
service_healthy = Gauge(
    "infra_service_healthy",
    "Service is healthy and operational",
    ["service", "hostname"]
)

# Container restart tracking
container_restart_count = Counter(
    "infra_container_restarts_total",
    "Total container restarts detected",
    ["container", "hostname"]
)

# Collector health
collector_checks_total = Counter(
    "telemetry_collector_checks_total",
    "Total health checks performed",
    ["check_type", "status"]
)

collector_info = Info(
    "telemetry_collector",
    "Telemetry collector information"
)

# ================================ Health Checks ================================

def get_hostname() -> str:
    """Get hostname from environment or system."""
    return os.getenv("HOSTNAME", "unknown")


def check_backup_health() -> None:
    """Check backup age and status from Prometheus."""
    hostname = get_hostname()
    
    try:
        # Query Prometheus for backup metrics
        query = "time() - docker_backup_last_success_timestamp"
        resp = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": query},
            timeout=10
        )
        resp.raise_for_status()
        
        result = resp.json().get("data", {}).get("result", [])
        if result:
            age = int(float(result[0]["value"][1]))
            backup_age_seconds.labels(hostname=hostname).set(age)
            backup_stale.labels(hostname=hostname).set(1 if age > 86400 else 0)
            
            collector_checks_total.labels(check_type="backup", status="success").inc()
        else:
            print(f"⚠️  No backup metrics found")
            collector_checks_total.labels(check_type="backup", status="no_data").inc()
    
    except Exception as e:
        print(f"❌ Backup health check failed: {e}")
        collector_checks_total.labels(check_type="backup", status="error").inc()


def check_disk_health() -> None:
    """Check disk usage from Docker host filesystem."""
    hostname = get_hostname()
    
    try:
        # Query Prometheus for node_exporter disk metrics
        query = 'node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"} * 100'
        resp = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": query},
            timeout=10
        )
        resp.raise_for_status()
        
        result = resp.json().get("data", {}).get("result", [])
        if result:
            avail_pct = float(result[0]["value"][1])
            usage_pct = 100 - avail_pct
            
            disk_usage_percent.labels(mountpoint="/", hostname=hostname).set(int(usage_pct))
            disk_critical.labels(mountpoint="/", hostname=hostname).set(1 if usage_pct > 85 else 0)
            
            collector_checks_total.labels(check_type="disk", status="success").inc()
        else:
            print(f"⚠️  No disk metrics found")
            collector_checks_total.labels(check_type="disk", status="no_data").inc()
    
    except Exception as e:
        print(f"❌ Disk health check failed: {e}")
        collector_checks_total.labels(check_type="disk", status="error").inc()


def check_data_freshness() -> None:
    """Check data freshness via MQTT message rates in Prometheus."""
    hostname = get_hostname()
    
    try:
        # Check MQTT message rate (messages flowing from sensors to Mosquitto)
        # If no messages in last hour, data is stale
        query = 'rate(mosquitto_messages_received_total[5m])'
        resp = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": query},
            timeout=10
        )
        resp.raise_for_status()
        
        result = resp.json().get("data", {}).get("result", [])
        if result:
            # If rate > 0, data is flowing
            rate = float(result[0]["value"][1])
            is_stale = 1 if rate == 0 else 0
            
            data_age_seconds.labels(
                database="mqtt",
                measurement="messages",
                hostname=hostname
            ).set(0 if rate > 0 else 3600)
            data_stale.labels(
                database="mqtt",
                measurement="messages",
                hostname=hostname
            ).set(is_stale)
            
            collector_checks_total.labels(check_type="data_freshness", status="success").inc()
        else:
            # No metrics - mark as stale
            print(f"⚠️  No MQTT message rate metrics found")
            data_age_seconds.labels(
                database="mqtt",
                measurement="messages",
                hostname=hostname
            ).set(999999)
            data_stale.labels(
                database="mqtt",
                measurement="messages",
                hostname=hostname
            ).set(1)
            collector_checks_total.labels(check_type="data_freshness", status="no_data").inc()
    
    except Exception as e:
        print(f"❌ Data freshness check failed: {e}")
        collector_checks_total.labels(check_type="data_freshness", status="error").inc()


def check_service_health() -> None:
    """Check critical service health via Prometheus and Docker."""
    hostname = get_hostname()
    
    # Check Prometheus targets
    services = ["prometheus", "telegraf", "mosquitto", "influxdb3-core"]
    
    for service in services:
        try:
            query = f'up{{job="{service}"}}'
            resp = requests.get(
                f"{PROMETHEUS_URL}/api/v1/query",
                params={"query": query},
                timeout=10
            )
            resp.raise_for_status()
            
            result = resp.json().get("data", {}).get("result", [])
            if result:
                up = int(float(result[0]["value"][1]))
                service_healthy.labels(service=service, hostname=hostname).set(up)
            else:
                service_healthy.labels(service=service, hostname=hostname).set(0)
        
        except Exception as e:
            print(f"❌ Service health check failed for {service}: {e}")
            service_healthy.labels(service=service, hostname=hostname).set(0)
    
    # Check pdc-agent via Docker API
    try:
        client = docker.from_env()
        pdc = client.containers.get("pdc-agent")
        is_running = pdc.status == "running"
        service_healthy.labels(service="pdc-agent", hostname=hostname).set(1 if is_running else 0)
        
        collector_checks_total.labels(check_type="service_health", status="success").inc()
    
    except Exception as e:
        print(f"❌ pdc-agent health check failed: {e}")
        service_healthy.labels(service="pdc-agent", hostname=hostname).set(0)
        collector_checks_total.labels(check_type="service_health", status="error").inc()


# ================================ Main Loop ====================================

def collect_all_metrics() -> None:
    """Run all health checks and export metrics."""
    print(f"[{datetime.now().isoformat()}] Running health checks...")
    
    check_backup_health()
    check_disk_health()
    check_data_freshness()
    check_service_health()
    
    print(f"[{datetime.now().isoformat()}] Health checks complete")


def main():
    """Main telemetry collector loop."""
    # Set collector info
    collector_info.info({
        "version": "1.0.0",
        "collection_interval": str(COLLECTION_INTERVAL),
        "prometheus_url": PROMETHEUS_URL,
        "influxdb3_url": INFLUXDB3_URL
    })
    
    # Start Prometheus metrics server
    start_http_server(METRICS_PORT)
    print(f"🚀 Telemetry collector started")
    print(f"📊 Metrics available at http://0.0.0.0:{METRICS_PORT}/metrics")
    print(f"🔄 Collection interval: {COLLECTION_INTERVAL}s")
    
    # Main collection loop
    while True:
        try:
            collect_all_metrics()
        except Exception as e:
            print(f"❌ Collection error: {e}")
        
        time.sleep(COLLECTION_INTERVAL)


if __name__ == "__main__":
    main()
