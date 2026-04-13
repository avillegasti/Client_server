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
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if ENGINE == "postgresql":
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS telemetry (
                    id SERIAL PRIMARY KEY,
                    device_name TEXT NOT NULL,
                    sensor_type TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    value REAL NOT NULL,
                    unit TEXT NOT NULL
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_device ON telemetry (device_name)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON telemetry (timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sensor ON telemetry (sensor_type)')
        else:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_name TEXT NOT NULL,
                    sensor_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    value REAL NOT NULL,
                    unit TEXT NOT NULL
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_device ON telemetry (device_name)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON telemetry (timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sensor ON telemetry (sensor_type)')
            
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")

def get_cursor(conn):
    if ENGINE == "postgresql":
        return conn.cursor(cursor_factory=RealDictCursor)
    else:
        return conn.cursor()

if __name__ == "__main__":
    init_db()
    print(f"Database initialized with {ENGINE} engine.")
