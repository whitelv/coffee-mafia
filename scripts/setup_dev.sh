#!/usr/bin/env bash
set -euo pipefail

# -----------------------------------------------------------------------
# Coffee Bar — Development Setup Script
# -----------------------------------------------------------------------

REQUIRED_PYTHON_MAJOR=3
REQUIRED_PYTHON_MINOR=10

# ---- Check Python version ----
if ! command -v python3 &>/dev/null; then
  echo "Error: python3 not found. Install Python 3.10 or higher." >&2
  exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt "$REQUIRED_PYTHON_MAJOR" ] || \
   ([ "$PYTHON_MAJOR" -eq "$REQUIRED_PYTHON_MAJOR" ] && [ "$PYTHON_MINOR" -lt "$REQUIRED_PYTHON_MINOR" ]); then
  echo "Error: Python $REQUIRED_PYTHON_MAJOR.$REQUIRED_PYTHON_MINOR+ required. Found: $PYTHON_VERSION" >&2
  exit 1
fi

echo "✔ Python $PYTHON_VERSION detected"

# ---- Navigate to backend ----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/../backend"
cd "$BACKEND_DIR"

# ---- Create virtual environment ----
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

# ---- Activate venv ----
# shellcheck disable=SC1091
source .venv/bin/activate
echo "✔ Virtual environment activated"

# ---- Install dependencies ----
echo "Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
echo "✔ Dependencies installed"

# ---- Copy .env if missing ----
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "✔ Created backend/.env from .env.example"
  echo ""
  echo "  !! ACTION REQUIRED: Edit backend/.env and set:"
  echo "     MONGODB_URI=mongodb+srv://..."
  echo "     JWT_SECRET=<random 64-char string>"
  echo ""
else
  echo "✔ backend/.env already exists"
fi

# ---- Run seed script ----
echo "Seeding database..."
cd "$SCRIPT_DIR"
python seed_db.py
echo "✔ Database seeded"

# ---- ASCII coffee cup ----
cat << 'EOF'

        ( (
         ) )
      ........
      |      |]
      \      /
       `----'

  ☕  Coffee Bar is ready!

Next steps:
  1. Edit backend/.env with your MongoDB URI and JWT secret
  2. Start the backend:
       cd backend
       source .venv/bin/activate
       uvicorn main:app --reload --port 8000
  3. Open the frontend:
       Open frontend/index.html in your browser, or serve it:
       cd frontend && python3 -m http.server 3000
  4. Test the API:
       curl http://localhost:8000/health
       curl http://localhost:8000/api/recipes

Tip: run 'python scripts/generate_jwt.py --rfid ADMIN001' to get an admin token for testing

EOF
