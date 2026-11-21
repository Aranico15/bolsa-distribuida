"""Núcleo paralelo de decisión de inversión.

Cada agente inversionista mira unos pocos activos (atención limitada), simula escenarios de precio
por Monte Carlo y elige comprar el de mejor utilidad ajustada por riesgo o vender el peor de los que
tiene. La función `decidir` es pura (solo arreglos NumPy), así que los agentes se reparten en
bloques entre procesos: esa es la parte de computación paralela dentro de cada nodo.

Descomposición de dominio: los agentes se dividen en sub-bloques de SUBBLOQUE agentes y cada
sub-bloque tiene su propio generador aleatorio, derivado de (semilla, número de sub-bloque). Por eso
el resultado es idéntico con 1, 2, 4 o N trabajadores: el paralelismo cambia el tiempo, no la respuesta.

Dos modos:
  - "procesos" (multiprocessing, ProcessPoolExecutor): cada proceso tiene su propio intérprete y GIL.
  - "hilos" (threading, ThreadPoolExecutor): comparten memoria; escalan solo en la parte de NumPy que
    libera el GIL. Se incluye para comparar ambos modelos en el benchmark.
"""
from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

import numpy as np

SUBBLOQUE = 64  # agentes por sub-bloque: pequeño para que los arreglos de trabajo quepan en caché


def decidir(args):
    (efectivo, aversion, posiciones, precios, mu, sigma, n_local, sesgo_local,
     k, escenarios, horizonte, semilla, *resto) = args
    desplazamiento = resto[0] if resto else 0  # índice global del primer agente de este bloque
    n, A = posiciones.shape
    salida = []
    if n == 0 or A == 0:
        return np.empty((0, 5))
    for ini in range(0, n, SUBBLOQUE):
        fin = min(n, ini + SUBBLOQUE)
        m = fin - ini
        # Generador propio por sub-bloque: resultado independiente del número de trabajadores.
        rng = np.random.default_rng([semilla, (desplazamiento + ini) // SUBBLOQUE])
        pos = posiciones[ini:fin]
        # Atención: k activos por agente, con sesgo hacia el mercado local; el primero es su mayor posición.
        locales = rng.integers(0, max(n_local, 1), size=(m, k))
        remotos = rng.integers(n_local, A, size=(m, k)) if A > n_local else locales
        cand = np.where(rng.random((m, k)) < sesgo_local, locales, remotos)
        mayor = pos.argmax(1)
        tiene = pos[np.arange(m), mayor] > 0
        cand[:, 0] = np.where(tiene, mayor, cand[:, 0])

        s = sigma[cand]
        creencia = mu[cand] + rng.normal(0.0, 0.35, (m, k)) * s  # cada agente tiene su propia opinión
        z = rng.standard_normal((m, k, escenarios, horizonte), dtype=np.float32)
        trayect = np.cumsum(creencia[..., None, None] + s[..., None, None] * z, axis=3)
        final = trayect[..., -1]
        retorno = np.expm1(final).mean(axis=2)
        cola = max(1, int(0.05 * escenarios))
        cvar = -np.sort(final, axis=2)[..., :cola].mean(axis=2)          # pérdida esperada en el 5% peor
        caida = -np.minimum(trayect.min(axis=3), 0).mean(axis=2)          # caída máxima promedio
        util = retorno - aversion[ini:fin, None] * 0.15 * (cvar + 0.5 * caida)

        filas = np.arange(m)
        umbral = 0.004
        # Compra: mejor candidato si la utilidad supera el umbral.
        b = util.argmax(1)
        ub = util[filas, b]
        activo_b = cand[filas, b]
        precio_b = precios[activo_b]
        frac = np.clip(ub * 8.0, 0.0, 0.25) / np.maximum(aversion[ini:fin], 0.5)
        qty_b = np.floor(efectivo[ini:fin] * frac / precio_b)
        compra = (ub > umbral) & (qty_b >= 1)
        lim_b = precio_b * (1.0 + rng.uniform(0.0, 0.025, m))
        # Venta: candidato con posición y utilidad negativa.
        pos_cand = pos[filas[:, None], cand]
        util_v = np.where(pos_cand > 0, util, np.inf)
        w = util_v.argmin(1)
        uw = util_v[filas, w]
        activo_w = cand[filas, w]
        qty_w = np.ceil(pos_cand[filas, w] * np.clip(-uw * 10.0, 0.15, 1.0))
        venta = np.isfinite(uw) & (uw < -umbral) & (qty_w >= 1)
        lim_w = precios[activo_w] * (1.0 - rng.uniform(0.0, 0.025, m))

        idx = np.arange(ini, fin)
        if compra.any():
            salida.append(np.column_stack([idx[compra], activo_b[compra], np.ones(compra.sum()),
                                           qty_b[compra], lim_b[compra]]))
        if venta.any():
            salida.append(np.column_stack([idx[venta], activo_w[venta], -np.ones(venta.sum()),
                                           qty_w[venta], lim_w[venta]]))
    return np.vstack(salida) if salida else np.empty((0, 5))


def repartir(n: int, trabajadores: int) -> list[np.ndarray]:
    """Reparte n agentes en `trabajadores` bloques contiguos alineados a SUBBLOQUE (balance de carga)."""
    bloques = -(-n // SUBBLOQUE)
    grupos = np.array_split(np.arange(bloques), min(trabajadores, bloques))
    return [np.arange(g[0] * SUBBLOQUE, min(n, (g[-1] + 1) * SUBBLOQUE)) for g in grupos if len(g)]


class Paralelo:
    """Reparte `decidir` entre trabajadores. Con trabajadores=1 corre en el mismo proceso (versión secuencial).

    modo="procesos" usa multiprocessing (ProcessPoolExecutor); modo="hilos" usa threading (ThreadPoolExecutor).
    """

    def __init__(self, trabajadores: int = 1, modo: str = "procesos"):
        if trabajadores <= 0:
            trabajadores = os.cpu_count() or 1
        self.trabajadores = trabajadores
        self.modo = modo
        if trabajadores == 1:
            self.pool = None
        elif modo == "hilos":
            self.pool = ThreadPoolExecutor(trabajadores)
        else:
            self.pool = ProcessPoolExecutor(trabajadores)

    def decidir(self, efectivo, aversion, posiciones, precios, mu, sigma, n_local, semilla,
                sesgo_local=0.7, k=8, escenarios=64, horizonte=20):
        n = len(efectivo)
        if self.pool is None or n < 2 * SUBBLOQUE:
            return decidir((efectivo, aversion, posiciones, precios, mu, sigma, n_local, sesgo_local,
                            k, escenarios, horizonte, semilla, 0))
        cortes = repartir(n, self.trabajadores)
        trabajos = [(efectivo[c], aversion[c], posiciones[c], precios, mu, sigma, n_local, sesgo_local,
                     k, escenarios, horizonte, semilla, int(c[0])) for c in cortes]
        resultados = list(self.pool.map(decidir, trabajos))
        for c, r in zip(cortes, resultados):
            if len(r):
                r[:, 0] += c[0]
        resultados = [r for r in resultados if len(r)]
        return np.vstack(resultados) if resultados else np.empty((0, 5))

    def cerrar(self):
        if self.pool:
            self.pool.shutdown(cancel_futures=True)
