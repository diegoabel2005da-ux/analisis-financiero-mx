"""Páginas: Inicio, Emisoras (catálogo + dashboard) y Datos históricos."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from core import data as dat, technical as ta, risk
from . import common as cm


def inicio():
    st.title("Plataforma de análisis financiero, valuación, derivados y coberturas")
    st.markdown("**Principio rector:** primero comprender y cuantificar el riesgo; después construir y comparar las "
                "alternativas de cobertura.")
    st.markdown("""
<div class="bloque-aviso">
<b>Recorrido accionario:</b> Emisoras → Datos históricos → Análisis y valuación → Estados financieros → Patrones y riesgos →
Análisis gráfico → Futuros / Opciones → Estrategias → Coberturas → Perfiles y escenarios → Reportes.<br>
<b>Recorrido de tasas:</b> Derivados de tasas (tasa y curva) → Caps y floors (exposición, valuación, sensibilidades,
escenarios) → Reportes.
</div>""", unsafe_allow_html=True)
    st.subheader("Estado de las fuentes de datos")
    fuentes = pd.DataFrame([
        ("Precios históricos de acciones e IPC", "Yahoo Finance (yfinance)", "Automático, diario, retrasado",
         "Proveedor secundario: no es el cierre oficial BMV. Reconciliable con archivo oficial importado."),
        ("Estados financieros, dividendos, estimados", "Yahoo Finance (yfinance)", "Automático",
         "Cobertura variable por emisora; los rubros faltantes se muestran como no disponibles."),
        ("Catálogo de subyacentes MexDer", "bmv.com.mx (páginas de contratos de futuro y opción)",
         "Revisado el 2026-11-21", "Actualizable editando data/catalogo_mexder.csv."),
        ("Tasas de referencia (TIIE de Fondeo, TIIE, Cetes, tasa objetivo)", "Banxico SIE-API", "Automático con token gratuito",
         "Sin token: captura o importación manual validada."),
        ("Cotizaciones de futuros y primas de opciones MexDer", "No hay acceso gratuito automático", "Captura manual",
         "Sin dato observado, la plataforma muestra valores TEÓRICOS etiquetados."),
        ("Aportaciones iniciales mínimas (AIM)", "Asigna/MexDer", "Captura manual verificada", "No se asumen valores."),
        ("Cotizaciones OTC de caps/floors", "No disponible", "—", "Valuación teórica con curva y volatilidad identificadas."),
    ], columns=["Dato", "Fuente", "Acceso", "Observaciones"])
    st.dataframe(fuentes, width="stretch", hide_index=True)
    st.subheader("Cómo empezar")
    st.markdown("1. Elija una emisora en la barra lateral (persistente en todas las secciones).\n"
                "2. Revise **Emisoras** para el tablero y **Datos históricos** para validar la información.\n"
                "3. Avance por el menú. Cada resultado indica su fuente, período y metodología.")


def emisoras():
    st.title("Emisoras — catálogo de subyacentes MexDer")
    cat = cm.catalogo()
    c1, c2, c3 = st.columns(3)
    sector = c1.multiselect("Sector", sorted(cat.sector.unique()))
    tipo = c2.selectbox("Derivado", ["Todos", "Con futuro", "Con opción"])
    texto = c3.text_input("Buscar")
    v = cat.copy()
    if sector:
        v = v[v.sector.isin(sector)]
    if tipo == "Con futuro":
        v = v[v.futuro_mexder == "SI"]
    if tipo == "Con opción":
        v = v[v.opcion_mexder == "SI"]
    if texto:
        v = v[v.apply(lambda r: texto.lower() in " ".join(r.values).lower(), axis=1)]
    st.dataframe(v, width="stretch", hide_index=True)
    st.caption(f"{len(cat)} subyacentes en catálogo. Fuente: páginas de contratos de futuro y opción de bmv.com.mx, "
               "revisión 2026-11-21. Una emisora puede tener varias series; el catálogo identifica la serie concreta "
               "(p. ej. AMX B). Las claves de contrato vacías no pudieron verificarse y no se suponen.")
    st.download_button("Descargar catálogo (CSV)", cat.to_csv(index=False).encode("utf-8-sig"), "catalogo_mexder.csv")

    st.divider()
    a = cm.activo_actual()
    st.header(f"Tablero: {a['nombre']} ({a['simbolo']})")
    df, meta, err = cm.datos_activo()
    if not cm.requiere_datos(df, meta, err):
        _disponibilidad(None, None)
        return
    c = df["Close"]
    var = c.iloc[-1] / c.iloc[-2] - 1 if len(c) > 1 else np.nan
    inf, e2 = cm.info(a["simbolo"])
    i = (inf or {}).get("info") or {}
    m = st.columns(6)
    m[0].metric("Último cierre (proveedor)", cm.fmt(c.iloc[-1]), cm.fmt(var, pct=True))
    m[1].metric("Volumen última sesión", f"{df['Volume'].iloc[-1]:,.0f}")
    m[2].metric("Máximo del período", cm.fmt(df["High"].max()))
    m[3].metric("Mínimo del período", cm.fmt(df["Low"].min()))
    mcap = i.get("marketCap")
    m[4].metric("Capitalización (Yahoo)", f"{mcap/1e9:,.1f} mm MXN" if mcap else "N/D")
    m[5].metric("Volatilidad anual", cm.fmt(ta.volatilidad(c, 252), pct=True))
    cm.ficha_fuente(meta, "Máx./mín. del período consultado (no histórico total). Volatilidad: desv. est. de rend. log × √252.")
    if meta["estado"].startswith(("Intradía", "Desactualizado")):
        cm.etiqueta(meta["estado"], "alerta")
    r = pd.DataFrame({"Período": ["1 mes", "3 meses", "6 meses", "Todo el rango"],
                      "Rendimiento": [_rend(c, 21), _rend(c, 63), _rend(c, 126), c.iloc[-1] / c.iloc[0] - 1]})
    r["Rendimiento"] = r["Rendimiento"].map(lambda x: cm.fmt(x, pct=True))
    col1, col2 = st.columns([1, 2])
    col1.markdown("**Rendimientos (cierre del proveedor)**")
    col1.dataframe(r, hide_index=True, width="stretch")
    mk, _, _ = cm.datos_mercado()
    rs = {}
    rr = ta.rend_log(c).dropna()
    rs["VaR 95% diario (hist.)"] = cm.fmt(risk.var_historico(rr), pct=True)
    rs["Máx. drawdown"] = cm.fmt(risk.max_drawdown(c)["max_drawdown"], pct=True)
    if not mk.empty:
        b = risk.beta(c, mk["Close"])
        rs["Beta vs IPC"] = cm.fmt(b["beta"])
    col1.markdown("**Resumen de riesgos**")
    col1.dataframe(pd.Series(rs, name="valor"), width="stretch")
    fig = go.Figure(go.Scatter(x=c.index, y=c, line=dict(color=cm.AZUL), name="Cierre"))
    fig.update_layout(height=330, template=cm.PLANTILLA_PLOTLY, margin=dict(l=10, r=10, t=30, b=10),
                      title="Cierre del proveedor (MXN)")
    col2.plotly_chart(fig, width="stretch")
    if i:
        ind = {"P/E (trailing)": i.get("trailingPE"), "P/B": i.get("priceToBook"), "Margen neto": i.get("profitMargins"),
               "ROE": i.get("returnOnEquity"), "Deuda/Capital (Yahoo, %)": i.get("debtToEquity"),
               "Dividend yield": i.get("dividendYield")}
        st.markdown("**Resumen de indicadores financieros (según Yahoo; ver Estados financieros para el cálculo propio)**")
        st.dataframe(pd.Series({k: ("N/D" if v is None else round(v, 4)) for k, v in ind.items()}, name="valor").to_frame().T,
                     width="stretch")
    fila = a.get("fila")
    if fila:
        st.markdown("**Derivados identificados en MexDer**")
        st.write(f"Futuro: **{fila['futuro_mexder']}** {('(clave ' + fila['clave_futuro'] + ')') if fila['clave_futuro'] else ''} · "
                 f"Opción: **{fila['opcion_mexder']}** {('(clave ' + fila['clave_opcion'] + ')') if fila['clave_opcion'] else ''} · "
                 f"Revisión: {fila['fecha_revision']} · [Fuente]({fila['fuente_revision']})")
    _disponibilidad(df, i)
    cm.guardar("activo", {"nombre": a["nombre"], "simbolo": a["simbolo"], "ultimo_cierre": float(c.iloc[-1]),
                          "ultima_fecha": meta["ultima_fecha_disponible"], "estado": meta["estado"]})


def _rend(c, n):
    return c.iloc[-1] / c.iloc[-1 - n] - 1 if len(c) > n else np.nan


def _disponibilidad(df, info):
    st.markdown("**Análisis disponibles con los datos existentes**")
    hay = df is not None and not df.empty
    filas = [("Históricos, rendimientos, volatilidad, técnicos, chartismo", "Disponible" if hay else "Pendiente: sin precios"),
             ("Beta y riesgo de mercado", "Disponible" if hay else "Pendiente: sin precios"),
             ("Estados financieros y ratios", "Disponible (verificar cobertura)" if info else "Pendiente: el proveedor no entregó datos"),
             ("Futuros y opciones", "Teórico con precio spot; observado requiere captura de cotización MexDer"),
             ("Caps y floors", "Independiente del activo: requiere curva (Banxico o importada)")]
    st.dataframe(pd.DataFrame(filas, columns=["Análisis", "Estado"]), hide_index=True, width="stretch")


FREQ = {"Diaria": "D", "Semanal": "W", "Mensual": "M", "Bimestral": "2M", "Trimestral": "Q", "Semestral": "6M", "Anual": "A"}


def historicos():
    st.title("Datos históricos")
    a = cm.activo_actual()
    df, meta, err = cm.datos_activo()
    if err or df.empty:
        cm.requiere_datos(df, meta, err)
        return
    c1, c2, c3 = st.columns(3)
    fr = c1.selectbox("Periodicidad", list(FREQ))
    precio = c2.radio("Precio para rendimientos", ["Close (sin ajustar por dividendos)", "Adj Close (ajustado)"],
                      horizontal=False)
    comparar = c3.checkbox("Comparar contra S&P/BMV IPC", True)
    col_p = "Adj Close" if precio.startswith("Adj") and "Adj Close" in df else "Close"
    d = dat.remuestrear(df, FREQ[fr])
    k = dat.FACTOR_ANUAL[FREQ[fr]]
    t = d.copy()
    t["Rend. simple"] = ta.rend_simple(d[col_p])
    t["Rend. log"] = ta.rend_log(d[col_p])
    t["Rend. acumulado"] = ta.rend_acumulado(d[col_p])
    t["Drawdown"] = ta.drawdown(d[col_p])
    if len(d) > 22:
        t["Vol. móvil anualizada (20)"] = ta.volatilidad(d[col_p], k, 20)
    st.markdown(f"**{a['nombre']}** · {len(d)} observaciones {fr.lower()}s · precio para rendimientos: `{col_p}`")
    cm.ficha_fuente(meta, f"Agregación: primera apertura, máximo, mínimo, último cierre, volumen total. "
                          f"Anualización ×√{k}. {dat.TIPOS_PRECIO[col_p]}")
    m = st.columns(4)
    m[0].metric("Rend. acumulado", cm.fmt(t["Rend. acumulado"].iloc[-1], pct=True))
    m[1].metric(f"Volatilidad anualizada ({fr.lower()})", cm.fmt(ta.volatilidad(d[col_p], k), pct=True) if len(d) > 2 else "N/D")
    m[2].metric("Máx. drawdown", cm.fmt(t["Drawdown"].min(), pct=True))
    m[3].metric("Última fecha disponible", str(meta["ultima_fecha_disponible"]))

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25], vertical_spacing=0.03)
    fig.add_trace(go.Candlestick(x=d.index, open=d["Open"], high=d["High"], low=d["Low"], close=d["Close"], name="OHLC"), 1, 1)
    fig.add_trace(go.Bar(x=d.index, y=d["Volume"], marker_color=cm.GRIS, name="Volumen"), 2, 1)
    fig.update_layout(height=520, template=cm.PLANTILLA_PLOTLY, xaxis_rangeslider_visible=False,
                      margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(fig, width="stretch")

    if comparar:
        mk, mmeta, merr = cm.datos_mercado()
        if mk.empty:
            st.info("No se obtuvo el IPC (^MXX) del proveedor para comparar.")
        else:
            j = pd.concat([df[col_p].rename(a["nombre"]), mk["Close"].rename("IPC")], axis=1, join="inner").dropna()
            base = j / j.iloc[0] * 100
            f2 = go.Figure([go.Scatter(x=base.index, y=base[cn], name=cn) for cn in base])
            f2.update_layout(height=320, template=cm.PLANTILLA_PLOTLY, title="Base 100 en la primera fecha común",
                             margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(f2, width="stretch")
            st.caption(f"Comparación con {len(j)} fechas comunes (intersección de calendarios). IPC: índice de precios, "
                       "no de rendimiento total.")

    st.subheader("Tabla")
    st.dataframe(t.sort_index(ascending=False), width="stretch")
    st.download_button("Descargar tabla (CSV)", t.to_csv().encode("utf-8-sig"), f"{a['simbolo']}_{FREQ[fr]}.csv")
    cm.guardar("historico", df)

    st.subheader("Validación y reconciliación")
    inc = dat.validar_ohlcv(df)
    if inc.empty:
        cm.etiqueta("Validación interna sin incidencias", "ok")
    else:
        cm.etiqueta(f"{len(inc)} incidencias ({(inc.severidad == 'CRITICA').sum()} críticas)",
                    "riesgo" if dat.hay_criticas(inc) else "alerta")
        st.dataframe(inc, width="stretch", hide_index=True)
    div = df[df.get("Dividends", pd.Series(0, index=df.index)) > 0] if "Dividends" in df else pd.DataFrame()
    spl = df[df.get("Stock Splits", pd.Series(0, index=df.index)) > 0] if "Stock Splits" in df else pd.DataFrame()
    st.markdown(f"**Eventos corporativos en el rango (proveedor):** {len(div)} dividendos, {len(spl)} splits. "
                "`Close` está ajustado por splits pero no por dividendos; `Adj Close` ajusta ambos.")
    if not div.empty:
        st.dataframe(div[["Dividends"]], width="stretch")
    with st.expander("Reconciliar contra cierre oficial (archivo CSV/Excel de BMV u otra fuente oficial)"):
        st.write("Suba un archivo con columnas `fecha` y `cierre` del MISMO instrumento y definición de precio. "
                 "La comparación se hace a 2 decimales y las discrepancias se registran; no se fuerzan coincidencias.")
        up = st.file_uploader("Archivo oficial", type=["csv", "xlsx"], key="up_ofi")
        if up:
            try:
                of = dat.importar_csv_precios(up)
                rec = dat.reconciliar(df["Close"], of["Close"])
                rec = rec.loc[rec.index.isin(of.index)]
                st.dataframe(rec.value_counts("estado").rename("días"), width="stretch")
                st.dataframe(rec[rec.estado != "Coincide"], width="stretch")
                cm.guardar("reconciliacion", rec)
                cm.registrar("Reconciliación", {"archivo": up.name}, "|proveedor − oficial| < 0.005",
                             rec.value_counts("estado").to_dict(), df)
            except Exception as e:
                st.error(f"Archivo no válido: {e}")
    with st.expander("Importar serie propia validada (sustituye a Yahoo en esta sesión)"):
        st.write("Útil cuando Yahoo no tiene datos de la emisora. Columnas: fecha, apertura, máximo, mínimo, cierre, volumen.")
        up2 = st.file_uploader("Serie de precios", type=["csv", "xlsx"], key="up_serie")
        if up2:
            try:
                s = dat.importar_csv_precios(up2)
                if not {"Open", "High", "Low", "Volume"} <= set(s.columns):
                    st.error("Para sustituir la serie se requieren apertura, máximo, mínimo, cierre y volumen.")
                else:
                    inc2 = dat.validar_ohlcv(s)
                    st.dataframe(inc2, width="stretch")
                    if dat.hay_criticas(inc2):
                        st.error("La serie tiene incidencias críticas; no se usará.")
                    elif st.button("Usar esta serie para el activo seleccionado"):
                        st.session_state.setdefault("serie_propia", {})[a["simbolo"]] = (s, up2.name)
                        st.success(f"{len(s)} filas activas en todos los módulos durante esta sesión.")
                        st.rerun()
            except Exception as e:
                st.error(str(e))
        if a["simbolo"] in st.session_state.get("serie_propia", {}):
            if st.button("Volver a datos de Yahoo"):
                del st.session_state["serie_propia"][a["simbolo"]]
                st.rerun()
