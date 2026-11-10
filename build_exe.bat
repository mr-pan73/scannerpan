@echo off
REM ==============================================================================
REM ScannerPan - Script di compilazione Standalone .EXE per Windows 11 / Windows 10
REM ==============================================================================
setlocal EnableDelayedExpansion

echo [1/4] Verifica ambiente Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRORE] Python non trovato nel PATH. Installa Python 3.10 o 3.11 a 64-bit e riprova.
    pause
    exit /b 1
)

echo [2/4] Installazione dipendenze richieste...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

echo [3/4] Pulizia vecchie build...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [4/4] Compilazione con PyInstaller (scannerpan.spec)...
python -m PyInstaller --clean scannerpan.spec

if %errorlevel% equ 0 (
    echo ==============================================================================
    echo [SUCCESSO] ScannerPan.exe generato con successo in: dist\ScannerPan.exe
    echo ==============================================================================
) else (
    echo [ERRORE] Errore durante la compilazione.
)

pause
