"""Libro de órdenes con subasta doble continua (prioridad precio-tiempo).

Cada orden reserva su efectivo o sus acciones al crearse; el libro solo cruza órdenes y acumula
lo ejecutado. La liquidación (devolver reservas, entregar acciones) la hace la economía del nodo
al cerrar el tick, igual para órdenes locales y remotas.
"""
from __future__ import annotations

import heapq
import itertools
import math
from dataclasses import dataclass


@dataclass(slots=True)
class Orden:
    nodo: str          # nodo dueño de la orden
    agente: int        # índice del agente en su nodo
    ticker: str
    lado: int          # +1 compra, -1 venta
    qty: float
    limite: float      # precio límite en la moneda del activo
    ref: str = ""      # identificador global (para órdenes remotas)
    lleno: float = 0.0
    costo: float = 0.0  # suma de qty * precio ejecutado (moneda del activo)
    pais: str = ""     # país del dueño (para reglas de propiedad extranjera)
    reserva: float = 0.0   # efectivo (compra) o acciones (venta) apartadas al crear la orden
    impuesto: float = 0.0  # impuesto a la transacción aplicable al dueño

    @property
    def pendiente(self) -> float:
        return self.qty - self.lleno


class LibroOrdenes:
    _seq = itertools.count()

    def __init__(self, ticker: str, precio: float):
        self.ticker = ticker
        self.ultimo = precio
        self.bids: list = []  # (-precio, seq, orden)
        self.asks: list = []  # (precio, seq, orden)
        self.nuevo_tick()

    def nuevo_tick(self):
        self.bids.clear()
        self.asks.clear()
        self.o = self.h = self.l = None
        self.vol = 0.0
        self.monto = 0.0
        self.operaciones = 0

    def _ejecutar(self, entrante: Orden, reposo: Orden, qty: float, precio: float):
        for o in (entrante, reposo):
            o.lleno += qty
            o.costo += qty * precio
        if self.o is None:
            self.o = self.h = self.l = precio
        self.h = max(self.h, precio)
        self.l = min(self.l, precio)
        self.ultimo = precio
        self.vol += qty
        self.monto += qty * precio
        self.operaciones += 1

    def enviar(self, orden: Orden):
        if orden.qty <= 0 or not math.isfinite(orden.limite) or orden.limite <= 0:
            return
        if orden.lado > 0:
            libro, propio = self.asks, self.bids
            cruza = lambda p: p <= orden.limite
            clave = lambda p: p
        else:
            libro, propio = self.bids, self.asks
            cruza = lambda p: p >= orden.limite
            clave = lambda p: -p
        while orden.pendiente > 1e-9 and libro:
            precio = clave(libro[0][0])
            if not cruza(precio):
                break
            reposo = libro[0][2]
            if reposo.nodo == orden.nodo and reposo.agente == orden.agente:
                heapq.heappop(libro)  # evita autocruce: cancela la orden vieja del mismo agente
                continue
            q = min(orden.pendiente, reposo.pendiente)
            self._ejecutar(orden, reposo, q, precio)
            if reposo.pendiente <= 1e-9:
                heapq.heappop(libro)
        if orden.pendiente > 1e-9:
            p = orden.limite
            heapq.heappush(propio, ((-p if orden.lado > 0 else p), next(self._seq), orden))

    def mejor_bid(self):
        return -self.bids[0][0] if self.bids else None

    def mejor_ask(self):
        return self.asks[0][0] if self.asks else None

    def vela(self):
        c = self.ultimo
        if self.o is None:
            return {"o": c, "h": c, "l": c, "c": c, "v": 0.0, "n": 0}
        return {"o": self.o, "h": self.h, "l": self.l, "c": c, "v": self.vol, "n": self.operaciones}
