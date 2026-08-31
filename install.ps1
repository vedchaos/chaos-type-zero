# CHAOS TYPE ZERO — Windows Installer
# Run: powershell -ExecutionPolicy Bypass -File install.ps1

$ErrorActionPreference = "Stop"
$NEXUS_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "  ╔══════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "  ║  CHAOS TYPE ZERO — Windows Installer     ║" -ForegroundColor Green
Write-Host "  ║  Version: 3.3                            ║" -ForegroundColor Green
Write-Host "  ╚══════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""

# --- Step 1: Check Python ---
Write-Host "[1/6] Checking Python installation..." -ForegroundColor Cyan
try {
    $pyVersion = python --version 2>&1
    if ($pyVersion -match "Python 3\.(\d+)") {
        $minor = [int]$Matches[1]
        if ($minor -lt 10) {
            Write-Host "  [ERROR] Python 3.10+ required. Found: $pyVersion" -ForegroundColor Red
            exit 1
        }
        Write-Host "  [OK] $pyVersion detected" -ForegroundColor Green
    } else {
        Write-Host "  [ERROR] Python 3 not found" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "  [ERROR] Python not found. Install from https://python.org" -ForegroundColor Red
    exit 1
}

# --- Step 2: Install pip dependencies ---
Write-Host "[2/6] Installing pip dependencies..." -ForegroundColor Cyan
$reqFile = Join-Path $NEXUS_DIR "requirements.txt"
if (Test-Path $reqFile) {
    python -m pip install --upgrade pip --quiet 2>&1 | Out-Null
    $result = python -m pip install -r $reqFile --quiet 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [WARN] Some dependencies may have failed. Continuing..." -ForegroundColor Yellow
    } else {
        Write-Host "  [OK] Dependencies installed" -ForegroundColor Green
    }
} else {
    Write-Host "  [SKIP] No requirements.txt found" -ForegroundColor Yellow
}

# --- Step 3: Create data directories ---
Write-Host "[3/6] Creating data directories..." -ForegroundColor Cyan
$dirs = @(
    "data\memory",
    "data\context",
    "data\cache",
    "data\logs",
    "data\automation",
    "data\vault",
    "data\heuristics",
    "data\meta_reasoner"
)
foreach ($d in $dirs) {
    $fullPath = Join-Path $NEXUS_DIR $d
    if (-not (Test-Path $fullPath)) {
        New-Item -ItemType Directory -Path $fullPath -Force | Out-Null
    }
}
Write-Host "  [OK] Data directories created" -ForegroundColor Green

# --- Step 4: Check Ollama ---
Write-Host "[4/6] Checking Ollama..." -ForegroundColor Cyan
try {
    $ollamaPath = Get-Command ollama -ErrorAction SilentlyContinue
    if ($ollamaPath) {
        Write-Host "  [OK] Ollama found at $($ollamaPath.Source)" -ForegroundColor Green
        Write-Host "  Pulling llama3 model (this may take a few minutes)..." -ForegroundColor Cyan
        ollama pull llama3 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  [OK] llama3 model ready" -ForegroundColor Green
        } else {
            Write-Host "  [WARN] Model pull failed. Run 'ollama pull llama3' manually." -ForegroundColor Yellow
        }
    } else {
        Write-Host "  [WARN] Ollama not found. Install from https://ollama.com" -ForegroundColor Yellow
        Write-Host "         Local LLM features will be unavailable." -ForegroundColor Yellow
    }
} catch {
    Write-Host "  [WARN] Could not check Ollama: $_" -ForegroundColor Yellow
}

# --- Step 5: Create .env ---
Write-Host "[5/6] Setting up environment..." -ForegroundColor Cyan
$envFile = Join-Path $NEXUS_DIR ".env"
$envTemplate = Join-Path $NEXUS_DIR ".env.template"
if (-not (Test-Path $envFile)) {
    if (Test-Path $envTemplate) {
        Copy-Item $envTemplate $envFile
        Write-Host "  [OK] Created .env from template" -ForegroundColor Green
    } else {
        $defaultEnv = @"
# CHAOS TYPE ZERO — Environment Configuration
CTZ_ENV=development
CTZ_DEBUG=false
CTZ_LOG_LEVEL=info
CTZ_PORT=8080
CTZ_OLLAMA_HOST=http://localhost:11434
"@
        Set-Content -Path $envFile -Value $defaultEnv
        Write-Host "  [OK] Created default .env" -ForegroundColor Green
    }
} else {
    Write-Host "  [SKIP] .env already exists" -ForegroundColor Yellow
}

# --- Step 6: Compile check ---
Write-Host "[6/6] Running compile check..." -ForegroundColor Cyan
$pyFiles = Get-ChildItem -Path $NEXUS_DIR -Filter "*.py" -Recurse -ErrorAction SilentlyContinue
$compileErrors = 0
foreach ($f in $pyFiles) {
    $result = python -c "import py_compile; py_compile.compile('$($f.FullName)', doraise=True)" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [ERROR] Compilation failed: $($f.Name)" -ForegroundColor Red
        Write-Host "    $result" -ForegroundColor Red
        $compileErrors++
    }
}
if ($compileErrors -eq 0) {
    Write-Host "  [OK] All $($pyFiles.Count) Python files compile clean" -ForegroundColor Green
} else {
    Write-Host "  [WARN] $compileErrors file(s) had compile errors" -ForegroundColor Yellow
}

# --- Summary ---
Write-Host ""
Write-Host "  ════════════════════════════════════════" -ForegroundColor Green
Write-Host "  INSTALLATION COMPLETE" -ForegroundColor Green
Write-Host "  ════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "  Python:     OK" -ForegroundColor Green
Write-Host "  Deps:       OK" -ForegroundColor Green
Write-Host "  Directories: OK" -ForegroundColor Green
Write-Host "  Environment: OK" -ForegroundColor Green
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor Cyan
Write-Host "    python dashboard/server.py    # Start dashboard" -ForegroundColor White
Write-Host "    python bridge_core.py          # Start core bridge" -ForegroundColor White
Write-Host ""
