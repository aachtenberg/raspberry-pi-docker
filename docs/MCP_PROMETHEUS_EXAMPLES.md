# Prometheus MCP Server - Usage Examples

This guide shows practical examples of querying Prometheus through the MCP server conversationally.

## What You Can Do

With the Prometheus MCP server, you can interact with your monitoring data using natural language instead of writing PromQL queries manually.

## Basic Queries

### Check System Status

**You ask:**
> "Claude, are all my Prometheus targets healthy?"

**What I'll do:**
- Query `up` metric to see which targets are responding
- Show you which services are up/down
- Alert you to any failing scrape targets

**You ask:**
> "Show me all metrics being collected"

**What I'll do:**
- List all available metric names
- Group them by job/exporter
- Help you discover what data you have

---

## Resource Monitoring

### CPU Usage

**You ask:**
> "What's the current CPU usage on the Raspberry Pi?"

**What I'll do:**
- Query: `100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)`
- Show current CPU percentage
- Break down by CPU core if needed

**You ask:**
> "Show me CPU usage trend for the last hour"

**What I'll do:**
- Query CPU metrics over time
- Show trends and spikes
- Identify peak usage periods

### Memory Usage

**You ask:**
> "How much memory is being used?"

**What I'll do:**
- Query: `(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes * 100`
- Show current memory percentage
- Break down by available, used, cached

**You ask:**
> "Which container is using the most memory?"

**What I'll do:**
- Query: `sum(container_memory_usage_bytes) by (name)`
- Rank containers by memory usage
- Show memory limits if configured

---

## Container Metrics

### Container Resource Usage

**You ask:**
> "Show me resource usage for all Docker containers"

**What I'll do:**
- Query CPU: `rate(container_cpu_usage_seconds_total[5m]) * 100`
- Query Memory: `container_memory_usage_bytes`
- Show table with container name, CPU%, and memory

**You ask:**
> "Is InfluxDB using too much CPU?"

**What I'll do:**
- Query: `rate(container_cpu_usage_seconds_total{name="influxdb"}[5m])`
- Compare against historical average
- Suggest if it's abnormal

### Network Traffic

**You ask:**
> "How much network traffic is Grafana handling?"

**What I'll do:**
- Query: `rate(container_network_receive_bytes_total{name="grafana"}[5m])`
- Query: `rate(container_network_transmit_bytes_total{name="grafana"}[5m])`
- Show inbound/outbound bandwidth

---

## Temperature Monitoring

### Current Temperatures

**You ask:**
> "What's the temperature in each room right now?"

**What I'll do:**
- Query InfluxDB metrics exposed to Prometheus (if configured)
- Show current readings per sensor
- Flag any abnormal readings

**You ask:**
> "Show me temperature trends from the past 24 hours"

**What I'll do:**
- Query temperature metrics over 24h window
- Calculate min/max/average per sensor
- Identify trends (rising, falling, stable)

---

## Disk and Storage

### Disk Space

**You ask:**
> "How much disk space is left?"

**What I'll do:**
- Query: `(node_filesystem_avail_bytes / node_filesystem_size_bytes) * 100`
- Show percentage free per mount point
- Warn if any are running low

**You ask:**
> "Which volumes are growing the fastest?"

**What I'll do:**
- Query filesystem size changes over time
- Calculate growth rate per volume
- Predict when space will run out

---

## Performance Analysis

### Query Response Times

**You ask:**
> "Is InfluxDB responding slowly?"

**What I'll do:**
- Query HTTP request duration metrics
- Show p50, p95, p99 latencies
- Compare to baseline performance

### Scrape Success Rate

**You ask:**
> "Are there any scrape failures?"

**What I'll do:**
- Query: `up` and `scrape_samples_scraped`
- Show which targets are failing
- Display error counts and reasons

---

## Alerting

### Check Active Alerts

**You ask:**
> "Are there any Prometheus alerts firing?"

**What I'll do:**
- Query `/api/v1/alerts` endpoint
- List active alerts with severity
- Show alert descriptions and values

**You ask:**
> "What alert rules are configured?"

**What I'll do:**
- Query `/api/v1/rules` endpoint
- List all alert rules
- Show conditions and thresholds

---

## Advanced Queries

### Custom Metrics

**You ask:**
> "Calculate the average request rate to Grafana over the past hour"

**What I'll do:**
- Query: `rate(http_requests_total{job="grafana"}[1h])`
- Calculate average across time window
- Break down by endpoint if available

### Correlations

**You ask:**
> "When CPU spikes, does memory usage also increase?"

**What I'll do:**
- Query both CPU and memory metrics
- Analyze correlation over time
- Show if they're related or independent

### Comparisons

**You ask:**
> "Compare container resource usage: Grafana vs InfluxDB"

**What I'll do:**
- Query metrics for both containers
- Show side-by-side comparison
- Highlight which uses more resources

---

## Troubleshooting Scenarios

### Performance Investigation

**Scenario:** Your dashboard is loading slowly

**You ask:**
> "Claude, help me debug slow dashboard performance"

**What I'll do:**
1. Check Grafana CPU/memory usage
2. Check InfluxDB query performance
3. Look for network issues
4. Check disk I/O metrics
5. Identify the bottleneck

### Container Restart Investigation

**Scenario:** A container keeps restarting

**You ask:**
> "Why did the Loki container restart?"

**What I'll do:**
1. Check memory usage trends before restart
2. Look for OOM (Out of Memory) kills
3. Check CPU spikes
4. Review error rates
5. Suggest potential causes

---

## Discovery and Exploration

### Metric Discovery

**You ask:**
> "What metrics are available for node-exporter?"

**What I'll do:**
- Query: `{job="node-exporter"}` labels
- List all metric families
- Explain what each metric measures

### Label Exploration

**You ask:**
> "What labels are on the container_memory_usage_bytes metric?"

**What I'll do:**
- Query metric metadata
- Show all available labels (name, id, image, etc.)
- Explain how to filter using labels

---

## Real Example Queries

Here are actual PromQL queries the MCP server might execute:

```promql
# CPU usage per container
sum(rate(container_cpu_usage_seconds_total[5m])) by (name) * 100

# Memory usage percentage
(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes * 100

# Disk I/O per device
rate(node_disk_read_bytes_total[5m])
rate(node_disk_written_bytes_total[5m])

# Network bandwidth
rate(node_network_receive_bytes_total[5m])
rate(node_network_transmit_bytes_total[5m])

# Container restarts
changes(container_start_time_seconds[1h]) > 0

# Top 5 containers by CPU
topk(5, sum(rate(container_cpu_usage_seconds_total[5m])) by (name))

# Grafana request rate
sum(rate(http_request_duration_seconds_count{job="grafana"}[5m]))

# Available disk space
node_filesystem_avail_bytes{fstype!~"tmpfs|fuse.*"} / node_filesystem_size_bytes * 100
```

---

## Tips for Effective Use

### Be Specific
❌ "Show me metrics"
✅ "Show me CPU usage for the last hour"

### Ask Follow-up Questions
"That CPU spike at 2pm - what else happened at that time?"

### Request Comparisons
"Compare this week's average CPU to last week"

### Ask for Context
"Is 80% memory usage normal for this system?"

### Request Visualizations
"Can you format that as a table?" or "Show the top 5 only"

---

## Common Use Cases

### Daily Health Check
> "Claude, give me a health check of all services"

### Capacity Planning
> "At the current growth rate, when will I run out of disk space?"

### Incident Response
> "What happened around 3pm when the system slowed down?"

### Optimization
> "Which containers could I optimize to save memory?"

### Trend Analysis
> "Is CPU usage trending up or down this week?"

---

## Limitations

The MCP server **cannot**:
- Modify Prometheus configuration
- Delete metrics or data
- Change alert rules
- Restart Prometheus

It's **read-only** for safety - perfect for querying and analysis!

---

## Next Steps

1. **Try it out**: Restart VSCode to activate the MCP server
2. **Start simple**: Ask "Show me all Prometheus targets"
3. **Get specific**: Ask about CPU, memory, or specific containers
4. **Explore**: Ask what metrics are available
5. **Combine**: Use with Docker MCP to correlate metrics with container state

---

## See Also

- [MCP_SERVERS.md](MCP_SERVERS.md) - Complete MCP server documentation
- [Prometheus Documentation](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [PromQL Basics](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Node Exporter Metrics](https://github.com/prometheus/node_exporter)
