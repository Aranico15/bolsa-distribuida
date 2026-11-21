"""Convierte los datos oficiales descargados (data/raw) en la semilla del simulador (config/semilla.json).

Fuentes:
  - Banco Mundial, API v2 (indicadores macro por país): data/raw/worldbank_indicadores.json
  - Banco de la República vía datos.gov.co, dataset 32sa-8pi3 (TRM diaria): data/raw/trm_banrep.csv
  - DANE, proyecciones de población (opcional): data/raw/poblacion_dane.csv

Uso:  python scripts/preparar_datos.py
"""
import csv
import json
import math
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RAW = RAIZ / "data" / "raw"

INDICADORES = {
    "FP.CPI.TOTL.ZG": "inflacion",        # inflación, precios al consumidor (% anual)
    "NY.GDP.MKTP.KD.ZG": "crecimiento",   # crecimiento del PIB (% anual)
    "SL.UEM.TOTL.ZS": "desempleo",        # desempleo (% de la fuerza laboral)
    "FR.INR.LEND": "tasa_prestamo",       # tasa de interés activa (%)
    "PA.NUS.FCRF": "fx_usd",              # tipo de cambio oficial (moneda local por USD)
    "GC.TAX.TOTL.GD.ZS": "recaudo_pib",   # recaudo tributario (% del PIB)
    "NY.GDP.PCAP.CD": "pib_pc_usd",       # PIB per cápita (USD corrientes)
}

# Población aproximada (proyecciones DANE 2025, redondeada). Si existe data/raw/poblacion_dane.csv
# (columnas: codigo,poblacion), esos valores reemplazan a estos.
POBLACION_APROX = {
    "TUN": 180_000, "BOG": 7_990_000, "MED": 2_650_000, "CAL": 2_290_000, "BAQ": 1_330_000,
    "BUC": 620_000, "CTG": 1_060_000, "BOY": 1_280_000, "ANT": 6_950_000, "VAL": 4_600_000,
    "CUN": 3_550_000, "SAN": 2_350_000, "MET": 1_120_000, "NAR": 1_650_000, "ATL": 2_850_000,
    "COL": 53_100_000,
}

# Tasas nominales de impuesto de renta corporativa de referencia (puedes ajustarlas en escenario.json).
RENTA_EMPRESAS = {"COL": 0.35, "USA": 0.21, "CHN": 0.25, "BRA": 0.34, "MEX": 0.30, "DEU": 0.30,
                  "JPN": 0.30, "GBR": 0.25, "CHL": 0.27, "PER": 0.295}


def ultimo_valor(filas):
    out = {}
    for f in filas:
        if f.get("value") is None:
            continue
        pais = f["countryiso3code"]
        nombre = INDICADORES.get(f["indicator"]["id"])
        if not nombre:
            continue
        previo = out.setdefault(pais, {}).get(nombre)
        if previo is None or f["date"] > previo[0]:
            out[pais][nombre] = (f["date"], float(f["value"]))
    return out


def taylor(inflacion, neutral_real=2.0, meta=3.0):
    return max(0.25, neutral_real + inflacion + 0.5 * (inflacion - meta))


def main():
    wb = json.loads((RAW / "worldbank_indicadores.json").read_text(encoding="utf-8"))
    datos = ultimo_valor(wb)
    paises = {}
    for pais, vals in sorted(datos.items()):
        v = {k: x[1] for k, x in vals.items()}
        anios = {k: x[0] for k, x in vals.items()}
        infl = v.get("inflacion", 3.0)
        paises[pais] = {
            "inflacion": round(infl, 3),
            "crecimiento": round(v.get("crecimiento", 2.0), 3),
            "desempleo": round(v.get("desempleo", 6.0), 3),
            # Tasa de política estimada con regla de Taylor a partir de la inflación observada.
            "tasa_politica": round(taylor(infl), 3),
            "tasa_prestamo": round(v["tasa_prestamo"], 3) if "tasa_prestamo" in v else None,
            "fx_usd": v.get("fx_usd", 1.0),
            "recaudo_pib": round(v.get("recaudo_pib", 15.0), 3),
            "pib_pc_usd": round(v.get("pib_pc_usd", 10_000.0), 1),
            "renta_empresas": RENTA_EMPRESAS.get(pais, 0.28),
            "anio_dato": max(anios.values()),
        }

    filas = list(csv.DictReader((RAW / "trm_banrep.csv").open(encoding="utf-8")))
    valores = [float(f["trm"]) for f in filas]
    rets = [math.log(b / a) for a, b in zip(valores, valores[1:])]
    media = sum(rets) / len(rets)
    vol = math.sqrt(sum((r - media) ** 2 for r in rets) / (len(rets) - 1))
    trm = {
        "ultimo": valores[-1], "fecha": filas[-1]["fecha"],
        "promedio_2a": round(sum(valores) / len(valores), 2),
        "vol_diaria": round(vol, 5), "observaciones": len(valores),
    }

    poblacion = dict(POBLACION_APROX)
    fuente_pob = "aproximada (proyecciones DANE 2025 redondeadas)"
    archivo_pob = RAW / "poblacion_dane.csv"
    if archivo_pob.exists():
        for f in csv.DictReader(archivo_pob.open(encoding="utf-8")):
            poblacion[f["codigo"]] = int(float(f["poblacion"]))
        fuente_pob = "DANE, Censo Nacional de Población 2018 (Marco Geoestadístico Nacional), data/raw/poblacion_dane.csv"

    semilla = {
        "fuentes": {
            "paises": "Banco Mundial API v2 (api.worldbank.org), último año disponible",
            "trm": "Banco de la República, TRM diaria vía datos.gov.co (32sa-8pi3)",
            "poblacion": fuente_pob,
        },
        "paises": paises,
        "trm": trm,
        "poblacion": poblacion,
        "salario_minimo_col": 1_423_500,  # SMMLV 2025 (Decreto 1572 de 2024)
    }
    destino = RAIZ / "config" / "semilla.json"
    destino.write_text(json.dumps(semilla, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Semilla escrita en {destino}: {len(paises)} países, TRM {trm['ultimo']} ({trm['fecha']}), "
          f"vol diaria {trm['vol_diaria']:.4%}")


if __name__ == "__main__":
    main()
