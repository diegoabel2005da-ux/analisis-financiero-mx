"""Páginas: Constructor de estrategias, Coberturas y Perfiles y escenarios."""
from __future__ import annotations

import copy
import datetime as dt

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import strategies as stg, scenarios as sc, technical as ta
from . import common as cm


def _base():
    df, meta, err = cm.datos_activo()
    if err or df.empty:
        cm.requiere_datos(df, meta, err)
        return None
    return float(df["Close"].iloc[-1]), ta.volatilidad(df["Close"], 252), df


def _mercado(key):
    c = st.columns(5)
    rf, txt_r = cm.rf_corto()
    qd, txt_q = cm.dividendo_auto()
    hoy = cm.dat.ahora_mx().date()
    prox = cm.vencimientos(1)[0]
    r = c[0].number_input("Tasa libre de riesgo % (cont.)", value=float(round(rf * 100, 4)), step=0.1, key=f"r_{key}", help=txt_r) / 100
    q = c[1].number_input("Dividendo % (cont.)", value=float(round(qd * 100, 4)), step=0.1, key=f"q_{key}", help=txt_q) / 100
    dias = c[2].number_input("Días al vencimiento", 1, 1100, max((prox - hoy).days, 1), key=f"d_{key}",
                             help=f"Predeterminado: próximo vencimiento MexDer {prox} (tercer viernes, ciclo trimestral)")
    mo = c[3].number_input("Multiplicador opciones", value=100.0, key=f"mo_{key}")
    mf = c[4].number_input("Multiplicador futuros", value=100.0, key=f"mf_{key}")
    st.caption(f"Tasa: {txt_r} · Dividendo: {txt_q} · Vencimiento predeterminado: {prox}")
    return r, q, dias / 365, mo, mf


# =========================================================================== 12
def estrategias():
    st.title("Constructor de estrategias")
    b = _base()
    if not b:
        return
    S0, vol, df = b
    st.caption(f"Spot de referencia: último cierre del proveedor {S0:.2f} · volatilidad histórica {vol*100:.2f}% (editable).")
    r, q, T, mo, mf = _mercado("e")
    c = st.columns(4)
    plantilla = c[0].selectbox("Plantilla", ["Manual (vacía)"] + stg.PLANTILLAS)
    sig = c[1].number_input("Volatilidad % para primas teóricas", value=float(round(vol * 100, 2)), key="sig_e") / 100
    contratos = c[2].number_input("Contratos", 1, 10000, 1)
    ancho = c[3].number_input("Ancho de alas / strangle %", value=5.0) / 100
    c = st.columns(3)
    kp = c[0].number_input("Strike put (% spot) — collar/strangle/protective", value=95.0) / 100
    kc = c[1].number_input("Strike call (% spot) — collar/strangle/covered", value=105.0) / 100
    stop = c[2].number_input("Stop hipotético (% desde F0)", value=5.0) / 100
    if plantilla == "Manual (vacía)":
        legs = [stg.Leg("call", 1, mo, round(S0, 2), T, stg.bsm(S0, S0, T, r, q, sig, "call"))]
    else:
        legs = stg.construir(plantilla, S0, T, r, q, sig, mo, mf, contratos,
                             params={"k_put": kp, "k_call": kc, "ancho": ancho, "stop_pct": stop})
    tabla = pd.DataFrame([l.to_dict() for l in legs])
    st.markdown("**Legs (edite libremente; agregue filas para combinar instrumentos)**")
    st.caption("cantidad > 0 = compra, < 0 = venta. Primas por unidad. Cambie 'origen_prima' a observada al capturar una "
               "prima del boletín de MexDer.")
    ed = st.data_editor(tabla, num_rows="dynamic", width="stretch", key=f"legs_{plantilla}",
                        column_config={"instrumento": st.column_config.SelectboxColumn(options=["accion", "call", "put", "futuro"]),
                                       "origen_prima": st.column_config.SelectboxColumn(options=["teórica (BSM)", "observada (MexDer)"])})
    legs = []
    for _, rw in ed.dropna(subset=["instrumento", "cantidad"]).iterrows():
        d = {k: (None if (isinstance(v, float) and np.isnan(v)) else v) for k, v in rw.to_dict().items()}
        d["multiplicador"] = d.get("multiplicador") or 1.0
        d["deslizamiento_pct"] = d.get("deslizamiento_pct") or 0.0
        d["comision"] = d.get("comision") or 0.0
        if d["instrumento"] == "accion" and not d.get("precio_inicial"):
            d["precio_inicial"] = S0
        if d["instrumento"] == "futuro" and not d.get("precio_inicial"):
            d["precio_inicial"] = stg.precio_teorico(S0, r, q, d.get("vencimiento_años") or T)
        legs.append(stg.Leg(**d))
    if not legs:
        st.info("Agregue al menos un leg.")
        return
    avisos = stg.validar_legs(legs, S0)
    errores = [a for a in avisos if "inválid" in a or "cero" in a]
    for a in avisos:
        (st.error if a in errores else st.warning)(a)
    if errores:
        return
    funcion = stg.FUNCION_ECONOMICA.get(plantilla, "Clasificación manual: revise la función económica")
    if any(l.instrumento == "accion" for l in legs) and plantilla == "Long Put":
        funcion = "Cobertura directa"
    cm.etiqueta(f"Función económica: {funcion}", "info")
    venc_min = min([l.vencimiento_años for l in legs if l.vencimiento_años] or [T])
    h_d = st.slider("Horizonte de evaluación (días)", 0, int(venc_min * 365), int(venc_min * 365))
    h = h_d / 365
    rango = (S0 * 0.6, S0 * 1.4)
    cv_venc = stg.curva_pnl(legs, S0, rango, venc_min, r, q, sig)
    cv_h = stg.curva_pnl(legs, S0, rango, h, r, q, sig)
    fig = go.Figure([go.Scatter(x=cv_venc["S"], y=cv_venc["pnl"], name="Al vencimiento"),
                     go.Scatter(x=cv_h["S"], y=cv_h["pnl"], name=f"Revaluación a {h_d} días", line=dict(dash="dash"))])
    fig.add_hline(0, line_color=cm.GRIS)
    fig.add_vline(S0, line_dash="dot", annotation_text="Spot")
    fig.update_layout(height=430, template=cm.PLANTILLA_PLOTLY, xaxis_title="Precio del subyacente", yaxis_title="P&L (MXN)")
    st.plotly_chart(fig, width="stretch")
    be = stg.puntos_equilibrio(cv_venc)
    costo = stg.costo_inicial(legs)
    m = st.columns(4)
    m[0].metric("Flujo inicial (primas y comisiones)", f"{costo:,.2f}")
    m[1].metric("Puntos de equilibrio (vencimiento)", ", ".join(f"{x:.2f}" for x in be) or "—")
    m[2].metric("Máximo en el rango", f"{cv_venc['pnl'].max():,.0f}")
    m[3].metric("Mínimo en el rango", f"{cv_venc['pnl'].min():,.0f}")
    st.caption("Máximos/mínimos dentro del rango ±40% del spot; los extremos pueden ser ilimitados fuera del rango. "
               "Garantías de futuros y ventas de opciones no se incluyen en el flujo inicial (son depósitos).")
    teo = [l for l in legs if l.instrumento in ("call", "put") and str(l.origen_prima).startswith("teór")]
    if teo:
        cm.etiqueta(f"{len(teo)} leg(s) con prima TEÓRICA", "teorico")
    cm.guardar("estrategias", pd.DataFrame([{**l.to_dict(), "estrategia": plantilla, "función": funcion} for l in legs]))


# =========================================================================== 13
def coberturas():
    st.title("Motor de evaluación de coberturas")
    b = _base()
    if not b:
        return
    S0, vol, df = b
    st.subheader("1. Identificación de la exposición")
    c = st.columns(4)
    tipo = c[0].selectbox("Tipo de posición", ["Accionaria existente declarada", "Accionaria hipotética"])
    direccion = c[1].selectbox("Dirección", ["larga", "corta"])
    acciones = c[2].number_input("Número de acciones", value=10_000.0, step=100.0)
    presupuesto = c[3].number_input("Presupuesto máximo de cobertura (MXN, 0 = sin límite)", value=0.0)
    c = st.columns(3)
    objetivo = c[0].selectbox("Objetivo de protección", ["Limitar pérdidas grandes", "Reducir volatilidad", "Generar ingreso"])
    restric = c[1].text_input("Restricciones", "Sin ventas descubiertas")
    horiz_d = c[2].number_input("Horizonte (días)", 1, 730, 91)
    st.write(f"Magnitud: **{acciones*S0:,.0f} MXN** · Moneda: MXN · Riesgo principal: "
             f"**{'caída del precio' if direccion == 'larga' else 'alza del precio'}** · Horizonte: {horiz_d} días")
    r, q, T, mo, mf = _mercado("c")
    sig = st.number_input("Volatilidad % (predet.: histórica)", value=float(round(vol * 100, 2)), key="sig_c") / 100
    h = horiz_d / 365
    perfiles = st.session_state.get("perfiles_acc", sc.PERFILES_ACCIONES)
    st.subheader("2. Estrategias compatibles")
    compat = sc.estrategias_compatibles(direccion)
    st.dataframe(pd.DataFrame(compat.items(), columns=["estrategia", "función económica"]), hide_index=True, width="stretch")
    pf_n = st.selectbox("Parámetros del perfil para costos", list(perfiles))
    pf = perfiles[pf_n]
    filas = []
    for e, f in compat.items():
        legs = sc.legs_cobertura(e, direccion, acciones, S0, T, r, q, sig, pf, mo, mf)
        costo = stg.costo_inicial(legs)
        n_fut = sum(abs(l.cantidad) for l in legs if l.instrumento == "futuro")
        cub = sum(abs(l.cantidad) * l.multiplicador for l in legs if l.instrumento in ("put", "call", "futuro") and
                  ((direccion == "larga" and ((l.instrumento == "put" and l.cantidad > 0) or (l.instrumento == "futuro" and l.cantidad < 0))) or
                   (direccion == "corta" and ((l.instrumento == "call" and l.cantidad > 0) or (l.instrumento == "futuro" and l.cantidad > 0)))))
        cub = min(cub, acciones) if "volatilidad" not in f else 0
        filas.append({"estrategia": e, "función": f, "costo_inicial_primas": costo,
                      "exposición_cubierta_%": cub / acciones * 100, "exposición_residual_%": 100 - cub / acciones * 100,
                      "requiere_garantías": "Sí" if n_fut or any(l.cantidad < 0 and l.instrumento in ("call", "put") for l in legs) else "No",
                      "contratos_futuros": n_fut,
                      "dentro_de_presupuesto": "N/A" if presupuesto == 0 else ("Sí" if -costo <= presupuesto else "No"),
                      "riesgo_vencimiento": "Desfase si el horizonte ≠ vencimiento" if abs(h - T) > 1e-9 else "Alineado"})
    st.dataframe(pd.DataFrame(filas).round(2), hide_index=True, width="stretch")
    st.subheader("3. Matriz comparativa (5 escenarios del perfil seleccionado)")
    m = sc.matriz_acciones(S0, acciones, direccion, h, T, r, q, sig, {pf_n: pf}, None, mo, mf)
    comp = sc.resumen_comparativo(m)
    crit = st.selectbox("Ordenar por", ["peor_resultado", "costo_inicial", "resultado_base", "rango_resultados", "mejor_resultado"])
    asc = crit in ("rango_resultados",)
    comp = comp.sort_values(crit, ascending=asc)
    st.dataframe(comp.round(0), hide_index=True, width="stretch")
    st.caption("Orden por un criterio cuantitativo explícito. No se usan puntuaciones opacas ni generadas por IA. "
               "Las estrategias de volatilidad no se tratan como coberturas.")
    piv = m.pivot_table(index="estrategia", columns="escenario", values="resultado_combinado", aggfunc="first")
    fig = go.Figure(go.Heatmap(z=piv.values, x=piv.columns, y=piv.index, colorscale="RdYlGn", text=np.round(piv.values / 1000, 1),
                               texttemplate="%{text}k"))
    fig.update_layout(height=380, template=cm.PLANTILLA_PLOTLY, title="Resultado combinado (miles de MXN)")
    st.plotly_chart(fig, width="stretch")
    cm.guardar("coberturas", pd.DataFrame(filas))
    cm.guardar("exposicion_acc", {"tipo": tipo, "direccion": direccion, "acciones": acciones, "S0": S0, "objetivo": objetivo,
                                  "restricciones": restric, "presupuesto": presupuesto, "horizonte_dias": horiz_d})


# =========================================================================== 14
def perfiles_escenarios():
    st.title("Perfiles de riesgo y motor de escenarios combinados")
    st.markdown("Cada combinación **perfil × estrategia** se evalúa en **cinco escenarios** como mínimo. Dentro de un perfil, "
                "el mismo choque de mercado se aplica a todas las estrategias. Los choques son hipótesis, no predicciones; no "
                "se asignan probabilidades.")
    b = _base()
    if not b:
        return
    S0, vol, df = b
    t1, t2, t3 = st.tabs(["Acciones", "Tasas (caps y floors)", "Versiones guardadas"])
    with t1:
        st.subheader("Perfiles (editables)")
        pa = copy.deepcopy(st.session_state.get("perfiles_acc", sc.PERFILES_ACCIONES))
        filas = []
        for n, p in pa.items():
            filas.append({"perfil": n, "k_put": p["k_put"], "k_call": p["k_call"], "cobertura_futuros": p["cobertura_futuros"],
                          **{f"z_{i+1}": p["z"][i] for i in range(5)}, **{f"vol_pts_{i+1}": p["vol_pts"][i] for i in range(5)},
                          "descripcion": p["descripcion"]})
        ed = st.data_editor(pd.DataFrame(filas), hide_index=True, width="stretch", num_rows="dynamic", key="ed_perf_acc")
        st.caption("k_put/k_call: strike como fracción del spot · cobertura_futuros: proporción cubierta · z_i: choque en múltiplos "
                   "de σ·√h (negativo = adverso para la exposición) · vol_pts_i: cambio de volatilidad en puntos. Escenarios: "
                   + " | ".join(sc.ESCENARIOS))
        nuevos = {}
        for _, rw in ed.dropna(subset=["perfil"]).iterrows():
            nuevos[rw["perfil"]] = {"descripcion": rw.get("descripcion", ""), "k_put": float(rw["k_put"]), "k_call": float(rw["k_call"]),
                                    "cobertura_futuros": float(rw["cobertura_futuros"]),
                                    "z": [float(rw[f"z_{i+1}"]) for i in range(5)], "vol_pts": [float(rw[f"vol_pts_{i+1}"]) for i in range(5)]}
        st.session_state["perfiles_acc"] = nuevos
        c = st.columns(3)
        direccion = c[0].selectbox("Exposición", ["larga", "corta"], key="dir_pe")
        acciones = c[1].number_input("Acciones", value=10_000.0, key="acc_pe")
        horiz = c[2].number_input("Horizonte (días)", 1, 730, 91, key="h_pe")
        r, q, T, mo, mf = _mercado("pe")
        sig = st.number_input("Volatilidad %", value=float(round(vol * 100, 2)), key="sig_pe") / 100
        compat = list(sc.estrategias_compatibles(direccion))
        sel = st.multiselect("Estrategias", compat, default=compat)
        if not sel or not nuevos:
            return
        m = sc.matriz_acciones(S0, acciones, direccion, horiz / 365, T, r, q, sig, nuevos, sel, mo, mf)
        st.success(f"{len(m)} evaluaciones = {len(nuevos)} perfiles × {len(sel)} estrategias × 5 escenarios")
        vista = st.radio("Visualización", ["Matriz perfil × estrategia × escenario", "Comparador lado a lado", "Tabla completa"], horizontal=True)
        if vista.startswith("Matriz"):
            for pn in nuevos:
                piv = m[m.perfil == pn].pivot_table(index="estrategia", columns="escenario", values="resultado_combinado", aggfunc="first")
                fig = go.Figure(go.Heatmap(z=piv.values, x=piv.columns, y=piv.index, colorscale="RdYlGn",
                                           text=np.round(piv.values / 1000, 1), texttemplate="%{text}k"))
                fig.update_layout(height=320, template=cm.PLANTILLA_PLOTLY, title=f"{pn} — resultado combinado (miles MXN)",
                                  margin=dict(l=10, r=10, t=40, b=10))
                st.plotly_chart(fig, width="stretch")
        elif vista.startswith("Comparador"):
            ests = st.multiselect("Estrategias a comparar", sel, default=sel[:3])
            pn = st.selectbox("Perfil", list(nuevos), key="pn_cmp")
            sub = m[(m.perfil == pn) & (m.estrategia.isin(ests))]
            fig = go.Figure([go.Bar(x=g["escenario"], y=g["resultado_combinado"], name=e) for e, g in sub.groupby("estrategia", sort=False)])
            fig.update_layout(barmode="group", height=420, template=cm.PLANTILLA_PLOTLY, yaxis_title="MXN")
            st.plotly_chart(fig, width="stretch")
            st.dataframe(sub.pivot_table(index="escenario", columns="estrategia",
                                         values=["resultado_combinado", "protección_conseguida"], aggfunc="first").round(0), width="stretch")
        else:
            st.dataframe(m.round(2), hide_index=True, width="stretch")
        cm.guardar("escenarios", m)
        cm.guardar("comparativas", sc.resumen_comparativo(m))
        cm.guardar("perfiles", ed)
        resumen = {}
        for pn in nuevos:
            e1 = m[(m.perfil == pn) & (m.escenario == sc.ESCENARIOS[0])]
            cand = e1[~e1["función_económica"].str.contains("volatilidad")].sort_values("resultado_combinado", ascending=False)
            if len(cand):
                resumen[pn] = {"estrategia": cand.iloc[0]["estrategia"], "resultado": float(cand.iloc[0]["resultado_combinado"]),
                               "sin_cobertura": float(e1[e1.estrategia == "Sin cobertura"]["resultado_combinado"].iloc[0])
                               if (e1.estrategia == "Sin cobertura").any() else np.nan}
        cm.guardar("escenarios_resumen", resumen)
        cm.registrar("Escenarios acciones", {"perfiles": nuevos, "estrategias": sel, "S0": S0, "sigma": sig, "h": horiz},
                     "S_h=S0·exp(s·z·σ·√h)", {"evaluaciones": len(m)}, df)
        nombre = st.text_input("Nombre de la versión", f"Escenarios {dt.datetime.now():%Y-%m-%d %H:%M}")
        if st.button("Guardar versión de escenarios"):
            st.session_state["versiones_escenarios"].append({"nombre": nombre, "tipo": "acciones", "perfiles": nuevos,
                                                             "parametros": {"S0": S0, "acciones": acciones, "direccion": direccion,
                                                                            "horizonte": horiz, "T": T, "r": r, "q": q, "sigma": sig,
                                                                            "estrategias": sel}, "resultados": m})
            st.success("Versión guardada (reproducible con los mismos parámetros).")
    with t2:
        st.subheader("Perfiles de tasas (editables)")
        pt_ = copy.deepcopy(st.session_state.get("perfiles_tasas", sc.PERFILES_TASAS))
        filas = [{"perfil": n, "offset_strike_bp": p["offset_strike_bp"], **{f"choque_bp_{i+1}": p["choques_bp"][i] for i in range(5)},
                  **{f"pendiente_bp_{i+1}": p["pendiente_bp"][i] for i in range(5)}, "descripcion": p["descripcion"]} for n, p in pt_.items()]
        ed2 = st.data_editor(pd.DataFrame(filas), hide_index=True, width="stretch", num_rows="dynamic", key="ed_perf_tasas")
        nv = {}
        for _, rw in ed2.dropna(subset=["perfil"]).iterrows():
            nv[rw["perfil"]] = {"descripcion": rw.get("descripcion", ""), "offset_strike_bp": float(rw["offset_strike_bp"]),
                                "choques_bp": [float(rw[f"choque_bp_{i+1}"]) for i in range(5)],
                                "pendiente_bp": [float(rw[f"pendiente_bp_{i+1}"]) for i in range(5)]}
        st.session_state["perfiles_tasas"] = nv
        st.caption("Choques en pb (positivo = adverso para un pasivo; para un activo el motor invierte el signo). Pendiente: pb "
                   "adicionales al último plazo, lineal en el tiempo. Los resultados se calculan en 'Caps y floors'.")
        mt = st.session_state["res"].get("escenarios_tasas")
        if isinstance(mt, pd.DataFrame):
            st.dataframe(mt.round(2), hide_index=True, width="stretch")
        else:
            st.info("Ejecute 'Caps y floors' para generar la matriz de tasas con estos perfiles.")
    with t3:
        v = st.session_state["versiones_escenarios"]
        if not v:
            st.info("No hay versiones guardadas.")
        for i, x in enumerate(v):
            with st.expander(f"{i+1}. {x['nombre']} ({x['tipo']})"):
                st.json(x["parametros"])
                st.dataframe(x["resultados"].round(2), hide_index=True, width="stretch")
