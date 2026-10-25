# 👁️ EdgeAI-CCTV: Real-Time Zone Intrusion & Safety Compliance System

[![Python 3.11](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Gateway-009688.svg)](https://fastapi.tiangolo.com/)
[![YOLO11](https://img.shields.io/badge/Ultralytics-YOLO11-orange.svg)](https://ultralytics.com/)
[![Docker](https://img.shields.io/badge/Docker-Microservices-2496ED.svg)](https://www.docker.com/)

A production-ready, containerized Computer Vision & Edge AI surveillance system designed for real-time zone intrusion detection, safety compliance, and automated alerting. Built with a modern microservices architecture to mimic enterprise-grade industrial monitoring solutions (inspired by platforms like viAct.ai).

---

## 🚀 Key Features

- **Multi-Zone Intrusion Detection:** Define custom polygonal/rectangular zones dynamically and detect unauthorized entry (e.g., restricted areas, parking zones, industrial hazard sites).
- **Edge AI Engine:** Powered by **Ultralytics YOLO11** optimized for high-accuracy object detection (person, vehicles, etc.) under challenging overhead and standard camera angles.
- **Microservices Architecture:** Decoupled architecture using **FastAPI** as a streaming gateway and an independent AI processing engine communicating via Docker volumes.
- **Low-Latency MJPEG Streaming:** High-performance live video streaming endpoint (`/video_feed`) accessible via standard web clients or downstream dashboards.
- **Automated Incident Logging & Alerts:** Real-time event logging, snapshot capture upon intrusion, and instant notifications (Telegram Bot & desktop alerts).
- **Containerized Deployment:** Fully dockerized with `Docker Compose` for seamless one-command deployment across cloud servers (AWS, DigitalOcean) or edge hardware.

---

## 🛠️ Tech Stack

- **Core:** Python 3.11, OpenCV, NumPy
- **Computer Vision Model:** Ultralytics YOLO11 (`yolo11s.pt`)
- **API & Streaming:** FastAPI, Uvicorn, Multipart MJPEG
- **Containerization:** Docker & Docker Compose
- **Notifications:** Telegram Bot API, Plyer, Requests

---

## 📂 Project Structure
```text
.
├── cctv_fixed/
│   ├── run_ai.py           # Core AI processing loop & zone logic
│   ├── fastapi_gateway.py  # FastAPI streaming & gateway server
│   ├── zone_utils.py       # Polygon zone management & configuration
│   └── zone_canvas/        # Interactive canvas UI for zone definition
├── alerts/                 # JSONL logs and captured intrusion snapshots
├── Dockerfile.ai           # Docker configuration for AI Engine
├── Dockerfile.gateway      # Docker configuration for FastAPI Gateway
├── docker-compose.yml      # Orchestration file for microservices
├── requirements.txt        # Python dependencies
└── README.md
