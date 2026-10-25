import streamlit as st
from PIL import Image, ImageDraw
import json
import os
import glob
import time
from datetime import datetime

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


st.title("🛡️ سامانه مدیریت هوشمند دوربین و مناطق خطر")

tab_live, tab_setup, tab_history = st.tabs([
    "📺 مانیتورینگ زنده و هشدارها", 
    "✏️ تنظیم و کالیبراسیون محدوده‌ها", 
    "📋 آرشیو وقایع و گزارشات"
])

# ----------------------------------------------------
# فرگمنت هشدارها
# ----------------------------------------------------
@st.fragment(run_every="2s")
def render_live_alerts():
    alerts = sorted(glob.glob(os.path.join(ALERTS_DIR, "*.jpg")), key=os.path.getmtime, reverse=True)
    if alerts:
        for alert_path in alerts[:4]:
            st.image(alert_path, caption=os.path.basename(alert_path), use_container_width=True)
    else:
        st.write("🟢 هیچ تخلف یا هشداری ثبت نشده است.")


# ----------------------------------------------------
# تب ۱: نمای زنده بدون قطعی
# ----------------------------------------------------
with tab_live:
    col_live, col_alerts = st.columns([2, 1])

    with col_live:
        st.subheader("تصویر زنده نظارتی (Stream 30FPS)")
        live_active = st.toggle("🔴 پخش زنده مستقیم", value=True)
        
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
            st.warning("پخش زنده موقتاً خاموش است.")

    with col_alerts:
        st.subheader("🚨 آخرین هشدارهای آنی")
        render_live_alerts()


# ----------------------------------------------------
# تب ۲: تنظیم محدوده با اسلایدر و پیش‌نمایش آنی
# ----------------------------------------------------
with tab_setup:
    st.subheader("مدیریت و تعیین محدوده نظارتی:")

    cfg = load_config()
    if cfg.get("zones"):
        st.markdown("### محدوده‌های فعال فعلی:")
        for idx, z in enumerate(list(cfg["zones"])):
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.write(f"📌 **{z['name']}** (اهداف: {', '.join(z['targets'])})")
            c2.write(f"فاصله هشدار: {z.get('cooldown_seconds', 8)} ثانیه")
            if c3.button("🗑️ حذف", key=f"del_{idx}"):
                cfg["zones"].pop(idx)
                save_config(cfg)
                st.rerun()

        if st.button("🗑️ حذف تمام محدوده‌ها", type="secondary"):
            save_config({"zones": []})
            st.rerun()

        st.markdown("---")

    col_ctrl, col_preview = st.columns([1, 2])

    # خواندن فریم فعلی برای مشخص شدن سایز تصویر
    orig_w, orig_h = 640, 480
    base_img = None
    if os.path.exists(LIVE_FRAME) and os.path.getsize(LIVE_FRAME) > 0:
        try:
            base_img = Image.open(LIVE_FRAME)
            orig_w, orig_h = base_img.size
        except Exception:
            base_img = None

    if base_img is None:
        base_img = Image.new("RGB", (orig_w, orig_h), color=(30, 30, 30))

    with col_ctrl:
        st.markdown("### تنظیمات کادر محدوده")
        zone_name = st.text_input("نام محدوده:", value=f"منطقه خطر {len(cfg.get('zones', [])) + 1}")
        target_type = st.multiselect(
            "اشیاء حساس جهت هشدار:",
            options=["person", "car", "motorcycle", "bus", "truck"],
            default=["person"],
            format_func=lambda x: {
                "person": "عابر پیاده (انسان)",
                "car": "خودرو",
                "motorcycle": "موتورسیکلت",
                "bus": "اتوبوس",
                "truck": "کامیون"
            }.get(x, x)
        )
        cooldown = st.slider("فاصله زمانی بین هشدارها (Cooldown به ثانیه):", 3, 60, 8)

        st.markdown("#### مختصات کادر (پیکسل):")
        pos_x = st.slider("موقعیت افقی (X شروع):", 0, orig_w - 50, int(orig_w * 0.2))
        pos_y = st.slider("موقعیت عمودی (Y شروع):", 0, orig_h - 50, int(orig_h * 0.2))
        box_w = st.slider("عرض محدوده (Width):", 20, orig_w - pos_x, int(orig_w * 0.5))
        box_h = st.slider("ارتفاع محدوده (Height):", 20, orig_h - pos_y, int(orig_h * 0.5))

    with col_preview:
        st.markdown(f"### پیش‌نمایش زنده کادر (ابعاد: {orig_w}x{orig_h})")
        # کشیدن کادر به صورت شفاف روی فریم کالیبراسیون
        preview_img = base_img.copy()
        draw = ImageDraw.Draw(preview_img)
        draw.rectangle(
            [pos_x, pos_y, pos_x + box_w, pos_y + box_h],
            outline="red",
            width=4
        )
        st.image(preview_img, caption="کادر قرمز محدوده انتخابی شماست", use_container_width=True)

    if st.button("💾 ذخیره این محدوده در سامانه", type="primary"):
        polygon = [
            [pos_x, pos_y],
            [pos_x + box_w, pos_y],
            [pos_x + box_w, pos_y + box_h],
            [pos_x, pos_y + box_h]
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
        st.success(f"محدوده «{zone_name}» با موفقیت ذخیره شد!")
        time.sleep(0.8)
        st.rerun()


# ----------------------------------------------------
# فرگمنت گزارشات
# ----------------------------------------------------
@st.fragment(run_every="3s")
def render_history_tab():
    logs = read_alert_logs()
    
    col_ref, col_flt = st.columns([1, 2])
    with col_ref:
        st.write(f"مجموع رویدادهای ثبت‌شده: **{len(logs)}**")

    with col_flt:
        all_zones = ["همه"] + sorted(list(set([l.get("zone_name") for l in logs if l.get("zone_name")])))
        selected_zone = st.selectbox("فیلتر بر اساس منطقه:", all_zones, key="flt_zone")

    if selected_zone != "همه":
        logs = [l for l in logs if l.get("zone_name") == selected_zone]

    if not logs:
        st.info("هنوز رخدادی ثبت نشده است.")
        return

    for log in logs[:25]:
        t_str = log.get("timestamp", "-")
        z_name = log.get("zone_name", "-")
        cls_name = log.get("class_name", "-")
        tid = log.get("track_id", "-")
        conf_val = log.get("confidence", 0.0)
        img_p = log.get("frame_path")

        with st.expander(f"🚨 [{t_str}] منطقه: {z_name} | شیء: {cls_name} (ID: {tid})"):
            ci, cd = st.columns([2, 1])
            with ci:
                if img_p and os.path.exists(img_p):
                    try:
                        im = Image.open(img_p)
                        st.image(im, caption=os.path.basename(img_p), use_container_width=True)
                    except Exception:
                        st.warning("خطا در بارگذاری تصویر.")
                else:
                    st.caption("تصویر یافت نشد.")
            with cd:
                st.write(f"**زمان:** `{t_str}`")
                st.write(f"**منطقه:** `{z_name}`")
                st.write(f"**کلاس:** `{cls_name}`")
                st.write(f"**شناسه Track:** `{tid}`")
                st.write(f"**اطمینان هوش مصنوعی:** `{int(conf_val * 100)}%`")


# ----------------------------------------------------
# تب ۳: رویدادها
# ----------------------------------------------------
with tab_history:
    st.subheader("📋 آرشیو زنده وقایع و هشدارهای ثبت‌شده")
    render_history_tab()
if __name__ == "__main__":
    from streamlit import runtime
    if not runtime.exists():
        import sys
        from streamlit.web import cli as stcli
        sys.argv = ["streamlit", "run", sys.argv[0]]
        sys.exit(stcli.main())
