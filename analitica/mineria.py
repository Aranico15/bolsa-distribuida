"""Minería de datos sobre una corrida: agrupa nodos y detecta observaciones atípicas.

Uso: python -m analitica.mineria [runs/<corrida>] [--grupos 3]
Genera mineria.md, nodos_minados.csv y anomalias.csv en la carpeta de la corrida.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
VARIABLES = ["inflacion", "desempleo", "gini", "quiebras_t", "red_ms"]


def leer_csv(carpeta: Path, nombre: str) -> pd.DataFrame:
    ruta = carpeta / f"{nombre}.csv"
    return pd.read_csv(ruta) if ruta.exists() and ruta.stat().st_size else pd.DataFrame()


def caracterizar(nodos: pd.DataFrame) -> pd.DataFrame:
    """Resume cada nodo con indicadores comparables para el agrupamiento."""
    requeridas = {"nodo", "t", "indice", *VARIABLES}
    if nodos.empty or not requeridas.issubset(nodos.columns):
        faltan = sorted(requeridas - set(nodos.columns))
        raise ValueError(f"nodos.csv vacío o sin columnas requeridas: {', '.join(faltan)}")
    df = nodos.sort_values("t").copy()
    df["retorno"] = df.groupby("nodo")["indice"].transform(lambda s: np.log(s.clip(lower=1e-9)).diff())
    resumen = df.groupby("nodo").agg(
        inflacion_media=("inflacion", "mean"),
        desempleo_medio=("desempleo", "mean"),
        desigualdad_gini=("gini", "mean"),
        quiebras_medias_tick=("quiebras_t", "mean"),
        latencia_red_media_ms=("red_ms", "mean"),
        volatilidad_indice=("retorno", "std"),
    ).fillna(0)
    return resumen


def kmeans(X: np.ndarray, k: int, semilla: int = 7, iteraciones: int = 100) -> np.ndarray:
    """K-means pequeño y determinista, sin dependencias externas."""
    n = len(X)
    if not 1 <= k <= n:
        raise ValueError(f"--grupos debe estar entre 1 y el número de nodos ({n})")
    rng = np.random.default_rng(semilla)
    centros = X[rng.choice(n, size=k, replace=False)].copy()
    etiquetas = np.zeros(n, dtype=int)
    for _ in range(iteraciones):
        nuevas = ((X[:, None, :] - centros[None, :, :]) ** 2).sum(axis=2).argmin(axis=1)
        if np.array_equal(nuevas, etiquetas):
            break
        etiquetas = nuevas
        for j in range(k):
            miembros = X[etiquetas == j]
            if len(miembros):
                centros[j] = miembros.mean(axis=0)
            else:
                centros[j] = X[rng.integers(n)]
    # Etiquetas estables por orden lexicográfico del centroide.
    orden = sorted(range(k), key=lambda j: tuple(centros[j]))
    mapa = {anterior: nuevo + 1 for nuevo, anterior in enumerate(orden)}
    return np.array([mapa[x] for x in etiquetas])


def detectar_anomalias(nodos: pd.DataFrame, umbral: float = 3.5) -> pd.DataFrame:
    """Marca valores raros mediante puntuación robusta MAD por variable."""
    columnas = [c for c in VARIABLES if c in nodos.columns]
    filas = []
    for columna in columnas:
        valores = pd.to_numeric(nodos[columna], errors="coerce")
        mediana = valores.median()
        mad = (valores - mediana).abs().median()
        if pd.isna(mad) or mad == 0:
            continue
        puntuacion = 0.6745 * (valores - mediana) / mad
        mascara = puntuacion.abs() >= umbral
        for i in nodos.index[mascara.fillna(False)]:
            r = nodos.loc[i]
            filas.append({"t": r.get("t"), "nodo": r.get("nodo"), "variable": columna,
                          "valor": valores.loc[i], "puntuacion_robusta": puntuacion.loc[i]})
    resultado = pd.DataFrame(filas, columns=["t", "nodo", "variable", "valor", "puntuacion_robusta"])
    return resultado.sort_values("puntuacion_robusta", key=lambda s: s.abs(), ascending=False) if len(resultado) else resultado


def tabla(df: pd.DataFrame, decimales: int = 3) -> str:
    """Renderiza una tabla Markdown sin requerir el paquete opcional tabulate."""
    columnas = [str(c) for c in df.columns]
    lineas = ["| " + " | ".join(columnas) + " |", "| " + " | ".join("---" for _ in columnas) + " |"]
    for _, fila in df.iterrows():
        celdas = [f"{v:.{decimales}f}" if isinstance(v, (float, np.floating)) else str(v) for v in fila]
        lineas.append("| " + " | ".join(celdas) + " |")
    return "\n".join(lineas)


def analizar(carpeta: Path, grupos: int = 3) -> None:
    nodos = leer_csv(carpeta, "nodos")
    resumen = caracterizar(nodos)
    matriz = resumen.to_numpy(dtype=float)
    escala = matriz.std(axis=0)
    escala[escala == 0] = 1
    normalizados = (matriz - matriz.mean(axis=0)) / escala
    resumen.insert(0, "nodo", resumen.index)
    resumen["grupo"] = kmeans(normalizados, grupos)
    anomalias = detectar_anomalias(nodos)
    resumen.to_csv(carpeta / "nodos_minados.csv", index=False)
    anomalias.to_csv(carpeta / "anomalias.csv", index=False)

    md = [f"# Minería de datos: corrida `{carpeta.name}`\n",
          "## Agrupamiento de nodos (K-means)\n",
          f"Se agruparon los nodos en **{grupos} grupos** usando indicadores estandarizados: inflación, desempleo, Gini, quiebras por tick, latencia de red y volatilidad del índice.\n",
          tabla(resumen), "",
          "Los números de grupo identifican perfiles similares dentro de esta corrida; no representan una categoría económica universal.\n",
          "## Valores atípicos (mediana y desviación absoluta mediana)\n",
          f"Se detectaron **{len(anomalias)} observaciones** con puntuación robusta absoluta ≥ 3.5. Revisa el tick y la variable para investigar choques o comportamientos inusuales.\n"]
    if len(anomalias):
        md.append(tabla(anomalias.head(30)))
        if len(anomalias) > 30:
            md.append(f"\nSe muestran las primeras 30; el CSV contiene las {len(anomalias)} observaciones.")
    else:
        md.append("No se encontraron observaciones por encima del umbral.")
    md += ["", "Archivos completos: `nodos_minados.csv` y `anomalias.csv`."]
    (carpeta / "mineria.md").write_text("\n".join(md), encoding="utf-8")
    print(f"Informe de minería: {carpeta / 'mineria.md'}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("corrida", nargs="?", type=Path, help="carpeta runs/<corrida>; por defecto la más reciente")
    ap.add_argument("--grupos", type=int, default=3, help="cantidad de grupos K-means (por defecto: 3)")
    args = ap.parse_args()
    corridas = sorted(c.parent for c in (RAIZ / "runs").glob("*/nodos.csv"))
    if args.corrida is None and not corridas:
        ap.error("no hay corridas en runs/; indica la carpeta de una corrida")
    carpeta = args.corrida or corridas[-1]
    if not carpeta.is_absolute():
        carpeta = RAIZ / carpeta
    analizar(carpeta, args.grupos)


if __name__ == "__main__":
    main()
