"""Páginas: Análisis y valuación, Estados financieros, Patrones y riesgos, Análisis gráfico."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from core import technical as ta, fundamentals as fd, risk, patterns as pt
from . import common as cm


def _precio_y_mercado():
    df, meta, err = cm.datos_activo()
    ok = cm.requiere_datos(df, meta, err)
    return df, meta, ok


# =========================================================================== 4
def analisis_valuacion():
    st.title("Análisis y valuación de la emisora")
    df, meta, ok = _precio_y_mercado()
    if not ok:
        return
    t1, t2, t3, t4, t5, t6 = st.tabs(["Precio spot", "ROC · Williams · Estocástico", "RSI 9/14/25", "Fibonacci",
                                      "Valuación DCF", "Múltiplos comparables"])
    c = df["Close"]
    with t1:
        st.metric("Último cierre del proveedor (referencia spot)", cm.fmt(c.iloc[-1]),
                  cm.fmt(c.iloc[-1] / c.iloc[-2] - 1, pct=True) if len(c) > 1 else None)
        cm.ficha_fuente(meta, "El 'spot' aquí es el último cierre disponible del proveedor (retrasado), no una cotización en tiempo real.")
        n_ma = st.multiselect("Medias móviles", [20, 50, 100, 200], [20, 50])
        fig = go.Figure(go.Scatter(x=c.index, y=c, name="Cierre", line=dict(color=cm.AZUL)))
        for n in n_ma:
            fig.add_scatter(x=c.index, y=ta.sma(c, n), name=f"SMA{n}")
        fig.update_layout(height=420, template=cm.PLANTILLA_PLOTLY, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, width="stretch")
        var = pd.DataFrame({"Variación diaria %": ta.rend_simple(c) * 100}).describe().T
        st.dataframe(var, width="stretch")
    with t2:
        a, b, cc, d = st.columns(4)
        n_roc = a.number_input("Períodos ROC", 1, 200, 12)
        n_w = b.number_input("Ventana Williams %R", 2, 200, 14)
        n_k = cc.number_input("Ventana estocástico", 2, 200, 14)
        modo = d.selectbox("Estocástico", ["lento", "rapido"])
        sk = a.number_input("Suavizado %K (lento)", 1, 20, 3)
        sd = b.number_input("Suavizado %D", 1, 20, 3)
        zs = cc.slider("Zonas Williams (sobreventa/sobrecompra)", -100, 0, (-80, -20))
        r = ta.roc(c, n_roc)
        w = ta.williams_r(df["High"], df["Low"], c, n_w)
        s = ta.estocastico(df["High"], df["Low"], c, n_k, sk, sd, modo)
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05,
                            subplot_titles=(f"ROC({n_roc})", f"Williams %R({n_w})", f"Estocástico {modo} ({n_k},{sk},{sd})"))
        fig.add_scatter(x=r.index, y=r, name="ROC", row=1, col=1)
        fig.add_hline(0, line_dash="dot", row=1, col=1)
        fig.add_scatter(x=w.index, y=w, name="%R", row=2, col=1)
        for z in zs:
            fig.add_hline(z, line_dash="dot", line_color=cm.GRIS, row=2, col=1)
        fig.add_scatter(x=s.index, y=s["%K"], name="%K", row=3, col=1)
        fig.add_scatter(x=s.index, y=s["%D"], name="%D", row=3, col=1)
        for z in (20, 80):
            fig.add_hline(z, line_dash="dot", line_color=cm.GRIS, row=3, col=1)
        fig.update_layout(height=650, template=cm.PLANTILLA_PLOTLY, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig, width="stretch")
        cr = ta.cruces_cero(r)
        st.markdown(f"**Cruces de cero del ROC:** {len(cr)}")
        st.dataframe(cr.tail(15), width="stretch")
        st.caption("ROC(n)=[(P_t/P_(t−n))−1]×100 · %R=−100×(Máx_n−C)/(Máx_n−Mín_n), indefinido si Máx_n=Mín_n · "
                   "%K=100×(C−Mín_n)/(Máx_n−Mín_n); lento: SMA(%K, suav.) y %D=SMA(%K, suav.).")
        cm.guardar("tecnico_vals", {"roc": float(r.iloc[-1]) if r.notna().any() else None,
                                    "williams": float(w.iloc[-1]) if w.notna().any() else None,
                                    "k": float(s["%K"].iloc[-1]) if s["%K"].notna().any() else None})
    with t3:
        rs = {n: ta.rsi_wilder(c, n) for n in (9, 14, 25)}
        fig = go.Figure([go.Scatter(x=v.index, y=v, name=f"RSI {n}") for n, v in rs.items()])
        for z in (30, 70):
            fig.add_hline(z, line_dash="dot", line_color=cm.GRIS)
        fig.update_layout(height=380, template=cm.PLANTILLA_PLOTLY, yaxis_range=[0, 100], margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, width="stretch")
        tab = pd.DataFrame({f"RSI {n}": [v.iloc[-1], v.max(), v.min(), (v > 70).sum(), (v < 30).sum()] for n, v in rs.items()},
                           index=["Último", "Máximo", "Mínimo", "Días > 70", "Días < 30"])
        st.dataframe(tab.round(2), width="stretch")
        st.caption("Suavizado de Wilder: promedio simple de las primeras n variaciones y luego AG_t=(AG_(t−1)(n−1)+G_t)/n.")
        tv = st.session_state["res"].get("tecnico_vals", {})
        tv.update({"rsi9": float(rs[9].iloc[-1]), "rsi14": float(rs[14].iloc[-1]), "rsi25": float(rs[25].iloc[-1])})
        cm.guardar("tecnico_vals", tv)
        cm.registrar("RSI", {"n": [9, 14, 25]}, "Wilder", {k: float(v.iloc[-1]) for k, v in rs.items()}, df)
    with t4:
        modo = st.radio("Anclaje", ["Automático (algoritmo de pivotes)", "Manual"], horizontal=True)
        if modo.startswith("Auto"):
            v = st.slider("Ventana de pivote (barras a cada lado)", 2, 20, 5)
            aut = ta.fibonacci_auto(df, v)
            if not aut:
                st.warning("No hay suficientes pivotes; se usan el máximo y mínimo del período (puede cambiar a manual).")
                aut = {"alto": float(df["High"].max()), "bajo": float(df["Low"].min()),
                       "tendencia": "alcista" if df["High"].idxmax() > df["Low"].idxmin() else "bajista",
                       "desde": df.index[0], "hasta": df.index[-1]}
            alto, bajo, tend = aut["alto"], aut["bajo"], aut["tendencia"]
            st.write(f"Anclas: {tend} de {aut['desde'].date()} a {aut['hasta'].date()} (bajo {bajo:.2f}, alto {alto:.2f}).")
        else:
            x1, x2, x3 = st.columns(3)
            alto = x1.number_input("Alto", value=float(df["High"].max()))
            bajo = x2.number_input("Bajo", value=float(df["Low"].min()))
            tend = x3.selectbox("Movimiento", ["alcista", "bajista"])
        ext = st.checkbox("Incluir extensiones (127.2%, 161.8%, 200%, 261.8%)", True)
        fib = ta.fibonacci(alto, bajo, tend, ext)
        fig = go.Figure(go.Candlestick(x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=c, name="OHLC"))
        for _, f in fib.iterrows():
            fig.add_hline(f["precio"], line_dash="dash" if f["tipo"] == "Extensión" else "solid",
                          line_color=cm.TURQUESA if f["tipo"] == "Retroceso" else cm.GRIS,
                          annotation_text=f"{f['nivel']} · {f['precio']:.2f}", annotation_position="right")
        fig.update_layout(height=520, template=cm.PLANTILLA_PLOTLY, xaxis_rangeslider_visible=False, margin=dict(l=10, r=90, t=20, b=10))
        st.plotly_chart(fig, width="stretch")
        st.dataframe(fib, hide_index=True, width="stretch")
        cm.guardar("fibonacci", fib)
    with t5:
        _dcf(df)
    with t6:
        _multiplos(df)


def _dcf(df):
    a = cm.activo_actual()
    inf, err = cm.info(a["simbolo"])
    if err or not inf:
        st.warning(f"Sin información financiera del proveedor ({err}). Puede capturar todos los supuestos manualmente.")
        inf = {}
    i = inf.get("info") or {}
    precio = float(df["Close"].iloc[-1])
    rt_df, extra = fd.ratios(inf.get("income_a"), inf.get("balance_a"), inf.get("cash_a"), i, precio)
    fcff_h = fd.fcff_historico(inf.get("income_a"), inf.get("cash_a")) if inf.get("cash_a") is not None else pd.Series(dtype=float)
    st.markdown("**FCFF histórico calculado** (FCFF = Flujo operativo + Intereses·(1−t) − CAPEX; datos del proveedor)")
    if fcff_h.dropna().size:
        st.dataframe(fcff_h.rename("FCFF").to_frame().T, width="stretch")
    else:
        st.info("No fue posible calcular el FCFF histórico con los datos del proveedor; capture el FCFF base.")
    mk, _, _ = cm.datos_mercado()
    b = risk.beta(df["Close"], mk["Close"]) if not mk.empty else {"beta": np.nan}
    st.markdown("**Supuestos (editables; son hipótesis del analista, no datos observados)**")
    c1, c2, c3, c4 = st.columns(4)
    fcff0 = c1.number_input("FCFF base (MXN)", value=float(fcff_h.dropna().iloc[-1]) if fcff_h.dropna().size else 1.0e9, format="%.0f")
    rf_l, txt_rf = cm.rf_largo()
    rf = c2.number_input("Tasa libre de riesgo % (largo plazo)", value=float(round(rf_l * 100, 3)), step=0.1, help=txt_rf) / 100
    beta_u = c3.number_input("Beta", value=float(round(b["beta"], 3)) if not np.isnan(b["beta"]) else 1.0, step=0.05)
    prm = c4.number_input("Prima de riesgo de mercado %", value=6.0, step=0.25) / 100
    c5, c6, c7, c8 = st.columns(4)
    pp = c5.number_input("Prima adicional (país/tamaño) %", value=0.0, step=0.25) / 100
    gi = extra.get("gasto_intereses")
    kd_def = abs(gi) / extra["deuda_total"] * 100 if (gi and extra.get("deuda_total") and not np.isnan(gi) and extra["deuda_total"] > 0) else 10.0
    kd = c6.number_input("Costo de deuda antes de impuestos %", value=float(round(min(kd_def, 30), 2)), step=0.1) / 100
    t_def = extra.get("tasa_efectiva")
    t = c7.number_input("Tasa de impuestos %", value=float(round(t_def * 100, 1)) if t_def and not np.isnan(t_def) else 30.0) / 100
    acciones = c8.number_input("Acciones en circulación", value=float(extra["acciones"]) if extra.get("acciones") and not np.isnan(extra["acciones"]) else 1.0e9, format="%.0f")
    E_def = float(extra["capitalizacion"]) if extra.get("capitalizacion") and not np.isnan(extra["capitalizacion"]) else precio * acciones
    D_def = float(extra["deuda_total"]) if extra.get("deuda_total") and not np.isnan(extra["deuda_total"]) else 0.0
    DN_def = float(extra["deuda_neta"]) if extra.get("deuda_neta") and not np.isnan(extra["deuda_neta"]) else D_def
    c9, c10, c11, c12 = st.columns(4)
    E = c9.number_input("Valor de mercado del capital (E)", value=E_def, format="%.0f")
    D = c10.number_input("Deuda (D)", value=D_def, format="%.0f")
    DN = c11.number_input("Deuda neta", value=DN_def, format="%.0f")
    medio = c12.checkbox("Ajuste a mitad de año", False)
    st.caption(f"Tasa libre de riesgo: {txt_rf}. Prima de mercado, crecimientos y g son supuestos del analista.")
    crec_txt = st.text_input("Crecimientos anuales del FCFF % (separados por coma)", "6, 6, 5, 5, 4")
    g = st.number_input("Crecimiento terminal %", value=3.5, step=0.1) / 100
    try:
        crec = [float(x) / 100 for x in crec_txt.split(",") if x.strip()]
        ke = fd.capm(rf, beta_u, prm, pp)
        w = fd.wacc(E, D, ke, kd, t)
        r = fd.dcf(fcff0, crec, g, w, DN, acciones, medio)
    except Exception as e:
        st.error(f"No se puede calcular: {e}")
        return
    m = st.columns(5)
    m[0].metric("Costo de capital (Ke)", cm.fmt(ke, pct=True))
    m[1].metric("WACC", cm.fmt(w, pct=True))
    m[2].metric("Valor empresa", f"{r['valor_empresa']/1e9:,.2f} mm")
    m[3].metric("Valor del capital", f"{r['valor_capital']/1e9:,.2f} mm")
    m[4].metric("Valor estimado por acción", cm.fmt(r["valor_por_accion"]), cm.fmt(r["valor_por_accion"] / precio - 1, pct=True))
    st.caption(f"Valor terminal = {r['peso_vt_%']:.1f}% del valor empresa. El valor teórico no implica que el precio de mercado "
               f"lo alcance. Precio de comparación: último cierre del proveedor {precio:.2f}.")
    st.dataframe(r["tabla"], hide_index=True, width="stretch")
    st.markdown("**Sensibilidad del valor por acción (WACC × g)**")
    ws = [w + d for d in (-0.02, -0.01, 0, 0.01, 0.02)]
    gs = [g + d for d in (-0.01, -0.005, 0, 0.005, 0.01)]
    sens = fd.sensibilidad_dcf(fcff0, crec, DN, acciones, ws, gs)
    st.dataframe(sens.round(2), width="stretch")
    cm.guardar("dcf", {"parametros": {"fcff0": fcff0, "wacc": w, "g": g, "deuda_neta": DN, "acciones": acciones,
                                      "crecimientos": crec, "medio": medio, "rf": rf, "beta": beta_u, "prm": prm, "kd": kd, "t": t, "ke": ke},
                       "resultado": {k: v for k, v in r.items() if k != "tabla"}, "tabla": r["tabla"], "sensibilidad": sens})
    cm.registrar("DCF", {"fcff0": fcff0, "crec": crec, "g": g, "wacc": w}, "EV=ΣFCFF/(1+WACC)^t + VT/(1+WACC)^N",
                 {"valor_por_accion": r["valor_por_accion"]}, df)


def _multiplos(df):
    a = cm.activo_actual()
    cat = cm.catalogo()
    pares = st.multiselect("Emisoras comparables", [s for s in cat.simbolo_yahoo if s not in (a["simbolo"], "^MXX")],
                           default=[s for s in ["FEMSAUBD.MX", "BIMBOA.MX", "KOFUBL.MX"] if s != a["simbolo"]])
    if not pares:
        return
    filas = []
    for s in pares:
        inf, err = cm.info(s)
        i = (inf or {}).get("info") or {}
        filas.append({"símbolo": s, "P/E": i.get("trailingPE"), "EV/EBITDA": i.get("enterpriseToEbitda"),
                      "P/B": i.get("priceToBook"), "EV/Ventas": i.get("enterpriseToRevenue"),
                      "estado": "OK" if i else f"Sin datos ({err})"})
    t = pd.DataFrame(filas)
    st.dataframe(t, hide_index=True, width="stretch")
    st.caption("Múltiplos según Yahoo Finance (proveedor secundario). Celdas vacías: el proveedor no publica el dato.")
    inf, _ = cm.info(a["simbolo"])
    i = (inf or {}).get("info") or {}
    _, extra = fd.ratios((inf or {}).get("income_a"), (inf or {}).get("balance_a"), None, i, float(df["Close"].iloc[-1]))
    num = t[["P/E", "EV/EBITDA", "P/B"]].apply(pd.to_numeric, errors="coerce")
    imp = fd.multiplos_comparables(num, extra, extra.get("acciones"), extra.get("deuda_neta") or 0)
    if imp.empty:
        st.info("No hay métricas suficientes de la emisora para valores implícitos.")
    else:
        st.markdown("**Valor implícito por acción (mediana de pares)**")
        st.dataframe(imp.round(2), hide_index=True, width="stretch")
        cm.guardar("multiplos", imp)


# =========================================================================== 5
def estados_financieros():
    st.title("Estados financieros")
    a = cm.activo_actual()
    inf, err = cm.info(a["simbolo"])
    if err or not inf:
        st.error(f"El proveedor no entregó información financiera: {err}")
        return
    st.caption(f"Fuente: {inf['fuente']} · Consulta: {inf['consulta']}. Pueden diferir de los reportes enviados por la "
               "emisora a BMV/CNBV (consolidado vs. individual, reclasificaciones). Rubros faltantes = no disponibles.")
    per = st.radio("Periodicidad", ["Anual", "Trimestral"], horizontal=True)
    sfx = "a" if per == "Anual" else "q"
    inc, bal, cash = inf.get(f"income_{sfx}"), inf.get(f"balance_{sfx}"), inf.get(f"cash_{sfx}")
    tabs = st.tabs(["Resumen", "Estado de resultados", "Balance general", "Flujos de efectivo", "Ratios", "Dividendos",
                    "Reportes", "Previsiones"])
    fmt_mm = lambda d: (d / 1e6).round(1) if isinstance(d, pd.DataFrame) else d
    with tabs[0]:
        rs = fd.resumen(inc, bal, cash)
        if rs.empty or rs.isna().all().all():
            st.info("Sin datos de resumen.")
        else:
            st.dataframe(fmt_mm(rs), width="stretch")
            st.caption("Millones de MXN (según moneda de reporte del proveedor).")
            ing = fd.rubro(inc, "ingresos").sort_index()
            un = fd.rubro(inc, "utilidad_neta").sort_index()
            mg = pd.DataFrame({"Margen EBITDA %": fd.rubro(inc, "ebitda") / ing * 100,
                               "Margen neto %": un / ing * 100, "Crecimiento ingresos %": ing.pct_change() * 100})
            st.dataframe(mg.T.round(2), width="stretch")
    for k, (df_, base) in zip([1, 2, 3], [(inc, "Total Revenue"), (bal, "Total Assets"), (cash, None)]):
        with tabs[k]:
            if df_ is None or not isinstance(df_, pd.DataFrame) or df_.empty:
                st.info("No disponible en el proveedor.")
                continue
            d = df_.reindex(sorted(df_.columns), axis=1)
            st.dataframe(fmt_mm(d), width="stretch")
            if base:
                c1, c2 = st.columns(2)
                c1.markdown("**Análisis horizontal (var. % vs período previo)**")
                c1.dataframe(fd.analisis_horizontal(d).round(1), width="stretch")
                c2.markdown(f"**Análisis vertical (% de {base})**")
                c2.dataframe(fd.analisis_vertical(d, base).round(1), width="stretch")
            if k == 3:
                fo, capex = fd.rubro(d, "flujo_operativo"), fd.rubro(d, "capex")
                fl = pd.DataFrame({"Operación": fo, "Inversión": fd.rubro(d, "flujo_inversion"),
                                   "Financiamiento": fd.rubro(d, "flujo_financiamiento"), "CAPEX": capex,
                                   "Flujo libre (FO + CAPEX)": fo + capex})
                fig = go.Figure([go.Bar(x=fl.index.astype(str), y=fl[c] / 1e6, name=c) for c in fl])
                fig.update_layout(barmode="group", height=360, template=cm.PLANTILLA_PLOTLY, title="Millones")
                st.plotly_chart(fig, width="stretch")
    with tabs[4]:
        df, meta, err2 = cm.datos_activo()
        precio = float(df["Close"].iloc[-1]) if not df.empty else None
        r, extra = fd.ratios(inf.get("income_a"), inf.get("balance_a"), inf.get("cash_a"), inf.get("info"), precio)
        r_show = r.copy()
        r_show["valor"] = [cm.fmt(v, 2, pct=(u == "%")) for v, u in zip(r["valor"], r["unidad"])]
        st.dataframe(r_show, hide_index=True, width="stretch")
        st.caption("Calculados con el último ejercicio anual disponible y el último cierre del proveedor. Explicación: "
                   "liquidez mide capacidad de pago de corto plazo; ROE/ROA/ROIC rentabilidad; márgenes eficiencia; "
                   "apalancamiento y cobertura riesgo financiero; múltiplos valoración relativa.")
        cm.guardar("ratios", r)
        cm.guardar("fund_extra", extra)
    with tabs[5]:
        dv = inf.get("dividends")
        if dv is None or len(dv) == 0:
            st.info("El proveedor no reporta dividendos.")
        else:
            dvd = dv.to_frame("dividendo_por_acción")
            dvd.index = pd.DatetimeIndex(dvd.index).tz_localize(None)
            anual = dvd.groupby(dvd.index.year).agg(total=("dividendo_por_acción", "sum"), pagos=("dividendo_por_acción", "count"))
            st.dataframe(dvd.sort_index(ascending=False).head(20), width="stretch")
            st.dataframe(anual.sort_index(ascending=False), width="stretch")
            i = inf.get("info") or {}
            st.write(f"Dividend yield (Yahoo): {cm.fmt(i.get('dividendYield'))} · Payout (Yahoo): {cm.fmt(i.get('payoutRatio'), pct=True)}")
            cm.guardar("dividendos", dvd)
    with tabs[6]:
        ed = inf.get("earnings_dates")
        if isinstance(ed, pd.DataFrame) and not ed.empty:
            st.markdown("**Fechas de reporte de resultados (proveedor)**")
            st.dataframe(ed, width="stretch")
        else:
            st.info("El proveedor no publica fechas de reporte para esta emisora.")
        st.markdown("Reportes oficiales verificables: [BMV — emisoras](https://www.bmv.com.mx/es/emisoras/informacion-de-emisoras) · "
                    "[CNBV STIV](https://stivconsultasexternas.cnbv.gob.mx/) · sitio de relación con inversionistas de la emisora.")
    with tabs[7]:
        st.markdown("**1. Estimaciones de analistas disponibles en el proveedor**")
        tg = inf.get("targets")
        if isinstance(tg, dict) and tg:
            st.dataframe(pd.Series(tg, name="precio objetivo").to_frame().T, width="stretch")
            i = inf.get("info") or {}
            st.caption(f"Número de analistas según Yahoo: {i.get('numberOfAnalystOpinions', 'N/D')}. No se crean consensos propios.")
        else:
            st.info("No hay estimaciones de analistas disponibles legalmente en el proveedor para esta emisora.")
        st.markdown("**2. Proyecciones del sistema:** la plataforma no genera pronósticos de precio. Las proyecciones de FCFF del "
                    "DCF se derivan exclusivamente de los supuestos del usuario.")
        dcf = st.session_state["res"].get("dcf")
        st.markdown("**3. Supuestos del usuario (DCF)**")
        if dcf:
            st.json({k: v for k, v in dcf["parametros"].items()})
        else:
            st.info("Aún no se han definido supuestos en Análisis y valuación → Valuación DCF.")


# =========================================================================== 6
def patrones_riesgos():
    st.title("Patrones, tendencias y riesgos")
    df, meta, ok = _precio_y_mercado()
    if not ok:
        return
    c = df["Close"]
    tabs = st.tabs(["Tendencias", "Beta", "Volatilidad, VaR y ES", "Correlaciones", "Liquidez y riesgo financiero"])
    with tabs[0]:
        tend = ta.clasificar_tendencias(c)
        st.dataframe(tend, hide_index=True, width="stretch")
        reg = ta.regresion_tendencia(c)
        ce = ta.cambio_estructural(c)
        fig = go.Figure(go.Scatter(x=c.index, y=c, name="Cierre", line=dict(color=cm.AZUL)))
        if reg:
            fig.add_scatter(x=reg["ajuste"].index, y=reg["ajuste"], name="Regresión log-lineal", line=dict(dash="dash"))
        for n in (20, 50, 200):
            if len(c) >= n:
                fig.add_scatter(x=c.index, y=ta.sma(c, n), name=f"SMA{n}", opacity=0.7)
        if ce:
            fig.add_vline(x=ce["fecha_quiebre"], line_dash="dot", line_color=cm.ROJO)
        pv = ta.pivotes(df["High"], df["Low"], 10)
        rel = pv.sort_values("precio")
        if len(rel):
            fig.add_scatter(x=[rel.iloc[-1]["fecha"], rel.iloc[0]["fecha"]], y=[rel.iloc[-1]["precio"], rel.iloc[0]["precio"]],
                            mode="markers+text", text=["Máximo relevante", "Mínimo relevante"], textposition="top center",
                            marker=dict(size=10, color=cm.TURQUESA), name="Extremos")
        fig.update_layout(height=450, template=cm.PLANTILLA_PLOTLY, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, width="stretch")
        if ce:
            st.write(f"**Cambio estructural (Chow):** quiebre más probable el {ce['fecha_quiebre'].date()} · F={ce['F']:.2f} · "
                     f"p nominal={ce['p_valor_nominal']:.4f} (optimista por búsqueda del punto de quiebre).")
        st.caption("Reglas: ver documentación en cada fila. Máximos/mínimos relevantes: pivotes con ventana de 10 barras.")
        cm.guardar("tendencias", tend)
    mk, mmeta, merr = cm.datos_mercado()
    with tabs[1]:
        if mk.empty:
            st.warning("No se obtuvo el IPC (^MXX) para calcular beta.")
        else:
            bg = risk.beta(c, mk["Close"])
            st.markdown("**Beta general** — horizonte predeterminado: todo el rango seleccionado (máx. 1 año), rendimientos diarios")
            m = st.columns(5)
            m[0].metric("β", cm.fmt(bg["beta"], 3)); m[1].metric("R²", cm.fmt(bg.get("r2"), 3))
            m[2].metric("Error estándar", cm.fmt(bg.get("error_std"), 3)); m[3].metric("Observaciones", bg["n"])
            m[4].metric("Período", f"{bg['inicio'].date()} → {bg['fin'].date()}" if "inicio" in bg else "N/D")
            st.caption(f"Índice de referencia: S&P/BMV IPC (^MXX). {bg.get('metodo', '')}.")
            st.markdown("**Beta personalizada**")
            x1, x2, x3 = st.columns(3)
            d0 = x1.date_input("Desde", c.index[max(0, len(c) - 126)].date(), min_value=c.index[0].date(), max_value=c.index[-1].date())
            d1 = x2.date_input("Hasta", c.index[-1].date(), min_value=d0, max_value=c.index[-1].date())
            freq = x3.selectbox("Frecuencia", ["Diaria", "Semanal"])
            ca = c.loc[str(d0):str(d1)]
            cmk = mk["Close"].loc[str(d0):str(d1)]
            if freq == "Semanal":
                ca, cmk = ca.resample("W-FRI").last(), cmk.resample("W-FRI").last()
            bp = risk.beta(ca, cmk)
            st.write(f"β = **{cm.fmt(bp['beta'], 3)}** · R² {cm.fmt(bp.get('r2'), 3)} · n = {bp['n']} {bp.get('nota', '')}")
            r = risk.alinear_rendimientos(c, mk["Close"], "simple")
            fig = go.Figure(go.Scatter(x=r["m"], y=r["a"], mode="markers", marker=dict(size=5, color=cm.AZUL), name="días"))
            xs = np.linspace(r["m"].min(), r["m"].max(), 10)
            fig.add_scatter(x=xs, y=bg["alfa_diaria"] + bg["beta"] * xs, name=f"β={bg['beta']:.2f}")
            fig.update_layout(height=380, template=cm.PLANTILLA_PLOTLY, xaxis_title="Rend. IPC", yaxis_title="Rend. activo")
            st.plotly_chart(fig, width="stretch")
            st.dataframe(risk.sensibilidad_mercado(bg["beta"]), hide_index=True, width="stretch")
            cm.guardar("beta", bg)
    with tabs[2]:
        rr = ta.rend_log(c).dropna()
        x1, x2, x3 = st.columns(3)
        nivel = x1.selectbox("Nivel de confianza", [0.95, 0.975, 0.99])
        horiz = x2.number_input("Horizonte (días hábiles)", 1, 60, 1)
        pos = x3.number_input("Valor de la posición (MXN)", value=1_000_000.0, step=100_000.0)
        filas = []
        for nombre, f in [("VaR histórico", risk.var_historico), ("ES histórico", risk.es_historico),
                          ("VaR paramétrico normal", risk.var_parametrico), ("ES paramétrico normal", risk.es_parametrico)]:
            v1 = f(rr, nivel)
            vh = risk.escalar_horizonte(v1, horiz)
            filas.append({"medida": nombre, "1 día %": v1 * 100, f"{horiz} días % (√t)": vh * 100, "MXN": vh * pos})
        tv = pd.DataFrame(filas)
        st.dataframe(tv.round(4), hide_index=True, width="stretch")
        md = risk.max_drawdown(c)
        vol = ta.volatilidad(c, 252)
        st.write(f"Volatilidad histórica anualizada: **{cm.fmt(vol, pct=True)}** · Máx. drawdown **{cm.fmt(md['max_drawdown'], pct=True)}** "
                 f"(pico {md['pico'].date()}, fondo {md['fondo'].date()}) · n = {len(rr)} rendimientos log diarios.")
        st.caption("La escala √t supone rendimientos independientes e idénticamente distribuidos; es una aproximación. "
                   "Estas medidas describen el pasado y no son estimaciones infalibles del futuro.")
        fig = go.Figure(go.Histogram(x=rr * 100, nbinsx=50, marker_color=cm.AZUL))
        fig.add_vline(x=-risk.var_historico(rr, nivel) * 100, line_color=cm.ROJO, annotation_text="VaR")
        fig.update_layout(height=300, template=cm.PLANTILLA_PLOTLY, xaxis_title="Rend. diario %")
        st.plotly_chart(fig, width="stretch")
        vm = ta.volatilidad(c, 252, 20)
        f2 = go.Figure(go.Scatter(x=vm.index, y=vm * 100, name="Vol. móvil 20d %"))
        f2.update_layout(height=260, template=cm.PLANTILLA_PLOTLY, title="Volatilidad móvil 20 días (anualizada, %)")
        st.plotly_chart(f2, width="stretch")
        b = st.session_state["res"].get("beta", {})
        cm.guardar("riesgo_vals", {"volatilidad": vol, "max_drawdown": md["max_drawdown"], "var95": risk.var_historico(rr, 0.95),
                                   "es95": risk.es_historico(rr, 0.95), "beta": b.get("beta"), "r2": b.get("r2")})
        cm.guardar("riesgo_tabla", tv)
    with tabs[3]:
        cat = cm.catalogo()
        otros = st.multiselect("Activos a correlacionar", list(cat.simbolo_yahoo),
                               default=[s for s in ["^MXX", "AMXB.MX", "FEMSAUBD.MX"] if s != cm.activo_actual()["simbolo"]])
        a = cm.activo_actual()
        pr = {a["simbolo"]: c}
        for s in otros:
            d_, _, e_ = cm.historico(s, a["inicio"], a["fin"], s)
            if not d_.empty:
                pr[s] = d_["Close"]
            else:
                st.caption(f"{s}: sin datos ({e_ or 'vacío'})")
        if len(pr) > 1:
            co = risk.correlaciones(pr)
            fig = go.Figure(go.Heatmap(z=co.values, x=co.columns, y=co.index, zmin=-1, zmax=1, colorscale="RdBu",
                                       text=co.round(2).values, texttemplate="%{text}"))
            fig.update_layout(height=420, template=cm.PLANTILLA_PLOTLY)
            st.plotly_chart(fig, width="stretch")
            st.caption("Correlación de Pearson de rendimientos logarítmicos diarios en fechas comunes.")
            cm.guardar("correlaciones", co)
    with tabs[4]:
        lq = risk.liquidez(df)
        m = st.columns(4)
        m[0].metric("Volumen promedio diario", f"{lq['volumen_promedio']:,.0f}")
        m[1].metric("Importe promedio (MXN)", f"{lq['importe_promedio_MXN']/1e6:,.1f} M")
        m[2].metric("Días sin volumen", f"{lq['dias_sin_volumen_%']:.1f}%")
        m[3].metric("Iliquidez de Amihud (×10⁶)", f"{lq['amihud_x1e6']:.5f}")
        st.caption("Amihud = promedio de |R_t|/importe_t: mayor valor ⇒ mayor impacto en precio por peso operado.")
        ex = st.session_state["res"].get("fund_extra")
        if ex:
            st.markdown("**Riesgo financiero (último ejercicio)**")
            rt_ = st.session_state["res"].get("ratios")
            st.dataframe(rt_[rt_["ratio"].isin(["Deuda / Capital", "Deuda neta / EBITDA", "Cobertura de intereses",
                                                 "Liquidez corriente", "Prueba ácida"])], hide_index=True, width="stretch")
        else:
            st.info("Abra 'Estados financieros' → Ratios para incorporar el riesgo financiero.")
        cm.guardar("liquidez", lq)


# =========================================================================== 7
def analisis_grafico():
    st.title("Análisis gráfico — chartismo")
    df, meta, ok = _precio_y_mercado()
    if not ok:
        return
    with st.expander("Parámetros de detección", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        v = c1.slider("Ventana de pivotes", 2, 15, 5)
        tol = c2.slider("Tolerancia de igualdad de picos/valles %", 0.5, 8.0, 3.0) / 100
        prof = c3.slider("Profundidad mínima del valle/pico %", 1.0, 15.0, 3.0) / 100
        tsr = c4.slider("Tolerancia de soportes/resistencias %", 0.5, 5.0, 1.5) / 100
        n_piv = c1.slider("Pivotes para rectas (triángulos/canales/cuñas)", 2, 6, 3)
        mastil = c2.slider("Mástil mínimo de bandera %", 3.0, 25.0, 8.0) / 100
    figuras = pt.dobles(df, v, tol, prof) + pt.hch(df, v, tol + 0.01, 0.02) + pt.banderas(df, 10, mastil)
    geo = pt.geometricas(df, v, n_piv)
    sr = pt.soportes_resistencias(df, v, tsr)
    fig = go.Figure(go.Candlestick(x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"], name="OHLC"))
    colores = {"Confirmada": cm.ROJO, "En formación": cm.AMBAR, "Invalidada": cm.GRIS}
    mostrar = st.multiselect("Figuras a mostrar", sorted({f["figura"] for f in figuras}), default=sorted({f["figura"] for f in figuras}))
    for f in figuras:
        if f["figura"] in mostrar and "puntos" in f:
            xs, ys = zip(*f["puntos"])
            fig.add_scatter(x=xs, y=ys, mode="lines+markers", name=f"{f['figura']} ({f['estado']})",
                            line=dict(color=colores.get(f["estado"], cm.TURQUESA), width=2))
    if geo:
        for k in ("linea_superior", "linea_inferior"):
            xs, ys = zip(*geo[k])
            fig.add_scatter(x=xs, y=ys, mode="lines", name=f"{geo['figura']} ({k.split('_')[1]})",
                            line=dict(color=cm.TURQUESA, dash="dash"))
    for _, r in sr.iterrows():
        fig.add_hline(r["nivel"], line_color=cm.VERDE if r["tipo"] == "Soporte" else cm.ROJO, line_dash="dot",
                      annotation_text=f"{r['tipo']} {r['nivel']:.2f} ({r['toques']} toques)", annotation_position="left")
    fig.update_layout(height=620, template=cm.PLANTILLA_PLOTLY, xaxis_rangeslider_visible=False, dragmode="drawline",
                      newshape=dict(line_color=cm.TURQUESA), margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, width="stretch", config={"modeBarButtonsToAdd": ["drawline", "drawopenpath", "drawrect",
                                                                            "drawcircle", "eraseshape"]})
    st.caption("Dibujo manual: use la barra de herramientas del gráfico (línea, trazo libre, rectángulo, borrar). "
               "Las figuras son herramientas descriptivas; no generan órdenes ni garantizan rentabilidad.")
    filas = [{k: v_ for k, v_ in f.items() if k != "puntos"} for f in figuras]
    if geo:
        filas.append({k: v_ for k, v_ in geo.items() if not k.startswith("linea")})
    tabla = pd.DataFrame(filas)
    st.subheader("Figuras detectadas")
    if tabla.empty:
        st.info("No se detectaron figuras con los parámetros actuales.")
    else:
        st.dataframe(tabla, hide_index=True, width="stretch")
    st.subheader("Soportes y resistencias")
    st.dataframe(sr.round({"nivel": 2, "distancia_%": 2}) if not sr.empty else sr, hide_index=True, width="stretch")
    cm.guardar("patrones", tabla)
    cm.guardar("soportes", sr)
