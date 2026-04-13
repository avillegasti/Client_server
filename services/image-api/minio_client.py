from minio import Minio
import logging
from config import config

# Logger setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("minio_client")

# Minio Config
minio_cfg = config.get("minio", {})
MINIO_ENDPOINT = minio_cfg.get("endpoint", "localhost:9000")
MINIO_ACCESS_KEY = minio_cfg.get("access_key", "minioadmin")
MINIO_SECRET_KEY = minio_cfg.get("secret_key", "minioadmin")
MINIO_BUCKET = minio_cfg.get("bucket", "os-bru-images")
MINIO_SECURE = minio_cfg.get("secure", False)

def get_minio_client():
    try:
        client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=MINIO_SECURE
        )
        return client
    except Exception as e:
        logger.error(f"Error connecting to Minio: {e}")
        return None

def get_image_data(object_name):
    client = get_minio_client()
    if not client:
        return None
    
    try:
        response = client.get_object(MINIO_BUCKET, object_name)
        data = response.read()
        response.close()
        response.release_conn()
        return data
    except Exception as e:
        logger.error(f"Error getting object {object_name}: {e}")
        return None

def list_images():
    client = get_minio_client()
    if not client:
        return []
    
    try:
        objects = client.list_objects(MINIO_BUCKET, recursive=True)
        images = []
        for obj in objects:
            if obj.object_name.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                # Generar una URL temporal para visualizar la imagen (valida por 1 hora)
                url = client.presigned_get_object(MINIO_BUCKET, obj.object_name)
                images.append({
                    "name": obj.object_name,
                    "last_modified": obj.last_modified.strftime("%Y-%m-%d %H:%M:%S"),
                    "size": obj.size,
                    "url": url
                })
        logger.info(f"Found {len(images)} images in bucket {MINIO_BUCKET}")
        return sorted(images, key=lambda x: x['last_modified'], reverse=True)
    except Exception as e:
        logger.error(f"Error listing images from Minio: {e}")
        return []

if __name__ == "__main__":
    # Test listing
    print(list_images())
