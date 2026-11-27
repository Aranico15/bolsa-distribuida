@echo off
REM OTRO PC: un nodo conectado al principal.
REM Uso: pc_nodo.bat NODO IP_PRINCIPAL TOKEN_SECRETO
REM   NODO = tunja ^| capitales ^| departamentos ^| colombia
if "%~3"=="" (echo Uso: pc_nodo.bat NODO IP_PRINCIPAL TOKEN & exit /b 1)
set NATS_TOKEN=%~3
REM Corre desde la carpeta del proyecto aunque se abra con doble clic o desde otra ruta.
cd /d "%~dp0"
if not exist sim\nodo.py if exist analitica\sim\nodo.py cd /d "%~dp0analitica"
REM Abre la vista propia de este nodo en el navegador.
start "" http://%~2:8000/nodo/%~1
"%~dp0.venv\Scripts\python" -m sim.nodo --nodo %~1 --nats nats://%~2:4222 --procesos 0 --reanudar
