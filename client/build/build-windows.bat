@echo off
REM Build the Windows ClueZero agent.exe. Run this on a Windows 10/11 machine.
REM Output lands in backend\static\agent.exe so /binary/windows can serve it.
setlocal

set HERE=%~dp0
set CLIENT_DIR=%HERE%..
set STATIC_DIR=%CLIENT_DIR%\..\backend\static

echo [build-windows] Setting up a fresh venv...
pushd "%CLIENT_DIR%"
python -m venv .build-venv
call .build-venv\Scripts\activate.bat

echo [build-windows] Installing deps + PyInstaller...
pip install --upgrade pip
pip install -r requirements.txt pyinstaller

echo [build-windows] Running PyInstaller...
pyinstaller ^
  --onefile ^
  --noconsole ^
  --name agent ^
  --hidden-import=pynput.keyboard._win32 ^
  --hidden-import=pynput.mouse._win32 ^
  agent.py

if not exist "%STATIC_DIR%" mkdir "%STATIC_DIR%"
copy /Y dist\agent.exe "%STATIC_DIR%\agent.exe"

call .build-venv\Scripts\deactivate.bat
popd

echo [build-windows] Done. Built: %STATIC_DIR%\agent.exe
