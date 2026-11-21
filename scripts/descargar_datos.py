"""Descarga datos oficiales públicos y gratuitos a data/raw y regenera config/semilla.json.

  python scripts/descargar_datos.py           # Banco Mundial + TRM
  python scripts/descargar_datos.py --dane    # además intenta leer la proyección municipal/departamental del DANE

Requiere internet. Los datos crudos no se versionan en el repositorio; sí se versiona el resultado ya
procesado (config/semilla.json, descargado el 30-oct-2026), así que la simulación corre aunque no haya
conexión. Volver a descargar actualiza la semilla con los datos oficiales más recientes.
"""
import argparse
import csv
import io
import json
import subprocess
import sys
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
RAW = RAIZ / "data" / "raw"

PAISES = "COL;USA;CHN;BRA;MEX;DEU;JPN;GBR;CHL;PER"
INDICADORES = "FP.CPI.TOTL.ZG;NY.GDP.MKTP.KD.ZG;SL.UEM.TOTL.ZS;FR.INR.LEND;PA.NUS.FCRF;GC.TAX.TOTL.GD.ZS;NY.GDP.PCAP.CD"
URL_WB = f"https://api.worldbank.org/v2/country/{PAISES}/indicator/{INDICADORES}?source=2&format=json&mrv=3&per_page=1000"
URL_TRM = "https://www.datos.gov.co/resource/32sa-8pi3.json?$select=valor,vigenciadesde&$order=vigenciadesde%20DESC&$limit=730"
URL_DANE_MUN = "https://www.dane.gov.co/files/censo2018/proyecciones-de-poblacion/Municipal/PPED-AreaMun-2018-2042_VP.xlsx"
URL_DANE_DEP = "https://www.dane.gov.co/files/censo2018/proyecciones-de-poblacion/Departamental/PPED-AreaDep-2018-2050_VP.xlsx"

# Códigos DIVIPOLA que usa el escenario.
MUNICIPIOS = {"15001": "TUN", "11001": "BOG", "05001": "MED", "76001": "CAL", "08001": "BAQ",
              "68001": "BUC", "13001": "CTG"}
DEPARTAMENTOS = {"15": "BOY", "05": "ANT", "76": "VAL", "25": "CUN", "68": "SAN", "50": "MET",
                 "52": "NAR", "08": "ATL"}


def descargar_wb():
    r = requests.get(URL_WB, timeout=60)
    r.raise_for_status()
    (RAW / "worldbank_indicadores.json").write_text(json.dumps(r.json()[1], ensure_ascii=False), encoding="utf-8")
    print("Banco Mundial: OK")


def descargar_trm():
    r = requests.get(URL_TRM, timeout=60)
    r.raise_for_status()
    filas = sorted((f["vigenciadesde"][:10], float(f["valor"])) for f in r.json())
    with (RAW / "trm_banrep.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["fecha", "trm"])
        w.writerows(filas)
    print(f"TRM: {len(filas)} días, último {filas[-1]}")


def descargar_dane(anio=2025):
    """Lee las hojas de Excel del DANE buscando columnas de código, año y total. Es tolerante a cambios
    de formato, pero si el DANE cambia mucho el archivo, ajusta los nombres de columna aquí."""
    import pandas as pd

    salida = {}
    for url, mapa, ancho in ((URL_DANE_MUN, MUNICIPIOS, 5), (URL_DANE_DEP, DEPARTAMENTOS, 2)):
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        crudo = pd.read_excel(io.BytesIO(r.content), header=None)
        fila_enc = next(i for i in range(30) if crudo.iloc[i].astype(str).str.contains("AÑO|Año|año").any())
        df = pd.read_excel(io.BytesIO(r.content), header=fila_enc)
        cols = {c.lower(): c for c in df.columns.astype(str)}
        col_cod = next(cols[c] for c in cols if c.startswith(("mpio", "dp", "cod")))
        col_anio = next(cols[c] for c in cols if "año" in c or "ano" in c)
        col_area = next((cols[c] for c in cols if "área" in c or "area" in c), None)
        col_total = next(cols[c] for c in cols if "total" in c or "población" in c or "poblacion" in c)
        df = df[df[col_anio] == anio]
        if col_area is not None:
            df = df[df[col_area].astype(str).str.lower().str.contains("total")]
        for _, f in df.iterrows():
            cod = str(f[col_cod]).split(".")[0].zfill(ancho)
            if cod in mapa:
                salida[mapa[cod]] = int(f[col_total])
    with (RAW / "poblacion_dane.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["codigo", "poblacion"])
        w.writerows(sorted(salida.items()))
    print(f"DANE: {len(salida)} territorios")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dane", action="store_true")
    a = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    descargar_wb()
    descargar_trm()
    if a.dane:
        try:
            descargar_dane()
        except Exception as e:  # el formato del Excel del DANE cambia con frecuencia
            print(f"DANE: no se pudo leer ({e}); se usará la población aproximada")
    subprocess.run([sys.executable, str(RAIZ / "scripts" / "preparar_datos.py")], check=True)


if __name__ == "__main__":
    main()
