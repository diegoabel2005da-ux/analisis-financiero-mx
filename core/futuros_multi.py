"""Futuros multiactivo: catálogo de contratos, valor del contrato, márgenes y diversificación del capital.

El margen inicial es una GARANTÍA de cumplimiento, no el costo del activo: el valor del contrato (nocional) suele
ser muchas veces mayor. Por eso se informa el apalancamiento (nocional / margen) y se calcula la pérdida en escenarios.

Fuentes de especificaciones y márgenes (capturados con fecha; los márgenes cambian y deben actualizarse):
- CITIC Securities, "Global Futures Contract Specifications and Margin Table", actualizada el 02/06/2026
  (márgenes de un intermediario, pueden exceder los mínimos de CME): ES, NQ, YM, CL, NG, GC, SI, HG, ZC, ZS, 6E.
- Barchart, especificaciones de 6M (peso mexicano) y ZN (T-Note 10 años): margen/mantenimiento publicados.
- CME Group: tamaño de 6M (500,000 MXN) y de ZN (US$100,000 nominal); MexDer/BMV: futuro del dólar (US$10,000)
  y futuro del IPC ($10 por punto; puja 5 puntos = $50).
Precios: Yahoo Finance (contrato continuo del mes más cercano, "=F"); el tipo de cambio, USD/MXN de Yahoo.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

F_CITIC = "CITIC Securities, tabla de márgenes 02/06/2026"
F_BARCHART = "Barchart, especificaciones del contrato (consulta 2026)"

CATALOGO = [
    # clave, nombre, clase, bolsa, yahoo, multiplicador (USD por unidad de precio), tick, tick USD, margen inicial, mantenimiento, moneda margen, fuente
    dict(clave="ES", nombre="E-mini S&P 500", clase="Índice bursátil", bolsa="CME", yahoo="ES=F", unidad="US$50 × índice",
         mult=50, tick=0.25, tick_usd=12.50, mi=40075.50, mm=36432.00, moneda="USD", fuente=F_CITIC, venc="Trimestral (mar, jun, sep, dic)"),
    dict(clave="NQ", nombre="E-mini Nasdaq-100", clase="Índice bursátil", bolsa="CME", yahoo="NQ=F", unidad="US$20 × índice",
         mult=20, tick=0.25, tick_usd=5.00, mi=40217.00, mm=36561.00, moneda="USD", fuente=F_CITIC, venc="Trimestral"),
    dict(clave="YM", nombre="E-mini Dow Jones", clase="Índice bursátil", bolsa="CBOT", yahoo="YM=F", unidad="US$5 × índice",
         mult=5, tick=1.0, tick_usd=5.00, mi=25006.50, mm=22732.50, moneda="USD", fuente=F_CITIC, venc="Trimestral"),
    dict(clave="6M", nombre="Peso mexicano (MXN/USD)", clase="Divisa", bolsa="CME", yahoo="6M=F", unidad="500,000 MXN",
         mult=500000, tick=0.00001, tick_usd=5.00, mi=1210.00, mm=1100.00, moneda="USD", fuente=F_BARCHART, venc="Mensual"),
    dict(clave="6E", nombre="Euro (EUR/USD)", clase="Divisa", bolsa="CME", yahoo="6E=F", unidad="125,000 EUR",
         mult=125000, tick=0.00005, tick_usd=6.25, mi=2640.00, mm=2400.00, moneda="USD", fuente=F_CITIC, venc="Trimestral"),
    dict(clave="ZN", nombre="T-Note 10 años", clase="Tasa de interés", bolsa="CBOT", yahoo="ZN=F", unidad="US$100,000 nominal",
         mult=1000, tick=0.015625, tick_usd=15.625, mi=2062.00, mm=1875.00, moneda="USD", fuente=F_BARCHART, venc="Trimestral"),
    dict(clave="CL", nombre="Petróleo WTI", clase="Energético", bolsa="NYMEX", yahoo="CL=F", unidad="1,000 barriles",
         mult=1000, tick=0.01, tick_usd=10.00, mi=16156.40, mm=14687.40, moneda="USD", fuente=F_CITIC, venc="Mensual"),
    dict(clave="MCL", nombre="Micro petróleo WTI", clase="Energético", bolsa="NYMEX", yahoo="CL=F", unidad="100 barriles",
         mult=100, tick=0.01, tick_usd=1.00, mi=1618.50, mm=1471.60, moneda="USD", fuente=F_CITIC, venc="Mensual"),
    dict(clave="NG", nombre="Gas natural Henry Hub", clase="Energético", bolsa="NYMEX", yahoo="NG=F", unidad="10,000 MMBtu",
         mult=10000, tick=0.001, tick_usd=10.00, mi=4392.70, mm=3993.60, moneda="USD", fuente=F_CITIC, venc="Mensual"),
    dict(clave="GC", nombre="Oro", clase="Metal", bolsa="COMEX", yahoo="GC=F", unidad="100 onzas troy",
         mult=100, tick=0.10, tick_usd=10.00, mi=37879.50, mm=34435.50, moneda="USD", fuente=F_CITIC, venc="Bimestral"),
    dict(clave="SI", nombre="Plata", clase="Metal", bolsa="COMEX", yahoo="SI=F", unidad="5,000 onzas troy",
         mult=5000, tick=0.005, tick_usd=25.00, mi=42328.00, mm=38480.00, moneda="USD", fuente=F_CITIC, venc="Mensual"),
    dict(clave="HG", nombre="Cobre", clase="Metal", bolsa="COMEX", yahoo="HG=F", unidad="25,000 libras",
         mult=25000, tick=0.0005, tick_usd=12.50, mi=13200.00, mm=12000.00, moneda="USD", fuente=F_CITIC, venc="Mensual"),
    dict(clave="ZC", nombre="Maíz", clase="Materia prima agrícola", bolsa="CBOT", yahoo="ZC=F", unidad="5,000 bushels (precio en centavos)",
         mult=50, tick=0.25, tick_usd=12.50, mi=1210.00, mm=1100.00, moneda="USD", fuente=F_CITIC, venc="Mar, may, jul, sep, dic"),
    dict(clave="ZS", nombre="Soya", clase="Materia prima agrícola", bolsa="CBOT", yahoo="ZS=F", unidad="5,000 bushels (precio en centavos)",
         mult=50, tick=0.25, tick_usd=12.50, mi=2420.00, mm=2200.00, moneda="USD", fuente=F_CITIC, venc="Ene, mar, may, jul, ago, sep, nov"),
    dict(clave="DA", nombre="Dólar (MexDer)", clase="Divisa", bolsa="MexDer", yahoo="MXN=X", unidad="US$10,000 (precio en pesos por dólar)",
         mult=10000, tick=None, tick_usd=None, mi=None, mm=None, moneda="MXN", fuente="BMV, contratos de futuro (margen: capturar AIM de Asigna)",
         venc="Diario, mensual o trimestral", precio_mxn=True),
    dict(clave="IPC", nombre="S&P/BMV IPC (MexDer)", clase="Índice bursátil", bolsa="MexDer", yahoo="^MXX", unidad="$10 MXN × punto",
         mult=10, tick=5.0, tick_usd=None, mi=None, mm=None, moneda="MXN", fuente="CME/MexDer: $10 por punto, puja 5 puntos (margen: capturar AIM)",
         venc="Trimestral", precio_mxn=True),
]

# Mezcla por clase de activo según perfil (pesos del capital de futuros). Suma 1.
MEZCLA = {
    "CONSERVADOR": {"Tasa de interés": 0.35, "Divisa": 0.25, "Metal": 0.20, "Índice bursátil": 0.10, "Energético": 0.05, "Materia prima agrícola": 0.05},
    "MODERADO": {"Índice bursátil": 0.25, "Tasa de interés": 0.20, "Divisa": 0.15, "Metal": 0.15, "Energético": 0.15, "Materia prima agrícola": 0.10},
    "AGRESIVO": {"Índice bursátil": 0.35, "Energético": 0.25, "Metal": 0.20, "Materia prima agrícola": 0.10, "Divisa": 0.05, "Tasa de interés": 0.05},
}


def mezcla_personalizada(s: float) -> dict:
    a, b = MEZCLA["CONSERVADOR"], MEZCLA["AGRESIVO"]
    clases = set(a) | set(b)
    m = {c: a.get(c, 0) + (b.get(c, 0) - a.get(c, 0)) * min(max(s, 0), 1) for c in clases}
    t = sum(m.values())
    return {c: v / t for c, v in m.items()}


def preparar_catalogo(precios: dict, vols: dict, usdmxn: float, margenes_capturados: dict | None = None,
                      seleccion: list | None = None) -> pd.DataFrame:
    """Tabla de contratos con precio, valor del contrato y márgenes en USD y MXN. Sin precio o sin margen: no asignable."""
    filas = []
    for c in CATALOGO:
        if seleccion and c["clave"] not in seleccion:
            continue
        p = precios.get(c["clave"])
        mi, mm = c["mi"], c["mm"]
        cap = (margenes_capturados or {}).get(c["clave"])
        if cap:
            mi, mm = cap.get("mi"), cap.get("mm") or cap.get("mi")
        en_mxn = c.get("precio_mxn", False)
        fx = 1.0 if en_mxn else usdmxn
        valor_mxn = p * c["mult"] * fx if p else np.nan
        mi_mxn = (mi * (1.0 if c["moneda"] == "MXN" else usdmxn)) if mi else np.nan
        mm_mxn = (mm * (1.0 if c["moneda"] == "MXN" else usdmxn)) if mm else np.nan
        tick_mxn = (c["tick_usd"] * usdmxn) if c.get("tick_usd") else ((c["tick"] * c["mult"]) if c.get("tick") and en_mxn else np.nan)
        filas.append({**{k: c[k] for k in ("clave", "nombre", "clase", "bolsa", "unidad", "venc", "fuente", "yahoo")},
                      "precio": p, "multiplicador": c["mult"], "valor_contrato_MXN": valor_mxn,
                      "margen_inicial_MXN": mi_mxn, "margen_mant_MXN": mm_mxn, "valor_tick_MXN": tick_mxn,
                      "apalancamiento": valor_mxn / mi_mxn if (mi_mxn and not np.isnan(mi_mxn) and p) else np.nan,
                      "vol_anual": vols.get(c["clave"], np.nan),
                      "asignable": bool(p) and bool(mi) and not np.isnan(vols.get(c["clave"], np.nan)),
                      "margen_capturado": bool(cap), "en_mxn": en_mxn})
    return pd.DataFrame(filas)


def asignar(cat: pd.DataFrame, monto: float, mezcla: dict, direcciones: dict | None = None, stop_pct: float | None = None) -> pd.DataFrame:
    """Reparte el monto de futuros entre clases según la mezcla y, dentro de cada clase, en partes iguales entre los
    contratos asignables. Contratos = ENTERO(monto del contrato / margen inicial). Dirección: +1 compra, −1 venta."""
    c = cat[cat.asignable].copy()
    if c.empty:
        return c
    clases = c["clase"].value_counts()
    c["peso"] = c["clase"].map(lambda k: mezcla.get(k, 0) / clases[k])
    t = c["peso"].sum()
    c["peso"] = c["peso"] / t if t > 0 else 0
    c["monto_asignado"] = c["peso"] * monto
    c["contratos"] = (c["monto_asignado"] // c["margen_inicial_MXN"]).astype(int)
    # Reparto del sobrante (entero, voraz): se agrega un contrato a la vez donde el faltante contra el objetivo es mayor,
    # sólo si su margen cabe en el efectivo restante.
    resto = monto - float((c["contratos"] * c["margen_inicial_MXN"]).sum())
    for _ in range(1000):
        falt = (c["monto_asignado"] - c["contratos"] * c["margen_inicial_MXN"]) / c["margen_inicial_MXN"]
        cand = c[(c["margen_inicial_MXN"] <= resto) & (c["peso"] > 0)]
        if cand.empty:
            break
        k = falt.loc[cand.index].idxmax()
        c.loc[k, "contratos"] += 1
        resto -= c.loc[k, "margen_inicial_MXN"]
    c["dirección"] = c["clave"].map(lambda k: (direcciones or {}).get(k, 1))
    c["garantía_MXN"] = c["contratos"] * c["margen_inicial_MXN"]
    c["efectivo_sin_usar"] = c["monto_asignado"] - c["garantía_MXN"]  # por contrato contra su objetivo (puede ser negativo)
    c["nocional_MXN"] = c["contratos"] * c["valor_contrato_MXN"]
    c["colchón_por_contrato"] = c["margen_inicial_MXN"] - c["margen_mant_MXN"]
    c["mov_para_llamada_%"] = c["colchón_por_contrato"] / c["valor_contrato_MXN"]
    c["stop_%"] = stop_pct
    return c


def pnl(asig: pd.DataFrame, z: float, h_dias: int, stop_pct: float | None = None, deslizamiento: float = 0.0,
        estres_en_contra: bool = True) -> tuple[float, pd.DataFrame]:
    """Resultado de cada contrato si el precio se mueve m = exp(z·σ·√T) − 1.
    Con estres_en_contra, un z < 0 se aplica en contra de cada posición (sin beneficio de diversificación: prudente).
    Stop-loss (hipotético): la pérdida por contrato se limita a stop% del valor más un deslizamiento; puede no ejecutarse al
    precio objetivo por brechas de mercado."""
    if asig is None or asig.empty:
        return 0.0, pd.DataFrame()
    T = h_dias / 365
    d = asig.copy()
    mov = np.exp(z * d["vol_anual"].values * math.sqrt(T)) - 1
    res_unit = np.where(estres_en_contra & (z < 0), -np.abs(mov), d["dirección"].values * mov)
    if stop_pct:
        res_unit = np.maximum(res_unit, -(stop_pct + deslizamiento))
    d["movimiento_%"] = mov * 100
    d["resultado_MXN"] = d["contratos"].values * d["valor_contrato_MXN"].values * res_unit
    d["llamada_margen"] = (-d["resultado_MXN"] / d["contratos"].replace(0, np.nan) > d["colchón_por_contrato"]).fillna(False)
    return float(d["resultado_MXN"].sum()), d
