"""Métricas de riesgo. Son medidas estadísticas históricas, no pronósticos infalibles."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def alinear_rendimientos(p_activo: pd.Series, p_mercado: pd.Series, tipo="log") -> pd.DataFrame:
    """Alinea por fechas comunes (intersección) antes de calcular rendimientos."""
    df = pd.concat([p_activo.rename("a"), p_mercado.rename("m")], axis=1, join="inner").dropna()
    if tipo == "log":
        r = np.log(df / df.shift(1))
    else:
        r = df / df.shift(1) - 1
    return r.dropna()


def beta(p_activo: pd.Series, p_mercado: pd.Series, tipo="simple") -> dict:
    """β = Cov(R_a, R_m) / Var(R_m) (muestral, ddof=1), con R², alfa, error estándar y n."""
    r = alinear_rendimientos(p_activo, p_mercado, tipo)
    n = len(r)
    if n < 10:
        return {"beta": np.nan, "n": n, "nota": "Observaciones insuficientes (<10)"}
    cov = np.cov(r["a"], r["m"], ddof=1)
    b = cov[0, 1] / cov[1, 1]
    reg = stats.linregress(r["m"], r["a"])
    return {"beta": b, "alfa_diaria": reg.intercept, "r2": reg.rvalue ** 2, "error_std": reg.stderr,
            "n": n, "inicio": r.index.min(), "fin": r.index.max(),
            "metodo": f"Rendimientos {tipo} diarios, fechas comunes, covarianza muestral"}


def var_historico(r: pd.Series, nivel=0.95) -> float:
    """VaR histórico = −cuantil_(1−nivel) de los rendimientos (pérdida positiva)."""
    return float(-np.quantile(r.dropna(), 1 - nivel))


def es_historico(r: pd.Series, nivel=0.95) -> float:
    """Expected Shortfall = −promedio de rendimientos ≤ cuantil_(1−nivel)."""
    r = r.dropna()
    q = np.quantile(r, 1 - nivel)
    return float(-r[r <= q].mean())


def var_parametrico(r: pd.Series, nivel=0.95) -> float:
    """VaR normal = −(μ + z_(1−nivel)·σ)."""
    r = r.dropna()
    return float(-(r.mean() + stats.norm.ppf(1 - nivel) * r.std(ddof=1)))


def es_parametrico(r: pd.Series, nivel=0.95) -> float:
    """ES normal = −μ + σ·φ(z)/(1−nivel)."""
    r = r.dropna()
    z = stats.norm.ppf(1 - nivel)
    return float(-r.mean() + r.std(ddof=1) * stats.norm.pdf(z) / (1 - nivel))


def escalar_horizonte(v: float, dias: int) -> float:
    """Regla de la raíz del tiempo (supone rendimientos i.i.d.; aproximación)."""
    return v * np.sqrt(dias)


def max_drawdown(p: pd.Series) -> dict:
    dd = p / p.cummax() - 1
    fondo = dd.idxmin()
    pico = p.loc[:fondo].idxmax()
    return {"max_drawdown": float(dd.min()), "pico": pico, "fondo": fondo}


def liquidez(df: pd.DataFrame) -> dict:
    """Volumen promedio, importe operado promedio, % días sin volumen e iliquidez de Amihud
    (promedio de |R_t| / importe_t, ×10^6)."""
    v = df["Volume"].astype(float)
    importe = v * df["Close"]
    r = df["Close"].pct_change().abs()
    amihud = (r / importe.replace(0, np.nan)).mean() * 1e6
    return {"volumen_promedio": float(v.mean()), "importe_promedio_MXN": float(importe.mean()),
            "dias_sin_volumen_%": float((v == 0).mean() * 100), "amihud_x1e6": float(amihud),
            "volumen_mediano": float(v.median())}


def correlaciones(precios: dict[str, pd.Series]) -> pd.DataFrame:
    df = pd.concat({k: v for k, v in precios.items()}, axis=1, join="inner").dropna()
    return np.log(df / df.shift(1)).dropna().corr()


def sensibilidad_mercado(b: float, choques=(-0.10, -0.05, 0.05, 0.10)) -> pd.DataFrame:
    """Impacto esperado lineal = β × choque de mercado (sin incluir riesgo idiosincrático)."""
    return pd.DataFrame({"choque_mercado_%": [c * 100 for c in choques],
                         "impacto_estimado_%": [b * c * 100 for c in choques]})
