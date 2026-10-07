@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
python atualizar_horarios.py index.html
echo.
pause
