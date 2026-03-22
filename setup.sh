#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

info()  { printf "${GREEN}✓${NC} %s\n" "$1"; }
warn()  { printf "${YELLOW}!${NC} %s\n" "$1"; }
err()   { printf "${RED}✗${NC} %s\n" "$1"; }
step()  { printf "\n${BOLD}── %s${NC}\n" "$1"; }

# ── 1. Check Python ──────────────────────────────────────────────────

step "Checking prerequisites"

if ! command -v python3 &>/dev/null; then
    err "Python 3 not found. Install Python 3.12+ first: https://python.org"
    exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 12 ]; }; then
    err "Python $PY_VERSION found, but 3.12+ is required."
    exit 1
fi
info "Python $PY_VERSION"

# ── 2. Install uv if missing ────────────────────────────────────────

if ! command -v uv &>/dev/null; then
    warn "uv not found — installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    info "uv installed"
else
    info "uv $(uv --version 2>/dev/null || echo 'found')"
fi

# ── 3. Install Python dependencies ──────────────────────────────────

step "Installing Python dependencies"
uv sync
info "Python deps installed"

# ── 4. Install Playwright browsers ──────────────────────────────────

step "Installing Playwright browsers (for Twitter/Reddit automation)"
uv run playwright install chromium 2>/dev/null && info "Playwright Chromium installed" \
    || warn "Playwright browser install failed — you can run 'uv run playwright install' later"

# ── 5. Node.js / Remotion (optional) ────────────────────────────────

step "Checking Node.js (optional — needed for Instagram Reels)"

REMOTION_DIR="src/adapters/instagram/reels/remotion"

if command -v node &>/dev/null; then
    NODE_VERSION=$(node --version)
    info "Node.js $NODE_VERSION"
    if [ -f "$REMOTION_DIR/package.json" ]; then
        (cd "$REMOTION_DIR" && npm install --silent 2>/dev/null) \
            && info "Remotion deps installed" \
            || warn "npm install failed in $REMOTION_DIR — run it manually if you need Reels"
    fi
else
    warn "Node.js not found — skip this if you don't need Instagram Reels"
    warn "Install later: https://nodejs.org (v18+)"
fi

# ── 6. Git hooks (pre-push: tests + lint) ──────────────────────────

step "Installing Git hooks"

if [ -d .git ]; then
    uv run pre-commit install --hook-type pre-push 2>/dev/null \
        && info "pre-push hook installed (runs tests + lint before push)" \
        || warn "pre-commit install failed — run 'uv run pre-commit install --hook-type pre-push' manually"
else
    warn "Not a Git repository — skipping hook install"
fi

# ── 7. Environment file ─────────────────────────────────────────────

step "Setting up environment"

if [ ! -f .env ]; then
    cp .env.example .env
    info "Created .env from .env.example"
    warn "Edit .env with your API keys before running"
else
    info ".env already exists — skipping"
fi

# ── 8. PostgreSQL via Docker ─────────────────────────────────────────

step "Database setup"

if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    if docker compose ps --services 2>/dev/null | grep -q postgres; then
        info "PostgreSQL container already running"
    else
        printf "  Start PostgreSQL via Docker Compose? [Y/n] "
        read -r REPLY
        REPLY=${REPLY:-Y}
        if [[ "$REPLY" =~ ^[Yy]$ ]]; then
            docker compose up -d postgres
            info "PostgreSQL started on localhost:5432 (user: mmn, db: marketmenow)"
            info "Database URL: postgresql://mmn:mmn@localhost:5432/marketmenow"
        else
            warn "Skipped — set MMN_WEB_DATABASE_URL in .env manually"
        fi
    fi
else
    warn "Docker not found — install Docker to auto-start PostgreSQL,"
    warn "or set MMN_WEB_DATABASE_URL in .env to an existing database"
fi

# ── Done ──────────────────────────────────────────────────────────────

step "Setup complete!"
printf "\n"
printf "  ${BOLD}Next steps:${NC}\n"
printf "  1. Edit ${BOLD}.env${NC} with your API keys\n"
printf "  2. Run the dashboard:  ${BOLD}uv run mmn-web${NC}\n"
printf "  3. Open ${BOLD}http://localhost:8000${NC}\n"
printf "\n"
printf "  Or use the CLI:  ${BOLD}uv run mmn --help${NC}\n"
printf "\n"
