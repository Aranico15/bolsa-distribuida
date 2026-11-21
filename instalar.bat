@echo off
REM Instala el entorno (una sola vez por PC). Requiere Python 3.10+
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt
echo Listo. Usa demo_local.bat, pc_principal.bat o pc_nodo.bat
