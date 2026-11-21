#!/usr/bin/env bash
# Reproduce los resultados del avance de principio a fin en Linux o macOS (requiere Python 3.10+).
set -e
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { python3 -m venv .venv && .venv/bin/pip install -r requirements.txt; }
.venv/bin/python scripts/descargar_datos.py || echo "Sin internet: se usa config/semilla.json incluida en el repositorio."
.venv/bin/python -m analitica.benchmark --salida runs/benchmark
.venv/bin/python ejecutar_local.py --ticks 250 --intervalo 0 --sin-dashboard
.venv/bin/python -m analitica.reporte
.venv/bin/python -m analitica.mineria --grupos 3
echo "Listo. Resultados en runs/"
