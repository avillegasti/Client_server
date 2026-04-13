from fastapi import FastAPI, Response
from fastapi.responses import StreamingResponse
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
import minio_client
import uvicorn
from config import config
import logging
import io
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

@app.get("/images")
def get_images(device: Optional[str] = None):
    try:
        conn = get_db_connection()
        cursor = get_cursor(conn)
        
        query = 'SELECT i.filename, i.captured_at FROM os_bru.images i JOIN "Uses_cases".devices d ON i.device_id = d.id'
        params = []
        
        # Check engine to use correct placeholder
        placeholder = "%s" if config.get("database", {}).get("engine") == "postgresql" else "?"

        if device:
            query += f" WHERE d.serial = {placeholder}"
            params.append(device)
            
        query += " ORDER BY i.captured_at DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        images = []
        for row in rows:
            images.append({
                "name": row['filename'],
                "url": f"/api/images/download/{row['filename']}",
                "last_modified": row['captured_at'].isoformat()
            })
            
        return images
        
    except Exception as e:
        logger.error(f"Error fetching images from DB: {e}")
        # Fallback to minio if DB fails? For now, empty list.
        return []

@app.get("/download/{filename}")
def download_image(filename: str):
    try:
        data = minio_client.get_image_data(filename)
        return StreamingResponse(io.BytesIO(data), media_type="image/jpeg")
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
