import paho.mqtt.client as mqtt
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from database import get_db_connection, get_device_id
from config import config
import time

# MQTT Config
mqtt_cfg = config.get("mqtt", {})
MQTT_BROKER = mqtt_cfg.get("broker", "localhost")
MQTT_PORT = int(mqtt_cfg.get("port", 1883))
MQTT_USER = mqtt_cfg.get("user", "")
MQTT_PASS = mqtt_cfg.get("pass", "")
MQTT_TOPIC_PREFIX = mqtt_cfg.get("topic_prefix", "devices/os_bru")

logging_cfg = config.get("logging", {})
LOG_LEVEL_NAME = str(logging_cfg.get("level", "INFO")).upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_NAME, logging.INFO)
LOG_FILE = Path(logging_cfg.get("file", "logs/ingestor.log"))
LOG_MAX_BYTES = int(logging_cfg.get("max_bytes", 1048576))
LOG_BACKUP_COUNT = int(logging_cfg.get("backup_count", 5))
LOG_MQTT_MESSAGES = bool(logging_cfg.get("log_mqtt_messages", True))
MQTT_PAYLOAD_PREVIEW_BYTES = int(logging_cfg.get("mqtt_payload_preview_bytes", 512))

# Simple Cache to avoid hitting DB for every message
device_cache = {}


def configure_logger():
    logger_instance = logging.getLogger("ingestor")
    logger_instance.setLevel(LOG_LEVEL)
    logger_instance.propagate = False

    if logger_instance.handlers:
        return logger_instance

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(LOG_LEVEL)
    stream_handler.setFormatter(formatter)
    logger_instance.addHandler(stream_handler)

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(LOG_LEVEL)
    file_handler.setFormatter(formatter)
    logger_instance.addHandler(file_handler)

    return logger_instance


logger = configure_logger()


def payload_preview(payload_bytes):
    preview = payload_bytes[:MQTT_PAYLOAD_PREVIEW_BYTES].decode("utf-8", errors="replace")
    if len(payload_bytes) > MQTT_PAYLOAD_PREVIEW_BYTES:
        preview += "...<truncated>"
    return preview

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("Connected to MQTT broker")
        topic = f"{MQTT_TOPIC_PREFIX}/+/sensors"
        client.subscribe(topic)
        logger.info(f"Subscribed to {topic}")
    else:
        logger.error(f"Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    try:
        preview = payload_preview(msg.payload)
        if LOG_MQTT_MESSAGES:
            logger.info(
                "MQTT message received topic=%s qos=%s retain=%s payload=%s",
                msg.topic,
                msg.qos,
                msg.retain,
                preview,
            )

        topic_parts = msg.topic.split('/')
        device_serial = topic_parts[len(MQTT_TOPIC_PREFIX.split('/'))]
        
        # Resolve device_id
        if device_serial not in device_cache:
            d_id = get_device_id(device_serial)
            if d_id:
                device_cache[device_serial] = d_id
            else:
                logger.warning(f"Device serial {device_serial} not found in uses_cases.devices. Ignoring message.")
                return
        
        device_id = device_cache[device_serial]
        
        payload = json.loads(msg.payload.decode("utf-8"))
        timestamp = payload.get("timestamp")
        temperature = payload.get("temperature")
        humidity = payload.get("humidity")
        voltage = payload.get("battery") # Mapping battery to voltage
        
        if timestamp:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Using the new os_bru.telemetry table schema
            sql = '''
                INSERT INTO os_bru.telemetry (device_id, timestamp, temperature, humidity, voltage)
                VALUES (%s, %s, %s, %s, %s)
            ''' if config.get("database", {}).get("engine") == "postgresql" else '''
                INSERT INTO telemetry (device_id, timestamp, temperature, humidity, voltage)
                VALUES (?, ?, ?, ?, ?)
            '''
            
            cursor.execute(sql, (device_id, timestamp, temperature, humidity, voltage))
            conn.commit()
            conn.close()
            logger.info(
                "Stored telemetry device=%s device_id=%s timestamp=%s",
                device_serial,
                device_id,
                timestamp,
            )
            
    except Exception as e:
        logger.exception("Error processing MQTT message on topic=%s: %s", msg.topic, e)

def run():
    client = mqtt.Client()
    if MQTT_USER and MQTT_PASS:
        client.username_pw_set(MQTT_USER, MQTT_PASS)
    
    client.enable_logger(logger)
    client.on_connect = on_connect
    client.on_message = on_message
    
    while True:
        try:
            logger.info(f"Connecting to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}...")
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
            break
        except Exception as e:
            logger.error(f"Failed to connect to MQTT: {e}. Retrying in 5 seconds...")
            time.sleep(5)

    client.loop_forever()

if __name__ == "__main__":
    run()
