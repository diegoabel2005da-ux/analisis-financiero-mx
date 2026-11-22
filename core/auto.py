"""Parámetros de mercado obtenidos automáticamente (sin captura del usuario).

- Tasa libre de riesgo de corto plazo: Cetes 28 días (Banxico SIE, serie SF43936), convertida de tasa simple
  ACT/360 a tasa continua: r_c = (365/d)·ln(1 + r·d/360).
- Tasa de largo plazo para el DCF: Bono M a 10 años si la serie candidata se verifica por su título en el SIE;
  si no, Cetes 364 días (SF43945) con aviso.
- Rendimiento por dividendo: dividendos pagados en los últimos 365 días (Yahoo) / último precio; q = ln(1+y).
- Vencimientos de futuros y opciones sobre acciones e IPC en MexDer: tercer viernes del mes de vencimiento,
  ciclo trimestral (marzo, junio, septiembre, diciembre), o el día hábil anterior si ese viernes es inhábil.
  Fuente: páginas de contratos de futuro y opción de bmv.com.mx. Los días inhábiles se leen de
  data/dias_inhabiles.csv (editable).
"""
from __future__ import annotations

import datetime as dt
import math
from pathlib import Path

import numpy as np
import pandas as pd

from . import rates as rt

CICLO_TRIMESTRAL = (3, 6, 9, 12)
# Claves candidatas del Bono M 10 años: sólo se usan si el título que devuelve Banxico lo confirma.
CANDIDATAS_BONO10 = ("SF44071",)


def simple_a_continua(r_pct: float, dias: int) -> float:
    r = r_pct / 100
    return (365 / dias) * math.log(1 + r * dias / 360)


def dividendo_continuo(dividendos: pd.Series | None, precio: float, hoy: dt.date) -> tuple[float, str]:
    if dividendos is None or len(dividendos) == 0 or not precio:
        return 0.0, "Sin dividendos reportados por Yahoo en 12 meses: q = 0"
    d = dividendos.copy()
    d.index = pd.DatetimeIndex(d.index).tz_localize(None)
    ult = d[d.index > pd.Timestamp(hoy) - pd.Timedelta(days=365)]
    total = float(ult.sum())
    y = total / precio
    return math.log(1 + y), f"Yahoo: {len(ult)} pago(s) en 12 meses, total {total:.4f} MXN / precio {precio:.2f} = {y*100:.2f}%"


def _festivos() -> set[dt.date]:
    p = Path(__file__).resolve().parents[1] / "data" / "dias_inhabiles.csv"
    if not p.exists():
        return set()
    df = pd.read_csv(p)
    return set(pd.to_datetime(df["fecha"]).dt.date) if "fecha" in df and len(df) else set()


def tercer_viernes(año: int, mes: int) -> dt.date:
    d = dt.date(año, mes, 1)
    primer_viernes = d + dt.timedelta(days=(4 - d.weekday()) % 7)
    return primer_viernes + dt.timedelta(days=14)


def ajustar_inhabil(d: dt.date, festivos: set[dt.date]) -> dt.date:
    while d.weekday() >= 5 or d in festivos:
        d -= dt.timedelta(days=1)
    return d


def proximos_vencimientos(hoy: dt.date, n: int = 4, ciclo=CICLO_TRIMESTRAL) -> list[dt.date]:
    """Próximos n vencimientos (incluye hoy si hoy es día de vencimiento)."""
    fest = _festivos()
    out = []
    año, mes = hoy.year, hoy.month
    while len(out) < n:
        if mes in ciclo:
            v = ajustar_inhabil(tercer_viernes(año, mes), fest)
            if v >= hoy:
                out.append(v)
        mes += 1
        if mes > 12:
            mes, año = 1, año + 1
    return out


def tasas_banxico(token: str) -> dict:
    """Consulta única de Banxico con todo lo necesario. Lanza excepción si la consulta falla."""
    ids = ["SF331451", "SF43936", "SF43939", "SF43942", "SF43945", "SF61745"]
    ult = rt.banxico_series(ids + list(CANDIDATAS_BONO10), token)
    if ult.empty:
        raise ValueError("Banxico no devolvió datos.")
    out = {"consulta": dt.datetime.now().isoformat(timespec="seconds"), "tabla": ult}
    fila = lambda s: ult[ult.serie == s].sort_values("fecha").iloc[-1] if (ult.serie == s).any() else None
    c28 = fila("SF43936")
    if c28 is not None:
        out["rf_corto"] = simple_a_continua(c28["valor_%"], 28)
        out["rf_corto_txt"] = f"Cetes 28 días {c28['valor_%']:.2f}% ({c28['fecha'].date()}), Banxico SF43936 → {out['rf_corto']*100:.3f}% continua"
    largo = None
    for s in CANDIDATAS_BONO10:
        f = fila(s)
        if f is not None and "10 a" in str(f["titulo"]).lower() and "bono" in str(f["titulo"]).lower():
            largo = (f["valor_%"] / 100, f"Bono M 10 años {f['valor_%']:.2f}% ({f['fecha'].date()}), Banxico {s}")
            break
    if largo is None:
        c364 = fila("SF43945")
        if c364 is not None:
            largo = (c364["valor_%"] / 100, f"Cetes 364 días {c364['valor_%']:.2f}% ({c364['fecha'].date()}), Banxico SF43945 "
                                             "(no se pudo verificar la serie del Bono M 10 años)")
    if largo:
        out["rf_largo"], out["rf_largo_txt"] = largo
    nodos = []
    for s, d in [("SF331451", 1), ("SF43936", 28), ("SF43939", 91), ("SF43942", 182), ("SF43945", 364)]:
        f = fila(s)
        if f is not None:
            nodos.append({"dias": d, "tasa_pct": float(f["valor_%"]), "convencion": "simple ACT/360",
                          "fuente": f"Banxico {s} {f['fecha'].date()}"})
    out["nodos_curva"] = pd.DataFrame(nodos)
    return out
