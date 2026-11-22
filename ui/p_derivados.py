"""Páginas: Futuros, Opciones, Derivados de tasas (referencias y curvas), Caps y floors."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import options as op, futures as fu, rates as rt, technical as ta, scenarios as sc
from . import common as cm


def _spot_y_vol():
    df, meta, err = cm.datos_activo()
    if err or df.empty:
        return None, None, df, meta
    return float(df["Close"].iloc[-1]), ta.volatilidad(df["Close"], 252), df, meta


HORIZONTES = {"Mensual": 30, "Bimestral": 61, "Trimestral": 91, "Semestral": 182, "Anual": 365}


def _horizonte(key):
    c1, c2 = st.columns(2)
    h = c1.selectbox("Horizonte de simulación", list(HORIZONTES) + ["Personalizado"], index=2, key=f"h_{key}")
    hoy = cm.dat.ahora_mx().date()
    if h == "Personalizado":
        f = c2.date_input("Fecha del horizonte", hoy + dt.timedelta(days=60), min_value=hoy + dt.timedelta(days=1), key=f"hf_{key}")
    else:
        f = hoy + dt.timedelta(days=HORIZONTES[h])
        c2.write(f"Fecha del horizonte: **{f}**")
    return (f - hoy).days / 365, f


# =========================================================================== 8
def futuros():
    st.title("Contratos de futuros")
    S, vol, df, meta = _spot_y_vol()
    if S is None:
        cm.requiere_datos(df, meta, None)
        return
    a = cm.activo_actual()
    fila = a.get("fila") or {}
    if fila and fila.get("futuro_mexder") != "SI":
        st.warning(f"Según el catálogo, {a['nombre']} no tiene futuro listado en MexDer. Puede analizarlo como contrato "
                   "TEÓRICO de simulación.")
    hoy = cm.dat.ahora_mx().date()
    st.subheader("Información contractual")
    st.caption("Capture los datos de las Condiciones Generales de Contratación y del boletín de MexDer. Los valores "
               "precargados son marcadores editables, NO datos verificados.")
    c = st.columns(4)
    simb = c[0].text_input("Símbolo del contrato", fila.get("clave_futuro") or "")
    venc = c[1].date_input("Vencimiento (verificar en MexDer)", hoy + dt.timedelta(days=90), min_value=hoy + dt.timedelta(days=1))
    venc_ok = c[2].checkbox("Vencimiento verificado contra MexDer", False)
    liq = c[3].selectbox("Liquidación", ["En especie (física)", "En efectivo (financiera)"])
    c = st.columns(4)
    M = c[0].number_input("Multiplicador / tamaño (acciones por contrato)", value=100.0, step=1.0)
    tick = c[1].number_input("Tick mínimo (MXN)", value=0.01, format="%.4f")
    Fobs = c[2].number_input("Precio del futuro OBSERVADO (0 = no disponible)", value=0.0, format="%.4f")
    fuente_obs = c[3].text_input("Fuente y fecha del precio observado", "")
    c = st.columns(4)
    vol_c = c[0].number_input("Volumen (observado)", value=0, step=1)
    oi = c[1].number_input("Interés abierto (observado)", value=0, step=1)
    com = c[2].number_input("Comisión por contrato (MXN)", value=0.0)
    r = c[3].number_input("Tasa libre de riesgo % (cont.)", value=7.0, step=0.1) / 100
    q = st.number_input("Rendimiento por dividendo % (cont.)", value=0.0, step=0.1) / 100
    T = (venc - hoy).days / 365
    Fteo = fu.precio_teorico(S, r, q, T)
    F0 = Fobs if Fobs > 0 else Fteo
    m = st.columns(5)
    m[0].metric("Spot de referencia (último cierre proveedor)", cm.fmt(S))
    m[1].metric("Futuro teórico F=S·e^((r−q)T)", cm.fmt(Fteo, 4))
    m[2].metric("Futuro usado", cm.fmt(F0, 4))
    m[3].metric("Valor del tick", cm.fmt(tick * M, 2))
    m[4].metric("Tamaño nocional del contrato", cm.fmt(F0 * M, 0))
    cm.etiqueta("Precio OBSERVADO" if Fobs > 0 else "Precio TEÓRICO (no es cotización MexDer)", "ok" if Fobs > 0 else "teorico")
    if not venc_ok:
        cm.etiqueta("Vencimiento no verificado: los resultados son de simulación", "alerta")
    if Fobs > 0:
        st.write(f"Base observada (F − S): {Fobs - S:,.4f} · Base teórica: {Fteo - S:,.4f}")
    st.caption("Los futuros no se clasifican como americanos o europeos: no tienen ejercicio.")

    st.subheader("Posturas y resultado agregado")
    c = st.columns(4)
    post = c[0].selectbox("Postura en futuros", ["Venta (corta)", "Compra (larga)"])
    n = c[1].number_input("Número de contratos", 1, 100000, 10)
    acc = c[2].number_input("Acciones del subyacente en cartera (+ larga, − corta)", value=1000.0, step=100.0)
    sugerido = fu.razon_cobertura(abs(acc), M)
    c[3].metric("Contratos para cubrir 1:1", f"{sugerido:,.1f}")
    h, fh = _horizonte("fut")
    posicion = "corta" if post.startswith("Venta") else "larga"
    precios = np.linspace(S * 0.7, S * 1.3, 61)
    filas = []
    for ST in precios:
        FT = fu.precio_teorico(ST, r, q, max(T - h, 0))
        agg = fu.resultado_agregado(acc, S, ST, n, M, F0, FT, posicion, com * n * 2)
        filas.append({"precio_subyacente": ST, "futuro_en_horizonte": FT, **agg})
    t = pd.DataFrame(filas)
    fig = go.Figure()
    for col, nombre in [("subyacente", "Subyacente"), ("futuro", "Futuros"), ("total", "Agregado")]:
        fig.add_scatter(x=t["precio_subyacente"], y=t[col], name=nombre, line=dict(width=3 if col == "total" else 2))
    fig.add_vline(S, line_dash="dot", annotation_text="Spot")
    fig.update_layout(height=420, template=cm.PLANTILLA_PLOTLY, xaxis_title="Precio del subyacente en el horizonte",
                      yaxis_title="P&L (MXN)", margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, width="stretch")
    st.caption(f"P&L = n·M·(F_h − F_0), signo inverso en cortas; F_h teórico con tiempo remanente {max(T-h,0):.3f} años. "
               "Incluye comisiones de entrada y salida. El resultado del derivado se muestra junto al del subyacente.")
    if h > T:
        st.warning("El horizonte excede el vencimiento: se supone liquidación al vencimiento (F_T = S_T).")

    st.subheader("Aportaciones iniciales mínimas (AIM) y liquidez")
    c = st.columns(3)
    aim = c[0].number_input("AIM por contrato (MXN, verificar con Asigna/MexDer)", value=0.0, step=100.0)
    mant = c[1].slider("Nivel de restitución (% de la AIM)", 50, 100, 100) / 100
    max_d = min(250, len(df) - 1)
    dias = c[2].slider("Trayectoria histórica para simular ajustes (días)", 2, max_d, min(60, max_d)) if max_d > 2 else max_d
    if aim <= 0:
        st.info("Capture la AIM verificada para simular garantías. No se asume ningún valor.")
    else:
        tray = df["Close"].iloc[-dias:]
        tf = pd.Series([fu.precio_teorico(s_, r, q, T) for s_ in tray], index=tray.index)
        tf = tf / tf.iloc[0] * F0
        mg = fu.margen_diario(tf, n, M, posicion, aim, mant)
        k = st.columns(4)
        k[0].metric("Garantía inicial (depósito)", f"{aim*n:,.0f}")
        k[1].metric("P&G acumulada (ajustes)", f"{mg['pyg_acumulada'].iloc[-1]:,.0f}")
        k[2].metric("Llamadas de margen totales", f"{mg['llamada_margen'].sum():,.0f}")
        k[3].metric("Necesidad máxima de liquidez", f"{aim*n + mg['llamada_margen'].sum():,.0f}")
        st.dataframe(mg, hide_index=True, width="stretch")
        st.caption("Simulación con la trayectoria HISTÓRICA del subyacente reescalada al futuro actual. La garantía es un depósito "
                   "recuperable, no una pérdida; las pérdidas son los ajustes diarios negativos.")
        cm.guardar("margen", mg)
    cm.guardar("futuros", pd.DataFrame([{"símbolo": simb, "subyacente": a["nombre"], "vencimiento": venc,
                                         "vencimiento_verificado": venc_ok, "precio_futuro": F0,
                                         "origen_precio": "observado: " + fuente_obs if Fobs > 0 else "teórico",
                                         "multiplicador": M, "tick": tick, "valor_tick": tick * M, "moneda": "MXN",
                                         "liquidación": liq, "volumen": vol_c, "interés_abierto": oi, "comisión": com,
                                         "AIM": aim if aim > 0 else None, "postura": posicion, "contratos": n}]))
    cm.registrar("Futuros", {"S": S, "r": r, "q": q, "T": T, "Fobs": Fobs}, "F=S·e^((r−q)T); P&L=n·M·ΔF", {"F0": F0}, df)


# =========================================================================== 9
def opciones():
    st.title("Contratos de opciones")
    S, vol, df, meta = _spot_y_vol()
    if S is None:
        cm.requiere_datos(df, meta, None)
        return
    a = cm.activo_actual()
    fila = a.get("fila") or {}
    if fila and fila.get("opcion_mexder") != "SI":
        st.warning("Según el catálogo, este activo no tiene opciones listadas en MexDer: análisis TEÓRICO.")
    hoy = cm.dat.ahora_mx().date()
    c = st.columns(4)
    tipo = c[0].selectbox("Tipo", ["call", "put"])
    K = c[1].number_input("Strike", value=float(round(S, 2)), step=0.5)
    venc = c[2].date_input("Vencimiento (verificar en MexDer)", hoy + dt.timedelta(days=91), min_value=hoy + dt.timedelta(days=1))
    estilo = c[3].selectbox("Estilo de ejercicio", ["Europeo", "Americano"])
    c = st.columns(4)
    S_in = c[0].number_input("Precio spot", value=S)
    sig = c[1].number_input("Volatilidad % (predet.: histórica 1 año)", value=float(round(vol * 100, 2)), step=0.5) / 100
    r = c[2].number_input("Tasa libre de riesgo % (cont.)", value=7.0, step=0.1) / 100
    q = c[3].number_input("Dividendo % (cont.)", value=0.0, step=0.1) / 100
    c = st.columns(4)
    M = c[0].number_input("Multiplicador", value=100.0)
    liq = c[1].selectbox("Liquidación", ["En especie", "En efectivo"])
    prima_obs = c[2].number_input("Prima OBSERVADA (0 = no disponible)", value=0.0, format="%.4f")
    fuente = c[3].text_input("Fuente/fecha de la prima observada", "")
    c = st.columns(4)
    bid = c[0].number_input("Bid", value=0.0, format="%.4f")
    ask = c[1].number_input("Ask", value=0.0, format="%.4f")
    vol_c = c[2].number_input("Volumen", value=0, step=1)
    oi = c[3].number_input("Interés abierto", value=0, step=1)
    T = (venc - hoy).days / 365
    teo = op.bsm(S_in, K, T, r, q, sig, tipo)
    g = op.griegas(S_in, K, T, r, q, sig, tipo)
    amer = estilo == "Americano"
    crr_v = op.crr(S_in, K, T, r, q, sig, 300, tipo, amer)
    st.subheader("Valuación")
    m = st.columns(4)
    m[0].metric("Prima teórica BSM (europea)", cm.fmt(teo, 4))
    m[1].metric(f"CRR 300 pasos ({estilo.lower()})", cm.fmt(crr_v, 4))
    m[2].metric("Prima observada", cm.fmt(prima_obs, 4) if prima_obs > 0 else "No disponible")
    iv = op.vol_implicita(prima_obs, S_in, K, T, r, q, tipo) if prima_obs > 0 else np.nan
    m[3].metric("Volatilidad implícita (de prima observada)", cm.fmt(iv, pct=True) if prima_obs > 0 else "Requiere prima observada")
    if prima_obs > 0 and np.isnan(iv):
        st.error("La prima observada viola los límites de no arbitraje del modelo BSM; no se calcula volatilidad implícita.")
    if bid > 0 and ask > 0:
        st.write(f"Punto medio bid/ask: {(bid+ask)/2:.4f} · Diferencial: {ask-bid:.4f} ({(ask-bid)/((bid+ask)/2)*100:.2f}%)")
    cm.etiqueta("Prima teórica (modelo) ≠ cotización de mercado", "teorico")
    if amer and tipo == "call" and q == 0:
        st.caption("Sin dividendos, la call americana no se ejerce anticipadamente: su valor coincide con la europea.")
    st.caption("BSM supone ejercicio europeo, volatilidad y tasa constantes, dividendo continuo. Dividendos discretos: no "
               "modelados (limitación); aproxímelos con q equivalente.")
    gr = pd.DataFrame([g]).rename(columns={"delta": "Delta", "gamma": "Gamma", "vega": "Vega (por 1 pt vol)",
                                           "theta": "Theta (por día)", "rho": "Rho (por 1 pt tasa)"})
    st.dataframe(gr.round(6), hide_index=True, width="stretch")

    t1, t2, t3 = st.tabs(["Operaciones básicas", "Modelo binomial (árbol y convergencia)", "Sensibilidades"])
    with t1:
        c = st.columns(3)
        posi = c[0].selectbox("Posición", ["larga", "corta"])
        n = c[1].number_input("Contratos", 1, 10000, 1)
        usar = c[2].selectbox("Prima a usar", ["Observada" if prima_obs > 0 else "Teórica"] + (["Teórica"] if prima_obs > 0 else []))
        prima = prima_obs if usar == "Observada" else teo
        res = op.resumen_basica(S_in, K, T, r, q, sig, tipo, posi, prima, M, n)
        nombre = f"{'Long' if posi == 'larga' else 'Short'} {tipo.capitalize()}"
        k = st.columns(4)
        k[0].metric("Flujo inicial (primas)", f"{res['flujo_inicial']:,.2f}")
        k[1].metric("Punto de equilibrio", cm.fmt(res["punto_equilibrio"]))
        k[2].metric("Ganancia máxima", "Ilimitada" if np.isinf(res["ganancia_maxima"]) else f"{res['ganancia_maxima']:,.2f}")
        k[3].metric("Pérdida máxima", "Ilimitada" if np.isinf(res["perdida_maxima"]) else f"{res['perdida_maxima']:,.2f}")
        if posi == "corta":
            cm.etiqueta("Posición vendida: requiere garantías y puede generar obligaciones elevadas", "riesgo")
        dias_h = st.slider("Revaluación antes del vencimiento: días transcurridos", 0, max(1, int(T * 365) - 1), int(T * 365 / 2))
        h = dias_h / 365
        Ss = np.linspace(S_in * 0.6, S_in * 1.4, 121)
        s_ = 1 if posi == "larga" else -1
        pay = s_ * (op.payoff_vencimiento(Ss, K, tipo) - prima) * M * n
        rev = s_ * (np.array([op.bsm(x, K, T - h, r, q, sig, tipo) for x in Ss]) - prima) * M * n
        fig = go.Figure([go.Scatter(x=Ss, y=pay, name="Payoff al vencimiento"),
                         go.Scatter(x=Ss, y=rev, name=f"Revaluación a {dias_h} días (BSM)", line=dict(dash="dash"))])
        fig.add_hline(0, line_color=cm.GRIS)
        fig.add_vline(S_in, line_dash="dot", annotation_text="Spot")
        fig.update_layout(height=400, template=cm.PLANTILLA_PLOTLY, title=nombre, xaxis_title="Precio del subyacente",
                          yaxis_title="Resultado (MXN)")
        st.plotly_chart(fig, width="stretch")
        st.caption("Antes del vencimiento la opción conserva valor tiempo: se revalúa con el modelo, no con el payoff terminal.")
    with t2:
        pasos = st.slider("Pasos del árbol a mostrar", 2, 8, 4)
        pv, arb = op.crr(S_in, K, T, r, q, sig, pasos, tipo, amer, devolver_arbol=True)
        st.write(f"u = {arb['u']:.5f}, d = {arb['d']:.5f}, p = {arb['p']:.5f}, Δt = {T/pasos:.5f} · Valor ({pasos} pasos) = {pv:.4f}")
        filas = []
        for i, (sv, vv, ex) in enumerate(zip(arb["S"], arb["V"], arb["ejercicio"])):
            for j in range(len(sv)):
                filas.append({"paso": i, "nodo (bajadas)": j, "S": sv[j], "valor": vv[j], "ejercicio anticipado": bool(ex[j])})
        st.dataframe(pd.DataFrame(filas).round(4), hide_index=True, width="stretch")
        conv = op.convergencia_crr(S_in, K, T, r, q, sig, tipo, amer)
        fig = go.Figure([go.Scatter(x=conv["pasos"], y=conv["CRR"], mode="lines+markers", name="CRR"),
                         go.Scatter(x=conv["pasos"], y=conv["BSM_europea"], name="BSM europea", line=dict(dash="dot"))])
        fig.update_layout(height=320, template=cm.PLANTILLA_PLOTLY, xaxis_type="log", title="Convergencia numérica")
        st.plotly_chart(fig, width="stretch")
        st.dataframe(conv.round(6), hide_index=True, width="stretch")
    with t3:
        Ss = np.linspace(S_in * 0.6, S_in * 1.4, 81)
        gg = pd.DataFrame([op.griegas(x, K, T, r, q, sig, tipo) for x in Ss], index=Ss)
        sel = st.selectbox("Griega", list(gg.columns))
        fig = go.Figure(go.Scatter(x=Ss, y=gg[sel]))
        fig.update_layout(height=320, template=cm.PLANTILLA_PLOTLY, xaxis_title="Spot", yaxis_title=sel)
        st.plotly_chart(fig, width="stretch")
    cm.guardar("opciones", pd.DataFrame([{"subyacente": a["nombre"], "tipo": tipo, "estilo": estilo, "liquidación": liq,
                                          "strike": K, "vencimiento": venc, "spot": S_in, "vol_%": sig * 100,
                                          "origen_vol": "histórica 1 año (editable)", "r_%": r * 100, "q_%": q * 100,
                                          "multiplicador": M, "prima_teórica_BSM": teo, "prima_CRR": crr_v,
                                          "prima_observada": prima_obs or None, "fuente_prima": fuente or None,
                                          "vol_implícita_%": iv * 100 if not np.isnan(iv) else None,
                                          "volumen": vol_c, "interés_abierto": oi, **g}]))
    cm.registrar("Opciones", {"S": S_in, "K": K, "T": T, "r": r, "q": q, "sigma": sig, "tipo": tipo},
                 "BSM / CRR", {"bsm": teo, "crr": crr_v, "iv": iv}, df)


# =========================================================================== 10
def _token():
    try:
        tk = st.secrets.get("BANXICO_TOKEN", "")
    except Exception:
        tk = ""
    return st.text_input("Token del SIE-API de Banxico (gratuito)", value=st.session_state.get("tk_banxico", tk), type="password",
                         help="Obténgalo en https://www.banxico.org.mx/SieAPIRest/service/v1/token") or ""


@st.cache_data(ttl=6 * 3600, show_spinner="Consultando Banxico…")
def _banxico(ids, token, ini=None, fin=None):
    try:
        return rt.banxico_series(list(ids), token, ini, fin), None
    except Exception as e:
        return pd.DataFrame(), f"{type(e).__name__}: {e}"


def derivados_tasas():
    st.title("Derivados sobre tasas — referencias y curvas")
    t1, t2 = st.tabs(["Tasas de referencia (Banxico)", "Curva de tasas"])
    with t1:
        tk = _token()
        st.session_state["tk_banxico"] = tk
        if not tk:
            st.info("Sin token no hay consulta automática. Puede capturar o importar la curva en la pestaña 'Curva de tasas'.")
        else:
            ult, err = _banxico(tuple(rt.SERIES_BANXICO), tk)
            if err:
                st.error(f"Banxico: {err}")
            elif not ult.empty:
                ult["plazo"] = ult["serie"].map(lambda s: {"SF331451": "1 día", "SF61745": "—", "SF43783": "28 días",
                                                            "SF43878": "91 días", "SF111916": "182 días"}.get(s, f"{rt.PLAZO_CETES.get(s, '')} días"))
                ult["convención"] = ult["serie"].map(lambda s: "Anual simple, ACT/360")
                ult["fuente"] = "Banxico SIE-API"
                st.dataframe(ult, hide_index=True, width="stretch")
                st.caption("Último dato publicado por Banxico (dato oportuno). Series sin publicación reciente (p. ej. TIIE a plazos "
                           "en transición hacia TIIE de Fondeo) aparecen con su última fecha. Se respeta la metodología vigente de "
                           "cada referencia.")
                cm.guardar("tasas_ref", ult)
                serie = st.selectbox("Histórico", list(rt.SERIES_BANXICO), format_func=lambda s: f"{s} — {rt.SERIES_BANXICO[s]}",
                                     index=1)
                hoy = cm.dat.ahora_mx().date()
                h, err2 = _banxico((serie,), tk, hoy - dt.timedelta(days=365), hoy)
                if not h.empty:
                    s_ = h.set_index("fecha")["valor_%"]
                    fig = go.Figure(go.Scatter(x=s_.index, y=s_, name=serie))
                    fig.update_layout(height=320, template=cm.PLANTILLA_PLOTLY, yaxis_title="%")
                    st.plotly_chart(fig, width="stretch")
                    vh = rt.vol_historica_tasa(s_)
                    st.write(f"Volatilidad HISTÓRICA (1 año): normal **{vh['normal_bp']:.1f} pb** anuales · lognormal "
                             f"**{vh['lognormal']*100:.1f}%** · n={vh['n']}. No es volatilidad implícita de mercado.")
                    st.session_state["vol_hist_tasa"] = vh
    with t2:
        _editor_curva()


def _editor_curva():
    st.markdown("Nodos de la curva de descuento. Convenciones: `simple ACT/360` (mercado de dinero: Cetes, TIIE) o "
                "`cero continua ACT/365`. Interpolación lineal en tasa cero continua; extrapolación plana.")
    st.warning("Una curva gubernamental (Cetes) NO equivale a la curva OIS de TIIE de Fondeo usada por el mercado de swaps. "
               "Para valuaciones de mercado importe una curva verificada de un proveedor de precios autorizado.")
    base = st.session_state.get("curva_nodos")
    c1, c2 = st.columns(2)
    if c1.button("Precargar Cetes 28/91/182/364 + TIIE de Fondeo desde Banxico"):
        tk = st.session_state.get("tk_banxico", "")
        if not tk:
            st.error("Capture el token de Banxico en la pestaña anterior.")
        else:
            ult, err = _banxico(tuple(["SF331451"] + list(rt.PLAZO_CETES)), tk)
            if err or ult.empty:
                st.error(f"No fue posible obtener las tasas: {err}")
            else:
                filas = []
                for _, r in ult.iterrows():
                    d = 1 if r["serie"] == "SF331451" else rt.PLAZO_CETES[r["serie"]]
                    filas.append({"dias": d, "tasa_pct": r["valor_%"], "convencion": "simple ACT/360",
                                  "fuente": f"Banxico {r['serie']} {r['fecha'].date()}"})
                base = pd.DataFrame(filas).sort_values("dias")
                st.session_state["curva_nodos"] = base
                st.session_state["curva_fuente"] = "Banxico SIE (Cetes + TIIE de Fondeo)"
    up = c2.file_uploader("Importar curva (CSV: dias, tasa_pct, convencion)", type=["csv", "xlsx"])
    if up:
        try:
            imp = pd.read_csv(up) if up.name.endswith(".csv") else pd.read_excel(up)
            imp.columns = [c.strip().lower() for c in imp.columns]
            if not {"dias", "tasa_pct"} <= set(imp.columns):
                raise ValueError("Faltan columnas 'dias' y 'tasa_pct'.")
            imp["convencion"] = imp.get("convencion", "simple ACT/360")
            imp["fuente"] = f"Importada: {up.name}"
            if (imp["dias"] <= 0).any() or imp["tasa_pct"].isna().any():
                raise ValueError("Plazos deben ser > 0 y tasas no vacías.")
            base = imp[["dias", "tasa_pct", "convencion", "fuente"]]
            st.session_state["curva_nodos"] = base
            st.session_state["curva_fuente"] = f"Importada ({up.name})"
        except Exception as e:
            st.error(f"Curva inválida: {e}")
    if base is None:
        base = pd.DataFrame({"dias": [28, 91, 182, 364], "tasa_pct": [np.nan] * 4, "convencion": ["simple ACT/360"] * 4,
                             "fuente": ["capturar"] * 4})
    ed = st.data_editor(base, num_rows="dynamic", width="stretch", key="ed_curva",
                        column_config={"convencion": st.column_config.SelectboxColumn(options=["simple ACT/360", "cero continua ACT/365"])})
    ed = ed.dropna(subset=["dias", "tasa_pct"])
    if ed.empty:
        st.info("Capture al menos un nodo con tasa para construir la curva. No se usan tasas supuestas.")
        return None
    if len(ed) < 3:
        st.warning("Con menos de 3 nodos la curva es muy limitada; la plataforma no la presenta como curva oficial.")
    fecha = cm.dat.ahora_mx().date()
    try:
        curva = rt.Curva(ed[["dias", "tasa_pct", "convencion"]], fecha, st.session_state.get("curva_fuente", "Capturada por el usuario"))
    except Exception as e:
        st.error(str(e))
        return None
    st.session_state["curva_nodos"] = ed
    st.session_state["curva"] = curva
    t = np.linspace(1 / 365, max(ed["dias"].max() / 365, 0.1), 120)
    z = curva.cero(t) * 100
    dfs = curva.df(t)
    fw = [(float(curva.forward_simple(x, x + 28 / 365, 28 / 360)[0]) * 100) for x in t]
    fig = go.Figure([go.Scatter(x=t * 365, y=z, name="Cero continua %"), go.Scatter(x=t * 365, y=fw, name="Forward 28d simple %"),
                     go.Scatter(x=ed["dias"], y=ed["tasa_pct"], mode="markers", name="Nodos (cotización original)")])
    fig.update_layout(height=360, template=cm.PLANTILLA_PLOTLY, xaxis_title="Plazo (días)", yaxis_title="%")
    st.plotly_chart(fig, width="stretch")
    f2 = go.Figure(go.Scatter(x=t * 365, y=dfs, name="Factor de descuento"))
    f2.update_layout(height=260, template=cm.PLANTILLA_PLOTLY, xaxis_title="Plazo (días)", title="Factores de descuento")
    st.plotly_chart(f2, width="stretch")
    tabla = pd.DataFrame({"plazo_dias": (t * 365).round(0), "cero_%": z, "DF": dfs, "forward_28d_%": fw}).iloc[::10]
    st.dataframe(tabla.round(6), hide_index=True, width="stretch")
    cm.guardar("curva", ed)
    cm.guardar("curva_tabla", tabla)
    return curva


# =========================================================================== 11
def caps_floors():
    st.title("Caps y floors — protección de exposiciones a tasas (MXN)")
    st.markdown('<div class="bloque-aviso">Los caps y floors sobre TIIE se negocian en el mercado <b>extrabursátil (OTC)</b>. '
                'No se afirma que existan como contratos listados en MexDer. Todas las primas son <b>valuaciones teóricas</b>.</div>',
                unsafe_allow_html=True)
    curva = st.session_state.get("curva")
    if curva is None:
        st.warning("Primero construya la curva en 'Derivados de tasas' → 'Curva de tasas' (o aquí abajo).")
        with st.expander("Construir curva aquí", expanded=True):
            curva = _editor_curva()
        if curva is None:
            return
    hoy = cm.dat.ahora_mx().date()
    st.subheader("1. Registro de la exposición")
    c = st.columns(4)
    N = c[0].number_input("Nocional / principal (MXN)", value=100_000_000.0, step=1_000_000.0, format="%.0f")
    posicion = c[1].selectbox("Tipo de exposición", ["pasivo", "activo"], format_func=lambda x: f"{x.capitalize()} a tasa variable")
    ref = c[2].selectbox("Tasa de referencia", ["TIIE de Fondeo compuesta en atraso", "TIIE 28 días (fijada al inicio)", "Otra (fijada al inicio)"])
    spread = c[3].number_input("Margen contractual (pb)", value=150.0) / 10000
    c = st.columns(4)
    ini = c[0].date_input("Fecha de inicio", hoy, min_value=hoy - dt.timedelta(days=30))
    fin = c[1].date_input("Fecha final", hoy + dt.timedelta(days=730), min_value=ini + dt.timedelta(days=28))
    per = c[2].selectbox("Periodicidad de intereses", ["28D", "1M", "3M", "6M"])
    base = c[3].selectbox("Base de días", ["ACT/360", "ACT/365", "30/360"])
    c = st.columns(3)
    amort = c[0].selectbox("Amortización", ["bullet", "lineal", "personalizada"])
    lista = c[1].text_input("Nocionales personalizados (coma)", "") if amort == "personalizada" else ""
    cond = c[2].text_input("Condiciones específicas", "")
    fijacion = "compuesta en atraso" if ref.startswith("TIIE de Fondeo") else "al inicio"
    periodos = rt.calendario(ini, fin, per)
    noc = rt.nocionales_amortizacion(N, len(periodos), amort, [float(x) for x in lista.split(",") if x.strip()] if lista else None)
    st.write(f"{len(periodos)} períodos · fijación: **{fijacion}** · riesgo principal: "
             f"**{'alza de tasas (aumenta el costo)' if posicion == 'pasivo' else 'baja de tasas (reduce el ingreso)'}**")
    st.caption("Calendario sin ajuste por días inhábiles (limitación). Composición en atraso: el forward del período se obtiene de "
               "la curva y la volatilidad usa el tiempo efectivo t_inicio + (t_fin − t_inicio)/3 (Lyashenko-Mercurio).")

    st.subheader("2. Instrumento y modelo")
    c = st.columns(4)
    instr = c[0].selectbox("Instrumento", ["cap", "floor"], index=0 if posicion == "pasivo" else 1)
    tab0 = rt.valuar_cap_floor(curva, hoy, periodos, noc, 0.05, 0.2, "Black-76", "cap", base, fijacion)
    fwd_prom = float(np.average(tab0["forward_%"], weights=tab0["nocional"] * tab0["alfa"])) if not tab0.empty else 8.0
    K = c[1].number_input("Strike %", value=float(round(fwd_prom + (1 if instr == "cap" else -1), 2)), step=0.25) / 100
    modelo = c[2].selectbox("Modelo", ["Black-76", "Bachelier"])
    vh = st.session_state.get("vol_hist_tasa", {})
    origen = c[3].selectbox("Origen de la volatilidad", ["Hipotética del analista", "Histórica (Banxico)", "Implícita de cotización real"])
    if modelo == "Black-76":
        vdef = vh.get("lognormal", 0.20) if origen.startswith("Hist") and vh else 0.20
        sigma = st.number_input("Volatilidad lognormal % (Black-76)", value=float(round(vdef * 100, 2)), step=1.0) / 100
    else:
        vdef = vh.get("normal_bp", 100.0) if origen.startswith("Hist") and vh else 100.0
        sigma = st.number_input("Volatilidad normal (pb anuales, Bachelier)", value=float(round(vdef, 1)), step=5.0) / 10000
    if origen.startswith("Implícita"):
        st.info("Indique en 'Condiciones' la cotización y fuente de donde obtuvo la volatilidad implícita. La plataforma no crea "
                "superficies de volatilidad ficticias.")
    incl = st.checkbox("Incluir el primer caplet/floorlet (si su tasa ya está fijada, sólo valor intrínseco)", True)
    tasa_fij = None
    if fijacion == "al inicio" and periodos and pd.Timestamp(periodos[0][0]) <= pd.Timestamp(hoy):
        tf = st.number_input("Tasa ya fijada del período en curso % (0 = usar forward)", value=0.0)
        tasa_fij = tf / 100 if tf > 0 else None

    tabla = rt.valuar_cap_floor(curva, hoy, periodos, noc, K, sigma, modelo, instr, base, fijacion, tasa_fij, incl)
    if tabla["valor_presente"].isna().any():
        st.error("Black-76 no admite forwards o strikes ≤ 0; use Bachelier.")
        return
    total = tabla["valor_presente"].sum()
    sens = rt.sensibilidades(curva, hoy, periodos, noc, K, sigma, modelo, instr, base, fijacion,
                             tasa_fijada_primer=tasa_fij, incluir_primero=incl)
    st.subheader("3. Valuación teórica")
    m = st.columns(5)
    m[0].metric(f"Valor {instr} (VP teórico)", f"{total:,.0f}")
    m[1].metric("% del nocional", f"{total/N*100:.3f}%")
    m[2].metric("DV01 (+1 pb paralelo)", f"{sens['DV01_+1pb']:,.0f}")
    m[3].metric("Vega (+1 punto)", f"{sens['vega_+1pt']:,.0f}")
    m[4].metric("Theta (1 día)", f"{sens['theta_1dia']:,.0f}")
    cm.etiqueta(f"Valuación teórica · volatilidad: {origen.lower()} · curva: {curva.fuente}", "teorico")
    st.dataframe(tabla.round(6), hide_index=True, width="stretch")
    fig = go.Figure([go.Bar(x=tabla["periodo"], y=tabla["valor_intrinseco"], name="Intrínseco"),
                     go.Bar(x=tabla["periodo"], y=tabla["valor_tiempo"], name="Valor tiempo")])
    fig.update_layout(barmode="stack", height=320, template=cm.PLANTILLA_PLOTLY, xaxis_title=f"{instr}let", yaxis_title="VP (MXN)")
    st.plotly_chart(fig, width="stretch")
    st.markdown("**Sensibilidades**")
    st.dataframe(pd.DataFrame([sens]).round(2), hide_index=True, width="stretch")
    st.caption("DV01: cambio de VP ante +1 pb en toda la curva cero. Vega: +1% (Black) o +1 pb (Bachelier). Theta: fecha de "
               "valuación +1 día con la misma curva. Empinamiento/aplanamiento/mariposa: choques no paralelos de ±10 pb.")
    st.markdown("**Comparación entre modelos**")
    F_med = fwd_prom / 100
    if modelo == "Black-76":
        s_alt = sigma * F_med
        otra = rt.valuar_cap_floor(curva, hoy, periodos, noc, K, s_alt, "Bachelier", instr, base, fijacion, tasa_fij, incl)["valor_presente"].sum()
        st.write(f"Bachelier con σ_normal ≈ σ_Black·F̄ = {s_alt*10000:.1f} pb → {otra:,.0f} MXN (diferencia {otra-total:,.0f}).")
    else:
        s_alt = sigma / F_med if F_med > 0 else np.nan
        otra = rt.valuar_cap_floor(curva, hoy, periodos, noc, K, s_alt, "Black-76", instr, base, fijacion, tasa_fij, incl)["valor_presente"].sum() if F_med > 0 else np.nan
        st.write(f"Black-76 con σ_Black ≈ σ_normal/F̄ = {s_alt*100:.2f}% → {otra:,.0f} MXN (diferencia {otra-total:,.0f}).")
    st.caption("Las diferencias surgen de la forma de la distribución supuesta: lognormal (Black) penaliza menos las bajas "
               "extremas y más las alzas lejanas; normal (Bachelier) admite tasas negativas. La conversión de volatilidad es "
               "aproximada (sólo ATM).")

    st.subheader("4. Simulación de protección — 3 perfiles × estrategias × 5 escenarios")
    perfiles = st.session_state.get("perfiles_tasas", sc.PERFILES_TASAS)
    ancho = st.number_input("Ancho del collar (pb entre strikes)", value=200.0, step=25.0)
    mat, meta_m = sc.matriz_tasas(curva, hoy, periodos, noc, posicion, spread, sigma, modelo, fijacion, base, perfiles, ancho)
    st.write(f"Forward promedio ponderado: **{meta_m['forward_promedio_%']:.3f}%** · Evaluaciones: **{len(mat)}** "
             f"({mat.perfil.nunique()} perfiles × {mat.estrategia.nunique()} estrategias × 5 escenarios)")
    pf = st.selectbox("Perfil", list(perfiles))
    sub = mat[mat.perfil == pf]
    fig = go.Figure([go.Bar(x=g["escenario"], y=g["resultado_combinado_VP"], name=e) for e, g in sub.groupby("estrategia", sort=False)])
    fig.update_layout(barmode="group", height=420, template=cm.PLANTILLA_PLOTLY, yaxis_title="VP flujos netos − primas (MXN)",
                      title=f"Resultado combinado por escenario — perfil {pf}")
    st.plotly_chart(fig, width="stretch")
    st.dataframe(sub.round(2), hide_index=True, width="stretch")
    esc = st.selectbox("Flujos del escenario", sc.ESCENARIOS)
    estr = st.selectbox("Estrategia", list(sc.estrategias_tasas(posicion)))
    k = sc.ESCENARIOS.index(esc)
    p = perfiles[pf]
    sgn = 1 if posicion == "pasivo" else -1
    tf_ = np.array([(pd.Timestamp(d) - pd.Timestamp(hoy)).days / 365 for d in tab0["fin"]])
    choque = sgn * (p["choques_bp"][k] + p["pendiente_bp"][k] * tf_ / tf_.max())
    defs = meta_m["primas"][(pf, estr)]["strikes"]
    cobs = []
    for (tipo_, K_), (signo, prop) in zip(defs, _signos(estr)):
        cobs.append({"tipo": tipo_, "K": K_ / 100, "signo": signo, "proporcion": prop})
    fl = rt.flujos_exposicion(tab0, choque, spread, posicion, cobs)
    fig = go.Figure([go.Bar(x=fl["periodo"], y=fl["flujo_exposicion"], name="Exposición"),
                     go.Bar(x=fl["periodo"], y=fl["flujo_coberturas"], name="Derivados"),
                     go.Scatter(x=fl["periodo"], y=fl["flujo_neto"], name="Neto", line=dict(color=cm.AZUL, width=3))])
    fig.update_layout(barmode="relative", height=360, template=cm.PLANTILLA_PLOTLY, yaxis_title="MXN por período")
    st.plotly_chart(fig, width="stretch")
    st.dataframe(fl.round(2), hide_index=True, width="stretch")
    cm.guardar("caps", tabla)
    cm.guardar("caps_sens", pd.DataFrame([sens]))
    cm.guardar("escenarios_tasas", mat)
    cm.guardar("caps_vals", {"valor": total, "modelo": modelo, "dv01": sens["DV01_+1pb"], "vega": sens["vega_+1pt"],
                             "origen_vol": origen.lower(), "strike_%": K * 100, "instrumento": instr})
    cm.guardar("exposicion_tasas", {"nocional": N, "posicion": posicion, "referencia": ref, "spread_pb": spread * 10000,
                                    "inicio": ini, "fin": fin, "periodicidad": per, "base": base, "amortizacion": amort,
                                    "condiciones": cond})
    cm.registrar("Cap/Floor", {"N": N, "K": K, "sigma": sigma, "modelo": modelo, "fijacion": fijacion, "curva": curva.fuente},
                 "Σ N·α·DF·Black/Bachelier", {"valor": total, **sens})


def _signos(estr):
    if estr == "Sin cobertura":
        return []
    if "50%" in estr:
        return [(1, 0.5)]
    if estr.startswith("Collar"):
        return [(1, 1.0), (-1, 1.0)]
    return [(1, 1.0)]
