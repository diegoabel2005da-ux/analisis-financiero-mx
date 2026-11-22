"""Indicadores técnicos, rendimientos y tendencias. Cada función documenta su fórmula."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


# ---------------------------------------------------------------- rendimientos
def rend_simple(p: pd.Series) -> pd.Series:
    """R_t = P_t / P_(t-1) - 1"""
    return p / p.shift(1) - 1


def rend_log(p: pd.Series) -> pd.Series:
    """r_t = ln(P_t / P_(t-1))"""
    return np.log(p / p.shift(1))


def rend_acumulado(p: pd.Series) -> pd.Series:
    """Rendimiento acumulado desde la primera observación: P_t / P_0 - 1"""
    return p / p.iloc[0] - 1


def volatilidad(p: pd.Series, factor_anual: int, ventana: int | None = None) -> pd.Series | float:
    """Desviación estándar muestral (ddof=1) de rendimientos logarítmicos × √(factor_anual).

    factor_anual: 252 diario, 52 semanal, 12 mensual... (convención de días hábiles).
    """
    r = rend_log(p).dropna()
    if ventana:
        return r.rolling(ventana).std(ddof=1) * np.sqrt(factor_anual)
    return float(r.std(ddof=1) * np.sqrt(factor_anual))


def drawdown(p: pd.Series) -> pd.Series:
    """DD_t = P_t / max(P_0..P_t) - 1"""
    return p / p.cummax() - 1


# ---------------------------------------------------------------- osciladores
def roc(p: pd.Series, n: int) -> pd.Series:
    """ROC(n) = [(P_t / P_(t-n)) - 1] × 100"""
    return (p / p.shift(n) - 1) * 100


def cruces_cero(s: pd.Series) -> pd.DataFrame:
    sgn = np.sign(s)
    cambio = (sgn != sgn.shift(1)) & sgn.shift(1).notna() & (sgn != 0) & s.notna()
    out = pd.DataFrame({"valor": s[cambio]})
    out["tipo"] = np.where(out["valor"] > 0, "Cruce al alza", "Cruce a la baja")
    return out


def williams_r(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    """%R = -100 × (Máx_n − Cierre) / (Máx_n − Mín_n). Si Máx_n = Mín_n el valor queda indefinido (NaN)."""
    hh = high.rolling(n).max()
    ll = low.rolling(n).min()
    rango = (hh - ll).replace(0, np.nan)
    return -100 * (hh - close) / rango


def estocastico(high, low, close, n: int = 14, suav_k: int = 3, suav_d: int = 3, modo: str = "lento"):
    """%K rápido = 100 × (C − Mín_n)/(Máx_n − Mín_n); %D rápido = SMA(%K rápido, suav_d).

    Lento: %K lento = SMA(%K rápido, suav_k); %D lento = SMA(%K lento, suav_d).
    Suavizado mediante medias móviles simples. Denominador cero ⇒ NaN.
    """
    hh = high.rolling(n).max()
    ll = low.rolling(n).min()
    k_rap = 100 * (close - ll) / (hh - ll).replace(0, np.nan)
    if modo == "rapido":
        k = k_rap
    else:
        k = k_rap.rolling(suav_k).mean()
    d = k.rolling(suav_d).mean()
    return pd.DataFrame({"%K": k, "%D": d})


def rsi_wilder(p: pd.Series, n: int = 14) -> pd.Series:
    """RSI de Wilder.

    Ganancia/pérdida inicial = promedio simple de las primeras n variaciones;
    después AG_t = (AG_(t-1)·(n−1) + G_t)/n (igual para pérdidas). RSI = 100 − 100/(1+AG/AL).
    """
    delta = p.diff()
    g = delta.clip(lower=0)
    l = (-delta).clip(lower=0)
    ag = pd.Series(np.nan, index=p.index)
    al = pd.Series(np.nan, index=p.index)
    if len(p) <= n:
        return ag
    ag.iloc[n] = g.iloc[1:n + 1].mean()
    al.iloc[n] = l.iloc[1:n + 1].mean()
    gv, lv = g.values, l.values
    agv, alv = ag.values.copy(), al.values.copy()
    for i in range(n + 1, len(p)):
        agv[i] = (agv[i - 1] * (n - 1) + gv[i]) / n
        alv[i] = (alv[i - 1] * (n - 1) + lv[i]) / n
    ag = pd.Series(agv, index=p.index)
    al = pd.Series(alv, index=p.index)
    rs = ag / al
    rsi = 100 - 100 / (1 + rs)
    rsi[(al == 0) & (ag > 0)] = 100.0
    rsi[(al == 0) & (ag == 0)] = 50.0
    return rsi


def sma(p, n):
    return p.rolling(n).mean()


def ema(p, n):
    return p.ewm(span=n, adjust=False).mean()


# ---------------------------------------------------------------- Fibonacci
NIVELES_FIBO = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
EXTENSIONES_FIBO = [1.272, 1.618, 2.0, 2.618]


def fibonacci(alto: float, bajo: float, tendencia: str = "alcista", extensiones: bool = True) -> pd.DataFrame:
    """Retrocesos medidos desde el extremo final del movimiento.

    Alcista (de bajo a alto): nivel = alto − f·(alto − bajo).
    Bajista (de alto a bajo): nivel = bajo + f·(alto − bajo).
    Extensiones (f > 1) proyectan más allá del punto de inicio del retroceso.
    """
    rango = alto - bajo
    niveles = NIVELES_FIBO + (EXTENSIONES_FIBO if extensiones else [])
    filas = []
    for f in niveles:
        precio = alto - f * rango if tendencia == "alcista" else bajo + f * rango
        filas.append({"nivel": f"{f*100:.1f}%", "factor": f, "precio": precio,
                      "tipo": "Extensión" if f > 1 else "Retroceso"})
    return pd.DataFrame(filas)


def pivotes(high: pd.Series, low: pd.Series, ventana: int = 5) -> pd.DataFrame:
    """Pivote alto: máximo estricto de la ventana centrada de 2·ventana+1 barras (igual para bajos).

    Los últimos `ventana` días no pueden confirmarse como pivote (requieren barras posteriores).
    """
    w = 2 * ventana + 1
    hmax = high.rolling(w, center=True).max()
    lmin = low.rolling(w, center=True).min()
    ph = high[(high == hmax)]
    pl = low[(low == lmin)]
    a = pd.DataFrame({"precio": ph, "tipo": "alto"})
    b = pd.DataFrame({"precio": pl, "tipo": "bajo"})
    out = pd.concat([a, b]).sort_index()
    # eliminar pivotes consecutivos del mismo tipo conservando el más extremo
    filas = []
    for fecha, r in out.iterrows():
        if filas and filas[-1]["tipo"] == r["tipo"]:
            prev = filas[-1]
            if (r["tipo"] == "alto" and r["precio"] > prev["precio"]) or (r["tipo"] == "bajo" and r["precio"] < prev["precio"]):
                filas[-1] = {"fecha": fecha, "precio": r["precio"], "tipo": r["tipo"]}
        else:
            filas.append({"fecha": fecha, "precio": r["precio"], "tipo": r["tipo"]})
    return pd.DataFrame(filas, columns=["fecha", "precio", "tipo"])


def fibonacci_auto(df: pd.DataFrame, ventana: int = 5):
    """Ancla automática: último par de pivotes alto/bajo confirmados (algoritmo de pivotes)."""
    pv = pivotes(df["High"], df["Low"], ventana)
    if len(pv) < 2:
        return None
    a, b = pv.iloc[-2], pv.iloc[-1]
    if a["tipo"] == "bajo":
        return {"bajo": a["precio"], "alto": b["precio"], "tendencia": "alcista",
                "desde": a["fecha"], "hasta": b["fecha"]}
    return {"alto": a["precio"], "bajo": b["precio"], "tendencia": "bajista", "desde": a["fecha"], "hasta": b["fecha"]}


# ---------------------------------------------------------------- tendencias
def regresion_tendencia(p: pd.Series) -> dict:
    """Regresión MCO de ln(P) contra el tiempo (en barras). Pendiente anualizada con 252 barras."""
    y = np.log(p.dropna().values)
    x = np.arange(len(y))
    if len(y) < 3:
        return {}
    res = stats.linregress(x, y)
    return {"pendiente_diaria": res.slope, "pendiente_anual_%": (np.exp(res.slope * 252) - 1) * 100,
            "r2": res.rvalue ** 2, "p_valor": res.pvalue, "n": len(y),
            "ajuste": pd.Series(np.exp(res.intercept + res.slope * x), index=p.dropna().index)}


def clasificar_tendencias(close: pd.Series) -> pd.DataFrame:
    """Reglas documentadas:
    - Primaria: signo de la pendiente de la regresión log-lineal de toda la muestra (p<0.05) y posición vs SMA200
      (si hay ≥200 barras; si no, SMA100).
    - Secundaria: pendiente de SMA50 en las últimas 20 barras.
    - Corto plazo: precio vs SMA20 y pendiente de SMA20 en las últimas 5 barras.
    """
    out = []
    reg = regresion_tendencia(close)
    n_larga = 200 if len(close) >= 200 else 100
    sl = sma(close, n_larga)
    if reg:
        dirc = "Alcista" if reg["pendiente_diaria"] > 0 else "Bajista"
        if reg["p_valor"] >= 0.05:
            dirc = "Lateral (pendiente no significativa)"
        pos = "sin datos suficientes"
        if sl.notna().any():
            pos = "por encima" if close.iloc[-1] > sl.iloc[-1] else "por debajo"
        out.append({"horizonte": "Primaria", "dirección": dirc,
                    "evidencia": f"Pendiente anualizada {reg['pendiente_anual_%']:.1f}%, R² {reg['r2']:.2f}; "
                                 f"precio {pos} de SMA{n_larga}"})
    for nombre, n, k in [("Secundaria", 50, 20), ("Corto plazo", 20, 5)]:
        m = sma(close, n)
        if m.notna().sum() > k:
            pend = m.iloc[-1] / m.iloc[-1 - k] - 1
            d = "Alcista" if pend > 0.002 else ("Bajista" if pend < -0.002 else "Lateral")
            out.append({"horizonte": nombre, "dirección": d,
                        "evidencia": f"Cambio de SMA{n} en {k} barras: {pend*100:.2f}%; precio "
                                     f"{'>' if close.iloc[-1] > m.iloc[-1] else '<'} SMA{n}"})
    return pd.DataFrame(out)


def cambio_estructural(p: pd.Series, minimo: int = 20) -> dict | None:
    """Prueba de Chow sobre la tendencia log-lineal buscando el punto de quiebre que minimiza la SCR.

    F = [(SCR_r − (SCR_1+SCR_2))/k] / [(SCR_1+SCR_2)/(n−2k)], k=2. Al buscar el quiebre, el p-valor
    nominal es optimista (sesgo de búsqueda); se reporta como indicativo.
    """
    y = np.log(p.dropna().values)
    n = len(y)
    if n < 2 * minimo + 5:
        return None
    x = np.arange(n)

    def scr(xx, yy):
        b = np.polyfit(xx, yy, 1)
        return float(((yy - np.polyval(b, xx)) ** 2).sum())

    scr_r = scr(x, y)
    mejor = None
    for t in range(minimo, n - minimo):
        s = scr(x[:t], y[:t]) + scr(x[t:], y[t:])
        if mejor is None or s < mejor[1]:
            mejor = (t, s)
    t, s = mejor
    k = 2
    F = ((scr_r - s) / k) / (s / (n - 2 * k))
    pval = 1 - stats.f.cdf(F, k, n - 2 * k)
    return {"fecha_quiebre": p.dropna().index[t], "F": F, "p_valor_nominal": pval, "n": n}
