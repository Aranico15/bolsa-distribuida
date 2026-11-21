"""Roles macro que viven en nodos específicos.

BancoCentral (nodo colombia): junta mensual con regla de Taylor usando la inflación y el desempleo
que reportan los cuatro nodos colombianos por la red.

MercadoMundial (nodo internacional): tasas de cada país, petróleo, demanda externa para Colombia
(con aranceles de cada socio) y la TRM, que reacciona al diferencial de tasas, al petróleo y a los
flujos de capital que cruzan la red entre nodos.
"""
from __future__ import annotations

import math

import numpy as np

DIAS_MES = 21


class BancoCentral:
    def __init__(self, semilla, nodos_colombia, meta=3.0, neutral_real=2.0):
        col = semilla["paises"]["COL"]
        self.tasa = col["tasa_politica"]
        self.meta = meta
        self.neutral = neutral_real
        self.u_natural = col["desempleo"]
        self.nodos = nodos_colombia
        self.reportes: dict[str, dict] = {}
        self.choque_tasa = 0.0

    def recibir(self, estado):
        if estado["nodo"] in self.nodos:
            self.reportes[estado["nodo"]] = estado["ind"]

    def agregados(self):
        if not self.reportes:
            return None, None, 0.0
        pib = sum(r["pib"] for r in self.reportes.values()) or 1.0
        infl = sum(r["inflacion"] * r["pib"] for r in self.reportes.values()) / pib
        des = sum(r["desempleo"] * r["pib"] for r in self.reportes.values()) / pib
        return infl, des, pib

    def paso(self, t, choques):
        for c in choques:
            if c["tipo"] == "subida_tasas":
                self.choque_tasa += float(c.get("magnitud", 1.0))
            elif c["tipo"] == "bajada_tasas":
                self.choque_tasa -= float(c.get("magnitud", 1.0))
        infl, des, pib = self.agregados()
        junta = t % DIAS_MES == 0 and infl is not None
        if junta:
            objetivo = self.neutral + infl + 0.5 * (infl - self.meta) - 0.5 * (des - self.u_natural)
            cambio = float(np.clip(0.3 * (objetivo - self.tasa), -1.0, 1.0))
            self.tasa = max(0.25, round((self.tasa + cambio) * 4) / 4)  # pasos de 25 pb
        if self.choque_tasa:
            self.tasa = max(0.25, self.tasa + self.choque_tasa)
            self.choque_tasa = 0.0
            junta = True
        return {"t": t, "tasa": round(self.tasa, 3), "inflacion": None if infl is None else round(infl, 3),
                "desempleo": None if des is None else round(des, 3), "pib": round(pib, 2), "junta": junta}


class MercadoMundial:
    def __init__(self, escenario, semilla, seed=7):
        self.rng = np.random.default_rng(seed)
        self.paises = {k: dict(v) for k, v in semilla["paises"].items() if k != "COL"}
        self.tasa_col = semilla["paises"]["COL"]["tasa_politica"]
        self.tasas = {k: v["tasa_politica"] for k, v in self.paises.items()}
        self.trm0 = semilla["trm"]["ultimo"]
        self.trm = self.trm0
        self.trm_ancla = semilla["trm"]["promedio_2a"]
        self.vol_trm = semilla["trm"]["vol_diaria"]
        m = escenario["mundo"]
        self.petroleo0 = m["petroleo_inicial"]
        self.petroleo = m["petroleo_inicial"]
        self.ancla_pet = m["petroleo_ancla"]
        self.vol_pet = m["vol_petroleo"]
        self.escala_flujo = m["escala_flujo_usd"]
        self.socios = escenario["socios_comerciales"]
        self.aranceles = {k: escenario["reglas_paises"].get(k, {}).get(
            "arancel_a_colombia", escenario["reglas_base"]["arancel_a_colombia"]) for k in self.socios}
        self.aranceles0 = dict(self.aranceles)
        self.dif0 = self.tasa_col - self.tasas.get("USA", 4.0)
        self.choques = []  # (tipo, magnitud, ticks restantes)

    def paso(self, t, choques_nuevos, flujo_neto_usd, tasa_col=None):
        rng = self.rng
        for c in choques_nuevos:
            m = float(c.get("magnitud", 1.0))
            if c["tipo"] == "guerra_comercial":
                for k in self.aranceles:
                    if k in ("USA", "CHN"):
                        self.aranceles[k] = min(0.6, self.aranceles[k] + 0.15 * m)
            elif c["tipo"] == "fin_guerra_comercial":
                self.aranceles = dict(self.aranceles0)
            else:
                self.choques.append([c["tipo"], m, int(c.get("duracion", 60))])
        vol_mult, pet_drift, demanda_mult = 1.0, 0.0, 1.0
        for ch in self.choques:
            tipo, m, _ = ch
            if tipo == "crisis_internacional":
                vol_mult *= 1 + m; pet_drift -= 0.0015 * m; demanda_mult *= max(0.3, 1 - 0.25 * m)
            elif tipo == "boom_petrolero":
                pet_drift += 0.0015 * m
            elif tipo == "crisis_financiera":
                vol_mult *= 1 + 0.5 * m
            ch[2] -= 1
        self.choques = [c for c in self.choques if c[2] > 0]
        if tasa_col is not None:
            self.tasa_col = tasa_col

        # Tasas de los demás países: reversión lenta a su regla de Taylor con ruido.
        for k, p in self.paises.items():
            objetivo = max(0.25, 2.0 + p["inflacion"] + 0.5 * (p["inflacion"] - 3.0))
            self.tasas[k] += 0.01 * (objetivo - self.tasas[k]) + rng.normal(0, 0.01)

        # Petróleo (USD/barril).
        dln_pet = 0.003 * math.log(self.ancla_pet / self.petroleo) + pet_drift + rng.normal(0, self.vol_pet * vol_mult)
        self.petroleo *= math.exp(dln_pet)

        # TRM (COP por USD): ancla de largo plazo, diferencial de tasas, petróleo, flujos de capital y ruido
        # con la volatilidad diaria observada en la serie oficial.
        dif = self.tasa_col - self.tasas.get("USA", 4.0)
        dln = (0.002 * math.log(self.trm_ancla / self.trm)
               - 0.0004 * (dif - self.dif0)
               - 0.15 * dln_pet
               + 0.001 * flujo_neto_usd / self.escala_flujo
               + rng.normal(0, self.vol_trm * vol_mult))
        self.trm *= math.exp(dln)

        # Demanda externa por productos colombianos: socios ponderados, su crecimiento y aranceles.
        dem = 0.0
        for k, w in self.socios.items():
            crec = self.paises.get(k, {}).get("crecimiento", 2.5)
            arancel = self.aranceles.get(k, 0.05)
            dem += w * (1 + (crec - 2.5) / 100) * (1 - arancel) / (1 - self.aranceles0.get(k, 0.05))
        dem *= demanda_mult
        return {"t": t, "trm": round(self.trm, 2), "petroleo": round(self.petroleo, 3),
                "petroleo_rel": round(self.petroleo / self.petroleo0, 5), "demanda_externa": round(dem, 5),
                "tasas": {k: round(v, 3) for k, v in self.tasas.items()}, "tasa_col": round(self.tasa_col, 3),
                "aranceles": self.aranceles, "vol_mult": vol_mult}
