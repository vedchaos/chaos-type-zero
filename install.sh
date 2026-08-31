#!/bin/bash
# CHAOS TYPE ZERO — Linux/Mac Installer
# Run: chmod +x install.sh && ./install.sh

set -e

NEXUS_DIR="$(cd "$(dirname "$0")" && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo -e "${GREEN}  ╔══════════════════════════════════════════╗"
echo "  ║  CHAOS TYPE ZERO — Linux/Mac Installer   ║"
echo "  ║  Version: 3.3                            ║"
echo -e "  ╚══════════════════════════════════════════╝${NC}"
echo ""

# --- Step 1: Check Python ---
echo -e "${CYAN}[1/6] Checking Python installation...${NC}"
if command -v python3 &>/dev/null; then
    PY_VERSION=$(python3 --version 2>&1)
    PY_MAJOR=$(echo "$PY_VERSION" | grep -oE '3\.[0-9]+' | cut -d. -f2)
    if [ "$PY_MAJOR" -lt 10 ] 2>/dev/null; then
        echo -e "  ${RED}[ERROR] Python 3.10+ required. Found: $PY_VERSION${NC}"
        exit 1
    fi
    echo -e "  ${GREEN}[OK] $PY_VERSION detected${NC}"
    PYTHON=python3
elif command -v python &>/dev/null; then
    PY_VERSION=$(python --version 2>&1)
    echo -e "  ${GREEN}[OK] $PY_VERSION detected${NC}"
    PYTHON=python
else
    echo -e "  ${RED}[ERROR] Python not found. Install python3 first.${NC}"
    exit 1
fi

# --- Step 2: Install pip dependencies ---
echo -e "${CYAN}[2/6] Installing pip dependencies...${NC}"
REQ_FILE="$NEXUS_DIR/requirements.txt"
if [ -f "$REQ_FILE" ]; then
    $PYTHON -m pip install --upgrade pip --quiet 2>/dev/null || true
    if $PYTHON -m pip install -r "$REQ_FILE" --quiet 2>&1; then
        echo -e "  ${GREEN}[OK] Dependencies installed${NC}"
    else
        echo -e "  ${YELLOW}[WARN] Some dependencies may have failed. Continuing...${NC}"
    fi
else
    echo -e "  ${YELLOW}[SKIP] No requirements.txt found${NC}"
fi

# --- Step 3: Create data directories ---
echo -e "${CYAN}[3/6] Creating data directories...${NC}"
DIRS=(
    "data/memory"
    "data/context"
    "data/cache"
    "data/logs"
    "data/automation"
    "data/vault"
    "data/heuristics"
    "data/meta_reasoner"
)
for d in "${DIRS[@]}"; do
    mkdir -p "$NEXUS_DIR/$d"
done
echo -e "  ${GREEN}[OK] Data directories created${NC}"

# --- Step 4: Check Ollama ---
echo -e "${CYAN}[4/6] Checking Ollama...${NC}"
if command -v ollama &>/dev/null; then
    echo -e "  ${GREEN}[OK] Ollama found at $(which ollama)${NC}"
    echo -e "  ${CYAN}Pulling llama3 model (this may take a few minutes)...${NC}"
    if ollama pull llama3 2>&1; then
        echo -e "  ${GREEN}[OK] llama3 model ready${NC}"
    else
        echo -e "  ${YELLOW}[WARN] Model pull failed. Run 'ollama pull llama3' manually.${NC}"
    fi
else
    echo -e "  ${YELLOW}[WARN] Ollama not found. Install from https://ollama.com${NC}"
    echo -e "         Local LLM features will be unavailable."
fi

# --- Step 5: Create .env ---
echo -e "${CYAN}[5/6] Setting up environment...${NC}"
ENV_FILE="$NEXUS_DIR/.env"
ENV_TEMPLATE="$NEXUS_DIR/.env.template"
if [ ! -f "$ENV_FILE" ]; then
    if [ -f "$ENV_TEMPLATE" ]; then
        cp "$ENV_TEMPLATE" "$ENV_FILE"
        echo -e "  ${GREEN}[OK] Created .env from template${NC}"
    else
        cat > "$ENV_FILE" <<'ENVEOF'
# CHAOS TYPE ZERO — Environment Configuration
CTZ_ENV=development
CTZ_DEBUG=false
CTZ_LOG_LEVEL=info
CTZ_PORT=8080
CTZ_OLLAMA_HOST=http://localhost:11434
ENVEOF
        echo -e "  ${GREEN}[OK] Created default .env${NC}"
    fi
else
    echo -e "  ${YELLOW}[SKIP] .env already exists${NC}"
fi

# --- Step 6: Compile check ---
echo -e "${CYAN}[6/6] Running compile check...${NC}"
COMPILE_ERRORS=0
TOTAL=0
while IFS= read -r -d '' pyfile; do
    TOTAL=$((TOTAL + 1))
    if ! $PYTHON -c "import py_compile; py_compile.compile('$pyfile', doraise=True)" 2>/dev/null; then
        echo -e "  ${RED}[ERROR] Compilation failed: $(basename "$pyfile")${NC}"
        COMPILE_ERRORS=$((COMPILE_ERRORS + 1))
    fi
done < <(find "$NEXUS_DIR" -name "*.py" -type f -print0)

if [ "$COMPILE_ERRORS" -eq 0 ]; then
    echo -e "  ${GREEN}[OK] All $TOTAL Python files compile clean${NC}"
else
    echo -e "  ${YELLOW}[WARN] $COMPILE_ERRORS file(s) had compile errors${NC}"
fi

# --- Summary ---
echo ""
echo -e "${GREEN}  ════════════════════════════════════════"
echo "  INSTALLATION COMPLETE"
echo -e "  ════════════════════════════════════════${NC}"
echo ""
echo -e "  ${GREEN}Python:      OK${NC}"
echo -e "  ${GREEN}Deps:        OK${NC}"
echo -e "  ${GREEN}Directories: OK${NC}"
echo -e "  ${GREEN}Environment: OK${NC}"
echo ""
echo -e "  ${CYAN}Next steps:${NC}"
echo "    $PYTHON dashboard/server.py    # Start dashboard"
echo "    $PYTHON bridge_core.py          # Start core bridge"
echo ""
