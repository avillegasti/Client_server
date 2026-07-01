import paho.mqtt.client as mqtt
import json
import logging
import os
import ssl
from logging.handlers import RotatingFileHandler
from pathlib import Path
from database import get_db_connection, get_device_id
from config import BASE_DIR, config
import time


def config_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("1", "true", "yes", "on"):
            return True
        if normalized in ("0", "false", "no", "off"):
            return False
    return bool(value)


def resolve_config_path(file_name):
    if not file_name:
        return None

    file_path = Path(str(file_name)).expanduser()
    if file_path.is_absolute():
        return file_path
    return BASE_DIR / file_path


# MQTT Config
mqtt_cfg = config.get("mqtt", {})
MQTT_ENABLED = config_bool(mqtt_cfg.get("enabled"), True)
MQTT_BROKER = mqtt_cfg.get("broker", "localhost")
MQTT_PORT = int(mqtt_cfg.get("port", 1883))
MQTT_USER = mqtt_cfg.get("username", mqtt_cfg.get("user", ""))
MQTT_PASS = mqtt_cfg.get("password", mqtt_cfg.get("pass", ""))
MQTT_TOPIC_PREFIX = mqtt_cfg.get("topic_prefix", "devices/os_bru")
MQTT_TLS_CFG = mqtt_cfg.get("tls") or {}
MQTT_TLS_ENABLED = config_bool(MQTT_TLS_CFG.get("enabled"), False)
MQTT_TLS_INSECURE = config_bool(MQTT_TLS_CFG.get("insecure"), False)

logging_cfg = config.get("logging", {})
LOG_LEVEL_NAME = str(logging_cfg.get("level", "INFO")).upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_NAME, logging.INFO)
LOG_FILE = resolve_config_path(logging_cfg.get("file", "logs/ingestor.log"))
LOG_MAX_BYTES = int(logging_cfg.get("max_bytes", 1048576))
LOG_BACKUP_COUNT = int(logging_cfg.get("backup_count", 5))
LOG_MQTT_MESSAGES = config_bool(logging_cfg.get("log_mqtt_messages"), True)
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

    if LOG_FILE:
        try:
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
            logger_instance.info("MQTT logs will be saved to %s", LOG_FILE)
        except OSError as exc:
            fallback_file = Path("/tmp") / f"ingestor-{os.getuid()}.log"
            fallback_handler = RotatingFileHandler(
                fallback_file,
                maxBytes=LOG_MAX_BYTES,
                backupCount=LOG_BACKUP_COUNT,
                encoding="utf-8",
            )
            fallback_handler.setLevel(LOG_LEVEL)
            fallback_handler.setFormatter(formatter)
            logger_instance.addHandler(fallback_handler)
            logger_instance.warning(
                "Could not write MQTT logs to %s (%s). Falling back to %s",
                LOG_FILE,
                exc,
                fallback_file,
            )

    return logger_instance


logger = configure_logger()


def get_tls_file_path(config_key):
    file_path = resolve_config_path(MQTT_TLS_CFG.get(config_key))
    if file_path and not file_path.exists():
        raise FileNotFoundError(
            f"MQTT TLS file configured at mqtt.tls.{config_key} was not found: {file_path}"
        )
    return str(file_path) if file_path else None


def configure_tls(client):
    if not MQTT_TLS_ENABLED:
        return

    ca_certs = get_tls_file_path("ca_cert_name")
    certfile = get_tls_file_path("client_cert_name")
    keyfile = get_tls_file_path("client_key_name")
    cert_reqs = ssl.CERT_NONE if MQTT_TLS_INSECURE else ssl.CERT_REQUIRED

    client.tls_set(
        ca_certs=ca_certs,
        certfile=certfile,
        keyfile=keyfile,
        cert_reqs=cert_reqs,
    )
    client.tls_insecure_set(MQTT_TLS_INSECURE)
    logger.info("MQTT TLS enabled; insecure certificate verification=%s", MQTT_TLS_INSECURE)


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
    if not MQTT_ENABLED:
        logger.info("MQTT is disabled in config. Ingestor will not connect.")
        return

    client = mqtt.Client()
    configure_tls(client)

    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASS or None)
    
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
