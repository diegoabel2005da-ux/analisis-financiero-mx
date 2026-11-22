"""Estados financieros, ratios y valuación fundamental (DCF/FCFF, WACC, múltiplos).

Los estados financieros provienen del proveedor secundario (Yahoo). Pueden diferir de los
reportes enviados por la emisora a BMV/CNBV; cuando falta un rubro se deja vacío y el
ratio correspondiente se marca como no disponible. No se rellenan cifras.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ALIAS = {
    "ingresos": ["Total Revenue", "Operating Revenue"],
    "costo_ventas": ["Cost Of Revenue"],
    "utilidad_bruta": ["Gross Profit"],
    "ebitda": ["EBITDA", "Normalized EBITDA"],
    "ebit": ["EBIT", "Operating Income"],
    "utilidad_operativa": ["Operating Income"],
    "gasto_intereses": ["Interest Expense", "Interest Expense Non Operating"],
    "utilidad_antes_imp": ["Pretax Income"],
    "impuestos": ["Tax Provision"],
    "utilidad_neta": ["Net Income", "Net Income Common Stockholders"],
    "activo_total": ["Total Assets"],
    "activo_circulante": ["Current Assets"],
    "pasivo_circulante": ["Current Liabilities"],
    "inventarios": ["Inventory"],
    "efectivo": ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"],
    "pasivo_total": ["Total Liabilities Net Minority Interest"],
    "deuda_total": ["Total Debt"],
    "deuda_neta": ["Net Debt"],
    "capital_contable": ["Stockholders Equity", "Common Stock Equity"],
    "flujo_operativo": ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"],
    "flujo_inversion": ["Investing Cash Flow", "Cash Flow From Continuing Investing Activities"],
    "flujo_financiamiento": ["Financing Cash Flow", "Cash Flow From Continuing Financing Activities"],
    "capex": ["Capital Expenditure"],
    "flujo_libre": ["Free Cash Flow"],
    "dividendos_pagados": ["Cash Dividends Paid", "Common Stock Dividend Paid"],
    "acciones": ["Ordinary Shares Number", "Share Issued"],
}


def rubro(df: pd.DataFrame | None, clave: str) -> pd.Series:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return pd.Series(dtype=float)
    for n in ALIAS[clave]:
        if n in df.index:
            return pd.to_numeric(df.loc[n], errors="coerce")
    return pd.Series(np.nan, index=df.columns)


def _div(a, b):
    try:
        if b is None or a is None or pd.isna(a) or pd.isna(b) or b == 0:
            return np.nan
        return a / b
    except Exception:
        return np.nan


def resumen(inc, bal, cash) -> pd.DataFrame:
    claves = ["ingresos", "ebitda", "ebit", "utilidad_neta", "deuda_total", "capital_contable", "flujo_libre"]
    filas = {}
    for c in claves:
        src = inc if c in ("ingresos", "ebitda", "ebit", "utilidad_neta") else (bal if c in ("deuda_total", "capital_contable") else cash)
        filas[c] = rubro(src, c)
    df = pd.DataFrame(filas).T
    if not df.empty:
        df = df.reindex(sorted(df.columns), axis=1)
    return df


def analisis_horizontal(df: pd.DataFrame) -> pd.DataFrame:
    """Variación % de cada rubro respecto del período anterior (columnas ordenadas cronológicamente)."""
    d = df.reindex(sorted(df.columns), axis=1)
    return (d / d.shift(1, axis=1) - 1) * 100


def analisis_vertical(df: pd.DataFrame, base: str) -> pd.DataFrame:
    """Cada rubro como % de la base (ingresos para resultados, activo total para balance)."""
    if base not in df.index:
        return pd.DataFrame()
    return df.div(df.loc[base]) * 100


def ratios(inc, bal, cash, info: dict | None, precio: float | None) -> pd.DataFrame:
    """Ratios del período anual más reciente disponible. Fórmulas en la columna 'fórmula'."""
    info = info or {}
    col = lambda s: s.dropna().sort_index().iloc[-1] if s is not None and s.dropna().size else np.nan
    ing, ub, uo, un = col(rubro(inc, "ingresos")), col(rubro(inc, "utilidad_bruta")), col(rubro(inc, "utilidad_operativa")), col(rubro(inc, "utilidad_neta"))
    ebitda, ebit, gi = col(rubro(inc, "ebitda")), col(rubro(inc, "ebit")), col(rubro(inc, "gasto_intereses"))
    uai, imp = col(rubro(inc, "utilidad_antes_imp")), col(rubro(inc, "impuestos"))
    at, ac, pc, inv = col(rubro(bal, "activo_total")), col(rubro(bal, "activo_circulante")), col(rubro(bal, "pasivo_circulante")), col(rubro(bal, "inventarios"))
    efe, deuda, cap = col(rubro(bal, "efectivo")), col(rubro(bal, "deuda_total")), col(rubro(bal, "capital_contable"))
    acciones = info.get("sharesOutstanding") or col(rubro(bal, "acciones"))
    mcap = (precio * acciones) if (precio and acciones and not pd.isna(acciones)) else info.get("marketCap", np.nan)
    deuda_neta = deuda - efe if not (pd.isna(deuda) or pd.isna(efe)) else np.nan
    ev = mcap + deuda_neta if not (pd.isna(mcap) or pd.isna(deuda_neta)) else np.nan
    tasa = _div(imp, uai)
    tasa = tasa if (not pd.isna(tasa) and 0 <= tasa <= 0.6) else np.nan
    nopat = ebit * (1 - tasa) if not pd.isna(tasa) else np.nan
    capital_invertido = deuda + cap - efe if not any(pd.isna(x) for x in (deuda, cap, efe)) else np.nan
    dps = info.get("dividendRate") or info.get("trailingAnnualDividendRate")
    eps = _div(un, acciones)
    filas = [
        ("Liquidez corriente", _div(ac, pc), "Activo circulante / Pasivo circulante", "veces"),
        ("Prueba ácida", _div(ac - inv if not pd.isna(inv) else np.nan, pc), "(Activo circulante − Inventarios) / Pasivo circulante", "veces"),
        ("ROA", _div(un, at), "Utilidad neta / Activo total", "%"),
        ("ROE", _div(un, cap), "Utilidad neta / Capital contable", "%"),
        ("ROIC", _div(nopat, capital_invertido), "EBIT·(1−t) / (Deuda + Capital − Efectivo)", "%"),
        ("Margen bruto", _div(ub, ing), "Utilidad bruta / Ingresos", "%"),
        ("Margen operativo", _div(uo, ing), "Utilidad operativa / Ingresos", "%"),
        ("Margen neto", _div(un, ing), "Utilidad neta / Ingresos", "%"),
        ("Deuda / Capital", _div(deuda, cap), "Deuda total / Capital contable", "veces"),
        ("Deuda neta / EBITDA", _div(deuda_neta, ebitda), "(Deuda − Efectivo) / EBITDA", "veces"),
        ("Cobertura de intereses", _div(ebit, abs(gi) if not pd.isna(gi) else np.nan), "EBIT / Gasto por intereses", "veces"),
        ("P/E", _div(precio, eps), "Precio / Utilidad por acción", "veces"),
        ("P/B", _div(mcap, cap), "Capitalización / Capital contable", "veces"),
        ("EV/EBITDA", _div(ev, ebitda), "(Capitalización + Deuda neta) / EBITDA", "veces"),
        ("EV/Ventas", _div(ev, ing), "(Capitalización + Deuda neta) / Ingresos", "veces"),
        ("Dividend yield", _div(dps, precio), "Dividendo anual por acción / Precio", "%"),
        ("Payout", _div(dps, eps), "Dividendo por acción / Utilidad por acción", "%"),
    ]
    df = pd.DataFrame(filas, columns=["ratio", "valor", "fórmula", "unidad"])
    df["estado"] = np.where(df["valor"].isna(), "No disponible (falta rubro)", "Calculado")
    extra = {"capitalizacion": mcap, "deuda_neta": deuda_neta, "ev": ev, "tasa_efectiva": tasa,
             "acciones": acciones, "ebitda": ebitda, "ebit": ebit, "deuda_total": deuda, "efectivo": efe,
             "gasto_intereses": gi, "utilidad_neta": un, "ingresos": ing, "capital": cap}
    return df, extra


def fcff_historico(inc, cash) -> pd.Series:
    """FCFF = Flujo operativo + Intereses·(1−t) − CAPEX (CAPEX en Yahoo viene con signo negativo)."""
    fo = rubro(cash, "flujo_operativo")
    capex = rubro(cash, "capex")
    gi = rubro(inc, "gasto_intereses").abs()
    uai, imp = rubro(inc, "utilidad_antes_imp"), rubro(inc, "impuestos")
    t = (imp / uai).clip(0, 0.6)
    fcff = fo + (gi * (1 - t)).reindex(fo.index).fillna(0) + capex.reindex(fo.index)
    return fcff.sort_index()


def capm(rf: float, beta: float, prima_mercado: float, prima_pais: float = 0.0) -> float:
    """Ke = rf + β·(prima de mercado) + prima adicional."""
    return rf + beta * prima_mercado + prima_pais


def wacc(E: float, D: float, ke: float, kd: float, t: float) -> float:
    """WACC = E/(D+E)·Ke + D/(D+E)·Kd·(1−t)"""
    V = E + D
    return E / V * ke + D / V * kd * (1 - t)


def dcf(fcff0: float, crecimientos: list[float], g_terminal: float, wacc_: float,
        deuda_neta: float, acciones: float, ajuste_medio_año: bool = False) -> dict:
    """DCF con FCFF.

    FCFF_t = FCFF_(t−1)·(1+g_t). VP_t = FCFF_t/(1+WACC)^t (t−0.5 con ajuste a mitad de año).
    VT = FCFF_N·(1+g)/(WACC−g), descontado a N. EV = ΣVP + VP(VT). Capital = EV − Deuda neta.
    Valor por acción = Capital / Acciones.
    """
    if wacc_ <= g_terminal:
        raise ValueError("El WACC debe ser mayor que el crecimiento terminal.")
    flujos, vps = [], []
    f = fcff0
    for i, g in enumerate(crecimientos, start=1):
        f = f * (1 + g)
        expo = i - 0.5 if ajuste_medio_año else i
        flujos.append(f)
        vps.append(f / (1 + wacc_) ** expo)
    N = len(crecimientos)
    vt = flujos[-1] * (1 + g_terminal) / (wacc_ - g_terminal)
    vp_vt = vt / (1 + wacc_) ** N
    ev = sum(vps) + vp_vt
    capital = ev - deuda_neta
    tabla = pd.DataFrame({"año": range(1, N + 1), "crecimiento": crecimientos, "FCFF": flujos,
                          "factor_descuento": [1 / (1 + wacc_) ** ((i - 0.5) if ajuste_medio_año else i) for i in range(1, N + 1)],
                          "VP": vps})
    return {"tabla": tabla, "valor_terminal": vt, "vp_valor_terminal": vp_vt, "valor_empresa": ev,
            "valor_capital": capital, "valor_por_accion": capital / acciones if acciones else np.nan,
            "peso_vt_%": vp_vt / ev * 100 if ev else np.nan}


def sensibilidad_dcf(fcff0, crec, deuda_neta, acciones, waccs, gs) -> pd.DataFrame:
    m = pd.DataFrame(index=[f"{w*100:.2f}%" for w in waccs], columns=[f"{g*100:.2f}%" for g in gs], dtype=float)
    for w in waccs:
        for g in gs:
            try:
                m.loc[f"{w*100:.2f}%", f"{g*100:.2f}%"] = dcf(fcff0, crec, g, w, deuda_neta, acciones)["valor_por_accion"]
            except ValueError:
                m.loc[f"{w*100:.2f}%", f"{g*100:.2f}%"] = np.nan
    m.index.name = "WACC \\ g"
    return m


def multiplos_comparables(tabla: pd.DataFrame, metrica_objetivo: dict, acciones: float, deuda_neta: float) -> pd.DataFrame:
    """Valor implícito por acción usando la mediana de múltiplos de pares.

    P/E: mediana·UPA. EV/EBITDA: (mediana·EBITDA − deuda neta)/acciones. P/B: mediana·valor en libros por acción.
    """
    out = []
    if "P/E" in tabla and metrica_objetivo.get("utilidad_neta") and acciones:
        m = tabla["P/E"].median()
        out.append(("P/E", m, m * metrica_objetivo["utilidad_neta"] / acciones))
    if "EV/EBITDA" in tabla and metrica_objetivo.get("ebitda") and acciones:
        m = tabla["EV/EBITDA"].median()
        out.append(("EV/EBITDA", m, (m * metrica_objetivo["ebitda"] - deuda_neta) / acciones))
    if "P/B" in tabla and metrica_objetivo.get("capital") and acciones:
        m = tabla["P/B"].median()
        out.append(("P/B", m, m * metrica_objetivo["capital"] / acciones))
    return pd.DataFrame(out, columns=["múltiplo", "mediana_pares", "valor_implícito_por_acción"])
