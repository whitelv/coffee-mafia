# Coffee Bar Management System

## Overview
Full-stack IoT coffee bar assistant. ESP32 hardware with HX711 weight sensor and MFRC522 RFID reader. FastAPI backend on Render. Vanilla JS frontend on Vercel. MongoDB Atlas database.

## Architecture
- Hardware: ESP32 + HX711 (DOUT=4, SCK=2) + MFRC522 (SS=5, RST=16)
- Backend: Python FastAPI + Motor (async MongoDB driver)
- Frontend: Vanilla JS, 5 pages, no build step required
- Database: MongoDB Atlas M0 free cluster
- Real-time: WebSocket communication between ESP32, backend, browser

## Setup Order
Follow this exact order or things will not work.

### Step 1 - MongoDB Atlas
1. Create account at mongodb.com/atlas
2. Create M0 free cluster
3. Create database user with password
4. Add Network Access: 0.0.0.0/0 (allow all IPs)
5. Get connection string: mongodb+srv://<user>:<pass>@cluster0.xxx.mongodb.net/coffeebardb
6. Create database named: coffeebardb

### Step 2 - Backend on Render
1. Fork or push this repo to GitHub
2. Go to render.com, create new Web Service
3. Connect your GitHub repo
4. Render will detect render.yaml automatically
5. Set environment variables in Render dashboard:
   - MONGODB_URI = your Atlas connection string
   - JWT_SECRET = any long random string
   - ALLOWED_ORIGINS = https://your-app.vercel.app
6. Deploy - first deploy takes 2-3 minutes
7. Note your backend URL: https://coffee-bar-backend.onrender.com

### Step 3 - Seed the database
Run locally after backend is deployed:

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your real MONGODB_URI and JWT_SECRET
python scripts/seed_db.py
```

### Step 4 - Frontend on Vercel
1. Go to vercel.com, create new project
2. Connect your GitHub repo
3. Set Root Directory to: frontend
4. No build command needed
5. Set environment variable:
   - No env vars needed - frontend reads backend URL from js/api.js
6. Update js/api.js BASE_URL to point to your Render backend URL
7. Deploy

### Step 5 - ESP32 Firmware
1. Install PlatformIO in VS Code
2. Copy firmware/coffee_esp32/include/config.example.h to firmware/coffee_esp32/include/config.h
3. Edit config.h:
   - Set WIFI_SSID and WIFI_PASSWORD
   - Set WS_HOST to your Render backend hostname (no https://)
   - Set WS_PORT to 443
   - Set WS_USE_SSL to true
4. Open firmware/coffee_esp32 in PlatformIO
5. Build and upload to ESP32
6. Open Serial Monitor at 115200 baud
7. ESP32 should connect to WiFi then WebSocket

### Step 6 - HX711 Calibration
1. Open scripts/calibrate_hx711 in PlatformIO or Arduino IDE
2. Flash to ESP32
3. Open Serial Monitor at 115200
4. Follow prompts - place known weight when asked
5. Copy printed CALIBRATION_F value into config.h
6. Reflash main firmware

### Step 7 - Add RFID Users
Use the admin panel at /admin.html or run curl:

```bash
# Get admin JWT first
python scripts/generate_jwt.py --role admin

# Create users (replace token and UIDs with your values)
curl -X POST https://your-backend.onrender.com/api/users \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Worker 1", "rfid_uid": "819597A3", "role": "client"}'
```

## Development Setup

```bash
cd /path/to/coffee-bar
bash scripts/setup_dev.sh
# In one terminal:
cd backend && source venv/bin/activate
uvicorn main:app --reload --port 8000
# Open frontend/index.html in browser
```

## Environment Variables
See backend/.env.example for all required variables.

## Project Structure

```text
coffee-bar/
├── backend/          # FastAPI application
├── firmware/         # ESP32 PlatformIO project
├── frontend/         # Vanilla JS frontend
├── scripts/          # Dev and seed scripts
├── render.yaml       # Render deployment config
└── README.md
```
