"""Capa de red: mensajes JSON sobre NATS (publicar/suscribir), con reconexión automática."""
from __future__ import annotations

import json
import logging

import nats

log = logging.getLogger("bus")


def _serial(o):
    try:
        return float(o)
    except (TypeError, ValueError):
        return str(o)


class Bus:
    def __init__(self, url: str, nombre: str, token: str | None = None):
        self.servidores = [s.strip() for s in url.split(",") if s.strip()]
        self.nombre = nombre
        self.token = token or None
        self.nc = None
        self.bytes_enviados = 0
        self.mensajes_enviados = 0

    async def conectar(self):
        async def desconectado():
            log.warning("[%s] desconectado de NATS, reintentando...", self.nombre)

        async def reconectado():
            log.warning("[%s] reconectado a %s", self.nombre, self.nc.connected_url.netloc)

        async def error(e):
            log.error("[%s] error NATS: %s", self.nombre, e)

        self.nc = await nats.connect(
            servers=self.servidores, name=self.nombre, token=self.token,
            max_reconnect_attempts=-1, reconnect_time_wait=1.0, connect_timeout=5,
            disconnected_cb=desconectado, reconnected_cb=reconectado, error_cb=error,
        )
        log.info("[%s] conectado a %s", self.nombre, self.nc.connected_url.netloc)

    async def pub(self, asunto: str, datos):
        carga = json.dumps(datos, separators=(",", ":"), default=_serial).encode()
        self.bytes_enviados += len(carga)
        self.mensajes_enviados += 1
        await self.nc.publish(asunto, carga)

    async def sub(self, asunto: str, cb):
        async def manejador(msg):
            try:
                await cb(msg.subject, json.loads(msg.data))
            except Exception:  # un mensaje malo no debe tumbar el nodo
                log.exception("[%s] error procesando %s", self.nombre, msg.subject)

        return await self.nc.subscribe(asunto, cb=manejador)

    async def flush(self):
        await self.nc.flush()

    async def cerrar(self):
        if self.nc:
            try:
                await self.nc.drain()
            except Exception:
                await self.nc.close()
