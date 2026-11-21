"""Analítica de una corrida: compara la simulación con los datos oficiales y mide la red.

  python -m analitica.reporte                 # última corrida en runs/
  python -m analitica.reporte runs/20261030-142210

Genera en la carpeta de la corrida: reporte.md y gráficos PNG.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
plt.rcParams.update({"figure.figsize": (9, 4), "axes.grid": True, "grid.alpha": 0.3, "axes.spines.top": False,
                     "axes.spines.right": False})
COLORES = {"tunja": "#f5a524", "capitales": "#3b82f6", "departamentos": "#16c784", "colombia": "#ea3943",
           "internacional": "#8b5cf6"}


def leer(carpeta: Path, nombre):
    f = carpeta / f"{nombre}.csv"
    return pd.read_csv(f) if f.exists() and f.stat().st_size > 0 else pd.DataFrame()


def gini(x):
    x = np.sort(np.clip(np.asarray(x, float), 0, None))
    return float((2 * np.arange(1, len(x) + 1) - len(x) - 1).dot(x) / (len(x) * x.sum())) if x.sum() > 0 else 0.0


def main(carpeta: Path):
    semilla = json.loads((RAIZ / "config" / "semilla.json").read_text(encoding="utf-8"))
    archivo_trm = RAIZ / "data" / "raw" / "trm_banrep.csv"  # se regenera con scripts/descargar_datos.py
    if archivo_trm.exists():
        vol_trm_real = float(np.diff(np.log(pd.read_csv(archivo_trm)["trm"].values)).std())
    else:  # sin datos crudos: usa la volatilidad ya procesada en la semilla
        vol_trm_real = float(semilla["trm"]["vol_diaria"])
    nodos, mundo, politica = leer(carpeta, "nodos"), leer(carpeta, "mundo"), leer(carpeta, "politica")
    precios, eventos, regiones = leer(carpeta, "precios"), leer(carpeta, "eventos"), leer(carpeta, "regiones")
    md = [f"# Reporte de la corrida `{carpeta.name}`\n"]
    T = int(nodos["t"].max()) if len(nodos) else 0
    md.append(f"Ticks simulados: **{T}** (≈ {T / 252:.1f} años hábiles).\n")

    # 1) Validación contra datos oficiales.
    md.append("## 1. Simulación vs. datos oficiales\n")
    filas = []
    if len(mundo):
        r_sim = np.diff(np.log(mundo["trm"].values))
        filas.append(("Volatilidad diaria TRM", f"{vol_trm_real:.3%}", f"{r_sim.std():.3%}",
                      "Banco de la República (datos.gov.co)"))
    col = nodos[nodos["nodo"].isin(["tunja", "capitales", "departamentos", "colombia"])]
    if len(col):
        ult = col[col["t"] > T - 63]
        filas.append(("Inflación Colombia (% anual)", f"{semilla['paises']['COL']['inflacion']:.2f}",
                      f"{np.average(ult['inflacion'], weights=ult['pib']):.2f}", "Banco Mundial FP.CPI.TOTL.ZG"))
        filas.append(("Desempleo Colombia (%)", f"{semilla['paises']['COL']['desempleo']:.2f}",
                      f"{np.average(ult['desempleo'], weights=ult['pib']):.2f}", "Banco Mundial SL.UEM.TOTL.ZS"))
    if len(politica):
        filas.append(("Tasa de política (%)", f"{semilla['paises']['COL']['tasa_politica']:.2f} (Taylor)",
                      f"{politica['tasa'].iloc[-1]:.2f}", "Estimada con regla de Taylor"))
    md.append("| Indicador | Dato real | Simulación | Fuente |\n|---|---|---|---|")
    md += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in filas]
    md.append("")

    # 2) Dinámica de empresas.
    md.append("## 2. Empresas: quiebras y emprendimiento\n")
    if len(eventos):
        conteo = eventos.groupby(["nodo", "tipo"]).size().unstack(fill_value=0)
        md.append("```\n" + conteo.to_string() + "\n```")
        md.append("")

    # 3) Desigualdad y riqueza.
    if len(nodos):
        md.append("## 3. Desigualdad (Gini de riqueza por nodo)\n")
        g = nodos.groupby("nodo").agg(gini_inicial=("gini", "first"), gini_final=("gini", "last"))
        md.append("```\n" + g.round(3).to_string() + "\n```")
        md.append("")

    # 4) Contagio: correlación entre índices de nodos.
    if len(nodos):
        md.append("## 4. Contagio entre mercados (correlación de retornos diarios de los índices)\n")
        piv = nodos.pivot_table(index="t", columns="nodo", values="indice")
        corr = np.log(piv).diff().corr().round(2)
        md.append("```\n" + corr.to_string() + "\n```")
        md.append("")
        fig, ax = plt.subplots()
        for n in piv.columns:
            ax.plot(piv.index, piv[n], label=n, color=COLORES.get(n))
        ax.set_title("Índices bursátiles por nodo (base 1000)")
        ax.legend()
        fig.tight_layout(); fig.savefig(carpeta / "indices.png", dpi=120); plt.close(fig)
        md.append("![Índices](indices.png)\n")

    # 5) Red y cómputo distribuido.
    if len(nodos):
        md.append("## 5. Red y cómputo distribuido\n")
        red = nodos.groupby("nodo").agg(computo_ms=("ms", "mean"), red_ms=("red_ms", "mean"),
                                        red_p95_ms=("red_ms", lambda s: s.quantile(0.95)),
                                        ordenes_remotas_enviadas=("remotas_enviadas", "sum"),
                                        ordenes_remotas_recibidas=("remotas_recibidas", "sum"))
        md.append("```\n" + red.round(2).to_string() + "\n```")
        md.append("")
        md.append("`red_ms` = ida y vuelta del tick menos el tiempo de cómputo del nodo: es el costo de la red.\n")
        fig, ax = plt.subplots()
        for n, d in nodos.groupby("nodo"):
            ax.plot(d["t"], d["red_ms"].rolling(10, min_periods=1).mean(), label=n, color=COLORES.get(n))
        ax.set_title("Latencia de red por nodo (ms, media móvil 10 ticks)")
        ax.legend()
        fig.tight_layout(); fig.savefig(carpeta / "latencia.png", dpi=120); plt.close(fig)
        md.append("![Latencia](latencia.png)\n")

    # 6) Macro.
    if len(mundo) and len(politica):
        fig, ax = plt.subplots(1, 2, figsize=(11, 4))
        ax[0].plot(mundo["t"], mundo["trm"], color="#f5a524"); ax[0].set_title("TRM simulada (COP/USD)")
        ax[1].plot(politica["t"], politica["tasa"], label="Tasa BanRep")
        ax[1].plot(politica["t"], politica["inflacion"], label="Inflación"); ax[1].legend(); ax[1].set_title("Política monetaria")
        fig.tight_layout(); fig.savefig(carpeta / "macro.png", dpi=120); plt.close(fig)
        md.append("## 6. Macroeconomía\n\n![Macro](macro.png)\n")

    if len(precios):
        ult = precios[precios["t"] == precios["t"].max()]
        md.append(f"Activos cotizando al final: **{len(ult)}**; volumen total negociado: "
                  f"**{precios['v'].sum():,.0f}** acciones.\n")

    (carpeta / "reporte.md").write_text("\n".join(md), encoding="utf-8")
    print(f"Reporte: {carpeta / 'reporte.md'}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        destino = Path(sys.argv[1])
    else:
        corridas = sorted(c.parent for c in (RAIZ / "runs").glob("*/nodos.csv"))
        if not corridas:
            sys.exit("No hay corridas en runs/")
        destino = corridas[-1]
    main(destino)
