-- TimescaleDB Initialization Script for Sensor Data
-- Run this inside the timescaledb container:
-- docker exec -i timescaledb psql -U postgres < init-timescale.sql

-- 1. Create the base table (Telegraf will add columns, but we pre-create core ones)
CREATE TABLE IF NOT EXISTS sensor_data (
    time        TIMESTAMPTZ       NOT NULL,
    device      TEXT              NOT NULL,
    topic       TEXT,
    fields      JSONB,
    tags        JSONB
);

-- 2. Transform into a TimescaleDB hypertable (partitioned by time)
-- 7 days is a good balance for Raspberry Pi memory
SELECT create_hypertable('sensor_data', 'time', chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE);

-- 3. Enable Compression (Critical for SD card longevity and performance)
ALTER TABLE sensor_data SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'device'
);

-- 4. Add a compression policy (compress data older than 14 days)
SELECT add_compression_policy('sensor_data', INTERVAL '14 days', if_not_exists => TRUE);

-- 5. Create an index for common lookups
CREATE INDEX IF NOT EXISTS idx_device_time ON sensor_data (device, time DESC);

-- 6. Verify
\d+ sensor_data
SELECT * FROM timescaledb_information.hypertables;
