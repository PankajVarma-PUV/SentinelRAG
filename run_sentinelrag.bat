@echo off
setlocal enabledelayedexpansion

REM ==========================================================
REM SentinelRAG - Startup Script (Windows 11)
REM ==========================================================

set "BASE_DIR=%~dp0"
if "%BASE_DIR:~-1%"=="\" set "BASE_DIR=%BASE_DIR:~0,-1%"
cd /d "%BASE_DIR%"

set "PORT=8000"
set "RELOAD_FLAG=--reload"

echo ==========================================================
echo  SentinelRAG: Metacognitive Intelligence System
echo ==========================================================
echo  Project : %BASE_DIR%
echo  Port    : %PORT%
echo ==========================================================
echo.

REM ----------------------------------------------------------
REM STEP 0: Port check
REM ----------------------------------------------------------
echo [0/6] Checking port %PORT%...
netstat -ano | findstr ":%PORT%" | findstr "LISTENING" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [WARNING] Port %PORT% is in use. Close other instances first.
) else (
    echo [OK] Port %PORT% is free.
)
echo.

REM ----------------------------------------------------------
REM STEP 1: Python check
REM ----------------------------------------------------------
echo [1/6] Checking Python...
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python not found. Install Python 3.10+ and add it to PATH.
    pause
    exit /b 1
)
for /f "tokens=2" %%V in ('python --version 2^>^&1') do set "PY_VER=%%V"
echo [OK] Python %PY_VER% found.
echo.

REM ----------------------------------------------------------
REM STEP 2: Virtual environment
REM ----------------------------------------------------------
set "VENV_DIR=%BASE_DIR%\.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "VENV_ACTIVATE=%VENV_DIR%\Scripts\activate.bat"

echo [2/6] Checking virtual environment...
if not exist "%VENV_DIR%" (
    echo [INFO] Creating virtual environment...
    python -m venv "%VENV_DIR%"
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.
) else (
    echo [OK] Virtual environment already exists.
)
echo.

REM ----------------------------------------------------------
REM STEP 3: Activate virtual environment
REM ----------------------------------------------------------
echo [3/6] Activating virtual environment...
if not exist "%VENV_ACTIVATE%" (
    echo [WARNING] Activate script missing - recreating venv...
    rmdir /s /q "%VENV_DIR%" >nul 2>&1
    python -m venv "%VENV_DIR%"
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Failed to recreate virtual environment.
        pause
        exit /b 1
    )
)
call "%VENV_ACTIVATE%"
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Could not activate virtual environment.
    pause
    exit /b 1
)
echo [OK] Virtual environment active.
echo.

REM ----------------------------------------------------------
REM STEP 4: Upgrade pip
REM ----------------------------------------------------------
echo [4/6] Upgrading pip...
"%VENV_PYTHON%" -m pip install --upgrade pip --quiet
if %ERRORLEVEL% NEQ 0 (
    echo [WARNING] pip upgrade failed - continuing anyway.
) else (
    echo [OK] pip is up to date.
)
echo.

REM ----------------------------------------------------------
REM STEP 5: Install dependencies
REM ----------------------------------------------------------
echo [5/6] Installing dependencies...
echo.

REM --- 5.1: Skip if PyTorch already installed ---
echo [INFO] Checking if PyTorch is already installed...
"%VENV_PYTHON%" -c "import torch" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] PyTorch is already installed - skipping GPU detection.
    goto :install_requirements
)

echo [INFO] PyTorch not found. Detecting hardware...
echo.

REM ----------------------------------------------------------
REM 5.2: Use Python to detect GPU and select the correct
REM      PyTorch wheel index URL.
REM
REM  WHY PYTHON: nvidia-smi output uses ASCII table borders with
REM  pipe characters (|) which completely break batch string
REM  parsing. Python handles this trivially and reliably.
REM
REM  The script below runs nvidia-smi -q (structured key:value
REM  output, no table borders) and maps the CUDA version to the
REM  correct PyTorch wheel URL. It prints exactly one line:
REM    - "CPU"  if no NVIDIA GPU is found
REM    - The full https://download.pytorch.org/whl/cuXXX URL
REM      if a GPU is found.
REM ----------------------------------------------------------
set "DETECT_SCRIPT=%TEMP%\sentinel_detect_%RANDOM%.py"

(
echo import subprocess, sys
echo.
echo def get_torch_url^(^):
echo     # Step 1: Check if nvidia-smi exists at all
echo     try:
echo         out = subprocess.check_output^(
echo             ['nvidia-smi', '-q'],
echo             text=True,
echo             stderr=subprocess.DEVNULL,
echo             timeout=10
echo         ^)
echo     except Exception:
echo         return 'CPU'
echo.
echo     # Step 2: Parse 'CUDA Version : 12.4' from -q output
echo     # nvidia-smi -q gives clean key:value lines, no table borders
echo     cuda_ver = None
echo     for line in out.splitlines^(^):
echo         line = line.strip^(^)
echo         if line.lower^(^).startswith^('cuda version'^):
echo             parts = line.split^(':'^)
echo             if len^(parts^) ^>= 2:
echo                 cuda_ver = parts[-1].strip^(^)
echo                 break
echo.
echo     if not cuda_ver or cuda_ver == 'N/A':
echo         return 'CPU'
echo.
echo     # Step 3: Map CUDA version to PyTorch wheel
echo     try:
echo         major, minor = int^(cuda_ver.split^('.'^)[0]^), int^(cuda_ver.split^('.'^)[1]^)
echo     except Exception:
echo         return 'https://download.pytorch.org/whl/cu121'
echo.
echo     if major == 11:
echo         return 'https://download.pytorch.org/whl/cu118'
echo     elif major == 12 and minor ^>= 4:
echo         return 'https://download.pytorch.org/whl/cu124'
echo     elif major == 12:
echo         return 'https://download.pytorch.org/whl/cu121'
echo     else:
echo         return 'https://download.pytorch.org/whl/cu121'
echo.
echo print^(get_torch_url^(^)^)
) > "%DETECT_SCRIPT%"

REM Run the detection script and capture the single-line output
set "TORCH_URL="
for /f "delims=" %%R in ('"%VENV_PYTHON%" "%DETECT_SCRIPT%"') do set "TORCH_URL=%%R"
del "%DETECT_SCRIPT%" >nul 2>&1

REM Check if detection produced any output at all
if "!TORCH_URL!"=="" (
    echo [WARNING] GPU detection script produced no output. Defaulting to CPU install.
    set "TORCH_URL=CPU"
)

echo [INFO] Detection result: !TORCH_URL!
echo.

REM ----------------------------------------------------------
REM 5.3: Install PyTorch based on detection result
REM ----------------------------------------------------------
if "!TORCH_URL!"=="CPU" (
    echo [INFO] No NVIDIA GPU detected. Installing CPU-only PyTorch...
    echo [INFO] This may take a few minutes.
    echo.
    "%VENV_PYTHON%" -m pip install torch torchvision torchaudio
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] PyTorch CPU install failed. Check your internet connection.
        pause
        exit /b 1
    )
    echo [OK] CPU PyTorch installed.
) else (
    echo [INFO] NVIDIA GPU detected. Installing GPU PyTorch...
    echo [INFO] Index URL : !TORCH_URL!
    echo [INFO] This is a large download ^(~2-3 GB^). Please be patient.
    echo.
    "%VENV_PYTHON%" -m pip install torch torchvision torchaudio --index-url "!TORCH_URL!"
    if !ERRORLEVEL! NEQ 0 (
        echo.
        echo [WARNING] GPU PyTorch install failed. Falling back to CPU-only build...
        echo.
        "%VENV_PYTHON%" -m pip install torch torchvision torchaudio
        if !ERRORLEVEL! NEQ 0 (
            echo [ERROR] CPU fallback also failed. Check your internet connection.
            pause
            exit /b 1
        )
        echo [OK] CPU fallback PyTorch installed.
    ) else (
        echo [OK] GPU PyTorch installed successfully.
    )
)
echo.

REM ----------------------------------------------------------
REM 5.4: Verify PyTorch actually works
REM ----------------------------------------------------------
echo [INFO] Verifying PyTorch...
"%VENV_PYTHON%" -c "import torch; print('[OK] PyTorch', torch.__version__, '| CUDA:', torch.cuda.is_available())"
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] PyTorch import failed. Delete .venv and re-run this script.
    pause
    exit /b 1
)
echo.

:install_requirements
REM ----------------------------------------------------------
REM 5.5: Install remaining project dependencies
REM ----------------------------------------------------------
echo [INFO] Checking core project dependencies...
"%VENV_PYTHON%" -c "import lancedb; import langgraph; from fpdf import FPDF" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] All dependencies already installed.
    goto :deps_done
)

echo [INFO] Installing from requirements.txt...
"%VENV_PYTHON%" -m pip install -r "%BASE_DIR%\requirements.txt"
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] requirements.txt install failed. Check the output above.
    pause
    exit /b 1
)
echo [OK] All dependencies installed.

:deps_done
echo.

REM ----------------------------------------------------------
REM STEP 6: Create data directories
REM ----------------------------------------------------------
echo [6/6] Verifying data directories...
if not exist "%BASE_DIR%\data"             mkdir "%BASE_DIR%\data"
if not exist "%BASE_DIR%\data\sentinel_db" mkdir "%BASE_DIR%\data\sentinel_db"
if not exist "%BASE_DIR%\Credentials"      mkdir "%BASE_DIR%\Credentials"
echo [OK] Directories ready.
echo.

REM ----------------------------------------------------------
REM Launch
REM ----------------------------------------------------------
echo ==========================================================
echo  Launching SentinelRAG
echo ==========================================================
echo  URL    : http://127.0.0.1:%PORT%
echo  Status : Starting (first load takes 30-60 seconds)
echo ==========================================================
echo.

"%VENV_PYTHON%" -m uvicorn src.api.main:app %RELOAD_FLAG% --host 127.0.0.1 --port %PORT%

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [FATAL] SentinelRAG crashed (Exit code: %ERRORLEVEL%^)
    echo.
    echo  Common causes:
    echo   1. Ollama not running        ^>  run: ollama serve
    echo   2. Port already in use       ^>  run: netstat -ano ^| findstr :%PORT%
    echo   3. Corrupt environment       ^>  delete .venv and re-run this script
    echo.
    pause
    exit /b %ERRORLEVEL%
)

endlocal
