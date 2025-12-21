# Surveillance Dashboard: Phased Implementation Plan

## Overview
- **Goal**: A unified web interface to view ≥5 cameras (live grid + per-camera live + motion gallery) and manage historical captures, using existing Raspberry Pi infrastructure.
- **Topology**: 
  - **Pi 1** (existing): Mosquitto, Telegraf, InfluxDB 3 Core, Prometheus, Nginx Proxy Manager, Cloudflare Tunnel
  - **Pi 2** (current stack): PostgreSQL, Node/Express API, Web UI (iframe-only), SFTP server
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
- **Event pipeline**: MQTT signaling planned (`surveillance/+/motion|image|status`) → Telegraf → InfluxDB 3 → Grafana Cloud (not yet wired; depends on sample payloads).
- **Image pipeline**: ESP32/other cameras upload JPEGs to Pi 2 SFTP → NAS path `/surveillance/captures/{device}/` → API to index/serve (image indexing still pending).
- **Live streaming**: Deferred. Mediamtx and HLS/WebRTC are removed from the active stack; revisit only if we add RTSP IP cams later.

## Phases

### Phase 0 — Discovery & Pre‑Requisites *(Status: DONE)*
- Confirm Pi 1 NPM setup (host/container), available vhost, Cloudflare Tunnel status.
- Verify `/mnt/nas-backup` on Pi 2 (read/write) and permissions for containers.
- Choose dashboard hostname (e.g., `camera-dashboard.local` or public via Tunnel).
- **Acceptance**: Paths verified, hostname decided, secrets approach documented.

### Phase 1 — Storage & SFTP Ingestion *(Status: DONE)*
- SFTP container on Pi 2 running; mount `/mnt/nas-backup/surveillance/captures` → `/camera-uploads`.
- Per‑camera SSH keys: ESP32 key authorized; directories created (`/camera-uploads/IDKCam`, `/camera-uploads/Surveillance Cam`).
- Retention job still pending (14–30 day purge/archive not yet wired).
- **Acceptance**: Uploads land on NAS confirmed (multiple JPEGs from ESP32 in `/camera-uploads/IDKCam/`).

### Phase 2 — Metadata DB & API *(Status: PARTIAL)*
- PostgreSQL + Pool configured; `cameras` table auto-created; API routes: `GET /api/health`, `GET /api/cameras`, `POST /api/cameras`, `DELETE /api/cameras/:id`.
- Not yet implemented: `motion_events`, `images` tables; indexing NAS files; auth in front of API.
- **Acceptance (current)**: API returns cameras from DB and health ok — ✅. **Open**: image/event metadata.

### Phase 3 — Web UI (Gallery & Timeline) *(Status: NOT STARTED)*
- Current UI is iframe-only (MJPEG) without gallery. Need gallery/timeline backed by indexed NAS files.
- Add lightbox, filters, pagination; basic auth via NPM.
- **Acceptance**: Gallery displays captured images per device/date with working filters.

### Phase 4 — Live Streaming (Unified Live View) *(Status: DEFERRED)*
- Mediamtx removed from stack; no HLS/WebRTC in current scope. Revisit if IP cams/RTSP are added.
- **Acceptance**: Not in scope until revisited.

### Phase 5 — Exposure & Remote Access *(Status: NOT STARTED)*
- Pi 1 NPM vhost: proxy `/` → UI, `/api` → API, `/streams/*` → Mediamtx HTTP on Pi 2.
- Enable gzip, static asset caching, and basic auth; rate‑limit requests.
- Cloudflare Tunnel publishes the vhost publicly (optional); keep RTSP private.
- **Acceptance**: External access works via Tunnel; auth enforced; no RTSP exposed.

### Phase 6 — Analytics (Grafana Cloud) *(Status: NOT STARTED)*
- Telegraf → InfluxDB 3 wiring for `surveillance/#` pending sample MQTT payloads.
- Grafana Cloud dashboards TBD.
- **Acceptance**: Motion trends visible via FlightSQL once data exists.

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
