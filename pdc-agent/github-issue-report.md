# GitHub Issue Report for grafana/pdc-agent

**Repository:** https://github.com/grafana/pdc-agent/issues/new

---

## Title
`pdc-agent:0.0.50` fails on ARM64 with broken OpenSSL libraries - "invalid SSH version: exit status 127"

## Description

### Summary
The `grafana/pdc-agent:0.0.50` Docker image (released 2025-12-16) has broken OpenSSL library dependencies on ARM64 architecture, causing the container to crash loop with SSH initialization failures.

### Environment
- **Architecture:** ARM64 (Raspberry Pi 4, 8GB)
- **OS:** Raspberry Pi OS (Debian-based)
- **Docker Version:** 27.x
- **Image:** `grafana/pdc-agent:0.0.50` and `grafana/pdc-agent:0.0.50-arm64`
- **Working Version:** `grafana/pdc-agent:0.0.48`

### Error Messages
```
level=error caller=main.go:197 ts=2025-12-17T21:34:38.985209413Z msg="cannot start ssh client: invalid SSH version: failed to run ssh -V command: exit status 127"
level=error caller=main.go:148 ts=2025-12-17T21:34:38.985349208Z err="invalid SSH version: failed to run ssh -V command: exit status 127"
```

### Root Cause
When attempting to execute `/usr/bin/ssh -V` inside the container, it fails with:
```
Error relocating /usr/lib/libcrypto.so.3: : symbol not found
Error relocating /usr/lib/libcrypto.so.3: : symbol not found
Error relocating /usr/lib/libcrypto.so.3: : symbol not found
Error relocating /usr/lib/libcrypto.so.3: : symbol not found
```

The SSH binary exists at `/usr/bin/ssh` but has broken dynamic library dependencies for OpenSSL.

### Reproduction Steps
```bash
# Pull the affected image
docker pull grafana/pdc-agent:0.0.50

# Attempt to run SSH version check
docker run --rm --entrypoint /bin/sh grafana/pdc-agent:0.0.50 -c "ssh -V"
# Result: Error relocating /usr/lib/libcrypto.so.3: symbol not found

# Compare with working version
docker pull grafana/pdc-agent:0.0.48
docker run --rm --entrypoint /bin/sh grafana/pdc-agent:0.0.48 -c "ssh -V"
# Result: OpenSSH_10.2p1, OpenSSL 3.5.4 30 Sep 2025
```

### Impact
- **Severity:** Critical - Container is completely non-functional on ARM64
- **Scope:** All ARM64 users (Raspberry Pi, AWS Graviton, etc.)
- **Timeline:** Broken since v0.0.50 release on 2025-12-16
- **Workaround:** Pin to `grafana/pdc-agent:0.0.48`

### Workaround
```yaml
# docker-compose.yml
pdc-agent:
  image: grafana/pdc-agent:0.0.48  # Pin to last working version
  container_name: pdc-agent
  restart: unless-stopped
  # ... rest of config
```

### Additional Context
- The issue manifested after a power outage when Docker automatically pulled `:latest`
- Version 0.0.48 (released 2025-11-24) works correctly with OpenSSL 3.5.4
- The ARM64-specific tag (`0.0.50-arm64`) has the same issue
- No issues reported on AMD64 architecture

### Expected Behavior
The SSH client should initialize successfully and connect to Grafana Cloud's Private Datasource Connect service.

### Actual Behavior
Container enters crash loop with OpenSSL symbol resolution failures.

### Request
Please investigate the OpenSSL library packaging in the 0.0.50 ARM64 build. There may be a missing or incompatible library version in the build pipeline.

---

**Related Issues:**
- Potentially related to #124 (Support other distros as docker base image)

**System Information:**
```
PDC agent info: version=v0.0.50 commit=07213502f1c36127a6a56ae189c7670598e22736 date=2025-12-16T22:25:58Z sshversion=UNKNOWN os=linux arch=arm64
```
