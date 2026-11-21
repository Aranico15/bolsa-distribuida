@echo off
REM OTRO PC: un nodo conectado al principal.
REM Uso: pc_nodo.bat NODO IP_PRINCIPAL TOKEN_SECRETO
REM   NODO = tunja ^| capitales ^| departamentos ^| colombia
if "%~3"=="" (echo Uso: pc_nodo.bat NODO IP_PRINCIPAL TOKEN & exit /b 1)
set NATS_TOKEN=%~3
REM Abre la vista propia de este nodo en el navegador.
start "" http://%~2:8000/nodo/%~1
.venv\Scripts\python -m sim.nodo --nodo %~1 --nats nats://%~2:4222 --procesos 0 --reanudar
