@echo off
REM Mide speedup y eficiencia del modulo paralelo (1, 2, 4, ... y N procesos). Resultados en runs\benchmark\
.venv\Scripts\python -m analitica.benchmark %*
