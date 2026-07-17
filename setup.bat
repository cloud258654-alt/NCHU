@echo off
cd /d "%~dp0"

echo [1/4] Checking Python virtual environment...
if not exist ".venv" (
    echo Creating virtual environment .venv...
    python -m venv .venv
    if errorlevel 1 (
        echo Error: Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo Virtual environment .venv already exists. Skipping creation.
)

echo.
echo [2/4] Activating virtual environment...
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo Error: Failed to activate virtual environment.
    pause
    exit /b 1
)

echo.
echo [3/4] Installing requirements...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo Error: Failed to install requirements.
    pause
    exit /b 1
)

echo.
echo [4/4] Installing Playwright Chromium browser...
python -m playwright install chromium
if errorlevel 1 (
    echo Error: Failed to install Playwright Chromium.
    pause
    exit /b 1
)

echo.
echo Setup completed successfully!
pause
