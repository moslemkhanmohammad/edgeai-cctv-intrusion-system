import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import json
import os
import glob
import time

st.set_page_config(page_title="AI CCTV Multi-Zone Guard", layout="wide", page_icon="🛡️")

CONFIG_FILE = "zones_config.json"
LIVE_FRAME = "live_frame.jpg"
ALERTS_DIR = "alerts"
ALERTS_LOG = os.path.join(ALERTS_DIR, "alerts_log.jsonl")


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "zones" in data:
                    return data
        except Exception:
            pass
    return {"zones": []}


def save_config(data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def read_alert_logs():
    records = []
    if os.path.exists(ALERTS_LOG) and os.path.getsize(ALERTS_LOG) > 0:
        with open(ALERTS_LOG, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except Exception:
                    continue
    records.reverse()
    return records


st.title("🛡️ AI Vision Surveillance & Restricted Zone Guard")

tab_live, tab_setup, tab_history = st.tabs([
    "📺 Live Monitoring & Alerts", 
    "✏️ Zone Calibration", 
    "📋 Incident Archive & Reports"
])

# ----------------------------------------------------
# Real-Time Alerts Fragment
# ----------------------------------------------------
@st.fragment(run_every="2s")
def render_live_alerts():
    alerts = sorted(glob.glob(os.path.join(ALERTS_DIR, "*.jpg")), key=os.path.getmtime, reverse=True)
    if alerts:
        for alert_path in alerts[:4]:
            st.image(alert_path, caption=os.path.basename(alert_path), use_container_width=True)
    else:
        st.write("🟢 No security incidents detected.")


# ----------------------------------------------------
# Tab 1: Live Monitoring Feed
# ----------------------------------------------------
with tab_live:
    col_live, col_alerts = st.columns([2, 1])

    with col_live:
        st.subheader("Live RTSP / AI Stream (30 FPS)")
        live_active = st.toggle("🔴 Stream Active", value=True)
        
        if live_active:
            st.markdown(
                """
                <div style="border-radius: 8px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.15);">
                    <img src="http://localhost:8089/video_feed" style="width: 100%; height: auto; display: block;" />
                </div>
                """,
                unsafe_allow_html=True
            )
        else:
            st.warning("Live monitoring stream is currently paused.")

    with col_alerts:
        st.subheader("🚨 Real-Time Security Alerts")
        render_live_alerts()


# ----------------------------------------------------
# Tab 2: Zone Calibration
# ----------------------------------------------------
with tab_setup:
    st.subheader("Restricted Zone Calibration & Boundaries")

    cfg = load_config()

    # List and manage already configured zones
    if cfg.get("zones"):
        st.markdown("### 📋 Active Configured Zones:")
        for idx, z in enumerate(list(cfg["zones"])):
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.write(f"🛡️ **{z['name']}** (Targets: {', '.join(z.get('targets', ['person']))})")
            c2.write(f"Cooldown: {z.get('cooldown_seconds', 8)}s")
            if c3.button("🗑️ Remove", key=f"del_{idx}"):
                cfg["zones"].pop(idx)
                save_config(cfg)
                st.success(f"Removed {z['name']}")
                time.sleep(0.5)
                st.rerun()

        if st.button("🗑️ Clear All Zones", type="secondary"):
            save_config({"zones": []})
            st.rerun()

        st.markdown("---")

    # Load Background Frame
    orig_w, orig_h = 640, 480
    base_img = None
    if os.path.exists(LIVE_FRAME) and os.path.getsize(LIVE_FRAME) > 0:
        try:
            base_img = Image.open(LIVE_FRAME).convert("RGB")
            orig_w, orig_h = base_img.size
        except Exception:
            base_img = None

    if base_img is None:
        base_img = Image.new("RGB", (orig_w, orig_h), color=(40, 44, 52))

    # Initialize session state for interactive coordinates if not present
    if "calib_x1" not in st.session_state:
        st.session_state.calib_x1 = int(orig_w * 0.2)
        st.session_state.calib_y1 = int(orig_h * 0.2)
        st.session_state.calib_x2 = int(orig_w * 0.7)
        st.session_state.calib_y2 = int(orig_h * 0.7)

    col_ctrl, col_canvas = st.columns([1, 2])

    with col_ctrl:
        st.markdown("### 1. Zone Parameters")
        zone_name = st.text_input("Zone Label:", value=f"Zone {len(cfg.get('zones', [])) + 1}")
        target_type = st.multiselect(
            "Trigger Object Classes:",
            options=["person", "car", "motorcycle", "bus", "truck"],
            default=["person"]
        )
        cooldown = st.slider("Cooldown Interval (Seconds):", 3, 60, 8)

        st.markdown("---")
        st.markdown("### 2. Precise Boundary Coordinates")

        # Range sliders for intuitive left/right and top/bottom control
        x_range = st.slider("Horizontal Span (X1 - X2):", 0, orig_w, (st.session_state.calib_x1, st.session_state.calib_x2))
        y_range = st.slider("Vertical Span (Y1 - Y2):", 0, orig_h, (st.session_state.calib_y1, st.session_state.calib_y2))

        # Update session state
        st.session_state.calib_x1, st.session_state.calib_x2 = x_range
        st.session_state.calib_y1, st.session_state.calib_y2 = y_range

        st.caption(f"Coordinates: `[{x_range[0]}, {y_range[0]}]` to `[{x_range[1]}, {y_range[1]}]`")

        if st.button("💾 Save Zone Definition", type="primary", use_container_width=True):
            polygon = [
                [x_range[0], y_range[0]],
                [x_range[1], y_range[0]],
                [x_range[1], y_range[1]],
                [x_range[0], y_range[1]]
            ]
            cfg = load_config()
            new_zone = {
                "id": f"zone_{int(time.time())}",
                "name": zone_name,
                "targets": target_type,
                "polygon": polygon,
                "cooldown_seconds": cooldown,
                "enabled": True
            }
            cfg["zones"].append(new_zone)
            save_config(cfg)
            st.success(f"✅ Zone '{zone_name}' saved and activated!")
            time.sleep(0.8)
            st.rerun()

    with col_canvas:
        st.markdown(f"### Visual Alignment Preview ({orig_w}x{orig_h})")
        st.caption("🟢 **Green boxes:** Already active saved zones | 🔴 **Red box:** Currently editing zone")

        # Create overlay image
        preview_img = base_img.copy()
        draw = ImageDraw.Draw(preview_img)

        # 1. Draw all previously saved zones in GREEN
        for z in cfg.get("zones", []):
            pts = [tuple(p) for p in z["polygon"]]
            if len(pts) >= 4:
                draw.polygon(pts, outline=(0, 255, 100), width=3)
                draw.text((pts[0][0] + 5, max(pts[0][1] - 15, 5)), f"ACTIVE: {z['name']}", fill=(0, 255, 100))

        # 2. Draw currently edited zone in RED
        cur_box = [
            (x_range[0], y_range[0]),
            (x_range[1], y_range[0]),
            (x_range[1], y_range[1]),
            (x_range[0], y_range[1])
        ]
        draw.polygon(cur_box, outline=(255, 50, 50), width=4)
        draw.text((x_range[0] + 5, max(y_range[0] - 15, 5)), f"NEW: {zone_name}", fill=(255, 50, 50))

        st.image(preview_img, caption="Live camera background with active and pending zones", use_container_width=True)


# ----------------------------------------------------
# Tab 3: Historical Logs & Filtering Fragment
# ----------------------------------------------------
@st.fragment(run_every="3s")
def render_history_tab():
    logs = read_alert_logs()
    
    col_ref, col_flt = st.columns([1, 2])
    with col_ref:
        st.write(f"Total Registered Incidents: **{len(logs)}**")

    with col_flt:
        all_zones = ["All"] + sorted(list(set([l.get("zone_name") for l in logs if l.get("zone_name")])))
        selected_zone = st.selectbox("Filter by Zone:", all_zones, key="flt_zone")

    if selected_zone != "All":
        logs = [l for l in logs if l.get("zone_name") == selected_zone]

    if not logs:
        st.info("No recorded breach logs available yet.")
        return

    for log in logs[:25]:
        t_str = log.get("timestamp", "-")
        z_name = log.get("zone_name", "-")
        cls_name = log.get("class_name", "-")
        tid = log.get("track_id", "-")
        conf_val = log.get("confidence", 0.0)
        img_p = log.get("frame_path")

        with st.expander(f"🚨 [{t_str}] Zone: {z_name} | Target: {cls_name} (ID: {tid})"):
            ci, cd = st.columns([2, 1])
            with ci:
                if img_p and os.path.exists(img_p):
                    try:
                        im = Image.open(img_p)
                        st.image(im, caption=os.path.basename(img_p), use_container_width=True)
                    except Exception:
                        st.warning("Failed to render incident snapshot.")
                else:
                    st.caption("Snapshot not found.")
            with cd:
                st.write(f"**Timestamp:** `{t_str}`")
                st.write(f"**Zone:** `{z_name}`")
                st.write(f"**Target Class:** `{cls_name}`")
                st.write(f"**Track ID:** `{tid}`")
                st.write(f"**AI Confidence:** `{int(conf_val * 100)}%`")


with tab_history:
    st.subheader("📋 Security Incident History & Breach Audits")
    render_history_tab()


if __name__ == "__main__":
    from streamlit import runtime
    if not runtime.exists():
        import sys
        from streamlit.web import cli as stcli
        sys.argv = ["streamlit", "run", sys.argv[0]]
        sys.exit(stcli.main())
