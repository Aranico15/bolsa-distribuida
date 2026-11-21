@echo off
REM PC PRINCIPAL: NATS + reloj global + dashboard + nodo internacional.
REM Uso: pc_principal.bat TOKEN_SECRETO
if "%~1"=="" (echo Uso: pc_principal.bat TOKEN_SECRETO & exit /b 1)
set NATS_TOKEN=%~1
.venv\Scripts\python ejecutar_local.py --solo internacional --procesos 0
