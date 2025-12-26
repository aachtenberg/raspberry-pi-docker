# Surveillance Dashboard: Phased Implementation Plan

## Overview
- **Goal**: A unified web interface to view ≥5 cameras (live grid + per-camera live + motion gallery) and manage historical captures, using existing Raspberry Pi infrastructure.
- **Topology**: 
  - **Pi 1** (existing): Mosquitto, Telegraf, InfluxDB 3 Core, Prometheus, Nginx Proxy Manager, Cloudflare Tunnel
  - **Pi 2** (new stack): PostgreSQL, Node/Express API, Web UI (SPA), SFTP server, Streaming server (Mediamtx)
  - **Pi 3**: Idle/standby for future scaling or batch jobs
- **Storage**: Shared NAS mount at `/mnt/nas-backup` (captures under `/mnt/nas-backup/surveillance/captures/{device}/`).
- **Visualization**: Grafana Cloud via FlightSQL to InfluxDB 3; local Grafana is deprecated.

## Non‑Negotiables & Conventions (from repo instructions)
- Use `docker compose` (no hyphen); validate with `docker compose config -q`.
- **Never commit `.env`**; use `.env.example` placeholders; hooks prevent secret commits.
- Conventional commits: `feat:`, `fix:`, `docs:`, `chore:`; run `./scripts/setup-git-hooks.sh` if needed.
- InfluxDB 3 requires bearer token; generate inside container and store locally.
- Nginx Proxy Manager host configs live under `nginx-proxy-manager/data/nginx/proxy_host/*.conf`; reload via container.
- Prefer Grafana Cloud over local Grafana; use FlightSQL for InfluxDB 3.

## Architecture & Data Flow
- **Event pipeline**: Cameras publish MQTT `surveillance/+/motion` → Telegraf → InfluxDB 3 → Grafana Cloud analytics.
- **Image pipeline**: Cameras upload JPEGs to Pi 2 SFTP → NAS path `/surveillance/captures/{device}/` → API indexes filenames in PostgreSQL.
- **Live streaming**: Hardware IP cameras (RTSP) ingested by **Mediamtx** on Pi 2 → exposed as **HLS/LL‑HLS** (Option A, default) or **WebRTC** (Option B) to the browser via NPM on Pi 1.

## Phases

### Phase 0 — Discovery & Pre‑Requisites
- Confirm Pi 1 NPM setup (host/container), available vhost, Cloudflare Tunnel status.
- Verify `/mnt/nas-backup` on Pi 2 (read/write) and permissions for containers.
- Choose dashboard hostname (e.g., `camera-dashboard.local` or public via Tunnel).
- **Acceptance**: Paths verified, hostname decided, secrets approach documented.

### Phase 1 — Storage & SFTP Ingestion
- Add SFTP container on Pi 2; mount `/mnt/nas-backup/surveillance/captures`.
- Per‑camera SSH keys; directory scheme `/captures/{device}/YYYY/MM/DD/filename.jpg`.
- Retention policy (14–30 days) with nightly purge/archive job.
- **Deliverables**: Compose service, directory layout, key management docs.
- **Acceptance**: Upload from a test camera lands on NAS; retention job runs.

### Phase 2 — Metadata DB & API
- PostgreSQL schema: `cameras(id, name, rtsp_url, enabled)`, `motion_events(id, device_id, ts, score, image_path)`, `images(id, device_id, ts, path, size, motion_triggered)`; indexes on `(device_id, ts)`.
- Node/Express API: `GET /api/cameras`, `GET /api/events`, `GET /api/images`, `GET /api/health`; auth (token/basic) behind NPM.
- **Deliverables**: SQL migrations, API routes, health checks.
- **Acceptance**: API returns sample data; metadata links resolve to NAS paths.

### Phase 3 — Web UI (Gallery & Timeline)
- SPA with views: **Live Grid**, **Per‑Camera Page**, **Motion Gallery** (filter by device/date), **Timeline**.
- Lightbox viewer for JPEGs; pagination; basic auth via NPM.
- **Deliverables**: UI build, asset caching, responsive layout.
- **Acceptance**: Gallery displays captured images per device; filters work.

### Phase 4 — Live Streaming (Unified Live View)
- **Default (Option A)**: HLS/LL‑HLS via **Mediamtx**. Ingest RTSP from each camera; re‑mux H.264 → HLS (avoid transcoding where possible). Expose `/streams/{camera}/index.m3u8`.
- **Alternative (Option B)**: WebRTC via Mediamtx/SRS for near‑real‑time. Requires signaling endpoints; consider STUN/TURN if needed.
- Grid view shows 5 camera players; per‑camera page has full player with stats.
- **Deliverables**: Compose service for Mediamtx; stream configs; UI players.
- **Acceptance**: All 5 cameras playable in grid; acceptable latency/profile.

### Phase 5 — Exposure & Remote Access
- Pi 1 NPM vhost: proxy `/` → UI, `/api` → API, `/streams/*` → Mediamtx HTTP on Pi 2.
- Enable gzip, static asset caching, and basic auth; rate‑limit requests.
- Cloudflare Tunnel publishes the vhost publicly (optional); keep RTSP private.
- **Acceptance**: External access works via Tunnel; auth enforced; no RTSP exposed.

### Phase 6 — Analytics (Grafana Cloud)
- Ensure Telegraf consumes `surveillance/#` and writes to InfluxDB 3.
- Build Grafana Cloud panels via FlightSQL (motion heatmaps, time‑of‑day patterns).
- **Acceptance**: Dashboards show motion trends by camera; queries perform.

### Phase 7 — Security & Compliance
- Secrets: `.env` local only; `.env.example` placeholders; validate via scripts.
- Streaming auth: Mediamtx users/tokens; NPM basic auth; restrict origins.
- Network isolation: RTSP stays on LAN; only HTTP(S) paths via NPM/Tunnel.
- **Acceptance**: Secret scans pass; unauthorized access blocked; logs collected.

### Phase 8 — Operations & Monitoring
- Backups: leverage existing NAS/systemd backup scripts; include PostgreSQL dumps and configs.
- Monitoring: Prometheus scrape for API/stream health; alerts on failed uploads or consumer lag.
- Retention: scheduled purge archive of images; disk usage monitoring.
- **Acceptance**: Backups verified; alert rules fire; retention keeps usage stable.

### Phase 9 — Rollout & Camera Onboarding
- Pilot with 1–2 cameras; add device entries; verify SFTP + MQTT + streams.
- Scale to 5 cameras; confirm CPU and bandwidth; adjust profiles/substreams.
- **Acceptance**: Stable operation with 5 cameras; performance within targets.

### Phase 10 — Future Enhancements
- MQTT thumbnails for instant UI previews; full‑res via SFTP.
- AI event classification; per‑camera alerting; role‑based access.
- Mobile‑friendly UI; Pi 3 for transcoding or CDN‑like caching.

## Risks & Mitigations
- **CPU/transcoding**: Prefer re‑mux over transcoding; use lower‑bitrate substreams.
- **Latency**: HLS adds seconds; LL‑HLS/WebRTC reduce latency; choose based on need.
- **Permissions**: Ensure NAS write for SFTP and read for UI/API; NPM perms.
- **Storage growth**: Retention/purge + monitoring; scale NAS as needed.
- **Remote exposure**: Only publish HTTP(S) via Tunnel; keep RTSP internal.

## Acceptance Summary
- Each phase includes acceptance checks to validate correctness and readiness.
- Final acceptance: unified live grid and gallery accessible via NPM + Tunnel; analytics in Grafana Cloud; secure, monitored, and backed up.

## Appendix
- **Paths**: NAS `/mnt/nas-backup/surveillance/captures/{device}/`.
- **NPM configs**: `nginx-proxy-manager/data/nginx/proxy_host/*.conf` (tracked in git).
- **Compose**: All new services on Pi 2; share `monitoring` network where applicable.
- **Tokens**: InfluxDB 3 bearer token; Cloudflare Tunnel token; keep in local `.env`.
