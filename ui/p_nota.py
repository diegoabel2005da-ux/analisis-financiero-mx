"""Página: Nota estructurada por perfil (KRF + capitales + derivados)."""
from __future__ import annotations

import copy
import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import nota as nt, reports_integral as ri, risk, technical as ta
from . import common as cm

PLAZOS_CETES = {28: "SF43936", 91: "SF43939", 182: "SF43942", 364: "SF43945"}


def _tasa_krf(dias: int) -> tuple[float, str]:
    """Rendimiento de Cetes del plazo más cercano al horizonte (Banxico), o valor de respaldo."""
    t = cm.tasas_auto()
    if t is not None:
        tab = t["tabla"]
        plazo = min(PLAZOS_CETES, key=lambda d: abs(d - dias))
        f = tab[tab.serie == PLAZOS_CETES[plazo]]
        if not f.empty:
            fila = f.sort_values("fecha").iloc[-1]
            return float(fila["valor_%"]) / 100, f"Cetes {plazo} días {fila['valor_%']:.2f}% ({fila['fecha'].date()}), Banxico {PLAZOS_CETES[plazo]}"
    return 0.0669, "6.69% del archivo de referencia (sin token de Banxico): edítela o configure BANXICO_TOKEN"


def base_actual() -> dict:
    return copy.deepcopy(st.session_state.get("nota_base", nt.PARAMS_EJEMPLO))


def construir(base: dict, aim_pct=0.15, aim_contrato=None, ancho=0.05):
    """Parámetros completos con el subyacente activo, usando las mismas series que el Excel (fechas comunes con el IPC)."""
    a = cm.activo_actual()
    df, _, _ = cm.datos_activo()
    mk, _, _ = cm.datos_mercado()
    if df.empty or mk.empty:
        return None
    d = ri.datos_desde_df(df, mk)
    if len(d) < 40:
        return None
    S0 = float(d["Close"].iloc[-1])
    sig = ta.volatilidad(d["Close"], 252)
    beta = risk.beta(d["Close"], d["IPC_Close"])["beta"]
    sig_ipc = float(d["IPC_Close"].pct_change().dropna().std(ddof=1) * math.sqrt(252))
    rf_c, _ = cm.rf_corto()
    q, _ = cm.dividendo_auto()
    return nt.preparar(base, a["nombre"].replace("*", "").strip(), S0, sig, beta, rf_c, q, sig_ipc, 100, aim_pct, aim_contrato, ancho)


@st.cache_data(ttl=6 * 3600, show_spinner="Calculando betas…")
def _beta_simbolo(simbolo, inicio, fin):
    d, _, e = cm.historico(simbolo, inicio, fin, simbolo)
    m, _, _ = cm.historico("^MXX", inicio, fin, "IPC")
    if d.empty or m.empty:
        return None
    return risk.beta(d["Close"], m["Close"])["beta"]


def nota_estructurada():
    st.title("Nota estructurada")
    st.markdown('<div class="bloque-aviso">Reparte la inversión por perfil entre <b>renta fija libre de riesgo (KRF)</b>, '
                '<b>mercado de capitales</b> y <b>derivados</b> (futuros con garantía AIM y opciones con primas). '
                'Las estimaciones son teóricas y los escenarios son hipótesis sin probabilidad asignada.</div>',
                unsafe_allow_html=True)
    c1, c2, c3 = st.columns([2, 1, 1])
    c1.image(str(cm.RAIZ / "data" / "img" / "nota_krf_xrisk.png"), width="stretch")
    c2.image(str(cm.RAIZ / "data" / "img" / "nota_perfiles.png"), width="stretch")
    c3.image(str(cm.RAIZ / "data" / "img" / "nota_dificultad.png"), width="stretch")
    base = base_actual()
    st.subheader("1. Inversión y tasa libre de riesgo")
    c = st.columns(4)
    base["inversion"] = c[0].number_input("Inversión (MXN)", value=float(base["inversion"]), step=100_000.0, format="%.0f")
    base["dias"] = int(c[1].number_input("Tiempo (días)", 1, 730, int(base["dias"])))
    rf, txt = _tasa_krf(base["dias"])
    base["rf_anual"] = c[2].number_input("Tasa KRF anual % (simple, ACT/360)", value=float(round(rf * 100, 4)), step=0.05, help=txt) / 100
    base["prm"] = c[3].number_input("Prima de mercado % (CAPM)", value=float(base["prm"] * 100), step=0.25) / 100
    base["fuente_rf"] = txt
    st.caption(f"Tasa KRF: {txt}")

    st.subheader("2. Perfiles")
    tp = pd.DataFrame([{"perfil": pf, "% KRF": base["krf_pct"][pf] * 100, "% capitales (de la porción de riesgo)": base["cap_pct"][pf] * 100,
                        "% futuros (de derivados)": base["fut_pct"][pf] * 100, "estrategia de opciones": base["estrategia"][pf]}
                       for pf in nt.PERFILES])
    ed = st.data_editor(tp, hide_index=True, width="stretch", disabled=["perfil"], key="ed_nota_perf",
                        column_config={"estrategia de opciones": st.column_config.SelectboxColumn(options=list(nt.ESTRATEGIAS_NOTA))})
    for _, r in ed.iterrows():
        pf = r["perfil"]
        base["krf_pct"][pf] = float(r["% KRF"]) / 100
        base["cap_pct"][pf] = float(r["% capitales (de la porción de riesgo)"]) / 100
        base["fut_pct"][pf] = float(r["% futuros (de derivados)"]) / 100
        base["estrategia"][pf] = r["estrategia de opciones"]
    st.caption("Estrategias: " + " · ".join(f"**{k}** = {v}" for k, v in nt.ESTRATEGIAS_NOTA.items()))

    st.subheader("3. Canasta de acciones (mercado de capitales)")
    modo = st.radio("Rendimiento esperado", ["Manual (capturado)", "CAPM automático (β vs IPC)"],
                    index=0 if base.get("modo_rend") == "manual" else 1, horizontal=True)
    base["modo_rend"] = "manual" if modo.startswith("Manual") else "capm"
    tc = pd.DataFrame([{"acción": a_["nombre"], "símbolo Yahoo": a_["simbolo"], "beta": a_["beta"],
                        "rendimiento manual %": a_["rend_manual"] * 100,
                        "peso CONSERVADOR %": a_["pesos"]["CONSERVADOR"] * 100, "peso MODERADO %": a_["pesos"]["MODERADO"] * 100,
                        "peso AGRESIVO %": a_["pesos"]["AGRESIVO"] * 100} for a_ in base["acciones"]])
    edc = st.data_editor(tc, num_rows="dynamic", width="stretch", key="ed_nota_canasta")
    if st.button("Actualizar betas con Yahoo Finance (vs S&P/BMV IPC)"):
        a = cm.activo_actual()
        nuevas = []
        for s in edc["símbolo Yahoo"]:
            b = _beta_simbolo(str(s), a["inicio"], a["fin"]) if isinstance(s, str) and s else None
            nuevas.append(b)
        edc["beta"] = [round(b, 3) if b is not None and not np.isnan(b) else old for b, old in zip(nuevas, edc["beta"])]
        faltan = [s for s, b in zip(edc["símbolo Yahoo"], nuevas) if b is None]
        if faltan:
            st.warning("Sin datos en Yahoo para: " + ", ".join(map(str, faltan)) + ". Se conserva la beta capturada.")
    acciones = []
    for _, r in edc.dropna(subset=["acción"]).iterrows():
        acciones.append({"nombre": str(r["acción"]), "simbolo": str(r.get("símbolo Yahoo") or ""), "beta": float(r["beta"] or 0),
                         "rend_manual": float(r["rendimiento manual %"] or 0) / 100,
                         "pesos": {"CONSERVADOR": float(r["peso CONSERVADOR %"] or 0) / 100, "MODERADO": float(r["peso MODERADO %"] or 0) / 100,
                                   "AGRESIVO": float(r["peso AGRESIVO %"] or 0) / 100}})
    base["acciones"] = acciones
    tot = {pf: sum(a_["pesos"][pf] for a_ in acciones) for pf in nt.PERFILES}
    for pf, t in tot.items():
        if abs(t - 1) > 1e-6 and t > 0:
            st.warning(f"Los pesos del perfil {pf} suman {t*100:.2f}% (deben sumar 100%).")
    st.session_state["nota_base"] = base

    st.subheader("4. Derivados")
    a = cm.activo_actual()
    c = st.columns(3)
    aim_pct = c[0].number_input("AIM como % del nocional (supuesto)", value=15.0, step=1.0,
                                help="Verifique la AIM real con Asigna/MexDer; no se asume como dato oficial.") / 100
    aim_c = c[1].number_input("AIM por contrato capturada (MXN, 0 = usar %)", value=0.0, step=500.0)
    ancho = c[2].number_input("Ancho de alas STG/BTF (% del spot)", value=5.0, step=0.5) / 100
    p = construir(base, aim_pct, aim_c or None, ancho)
    if p is None:
        st.error("Se requieren precios de la emisora seleccionada y del IPC (al menos 40 fechas comunes).")
        return
    st.caption(f"Subyacente de futuros y opciones: **{p['derivados']['nombre']}** (emisora seleccionada en la barra lateral) · "
               f"spot {p['derivados']['S0']:.2f} · σ {p['derivados']['sigma']*100:.2f}% · β {p['derivados']['beta']:.3f}. "
               "Vencimiento de futuros y opciones = horizonte de la nota.")
    r = nt.calcular(p)
    st.session_state["res"]["nota_params"] = p
    st.session_state["res"]["nota"] = r

    st.subheader("5. Resultados (escenario base)")
    rs = r["resumen"].copy()
    m = st.columns(3)
    for i, pf in enumerate(nt.PERFILES):
        f = rs[rs.perfil == pf].iloc[0]
        m[i].metric(pf, f"${f['NE']:,.0f}", f"{f['NE %']*100:.2f}%")
    st.dataframe(rs.round(2), hide_index=True, width="stretch",
                 column_config={"%KRF": st.column_config.NumberColumn(format="percent"),
                                "NE %": st.column_config.NumberColumn(format="percent")})
    t1, t2, t3, t4, t5 = st.tabs(["Diversificación", "Capitales", "Derivados", "Futuros y opciones", "Escenarios"])
    with t1:
        st.dataframe(r["diversificacion"], hide_index=True, width="stretch")
        comp = pd.DataFrame({"KRF": r["resumen"]["KRF $"].values, "Capitales": r["diversificacion"]["$ capitales"].values,
                             "Futuros (AIM)": r["derivados"]["monto futuros"].values,
                             "Opciones (primas)": r["derivados"]["monto opciones"].values}, index=nt.PERFILES)
        fig = go.Figure([go.Bar(y=comp.index, x=comp[c_], name=c_, orientation="h") for c_ in comp])
        fig.update_layout(barmode="stack", height=300, template=cm.PLANTILLA_PLOTLY, title="Composición de la inversión (MXN)")
        st.plotly_chart(fig, width="stretch")
    with t2:
        st.dataframe(r["capitales"], hide_index=True, width="stretch")
        st.caption("Montos = peso × monto de capitales del perfil. Rendimiento " +
                   ("capturado." if base["modo_rend"] == "manual" else "CAPM: (rf + β·PRM)·días/365."))
    with t3:
        st.dataframe(r["derivados"], hide_index=True, width="stretch")
    with t4:
        st.markdown("**Futuros (posición larga)**")
        st.dataframe(r["futuros"], hide_index=True, width="stretch")
        alto = r["futuros"]["nocional / inversión"].max()
        if alto > 1:
            cm.etiqueta(f"Apalancamiento: el nocional de futuros llega a {alto:.1f}× la inversión", "riesgo")
        st.markdown("**Opciones**")
        st.dataframe(r["opciones"], hide_index=True, width="stretch")
        st.caption("Primas teóricas (BSM). Las opciones son sobre el subyacente seleccionado: un FLOOR protege la canasta sólo "
                   "en la medida en que ésta se mueva como ese subyacente.")
    with t5:
        e = r["escenarios"]
        fig = go.Figure([go.Bar(x=g["escenario"], y=g["NE"], name=pf) for pf, g in e.groupby("perfil", sort=False)])
        fig.update_layout(barmode="group", height=420, template=cm.PLANTILLA_PLOTLY, yaxis_title="NE (MXN)",
                          title="Resultado neto por escenario y perfil")
        st.plotly_chart(fig, width="stretch")
        st.dataframe(e.round(2), hide_index=True, width="stretch")
        st.caption("S_h = S0·e^(μ + z·σ·√T) con μ = CAPM del subyacente; acciones: r_i = rendimiento_i + β_i·z·σ_IPC·√T. "
                   "z = 0 es el escenario base.")
    cm.registrar("Nota estructurada", {"inversion": base["inversion"], "dias": base["dias"], "rf": base["rf_anual"]},
                 "KRF + capitales + derivados", {pf: float(rs.loc[rs.perfil == pf, "NE"].iloc[0]) for pf in nt.PERFILES})
    st.info("La hoja NOTA ESTRUCTURADA se incluye en el Excel INTEGRAL (sección 15. Reportes) con estos mismos parámetros.")
