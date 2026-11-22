"""Pruebas matemáticas con valores de referencia independientes (literatura y cálculos manuales)."""
import datetime as dt
import math

import numpy as np
import pandas as pd
import pytest

from core import technical as ta, risk, options as op, futures as fu, rates as rt, fundamentals as fd
from core import strategies as stg, scenarios as sc, patterns as pt, data as dat


# ------------------------------------------------------------------ datos
def _serie(n=260, semilla=1):
    rng = np.random.default_rng(semilla)
    idx = pd.bdate_range("2025-11-21", periods=n)
    c = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.015, n)))
    o = c * (1 + rng.normal(0, 0.003, n))
    h = np.maximum(c, o) * (1 + abs(rng.normal(0, 0.005, n)))
    l = np.minimum(c, o) * (1 - abs(rng.normal(0, 0.005, n)))
    v = rng.integers(1e5, 1e6, n)
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Adj Close": c, "Volume": v}, index=idx)


def test_remuestreo_ohlc():
    df = _serie()
    w = dat.remuestrear(df, "W")
    sem = df.loc[(df.index >= w.index[1] - pd.Timedelta(days=6)) & (df.index <= w.index[1])]
    assert w["Open"].iloc[1] == pytest.approx(sem["Open"].iloc[0])
    assert w["High"].iloc[1] == pytest.approx(sem["High"].max())
    assert w["Low"].iloc[1] == pytest.approx(sem["Low"].min())
    assert w["Close"].iloc[1] == pytest.approx(sem["Close"].iloc[-1])
    assert w["Volume"].iloc[1] == sem["Volume"].sum()
    for f in ["M", "2M", "Q", "6M", "A"]:
        r = dat.remuestrear(df, f)
        assert r["Volume"].sum() == df["Volume"].sum()
        assert r["High"].max() == pytest.approx(df["High"].max())


def test_validacion_detecta_errores():
    df = _serie(30)
    df.iloc[5, df.columns.get_loc("High")] = df["Low"].iloc[5] * 0.5
    df.iloc[7, df.columns.get_loc("Close")] = -1
    inc = dat.validar_ohlcv(df)
    assert dat.hay_criticas(inc)
    assert (inc["regla"] == "Máximo < Mínimo").any()


def test_reconciliacion():
    idx = pd.bdate_range("2026-01-01", periods=3)
    a = pd.Series([10.00, 10.50, 11.004], index=idx)
    b = pd.Series([10.00, 10.51, 11.00], index=idx)
    r = dat.reconciliar(a, b)
    assert list(r["estado"]) == ["Coincide", "DISCREPANCIA", "Coincide"]


# ------------------------------------------------------------------ rendimientos y volatilidad
def test_rendimientos():
    p = pd.Series([100, 110, 99])
    assert ta.rend_simple(p).iloc[1] == pytest.approx(0.10)
    assert ta.rend_log(p).iloc[2] == pytest.approx(math.log(99 / 110))
    assert ta.rend_acumulado(p).iloc[-1] == pytest.approx(-0.01)


def test_volatilidad_anualizada():
    p = pd.Series([100, 101, 100, 102, 101])
    r = np.log(p / p.shift(1)).dropna()
    assert ta.volatilidad(p, 252) == pytest.approx(r.std(ddof=1) * math.sqrt(252))


def test_drawdown():
    p = pd.Series([100, 120, 90, 130])
    assert ta.drawdown(p).min() == pytest.approx(90 / 120 - 1)


# ------------------------------------------------------------------ técnicos
def test_roc():
    p = pd.Series([10, 11, 12, 13, 15])
    assert ta.roc(p, 2).iloc[4] == pytest.approx((15 / 12 - 1) * 100)


def test_williams_denominador_cero():
    h = pd.Series([10.0] * 5); l = pd.Series([10.0] * 5); c = pd.Series([10.0] * 5)
    assert ta.williams_r(h, l, c, 3).isna().all()
    h = pd.Series([10, 12, 11.0]); l = pd.Series([8, 9, 9.0]); c = pd.Series([9, 11, 10.0])
    assert ta.williams_r(h, l, c, 3).iloc[2] == pytest.approx(-100 * (12 - 10) / (12 - 8))


def test_estocastico():
    h = pd.Series([10, 12, 11.0]); l = pd.Series([8, 9, 9.0]); c = pd.Series([9, 11, 10.0])
    k = ta.estocastico(h, l, c, n=3, modo="rapido")["%K"]
    assert k.iloc[2] == pytest.approx(100 * (10 - 8) / (12 - 8))


def test_rsi_wilder_referencia():
    # Serie clásica de Wilder / StockCharts (cierres de QQQ); RSI14 de referencia ≈ 70.53 en la observación 15.
    c = pd.Series([44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61,
                   46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64])
    # StockCharts publica 70.53 con cierres de más decimales; con cierres a 2 decimales el valor es ≈70.46.
    r = ta.rsi_wilder(c, 14)
    d = c.diff()
    ag, al = d.clip(lower=0).iloc[1:15].mean(), (-d).clip(lower=0).iloc[1:15].mean()
    assert r.iloc[14] == pytest.approx(100 - 100 / (1 + ag / al))
    assert r.iloc[14] == pytest.approx(70.53, abs=0.1)
    ag2 = (ag * 13 + max(d.iloc[15], 0)) / 14
    al2 = (al * 13 + max(-d.iloc[15], 0)) / 14
    assert r.iloc[15] == pytest.approx(100 - 100 / (1 + ag2 / al2))
    assert r.iloc[15] == pytest.approx(66.32, abs=0.1)
    for n in (9, 25):
        x = ta.rsi_wilder(_serie()["Close"], n).dropna()
        assert ((x >= 0) & (x <= 100)).all()


def test_fibonacci():
    f = ta.fibonacci(200, 100, "alcista", extensiones=False)
    assert f.loc[f["factor"] == 0.618, "precio"].iloc[0] == pytest.approx(200 - 61.8)
    f2 = ta.fibonacci(200, 100, "bajista", extensiones=False)
    assert f2.loc[f2["factor"] == 0.382, "precio"].iloc[0] == pytest.approx(138.2)


def test_patrones_doble_techo_sintetico():
    x = np.concatenate([np.linspace(100, 120, 15), np.linspace(120, 108, 10), np.linspace(108, 120.5, 10),
                        np.linspace(120.5, 100, 15)])
    idx = pd.bdate_range("2026-01-01", periods=len(x))
    df = pd.DataFrame({"Open": x, "High": x * 1.001, "Low": x * 0.999, "Close": x, "Volume": 1}, index=idx)
    d = pt.dobles(df, ventana=3)
    assert any(f["figura"] == "Doble techo" and f["estado"] == "Confirmada" for f in d)


def test_patrones_hch_sintetico():
    tramos = [(100, 110, 8), (110, 103, 6), (103, 118, 8), (118, 103, 8), (103, 110.5, 6), (110.5, 95, 10)]
    x = np.concatenate([np.linspace(a, b, n, endpoint=False) for a, b, n in tramos])
    idx = pd.bdate_range("2026-01-01", periods=len(x))
    df = pd.DataFrame({"Open": x, "High": x * 1.001, "Low": x * 0.999, "Close": x, "Volume": 1}, index=idx)
    h = pt.hch(df, ventana=3)
    assert any(f["figura"] == "Hombro-cabeza-hombro" and f["estado"] == "Confirmada" for f in h)


# ------------------------------------------------------------------ riesgo
def test_beta_exacta():
    idx = pd.bdate_range("2026-01-01", periods=60)
    rng = np.random.default_rng(3)
    rm = rng.normal(0, 0.01, 60)
    pm = pd.Series(100 * np.cumprod(1 + rm), index=idx)
    pa = pd.Series(50 * np.cumprod(1 + 1.5 * rm), index=idx)
    b = risk.beta(pa, pm)
    assert b["beta"] == pytest.approx(1.5, abs=1e-9)
    assert b["r2"] == pytest.approx(1.0)


def test_var_es():
    r = pd.Series(np.arange(-50, 50) / 1000)  # 100 observaciones uniformes
    assert risk.var_historico(r, 0.95) == pytest.approx(-np.quantile(r, 0.05))
    assert risk.es_historico(r, 0.95) >= risk.var_historico(r, 0.95)
    rn = pd.Series(np.random.default_rng(0).normal(0, 0.01, 200000))
    assert risk.var_parametrico(rn, 0.99) == pytest.approx(0.02326, rel=0.01)
    assert risk.es_parametrico(rn, 0.975) == pytest.approx(0.02338, rel=0.01)


# ------------------------------------------------------------------ fundamentales
def test_dcf_manual():
    r = fd.dcf(100, [0.10, 0.10], 0.02, 0.10, deuda_neta=50, acciones=10)
    f1, f2 = 110, 121
    vp = f1 / 1.1 + f2 / 1.21
    vt = f2 * 1.02 / 0.08
    ev = vp + vt / 1.21
    assert r["valor_empresa"] == pytest.approx(ev)
    assert r["valor_por_accion"] == pytest.approx((ev - 50) / 10)
    with pytest.raises(ValueError):
        fd.dcf(100, [0.1], 0.12, 0.10, 0, 1)


def test_wacc_capm():
    ke = fd.capm(0.09, 1.2, 0.06)
    assert ke == pytest.approx(0.162)
    assert fd.wacc(600, 400, ke, 0.10, 0.30) == pytest.approx(0.6 * 0.162 + 0.4 * 0.07)


def test_ratios_con_faltantes():
    inc = pd.DataFrame({"2025-12-31": [1000, 400, 200, 120, 150]},
                       index=["Total Revenue", "Gross Profit", "Operating Income", "Net Income", "EBITDA"])
    bal = pd.DataFrame({"2025-12-31": [2000, 500, 250, 800, 300, 100]},
                       index=["Total Assets", "Current Assets", "Current Liabilities", "Stockholders Equity",
                              "Total Debt", "Cash And Cash Equivalents"])
    df, extra = fd.ratios(inc, bal, None, {"sharesOutstanding": 100}, precio=20)
    get = lambda n: df.loc[df["ratio"] == n, "valor"].iloc[0]
    assert get("ROE") == pytest.approx(120 / 800)
    assert get("Margen bruto") == pytest.approx(0.4)
    assert get("Liquidez corriente") == pytest.approx(2.0)
    assert get("Deuda neta / EBITDA") == pytest.approx(200 / 150)
    assert get("P/E") == pytest.approx(20 / 1.2)
    assert np.isnan(get("Prueba ácida"))  # sin inventarios: no se inventa


# ------------------------------------------------------------------ opciones
def test_bsm_hull():
    # Hull, Options Futures & Other Derivatives, ej. 15.6: S=42,K=40,r=10%,σ=20%,T=0.5 → c=4.76, p=0.81
    assert op.bsm(42, 40, 0.5, 0.10, 0, 0.20, "call") == pytest.approx(4.76, abs=0.005)
    assert op.bsm(42, 40, 0.5, 0.10, 0, 0.20, "put") == pytest.approx(0.81, abs=0.005)


def test_paridad_put_call():
    S, K, T, r, q, s = 100, 95, 0.75, 0.08, 0.03, 0.3
    c, p = op.bsm(S, K, T, r, q, s, "call"), op.bsm(S, K, T, r, q, s, "put")
    assert c - p == pytest.approx(S * math.exp(-q * T) - K * math.exp(-r * T))


def test_griegas_diferencias_finitas():
    S, K, T, r, q, s = 100, 100, 1, 0.05, 0.02, 0.25
    g = op.griegas(S, K, T, r, q, s, "call")
    h = 1e-4
    d_num = (op.bsm(S + h, K, T, r, q, s) - op.bsm(S - h, K, T, r, q, s)) / (2 * h)
    g_num = (op.bsm(S + 0.01, K, T, r, q, s) - 2 * op.bsm(S, K, T, r, q, s) + op.bsm(S - 0.01, K, T, r, q, s)) / 0.0001
    v_num = (op.bsm(S, K, T, r, q, s + h) - op.bsm(S, K, T, r, q, s - h)) / (2 * h) / 100
    assert g["delta"] == pytest.approx(d_num, rel=1e-5)
    assert g["gamma"] == pytest.approx(g_num, rel=1e-3)
    assert g["vega"] == pytest.approx(v_num, rel=1e-5)
    th_num = (op.bsm(S, K, T - 1 / 365, r, q, s) - op.bsm(S, K, T, r, q, s))
    assert g["theta"] == pytest.approx(th_num, rel=2e-2)


def test_crr_converge_y_americana():
    S, K, T, r, q, s = 50, 50, 5 / 12, 0.10, 0, 0.40
    assert op.crr(S, K, T, r, q, s, 1000, "call") == pytest.approx(op.bsm(S, K, T, r, q, s, "call"), abs=0.01)
    # Hull ej. 21.1 (put americana, 5 pasos): 4.49
    assert op.crr(S, K, T, r, q, s, 5, "put", americana=True) == pytest.approx(4.49, abs=0.01)
    assert op.crr(S, K, T, r, q, s, 200, "put", True) >= op.crr(S, K, T, r, q, s, 200, "put", False)


def test_vol_implicita_recupera():
    p = op.bsm(100, 105, 0.5, 0.07, 0.01, 0.33, "put")
    assert op.vol_implicita(p, 100, 105, 0.5, 0.07, 0.01, "put") == pytest.approx(0.33, abs=1e-6)
    assert np.isnan(op.vol_implicita(0.0001, 100, 50, 0.5, 0.07, 0, "call"))  # viola límite inferior


# ------------------------------------------------------------------ futuros
def test_futuros():
    assert fu.pnl(2, 100, 50, 55, "larga") == pytest.approx(1000)
    assert fu.pnl(2, 100, 50, 55, "corta") == pytest.approx(-1000)
    agg = fu.resultado_agregado(200, 50, 45, 2, 100, 50.5, 45.4, "corta")
    assert agg["total"] == pytest.approx(-1000 + 1020)
    m = fu.margen_diario(pd.Series([100, 98, 95, 97.0]), 1, 100, "larga", 500, 0.75)
    assert m["pyg_acumulada"].iloc[-1] == pytest.approx(-300)
    assert m["llamada_margen"].sum() > 0  # la garantía se restituye, no es pérdida


# ------------------------------------------------------------------ tasas
def _curva(t=0.10):
    nod = pd.DataFrame({"dias": [28, 91, 182, 364, 728], "tasa_pct": [t * 100] * 5,
                        "convencion": ["cero continua ACT/365"] * 5})
    return rt.Curva(nod, dt.date(2026, 11, 23))


def test_curva_df_y_forward():
    c = _curva(0.10)
    assert c.df(1.0)[0] == pytest.approx(math.exp(-0.10))
    f = c.forward_simple(0.5, 1.0, 0.5)[0]
    assert f == pytest.approx((math.exp(0.05) - 1) / 0.5)
    nod = pd.DataFrame({"dias": [28], "tasa_pct": [7.0], "convencion": ["simple ACT/360"]})
    c2 = rt.Curva(nod, dt.date(2026, 1, 1))
    assert c2.df(28 / 365)[0] == pytest.approx(1 / (1 + 0.07 * 28 / 360))


def test_fraccion_año():
    assert rt.fraccion_año(dt.date(2026, 1, 1), dt.date(2026, 1, 29), "ACT/360") == pytest.approx(28 / 360)
    assert rt.fraccion_año(dt.date(2026, 1, 31), dt.date(2026, 2, 28), "30/360") == pytest.approx(28 / 360)


def _cap(K, tipo="cap", modelo="Black-76", sigma=0.2, N=1e6, curva=None):
    c = curva or _curva()
    per = rt.calendario(dt.date(2026, 12, 21), dt.date(2028, 11, 20), "28D")
    return rt.valuar_cap_floor(c, dt.date(2026, 11, 23), per, [N] * len(per), K, sigma, modelo, tipo)


def test_paridad_cap_floor():
    for modelo, s in [("Black-76", 0.25), ("Bachelier", 0.012)]:
        cap, flo = _cap(0.10, "cap", modelo, s), _cap(0.10, "floor", modelo, s)
        swap = (cap["nocional"] * cap["alfa"] * cap["DF_pago"] * (cap["forward_%"] / 100 - 0.10)).sum()
        assert cap["valor_presente"].sum() - flo["valor_presente"].sum() == pytest.approx(swap, rel=1e-9, abs=1e-6)


def test_monotonia_strike_y_escala():
    v = [_cap(k)["valor_presente"].sum() for k in (0.08, 0.10, 0.12)]
    assert v[0] >= v[1] >= v[2]
    f = [_cap(k, "floor")["valor_presente"].sum() for k in (0.08, 0.10, 0.12)]
    assert f[0] <= f[1] <= f[2]
    assert _cap(0.10, N=2e6)["valor_presente"].sum() == pytest.approx(2 * _cap(0.10)["valor_presente"].sum())
    assert (_cap(0.10)["valor_presente"] >= 0).all()


def test_black76_bachelier_referencia():
    # Black-76: F=K=5%, σ=20%, T=1 → 0.05·(2N(0.1)−1)
    assert rt.black76(0.05, 0.05, 1, 0.20) == pytest.approx(0.05 * (2 * 0.5398278 - 1), rel=1e-5)
    # Bachelier ATM = σ√T/√(2π)
    assert rt.bachelier(0.05, 0.05, 1, 0.01) == pytest.approx(0.01 / math.sqrt(2 * math.pi))


def test_flujos_cobertura_no_negativos():
    t = _cap(0.10)
    fl = rt.flujos_exposicion(t, 300, 0.01, "pasivo", [{"tipo": "cap", "K": 0.10, "signo": 1}])
    assert (fl["flujo_coberturas"] >= 0).all()
    fl2 = rt.flujos_exposicion(t, -300, 0.01, "activo", [{"tipo": "floor", "K": 0.10, "signo": 1}])
    assert (fl2["flujo_coberturas"] >= 0).all()


def test_sensibilidades_signos():
    c = _curva()
    per = rt.calendario(dt.date(2026, 12, 21), dt.date(2028, 11, 20), "28D")
    s = rt.sensibilidades(c, dt.date(2026, 11, 23), per, [1e6] * len(per), 0.10, 0.2, "Black-76", "cap", "ACT/360", "al inicio")
    assert s["vega_+1pt"] > 0
    assert s["DV01_+1pb"] > 0  # un cap comprado gana valor con alzas de tasas


def test_tiempo_en_atraso():
    assert rt.tiempo_efectivo(1.0, 1.25, "compuesta en atraso") == pytest.approx(1.0 + 0.25 / 3)
    assert rt.tiempo_efectivo(1.0, 1.25, "al inicio") == pytest.approx(1.0)


# ------------------------------------------------------------------ estrategias
def test_payoffs_estrategias():
    S0, T, r, q, s = 100, 0.5, 0.08, 0.0, 0.3
    leg = stg.construir("Long Straddle", S0, T, r, q, s, mult_opc=1, contratos=1)
    prem = sum(l.prima for l in leg)
    assert stg.pnl_estrategia(leg, S0, 100, T, r, q, s) == pytest.approx(-prem)
    assert stg.pnl_estrategia(leg, S0, 130, T, r, q, s) == pytest.approx(30 - prem)
    bf = stg.construir("Long Call Butterfly", S0, T, r, q, s, mult_opc=1, contratos=1, params={"ancho": 0.1})
    assert stg.pnl_estrategia(bf, S0, 150, T, r, q, s) == pytest.approx(stg.costo_inicial(bf))
    pp = stg.construir("Protective Put", S0, T, r, q, s, mult_opc=1, contratos=1, acciones=1, params={"k_put": 0.9})
    peor = min(stg.pnl_estrategia(pp, S0, x, T, r, q, s) for x in np.linspace(10, 100, 50))
    assert peor == pytest.approx(90 - 100 - pp[1].prima)
    col = stg.construir("Collar accionario", S0, T, r, q, s, 1, contratos=1, acciones=1, params={"k_put": .9, "k_call": 1.1})
    assert stg.pnl_estrategia(col, S0, 200, T, r, q, s) == pytest.approx(10 + stg.costo_inicial(col))
    cc = stg.construir("Covered Call", S0, T, r, q, s, 1, contratos=1, acciones=1, params={"k_call": 1.1})
    assert stg.pnl_estrategia(cc, S0, 50, T, r, q, s) == pytest.approx(-50 + cc[1].prima)


def test_revaluacion_antes_vencimiento_no_es_payoff():
    leg = stg.construir("Long Call", 100, 1.0, 0.08, 0, 0.3, mult_opc=1)
    v_h = stg.pnl_estrategia(leg, 100, 100, 0.5, 0.08, 0, 0.3)
    assert v_h > -leg[0].prima  # conserva valor tiempo, no se usa max(S−K,0)


def test_stop_futuros():
    px, ej = fu.stop_loss_terminal(100, 90, 95, "larga", 0.01)
    assert ej and px == pytest.approx(94.05)


# ------------------------------------------------------------------ escenarios
def test_matriz_acciones_cinco_por_combinacion():
    m = sc.matriz_acciones(100, 1000, "larga", 0.25, 0.25, 0.08, 0.0, 0.3)
    cnt = m.groupby(["perfil", "estrategia"]).size()
    assert (cnt >= 5).all()
    assert len(m) == 3 * 6 * 5
    # mismos precios de escenario para todas las estrategias dentro de un perfil
    for (p, e), g in m.groupby(["perfil", "escenario"]):
        assert g["precio_final"].nunique() == 1
    pp = m[(m.perfil == "Conservador") & (m.estrategia == "Protective Put")]
    sin = m[(m.perfil == "Conservador") & (m.estrategia == "Sin cobertura")]
    assert pp["resultado_combinado"].iloc[0] > sin["resultado_combinado"].iloc[0]  # protege en estrés


def test_matriz_tasas_cinco_y_signos():
    c = _curva()
    per = rt.calendario(dt.date(2026, 11, 23), dt.date(2028, 11, 20), "28D")
    m, meta = sc.matriz_tasas(c, dt.date(2026, 11, 23), per, [1e7] * len(per), "pasivo", 0.01, 0.2, "Black-76", "al inicio")
    assert (m.groupby(["perfil", "estrategia"]).size() >= 5).all()
    e1 = m[(m.perfil == "Conservador") & (m.escenario.str.startswith("1"))]
    assert e1["choque_paralelo_bp"].iloc[0] > 0  # alza = adverso para pasivo
    cap = e1[e1.estrategia == "Cap comprado"]["resultado_combinado_VP"].iloc[0]
    sin = e1[e1.estrategia == "Sin cobertura"]["resultado_combinado_VP"].iloc[0]
    assert cap > sin
    ma, _ = sc.matriz_tasas(c, dt.date(2026, 11, 23), per, [1e7] * len(per), "activo", 0.0, 0.2, "Black-76", "al inicio")
    assert ma[ma.escenario.str.startswith("1")]["choque_paralelo_bp"].iloc[0] < 0  # baja = adverso para activo


# ------------------------------------------------------------------ automatización
from core import auto


def test_tercer_viernes_y_vencimientos():
    assert auto.tercer_viernes(2026, 12) == dt.date(2026, 12, 18)
    assert auto.tercer_viernes(2027, 3) == dt.date(2027, 3, 19)
    v = auto.proximos_vencimientos(dt.date(2026, 11, 22), 4)
    assert v == [dt.date(2026, 12, 18), dt.date(2027, 3, 19), dt.date(2027, 6, 18), dt.date(2027, 9, 17)]
    assert auto.proximos_vencimientos(dt.date(2026, 12, 18), 1) == [dt.date(2026, 12, 18)]
    assert auto.ajustar_inhabil(dt.date(2026, 12, 18), {dt.date(2026, 12, 18)}) == dt.date(2026, 12, 17)


def test_conversion_tasa_y_dividendo():
    rc = auto.simple_a_continua(7.0, 28)
    assert math.exp(rc * 28 / 365) == pytest.approx(1 + 0.07 * 28 / 360)
    div = pd.Series([0.5, 0.6, 0.7], index=pd.to_datetime(["2025-06-01", "2026-04-01", "2026-10-01"]).tz_localize("UTC"))
    q, txt = auto.dividendo_continuo(div, 50.0, dt.date(2026, 11, 22))
    assert q == pytest.approx(math.log(1 + 1.3 / 50))
    assert auto.dividendo_continuo(None, 50, dt.date(2026, 11, 22))[0] == 0.0
