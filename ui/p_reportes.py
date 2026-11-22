"""Páginas: Reportes (IA explicativa, Excel, PDF) y Estudios guardados (con auditoría)."""
from __future__ import annotations

import datetime as dt
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from core import reports as rp, reports_integral as ri, ai, audit, data as dat, technical as ta  # noqa: E402
from . import common as cm  # noqa: E402

METODOLOGIA = ("Datos diarios de Yahoo Finance (proveedor secundario) sin ajuste automático; validación de consistencia OHLCV y "
               "reconciliación opcional contra fuente oficial. Rendimientos log para volatilidad (×√252), beta por covarianza "
               "muestral contra el S&P/BMV IPC en fechas comunes, VaR/ES histórico y paramétrico normal. Indicadores técnicos con "
               "fórmulas documentadas (RSI de Wilder). DCF con FCFF y WACC por CAPM. Opciones con BSM y CRR; futuros por costo de "
               "acarreo. Caps/floors con Black-76 o Bachelier sobre curva con interpolación lineal en tasa cero continua. "
               "Escenarios: 5 choques por perfil aplicados de forma homogénea a todas las estrategias.")

LIMITACIONES = ("• Los precios de Yahoo no son el cierre oficial de la BMV y llegan con retraso.\n"
                "• No hay acceso automático a cotizaciones de futuros, primas de opciones ni AIM de MexDer: sin captura se usan valores teóricos.\n"
                "• Los estados financieros del proveedor pueden diferir de los reportes oficiales.\n"
                "• Dividendos discretos no modelados en opciones; calendario de tasas sin ajuste por días inhábiles.\n"
                "• En composición en atraso no se incorporan fijaciones ya observadas del período en curso.\n"
                "• Las métricas de riesgo describen el pasado; los escenarios son hipótesis sin probabilidad asignada.\n"
                "• Historia limitada a 1 año por diseño.")


def _contexto():
    r = st.session_state["res"]
    ctx = {}
    for k_src, k_dst in [("activo", "activo"), ("riesgo_vals", "riesgo"), ("caps_vals", "caps"), ("escenarios_resumen", "escenarios_resumen"),
                         ("exposicion_acc", "exposicion_acciones"), ("exposicion_tasas", "exposicion_tasas")]:
        if k_src in r:
            ctx[k_dst] = r[k_src]
    tv = r.get("tecnico_vals")
    if tv:
        t = dict(tv)
        if isinstance(r.get("tendencias"), pd.DataFrame):
            t["tendencias"] = "; ".join(f"{x.horizonte}: {x.dirección}" for x in r["tendencias"].itertuples())
        ctx["tecnico"] = t
    if "dcf" in r:
        d = r["dcf"]
        ctx["valuacion"] = {"valor_por_accion": d["resultado"]["valor_por_accion"], "wacc": d["parametros"]["wacc"],
                            "g": d["parametros"]["g"], "peso_vt": d["resultado"]["peso_vt_%"], "supuestos": d["parametros"]}
    if isinstance(r.get("comparativas"), pd.DataFrame):
        ctx["comparativa_acciones"] = r["comparativas"].round(2).to_dict("records")
    if isinstance(r.get("escenarios_tasas"), pd.DataFrame):
        et = r["escenarios_tasas"]
        ctx["escenarios_tasas"] = et[["perfil", "estrategia", "escenario", "resultado_combinado_VP", "prima_neta_pagada",
                                      "protección_conseguida"]].round(0).to_dict("records")
    if isinstance(r.get("ratios"), pd.DataFrame):
        ctx["ratios"] = r["ratios"][["ratio", "valor", "estado"]].to_dict("records")
    if isinstance(r.get("opciones"), pd.DataFrame):
        ctx["opciones"] = r["opciones"].to_dict("records")
    if r.get("nota"):
        ctx["nota_estructurada"] = {"resumen": r["nota"]["resumen"].round(2).to_dict("records"),
                                    "escenarios": r["nota"]["escenarios"][["perfil", "escenario", "NE", "NE %"]].round(4).to_dict("records")}
    if isinstance(r.get("patrones"), pd.DataFrame) and not r["patrones"].empty:
        ctx["patrones"] = r["patrones"][[c for c in ["figura", "estado", "inicio", "fin"] if c in r["patrones"]]].astype(str).to_dict("records")
    return ctx


def _api_key():
    try:
        return st.secrets.get("ANTHROPIC_API_KEY", "")
    except Exception:
        return ""


def _estudio():
    r = st.session_state["res"]
    a = cm.activo_actual()
    h = r.get("historico")
    _, meta, _ = cm.datos_activo()
    fuentes = pd.DataFrame([{"dato": "Precios", "fuente": (meta or {}).get("fuente"), "consulta": (meta or {}).get("fecha_consulta"),
                             "última fecha": (meta or {}).get("ultima_fecha_disponible"), "estado": (meta or {}).get("estado")},
                            {"dato": "Catálogo MexDer", "fuente": "bmv.com.mx", "consulta": "2026-11-21", "última fecha": "", "estado": "Revisado"}])
    if isinstance(r.get("tasas_ref"), pd.DataFrame):
        fuentes = pd.concat([fuentes, pd.DataFrame([{"dato": "Tasas", "fuente": "Banxico SIE-API", "consulta": "",
                                                      "última fecha": str(r["tasas_ref"]["fecha"].max().date()), "estado": "Oficial"}])])
    tec = None
    if isinstance(h, pd.DataFrame) and not h.empty:
        from core import technical as ta
        c = h["Close"]
        tec = pd.DataFrame({"Cierre": c, "RSI9": ta.rsi_wilder(c, 9), "RSI14": ta.rsi_wilder(c, 14), "RSI25": ta.rsi_wilder(c, 25),
                            "ROC12": ta.roc(c, 12), "Williams14": ta.williams_r(h["High"], h["Low"], c, 14),
                            "SMA20": ta.sma(c, 20), "SMA50": ta.sma(c, 50)}).reset_index()
    inf, _ = cm.info(a["simbolo"]) if a else ({}, None)
    est = {}
    for k, nm in [("income_a", "Resultados anual"), ("balance_a", "Balance anual"), ("cash_a", "Flujos anual"),
                  ("income_q", "Resultados trimestral")]:
        v = (inf or {}).get(k)
        if isinstance(v, pd.DataFrame) and not v.empty:
            est[nm] = v.reindex(sorted(v.columns), axis=1)
    riesgo = {}
    for k, nm in [("riesgo_tabla", "VaR y ES"), ("correlaciones", "Correlaciones"), ("tendencias", "Tendencias")]:
        if isinstance(r.get(k), pd.DataFrame):
            riesgo[nm] = r[k]
    if r.get("beta"):
        riesgo["Beta"] = pd.DataFrame([{k: v for k, v in r["beta"].items()}])
    if r.get("liquidez"):
        riesgo["Liquidez"] = pd.DataFrame([r["liquidez"]])
    fut = {"Contrato": r.get("futuros"), "Simulación de garantías": r.get("margen")}
    caps = {"Caplets/floorlets": r.get("caps"), "Sensibilidades": r.get("caps_sens"), "Escenarios de tasas": r.get("escenarios_tasas")}
    sup = []
    for k in ("exposicion_acc", "exposicion_tasas"):
        if r.get(k):
            sup += [{"bloque": k, "parámetro": a_, "valor": str(b_)} for a_, b_ in r[k].items()]
    if r.get("dcf"):
        sup += [{"bloque": "DCF", "parámetro": a_, "valor": str(b_)} for a_, b_ in r["dcf"]["parametros"].items()]
    return {
        "meta": {"Activo": f"{a.get('nombre')} ({a.get('simbolo')})", "Período": f"{a.get('inicio')} a {a.get('fin')}",
                 "Fecha de generación": dat.ahora_mx().strftime("%Y-%m-%d %H:%M %Z"), "Fuente de precios": dat.FUENTE_YAHOO,
                 "Versión del motor": audit.VERSION_MOTOR, "Huella de datos": audit.huella(h)},
        "fuentes": fuentes, "historico": h, "historico_tail": h.tail(25) if isinstance(h, pd.DataFrame) else None,
        "estados": est, "ratios": r.get("ratios"), "dcf": r.get("dcf"),
        "dcf_tabla": {"Proyección": r["dcf"]["tabla"], "Sensibilidad WACC × g": r["dcf"]["sensibilidad"]} if r.get("dcf") else None,
        "tecnico": tec, "tecnico_resumen": pd.DataFrame([r["tecnico_vals"]]) if r.get("tecnico_vals") else None,
        "patrones": r.get("patrones"), "riesgo": riesgo, "riesgo_resumen": pd.DataFrame([r["riesgo_vals"]]) if r.get("riesgo_vals") else None,
        "futuros": fut, "opciones": r.get("opciones"), "curva": {"Nodos": r.get("curva"), "Curva interpolada": r.get("curva_tabla")},
        "caps": caps, "estrategias": r.get("estrategias") if r.get("estrategias") is not None else r.get("coberturas"),
        "perfiles": r.get("perfiles"), "escenarios": r.get("escenarios"), "comparativas": r.get("comparativas"),
        "supuestos": pd.DataFrame(sup), "metodologia": METODOLOGIA, "limitaciones": LIMITACIONES,
        "resumen_ejecutivo": st.session_state.get("resumen_ejecutivo") or ai.explicacion_reglas(_contexto()),
    }


def _graficas(est):
    g = {}
    h = est.get("historico")
    if isinstance(h, pd.DataFrame) and not h.empty:
        fig, ax = plt.subplots(figsize=(11, 4))
        ax.plot(h.index, h["Close"], color=cm.AZUL)
        ax.set_title("Cierre del proveedor (MXN)"); ax.grid(alpha=.3)
        g["Datos históricos (últimas filas)"] = rp.png_matplotlib(fig); plt.close(fig)
    m = est.get("escenarios")
    if isinstance(m, pd.DataFrame) and not m.empty:
        pn = m["perfil"].iloc[0]
        piv = m[m.perfil == pn].pivot_table(index="escenario", columns="estrategia", values="resultado_combinado", aggfunc="first")
        fig, ax = plt.subplots(figsize=(11, 4))
        piv.plot(kind="bar", ax=ax); ax.set_title(f"Resultado combinado por escenario — perfil {pn}"); ax.grid(alpha=.3)
        ax.tick_params(axis="x", rotation=0, labelsize=7); ax.legend(fontsize=7)
        g["Cinco escenarios por perfil y estrategia"] = rp.png_matplotlib(fig); plt.close(fig)
    c = st.session_state["res"].get("caps")
    if isinstance(c, pd.DataFrame) and not c.empty:
        fig, ax = plt.subplots(figsize=(11, 4))
        ax.bar(c["periodo"], c["valor_presente"], color=cm.TURQUESA); ax.set_title("VP teórico por caplet/floorlet"); ax.grid(alpha=.3)
        g["Caps y floors"] = rp.png_matplotlib(fig); plt.close(fig)
    return g


def params_integral():
    """Parámetros del Excel INTEGRAL tomados de la sesión (o valores automáticos documentados)."""
    a = cm.activo_actual()
    df, meta, err = cm.datos_activo()
    mk, _, _ = cm.datos_mercado()
    if df.empty or mk.empty:
        return None, "Se requieren precios de la emisora y del IPC."
    datos = ri.datos_desde_df(df, mk)
    if len(datos) < 40:
        return None, "Se requieren al menos 40 fechas comunes con el IPC (amplíe el período)."
    r = st.session_state["res"]
    spot = float(datos["Close"].iloc[-1])
    rf, txt_r = cm.rf_corto()
    qd, txt_q = cm.dividendo_auto()
    hoy = dat.ahora_mx().date()
    prox = cm.vencimientos(1)[0]
    op = r.get("opciones")
    k_std = float(op["strike"].iloc[0]) if isinstance(op, pd.DataFrame) and not op.empty else ri.strike_redondo(spot, spot)
    reg = ta.regresion_tendencia(datos["Close"])
    tendencia = float(reg["ajuste"].iloc[-1]) if reg else spot
    fu = r.get("futuros")
    f_obs = 0.0
    n_fut, m_fut = 1, 100
    if isinstance(fu, pd.DataFrame) and not fu.empty:
        if str(fu["origen_precio"].iloc[0]).startswith("observado"):
            f_obs = float(fu["precio_futuro"].iloc[0])
        n_fut, m_fut = int(fu["contratos"].iloc[0]), float(fu["multiplicador"].iloc[0])
    return {
        "emisora": a["nombre"].replace("*", "").strip(), "datos": datos, "spot": spot, "r": rf, "q": qd,
        "fuente_r": txt_r, "fuente_q": txt_q, "dias": max((prox - hoy).days, 1),
        "fuente_dias": f"Próximo vencimiento MexDer {prox} (tercer viernes, ciclo trimestral)",
        "k_straddle": k_std, "k_call_strangle": ri.strike_redondo(spot * 1.05, spot),
        "k_put_strangle": ri.strike_redondo(spot * 0.95, spot), "paso": ri.paso_redondo(spot),
        "paso_btfl": ri.paso_redondo(spot), "tendencia": round(tendencia, 2),
        "fuente_tendencia": "Valor de la recta de tendencia log-lineal (regresión MCO) en la última fecha; editable.",
        "rsi_wilder": {n: float(ta.rsi_wilder(datos["Close"], n).iloc[-1]) for n in (9, 14, 25)},
        "primas_obs": {}, "f_obs": f_obs, "n_fut": n_fut, "mult_fut": m_fut, "mult": 100,
        "confianza": 0.95, "monto": 1_000_000.0, "dias_var": max((prox - hoy).days, 1),
        "nota": r.get("nota_params") or _nota_por_defecto(),
    }, None


def _nota_por_defecto():
    from . import p_nota
    return p_nota.construir(p_nota.base_actual())


def reportes():
    st.title("Reportes e interpretación")
    t1, t2, t3 = st.tabs(["Asistente de IA explicativa", "Informe Excel", "Informe PDF"])
    ctx = _contexto()
    with t1:
        st.caption("El asistente recibe sólo resultados estructurados del motor matemático; no genera cifras nuevas.")
        with st.expander("Datos que recibirá el asistente"):
            st.code(audit.a_json(ctx)[:20000], language="json")
        key = _api_key()
        pregunta = st.text_area("Pregunta", "Redacta un resumen ejecutivo de los riesgos observados y de cómo se comparan las "
                                "alternativas de cobertura dentro del mismo escenario.")
        ejemplos = ["¿Qué variables explican principalmente el riesgo observado?", "¿Por qué cambia el valor teórico de la opción?",
                    "¿Qué diferencia existe entre dos alternativas de cobertura?", "¿Qué ocurre con el valor del cap si cambia la curva de tasas?",
                    "¿Qué riesgos persisten después de aplicar una cobertura?"]
        st.caption("Ejemplos: " + " · ".join(ejemplos))
        if st.button("Generar explicación"):
            if not ctx:
                st.warning("No hay resultados calculados todavía. Recorra los módulos de análisis primero.")
            elif key:
                try:
                    with st.spinner("Consultando al asistente…"):
                        txt = ai.preguntar_claude(ctx, pregunta, key)
                    st.markdown(txt)
                    st.session_state["resumen_ejecutivo"] = txt
                except Exception as e:
                    st.error(f"No se pudo consultar el asistente ({e}). Se muestra la explicación basada en reglas.")
                    st.markdown(ai.explicacion_reglas(ctx))
            else:
                txt = ai.explicacion_reglas(ctx)
                st.markdown(txt)
                st.session_state["resumen_ejecutivo"] = txt
    est = None
    with t2:
        formato = st.radio("Formato", ["Integral (formato de referencia) + análisis de la plataforma", "Estándar (17 hojas)"])
        if formato.startswith("Integral"):
            st.write("Hojas: Portada · DATOS · TENDENCIAS RSI · BS · STRADDLE CALL|PUT · STRANGLE CALL|PUT · COMPRA VTA FUT · "
                     "BTFL CALL|PUT · NOTA ESTRUCTURADA · y las hojas de análisis de la plataforma (estados financieros, ratios, DCF, riesgo, "
                     "escenarios, caps y floors…). Todo con fórmulas vivas: cambie un strike o una tasa y el libro se recalcula.")
        else:
            st.write("Libro con 17 hojas: " + ", ".join(rp.HOJAS) + ". Incluye fórmulas auditables en Datos históricos y DCF.")
        if st.button("Preparar Excel"):
            est = _estudio()
            if formato.startswith("Integral"):
                p, err = params_integral()
                if err:
                    st.error(err)
                else:
                    st.session_state["xlsx"] = ri.excel_integral(est, p)
            else:
                st.session_state["xlsx"] = rp.excel(est)
        if st.session_state.get("xlsx"):
            st.download_button("Descargar Excel", st.session_state["xlsx"], f"analisis_{cm.activo_actual().get('simbolo')}.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    with t3:
        st.write("Informe profesional con portada, resumen ejecutivo, metodología, fuentes, análisis, escenarios, limitaciones y anexo de fórmulas.")
        if st.button("Preparar PDF"):
            est = est or _estudio()
            st.session_state["pdf"] = rp.pdf(est, _graficas(est))
        if st.session_state.get("pdf"):
            st.download_button("Descargar PDF", st.session_state["pdf"], f"informe_{cm.activo_actual().get('simbolo')}.pdf", "application/pdf")
    st.caption("Excel, PDF e interfaz usan los mismos resultados almacenados en la sesión. Las secciones sin calcular se indican como tales.")


def estudios():
    st.title("Estudios guardados y auditoría")
    t1, t2 = st.tabs(["Estudios", "Bitácora de auditoría"])
    with t1:
        nombre = st.text_input("Nombre del estudio", f"{cm.activo_actual().get('nombre')} {dt.datetime.now():%Y-%m-%d %H:%M}")
        if st.button("Guardar estudio actual"):
            a = cm.activo_actual()
            st.session_state["estudios"].append({
                "nombre": nombre, "creado": dat.ahora_mx().isoformat(timespec="seconds"),
                "activo": {k: str(v) for k, v in a.items() if k != "fila"},
                "perfiles_acciones": st.session_state.get("perfiles_acc"), "perfiles_tasas": st.session_state.get("perfiles_tasas"),
                "curva": st.session_state.get("curva_nodos").to_dict("records") if isinstance(st.session_state.get("curva_nodos"), pd.DataFrame) else None,
                "resultados_clave": json.loads(audit.a_json(_contexto())), "bitacora": list(st.session_state["bitacora"])})
            st.success("Estudio guardado en la sesión. Descárguelo para conservarlo (la sesión se borra al cerrar la página).")
        for i, e in enumerate(st.session_state["estudios"]):
            with st.expander(f"{i+1}. {e['nombre']} — {e['creado']}"):
                st.json({k: v for k, v in e.items() if k != "bitacora"}, expanded=False)
                st.download_button("Descargar estudio (JSON)", audit.a_json(e).encode("utf-8"), f"estudio_{i+1}.json", key=f"dl_{i}")
        st.markdown("**Restaurar un estudio**")
        up = st.file_uploader("Archivo JSON de estudio", type="json")
        if up:
            try:
                e = json.load(up)
                if e.get("perfiles_acciones"):
                    st.session_state["perfiles_acc"] = e["perfiles_acciones"]
                if e.get("perfiles_tasas"):
                    st.session_state["perfiles_tasas"] = e["perfiles_tasas"]
                if e.get("curva"):
                    st.session_state["curva_nodos"] = pd.DataFrame(e["curva"])
                    st.session_state.pop("curva", None)
                st.success(f"Restaurados perfiles y curva de '{e.get('nombre')}'. Activo original: {e.get('activo', {}).get('simbolo')} "
                           f"({e.get('activo', {}).get('inicio')} a {e.get('activo', {}).get('fin')}). Seleccione ese activo y período para "
                           "reproducir el análisis; compare la huella de datos en la bitácora.")
            except Exception as ex:
                st.error(f"Archivo inválido: {ex}")
    with t2:
        b = st.session_state["bitacora"]
        st.write(f"{len(b)} registros en esta sesión. Cada uno guarda fuente, huella de los datos, parámetros, fórmula y resultado.")
        if b:
            st.dataframe(pd.DataFrame([{k: (json.dumps(v, ensure_ascii=False)[:200] if isinstance(v, (dict, list)) else v)
                                        for k, v in x.items()} for x in b[::-1]]), hide_index=True, width="stretch")
            st.download_button("Descargar bitácora (JSON)", audit.a_json(b).encode("utf-8"), "bitacora_auditoria.json")
