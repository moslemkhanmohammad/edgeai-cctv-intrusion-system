import os
import time
import cv2
import numpy as np
import requests
import supervision as sv
from ultralytics import YOLO
from datetime import datetime
from plyer import notification

# =========================
#  تنظیمات اصلی
# =========================
RTSP_URL = "rtsp://localhost:8554/mystream"

TELEGRAM_BOT_TOKEN = "8830511012:AAE010k07xyAsr0sdAx2YTrfI2W20DdYit4"
TELEGRAM_CHAT_ID = ""  # شناسه چت خود را اینجا قرار دهید (مثلاً عدد تلگرامتان)

ALERT_DIR = "alerts"
os.makedirs(ALERT_DIR, exist_ok=True)

ALERT_COOLDOWN_SEC = 15  # جلوگیری از ارسال پیام‌های تکراری پشت سر هم برای یک فرد
OUTPUT_FILE = "output_intrusion_rtsp.mp4"

# =========================
#  تابع ارسال تلگرام
# =========================
def send_telegram_alert(text: str, image_path: str | None = None) -> bool:
    if not TELEGRAM_CHAT_ID or TELEGRAM_CHAT_ID == "PUT_YOUR_CHAT_ID_HERE":
        return False
    try:
        base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
        if image_path and os.path.exists(image_path):
            url = f"{base}/sendPhoto"
            with open(image_path, "rb") as f:
                r = requests.post(
                    url,
                    data={"chat_id": TELEGRAM_CHAT_ID, "caption": text},
                    files={"photo": f},
                    timeout=15
                )
        else:
            url = f"{base}/sendMessage"
            r = requests.post(
                url,
                data={"chat_id": TELEGRAM_CHAT_ID, "text": text},
                timeout=15
            )
        return r.status_code == 200
    except Exception as e:
        print("Telegram error:", e)
        return False

# =========================
#  تابع اخطار ویندوز
# =========================
def show_desktop_notification(title, message):
    try:
        notification.notify(
            title=title,
            message=message,
            app_name='AI CCTV Security',
            timeout=4
        )
    except Exception:
        pass

def open_capture(url: str) -> cv2.VideoCapture:
    return cv2.VideoCapture(url, cv2.CAP_FFMPEG)

def main():
    model = YOLO("yolo11n.pt")

    cap = open_capture(RTSP_URL)
    if not cap.isOpened():
        print(f"خطا: اتصال به RTSP برقرار نشد: {RTSP_URL}")
        return

    width = height = None
    for _ in range(80):
        ret, frame0 = cap.read()
        if ret and frame0 is not None:
            height, width = frame0.shape[:2]
            break
        time.sleep(0.05)

    if width is None:
        print("خطا: فریم دریافت نشد.")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    fps = int(fps) if fps and fps > 1 else 25

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(OUTPUT_FILE, fourcc, fps, (width, height))

    # تعریف چند منطقه ممنوعه نمونه
    zones = [
        {
            "name": "Zone-A (Warehouse)",
            "polygon": np.array([
                [int(width * 0.10), int(height * 0.45)],
                [int(width * 0.55), int(height * 0.45)],
                [int(width * 0.55), int(height * 0.90)],
                [int(width * 0.10), int(height * 0.90)]
            ])
        },
        {
            "name": "Zone-B (Restricted)",
            "polygon": np.array([
                [int(width * 0.60), int(height * 0.55)],
                [int(width * 0.95), int(height * 0.55)],
                [int(width * 0.95), int(height * 0.92)],
                [int(width * 0.60), int(height * 0.92)]
            ])
        }
    ]

    polygon_zones = []
    zone_annotators = []
    zone_colors = [sv.Color.RED, sv.Color.ORANGE]

    for i, z in enumerate(zones):
        pz = sv.PolygonZone(polygon=z["polygon"], triggering_anchors=[sv.Position.BOTTOM_CENTER])
        polygon_zones.append(pz)
        zone_annotators.append(sv.PolygonZoneAnnotator(zone=pz, color=zone_colors[i % len(zone_colors)], thickness=2))

    safe_box = sv.BoxAnnotator(color=sv.Color.GREEN, thickness=2)
    alert_box = sv.BoxAnnotator(color=sv.Color.RED, thickness=3)
    safe_label = sv.LabelAnnotator(color=sv.Color.GREEN, text_color=sv.Color.BLACK, text_scale=0.5)
    alert_label = sv.LabelAnnotator(color=sv.Color.RED, text_color=sv.Color.WHITE, text_scale=0.6)

    last_alert_time = {}

    print(">> سیستم هوشمند AI CCTV با قابلیت نوتیفیکیشن فعال شد.")
    print(">> برای خروج: Ctrl+C در ترمینال")

    frame_idx = 0
    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                continue

            frame_idx += 1

            results = model.track(
                frame,
                persist=True,
                classes=[0],
                tracker="bytetrack.yaml",
                conf=0.35,
                verbose=False
            )[0]

            detections = sv.Detections.from_ultralytics(results)
            zone_hit = np.zeros(len(detections), dtype=bool)
            zone_name_for_det = np.array([""] * len(detections), dtype=object)

            if len(detections) > 0 and detections.tracker_id is not None:
                for idx_zone, pz in enumerate(polygon_zones):
                    hit = pz.trigger(detections)
                    for i_det in range(len(detections)):
                        if hit[i_det] and (zone_name_for_det[i_det] == ""):
                            zone_hit[i_det] = True
                            zone_name_for_det[i_det] = zones[idx_zone]["name"]

                intruders = detections[zone_hit]
                safe_people = detections[~zone_hit]

                if len(safe_people) > 0:
                    safe_labels = [f"ID #{tid}" for tid in safe_people.tracker_id]
                    frame = safe_box.annotate(scene=frame, detections=safe_people)
                    frame = safe_label.annotate(scene=frame, detections=safe_people, labels=safe_labels)

                if len(intruders) > 0:
                    intruder_zone_names = zone_name_for_det[zone_hit]
                    labels = [f"ALERT {zn} | ID #{tid}" for zn, tid in zip(intruder_zone_names, intruders.tracker_id)]
                    frame = alert_box.annotate(scene=frame, detections=intruders)
                    frame = alert_label.annotate(scene=frame, detections=intruders, labels=labels)

                    now = time.time()
                    for zn, tid in zip(intruder_zone_names, intruders.tracker_id):
                        key = (zn, int(tid))
                        if now - last_alert_time.get(key, 0) < ALERT_COOLDOWN_SEC:
                            continue
                        last_alert_time[key] = now

                        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                        img_path = os.path.join(ALERT_DIR, f"intruder_{zn.split()[0]}_id_{tid}_{ts}.jpg")
                        cv2.imwrite(img_path, frame)

                        # اعلان دسکتاپ ویندوز
                        show_desktop_notification("هشدار نفوذ امنیتی!", f"تشخیص فرد در {zn} (ID: {tid})")

                        # ارسال به تلگرام
                        msg = f"🚨 **INTRUSION ALERT**\n📍 Zone: {zn}\n🆔 Person ID: {tid}\n⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        send_telegram_alert(msg, img_path)
                        print(f"⚠️ هشدار ثبت و ارسال شد -> {img_path}")

            for ann in zone_annotators:
                frame = ann.annotate(scene=frame)

            out.write(frame)

            if frame_idx % 120 == 0:
                print(f"در حال پردازش... frame={frame_idx}")

    except KeyboardInterrupt:
        print("توقف برنامه.")
    finally:
        cap.release()
        out.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
