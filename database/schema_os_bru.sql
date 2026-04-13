-- Schema for OS-BRU System (Linked to Uses_cases schema)
-- Created: 2026-03-23

CREATE SCHEMA IF NOT EXISTS os_bru;

-- 1. Structured Telemetry
-- Links to central devices and use_cases tables
CREATE TABLE IF NOT EXISTS os_bru.telemetry (
    id          BIGSERIAL PRIMARY KEY,
    device_id   BIGINT NOT NULL,
    temperature       NUMERIC(12, 4),
    humidity   NUMERIC(12, 4), -- 'temperature', 'humidity', 'battery', etc.
    voltage   NUMERIC(12, 4), -- 'temperature', 'humidity', 'battery', etc.
    timestamp   TIMESTAMP NOT NULL,
    received_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_os_bru_telemetry_device
        FOREIGN KEY (device_id) REFERENCES "Uses_cases".devices(id) ON DELETE CASCADE
);

-- Index for fast dashboard performance
CREATE INDEX IF NOT EXISTS idx_os_bru_telemetry_device_time ON os_bru.telemetry (device_id, timestamp DESC);

-- 2. Image Metadata
-- Tracks files in MinIO
CREATE TABLE IF NOT EXISTS os_bru.images (
    id              BIGSERIAL PRIMARY KEY,
    device_id       BIGINT NOT NULL,
    filename        VARCHAR(255) NOT NULL,
    minio_bucket    VARCHAR(255) DEFAULT 'os-bru-images',
    minio_path      TEXT NOT NULL,
    captured_at     TIMESTAMP NOT NULL,
    file_size_bytes BIGINT,
    metadata        JSONB,
    received_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_os_bru_images_device
        FOREIGN KEY (device_id) REFERENCES "Uses_cases".devices(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_os_bru_images_device_time ON os_bru.images (device_id, captured_at DESC);

-- 3. System & Health Events
CREATE TABLE IF NOT EXISTS os_bru.system_events (
    id          BIGSERIAL PRIMARY KEY,
    device_id   BIGINT NOT NULL,
    event_type  VARCHAR(100) NOT NULL, -- 'reboot', 'vpn_up', 'vpn_down', 'disk_full'
    severity    VARCHAR(20) DEFAULT 'info', -- 'info', 'warning', 'error'
    message     TEXT,
    timestamp   TIMESTAMP NOT NULL,
    CONSTRAINT fk_os_bru_events_device
        FOREIGN KEY (device_id) REFERENCES "Uses_cases".devices(id) ON DELETE CASCADE
);

-- 4. Current Device Status
CREATE TABLE IF NOT EXISTS os_bru.device_status (
    device_id       BIGINT PRIMARY KEY,
    is_online       BOOLEAN DEFAULT FALSE,
    last_telemetry  TIMESTAMP,
    last_image      TIMESTAMP,
    firmware_ver    VARCHAR(50),
    battery_level   NUMERIC(5, 2),
    CONSTRAINT fk_os_bru_status_device
        FOREIGN KEY (device_id) REFERENCES "Uses_cases".devices(id) ON DELETE CASCADE
);
