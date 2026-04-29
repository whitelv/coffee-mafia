# Coffee Bar Management System

A hardware-integrated coffee bar management system with real-time weight streaming.

## Architecture

```
┌──────────────┐   WebSocket   ┌──────────────────────┐   WebSocket   ┌─────────────────┐
│   ESP32      │ ◄───────────► │  FastAPI Backend      │ ◄───────────► │  Browser (JS)   │
│  HX711       │               │  MongoDB Atlas        │               │  Vanilla JS     │
│  MFRC522     │               │  Render.com           │               │  Vercel         │
└──────────────┘               └──────────────────────┘               └─────────────────┘
```

**Hardware:** ESP32 with HX711 (weight sensor) and MFRC522 (RFID reader)  
**Backend:** Python FastAPI + MongoDB Atlas, deployed on Render  
**Frontend:** Vanilla JS static site, deployed on Vercel  
**Auth:** RFID-card based — no passwords

## Quick Start

### 1. Prerequisites
- Python 3.10+
- MongoDB Atlas account (free tier works)
- Node.js (optional, for serving frontend locally)

### 2. Backend Setup

```bash
cd coffee-bar
bash scripts/setup_dev.sh
```

This will:
- Create a Python virtual environment
- Install dependencies
- Copy `.env.example` → `backend/.env`
- Seed the database with sample users and recipes

Edit `backend/.env`:
```env
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/coffeedb
JWT_SECRET=<generate with: python3 -c "import secrets; print(secrets.token_hex(32))">
```

### 3. Start the Backend

```bash
cd backend
source .venv/bin/activate
uvicorn main:app --reload --port 8000
```

API docs available at: http://localhost:8000/docs

### 4. Start the Frontend

```bash
cd frontend
python3 -m http.server 3000
# Open http://localhost:3000/index.html
```

### 5. Test Authentication (without hardware)

```bash
# Generate a token for a user
cd scripts
python generate_jwt.py --rfid CLIENT001

# Or trigger auth flow manually (simulates RFID scan)
# The /auth/status endpoint polls for pending_auth set by WebSocket
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/auth/status?esp_id=` | Poll for auth result |
| GET | `/api/recipes` | List active recipes |
| POST | `/api/sessions` | Create brew session |
| PATCH | `/api/sessions/current/heartbeat` | Session keepalive |
| GET | `/api/history` | Brew history |
| GET | `/api/users` | List users (admin) |
| WS | `/ws/esp/{esp_id}` | ESP32 WebSocket |
| WS | `/ws/browser/{session_id}` | Browser WebSocket |

## WebSocket Events

### ESP32 → Backend
| Event | Payload |
|-------|---------|
| `rfid_scan` | `{uid}` |
| `weight_reading` | `{value, unit}` |
| `heartbeat` | `{state}` |

### Backend → ESP32
| Event | Payload |
|-------|---------|
| `auth_ok` | `{token, user, resume_available}` |
| `auth_fail` | `{reason}` |
| `request_weight` | `{target}` |
| `stop_weight` | — |
| `tare_scale` | — |
| `session_complete` | — |
| `session_abandoned` | — |

### Backend → Browser
| Event | Payload |
|-------|---------|
| `session_state` | `{status, current_step, recipe}` |
| `weight_update` | `{value, stable}` |
| `weight_stable` | `{value}` |
| `step_advance` | `{step_index, step}` |
| `session_complete` | — |
| `session_abandoned` | — |
| `esp_disconnected` | — |
| `esp_reconnected` | — |

## Hardware Wiring

| Component | ESP32 Pin |
|-----------|-----------|
| HX711 DOUT | GPIO 4 |
| HX711 SCK | GPIO 2 |
| MFRC522 SS | GPIO 5 |
| MFRC522 RST | GPIO 16 |
| SPI SCK | GPIO 18 (hardware default) |
| SPI MISO | GPIO 19 (hardware default) |
| SPI MOSI | GPIO 23 (hardware default) |

### HX711 Calibration

1. Upload `scripts/calibrate_hx711/calibrate_hx711.ino`
2. Open Serial Monitor at 115200 baud
3. Follow on-screen instructions
4. Copy the calibration factor to `firmware/coffee_esp32/config.h`

## Project Structure

```
coffee-bar/
├── backend/
│   ├── main.py          # FastAPI app, lifespan
│   ├── config.py        # Settings (pydantic-settings)
│   ├── database.py      # Motor async client
│   ├── state.py         # In-memory session registry
│   ├── models/          # Pydantic v2 models
│   └── routers/         # auth, ws, recipes, sessions, history, users
├── frontend/
│   ├── index.html       # RFID scan / login
│   ├── select.html      # Recipe selection
│   ├── brew.html        # Real-time brew guidance
│   ├── history.html     # Brew history
│   ├── admin.html       # Admin panel
│   ├── css/style.css
│   └── js/              # api.js, ws.js, per-page scripts
├── firmware/
│   └── coffee_esp32/    # Arduino sketch + config.h
├── scripts/
│   ├── seed_db.py       # Idempotent seeder
│   ├── reset_db.py      # Drop + re-seed
│   ├── generate_jwt.py  # CLI JWT generator
│   ├── setup_dev.sh     # Dev environment setup
│   └── calibrate_hx711/ # HX711 calibration sketch
└── render.yaml          # Render.com deployment config
```

## Default Seed Data

| User | RFID UID | Role |
|------|----------|------|
| Admin | ADMIN001 | admin |
| Barista 1 | CLIENT001 | client |

5 recipes pre-loaded: Espresso, Americano, Latte, Cappuccino, Flat White

## Deployment

### Backend (Render)

1. Push to GitHub
2. Create new Web Service on Render, connect repo
3. Set `Root Directory` to `backend`
4. Add environment variables from `render.yaml`
5. Deploy

### Frontend (Vercel)

1. Point Vercel to the `frontend/` directory
2. Update `ALLOWED_ORIGINS` in the backend to include your Vercel domain
3. Update API URLs in `frontend/js/api.js` if the backend is not on the same origin
