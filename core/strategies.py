"""Constructor de estrategias con acciones, opciones y futuros (por posiciones o 'legs').

Valuación de cada leg en un horizonte h:
- Acción: S_h.
- Opción: si vence después de h, se REVALÚA con BSM (tiempo restante T−h); si vence en o antes de h, payoff
  al vencimiento. Nunca se usa el payoff terminal para valorar antes del vencimiento.
- Futuro: precio teórico S_h·e^((r−q)(T−h)) (o S_h al vencimiento). P&L = n·M·(F_h − F_0).
P&L del leg = cantidad·multiplicador·(V_h − V_0), con cantidad > 0 compra y < 0 venta.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd

from .options import bsm
from .futures import precio_teorico, stop_loss_terminal


@dataclass
class Leg:
    instrumento: str          # 'accion' | 'call' | 'put' | 'futuro'
    cantidad: float           # contratos (opción/futuro) o acciones; signo = dirección
    multiplicador: float = 1.0
    strike: float | None = None
    vencimiento_años: float | None = None
    prima: float | None = None          # por unidad de subyacente
    origen_prima: str = "teórica (BSM)"  # 'observada (MexDer)' | 'teórica (BSM)'
    precio_inicial: float | None = None  # acción: S0; futuro: F0
    stop: float | None = None            # sólo futuros, hipotético
    deslizamiento_pct: float = 0.0
    comision: float = 0.0

    def to_dict(self):
        return asdict(self)


def validar_legs(legs: list[Leg], S0: float) -> list[str]:
    avisos = []
    for i, l in enumerate(legs, 1):
        if l.cantidad == 0:
            avisos.append(f"Leg {i}: cantidad cero.")
        if l.instrumento in ("call", "put"):
            if not l.strike or l.strike <= 0:
                avisos.append(f"Leg {i}: strike inválido.")
            if not l.vencimiento_años or l.vencimiento_años <= 0:
                avisos.append(f"Leg {i}: vencimiento inválido.")
            if l.prima is None or l.prima < 0:
                avisos.append(f"Leg {i}: prima inválida.")
            if l.cantidad < 0 and l.instrumento == "call":
                cubierto = sum(x.cantidad * x.multiplicador for x in legs if x.instrumento == "accion")
                vendidas = sum(-x.cantidad * x.multiplicador for x in legs if x.instrumento == "call" and x.cantidad < 0)
                if vendidas > cubierto:
                    avisos.append(f"Leg {i}: call vendida DESCUBIERTA — pérdida potencial ilimitada y requerimiento de garantías.")
            if l.cantidad < 0 and l.instrumento == "put":
                avisos.append(f"Leg {i}: put vendida — obligación de comprar a {l.strike:.2f}; pérdida hasta strike − prima.")
        if l.instrumento == "futuro":
            avisos.append(f"Leg {i}: futuro — requiere garantías (AIM) y ajustes diarios; pérdida potencial "
                          f"{'ilimitada' if l.cantidad < 0 else 'hasta el valor del contrato'}.")
            if l.stop is not None:
                avisos.append(f"Leg {i}: stop-loss HIPOTÉTICO; puede ejecutarse peor por brechas o no ejecutarse.")
    return avisos


def valor_leg(l: Leg, S_h, h, r, q, sigma_h):
    """Valor por unidad del leg en el horizonte h (años)."""
    if l.instrumento == "accion":
        return S_h
    if l.instrumento in ("call", "put"):
        T_rest = max(l.vencimiento_años - h, 0.0)
        if T_rest <= 1e-10:
            return max(S_h - l.strike, 0.0) if l.instrumento == "call" else max(l.strike - S_h, 0.0)
        return bsm(S_h, l.strike, T_rest, r, q, sigma_h, l.instrumento)
    if l.instrumento == "futuro":
        T_rest = max((l.vencimiento_años or h) - h, 0.0)
        return precio_teorico(S_h, r, q, T_rest)
    raise ValueError(l.instrumento)


def valor_inicial(l: Leg, S0):
    if l.instrumento == "accion":
        return l.precio_inicial if l.precio_inicial else S0
    if l.instrumento in ("call", "put"):
        return l.prima
    return l.precio_inicial


def pnl_estrategia(legs: list[Leg], S0, S_h, h, r, q, sigma_h, desglose=False):
    total = 0.0
    partes = []
    for l in legs:
        v0 = valor_inicial(l, S0)
        vh = valor_leg(l, S_h, h, r, q, sigma_h)
        ejecutado = False
        if l.instrumento == "futuro" and l.stop is not None:
            vh, ejecutado = stop_loss_terminal(v0, vh, l.stop, "larga" if l.cantidad > 0 else "corta", l.deslizamiento_pct)
        p = l.cantidad * l.multiplicador * (vh - v0) - abs(l.comision)
        total += p
        partes.append({"instrumento": l.instrumento, "cantidad": l.cantidad, "V0": v0, "Vh": vh, "pnl": p,
                       "stop_ejecutado": ejecutado})
    return (total, partes) if desglose else total


def curva_pnl(legs, S0, rango, h, r, q, sigma_h, puntos=201):
    S = np.linspace(rango[0], rango[1], puntos)
    return pd.DataFrame({"S": S, "pnl": [pnl_estrategia(legs, S0, s, h, r, q, sigma_h) for s in S]})


def costo_inicial(legs: list[Leg]) -> float:
    """Flujo neto inicial de primas (negativo = pago) y comisiones. Excluye la compra de acciones y las
    garantías de futuros (las garantías son depósitos, no costos)."""
    c = 0.0
    for l in legs:
        if l.instrumento in ("call", "put"):
            c -= l.cantidad * l.multiplicador * l.prima
        c -= abs(l.comision)
    return c


def puntos_equilibrio(df_curva: pd.DataFrame) -> list[float]:
    s, p = df_curva["S"].values, df_curva["pnl"].values
    out = []
    for i in range(1, len(p)):
        if p[i - 1] == 0:
            out.append(s[i - 1])
        elif p[i - 1] * p[i] < 0:
            out.append(s[i - 1] - p[i - 1] * (s[i] - s[i - 1]) / (p[i] - p[i - 1]))
    return out


# ------------------------------------------------------------------- plantillas
PLANTILLAS = ["Long Call", "Short Call", "Long Put", "Short Put", "Long Straddle", "Short Straddle",
              "Long Strangle", "Short Strangle", "Long Call Butterfly", "Short Call Butterfly",
              "Long Put Butterfly", "Short Put Butterfly", "Collar accionario", "Protective Put",
              "Covered Call", "Compra de futuros", "Venta de futuros", "Compra de futuros con stop",
              "Venta de futuros con stop"]

FUNCION_ECONOMICA = {
    "Protective Put": "Cobertura directa", "Collar accionario": "Cobertura directa",
    "Venta de futuros": "Cobertura directa", "Covered Call": "Estrategia de ingreso por primas (protección limitada a la prima)",
    "Long Straddle": "Estrategia de volatilidad", "Short Straddle": "Estrategia de volatilidad (riesgo elevado)",
    "Long Strangle": "Estrategia de volatilidad", "Short Strangle": "Estrategia de volatilidad (riesgo elevado)",
    "Long Call Butterfly": "Estrategia de volatilidad", "Short Call Butterfly": "Estrategia de volatilidad",
    "Long Put Butterfly": "Estrategia de volatilidad", "Short Put Butterfly": "Estrategia de volatilidad",
    "Long Call": "Exposición direccional", "Short Call": "Ingreso por primas (riesgo ilimitado si descubierta)",
    "Long Put": "Cobertura directa si existe posición larga; si no, exposición direccional",
    "Short Put": "Ingreso por primas", "Compra de futuros": "Exposición direccional / cobertura de posición corta",
    "Compra de futuros con stop": "Exposición direccional", "Venta de futuros con stop": "Exposición direccional",
    "Sin cobertura": "Exposición original",
}


def construir(nombre, S0, T, r, q, sigma, mult_opc=100, mult_fut=100, contratos=1, acciones=None, params=None) -> list[Leg]:
    """Crea los legs de una plantilla con primas TEÓRICAS (BSM) que el usuario puede sustituir por observadas."""
    p = {"k_put": 0.95, "k_call": 1.05, "ancho": 0.05, "hedge": 1.0, "stop_pct": 0.05}
    p.update(params or {})
    acciones = acciones if acciones is not None else contratos * mult_opc
    prem = lambda K, t: bsm(S0, K, T, r, q, sigma, t)
    op = lambda t, K, c: Leg(t, c, mult_opc, K, T, prem(K, t))
    F0 = precio_teorico(S0, r, q, T)
    acc = Leg("accion", acciones, 1, precio_inicial=S0)
    K_atm = S0
    kp, kc = S0 * p["k_put"], S0 * p["k_call"]
    a = p["ancho"] * S0
    n_cob = contratos
    legs = {
        "Long Call": [op("call", K_atm, n_cob)], "Short Call": [op("call", K_atm, -n_cob)],
        "Long Put": [op("put", K_atm, n_cob)], "Short Put": [op("put", K_atm, -n_cob)],
        "Long Straddle": [op("call", K_atm, n_cob), op("put", K_atm, n_cob)],
        "Short Straddle": [op("call", K_atm, -n_cob), op("put", K_atm, -n_cob)],
        "Long Strangle": [op("call", kc, n_cob), op("put", kp, n_cob)],
        "Short Strangle": [op("call", kc, -n_cob), op("put", kp, -n_cob)],
        "Long Call Butterfly": [op("call", K_atm - a, n_cob), op("call", K_atm, -2 * n_cob), op("call", K_atm + a, n_cob)],
        "Short Call Butterfly": [op("call", K_atm - a, -n_cob), op("call", K_atm, 2 * n_cob), op("call", K_atm + a, -n_cob)],
        "Long Put Butterfly": [op("put", K_atm - a, n_cob), op("put", K_atm, -2 * n_cob), op("put", K_atm + a, n_cob)],
        "Short Put Butterfly": [op("put", K_atm - a, -n_cob), op("put", K_atm, 2 * n_cob), op("put", K_atm + a, -n_cob)],
        "Collar accionario": [acc, op("put", kp, n_cob), op("call", kc, -n_cob)],
        "Protective Put": [acc, op("put", kp, n_cob)],
        "Covered Call": [acc, op("call", kc, -n_cob)],
        "Compra de futuros": [Leg("futuro", n_cob, mult_fut, vencimiento_años=T, precio_inicial=F0)],
        "Venta de futuros": [Leg("futuro", -n_cob, mult_fut, vencimiento_años=T, precio_inicial=F0)],
        "Compra de futuros con stop": [Leg("futuro", n_cob, mult_fut, vencimiento_años=T, precio_inicial=F0,
                                           stop=F0 * (1 - p["stop_pct"]))],
        "Venta de futuros con stop": [Leg("futuro", -n_cob, mult_fut, vencimiento_años=T, precio_inicial=F0,
                                          stop=F0 * (1 + p["stop_pct"]))],
    }
    if nombre not in legs:
        raise ValueError(nombre)
    return legs[nombre]
