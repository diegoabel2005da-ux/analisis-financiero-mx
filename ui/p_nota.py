"""Página: Nota estructurada — perfilador, renta fija, capitales MX/EE.UU., futuros multiactivo, opciones, escenarios,
ficha de condiciones y reporte ejecutivo."""
from __future__ import annotations

import copy
import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import nota as nt, reports_integral as ri, risk, technical as ta, futuros_multi as fm, perfil as pfm
from core import renta_fija as rfj, reporte_nota as rn
from . import common as cm

# Tasas de respaldo con fuente y fecha (se usan sólo si Banxico no responde o no hay token)
RESPALDO = {
    "cetes": ({28: 0.0618}, "Cetes 28 días 6.18%: subasta del 21/07/2026 (Monex, con datos de Banxico)"),
    "bono_m": ({5: 0.0863, 10: 0.0954, 20: 0.0959}, "Bono M 5a 8.63% (subasta 10/03/2026, Monex); 10a 9.54% (Trading Economics, 28/09/2026); "
                                                       "20a 9.59% (subasta 21/07/2026, Monex)"),
    "udibono_real": ({20: 0.0470}, "Udibono 20a 4.70% real (subasta 21/07/2026, Monex)"),
    "bondes_f_sobretasa": (0.0023, "Bondes F sobretasa 0.23% (subasta 21/07/2026, Monex)"),
    "udi": (8.796118, "UDI 8.796118 pesos (21/07/2026, Monex con datos de Banxico)"),
    "inflacion": (0.03, "3%: meta de inflación de Banxico (supuesto del analista)"),
}
PLAZOS = {"SF43936": 28, "SF43939": 91, "SF43942": 182, "SF43945": 364}


def _ss():
    s = st.session_state
    s.setdefault("nota_base", copy.deepcopy(nt.PARAMS_EJEMPLO))
    s.setdefault("nota_resp", {k: 1 for k, _, _ in pfm.PREGUNTAS})
    s.setdefault("nota_margenes", {})
    return s


def tasas_renta_fija():
    """Tasas para el comparador: Banxico (automático) o respaldo con fuente."""
    t = cm.tasas_auto()
    fuentes = {}
    tasas = {"cetes": dict(RESPALDO["cetes"][0]), "bono_m": dict(RESPALDO["bono_m"][0]),
             "udibono_real": dict(RESPALDO["udibono_real"][0]), "bondes_f_sobretasa": RESPALDO["bondes_f_sobretasa"][0]}
    fuentes["CETES"] = RESPALDO["cetes"][1]
    fuentes["BONOS M"] = RESPALDO["bono_m"][1]
    fuentes["UDIBONOS"] = RESPALDO["udibono_real"][1]
    fuentes["BONDES F"] = RESPALDO["bondes_f_sobretasa"][1]
    tf = None
    if t is not None:
        tab = t["tabla"]
        c = {}
        for s_, d in PLAZOS.items():
            f = tab[tab.serie == s_]
            if not f.empty:
                c[d] = float(f.sort_values("fecha").iloc[-1]["valor_%"]) / 100
        if c:
            tasas["cetes"] = c
            fuentes["CETES"] = "Banxico SIE (SF43936, SF43939, SF43942, SF43945), " + str(tab["fecha"].max().date())
        f = tab[tab.serie == "SF331451"]
        if not f.empty:
            tf = float(f.sort_values("fecha").iloc[-1]["valor_%"]) / 100
        if "rf_largo" in t and "Bono M" in t.get("rf_largo_txt", ""):
            tasas["bono_m"][10] = t["rf_largo"]
            fuentes["BONOS M"] = t["rf_largo_txt"] + "; otros plazos: " + RESPALDO["bono_m"][1]
    if tf is None:
        tf = cm.rf_corto()[0]
        fuentes["BONDES F"] += "; TIIE de Fondeo aproximada con la tasa libre de riesgo disponible"
    else:
        fuentes["BONDES F"] += "; TIIE de Fondeo: Banxico SF331451"
    tasas["tiie_fondeo"] = tf
    return tasas, fuentes


@st.cache_data(ttl=3600, show_spinner="Consultando precios de futuros…")
def _precios_futuros(inicio, fin):
    precios, vols, fechas = {}, {}, {}
    fx, _, _ = cm.historico("MXN=X", inicio, fin, "USD/MXN")
    usdmxn = float(fx["Close"].iloc[-1]) if not fx.empty else np.nan
    for c in fm.CATALOGO:
        d, _, _ = cm.historico(c["yahoo"], inicio, fin, c["clave"])
        if c["clave"] == "6M" and d.empty and not fx.empty:
            d = (1 / fx[["Close"]]).copy()  # aproximación: inverso del USD/MXN
        if not d.empty:
            precios[c["clave"]] = float(d["Close"].iloc[-1])
            vols[c["clave"]] = ta.volatilidad(d["Close"], 252)
            fechas[c["clave"]] = str(d.index.max().date())
    return precios, vols, fechas, usdmxn


@st.cache_data(ttl=3600, show_spinner="Analizando la canasta…")
def _datos_canasta(simbolos: tuple, inicio, fin):
    m, _, _ = cm.historico("^MXX", inicio, fin, "IPC")
    sp, _, _ = cm.historico("^GSPC", inicio, fin, "S&P 500")
    fx, _, _ = cm.historico("MXN=X", inicio, fin, "USD/MXN")
    filas, series = [], {}
    for s in simbolos:
        d, _, _ = cm.historico(s, inicio, fin, s)
        if d.empty:
            filas.append({"símbolo": s, "estado": "Sin datos en Yahoo"})
            continue
        c = d["Close"]
        usd = not s.upper().endswith(".MX")
        px = float(c.iloc[-1])
        filas.append({"símbolo": s, "moneda": "USD" if usd else "MXN", "precio": px,
                      "precio MXN": px * float(fx["Close"].iloc[-1]) if usd and not fx.empty else px,
                      "fecha": str(c.index.max().date()), "rend. período": c.iloc[-1] / c.iloc[0] - 1,
                      "vol. anual": ta.volatilidad(c, 252),
                      "beta vs IPC": risk.beta(c, m["Close"])["beta"] if not m.empty else np.nan,
                      "beta vs S&P 500": risk.beta(c, sp["Close"])["beta"] if (usd and not sp.empty) else np.nan,
                      "máx. drawdown": risk.max_drawdown(c)["max_drawdown"], "estado": "OK"})
        series[s] = c
    corr = risk.correlaciones(series) if len(series) > 1 else pd.DataFrame()
    return pd.DataFrame(filas), corr


def construir(base: dict, respuestas: dict | None = None, margenes: dict | None = None, aim_pct=None, ancho=0.05):
    """Parámetros completos de la nota con los datos de la sesión (mismo cálculo que usa el Excel)."""
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
    tasas, fuentes = tasas_renta_fija()
    precios, vols, fechas, usdmxn = _precios_futuros(a["inicio"], a["fin"])
    if not precios or np.isnan(usdmxn):
        cat = fm.preparar_catalogo({}, {}, 18.0, margenes)  # sin precios: ningún contrato asignable
    else:
        if "CL" in precios:
            precios.setdefault("MCL", precios["CL"]); vols.setdefault("MCL", vols["CL"])
        cat = fm.preparar_catalogo(precios, vols, usdmxn, margenes)
    excl = set(base.get("futuros_excluidos") or [])
    if excl:
        cat.loc[cat["clave"].isin(excl), "asignable"] = False  # contratos que el usuario decidió no usar
    respuestas = respuestas or st.session_state.get("nota_resp")
    asg = pfm.asignacion(respuestas) if respuestas else None
    b = copy.deepcopy(base)
    if asg:
        b["perdida_tolerada"] = asg["perdida_tolerada"]
    p = nt.preparar(b, a["nombre"].replace("*", "").strip(), S0, sig, beta, rf_c, q, sig_ipc, 100, ancho,
                    renta_fija={"tasas": tasas, "inflacion": b.get("inflacion", RESPALDO["inflacion"][0]), "udi": b.get("udi", RESPALDO["udi"][0])},
                    futuros_cat=cat, personalizado=asg)
    p["respuestas"] = respuestas
    p["usdmxn"] = usdmxn if not np.isnan(usdmxn) else 18.0
    p["fuentes"] = {**fuentes, "inflacion": RESPALDO["inflacion"][1], "udi": RESPALDO["udi"][1]}
    p["fechas_futuros"] = fechas
    p["rf_anual"] = tasas["cetes"].get(28, rf_c)
    p["fuente_rf"] = "CAPM con Cetes 28 días: " + fuentes["CETES"]
    p["tope_primas_pct"] = float(b.get("tope_primas_pct") or 0.0)
    p["fecha_valuacion"] = d.index.max().date()
    simbolos = tuple(x["simbolo"] for x in b["acciones"] if x.get("simbolo"))
    if simbolos:
        datos_c, corr = _datos_canasta(simbolos, a["inicio"], a["fin"])
        p["canasta_datos"] = datos_c.to_dict("records") if not datos_c.empty else []
        p["canasta_corr"] = corr
    return p


def nota_estructurada():
    s = _ss()
    st.title("Nota estructurada")
    st.markdown('<div class="bloque-aviso">El cliente responde el perfilador; la plataforma propone la nota: <b>renta fija</b> elegida '
                'automáticamente, <b>acciones mexicanas y estadounidenses</b>, <b>futuros</b> diversificados por margen y <b>opciones</b>. '
                'Todo se recalcula al cambiar cualquier variable. Las estimaciones son teóricas y los escenarios no tienen probabilidad asignada.</div>',
                unsafe_allow_html=True)
    base = s["nota_base"]
    tabs = st.tabs(["1. Perfil", "2. Renta fija", "3. Capitales", "4. Futuros", "5. Opciones", "6. Asignación por perfil",
                    "7. Resultados y ficha", "8. Reporte ejecutivo"])
    # ------------------------------------------------------------------ 1
    with tabs[0]:
        c1, c2 = st.columns([1, 1])
        c1.image(str(cm.RAIZ / "data" / "img" / "nota_krf_xrisk.png"), width="stretch")
        c2.image(str(cm.RAIZ / "data" / "img" / "nota_perfiles.png"), width=160)
        st.subheader("Cuestionario del inversionista")
        resp = {}
        cols = st.columns(2)
        for i, (k, lab, ops) in enumerate(pfm.PREGUNTAS):
            resp[k] = ops.index(cols[i % 2].selectbox(lab, ops, index=int(s["nota_resp"].get(k, 1)), key=f"q_{k}"))
        s["nota_resp"] = resp
        asg = pfm.asignacion(resp)
        c = st.columns(4)
        base["inversion"] = c[0].number_input("Monto a invertir (MXN)", value=float(base["inversion"]), step=100_000.0, format="%.0f")
        base["dias"] = int(c[1].number_input("Horizonte (días)", 7, 1825, int(base["dias"])))
        base["objetivo_rend"] = c[2].number_input("Objetivo de rendimiento anual %", value=float(base.get("objetivo_rend", 0.03) * 100), step=0.5) / 100
        c[3].metric("Pérdida máxima tolerada", f"{asg['perdida_tolerada']*100:.0f}%")
        m = st.columns(5)
        m[0].metric("Puntaje de riesgo", f"{asg['puntaje']*100:.0f}/100")
        m[1].metric("Perfil de referencia", asg["perfil_referencia"])
        m[2].metric("Renta fija sugerida", f"{asg['krf_pct']*100:.1f}%")
        m[3].metric("Capitales (de la porción de riesgo)", f"{asg['cap_pct']*100:.1f}%")
        m[4].metric("Estrategia de opciones", asg["estrategia"])
        st.caption("Reglas del perfilador: puntaje = puntos/30; KRF = 0.80 − 0.65·s (15%–85%); capitales = 0.75 − 0.50·s; futuros = 0.30 + 0.35·s "
                   "(0 si no tiene experiencia con derivados); stop-loss = 3% + 7%·s; estrategia según su expectativa de mercado. "
                   "La propuesta PERSONALIZADO se compara con los tres perfiles de referencia.")
    p = construir(base, resp, s["nota_margenes"], ancho=st.session_state.get("nota_ancho", 0.05))
    if p is None:
        st.error("Se requieren precios de la emisora seleccionada y del IPC (al menos 40 fechas comunes). Elija una emisora en la barra lateral.")
        return
    # ------------------------------------------------------------------ 2
    with tabs[1]:
        st.subheader("Comparador de instrumentos gubernamentales")
        c = st.columns(3)
        base["inflacion"] = c[0].number_input("Inflación esperada anual %", value=float(base.get("inflacion", 0.03) * 100), step=0.1) / 100
        base["udi"] = c[1].number_input("Valor de la UDI (pesos)", value=float(base.get("udi", RESPALDO["udi"][0])), format="%.6f")
        c[2].caption(f"Inflación: {RESPALDO['inflacion'][1]} · UDI: {RESPALDO['udi'][1]}")
        tabla = p["renta_fija_tabla"]
        mostrar = tabla[["instrumento", "plazo_días", "precio_título", "tasa_anual", "rend_horizonte", "duración_al_vender", "pérdida_+100pb",
                         "riesgo_crédito", "riesgo_mercado", "riesgo_inflación", "riesgo_reinversión", "riesgo_liquidez", "pagos"]].copy()
        st.dataframe(mostrar, hide_index=True, width="stretch",
                     column_config={c_: st.column_config.NumberColumn(format="percent") for c_ in ["tasa_anual", "rend_horizonte", "pérdida_+100pb"]})
        st.caption("Riesgos: 1 = bajo, 2 = medio, 3 = alto. Fuentes de tasas: " + " · ".join(f"{k}: {v}" for k, v in p["fuentes"].items()
                                                                                             if k in ("CETES", "BONOS M", "BONDES F", "UDIBONOS")))
        st.markdown("**Selección automática por perfil**")
        sel = pd.DataFrame([{"perfil": pf, "instrumento": v["instrumento"], "rend. al horizonte": v["rend_horizonte"], "duración": v["duración"],
                             "justificación": v["justificación"]} for pf, v in p["renta_fija"].items()])
        st.dataframe(sel, hide_index=True, width="stretch", column_config={"rend. al horizonte": st.column_config.NumberColumn(format="percent")})
        st.markdown("**Elegir otro instrumento (opcional)**")
        opciones = ["Automático"] + list(tabla["instrumento"])
        man = dict(base.get("rf_manual") or {})
        cols_m = st.columns(len(p["perfiles"]))
        for i, pf in enumerate(p["perfiles"]):
            v = cols_m[i].selectbox(pf, opciones, index=opciones.index(man[pf]) if man.get(pf) in opciones else 0, key=f"rfm_{pf}")
            if v == "Automático":
                man.pop(pf, None)
            else:
                man[pf] = v
        if man != (base.get("rf_manual") or {}):
            base["rf_manual"] = man
            st.rerun()
        st.markdown("**Características y riesgos**")
        st.dataframe(pd.DataFrame([{"instrumento": k, **v, "riesgo de mercado": rfj.RIESGOS[k]["mercado"][1],
                                    "riesgo de inflación": rfj.RIESGOS[k]["inflación"][1], "riesgo de reinversión": rfj.RIESGOS[k]["reinversión"][1]}
                                   for k, v in rfj.FICHAS.items()]), hide_index=True, width="stretch")
        st.caption("Ningún instrumento gubernamental está libre de todo riesgo: el crédito soberano es de riesgo bajo, pero hay riesgo de mercado "
                   "(si se vende antes del vencimiento), de inflación, de reinversión y de liquidez.")
    # ------------------------------------------------------------------ 3
    with tabs[2]:
        st.subheader("Canasta de acciones (BMV y NYSE/NASDAQ)")
        modo = st.radio("Rendimiento esperado", ["Manual (capturado)", "CAPM automático (β vs IPC)"],
                        index=0 if base.get("modo_rend") == "manual" else 1, horizontal=True)
        base["modo_rend"] = "manual" if modo.startswith("Manual") else "capm"
        perf_cols = nt.PERFILES
        tc = pd.DataFrame([{"acción": x["nombre"], "símbolo": x["simbolo"], "mercado": x.get("mercado", ""), "sector": x.get("sector", ""),
                            "beta": x["beta"], "rendimiento manual %": x["rend_manual"] * 100, "perspectivas": x.get("perspectivas", ""),
                            **{f"peso {pf} %": x["pesos"].get(pf, 0) * 100 for pf in perf_cols}} for x in base["acciones"]])
        edc = st.data_editor(tc, num_rows="dynamic", width="stretch", key="ed_canasta2")
        acciones = []
        for _, r in edc.dropna(subset=["acción"]).iterrows():
            acciones.append({"nombre": str(r["acción"]), "simbolo": str(r.get("símbolo") or ""), "mercado": str(r.get("mercado") or ""),
                             "sector": str(r.get("sector") or ""), "beta": float(r["beta"] or 0), "rend_manual": float(r["rendimiento manual %"] or 0) / 100,
                             "perspectivas": str(r.get("perspectivas") or "") if str(r.get("perspectivas") or "") != "nan" else "",
                             "pesos": {pf: float(r[f"peso {pf} %"] or 0) / 100 for pf in perf_cols}})
        base["acciones"] = acciones
        for pf in perf_cols:
            t = sum(x["pesos"][pf] for x in acciones)
            if t > 0 and abs(t - 1) > 1e-6:
                st.warning(f"Los pesos de {pf} suman {t*100:.2f}% (deben sumar 100%).")
        st.caption("Acciones de EE.UU. con su símbolo de NYSE/NASDAQ (p. ej. AAPL, NVDA): precio en dólares convertido con el USD/MXN de Yahoo. "
                   "PERSONALIZADO usa los pesos del perfil de referencia.")
        a = cm.activo_actual()
        datos_c, corr = _datos_canasta(tuple(x["simbolo"] for x in acciones if x["simbolo"]), a["inicio"], a["fin"])
        if st.button("Usar las betas calculadas (vs IPC) en la canasta"):
            mp = dict(zip(datos_c.get("símbolo", []), datos_c.get("beta vs IPC", [])))
            for x in base["acciones"]:
                b_ = mp.get(x["simbolo"])
                if b_ is not None and not np.isnan(b_):
                    x["beta"] = round(float(b_), 3)
            st.rerun()
        st.markdown("**Datos de mercado y justificación cuantitativa**")
        if not datos_c.empty and "vol. anual" in datos_c:
            dc = datos_c.copy()
            dc["rend./vol."] = dc["rend. período"] / dc["vol. anual"]
            if not corr.empty:
                dc["corr. media con la canasta"] = dc["símbolo"].map(lambda s_: (corr[s_].drop(s_).mean() if s_ in corr else np.nan))
            st.dataframe(dc, hide_index=True, width="stretch")
            st.caption("Justificación: mayor rendimiento por unidad de volatilidad (rend./vol.) y menor correlación media aportan diversificación; "
                       "la β indica la sensibilidad al mercado. Rendimientos y volatilidades del período seleccionado (máx. 1 año), Yahoo Finance.")
            if not corr.empty:
                fig = go.Figure(go.Heatmap(z=corr.values, x=corr.columns, y=corr.index, zmin=-1, zmax=1, colorscale="RdBu",
                                           text=corr.round(2).values, texttemplate="%{text}"))
                fig.update_layout(height=380, template=cm.PLANTILLA_PLOTLY, title="Correlación de rendimientos diarios")
                st.plotly_chart(fig, width="stretch")
    # ------------------------------------------------------------------ 4
    with tabs[3]:
        st.subheader("Catálogo de futuros (16 contratos, 6 clases de activo)")
        nombres_f = {c["clave"]: f'{c["clave"]} · {c["nombre"]}' for c in fm.CATALOGO}
        excl = st.multiselect("Contratos que NO desea usar (los demás se asignan según la mezcla del perfil)", list(nombres_f),
                              default=[k for k in base.get("futuros_excluidos", []) if k in nombres_f], format_func=nombres_f.get)
        if excl != list(base.get("futuros_excluidos") or []):
            base["futuros_excluidos"] = excl
            st.rerun()
        cat = p.get("futuros_cat")
        if not cat["asignable"].any():
            st.error("No se obtuvieron precios de futuros o el tipo de cambio de Yahoo: ningún contrato es asignable.")
        else:
            st.dataframe(cat.drop(columns=["yahoo"]), hide_index=True, width="stretch",
                         column_config={"vol_anual": st.column_config.NumberColumn(format="percent")})
            st.caption("Precios: Yahoo Finance (contrato continuo), fechas: " + ", ".join(f"{k} {v}" for k, v in p["fechas_futuros"].items()) +
                       f". USD/MXN {p['usdmxn']:.4f}. El margen inicial es garantía, no el costo: el valor del contrato es el nocional.")
            with st.expander("Capturar o actualizar márgenes (p. ej. AIM de MexDer para DA e IPC)"):
                cap_df = pd.DataFrame([{"clave": c["clave"], "margen inicial": (s["nota_margenes"].get(c["clave"], {}) or {}).get("mi", c["mi"] or 0.0),
                                        "margen mantenimiento": (s["nota_margenes"].get(c["clave"], {}) or {}).get("mm", c["mm"] or 0.0),
                                        "moneda": c["moneda"]} for c in fm.CATALOGO])
                edm = st.data_editor(cap_df, hide_index=True, width="stretch", disabled=["clave", "moneda"], key="ed_margenes")
                nuevos = {}
                for _, r in edm.iterrows():
                    orig = next(c for c in fm.CATALOGO if c["clave"] == r["clave"])
                    if (r["margen inicial"] or 0) > 0 and (r["margen inicial"] != (orig["mi"] or 0) or r["margen mantenimiento"] != (orig["mm"] or 0)):
                        nuevos[r["clave"]] = {"mi": float(r["margen inicial"]), "mm": float(r["margen mantenimiento"] or r["margen inicial"])}
                if nuevos != s["nota_margenes"]:
                    s["nota_margenes"] = nuevos
                    st.rerun()
            r_ = nt.calcular(p)
            st.markdown("**Diversificación por perfil (contratos según margen)**")
            f = r_["futuros"]
            if not f.empty:
                piv = f.pivot_table(index="clave", columns="perfil", values="contratos", aggfunc="sum").fillna(0).astype(int)
                st.dataframe(piv, width="stretch")
            st.dataframe(r_["derivados"][["perfil", "monto futuros", "contratos futuros", "nocional futuros", "apalancamiento (nocional/inversión)"]],
                         hide_index=True, width="stretch")
            minimo = cat[cat.asignable]["margen_inicial_MXN"].sum()
            st.info(f"Para tener al menos un contrato de cada uno de los {int(cat.asignable.sum())} futuros con margen disponible se requieren "
                    f"≈ ${minimo:,.0f} MXN en garantías. Con montos menores, la asignación prioriza las clases del perfil.")
    # ------------------------------------------------------------------ 5
    with tabs[4]:
        st.subheader(f"Estrategias con opciones sobre {p['derivados']['nombre']}")
        st.session_state["nota_ancho"] = st.number_input("Ancho de alas STG/BTF (% del spot)", value=5.0, step=0.5) / 100
        est = st.selectbox("Estrategia a revisar", list(nt.ESTRATEGIAS_NOTA))
        d = p["derivados"]
        legs = nt.legs_estrategia(est, d["S0"], p["dias"] / 365, d["r_cont"], d["q"], d["sigma"], st.session_state["nota_ancho"])
        rs = nt.resumen_estrategia(legs, d["S0"])
        obj, cuando = nt.CUANDO_CONVIENE[est]
        st.markdown(f"**Objetivo:** {obj}. **Conviene cuando:** {cuando}.")
        st.dataframe(pd.DataFrame([{"posición": "Compra" if l["pos"] > 0 else "Venta", "cantidad": abs(l["pos"]), "tipo": l["tipo"], "strike": l["K"],
                                    "prima BSM": l["prima"], "vencimiento (días)": p["dias"]} for l in legs]), hide_index=True, width="stretch")
        m = st.columns(4)
        m[0].metric("Prima neta (pagada + / recibida −)", f"{rs['costo_neto']:.4f}")
        m[1].metric("Pérdida máxima por unidad", "Ilimitada" if np.isinf(rs["perdida_max"]) else f"{rs['perdida_max']:.2f}")
        m[2].metric("Ganancia máxima por unidad", "Ilimitada" if np.isinf(rs["ganancia_max"]) else f"{rs['ganancia_max']:.2f}")
        m[3].metric("Break-even", ", ".join(f"{x:.2f}" for x in rs["break_even"]) or "—")
        S = np.linspace(d["S0"] * 0.6, d["S0"] * 1.4, 161)
        pay = [sum(l["pos"] * ((max(x - l["K"], 0) if l["tipo"] == "CALL" else max(l["K"] - x, 0)) - l["prima"]) for l in legs) for x in S]
        fig = go.Figure(go.Scatter(x=S, y=pay, name="Resultado al vencimiento", line=dict(color=cm.AZUL, width=3)))
        fig.add_hline(0, line_color=cm.GRIS); fig.add_vline(d["S0"], line_dash="dot", annotation_text="Spot")
        fig.update_layout(height=360, template=cm.PLANTILLA_PLOTLY, xaxis_title="Precio del subyacente al vencimiento", yaxis_title="Resultado por unidad")
        st.plotly_chart(fig, width="stretch")
        st.caption("Black-Scholes: C = S·e^(−qT)·N(d1) − K·e^(−rT)·N(d2); P = K·e^(−rT)·N(−d2) − S·e^(−qT)·N(−d1); d1 = [ln(S/K) + (r − q + σ²/2)T]/(σ√T). "
                   f"Valores usados: S = {d['S0']:.2f}, T = {p['dias']/365:.4f}, r = {d['r_cont']*100:.3f}%, σ = {d['sigma']*100:.2f}%, q = {d['q']*100:.2f}%. "
                   "STOP LOSS: en la nota se aplica a los futuros (pestaña 4) como barrera hipotética.")
    # ------------------------------------------------------------------ 6
    with tabs[5]:
        st.subheader("Asignación por perfil (editable)")
        cfg = pd.DataFrame([{"perfil": pf, "% renta fija": c_["krf_pct"] * 100, "% capitales (de la porción de riesgo)": c_["cap_pct"] * 100,
                             "% futuros (de derivados)": c_["fut_pct"] * 100, "estrategia de opciones": c_["estrategia"],
                             "stop-loss futuros %": (c_.get("stop_pct") or 0) * 100} for pf, c_ in base["config"].items()])
        edp = st.data_editor(cfg, hide_index=True, width="stretch", disabled=["perfil"], key="ed_cfg2",
                             column_config={"estrategia de opciones": st.column_config.SelectboxColumn(options=list(nt.ESTRATEGIAS_NOTA))})
        for _, r in edp.iterrows():
            base["config"][r["perfil"]] = {"krf_pct": r["% renta fija"] / 100, "cap_pct": r["% capitales (de la porción de riesgo)"] / 100,
                                           "fut_pct": r["% futuros (de derivados)"] / 100, "estrategia": r["estrategia de opciones"],
                                           "stop_pct": r["stop-loss futuros %"] / 100}
        st.caption("PERSONALIZADO se calcula con el perfilador (pestaña 1).")
        base["tope_primas_pct"] = st.number_input("Tope de primas de opciones (% de la inversión; 0 = sin tope)", 0.0, 100.0,
                                                  float(base.get("tope_primas_pct", 0.0) * 100), step=1.0) / 100
        st.caption("Con tope, el excedente del presupuesto de opciones se invierte en la renta fija seleccionada. Sin tope (0) se reproducen "
                   "los pesos del archivo del curso; un tope bajo reduce la pérdida por primas en el escenario base.")
    s["nota_base"] = base
    p = construir(base, resp, s["nota_margenes"], ancho=st.session_state.get("nota_ancho", 0.05))
    r = nt.calcular(p)
    st.session_state["res"]["nota_params"] = p
    st.session_state["res"]["nota"] = r
    # ------------------------------------------------------------------ 7
    with tabs[6]:
        m = st.columns(len(p["perfiles"]))
        for i, pf in enumerate(p["perfiles"]):
            fila = r["resumen"].set_index("perfil").loc[pf]
            m[i].metric(pf, f"${fila['NE']:,.0f}", f"{fila['NE %']*100:.2f}% (escenario neutral)")
        st.dataframe(r["resumen"], hide_index=True, width="stretch")
        dv = r["diversificacion"].set_index("perfil")
        fig = go.Figure([go.Bar(y=dv.index, x=dv[c_], name=c_.replace(" $", ""), orientation="h")
                         for c_ in ["renta fija $", "capitales $", "futuros (garantía) $", "opciones (primas) $"]])
        fig.update_layout(barmode="stack", height=300, template=cm.PLANTILLA_PLOTLY, title="Distribución del capital (MXN)")
        st.plotly_chart(fig, width="stretch")
        e = r["escenarios"]
        fig = go.Figure([go.Bar(x=g["escenario"], y=g["NE"], name=pf_) for pf_, g in e.groupby("perfil", sort=False)])
        fig.update_layout(barmode="group", height=420, template=cm.PLANTILLA_PLOTLY, title="Escenarios adversos, neutral y optimistas", yaxis_title="NE (MXN)")
        st.plotly_chart(fig, width="stretch")
        st.dataframe(e.round(2), hide_index=True, width="stretch")
        st.markdown("**Ficha de condiciones**")
        st.dataframe(r["ficha"], hide_index=True, width="stretch")
        st.markdown("**Objetivo de rendimiento y tolerancia al riesgo**")
        st.dataframe(r["chequeo"], hide_index=True, width="stretch")
        if "PERSONALIZADO" in p["perfiles"]:
            ch = r["chequeo"].set_index("perfil").loc["PERSONALIZADO"]
            if ch["dentro de tolerancia"] is False:
                k = nt.krf_para_tolerancia(p, "PERSONALIZADO")
                st.warning(f"La propuesta PERSONALIZADA pierde {ch['pérdida adverso moderado %']*100:.2f}% en el escenario adverso moderado, más que "
                           f"la tolerancia de {ch['pérdida tolerada %']*100:.0f}%. " +
                           (f"Con {k*100:.0f}% en renta fija quedaría dentro de la tolerancia." if k else "Ningún %KRF la deja dentro: reduzca derivados."))
        alto = r["derivados"]["apalancamiento (nocional/inversión)"].max()
        if alto > 1:
            cm.etiqueta(f"Apalancamiento: el nocional de futuros llega a {alto:.1f}× la inversión", "riesgo")
        st.caption("La protección sólo proviene de la renta fija mantenida al vencimiento y del riesgo soberano: no hay garantía contractual del "
                   "capital. Las pérdidas de futuros pueden exceder la garantía y el stop-loss puede ejecutarse peor por brechas de mercado.")
    # ------------------------------------------------------------------ 8
    with tabs[7]:
        rec = "PERSONALIZADO" if "PERSONALIZADO" in p["perfiles"] else pfm.perfil_referencia(0.5)
        rec = st.selectbox("Propuesta del reporte", p["perfiles"], index=p["perfiles"].index(rec))
        fuentes = [f"{k}: {v}" for k, v in p["fuentes"].items()] + [
            "Futuros: precios Yahoo Finance; márgenes CITIC Securities (02/06/2026) y Barchart; especificaciones CME Group y BMV/MexDer.",
            "Acciones e IPC: Yahoo Finance (proveedor secundario, con retraso).",
            f"Fecha de consulta: {cm.dat.ahora_mx().strftime('%d/%m/%Y %H:%M')} (Ciudad de México)."]
        if st.button("Generar reporte ejecutivo (PDF)"):
            st.session_state["nota_pdf"] = rn.pdf(p, r, rec, cm.dat.ahora_mx().strftime("%d/%m/%Y"), fuentes)
        if st.session_state.get("nota_pdf"):
            st.download_button("Descargar reporte ejecutivo", st.session_state["nota_pdf"], "reporte_ejecutivo_nota.pdf", "application/pdf")
        st.caption("El Excel INTEGRAL (sección 15) incluye las hojas NOTA ESTRUCTURADA, PERFIL, RENTA FIJA y FUTUROS MULTIACTIVO con estos mismos datos.")
    cm.registrar("Nota estructurada", {"inversion": base["inversion"], "dias": base["dias"], "respuestas": resp},
                 "renta fija + capitales + futuros + opciones", {pf: float(r["resumen"].set_index("perfil").loc[pf, "NE"]) for pf in p["perfiles"]})
