import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
from config import config
import logging

logger = logging.getLogger("database")

db_cfg = config.get("database", {})
ENGINE = db_cfg.get("engine", "sqlite")

def get_db_connection():
    if ENGINE == "postgresql":
        try:
            conn = psycopg2.connect(
                host=db_cfg.get("host", "localhost"),
                port=db_cfg.get("port", 5432),
                user=db_cfg.get("user", "osbru"),
                password=db_cfg.get("pass", "osbru_pass"),
                dbname=db_cfg.get("name", "osbru_db")
            )
            return conn
        except Exception as e:
            logger.error(f"Error connecting to PostgreSQL: {e}")
            raise
    else:
        DB_PATH = db_cfg.get("path", "telemetry.db")
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

def init_db():
    # Note: We assume the schema has been created via the .sql file
    # But we can add a check if needed.
    pass

def get_device_id(serial: str):
    """Lookup device_id in Uses_cases.devices by serial number."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if ENGINE == "postgresql":
            # Quoted schema name for Uses_cases.devices
            cursor.execute('SELECT id FROM "Uses_cases".devices WHERE serial = %s', (serial,))
        else:
            # Fallback for local sqlite testing if table exists
            cursor.execute("SELECT id FROM devices WHERE serial = ?", (serial,))
        row = cursor.fetchone()
        return row[0] if row else None
    except Exception as e:
        logger.error(f"Error looking up device {serial}: {e}")
        return None
    finally:
        conn.close()

def get_default_use_case_id():
    """Get the first use case or a default one."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if ENGINE == "postgresql":
            # Quoted schema name for Uses_cases.use_cases
            cursor.execute('SELECT id FROM "Uses_cases".use_cases LIMIT 1')
        else:
            cursor.execute("SELECT id FROM use_cases LIMIT 1")
        row = cursor.fetchone()
        return row[0] if row else None
    except Exception as e:
        logger.error(f"Error looking up default use case: {e}")
        return None
    finally:
        conn.close()

def get_cursor(conn):
    if ENGINE == "postgresql":
        return conn.cursor(cursor_factory=RealDictCursor)
    else:
        return conn.cursor()
