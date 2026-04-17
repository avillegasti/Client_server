from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from database import get_db_connection, get_cursor
import uvicorn
import logging
from contextlib import asynccontextmanager
from config import config
from datetime import datetime, timedelta

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


def get_placeholder() -> str:
    return "%s" if config.get("database", {}).get("engine") == "postgresql" else "?"


def parse_end_date(end_date: Optional[str]):
    if not end_date:
        return None, False

    if len(end_date) == 10:
        try:
            return datetime.fromisoformat(end_date) + timedelta(days=1), True
        except ValueError:
            return end_date, False

    return end_date, False


def append_date_filters(query: str, params: list, start_date: Optional[str], end_date: Optional[str], column_name: str):
    placeholder = get_placeholder()

    if start_date:
        query += f" AND {column_name} >= {placeholder}"
        params.append(start_date)

    end_value, use_exclusive_end = parse_end_date(end_date)
    if end_value is not None:
        operator = "<" if use_exclusive_end else "<="
        query += f" AND {column_name} {operator} {placeholder}"
        params.append(end_value)

    return query, params


def to_number(value):
    return float(value) if value is not None else None


def row_value(row, key):
    return row[key] if key in row.keys() else None


def build_overview_entry(row):
    serial = row["serial"]
    label = row_value(row, "description") or serial
    return {
        "serial": serial,
        "device_name": label,
        "latest_timestamp": None,
        "temperature": None,
        "humidity": None,
        "battery": None,
        "image_count": 0,
        "trend": {
            "temperature": [],
            "humidity": [],
            "battery": [],
        }
    }


def build_series_entry(row):
    serial = row["serial"]
    label = row_value(row, "description") or serial
    return {
        "serial": serial,
        "device_name": label,
        "series": {
            "temperature": [],
            "humidity": [],
            "battery": [],
        }
    }

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
        placeholder = get_placeholder()
        
        if device:
            query += f" AND d.serial = {placeholder}"
            params.append(device)
        query, params = append_date_filters(query, params, start_date, end_date, "t.timestamp")
            
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


@app.get("/overview")
def get_overview(
    device: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    trend_points: int = 8
):
    conn = None
    try:
        conn = get_db_connection()
        cursor = get_cursor(conn)
        placeholder = get_placeholder()

        devices_query = """
            SELECT d.id, d.serial, d.description
            FROM "Uses_cases".devices d
            JOIN "Uses_cases".device_use_case_history h ON d.id = h.device_id
            JOIN "Uses_cases".use_cases u ON h.use_case_id = u.id
            WHERE u.use_case_name = 'OS_BRU'
        """
        device_params = []
        if device:
            devices_query += f" AND d.serial = {placeholder}"
            device_params.append(device)

        devices_query += " ORDER BY COALESCE(d.description, d.serial)"
        cursor.execute(devices_query, device_params)
        device_rows = cursor.fetchall()

        overview_by_serial = {
            row["serial"]: build_overview_entry(row)
            for row in device_rows
        }

        telemetry_query = f"""
            WITH ranked_telemetry AS (
                SELECT
                    t.device_id,
                    d.serial,
                    d.description,
                    t.timestamp,
                    t.temperature,
                    t.humidity,
                    t.voltage,
                    ROW_NUMBER() OVER (
                        PARTITION BY t.device_id
                        ORDER BY t.timestamp DESC
                    ) AS rn
                FROM os_bru.telemetry t
                JOIN "Uses_cases".devices d ON t.device_id = d.id
                WHERE 1=1
        """
        telemetry_params = []
        if device:
            telemetry_query += f" AND d.serial = {placeholder}"
            telemetry_params.append(device)
        telemetry_query, telemetry_params = append_date_filters(
            telemetry_query,
            telemetry_params,
            start_date,
            end_date,
            "t.timestamp"
        )
        telemetry_query += f"""
            )
            SELECT device_id, serial, description, timestamp, temperature, humidity, voltage, rn
            FROM ranked_telemetry
            WHERE rn <= {placeholder}
            ORDER BY COALESCE(description, serial), timestamp DESC
        """
        telemetry_params.append(trend_points)
        cursor.execute(telemetry_query, telemetry_params)
        telemetry_rows = cursor.fetchall()

        for row in telemetry_rows:
            serial = row["serial"]
            entry = overview_by_serial.setdefault(serial, build_overview_entry(row))

            if row["rn"] == 1:
                entry["latest_timestamp"] = row["timestamp"]
                entry["temperature"] = to_number(row["temperature"])
                entry["humidity"] = to_number(row["humidity"])
                entry["battery"] = to_number(row["voltage"])

            if row["temperature"] is not None:
                entry["trend"]["temperature"].append({
                    "timestamp": row["timestamp"],
                    "value": to_number(row["temperature"]),
                })
            if row["humidity"] is not None:
                entry["trend"]["humidity"].append({
                    "timestamp": row["timestamp"],
                    "value": to_number(row["humidity"]),
                })
            if row["voltage"] is not None:
                entry["trend"]["battery"].append({
                    "timestamp": row["timestamp"],
                    "value": to_number(row["voltage"]),
                })

        image_query = """
            SELECT d.serial, COUNT(*) AS image_count
            FROM os_bru.images i
            JOIN "Uses_cases".devices d ON i.device_id = d.id
            WHERE 1=1
        """
        image_params = []
        if device:
            image_query += f" AND d.serial = {placeholder}"
            image_params.append(device)
        image_query, image_params = append_date_filters(
            image_query,
            image_params,
            start_date,
            end_date,
            "i.captured_at"
        )
        image_query += " GROUP BY d.serial"

        cursor.execute(image_query, image_params)
        for row in cursor.fetchall():
            serial = row["serial"]
            if serial in overview_by_serial:
                overview_by_serial[serial]["image_count"] = int(row["image_count"])

        overview_items = [
            item for item in overview_by_serial.values()
            if item["latest_timestamp"] is not None or item["image_count"] > 0 or device
        ]
        overview_items.sort(key=lambda item: item["device_name"])
        return overview_items
    except Exception as e:
        logger.error(f"Error fetching overview: {e}")
        return []
    finally:
        if conn:
            conn.close()


@app.get("/series")
def get_series(
    device: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    points_per_device: int = 100
):
    conn = None
    try:
        conn = get_db_connection()
        cursor = get_cursor(conn)
        placeholder = get_placeholder()

        devices_query = """
            SELECT d.id, d.serial, d.description
            FROM "Uses_cases".devices d
            JOIN "Uses_cases".device_use_case_history h ON d.id = h.device_id
            JOIN "Uses_cases".use_cases u ON h.use_case_id = u.id
            WHERE u.use_case_name = 'OS_BRU'
        """
        device_params = []
        if device:
            devices_query += f" AND d.serial = {placeholder}"
            device_params.append(device)

        devices_query += " ORDER BY COALESCE(d.description, d.serial)"
        cursor.execute(devices_query, device_params)
        device_rows = cursor.fetchall()

        series_by_serial = {
            row["serial"]: build_series_entry(row)
            for row in device_rows
        }

        telemetry_query = f"""
            WITH ranked_telemetry AS (
                SELECT
                    t.device_id,
                    d.serial,
                    d.description,
                    t.timestamp,
                    t.temperature,
                    t.humidity,
                    t.voltage,
                    ROW_NUMBER() OVER (
                        PARTITION BY t.device_id
                        ORDER BY t.timestamp DESC
                    ) AS rn
                FROM os_bru.telemetry t
                JOIN "Uses_cases".devices d ON t.device_id = d.id
                WHERE 1=1
        """
        telemetry_params = []
        if device:
            telemetry_query += f" AND d.serial = {placeholder}"
            telemetry_params.append(device)
        telemetry_query, telemetry_params = append_date_filters(
            telemetry_query,
            telemetry_params,
            start_date,
            end_date,
            "t.timestamp"
        )
        telemetry_query += f"""
            )
            SELECT serial, description, timestamp, temperature, humidity, voltage
            FROM ranked_telemetry
            WHERE rn <= {placeholder}
            ORDER BY COALESCE(description, serial), timestamp DESC
        """
        telemetry_params.append(points_per_device)
        cursor.execute(telemetry_query, telemetry_params)

        for row in cursor.fetchall():
            serial = row["serial"]
            entry = series_by_serial.setdefault(serial, build_series_entry(row))

            if row["temperature"] is not None:
                entry["series"]["temperature"].append({
                    "timestamp": row["timestamp"],
                    "value": to_number(row["temperature"]),
                })
            if row["humidity"] is not None:
                entry["series"]["humidity"].append({
                    "timestamp": row["timestamp"],
                    "value": to_number(row["humidity"]),
                })
            if row["voltage"] is not None:
                entry["series"]["battery"].append({
                    "timestamp": row["timestamp"],
                    "value": to_number(row["voltage"]),
                })

        series_items = []
        for item in series_by_serial.values():
            for sensor_name in ("temperature", "humidity", "battery"):
                item["series"][sensor_name].reverse()

            has_series = any(item["series"][sensor_name] for sensor_name in item["series"])
            if has_series or device:
                series_items.append(item)

        series_items.sort(key=lambda item: item["device_name"])
        return series_items
    except Exception as e:
        logger.error(f"Error fetching telemetry series: {e}")
        return []
    finally:
        if conn:
            conn.close()

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    port = config.get("api", {}).get("telemetry_port", 8001)
    host = config.get("api", {}).get("host", "0.0.0.0")
    uvicorn.run("main:app", host=host, port=port, reload=True)
