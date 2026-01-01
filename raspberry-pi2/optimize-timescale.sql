-- Comprehensive TimescaleDB Optimization Script
-- Converts Telegraf-created tables into hypertables and enables compression

-- Function to safely create hypertable
CREATE OR REPLACE FUNCTION create_hypertable_if_not_exists(tbl_name TEXT, time_col TEXT) 
RETURNS VOID AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM timescaledb_information.hypertables WHERE hypertable_name = tbl_name) THEN
        -- Convert time column to TIMESTAMPTZ for best practices
        EXECUTE format('ALTER TABLE %I ALTER COLUMN %I TYPE TIMESTAMPTZ USING %I AT TIME ZONE ''UTC''', tbl_name, time_col, time_col);
        -- Create hypertable with data migration
        PERFORM create_hypertable(tbl_name, time_col, chunk_time_interval => INTERVAL '7 days', migrate_data => true);
    END IF;
END;
$$ LANGUAGE plpgsql;

-- 1. Convert main sensor tables to hypertables
SELECT create_hypertable_if_not_exists('esp_temperature', 'time');
SELECT create_hypertable_if_not_exists('esp_status', 'time');
SELECT create_hypertable_if_not_exists('surveillance', 'time');

-- 2. Convert Docker monitoring tables
SELECT create_hypertable_if_not_exists('docker', 'time');
SELECT create_hypertable_if_not_exists('docker_container_cpu', 'time');
SELECT create_hypertable_if_not_exists('docker_container_mem', 'time');
SELECT create_hypertable_if_not_exists('docker_container_net', 'time');
SELECT create_hypertable_if_not_exists('docker_container_blkio', 'time');
SELECT create_hypertable_if_not_exists('docker_container_status', 'time');

-- 3. Enable Compression on all hypertables
DO $$
DECLARE
    ht RECORD;
    seg_col TEXT;
BEGIN
    FOR ht IN SELECT hypertable_name FROM timescaledb_information.hypertables LOOP
        -- Check if 'device' or 'host' column exists for segmentation
        IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = ht.hypertable_name AND column_name = 'device') THEN
            seg_col := 'device';
        ELSIF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = ht.hypertable_name AND column_name = 'host') THEN
            seg_col := 'host';
        ELSE
            seg_col := NULL;
        END IF;

        IF seg_col IS NOT NULL THEN
            -- Enable compression on the table
            EXECUTE format('ALTER TABLE %I SET (timescaledb.compress, timescaledb.compress_segmentby = %L)', ht.hypertable_name, seg_col);
            
            -- Add compression policy (check if it exists first)
            IF NOT EXISTS (SELECT 1 FROM timescaledb_information.jobs WHERE hypertable_name = ht.hypertable_name AND proc_name = 'policy_compression') THEN
                -- Use explicit cast to regclass for the table name
                EXECUTE format('SELECT add_compression_policy(%L, INTERVAL ''14 days'')', ht.hypertable_name);
            END IF;
        END IF;
    END LOOP;
END $$;

-- 4. Verify results
SELECT hypertable_name, compression_enabled 
FROM timescaledb_information.hypertables;

-- 4. Cleanup
DROP FUNCTION create_hypertable_if_not_exists(TEXT, TEXT);

-- 5. Verify
SELECT hypertable_name, compression_enabled FROM timescaledb_information.hypertables;
