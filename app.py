"""Plataforma de análisis financiero, valuación, derivados y coberturas — Mercado mexicano.

Ejecutar localmente:  streamlit run app.py
"""
import datetime as dt

import streamlit as st

st.set_page_config(page_title="Plataforma de Análisis Financiero MX", page_icon="📈", layout="wide")

from ui import common as cm  # noqa: E402
from ui import p_mercado, p_analisis, p_derivados, p_estrategias, p_reportes  # noqa: E402

cm.estado()
st.markdown(cm.CSS, unsafe_allow_html=True)

MENU = {
    "1. Inicio": p_mercado.inicio,
    "2. Emisoras": p_mercado.emisoras,
    "3. Datos históricos": p_mercado.historicos,
    "4. Análisis y valuación": p_analisis.analisis_valuacion,
    "5. Estados financieros": p_analisis.estados_financieros,
    "6. Patrones y riesgos": p_analisis.patrones_riesgos,
    "7. Análisis gráfico": p_analisis.analisis_grafico,
    "8. Futuros": p_derivados.futuros,
    "9. Opciones": p_derivados.opciones,
    "10. Derivados de tasas": p_derivados.derivados_tasas,
    "11. Caps y floors": p_derivados.caps_floors,
    "12. Estrategias": p_estrategias.estrategias,
    "13. Coberturas": p_estrategias.coberturas,
    "14. Perfiles y escenarios": p_estrategias.perfiles_escenarios,
    "15. Reportes": p_reportes.reportes,
    "16. Estudios guardados": p_reportes.estudios,
}

with st.sidebar:
    st.markdown("## 📈 Análisis Financiero MX")
    cat = cm.catalogo()
    opciones = [f"{r.clave_bmv} — {r.simbolo_yahoo}" for r in cat.itertuples()] + ["Otro símbolo (escribir)…"]
    sel = st.selectbox("Activo (persistente)", opciones, index=int(cat.index[cat.simbolo_yahoo == "WALMEX.MX"][0]),
                       key="sel_activo")
    if sel.startswith("Otro"):
        simbolo = st.text_input("Símbolo de Yahoo Finance (p. ej. GFNORTEO.MX)", "GFNORTEO.MX").strip().upper()
        nombre = simbolo
        fila = None
    else:
        fila = cat.iloc[opciones.index(sel)]
        simbolo, nombre = fila.simbolo_yahoo, fila.clave_bmv
    hoy = cm.dat.ahora_mx().date()
    rango = st.selectbox("Período", ["1 año", "6 meses", "3 meses", "1 mes", "Personalizado"], index=0)
    if rango == "Personalizado":
        c1, c2 = st.columns(2)
        ini = c1.date_input("Desde", hoy - dt.timedelta(days=365), min_value=hoy - dt.timedelta(days=365), max_value=hoy)
        fin = c2.date_input("Hasta", hoy, min_value=ini, max_value=hoy)
    else:
        dias = {"1 año": 365, "6 meses": 182, "3 meses": 91, "1 mes": 30}[rango]
        ini, fin = hoy - dt.timedelta(days=dias), hoy
    st.session_state["activo"] = {"simbolo": simbolo, "nombre": nombre, "inicio": ini, "fin": fin,
                                  "fila": None if fila is None else fila.to_dict()}
    st.caption("Máximo 1 año de historia. Los datos se consultan a Yahoo Finance cada vez que abre la página "
               "(caché de 1 hora).")
    st.divider()
    pagina = st.radio("Menú", list(MENU), key="menu", label_visibility="collapsed")
    st.divider()
    st.caption("Tema claro/oscuro: menú ⋮ (arriba a la derecha) → Settings → Theme.")

MENU[pagina]()

st.divider()
st.caption("Herramienta profesional de análisis e investigación. No ejecuta órdenes reales, no promete resultados y no "
           "presenta simulaciones como cotizaciones oficiales. Datos de mercado: Yahoo Finance (proveedor secundario, con "
           "retraso). Los valores teóricos se identifican como tales.")
