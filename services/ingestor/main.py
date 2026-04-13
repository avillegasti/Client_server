import paho.mqtt.client as mqtt
import json
import logging
from database import get_db_connection, get_device_id
from config import config
import time

# Logger setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ingestor")

# MQTT Config
mqtt_cfg = config.get("mqtt", {})
MQTT_BROKER = mqtt_cfg.get("broker", "localhost")
MQTT_PORT = int(mqtt_cfg.get("port", 1883))
MQTT_USER = mqtt_cfg.get("user", "")
MQTT_PASS = mqtt_cfg.get("pass", "")
MQTT_TOPIC_PREFIX = mqtt_cfg.get("topic_prefix", "devices/os_bru")

# Simple Cache to avoid hitting DB for every message
device_cache = {}

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
        
        payload = json.loads(msg.payload.decode())
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
            logger.debug(f"Stored telemetry for {device_serial} (ID: {device_id}) at {timestamp}")
            
    except Exception as e:
        logger.error(f"Error processing message: {e}")

def run():
    client = mqtt.Client()
    if MQTT_USER and MQTT_PASS:
        client.username_pw_set(MQTT_USER, MQTT_PASS)
    
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
