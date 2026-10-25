import os
import time
import json
import cv2
import numpy as np
import requests
from ultralytics import YOLO
from datetime import datetime
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

try:
    from plyer import notification
except ImportError:
    notification = None

import winsound

RTSP_URL = os.environ.get("RTSP_URL", "person-bicycle-car-detection.mp4")
MODEL_PATH = os.environ.get("MODEL_PATH", "yolo11s.pt")
CONF_THRES = float(os.environ.get("CONF_THRES", 0.12))   # پایین آمد تا زودتر تشخیص دهد
DEVICE = os.environ.get("DEVICE", "auto")                # auto -> cuda اگر باشد، وگرنه cpu

CONFIG_FILE = "zones_config.json"
LIVE_FRAME = "live_frame.jpg"
RAW_FRAME = "raw_frame.jpg"
ALERTS_DIR = "alerts"
ALERTS_LOG = os.path.join(ALERTS_DIR, "alerts_log.jsonl")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "*******")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "172403756")
TELEGRAM_ENABLED = True
STREAM_PORT = 8089

TARGET_CLASS_IDS = [0, 1, 2, 3, 5, 7]  # person, bicycle, car, motorcycle, bus, truck

os.makedirs(ALERTS_DIR, exist_ok=True)

global_frame_bytes = None
raw_frame_bytes = None
frame_lock = threading.Lock()

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

class MJPEGStreamHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global global_frame_bytes, raw_frame_bytes
        if self.path == '/video_feed':
            self.send_response(200)
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
            self.send_header('Pragma', 'no-cache')
            self.end_headers()
            while True:
                with frame_lock:
                    if global_frame_bytes is None:
                        time.sleep(0.02)
                        continue
                    frame_data = global_frame_bytes
                try:
                    self.wfile.write(b'--frame\r\n')
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', str(len(frame_data)))
                    self.end_headers()
                    self.wfile.write(frame_data)
                    self.wfile.write(b'\r\n')
                    time.sleep(0.03)
                except (BrokenPipeError, ConnectionResetError):
                    break
        elif self.path == '/snapshot.jpg':
            with frame_lock:
                data = global_frame_bytes
            if data:
                self.send_response(200)
                self.send_header('Content-Type', 'image/jpeg')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(404)
                self.end_headers()
        elif self.path == '/raw.jpg':
            with frame_lock:
                rdata = raw_frame_bytes
            if rdata:
                self.send_response(200)
                self.send_header('Content-Type', 'image/jpeg')
                self.send_header('Content-Length', str(len(rdata)))
                self.end_headers()
                self.wfile.write(rdata)
            else:
                self.send_response(404)
                self.end_headers()
        elif self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        return

def start_streaming_server():
    server = ThreadedHTTPServer(('0.0.0.0', STREAM_PORT), MJPEGStreamHandler)
    server.serve_forever()

def send_telegram_alert(photo_path, caption):
    if not TELEGRAM_ENABLED:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    try:
        with open(photo_path, 'rb') as f:
            files = {'photo': f}
            data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': caption, 'parse_mode': 'Markdown'}
            requests.post(url, files=files, data=data, timeout=5)
    except Exception as e:
        print(f"⚠️ Telegram alert delivery error: {e}")

def send_system_alert(zone_name, class_name, track_id, frame, conf):
    now = datetime.now()
    timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")
    file_prefix = now.strftime("%Y%m%d_%H%M%S")
    filename = f"{file_prefix}_{zone_name}_{class_name}_id{track_id}.jpg"
    filepath = os.path.join(ALERTS_DIR, filename)

    cv2.imwrite(filepath, frame)

    log_entry = {
        "timestamp": timestamp_str,
        "zone_name": zone_name,
        "class_name": class_name,
        "track_id": track_id,
        "confidence": round(float(conf), 2),
        "frame_path": filepath
    }
    with open(ALERTS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    caption = (
        f"🚨 *RESTRICTED ZONE INTRUSION*\n\n"
        f"📍 *Zone:* `{zone_name}`\n"
        f"👤 *Detected Object:* `{class_name}` (Track ID: `{track_id}`)\n"
        f"🎯 *Confidence:* `{int(conf * 100)}%`\n"
        f"⏰ *Timestamp:* `{timestamp_str}`"
    )

    threading.Thread(target=send_telegram_alert, args=(filepath, caption), daemon=True).start()

    if notification:
        try:
            notification.notify(title=f"Zone Intrusion: {zone_name}", message=f"Detected: {class_name}", timeout=3)
        except Exception:
            pass
    try:
        winsound.Beep(1200, 300)
    except Exception:
        pass

def load_zones():
    if not os.path.exists(CONFIG_FILE):
        return []
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("zones", [])
    except Exception:
        return []

def is_point_in_polygon(point, polygon):
    pts = np.array(polygon, dtype=np.int32)
    return cv2.pointPolygonTest(pts, (float(point[0]), float(point[1])), False) >= 0

def check_intrusion(box, polygon):
    x1, y1, x2, y2 = box
    cx = int((x1 + x2) / 2)
    cy = int((y1 + y2) / 2)
    bottom_y = int(y2)
    lower_mid_y = int((cy + y2) / 2)

    test_points = [
        (cx, bottom_y),     # چرخ‌ها
        (cx, cy),           # مرکز بدنه
        (cx, lower_mid_y)   # یک‌چهارم پایینی
    ]

    for pt in test_points:
        if is_point_in_polygon(pt, polygon):
            return True, pt
    return False, (cx, bottom_y)

def main():
    global global_frame_bytes, raw_frame_bytes

    # تشخیص خودکار دستگاه: اگر CUDA باشد استفاده می‌کند وگرنه CPU
    import torch
    device = "cuda" if (DEVICE == "auto" and torch.cuda.is_available()) else ("cuda" if DEVICE == "cuda" else "cpu")
    print(f"🚀 Initializing YOLO Model: {MODEL_PATH} (device={device}) ...")
    model = YOLO(MODEL_PATH)

    print(f"🎥 Connecting to stream source: {RTSP_URL}")
    cap = cv2.VideoCapture(RTSP_URL)
    if not cap.isOpened():
        print(f"❌ Could not open video source: {RTSP_URL}")
        return

    t = threading.Thread(target=start_streaming_server, daemon=True)
    t.start()
    print(f"📡 High-speed MJPEG stream server active on http://localhost:{STREAM_PORT}/video_feed")

    last_alert_time = {}
    last_config_check = 0
    zones = load_zones()

    while True:
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue

        current_time = time.time()
        if current_time - last_config_check > 2.0:
            zones = load_zones()
            last_config_check = current_time

        annotated_frame = frame.copy()

        for zone in zones:
            if not zone.get("enabled", True):
                continue
            poly = np.array(zone["polygon"], dtype=np.int32)
            cv2.polylines(annotated_frame, [poly], isClosed=True, color=(0, 0, 255), thickness=2)
            cv2.putText(annotated_frame, zone["name"], (zone["polygon"][0][0], max(zone["polygon"][0][1] - 10, 20)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        # اجرای ترک با فیلتر کلاس‌ها + آستانهٔ پایین برای تشخیص زودهنگام
        results = model.track(
            frame,
            persist=True,
            classes=TARGET_CLASS_IDS,
            conf=CONF_THRES,
            device=device,
            verbose=False
        )

        if results and results[0].boxes and results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            track_ids = results[0].boxes.id.int().cpu().tolist()
            cls_ids = results[0].boxes.cls.int().cpu().tolist()
            confs = results[0].boxes.conf.cpu().tolist()
            names = results[0].names

            for box, track_id, cls_id, conf in zip(boxes, track_ids, cls_ids, confs):
                class_name = names[cls_id]
                x1, y1, x2, y2 = box

                cv2.rectangle(annotated_frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
                cv2.putText(annotated_frame, f"{class_name} #{track_id} {int(conf*100)}%",
                            (int(x1), max(int(y1) - 6, 15)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

                for zone in zones:
                    if not zone.get("enabled", True):
                        continue

                    target_classes = zone.get("targets", ["person", "car"])
                    if class_name in target_classes:
                        intruded, active_pt = check_intrusion(box, zone["polygon"])

                        cv2.circle(annotated_frame, active_pt, 5, (0, 0, 255) if intruded else (255, 255, 0), -1)

                        if intruded:
                            zone_id = zone.get("id", zone["name"])
                            cooldown = zone.get("cooldown_seconds", 8)
                            key = f"{zone_id}_{track_id}"

                            if current_time - last_alert_time.get(key, 0) > cooldown:
                                last_alert_time[key] = current_time
                                print(f"⚠️ [BREACH DETECTED] Zone: '{zone['name']}' | Object: {class_name} (ID: {track_id})")
                                send_system_alert(zone["name"], class_name, track_id, annotated_frame, conf)

        ret_enc, buffer = cv2.imencode('.jpg', annotated_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        ret_raw, rbuffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if ret_enc and ret_raw:
            with frame_lock:
                global_frame_bytes = buffer.tobytes()
                raw_frame_bytes = rbuffer.tobytes()

        time.sleep(0.01)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Stopped.")
