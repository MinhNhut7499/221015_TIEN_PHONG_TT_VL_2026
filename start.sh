#!/usr/bin/env bash
# ============================================================
# Architecture AI Backend — Startup Script
# Usage: bash start.sh [--prod]
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Colour helpers ─────────────────────────────────────────────
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── Pre-flight checks ──────────────────────────────────────────
info "Starting Architecture AI Backend..."

if [ ! -f ".env" ]; then
    error ".env file not found. Run: cp .env.example .env  — then fill in your values."
fi

python_version=$(python3 --version 2>&1 | awk '{print $2}')
required_major=3
required_minor=10
actual_major=$(echo "$python_version" | cut -d. -f1)
actual_minor=$(echo "$python_version" | cut -d. -f2)

if [ "$actual_major" -lt "$required_major" ] || \
   ([ "$actual_major" -eq "$required_major" ] && [ "$actual_minor" -lt "$required_minor" ]); then
    error "Python ${required_major}.${required_minor}+ required. Found: $python_version"
fi

info "Python version: $python_version — OK"

# ── Dependency installation ────────────────────────────────────
info "Installing dependencies from requirements.txt..."
pip install -r requirements.txt --quiet

# ── Upload directory ───────────────────────────────────────────
mkdir -p utils/upload_temp utils/download utils/data_vector
info "Upload directories verified."

# ── Launch ─────────────────────────────────────────────────────
MODE="${1:-}"
if [ "$MODE" == "--prod" ]; then
    warn "Production mode: reload disabled, log level = info"
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2 --log-level info
else
    info "Development mode: hot-reload enabled"
    python run_api.py
fi
