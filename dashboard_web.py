import sys
import os

try:
    from streamlit import runtime
    if not runtime.exists():
        from streamlit.web import cli as stcli
        sys.argv = ["streamlit", "run", sys.argv[0]]
        sys.exit(stcli.main())
except Exception:
    pass

import streamlit as st
import cv2
import numpy as np
from PIL import Image, ImageDraw
import json
import glob
import time
import requests
from zone_utils import load_config, save_config

try:
    from streamlit_image_coordinates import streamlit_image_coordinates
except ImportError:
    streamlit_image_coordinates = None

st.set_page_config(page_title="AI CCTV Multi-Zone Guard", layout="wide", page_icon="🛡️")

CONFIG_FILE = "zones_config.json"
LIVE_FRAME = "live_frame.jpg"
RAW_FRAME = "raw_frame.jpg"
ALERTS_DIR = "alerts"
ALERTS_LOG = os.path.join(ALERTS_DIR, "alerts_log.jsonl")
STREAM_SNAPSHOT_URL = "http://localhost:8089/snapshot.jpg"

if "clicks" not in st.session_state:
    st.session_state["clicks"] = []

st.title("🛡️ AI Vision Surveillance & Restricted Zone Guard")

tab_live, tab_setup, tab_history = st.tabs([
    "📺 Live Monitoring & Alerts", 
    "✏️ Zone Calibration", 
    "📋 Incident Archive & Reports"
])

# Define decorator for auto-updating alerts column every 2 seconds
if hasattr(st, "fragment"):
    alert_fragment = st.fragment(run_every=2)
elif hasattr(st, "experimental_fragment"):
    alert_fragment = st.experimental_fragment(run_every=2)
else:
    alert_fragment = lambda func: func

# Live function to render recent alerts
@alert_fragment
def render_live_alerts():
    col_h1, col_h2 = st.columns([2, 1])
    col_h1.subheader("🚨 Recent Detections")
    if col_h2.button("🔄 Refresh", key="refresh_alerts_btn", use_container_width=True):
        st.rerun()

    alerts = sorted(glob.glob(os.path.join(ALERTS_DIR, "*.jpg")), key=os.path.getmtime, reverse=True)
    if alerts:
        st.caption(f"⚡ Auto-updating feed ({len(alerts)} alert images)")
        for alert_path in alerts[:4]:
            st.image(alert_path, caption=os.path.basename(alert_path), use_container_width=True)
    else:
        st.write("🟢 No security incidents detected.")

# Tab 1: Live Stream & Auto-Updating Alerts
with tab_live:
    col_live, col_alerts = st.columns([2, 1])
    with col_live:
        st.subheader("Live RTSP / AI Stream")
        if st.toggle("🔴 Stream Active", value=True):
            st.markdown(
                """
                <div style="border-radius: 8px; overflow: hidden; background: #111;">
                    <img src="http://localhost:8089/video_feed" style="width: 100%; height: auto; display: block;" 
                         onerror="this.onerror=null; this.src='http://127.0.0.1:8089/snapshot.jpg';" />
                </div>
                """,
                unsafe_allow_html=True
            )
    with col_alerts:
        render_live_alerts()

# Tab 2: Calibration
with tab_setup:
    st.subheader("Define Custom Zone Boundaries")
    cfg = load_config(CONFIG_FILE)

    # Active zones
    if cfg.get("zones"):
        st.markdown("### 📋 Active Saved Zones:")
        for idx, z in enumerate(list(cfg["zones"])):
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.write(f"🛡️ **{z['name']}** ({len(z.get('polygon', []))} points)")
            c2.write(f"Targets: {', '.join(z.get('targets', ['person']))}")
            if c3.button("🗑️ Delete", key=f"del_{idx}"):
                cfg["zones"].pop(idx)
                save_config(cfg, CONFIG_FILE)
                st.session_state["clicks"] = []
                st.rerun()

        if st.button("🗑️ Clear All Saved Zones"):
            save_config({"zones": []}, CONFIG_FILE)
            st.session_state["clicks"] = []
            st.rerun()
        st.markdown("---")

    # Fetch snapshot
    base_img = None
    for candidate in [RAW_FRAME, LIVE_FRAME]:
        if os.path.exists(candidate) and os.path.getsize(candidate) > 0:
            try:
                base_img = Image.open(candidate).convert("RGB")
                break
            except Exception:
                pass

    if base_img is None:
        try:
            resp = requests.get(STREAM_SNAPSHOT_URL, timeout=1.0)
            if resp.status_code == 200:
                import io
                base_img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        except Exception:
            pass

    if base_img is None:
        base_img = Image.new("RGB", (640, 480), color=(40, 44, 52))

    orig_w, orig_h = base_img.size

    # Draw existing saved zones (Green) + New In-Progress Clicked Points (Red)
    draw_img = base_img.copy()
    draw = ImageDraw.Draw(draw_img)

    for z in cfg.get("zones", []):
        pts = [tuple(p) for p in z.get("polygon", [])]
        if len(pts) >= 3:
            draw.polygon(pts, outline=(0, 255, 120), width=3)
            draw.text((pts[0][0] + 5, max(pts[0][1] - 15, 5)), z['name'], fill=(0, 255, 120))

    # Draw current interactive clicks
    pts_in_progress = st.session_state["clicks"]
    for i, pt in enumerate(pts_in_progress):
        draw.ellipse([pt[0]-5, pt[1]-5, pt[0]+5, pt[1]+5], fill=(255, 50, 50), outline=(255, 255, 255))
        draw.text((pt[0]+7, pt[1]-7), f"P{i+1}", fill=(255, 255, 0))

    if len(pts_in_progress) >= 2:
        draw.line(pts_in_progress, fill=(255, 50, 50), width=2)
    if len(pts_in_progress) >= 3:
        draw.line([pts_in_progress[-1], pts_in_progress[0]], fill=(255, 50, 50), width=2)

    col_view, col_form = st.columns([3, 2])

    with col_view:
        st.markdown(f"#### Click Points Directly On Frame ({orig_w}x{orig_h})")
        st.caption("👉 **Guide:** Click 4 times at desired corners on the image to form your zone.")

        value = None
        if streamlit_image_coordinates is not None:
            value = streamlit_image_coordinates(draw_img, key="zone_click_canvas")
        else:
            st.image(draw_img, caption="Interactive preview")

        if value is not None:
            new_pt = [int(value["x"]), int(value["y"])]
            if len(st.session_state["clicks"]) == 0 or st.session_state["clicks"][-1] != new_pt:
                st.session_state["clicks"].append(new_pt)
                st.rerun()

        c_reset, c_undo = st.columns(2)
        if c_reset.button("🔄 Reset Current Points", use_container_width=True):
            st.session_state["clicks"] = []
            st.rerun()
        if c_undo.button("↩️ Undo Last Point", use_container_width=True):
            if st.session_state["clicks"]:
                st.session_state["clicks"].pop()
                st.rerun()

    with col_form:
        st.markdown("#### Zone Properties")
        zone_name = st.text_input("Zone Name:", value=f"Zone {len(cfg.get('zones', [])) + 1}")
        target_type = st.multiselect("Trigger Targets:", ["person", "car", "motorcycle", "bus", "truck"], default=["person"])
        cooldown = st.slider("Alert Cooldown (s):", 2, 60, 8)

        st.markdown("---")
        st.write(f"Points collected: **{len(st.session_state['clicks'])}**")
        for i, p in enumerate(st.session_state["clicks"]):
            st.code(f"Point {i+1}: X={p[0]}, Y={p[1]}")

        # Direct Save button
        if len(st.session_state["clicks"]) >= 3:
            if st.button("💾 SAVE EXACT CLICKED ZONE", type="primary", use_container_width=True):
                new_zone = {
                    "id": f"zone_{int(time.time())}",
                    "name": zone_name,
                    "targets": target_type,
                    "polygon": st.session_state["clicks"],
                    "cooldown_seconds": cooldown,
                    "enabled": True
                }
                cfg["zones"].append(new_zone)
                save_config(cfg, CONFIG_FILE)
                st.session_state["clicks"] = []
                st.toast(f"✅ Zone '{zone_name}' saved accurately!", icon="🎯")
                time.sleep(0.4)
                st.rerun()
        else:
            st.info("💡 Click at least 3 or 4 points on the image to enable the save button.")

# Tab 3: History
with tab_history:
    st.subheader("📋 Security Incident History")
    records = []
    if os.path.exists(ALERTS_LOG):
        with open(ALERTS_LOG, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try: records.append(json.loads(line.strip()))
                    except: pass
    records.reverse()
    st.write(f"Total Logged Alerts: {len(records)}")
    for r in records[:10]:
        st.json(r)
