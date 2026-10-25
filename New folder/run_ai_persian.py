import os
import time
import json
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import cv2
import numpy as np
import requests
from ultralytics import YOLO

try:
    from plyer import notification
except ImportError:
    notification = None

try:
    import winsound
except ImportError:
    winsound = None

# --------------------------
# تنظیمات
# --------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_VIDEO = os.path.join(BASE_DIR, "person-bicycle-car-detection.mp4")
RTSP_URL = os.environ.get("RTSP_URL", DEFAULT_VIDEO if os.path.exists(DEFAULT_VIDEO) else "rtsp://localhost:8554/mystream")

MODEL_PATH = os.environ.get("MODEL_PATH", "yolo11n.pt")
CONF_THRES = float(os.environ.get("CONF_THRES", "0.35"))
IOU_THRES = float(os.environ.get("IOU_THRES", "0.45"))

LIVE_FRAME_PATH = os.path.join(BASE_DIR, "live_frame.jpg")
CONFIG_FILE = os.path.join(BASE_DIR, "zones_config.json")
ALERTS_DIR = os.path.join(BASE_DIR, "alerts")
ALERTS_LOG = os.path.join(ALERTS_DIR, "alerts_log.jsonl")

os.makedirs(ALERTS_DIR, exist_ok=True)
_log_lock = threading.Lock()

TELEGRAM_BOT_TOKEN = "8830511012:AAE010k07xyAsr0sdAx2YTrfI2W20DdYit4"
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# بافر درون حافظه برای استریم زنده روان
latest_jpeg = None
frame_lock = threading.Lock()


# --------------------------
# سرور استریم ویدیو روان (MJPEG)
# --------------------------
class MJPEGHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global latest_jpeg
        if self.path == "/video_feed":
            self.send_response(200)
            self.send_header("Age", "0")
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=FRAME")
            self.end_headers()
            try:
                while True:
                    with frame_lock:
                        if latest_jpeg is None:
                            time.sleep(0.01)
                            continue
                        frame_bytes = latest_jpeg

                    self.wfile.write(b"--FRAME\r\n")
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(frame_bytes)))
                    self.end_headers()
                    self.wfile.write(frame_bytes)
                    self.wfile.write(b"\r\n")
                    time.sleep(0.03)  # حدود ۳۰ فریم بر ثانیه روان
            except Exception:
                pass
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # جلوگیری از شلوغ شدن کنسول پایتون
        return


def start_streaming_server():
    server = HTTPServer(("0.0.0.0", 8089), MJPEGHandler)
    server.serve_forever()


threading.Thread(target=start_streaming_server, daemon=True).start()


def append_alert_log(record: dict):
    with _log_lock:
        with open(ALERTS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def send_desktop_alert(title, message):
    if winsound:
        try:
            winsound.Beep(2500, 400)
        except Exception:
            pass

    if notification:
        try:
            notification.notify(
                title=title,
                message=message,
                app_name="AI CCTV Guard",
                timeout=3
            )
        except Exception:
            pass


def send_telegram_alert(image_path, caption):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    def _worker():
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            with open(image_path, "rb") as photo_file:
                files = {"photo": photo_file}
                data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption}
                requests.post(url, data=data, files=files, timeout=6)
        except Exception as e:
            print(f">> خطا در ارسال تلگرام: {e}")

    threading.Thread(target=_worker, daemon=True).start()


def load_zones_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("zones", [])
        except Exception:
            pass
    return []


def point_in_polygon(pt, polygon):
    poly_np = np.array(polygon, np.int32)
    result = cv2.pointPolygonTest(poly_np, (float(pt[0]), float(pt[1])), False)
    return result >= 0


print(">> در حال بارگذاری مدل هوش مصنوعی...")
model = YOLO(MODEL_PATH)
print(">> مدل بارگذاری شد. سرور استریم روان روی پورت 8089 آماده است.")

cap = cv2.VideoCapture(RTSP_URL)
last_alert_time = {}
config_reload_timer = time.time()
disk_save_timer = time.time()
zones = load_zones_config()

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        if isinstance(RTSP_URL, str) and not RTSP_URL.startswith("rtsp://"):
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue
        print(">> دریافت فریم با وقفه روبرو شد. در حال تلاش مجدد...")
        time.sleep(1)
        cap = cv2.VideoCapture(RTSP_URL)
        continue

    if time.time() - config_reload_timer > 3.0:
        zones = load_zones_config()
        config_reload_timer = time.time()

    results = model.track(frame, persist=True, conf=CONF_THRES, iou=IOU_THRES, verbose=False)
    current_frame_time = time.time()

    # ترسیم محدوده‌ها
    for zone in zones:
        if not zone.get("enabled", True):
            continue
        poly = np.array(zone["polygon"], np.int32)
        cv2.polylines(frame, [poly], isClosed=True, color=(0, 255, 255), thickness=2)
        cv2.putText(
            frame,
            zone["name"],
            (poly[0][0], max(20, poly[0][1] - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 255),
            2
        )

    if results and results[0].boxes is not None:
        boxes = results[0].boxes
        if boxes.id is not None:
            xyxy_list = boxes.xyxy.cpu().numpy()
            track_ids = boxes.id.cpu().numpy()
            class_ids = boxes.cls.cpu().numpy()
            confs = boxes.conf.cpu().numpy() if boxes.conf is not None else [0.85] * len(track_ids)

            for box, track_id, cls_id, conf in zip(xyxy_list, track_ids, class_ids, confs):
                class_name = model.names[int(cls_id)]
                x1, y1, x2, y2 = map(int, box)

                center_x = int((x1 + x2) / 2)
                center_y = int(y2)
                obj_center = (center_x, center_y)

                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(
                    frame,
                    f"ID:{int(track_id)} {class_name}",
                    (x1, max(20, y1 - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 0),
                    2
                )

                for zone in zones:
                    if not zone.get("enabled", True):
                        continue

                    target_classes = zone.get("targets", ["person"])
                    if class_name in target_classes:
                        if point_in_polygon(obj_center, zone["polygon"]):
                            z_id = zone.get("id", zone["name"])
                            cooldown = zone.get("cooldown_seconds", 8)
                            key = (z_id, int(track_id))

                            if current_frame_time - last_alert_time.get(key, 0) > cooldown:
                                last_alert_time[key] = current_frame_time

                                now_dt = datetime.now()
                                timestamp_str = now_dt.strftime("%Y%m%d_%H%M%S")
                                alert_filename = os.path.join(
                                    ALERTS_DIR,
                                    f"alert_{zone['name']}_{track_id}_{timestamp_str}.jpg"
                                )

                                cv2.imwrite(alert_filename, frame)

                                log_entry = {
                                    "timestamp": now_dt.isoformat(timespec="seconds"),
                                    "event_type": "zone_intrusion",
                                    "zone_name": zone["name"],
                                    "track_id": int(track_id),
                                    "class_name": class_name,
                                    "confidence": round(float(conf), 2),
                                    "frame_path": alert_filename
                                }
                                append_alert_log(log_entry)

                                print(f">> 🚨 ورود غیرمجاز: {zone['name']} توسط {class_name} (ID: {int(track_id)})")
                                send_desktop_alert(f"هشدار: {zone['name']}", f"شناسایی {class_name} در محدوده!")
                                send_telegram_alert(alert_filename, f"🚨 ورود غیرمجاز: {zone['name']}\nشیء: {class_name}")

    # تبدیل فریم به بایت JPEG در رم (فوق‌العاده سریع بدون درگیر کردن هارد دیسک)
    success, encoded_img = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if success:
        with frame_lock:
            latest_jpeg = encoded_img.tobytes()

    # ذخیره فریم روی دیسک فقط هر ۲ ثانیه یک‌بار (صرفاً برای تب ترسیم کادر با ماوس)
    if time.time() - disk_save_timer > 2.0:
        try:
            cv2.imwrite(LIVE_FRAME_PATH, frame)
            disk_save_timer = time.time()
        except Exception:
            pass

cap.release()
