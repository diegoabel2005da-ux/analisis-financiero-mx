"""Utilidades compartidas de la interfaz: carga de datos con caché, estilos, avisos y estado de sesión."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from core import data as dat, audit

RAIZ = Path(__file__).resolve().parents[1]
AZUL, TURQUESA, GRIS = "#0B1F3A", "#14B8C4", "#8A94A6"
VERDE, AMBAR, ROJO = "#1F9D55", "#D97706", "#C0392B"
PLANTILLA_PLOTLY = "plotly_white"


def estado():
    s = st.session_state
    s.setdefault("bitacora", [])
    s.setdefault("res", {})
    s.setdefault("estudios", [])
    s.setdefault("versiones_escenarios", [])
    return s


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def catalogo() -> pd.DataFrame:
    return pd.read_csv(RAIZ / "data" / "catalogo_mexder.csv", dtype=str).fillna("")


@st.cache_data(ttl=3600, show_spinner="Consultando Yahoo Finance…")
def historico(simbolo: str, inicio: dt.date, fin: dt.date, nombre: str = ""):
    """Caché de 1 hora: los datos se renuevan automáticamente cada día de consulta."""
    try:
        df, meta = dat.descargar_historico(simbolo, inicio, fin, nombre)
        return df, meta.to_dict(), None
    except Exception as e:
        return pd.DataFrame(), None, f"{type(e).__name__}: {e}"


@st.cache_data(ttl=6 * 3600, show_spinner="Consultando información financiera…")
def info(simbolo: str):
    try:
        return dat.descargar_info(simbolo), None
    except Exception as e:
        return {}, f"{type(e).__name__}: {e}"


def activo_actual() -> dict:
    return st.session_state.get("activo", {})


def datos_activo():
    """Devuelve (df, meta, error) del activo seleccionado en el rango seleccionado."""
    a = activo_actual()
    if not a:
        return pd.DataFrame(), None, "Seleccione un activo."
    propia = st.session_state.get("serie_propia", {}).get(a["simbolo"])
    if propia is not None:
        s, nombre_archivo = propia
        s = s.loc[(s.index >= pd.Timestamp(a["inicio"])) & (s.index <= pd.Timestamp(a["fin"]))]
        ult = s.index.max() if len(s) else None
        meta = dat.MetaSerie(a["nombre"], a["simbolo"], "BMV", f"Archivo importado por el usuario: {nombre_archivo}",
                             "Diario OHLCV importado", "MXN", a["inicio"].isoformat(), a["fin"].isoformat(),
                             None if ult is None else ult.date().isoformat(), dat.ahora_mx().isoformat(timespec="seconds"),
                             estado=dat.estado_actualizacion(ult)).to_dict()
        return s, meta, None
    return historico(a["simbolo"], a["inicio"], a["fin"], a["nombre"])


def datos_mercado():
    a = activo_actual()
    return historico("^MXX", a["inicio"], a["fin"], "S&P/BMV IPC")


def ficha_fuente(meta: dict | None, metodologia: str = "", periodo: str | None = None):
    if not meta:
        return
    txt = (f"Fuente: {meta['fuente']} · Tipo: {meta['tipo_cotizacion']} · Moneda: {meta['moneda']} · "
           f"Período: {periodo or (meta['fecha_inicio'] + ' a ' + str(meta['ultima_fecha_disponible']))} · "
           f"Consulta: {meta['fecha_consulta']} ({meta['zona_horaria']}) · Estado: {meta['estado']}")
    if metodologia:
        txt += f" · Metodología: {metodologia}"
    st.caption(txt)


def etiqueta(texto: str, tipo: str = "info"):
    """Etiquetas de color SIEMPRE acompañadas de texto (accesibilidad)."""
    color = {"ok": VERDE, "alerta": AMBAR, "riesgo": ROJO, "info": TURQUESA, "teorico": GRIS}[tipo]
    st.markdown(f"<span style='background:{color};color:white;padding:2px 8px;border-radius:10px;"
                f"font-size:0.8rem'>{texto}</span>", unsafe_allow_html=True)


def requiere_datos(df, meta, err) -> bool:
    if err:
        st.error(f"No fue posible obtener datos del proveedor: {err}")
        return False
    if df is None or df.empty:
        obs = (meta or {}).get("observaciones", [])
        st.warning("Sin datos disponibles para este activo y rango. " + " ".join(obs))
        return False
    inc = dat.validar_ohlcv(df)
    if dat.hay_criticas(inc):
        st.error("Se detectaron inconsistencias CRÍTICAS en los datos; los cálculos críticos quedan bloqueados "
                 "hasta resolverlas (revise 'Datos históricos' → Validación).")
        st.dataframe(inc[inc["severidad"] == "CRITICA"], width="stretch")
        return False
    return True


def registrar(modulo, entradas, formula, resultado, df=None):
    a = activo_actual()
    audit.registrar(st.session_state["bitacora"], modulo, {"activo": a.get("simbolo"), **entradas}, formula, resultado,
                    fuente=dat.FUENTE_YAHOO if df is not None else None, huella_datos=audit.huella(df))


def guardar(clave, valor):
    st.session_state["res"][clave] = valor


def fmt(x, d=2, pct=False):
    if x is None or (isinstance(x, (float, np.floating)) and (np.isnan(x) or np.isinf(x))):
        return "N/D"
    return f"{x*100:,.{d}f}%" if pct else f"{x:,.{d}f}"


CSS = f"""
<style>
[data-testid="stSidebar"] {{ background: {AZUL}; }}
[data-testid="stSidebar"] label, [data-testid="stSidebar"] p, [data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3, [data-testid="stSidebar"] small,
[data-testid="stSidebar"] span {{ color: #FFFFFF; }}
[data-testid="stSidebar"] [data-baseweb="select"] span, [data-testid="stSidebar"] input {{ color: {AZUL}; }}
.bloque-aviso {{ border-left: 4px solid {TURQUESA}; padding: .5rem .8rem; background: rgba(20,184,196,.10); }}
</style>
"""
