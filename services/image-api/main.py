from fastapi import FastAPI, Response
from fastapi.responses import StreamingResponse
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
import minio_client
import uvicorn
from config import config
import logging
import io
import mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote
from database import get_db_connection, get_cursor

# Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("image-api")

app = FastAPI(title="OS-BRU Image API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
),


DEFAULT_IMAGE_PREFIX = "OS_BRU/"


def get_image_prefix(camera: Optional[str] = None) -> str:
    if camera:
        return f"{DEFAULT_IMAGE_PREFIX}{camera.strip('/')}/"
    return DEFAULT_IMAGE_PREFIX


def build_download_url(object_name: str) -> str:
    return f"/api/images/download/{quote(object_name, safe='/')}"


def parse_image_date_range(start_date: Optional[str] = None, end_date: Optional[str] = None):
    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) + timedelta(days=1) if end_date else None
    return start_dt, end_dt


def lookup_object_path(filename: str) -> Optional[str]:
    conn = None
    try:
        conn = get_db_connection()
        cursor = get_cursor(conn)
        placeholder = "%s" if config.get("database", {}).get("engine") == "postgresql" else "?"
        query = (
            "SELECT minio_path FROM os_bru.images "
            f"WHERE filename = {placeholder} ORDER BY captured_at DESC LIMIT 1"
        )
        cursor.execute(query, (filename,))
        row = cursor.fetchone()
        return row["minio_path"] if row else None
    except Exception as e:
        logger.error(f"Error resolving MinIO path for {filename}: {e}")
        return None
    finally:
        if conn:
            conn.close()


def list_images_from_minio(
    camera: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    prefix = get_image_prefix(camera=camera)
    start_dt, end_dt = parse_image_date_range(start_date=start_date, end_date=end_date)
    images = minio_client.list_images(prefix=prefix, start_dt=start_dt, end_dt=end_dt)
    return [
        {
            "name": img["name"].rsplit("/", 1)[-1],
            "url": build_download_url(img["object_name"]),
            "last_modified": img["last_modified"],
        }
        for img in images
    ]


@app.get("/images")
def get_images(
    device: Optional[str] = None,
    camera: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    conn = None
    try:
        conn = get_db_connection()
        cursor = get_cursor(conn)
        
        query = (
            'SELECT i.filename, i.minio_path, i.captured_at '
            'FROM os_bru.images i '
            'JOIN "Uses_cases".devices d ON i.device_id = d.id'
        )
        params = []
        
        # Check engine to use correct placeholder
        placeholder = "%s" if config.get("database", {}).get("engine") == "postgresql" else "?"

        if device:
            query += f" WHERE d.serial = {placeholder}"
            params.append(device)
        else:
            query += " WHERE 1=1"

        image_prefix = get_image_prefix(camera=camera)
        query += f" AND i.minio_path LIKE {placeholder}"
        params.append(f"{image_prefix}%")

        start_dt, end_dt = parse_image_date_range(start_date=start_date, end_date=end_date)
        if start_dt:
            query += f" AND i.captured_at >= {placeholder}"
            params.append(start_dt)
        if end_dt:
            query += f" AND i.captured_at < {placeholder}"
            params.append(end_dt)
            
        query += " ORDER BY i.captured_at DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        images = []
        for row in rows:
            object_name = row["minio_path"] or row["filename"]
            captured_at = row["captured_at"]
            images.append({
                "name": row['filename'],
                "url": build_download_url(object_name),
                "last_modified": captured_at.isoformat() if hasattr(captured_at, "isoformat") else str(captured_at)
            })

        if images:
            return images

        logger.info(
            "No image metadata rows found for device=%s camera=%s. Falling back to MinIO listing.",
            device,
            camera,
        )
        return list_images_from_minio(camera=camera, start_date=start_date, end_date=end_date)
            
    except Exception as e:
        logger.error(f"Error fetching images from DB: {e}")
        return list_images_from_minio(camera=camera, start_date=start_date, end_date=end_date)
    finally:
        if conn:
            conn.close()

@app.get("/download/{object_name:path}")
def download_image(object_name: str):
    try:
        resolved_object_name = object_name
        if "/" not in object_name:
            resolved_object_name = lookup_object_path(object_name) or object_name

        data = minio_client.get_image_data(resolved_object_name)
        if data is None:
            return Response(status_code=404)

        media_type = mimetypes.guess_type(resolved_object_name)[0] or "application/octet-stream"
        return StreamingResponse(io.BytesIO(data), media_type=media_type)
    except Exception as e:
        logger.error(f"Error streaming image: {e}")
        return Response(status_code=404)

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    port = config.get("api", {}).get("image_port", 8002)
    host = config.get("api", {}).get("host", "0.0.0.0")
    uvicorn.run("main:app", host=host, port=port, reload=True)
