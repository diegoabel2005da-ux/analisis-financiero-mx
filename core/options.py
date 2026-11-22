"""Opciones sobre acciones: Black-Scholes-Merton, griegas, Cox-Ross-Rubinstein y volatilidad implícita.

Todas las primas calculadas aquí son TEÓRICAS. La volatilidad implícita sólo se calcula a partir
de una prima OBSERVADA que el usuario introduce (p. ej., boletín de MexDer); nunca a partir de
una prima producida por el propio modelo.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import norm


def _d1d2(S, K, T, r, q, sigma):
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return d1, d1 - sigma * np.sqrt(T)


def bsm(S, K, T, r, q, sigma, tipo="call") -> float:
    """Prima europea BSM con rendimiento por dividendo continuo q.
    Call = S·e^(−qT)·N(d1) − K·e^(−rT)·N(d2); Put = K·e^(−rT)·N(−d2) − S·e^(−qT)·N(−d1)."""
    if T <= 0:
        return max(S - K, 0.0) if tipo == "call" else max(K - S, 0.0)
    if sigma <= 0:
        fwd = S * np.exp((r - q) * T)
        df = np.exp(-r * T)
        return df * (max(fwd - K, 0) if tipo == "call" else max(K - fwd, 0))
    d1, d2 = _d1d2(S, K, T, r, q, sigma)
    if tipo == "call":
        return S * np.exp(-q * T) * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    return K * np.exp(-r * T) * norm.cdf(-d2) - S * np.exp(-q * T) * norm.cdf(-d1)


def griegas(S, K, T, r, q, sigma, tipo="call") -> dict:
    """Delta, Gamma, Vega (por 1 punto de volatilidad = 0.01), Theta (por día calendario, /365) y
    Rho (por 1 punto porcentual = 0.01)."""
    if T <= 0 or sigma <= 0:
        itm = (S > K) if tipo == "call" else (S < K)
        return {"delta": (1.0 if tipo == "call" else -1.0) if itm else 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0, "rho": 0.0}
    d1, d2 = _d1d2(S, K, T, r, q, sigma)
    pdf = norm.pdf(d1)
    gamma = np.exp(-q * T) * pdf / (S * sigma * np.sqrt(T))
    vega = S * np.exp(-q * T) * pdf * np.sqrt(T) / 100
    if tipo == "call":
        delta = np.exp(-q * T) * norm.cdf(d1)
        theta = (-S * np.exp(-q * T) * pdf * sigma / (2 * np.sqrt(T)) - r * K * np.exp(-r * T) * norm.cdf(d2)
                 + q * S * np.exp(-q * T) * norm.cdf(d1))
        rho = K * T * np.exp(-r * T) * norm.cdf(d2) / 100
    else:
        delta = -np.exp(-q * T) * norm.cdf(-d1)
        theta = (-S * np.exp(-q * T) * pdf * sigma / (2 * np.sqrt(T)) + r * K * np.exp(-r * T) * norm.cdf(-d2)
                 - q * S * np.exp(-q * T) * norm.cdf(-d1))
        rho = -K * T * np.exp(-r * T) * norm.cdf(-d2) / 100
    return {"delta": delta, "gamma": gamma, "vega": vega, "theta": theta / 365, "rho": rho}


def crr(S, K, T, r, q, sigma, pasos=200, tipo="call", americana=False, devolver_arbol=False):
    """Árbol binomial Cox-Ross-Rubinstein.

    u = e^(σ√Δt), d = 1/u, p = (e^((r−q)Δt) − d)/(u − d). Ejercicio anticipado si americana.
    Dividendos discretos: no modelados (se usa q continuo); la limitación se informa en la interfaz.
    """
    dt_ = T / pasos
    u = np.exp(sigma * np.sqrt(dt_))
    d = 1 / u
    p = (np.exp((r - q) * dt_) - d) / (u - d)
    if not (0 < p < 1):
        raise ValueError("Probabilidad neutral al riesgo fuera de (0,1): aumente pasos o revise parámetros.")
    disc = np.exp(-r * dt_)
    j = np.arange(pasos + 1)
    ST = S * u ** (pasos - j) * d ** j
    V = np.maximum(ST - K, 0) if tipo == "call" else np.maximum(K - ST, 0)
    arbol_S, arbol_V, ejercicio = [], [], []
    if devolver_arbol:
        arbol_S.append(ST.copy()); arbol_V.append(V.copy()); ejercicio.append(np.zeros_like(V, dtype=bool))
    for i in range(pasos - 1, -1, -1):
        Si = S * u ** (i - np.arange(i + 1)) * d ** np.arange(i + 1)
        cont = disc * (p * V[:-1] + (1 - p) * V[1:])
        if americana:
            intr = np.maximum(Si - K, 0) if tipo == "call" else np.maximum(K - Si, 0)
            ex = intr > cont + 1e-12
            V = np.where(ex, intr, cont)
        else:
            ex = np.zeros(i + 1, dtype=bool)
            V = cont
        if devolver_arbol:
            arbol_S.append(Si); arbol_V.append(V.copy()); ejercicio.append(ex)
    precio = float(V[0])
    if devolver_arbol:
        return precio, {"S": arbol_S[::-1], "V": arbol_V[::-1], "ejercicio": ejercicio[::-1], "u": u, "d": d, "p": p}
    return precio


def convergencia_crr(S, K, T, r, q, sigma, tipo="call", americana=False, pasos=(10, 25, 50, 100, 200, 400, 800)):
    ref = bsm(S, K, T, r, q, sigma, tipo)
    filas = []
    for n in pasos:
        v = crr(S, K, T, r, q, sigma, n, tipo, americana)
        filas.append({"pasos": n, "CRR": v, "BSM_europea": ref, "diferencia": v - ref})
    return pd.DataFrame(filas)


def vol_implicita(prima_observada, S, K, T, r, q, tipo="call", lo=1e-4, hi=5.0) -> float:
    """Resuelve BSM(σ) = prima observada con Brent. Devuelve NaN si la prima viola los límites de no arbitraje."""
    lim_inf = bsm(S, K, T, r, q, 1e-9, tipo)
    lim_sup = S * np.exp(-q * T) if tipo == "call" else K * np.exp(-r * T)
    if not (lim_inf - 1e-10 < prima_observada < lim_sup):
        return np.nan
    f = lambda s: bsm(S, K, T, r, q, s, tipo) - prima_observada
    try:
        return brentq(f, lo, hi, xtol=1e-10, maxiter=200)
    except ValueError:
        return np.nan


def payoff_vencimiento(ST, K, tipo="call"):
    ST = np.asarray(ST, dtype=float)
    return np.maximum(ST - K, 0) if tipo == "call" else np.maximum(K - ST, 0)


def resumen_basica(S, K, T, r, q, sigma, tipo, posicion, prima_usada, multiplicador, contratos):
    """Long/Short Call/Put: prima, punto de equilibrio, pérdida y ganancia máxima por contrato."""
    signo = 1 if posicion == "larga" else -1
    be = K + prima_usada if tipo == "call" else K - prima_usada
    n = multiplicador * contratos
    if tipo == "call":
        maxg = np.inf if signo == 1 else prima_usada * n
        maxp = prima_usada * n if signo == 1 else np.inf
    else:
        maxg = (K - prima_usada) * n if signo == 1 else prima_usada * n
        maxp = prima_usada * n if signo == 1 else (K - prima_usada) * n
    return {"punto_equilibrio": be, "ganancia_maxima": maxg, "perdida_maxima": maxp,
            "flujo_inicial": -signo * prima_usada * n}
