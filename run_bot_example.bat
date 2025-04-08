@echo off
title Start BotAnya + Ollama

echo Check is ollama running...
tasklist /FI "IMAGENAME eq ollama.exe" | find /I "ollama.exe" >nul
if errorlevel 1 (
    echo Ollama starting...
    start "" "***********************\Ollama\ollama app.exe"
    timeout /t 5 /nobreak >nul
) else (
    echo Ollama running allready.
)

echo BotAnya starting...
python BotAnya.py

echo BotAnya stoped
pause
