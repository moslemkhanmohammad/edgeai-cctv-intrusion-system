# cctv_fixed/fastapi_gateway.py
import os
import time
from typing import Iterator

from fastapi import FastAPI, Response
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from starlette.middleware.cors import CORSMiddleware

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIVE_FRAME = os.path.join(BASE_DIR, "live_frame.jpg")
RAW_FRAME = os.path.join(BASE_DIR, "raw_frame.jpg")

app = FastAPI(title="AI CCTV Stream Gateway", version="1.0.0")

# Allow dashboard UI to fetch from gateway (use env for production domains)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def mjpeg_generator(interval: float = 0.05) -> Iterator[bytes]:
    """
    Yields multipart MJPEG frames from LIVE_FRAME, falling back to RAW_FRAME.
    interval: seconds between polls to reduce CPU usage.
    """
    while True:
        path = LIVE_FRAME if os.path.exists(LIVE_FRAME) and os.path.getsize(LIVE_FRAME) > 0 else RAW_FRAME
        if path and os.path.exists(path) and os.path.getsize(path) > 0:
            try:
                with open(path, "rb") as f:
                    frame = f.read()
                # multipart MJPEG chunk
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            except Exception:
                # if reading fails, wait a bit
                time.sleep(interval)
        else:
            # No frame available: send a small blank JPEG or wait
            time.sleep(interval)

@app.get("/video_feed")
def video_feed():
    return StreamingResponse(mjpeg_generator(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/snapshot.jpg")
def snapshot():
    path = LIVE_FRAME if os.path.exists(LIVE_FRAME) and os.path.getsize(LIVE_FRAME) > 0 else RAW_FRAME
    if path and os.path.exists(path) and os.path.getsize(path) > 0:
        return FileResponse(path, media_type="image/jpeg")
    return Response(status_code=404)

@app.get("/raw.jpg")
def raw():
    if os.path.exists(RAW_FRAME) and os.path.getsize(RAW_FRAME) > 0:
        return FileResponse(RAW_FRAME, media_type="image/jpeg")
    return Response(status_code=404)

@app.get("/health")
def health():
    live_ok = os.path.exists(LIVE_FRAME) and os.path.getsize(LIVE_FRAME) > 0
    raw_ok = os.path.exists(RAW_FRAME) and os.path.getsize(RAW_FRAME) > 0
    return JSONResponse({
        "live_frame": {"exists": os.path.exists(LIVE_FRAME), "size": os.path.getsize(LIVE_FRAME) if os.path.exists(LIVE_FRAME) else 0, "ok": live_ok},
        "raw_frame": {"exists": os.path.exists(RAW_FRAME), "size": os.path.getsize(RAW_FRAME) if os.path.exists(RAW_FRAME) else 0, "ok": raw_ok},
        "status": "ok" if (live_ok or raw_ok) else "no_frames"
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("fastapi_gateway:app", host="0.0.0.0", port=8089, reload=False)
