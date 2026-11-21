@echo off
REM Reproduce los resultados del avance de principio a fin en Windows (requiere Python 3.10+).
REM   1) entorno  2) datos oficiales (opcional, requiere internet)  3) benchmark paralelo
REM   4) corrida corta de la simulacion distribuida  5) reporte analitico y mineria de datos
if not exist .venv\Scripts\python.exe call instalar.bat
.venv\Scripts\python scripts\descargar_datos.py || echo Sin internet: se usa config\semilla.json incluida en el repositorio.
.venv\Scripts\python -m analitica.benchmark --salida runs\benchmark || exit /b 1
.venv\Scripts\python ejecutar_local.py --ticks 250 --intervalo 0 --sin-dashboard || exit /b 1
.venv\Scripts\python -m analitica.reporte || exit /b 1
.venv\Scripts\python -m analitica.mineria --grupos 3 || exit /b 1
echo Listo. Resultados en runs\
