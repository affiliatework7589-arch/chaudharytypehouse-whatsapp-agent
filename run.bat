@echo off
REM ===========================================================================
REM  Chaudhary Type House & Property Advisors
REM  ONE-CLICK launcher for Windows - installs everything FREE, then starts.
REM  Zero paid APIs. Zero cost. Docker NOT required.
REM ===========================================================================
setlocal EnableDelayedExpansion
title Chaudhary Type House - FREE Automation System
cd /d "%~dp0"

echo.
echo  ============================================================
echo    CHAUDHARY TYPE HOUSE ^& PROPERTY ADVISORS
echo    Near Baldia Chowk, City Chishtian
echo    Owner: Chaudhary Muhammad Sanaullah - 0308-3027589
echo    FREE Registry Kharcha Calculator: https://chtype.online
echo  ============================================================
echo.

REM ---------- 1. Locate Python ----------
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY (
  echo [X] Python nahi mila.
  echo     Sirf ek baar: https://www.python.org/downloads/  ^(Python 3.10+^)
  echo     Install karne ke baad "Install Now" dabayein, phir ye file dobara chala dein.
  pause
  exit /b 1
)
echo [1/5] Python mil gaya: %PY%

REM ---------- 2. Virtual environment ----------
if not exist ".venv\Scripts\python.exe" (
  echo [2/5] Virtual environment bana rahe hain...
  %PY% -m venv .venv 2>nul || %PY% -m venv .venv
  if not exist ".venv\Scripts\python.exe" (
    echo [X] Virtual environment nahi bani. %PY% -m venv .venv manually chala dein.
    pause
    exit /b 1
  )
)
set "VENV_PY=.venv\Scripts\python.exe"
%VENV_PY% -m pip install --upgrade pip --quiet --disable-pip-version-check
echo [2/5] Virtual environment ready.

REM ---------- 3. Dependencies (all FREE) ----------
echo [3/5] FREE libraries install ho rahi hain (pehli baar 2-4 minute lagenge)...
%VENV_PY% -m pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
  echo [!] Kuch packages install nahi hue. Dobara try kar rahe hain (no --quiet)...
  %VENV_PY% -m pip install -r requirements.txt --disable-pip-version-check
)
%VENV_PY% -c "import fastapi,PIL,uvicorn" >nul 2>nul
if errorlevel 1 (
  echo [!] Core packages (fastapi / pillow / uvicorn) install nahi hue.
  echo     Internet check karein aur run.bat dobara chala dein.
  pause
  exit /b 1
)

REM ---------- 4. Playwright browser (FREE, one time) ----------
echo [4/5] Playwright Chromium install ho raha hai (FREE, ~140MB, ek baar)...
%VENV_PY% -m playwright install chromium
if errorlevel 1 (
  echo [!] Chromium install nahi hua. Website, AI, Leads, Content aur Videos phir bhi
  echo     chalengi. Browser agents ke liye run.bat dobara chala dein.
)

REM ---------- 5. Launch ----------
echo [5/5] System start ho raha hai...
echo.
echo   Website  : http://127.0.0.1:8000/
echo   Dashboard: http://127.0.0.1:8000/dashboard
echo.
echo   Browser khul jayega. Band karne ke liye is window ko Ctrl+C karein.
echo.
%VENV_PY% app.py
if errorlevel 1 (
  echo.
  echo [!] Server ruk gaya. Error message upar dekhein.
  pause
)
endlocal