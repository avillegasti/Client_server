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
