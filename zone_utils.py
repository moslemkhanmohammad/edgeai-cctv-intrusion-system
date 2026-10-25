import os
import json
import numpy as np

def load_config(config_file="zones_config.json"):
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "zones" in data:
                    return data
        except Exception:
            pass
    return {"zones": []}

def save_config(data, config_file="zones_config.json"):
    tmp_file = config_file + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    os.replace(tmp_file, config_file)

def rect_to_polygon(x1, y1, x2, y2):
    rx1, rx2 = sorted([int(x1), int(x2)])
    ry1, ry2 = sorted([int(y1), int(y2)])
    return [
        [rx1, ry1],
        [rx2, ry1],
        [rx2, ry2],
        [rx1, ry2]
    ]

def is_point_in_polygon(point, polygon):
    pts = np.array(polygon, dtype=np.int32)
    return cv2_point_polygon_test(pts, point, False) >= 0

def cv2_point_polygon_test(pts, point, measureDist):
    import cv2
    return cv2.pointPolygonTest(pts, point, measureDist)
