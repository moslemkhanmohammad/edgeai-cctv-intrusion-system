@echo off
title AI CCTV Surveillance System
echo ====================================================
echo Starting AI Surveillance Vision Core & Web Dashboard
echo ====================================================

start "AI Core" cmd /k "python run_ai.py"
timeout /t 3 >nul
start "Web Dashboard" cmd /k "streamlit run dashboard_web.py"

echo System started successfully!
