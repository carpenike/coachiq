#!/bin/bash
# Command: /dev-health-check
# Description: Comprehensive development environment health check and diagnostics

set -euo pipefail

echo "🏥 Development Environment Health Check"
echo "═══════════════════════════════════════"
echo ""

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Python/Poetry
echo "🐍 Python Environment:"
if command -v poetry &> /dev/null; then
    echo -e "${GREEN}✓${NC} Poetry installed: $(poetry --version)"

    # Check if we're in a poetry environment
    if poetry env info &> /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} Poetry environment active"
        echo "  Python: $(poetry run python --version 2>&1)"

        # Check key dependencies
        missing_deps=0
        for dep in fastapi pydantic sqlalchemy pytest ruff pyright; do
            if ! poetry show $dep &> /dev/null 2>&1; then
                echo -e "${RED}✗${NC} Missing: $dep"
                ((missing_deps++))
            fi
        done

        if [ $missing_deps -eq 0 ]; then
            echo -e "${GREEN}✓${NC} All key dependencies installed"
        else
            echo -e "${YELLOW}⚠${NC} Run: poetry install"
        fi
    else
        echo -e "${RED}✗${NC} Not in poetry environment"
        echo "  Run: poetry install"
    fi
else
    echo -e "${RED}✗${NC} Poetry not found!"
    echo "  Install: curl -sSL https://install.python-poetry.org | python3 -"
fi
echo ""

# Check Node/npm
echo "📦 Node.js Environment:"
if command -v node &> /dev/null; then
    echo -e "${GREEN}✓${NC} Node.js installed: $(node --version)"

    if command -v npm &> /dev/null; then
        echo -e "${GREEN}✓${NC} npm installed: $(npm --version)"

        # Check if node_modules exists
        if [ -d "frontend/node_modules" ]; then
            echo -e "${GREEN}✓${NC} Frontend dependencies installed"
        else
            echo -e "${RED}✗${NC} Frontend dependencies missing"
            echo "  Run: cd frontend && npm install"
        fi
    else
        echo -e "${RED}✗${NC} npm not found!"
    fi
else
    echo -e "${RED}✗${NC} Node.js not found!"
fi
echo ""

# Check required config files
echo "📋 Configuration Files:"
for file in .env backend/services/feature_flags.yaml config/rvc.json; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓${NC} $file exists"
    else
        echo -e "${RED}✗${NC} $file missing"
        if [ "$file" = ".env" ]; then
            echo "  Run: cp .env.example .env"
        fi
    fi
done
echo ""

# Check database (if enabled)
echo "🗄️  Database Status:"
if [ -f ".env" ] && grep -q "COACHIQ_FEATURES__ENABLE_PERSISTENCE=true" .env 2>/dev/null; then
    if [ -f "data/main.db" ]; then
        echo -e "${GREEN}✓${NC} SQLite database exists"
        size=$(du -h data/main.db | cut -f1)
        echo "  Size: $size"
    else
        echo -e "${YELLOW}⚠${NC} Database file missing (will be created on startup)"
    fi
else
    echo "  Persistence disabled (SQLite not required)"
fi
echo ""

# Check services can start
echo "🚀 Service Startup Check:"
echo -n "  Backend syntax check... "
if poetry run python -m py_compile backend/main.py 2>/dev/null; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}✗${NC} Syntax errors in backend!"
fi

echo -n "  Frontend build check... "
if [ -d "frontend/node_modules" ] && cd frontend && npm run typecheck &>/dev/null; then
    echo -e "${GREEN}✓${NC}"
    cd ..
else
    echo -e "${YELLOW}⚠${NC} TypeScript errors (non-blocking)"
    cd .. 2>/dev/null || true
fi
echo ""

# Check for common issues
echo "🔍 Common Issues Check:"

# Port availability
for port in 8080 5173; do
    if lsof -i :$port &>/dev/null || netstat -an | grep -q ":$port.*LISTEN" 2>/dev/null; then
        echo -e "${YELLOW}⚠${NC} Port $port already in use"
        lsof -i :$port 2>/dev/null | grep LISTEN | head -1 || true
    else
        echo -e "${GREEN}✓${NC} Port $port available"
    fi
done

# File permissions
if [ -w "." ]; then
    echo -e "${GREEN}✓${NC} Directory writable"
else
    echo -e "${RED}✗${NC} Directory not writable!"
fi
echo ""

# Quick commands
echo "⚡ Quick Start Commands:"
echo "  Backend only:  poetry run python run_server.py --reload"
echo "  Frontend only: cd frontend && npm run dev"
echo "  Full stack:    Run both commands in separate terminals"
echo "  Tests:         poetry run pytest"
echo "  Type check:    poetry run pyright backend"
echo "  Lint:          poetry run ruff check ."
echo ""

# Environment info
echo "💻 System Info:"
echo "  OS: $(uname -s) $(uname -r)"
echo "  CPU: $(uname -m)"
echo "  Shell: $SHELL"
echo "  Current dir: $(pwd)"
echo ""

# Final status
errors=0
[ ! -f ".env" ] && ((errors++))
[ ! -d "frontend/node_modules" ] && ((errors++))
! command -v poetry &> /dev/null && ((errors++))

if [ $errors -eq 0 ]; then
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "✅ Environment is healthy and ready!"
    echo -e "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
else
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "⚠️  Environment needs setup ($errors issues)"
    echo -e "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
fi
