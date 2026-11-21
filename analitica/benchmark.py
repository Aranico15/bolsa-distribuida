"""Benchmark del módulo paralelo: speedup y eficiencia del núcleo de decisión de inversión.

  python -m analitica.benchmark                         # 1, 2, 4 y N procesos; 5.000, 20.000 y 40.000 agentes
  python -m analitica.benchmark --agentes 20000 --repeticiones 5 --modos procesos hilos
  python -m analitica.benchmark --rapido                # prueba corta (menos de un minuto)

Métricas (escalamiento fuerte, tamaño del problema fijo):
  speedup      S(p) = T(1) / T(p)
  eficiencia   E(p) = S(p) / p
  fracción serial experimental (Karp-Flatt)  e(p) = (1/S(p) - 1/p) / (1 - 1/p)
  ley de Amdahl ajustada  S(p) = 1 / (f + (1 - f) / p)

T(1) es la versión secuencial (mismo código, sin pool, en el proceso principal). Cada medición se
repite y se reporta la mediana (y la desviación estándar). Antes de medir se verifica que la salida con
p trabajadores sea idéntica bit a bit a la secuencial, así que el paralelismo no cambia el resultado.

Salida en runs/benchmark/ (o --salida): benchmark.csv, equipo.json y las gráficas speedup.png,
eficiencia.png y tiempos.png.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import time
from pathlib import Path

import numpy as np

from sim.kernel import Paralelo


def datos(n, activos=200, seed=1):
    """Problema sintético reproducible con la forma de los datos de un nodo: n agentes y `activos` acciones."""
    rng = np.random.default_rng(seed)
    pos = np.where(rng.random((n, activos)) < 0.05, rng.integers(1, 1000, (n, activos)), 0).astype(float)
    return (rng.lognormal(17, 1, n), rng.lognormal(0.2, 0.45, n), pos, rng.lognormal(6, 1, activos),
            rng.normal(0, 0.001, activos), rng.uniform(0.01, 0.04, activos))


def lista_procesos(nucleos: int, pedido: list[int] | None) -> list[int]:
    if pedido:
        return sorted(set(pedido))
    base = {1, 2, 4, nucleos}
    p = 8
    while p < nucleos:
        base.add(p)
        p *= 2
    return sorted(x for x in base if x <= nucleos)


def ajustar_amdahl(ps, speedups) -> float:
    """Fracción serial f que mejor ajusta S(p) = 1 / (f + (1-f)/p) por mínimos cuadrados (búsqueda en malla)."""
    ps, s = np.array(ps, float), np.array(speedups, float)
    malla = np.linspace(0, 1, 2001)
    err = [((1 / (f + (1 - f) / ps) - s) ** 2).sum() for f in malla]
    return float(malla[int(np.argmin(err))])


def medir(par, args, repeticiones):
    tiempos = []
    for r in range(repeticiones):
        t0 = time.perf_counter()
        par.decidir(*args, semilla=100 + r)
        tiempos.append(time.perf_counter() - t0)
    return statistics.median(tiempos), (statistics.stdev(tiempos) if len(tiempos) > 1 else 0.0)


def equipo(nucleos):
    info = {"sistema": platform.platform(), "python": platform.python_version(), "numpy": np.__version__,
            "procesador": platform.processor() or "", "nucleos_logicos": nucleos}
    try:  # nombre del procesador en Linux
        for linea in Path("/proc/cpuinfo").read_text().splitlines():
            if linea.startswith("model name"):
                info["procesador"] = linea.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    return info


def graficar(filas, salida: Path, modos, tamanos):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib no está instalado: se omiten las gráficas")
        return
    estilos = {"procesos": "-", "hilos": ":"}
    ps_todos = sorted({f["procesos"] for f in filas})
    for metrica, etiqueta, ideal in (("speedup", "Speedup S(p)", lambda p: p),
                                     ("eficiencia", "Eficiencia E(p)", lambda p: 1.0),
                                     ("segundos", "Tiempo (s)", None)):
        fig, ax = plt.subplots(figsize=(6.4, 4.0))
        for modo in modos:
            for i, n in enumerate(tamanos):
                fs = [f for f in filas if f["modo"] == modo and f["agentes"] == n]
                if not fs:
                    continue
                ax.plot([f["procesos"] for f in fs], [f[metrica] for f in fs], estilos.get(modo, "-"),
                        marker="o", color=f"C{i}", label=f"{modo} ({n:,} agentes)".replace(",", "."))
        if ideal:
            ax.plot(ps_todos, [ideal(p) for p in ps_todos], "k--", alpha=0.45, label="ideal")
        ax.set_xlabel("procesos / hilos (p)")
        ax.set_ylabel(etiqueta)
        ax.set_xticks(ps_todos)
        if metrica == "segundos":
            ax.set_yscale("log")
        if metrica == "eficiencia":
            ax.set_ylim(0, 1.1)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(salida / f"{'tiempos' if metrica == 'segundos' else metrica}.png", dpi=160)
        plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agentes", type=int, nargs="+", default=[5000, 20000, 40000])
    ap.add_argument("--procesos", type=int, nargs="+", help="lista de p (por defecto 1, 2, 4, 8, ... y N)")
    ap.add_argument("--modos", nargs="+", default=["procesos", "hilos"], choices=["procesos", "hilos"])
    ap.add_argument("--repeticiones", type=int, default=3)
    ap.add_argument("--salida", default="runs/benchmark")
    ap.add_argument("--rapido", action="store_true", help="prueba corta: 4.000 agentes, 2 repeticiones")
    a = ap.parse_args()
    if a.rapido:
        a.agentes, a.repeticiones = [4000], 2

    nucleos = os.cpu_count() or 1
    procesos = lista_procesos(nucleos, a.procesos)
    salida = Path(a.salida)
    salida.mkdir(parents=True, exist_ok=True)
    info = equipo(nucleos)
    print(f"Equipo: {info['procesador']} | {nucleos} núcleos lógicos | Python {info['python']}")
    print(f"p = {procesos} | modos = {a.modos} | repeticiones = {a.repeticiones}\n")

    filas = []
    for n in a.agentes:
        ef, av, pos, pr, mu, sg = datos(n)
        args = (ef, av, pos, pr, mu, sg, 100)
        secuencial = Paralelo(1)
        referencia = secuencial.decidir(*args, semilla=0)
        t1, d1 = medir(secuencial, args, a.repeticiones)
        for modo in a.modos:
            for p in procesos:
                if p == 1:
                    t, d = t1, d1
                else:
                    par = Paralelo(p, modo)
                    salida_p = par.decidir(*args, semilla=0)          # calienta el pool y verifica
                    if not np.array_equal(salida_p, referencia):
                        raise SystemExit(f"ERROR: la salida con {p} {modo} difiere de la secuencial")
                    t, d = medir(par, args, a.repeticiones)
                    par.cerrar()
                s = t1 / t
                kf = (1 / s - 1 / p) / (1 - 1 / p) if p > 1 else float("nan")
                filas.append({"modo": modo, "agentes": n, "procesos": p, "segundos": t, "desv": d,
                              "speedup": s, "eficiencia": s / p, "karp_flatt": kf})
                print(f"{modo:9} agentes={n:>6} p={p:>2}  T={t:8.3f} s (±{d:.3f})  "
                      f"S={s:5.2f}  E={s / p:5.2f}" + (f"  e={kf:5.3f}" if p > 1 else ""))
            fs = [f for f in filas if f["modo"] == modo and f["agentes"] == n]
            f_amdahl = ajustar_amdahl([f["procesos"] for f in fs], [f["speedup"] for f in fs])
            for f in fs:
                f["amdahl_f"] = f_amdahl
            print(f"{'':9} fracción serial ajustada (Amdahl) f = {f_amdahl:.3f}  "
                  f"-> speedup máximo teórico 1/f = {1 / f_amdahl if f_amdahl else float('inf'):.1f}\n")

    cols = ["modo", "agentes", "procesos", "segundos", "desv", "speedup", "eficiencia", "karp_flatt", "amdahl_f"]
    with (salida / "benchmark.csv").open("w", encoding="utf-8") as fh:
        fh.write(",".join(cols) + "\n")
        for f in filas:
            fh.write(",".join(str(round(f[c], 5)) if isinstance(f[c], float) else str(f[c]) for c in cols) + "\n")
    info.update({"procesos": procesos, "modos": a.modos, "agentes": a.agentes, "repeticiones": a.repeticiones,
                 "verificacion": "salida idéntica a la secuencial en todas las configuraciones"})
    (salida / "equipo.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    graficar(filas, salida, a.modos, a.agentes)
    print(f"Resultados en {salida}/ (benchmark.csv, equipo.json, speedup.png, eficiencia.png, tiempos.png)")


if __name__ == "__main__":
    main()
