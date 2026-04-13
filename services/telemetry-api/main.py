from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from database import get_db_connection, get_cursor
import uvicorn
import logging
from contextlib import asynccontextmanager
from config import config

# Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("telemetry-api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up...")
    # init_db() # We assume schema is managed externally
    yield
    # Shutdown
    logger.info("Shutting down...")

app = FastAPI(title="OS-BRU Telemetry API", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/devices")
def get_devices():
    try:
        conn = get_db_connection()
        cursor = get_cursor(conn)
        # Query based on Use Case 'OS_BRUC', using correct quoted schema and column names
        query = """
            SELECT d.serial, d.description
            FROM "Uses_cases".devices d
            JOIN "Uses_cases".device_use_case_history h ON d.id = h.device_id
            JOIN "Uses_cases".use_cases u ON h.use_case_id = u.id
            WHERE u.use_case_name = 'OS_BRU'
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()
        # Return objects with serial and description
        return [{"serial": row['serial'], "description": row['description']} for row in rows]
    except Exception as e:
        logger.error(f"Error fetching devices: {e}")
        return []

@app.get("/telemetry")
def get_telemetry(
    device: Optional[str] = None,
    sensor: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 1000 # Increased limit for unpivoting
):
    try:
        conn = get_db_connection()
        # Corrected query to use quoted schema name for "Uses_cases".devices
        query = """
            SELECT t.timestamp, t.temperature, t.humidity, t.voltage, d.serial as device_name 
            FROM os_bru.telemetry t 
            JOIN "Uses_cases".devices d ON t.device_id = d.id 
            WHERE 1=1
        """
        params = []
        
        placeholder = "%s" if config.get("database", {}).get("engine") == "postgresql" else "?"
        
        if device:
            query += f" AND d.serial = {placeholder}"
            params.append(device)
        if start_date:
            query += f" AND t.timestamp >= {placeholder}"
            params.append(start_date)
        if end_date:
            query += f" AND t.timestamp <= {placeholder}"
            params.append(end_date)
            
        query += " ORDER BY t.timestamp DESC LIMIT " + placeholder
        params.append(limit)
        
        cursor = get_cursor(conn)
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        # Unpivot data
        unpivoted_data = []
        for row in rows:
            if row['temperature'] is not None and (not sensor or sensor == 'temperature'):
                unpivoted_data.append({
                    "device_name": row['device_name'],
                    "timestamp": row['timestamp'],
                    "sensor_type": "temperature",
                    "value": row['temperature'],
                    "unit": "°C"
                })
            if row['humidity'] is not None and (not sensor or sensor == 'humidity'):
                unpivoted_data.append({
                    "device_name": row['device_name'],
                    "timestamp": row['timestamp'],
                    "sensor_type": "humidity",
                    "value": row['humidity'],
                    "unit": "%"
                })
            if row['voltage'] is not None and (not sensor or sensor == 'battery'):
                unpivoted_data.append({
                    "device_name": row['device_name'],
                    "timestamp": row['timestamp'],
                    "sensor_type": "battery",
                    "value": row['voltage'],
                    "unit": "V"
                })
                
        return unpivoted_data
        
    except Exception as e:
        logger.error(f"Error fetching telemetry: {e}")
        return []

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    port = config.get("api", {}).get("telemetry_port", 8001)
    host = config.get("api", {}).get("host", "0.0.0.0")
    uvicorn.run("main:app", host=host, port=port, reload=True)
