# OS-BRU | Central Client Server (Microservices)

Professional, scalable dashboard and API suite for OS-BRU IoT devices.

## Features
- **Advanced Microservices**: Decoupled ingestion, telemetry, and image management.
- **High Performance**: PostgreSQL for telemetry and Nginx for high-speed delivery.
- **Professional UI**: Modern, responsive dashboard with advanced charts and gallery.
- **Dockerized**: Entire stack orchestrate with Docker Compose.

## Architecture
- **Gateway (Nginx)**: Routes traffic to appropriate services.
- **Ingestor (Python)**: Subscribes to MQTT and persists data.
- **Telemetry API (FastAPI)**: Serves sensor data from PostgreSQL.
- **Image API (FastAPI)**: Manages MinIO interactions and presigned URLs.
- **Database (PostgreSQL)**: Reliable persistent storage.

## Quick Start (Docker)

1. **Configure**:
   Update `services/telemetry-api/config.yaml` with your MQTT and MinIO credentials.

2. **Launch**:
   ```bash
   cd "Client Server"
   docker-compose up --build
   ```

3. **Access**:
   - Dashboard: `http://localhost`
   - Telemetry API Docs: `http://localhost/api/telemetry/docs`
   - Image API Docs: `http://localhost/api/images/docs`

## Manual Setup (Development)
If you prefer to run services manually, navigate to each service in `services/`, install `requirements.txt`, and run `python main.py`. Ensure you have a running PostgreSQL instance and a Gateway (or adjust frontend `config.js`).

## MQTT Logging
The ingestor now writes MQTT activity to `services/ingestor/logs/ingestor.log` and also prints the same entries to stdout. You can tune the behavior in `services/ingestor/config.yaml` under `logging`:

- `level`: standard Python log level such as `INFO` or `DEBUG`
- `file`: log file path
- `max_bytes` and `backup_count`: rotation settings
- `log_mqtt_messages`: enable or disable per-message MQTT logging
- `mqtt_payload_preview_bytes`: limit how much payload content is written per message
