"""Hojas recomendadas por el Proyecto Integrador (fase 5), conectadas por fórmulas con el motor NOTA ESTRUCTURADA.

DASHBOARD (entradas del cliente + resumen) · MERCADO DE CAPITALES · OPCIONES Y ESTRATEGIAS · BLACK-SCHOLES ·
DIVERSIFICACIÓN · ESCENARIOS DE LA NOTA · REPORTE EJECUTIVO. PERFIL, RENTA FIJA y FUTUROS MULTIACTIVO ya existen.
Ninguna cifra de resultados se escribe como valor: todo se lee de las hojas de cálculo con fórmulas.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
from xlsxwriter.utility import xl_col_to_name as COL, xl_rowcol_to_cell as CELL

from . import nota as nt
from .reports_nota import (CAP_R0, H_CAP, H_DASH, H_FUT, H_NOTA, H_PERFIL, H_RF, _rf_sel_row, q)

H_OPC, H_BSM, H_DIV, H_ESC, H_REP = "OPCIONES Y ESTRATEGIAS", "BLACK-SCHOLES", "DIVERSIFICACIÓN", "ESCENARIOS DE LA NOTA", "REPORTE EJECUTIVO"
ORDEN = [H_DASH, H_PERFIL, H_RF, H_CAP, H_FUT, H_OPC, H_BSM, H_DIV, H_ESC, H_REP, H_NOTA]
N = q(H_NOTA)
COLORES = ["#C0392B", "#14B8C4", "#0B1F3A", "#E8833A", "#7D3C98", "#27AE60"]
MX = ("BMV", "BIVA")


def _hw(wb):
    return wb.add_format({"font_name": "Arial", "font_size": 10, "bold": True, "font_color": "white", "bg_color": "#14B8C4", "border": 1,
                          "align": "center", "valign": "vcenter", "text_wrap": True})


def _pf_rec(p):
    return "PERSONALIZADO" if "PERSONALIZADO" in p["perfiles"] else p["perfiles"][0]


def _bs(tipo, S, K, T, r, qd, sg):
    d1 = f"((LN({S}/{K})+({r}-{qd}+{sg}^2/2)*{T})/({sg}*SQRT({T})))"
    d2 = f"({d1}-{sg}*SQRT({T}))"
    if tipo == "CALL":
        return f"({S}*EXP(-{qd}*{T})*NORMSDIST({d1})-{K}*EXP(-{r}*{T})*NORMSDIST({d2}))"
    return f"({K}*EXP(-{r}*{T})*NORMSDIST(-{d2})-{S}*EXP(-{qd}*{T})*NORMSDIST(-{d1}))"


def _chart(wb, tipo, titulo, ancho=520, alto=280, sub=None):
    ch = wb.add_chart({"type": tipo, **({"subtype": sub} if sub else {})})
    ch.set_title({"name": titulo, "name_font": {"size": 11, "color": "#0B1F3A"}})
    ch.set_legend({"position": "bottom"})
    ch.set_size({"width": ancho, "height": alto})
    return ch


# ============================================================================ DASHBOARD
def hoja_dashboard(wb, f, p, X, fuente_rf=""):
    ws = wb.add_worksheet(H_DASH)
    ws.merge_range("B2:N2", "DASHBOARD — NOTA ESTRUCTURADA DE INVERSIÓN", f.bloque)
    ws.merge_range("B4:E4", "DATOS DEL CLIENTE (capture en las celdas amarillas)", f.head)
    entradas = [("Monto a invertir (MXN)", p["inversion"], f.num_in), ("Horizonte (días)", p["dias"], f.ent_in),
                ("Prima de riesgo de mercado (supuesto)", p["prm"], f.pct_in), ("Tasa libre de riesgo (Cetes 28 días)", p["rf_anual"], f.pct_in),
                ("Tope de primas de opciones (% inversión; 0 = sin tope)", p.get("tope_primas_pct") or 0.0, f.pct_in)]
    for k, (lab, v, fm_) in enumerate(entradas):
        ws.merge_range(5 + k, 1, 5 + k, 2, lab, f.lab_r)
        ws.write(5 + k, 3, v, fm_)
    ws.write("E9", fuente_rf, f.nota)
    ws.data_validation("D6", {"validate": "decimal", "criteria": ">", "value": 0, "error_message": "La inversión debe ser positiva"})
    ws.data_validation("D7", {"validate": "integer", "criteria": "between", "minimum": 1, "maximum": 1825, "error_message": "Horizonte de 1 a 1825 días"})
    ws.data_validation("D8", {"validate": "decimal", "criteria": "between", "minimum": 0, "maximum": 0.2, "error_message": "PRM entre 0% y 20%"})
    ws.data_validation("D9", {"validate": "decimal", "criteria": "between", "minimum": 0, "maximum": 0.3, "error_message": "Tasa entre 0% y 30%"})
    ws.data_validation("D10", {"validate": "decimal", "criteria": "between", "minimum": 0, "maximum": 1, "error_message": "Tope entre 0% y 100%"})
    perfil = [("Puntaje de riesgo (0–1)", f"={q(H_PERFIL)}!$E$17", f.res4), ("Perfil de referencia", f"={q(H_PERFIL)}!$E$18", f.res),
              ("Pérdida máxima tolerada", f"={q(H_PERFIL)}!$E$23", f.pct_b), ("Objetivo de rendimiento anual", f"={q(H_PERFIL)}!$E$26", f.pct_b),
              ("Estrategia de opciones sugerida", f"={q(H_PERFIL)}!$E$24", f.res)]
    ws.merge_range("B12:E12", "PERFIL (responda el cuestionario en la hoja PERFIL)", f.head)
    for k, (lab, fo, fm_) in enumerate(perfil):
        ws.merge_range(12 + k, 1, 12 + k, 2, lab, f.lab_r)
        ws.write_formula(12 + k, 3, fo, fm_)
    pf = _pf_rec(p)
    R, Rd, Rf = X["fila"][pf] + 1, X["fdiv"][pf] + 1, X["ficha"][pf] + 1
    fl = X["filas_ne"][pf]
    ws.merge_range("G4:J4", f"PROPUESTA {pf}", f.head)
    kpi = [("Renta fija elegida", f"={N}!$G${R}", f.res), ("% en renta fija", f"={N}!$F${R}/{N}!$E$4", f.pct_b),
           ("Resultado neto esperado (base)", f"={N}!$N${R}", f.mon_b), ("Rendimiento en el horizonte (base)", f"={N}!$O${R}", f.pct_b),
           ("Peor escenario (NE)", f"={N}!$L${Rf}", f.mon_b), ("Mejor escenario (NE)", f"=MAX({N}!$M${fl[0]}:$M${fl[-1]})", f.mon_b),
           ("Piso por renta fija", f"={N}!$F${Rf}", f.pct_b), ("Apalancamiento de futuros (nocional/inversión)", f"={N}!$K${Rf}", f.num),
           ("¿Cumple el objetivo de rendimiento?", f"={N}!$N${Rf}", f.res), ("¿Pérdida dentro de la tolerancia?", f"={N}!$P${Rf}", f.res),
           ("Protección del capital", f"={N}!$H${Rf}", f.txt)]
    for k, (lab, fo, fm_) in enumerate(kpi):
        ws.merge_range(5 + k, 6, 5 + k, 8, lab, f.lab_r)
        ws.write_formula(5 + k, 9, fo, fm_)
    # Comparativo de perfiles
    t0 = 19
    hdr = ["Perfil", "% renta fija", "Renta fija $", "Capitales $", "Futuros (garantía) $", "Opciones (primas) $", "NE base $", "NE base %",
           "Peor escenario $", "Mejor escenario $", "Piso renta fija", "¿Cumple objetivo?", "¿Dentro de tolerancia?"]
    ws.merge_range(t0 - 1, 1, t0 - 1, 13, "COMPARATIVO DE PERFILES", f.head)
    hw = _hw(wb); ws.set_row(t0, 30)
    for j, e in enumerate(hdr):
        ws.write(t0, 1 + j, e, hw)
    filas = []
    for k, pf_ in enumerate(p["perfiles"]):
        r = t0 + 1 + k
        R, Rd, Rf = X["fila"][pf_] + 1, X["fdiv"][pf_] + 1, X["ficha"][pf_] + 1
        fl = X["filas_ne"][pf_]
        ws.write(r, 1, pf_, f.lab_r)
        for j, (fo, fm_) in enumerate([(f"={N}!$F${R}/{N}!$E$4", f.pct), (f"={N}!$F${R}", f.mon), (f"={N}!$G${Rd}", f.mon),
                                       (f"={N}!$J${Rd}", f.mon), (f"={N}!$K${Rd}", f.mon), (f"={N}!$N${R}", f.mon_b), (f"={N}!$O${R}", f.pct_b),
                                       (f"={N}!$L${Rf}", f.mon), (f"=MAX({N}!$M${fl[0]}:$M${fl[-1]})", f.mon), (f"={N}!$F${Rf}", f.pct),
                                       (f"={N}!$N${Rf}", f.txt_c), (f"={N}!$P${Rf}", f.txt_c)]):
            ws.write_formula(r, 2 + j, fo, fm_)
        filas.append(r + 1)
    a, b = filas[0], filas[-1]
    verde = wb.add_format({"bg_color": "#D5F5E3", "font_color": "#1E8449", "bold": True})
    rojo = wb.add_format({"bg_color": "#FADBD8", "font_color": "#922B21", "bold": True})
    for rng in (f"M{a}:N{b}", "J13:J14"):
        ws.conditional_format(rng, {"type": "cell", "criteria": "==", "value": '"SÍ"', "format": verde})
        ws.conditional_format(rng, {"type": "cell", "criteria": "==", "value": '"NO"', "format": rojo})
    cc = _chart(wb, "bar", "Composición de la inversión por perfil", 560, 300, "percent_stacked")
    for k, (lab, c) in enumerate([("Renta fija", "D"), ("Capitales", "E"), ("Futuros (garantía)", "F"), ("Opciones (primas)", "G")]):
        cc.add_series({"name": lab, "categories": f"={q(H_DASH)}!$B${a}:$B${b}", "values": f"={q(H_DASH)}!${c}${a}:${c}${b}",
                       "fill": {"color": COLORES[k]}})
    ws.insert_chart(f"B{b + 3}", cc)
    ce = _chart(wb, "line", "Rendimiento de la nota por escenario (NE %)", 600, 300)
    e = X["esc_tabla"]
    for k, pf_ in enumerate(p["perfiles"]):
        c = COL(6 + 2 * k)
        ce.add_series({"name": pf_, "categories": f"={q(H_ESC)}!$B${e[0]}:$B${e[1]}", "values": f"={q(H_ESC)}!${c}${e[0]}:${c}${e[1]}",
                       "line": {"color": COLORES[k % 6], "width": 2.25}, "marker": {"type": "circle"}})
    ce.set_x_axis({"label_position": "low"})
    ce.set_y_axis({"num_format": "0%", "major_gridlines": {"visible": True, "line": {"color": "#E0E0E0"}}})
    ws.insert_chart(f"H{b + 3}", ce)
    ws.write(b + 20, 1, "Celdas amarillas = entradas · verde = vínculo a otra hoja · negro = fórmula. Cambie el monto, el horizonte o las respuestas "
                        "del PERFIL y todas las hojas se recalculan. Las cifras son estimaciones teóricas; ninguna estructura garantiza el capital.", f.nota)
    ws.set_column("A:A", 2); ws.set_column("B:B", 16); ws.set_column("C:C", 30); ws.set_column("D:D", 16); ws.set_column("E:F", 15)
    ws.set_column("G:H", 18); ws.set_column("I:I", 16); ws.set_column("J:J", 24); ws.set_column("K:N", 16)
    return ws


# ============================================================================ MERCADO DE CAPITALES
def hoja_capitales(wb, f, p, X):
    ws = wb.add_worksheet(H_CAP)
    acc = p["acciones"]
    n = len(acc)
    datos = {d.get("símbolo"): d for d in (p.get("canasta_datos") or [])}
    corr = p.get("canasta_corr")
    ws.merge_range("B2:S2", "MERCADO DE CAPITALES — ACCIONES DE MÉXICO Y EE.UU.", f.bloque)
    ws.write("B4", "Fuente: Yahoo Finance (precios de cierre ajustados por splits, hasta 1 año). Acciones de EE.UU. convertidas con USD/MXN de Yahoo. "
                   "La beta usada alimenta la hoja NOTA; la beta calculada se muestra para comparar.", f.nota)
    ws.write("B5", "Tasa libre de riesgo, PRM y horizonte: hoja DASHBOARD.", f.nota)
    hw = _hw(wb); ws.set_row(CAP_R0 - 1, 42)
    hdr = ["Empresa", "Ticker", "Mercado", "Sector", "Moneda", "Precio", "Precio (MXN)", "Fecha de consulta", "Rend. del período",
           "Volatilidad anual", "Beta usada", "Beta vs IPC (calc.)", "Beta vs S&P 500", "Máx. drawdown", "Rend. esperado CAPM (horizonte)",
           "Rend. / volatilidad", "Correlación media", "Justificación cuantitativa"]
    for j, e in enumerate(hdr):
        ws.write(CAP_R0 - 1, 1 + j, e, hw)
    pfs = p["perfiles"]
    for j, pf in enumerate(pfs):
        ws.write(CAP_R0 - 1, 19 + j, f"$ {pf}", hw)
    c_per = 19 + len(pfs)
    ws.write(CAP_R0 - 1, c_per, "Perspectivas (análisis del equipo)", hw)
    simbolos = [a.get("simbolo", "") for a in acc]
    tick_corr = [s for s in simbolos if corr is not None and not corr.empty and s in corr.columns]
    m0 = CAP_R0 + n + 5  # fila de encabezado de la matriz de correlaciones
    for i, a in enumerate(acc):
        r, R = CAP_R0 + i, CAP_R0 + i + 1
        d = datos.get(a.get("simbolo"), {})
        ws.write(r, 1, a["nombre"], f.lab_r); ws.write(r, 2, a.get("simbolo", ""), f.txt); ws.write(r, 3, a.get("mercado", ""), f.txt)
        ws.write(r, 4, a.get("sector", ""), f.txt)
        ws.write(r, 5, d.get("moneda", "USD" if a.get("mercado") in ("NYSE", "NASDAQ") else "MXN"), f.txt_c)
        for c, k, fm_ in [(6, "precio", f.dato), (7, "precio MXN", f.dato), (9, "rend. período", f.pct), (10, "vol. anual", f.pct),
                          (12, "beta vs IPC", f.num4), (13, "beta vs S&P 500", f.num4), (14, "máx. drawdown", f.pct)]:
            v = d.get(k)
            if v is not None and not (isinstance(v, float) and np.isnan(v)):
                ws.write_number(r, c, float(v), fm_)
        if d.get("fecha"):
            ws.write(r, 8, d["fecha"], f.txt_c)
        else:
            ws.write(r, 8, "sin datos de mercado", f.nota)
        ws.write_number(r, 11, float(a["beta"]), f.num_in)
        ws.write_formula(r, 15, f"=({N}!$G$5+L{R}*{N}!$G$4)*{N}!$E$5/365", f.pct)
        ws.write_formula(r, 16, f'=IF(OR(J{R}="",K{R}=""),"",J{R}/K{R})', f.num)
        if a.get("simbolo") in tick_corr and len(tick_corr) > 1:
            k = tick_corr.index(a["simbolo"])
            fila_m = m0 + 2 + k
            ws.write_formula(r, 17, f"=(SUM({CELL(fila_m, 2)}:{CELL(fila_m, 1 + len(tick_corr))})-1)/{len(tick_corr) - 1}", f.num)
        ws.write_formula(r, 18, f'=IF(Q{R}="","β "&TEXT(L{R},"0.00")&": sensibilidad al mercado (capturada; sin datos de mercado)",'
                                f'"β "&TEXT(L{R},"0.00")&" · rend./vol. "&TEXT(Q{R},"0.00")&IF(R{R}="",""," · corr. media "&TEXT(R{R},"0.00"))'
                                f'&IF(AND(R{R}<>"",R{R}<0.3)," → aporta diversificación","")&IF(Q{R}>0.5," · buen rendimiento por riesgo",""))', f.txt)
        for j, pf in enumerate(pfs):
            ws.write_formula(r, 19 + j, f"={N}!{COL(8 + j)}{X['a0'] + 1 + i}", f.mon)
        ws.write(r, c_per, a.get("perspectivas") or "Capturar en la plataforma (pestaña 3)", f.txt if a.get("perspectivas") else f.nota)
    rt = CAP_R0 + n
    ws.write(rt, 1, "TOTAL / PROMEDIO", f.lab)
    ws.write_formula(rt, 11, f"=AVERAGE(L{CAP_R0 + 1}:L{rt})", f.num)
    for j in range(len(pfs)):
        c = COL(19 + j)
        ws.write_formula(rt, 19 + j, f"=SUM({c}{CAP_R0 + 1}:{c}{rt})", f.mon_b)
    ws.write(rt + 1, 1, "Beta ponderada", f.lab)
    for j in range(len(pfs)):
        c = COL(19 + j)
        ws.write_formula(rt + 1, 19 + j, f"=IF({c}{rt + 1}=0,0,SUMPRODUCT($L${CAP_R0 + 1}:$L${rt},{c}{CAP_R0 + 1}:{c}{rt})/{c}{rt + 1})", f.num)
    ws.write(rt + 2, 1, "CAPM: E[r] = (rf + β·PRM)·días/365. Rend./vol. = rendimiento del período entre volatilidad anual. Correlación media = "
                        "promedio de la correlación de rendimientos diarios con las demás acciones de la canasta.", f.nota)
    # Matriz de correlaciones
    ws.merge_range(m0, 1, m0, 2 + max(len(tick_corr), 1), "CORRELACIÓN DE RENDIMIENTOS DIARIOS", f.head)
    if len(tick_corr) > 1:
        for k, s in enumerate(tick_corr):
            ws.write(m0 + 1, 2 + k, s, f.head_t)
            ws.write(m0 + 2 + k, 1, s, f.lab_r)
            for j, s2 in enumerate(tick_corr):
                ws.write_number(m0 + 2 + k, 2 + j, float(corr.loc[s, s2]), f.num)
        ws.conditional_format(m0 + 2, 2, m0 + 1 + len(tick_corr), 1 + len(tick_corr),
                              {"type": "3_color_scale", "min_type": "num", "min_value": -1, "mid_type": "num", "mid_value": 0,
                               "max_type": "num", "max_value": 1, "min_color": "#2E86C1", "mid_color": "#FFFFFF", "max_color": "#C0392B"})
        # gráfica riesgo-rendimiento
        sc = wb.add_chart({"type": "scatter"})
        sc.add_series({"name": "Acciones", "categories": f"={q(H_CAP)}!$K${CAP_R0 + 1}:$K${rt}", "values": f"={q(H_CAP)}!$J${CAP_R0 + 1}:$J${rt}",
                       "marker": {"type": "circle", "size": 8, "fill": {"color": "#14B8C4"}, "border": {"color": "#0B1F3A"}},
                       "data_labels": {"value": False, "custom": [{"value": f"={q(H_CAP)}!$C${CAP_R0 + 1 + i}"} for i in range(n)]}})
        sc.set_title({"name": "Riesgo y rendimiento del período", "name_font": {"size": 11, "color": "#0B1F3A"}})
        sc.set_x_axis({"name": "Volatilidad anual", "num_format": "0%"}); sc.set_y_axis({"name": "Rendimiento del período", "num_format": "0%"})
        sc.set_legend({"none": True}); sc.set_size({"width": 560, "height": 320})
        ws.insert_chart(m0, 4 + len(tick_corr), sc)
    else:
        ws.write(m0 + 1, 1, "Sin series de precios suficientes: la plataforma calcula la matriz al descargar los datos de Yahoo.", f.nota)
    ws.set_column("A:A", 2); ws.set_column("B:B", 16); ws.set_column("C:C", 13); ws.set_column("D:F", 12); ws.set_column("G:R", 13)
    ws.set_column("S:S", 70); ws.set_column(19, c_per - 1, 15); ws.set_column(c_per, c_per, 60)
    return {"mercado": f"{q(H_CAP)}!$D${CAP_R0 + 1}:$D${rt}", "beta": f"{q(H_CAP)}!$L${CAP_R0 + 1}:$L${rt}", "rt": rt}


# ============================================================================ OPCIONES Y ESTRATEGIAS
ESTR = [  # clave, nombre, patas (tipo, strike, posición); strike: S, up, dn, p95, p105
    ("STRADDLE", "Straddle largo", [("CALL", "S", 1), ("PUT", "S", 1)]),
    ("STRANGLE", "Strangle largo", [("CALL", "up", 1), ("PUT", "dn", 1)]),
    ("COLLAR", "Collar", [("PUT", "p95", 1), ("CALL", "p105", -1)]),
    ("CAP", "Cap (call vendida)", [("CALL", "p105", -1)]),
    ("FLOOR", "Floor (put comprada)", [("PUT", "p95", 1)]),
    ("BUTTERFLY", "Butterfly con calls", [("CALL", "dn", 1), ("CALL", "S", -2), ("CALL", "up", 1)]),
]
CLAVE_NOTA = {"STRADDLE": "STRADDLE", "STRANGLE": "STG", "COLLAR": "COLLAR", "CAP": "CAP", "FLOOR": "FLOOR", "BUTTERFLY": "BTF"}


def hoja_opciones(wb, f, p, X, fecha_val: dt.date):
    ws = wb.add_worksheet(H_OPC)
    c = X["cel"]
    ws.merge_range("B2:R2", "OPCIONES — POSICIONES LONG/SHORT, ESTRATEGIAS Y STOP LOSS", f.bloque)
    params = [("Subyacente", p["derivados"]["nombre"], f.res), ("Precio actual S0", f"={N}!{c['Spot']}", f.num_v),
              ("Tasa libre de riesgo r (continua)", f"={N}!{c['r (continua)']}", f.pct_v), ("Dividendos q (continuo)", f"={N}!{c['q']}", f.pct_v),
              ("Volatilidad σ", f"={N}!{c['σ subyacente']}", f.pct_v), ("Tiempo T (años)", f"={N}!{c['T (años)']}", f.num4),
              ("Ancho de las alas", f"={N}!{c['Ancho alas']}", f.pct_v), ("Multiplicador", f"={N}!{c['Multiplicador']}", f.num_v),
              ("Fecha de valuación", fecha_val, f.fecha), ("Fecha de vencimiento", "=C12+" + f"{N}!$E$5", f.fecha)]
    for k, (lab, v, fm_) in enumerate(params):
        ws.write(3 + k, 1, lab, f.lab_r)
        if isinstance(v, str) and v.startswith("="):
            ws.write_formula(3 + k, 2, v, fm_)
        elif isinstance(v, dt.date):
            ws.write_datetime(3 + k, 2, dt.datetime.combine(v, dt.time()), f.fecha)
        else:
            ws.write(3 + k, 2, v, fm_)
    S, r_, qd, sg, T, an = "$C$5", "$C$6", "$C$7", "$C$8", "$C$9", "$C$10"
    ws.write("E4", "Primas teóricas con Black-Scholes (opciones europeas, vencimiento = horizonte de la nota). Resultados por unidad del "
                   "subyacente, sólo opciones (en la nota, las calls vendidas quedan cubiertas por la canasta de acciones).", f.nota)
    kx = {"S": S, "up": f"{S}*(1+{an})", "dn": f"{S}*(1-{an})", "p95": f"{S}*0.95", "p105": f"{S}*1.05"}
    # A. Posiciones básicas
    a0 = 15
    ws.merge_range(a0 - 1, 1, a0 - 1, 11, "A. POSICIONES BÁSICAS (strike = S0)", f.head)
    hw = _hw(wb); ws.set_row(a0, 30)
    for j, e in enumerate(["Posición", "Tipo", "Compra / venta", "Strike", "Prima BSM", "Prima pagada (−) / recibida (+)", "Pérdida máxima",
                           "Ganancia máxima", "Break-even", "Genera beneficio si", "Vencimiento"]):
        ws.write(a0, 1 + j, e, hw)
    basicas = [("Long call", "CALL", "Compra", 1), ("Short call", "CALL", "Venta", -1), ("Long put", "PUT", "Compra", 1), ("Short put", "PUT", "Venta", -1)]
    fb = {}
    for i, (nom, tipo, cv, pos) in enumerate(basicas):
        r, R = a0 + 1 + i, a0 + 2 + i
        fb[nom] = R
        ws.write(r, 1, nom, f.lab_r); ws.write(r, 2, tipo, f.txt_c); ws.write(r, 3, cv, f.txt_c)
        ws.write_formula(r, 4, f"={S}", f.num)
        ws.write_formula(r, 5, "=" + _bs(tipo, S, f"E{R}", T, r_, qd, sg), f.num4)
        ws.write_formula(r, 6, f"={-pos}*F{R}", f.num4)
        if tipo == "CALL":
            ws.write_formula(r, 9, f"=E{R}+F{R}", f.num)
        else:
            ws.write_formula(r, 9, f"=E{R}-F{R}", f.num)
        if nom == "Long call":
            ws.write_formula(r, 7, f"=-F{R}", f.num4); ws.write(r, 8, "Ilimitada", f.txt_c)
            ws.write_formula(r, 10, f'="S > "&TEXT(J{R},"#,##0.00")', f.txt)
        elif nom == "Short call":
            ws.write(r, 7, "Ilimitada", f.txt_c); ws.write_formula(r, 8, f"=F{R}", f.num4)
            ws.write_formula(r, 10, f'="S < "&TEXT(J{R},"#,##0.00")', f.txt)
        elif nom == "Long put":
            ws.write_formula(r, 7, f"=-F{R}", f.num4); ws.write_formula(r, 8, f"=E{R}-F{R}", f.num4)
            ws.write_formula(r, 10, f'="S < "&TEXT(J{R},"#,##0.00")', f.txt)
        else:
            ws.write_formula(r, 7, f"=-(E{R}-F{R})", f.num4); ws.write_formula(r, 8, f"=F{R}", f.num4)
            ws.write_formula(r, 10, f'="S > "&TEXT(J{R},"#,##0.00")', f.txt)
        ws.write_formula(r, 11, "=$C$13", f.fecha)
    # B. Estrategias
    b0 = a0 + 7
    ws.merge_range(b0 - 1, 1, b0 - 1, 18, "B. ESTRATEGIAS (STRADDLE, STRANGLE, COLLAR, CAP, FLOOR, BUTTERFLY)", f.head)
    hdr = ["Estrategia", "Objetivo financiero", "Conveniente cuando", "Pata", "Tipo", "Compra / venta", "Posición", "Strike", "Prima BSM",
           "Prima pagada (−) / recibida (+)", "Costo neto por unidad", "Pérdida máxima", "Ganancia máxima", "Break-even inferior",
           "Break-even superior", "Genera beneficio si", "Vencimiento", "¿La usa algún perfil?"]
    ws.set_row(b0, 30)
    for j, e in enumerate(hdr):
        ws.write(b0, 1 + j, e, hw)
    fe = {}
    usados = {p["config"][pf]["estrategia"] for pf in p["perfiles"]}
    for k, (clave, nom, legs) in enumerate(ESTR):
        base = b0 + 1 + 3 * k
        Rb = base + 1
        fe[clave] = (Rb, len(legs))
        obj, cuando = nt.CUANDO_CONVIENE.get(CLAVE_NOTA[clave], ("", ""))
        ws.write(base, 1, nom, f.lab_r); ws.write(base, 2, obj, f.txt); ws.write(base, 3, cuando, f.txt)
        for i, (tipo, kk, pos) in enumerate(legs):
            r, R = base + i, base + i + 1
            ws.write_number(r, 4, i + 1, f.ent)
            ws.write(r, 5, tipo, f.txt_c); ws.write(r, 6, "Compra" if pos > 0 else "Venta", f.txt_c)
            ws.write_number(r, 7, pos, f.ent_in)
            ws.write_formula(r, 8, f"={kx[kk]}", f.num)
            ws.write_formula(r, 9, "=" + _bs(tipo, S, f"I{R}", T, r_, qd, sg), f.num4)
            ws.write_formula(r, 10, f"=-H{R}*J{R}", f.num4)
        Rl = Rb + len(legs) - 1
        ws.write_formula(base, 11, f"=-SUM(K{Rb}:K{Rl})", f.num4)
        nC = f"L{Rb}"
        if clave in ("STRADDLE", "STRANGLE"):
            kc, kp = f"I{Rb}", f"I{Rb + 1}"
            ws.write_formula(base, 12, f"=-{nC}", f.num4); ws.write(base, 13, "Ilimitada", f.txt_c)
            ws.write_formula(base, 14, f"={kp}-{nC}", f.num); ws.write_formula(base, 15, f"={kc}+{nC}", f.num)
            ws.write_formula(base, 16, f'="S < "&TEXT(O{Rb},"#,##0.00")&" o S > "&TEXT(P{Rb},"#,##0.00")', f.txt)
        elif clave == "COLLAR":
            k1, k2 = f"I{Rb}", f"I{Rb + 1}"
            ws.write(base, 12, "Ilimitada sin subyacente (cubierta por la canasta)", f.txt)
            ws.write_formula(base, 13, f"={k1}-{nC}", f.num4)
            ws.write_formula(base, 14, f"=IF({nC}>0,{k1}-{nC},IF({nC}<0,{k2}-{nC},{k1}))", f.num)
            ws.write_formula(base, 16, f'=IF({nC}>0,"S < "&TEXT(O{Rb},"#,##0.00"),"S < "&TEXT(O{Rb},"#,##0.00")&" (con prima neta cobrada)")', f.txt)
        elif clave == "CAP":
            ws.write(base, 12, "Ilimitada sin subyacente (cubierta por la canasta)", f.txt)
            ws.write_formula(base, 13, f"=-{nC}", f.num4); ws.write_formula(base, 15, f"=I{Rb}-{nC}", f.num)
            ws.write_formula(base, 16, f'="S < "&TEXT(P{Rb},"#,##0.00")', f.txt)
        elif clave == "FLOOR":
            ws.write_formula(base, 12, f"=-{nC}", f.num4); ws.write_formula(base, 13, f"=I{Rb}-{nC}", f.num4)
            ws.write_formula(base, 14, f"=I{Rb}-{nC}", f.num)
            ws.write_formula(base, 16, f'="S < "&TEXT(O{Rb},"#,##0.00")', f.txt)
        else:  # BUTTERFLY
            k1, k2, k3 = f"I{Rb}", f"I{Rb + 1}", f"I{Rb + 2}"
            ws.write_formula(base, 12, f"=-{nC}", f.num4); ws.write_formula(base, 13, f"=({k2}-{k1})-{nC}", f.num4)
            ws.write_formula(base, 14, f"={k1}+{nC}", f.num); ws.write_formula(base, 15, f"={k3}-{nC}", f.num)
            ws.write_formula(base, 16, f'=TEXT(O{Rb},"#,##0.00")&" < S < "&TEXT(P{Rb},"#,##0.00")', f.txt)
        ws.write_formula(base, 17, "=$C$13", f.fecha)
        quien = [pf for pf in p["perfiles"] if p["config"][pf]["estrategia"] == CLAVE_NOTA[clave]]
        ws.write(base, 18, ", ".join(quien) if quien else "—", f.txt)
    nfin = b0 + 1 + 3 * len(ESTR)
    ws.write(nfin, 1, "Costo neto > 0 = prima pagada; < 0 = prima recibida. El collar con 1 unidad del subyacente queda acotado entre K_put − S0 − costo "
                      "y K_call − S0 − costo, con break-even en S0 + costo. CALL comprada: ver posiciones básicas.", f.nota)
    # C. Stop loss
    c0 = nfin + 3
    ws.merge_range(c0 - 1, 1, c0 - 1, 8, "C. STOP LOSS (control de pérdidas)", f.head)
    for j, e in enumerate(["Perfil", "Stop-loss", "Nivel de salida del subyacente", "Pérdida máx. por unidad", "Nocional de futuros (MXN)",
                           "Pérdida máx. estimada en futuros (MXN)", "Comentario"]):
        ws.write(c0, 1 + j, e, hw)
    ws.set_row(c0, 30)
    for k, pf in enumerate(p["perfiles"]):
        r, R = c0 + 1 + k, c0 + 2 + k
        ws.write(r, 1, pf, f.lab_r)
        ws.write_formula(r, 2, f"={N}!$M${X['fdiv'][pf] + 1}", f.pct_v)
        ws.write_formula(r, 3, f"={S}*(1-C{R})", f.num)
        ws.write_formula(r, 4, f"={S}*C{R}", f.num4)
        ws.write_formula(r, 5, f"={X['fut'][pf]['nocional']}", f.mon)
        ws.write_formula(r, 6, f"=-F{R}*C{R}", f.mon)
        ws.write(r, 7, "Orden hipotética: con brechas de precio la ejecución puede ser peor (deslizamiento).", f.nota)
    # D. Malla de resultados al vencimiento
    g0 = c0 + len(p["perfiles"]) + 4
    npts = 41
    ws.merge_range(g0 - 1, 1, g0 - 1, 1 + npts, "D. RESULTADO AL VENCIMIENTO POR UNIDAD (precio del subyacente de −30% a +30%)", f.head)
    ws.write(g0, 1, "S al vencimiento", f.head_t)
    for k in range(npts):
        ws.write_formula(g0, 2 + k, f"={S}*(0.7+0.015*{k})", f.num)
    filas_g = {}
    nombres = [b[0] for b in basicas] + [e[1] for e in ESTR]
    for i, nom in enumerate(nombres):
        r = g0 + 1 + i
        filas_g[nom] = r + 1
        ws.write(r, 1, nom, f.lab_r)
        for k in range(npts):
            Sx = f"{COL(2 + k)}${g0 + 1}"
            if i < 4:
                Rb = fb[nom]
                pos = basicas[i][3]
                pay = f"MAX({Sx}-$E${Rb},0)" if basicas[i][1] == "CALL" else f"MAX($E${Rb}-{Sx},0)"
                fo = f"={pos}*({pay}-$F${Rb})"
            else:
                clave = ESTR[i - 4][0]
                Rb, nl = fe[clave]
                partes = []
                for j in range(nl):
                    tipo = ESTR[i - 4][2][j][0]
                    pay = f"MAX({Sx}-$I${Rb + j},0)" if tipo == "CALL" else f"MAX($I${Rb + j}-{Sx},0)"
                    partes.append(f"$H${Rb + j}*({pay}-$J${Rb + j})")
                fo = "=" + "+".join(partes)
            ws.write_formula(r, 2 + k, fo, f.num)
    # gráficas
    cats = f"={q(H_OPC)}!$C${g0 + 1}:${COL(1 + npts)}${g0 + 1}"
    ch = _chart(wb, "line", "Posiciones básicas (LONG/SHORT CALL y PUT)", 520, 280)
    for k, nom in enumerate(nombres[:4]):
        R = filas_g[nom]
        ch.add_series({"name": nom, "categories": cats, "values": f"={q(H_OPC)}!$C${R}:${COL(1 + npts)}${R}", "line": {"color": COLORES[k], "width": 2}})
    ch.set_x_axis({"num_format": "#,##0", "interval_unit": 10, "name": "S al vencimiento", "label_position": "low", "num_font": {"rotation": 0, "size": 8}})
    ch.set_y_axis({"major_gridlines": {"visible": True, "line": {"color": "#E0E0E0"}}})
    graf0 = g0 + len(nombres) + 3
    ws.insert_chart(graf0, 1, ch)
    for k, (clave, nom, _) in enumerate(ESTR):
        R = filas_g[nom]
        g = _chart(wb, "line", f"{nom}: resultado al vencimiento", 520, 280)
        g.add_series({"name": nom, "categories": cats, "values": f"={q(H_OPC)}!$C${R}:${COL(1 + npts)}${R}",
                      "line": {"color": COLORES[(k + 1) % 6], "width": 2.25}})
        g.set_legend({"none": True})
        g.set_x_axis({"num_format": "#,##0", "interval_unit": 10, "name": "S al vencimiento", "label_position": "low", "num_font": {"rotation": 0, "size": 8}})
        g.set_y_axis({"major_gridlines": {"visible": True, "line": {"color": "#E0E0E0"}}})
        pos = k + 1
        ws.insert_chart(graf0 + 15 * (pos // 3), 1 + 8 * (pos % 3), g)
    ws.set_column("A:A", 2); ws.set_column("B:B", 22); ws.set_column("C:C", 34); ws.set_column("D:D", 34); ws.set_column("E:L", 13)
    ws.set_column("M:N", 20); ws.set_column("O:P", 13); ws.set_column("Q:Q", 26); ws.set_column("R:S", 14); ws.set_column("T:AQ", 9)
    return {"S": f"{q(H_OPC)}!$C$5", "r": f"{q(H_OPC)}!$C$6", "q": f"{q(H_OPC)}!$C$7", "sg": f"{q(H_OPC)}!$C$8", "T": f"{q(H_OPC)}!$C$9"}


# ============================================================================ BLACK-SCHOLES
def hoja_black_scholes(wb, f, O):
    ws = wb.add_worksheet(H_BSM)
    ws.merge_range("B2:F2", "BLACK-SCHOLES — CÁLCULO AUTOMATIZADO DE PRIMAS", f.bloque)
    ws.write("B3", "Opción europea sobre el subyacente de la nota. K editable (por omisión, at-the-money).", f.nota)
    ent = [("Precio actual del subyacente S", f"={O['S']}", f.num_v), ("Precio de ejercicio K", "=C5", f.num_in),
           ("Tiempo al vencimiento T (años)", f"={O['T']}", f.num4), ("Tasa libre de riesgo r (continua)", f"={O['r']}", f.pct_v),
           ("Dividendos q (continuo)", f"={O['q']}", f.pct_v), ("Volatilidad σ", f"={O['sg']}", f.pct_v)]
    ws.write("B4", "Variable", f.head); ws.write("C4", "Valor", f.head); ws.write("D4", "Fórmula / sustitución", f.head)
    for k, (lab, fo, fm_) in enumerate(ent):
        ws.write(4 + k, 1, lab, f.lab_r); ws.write_formula(4 + k, 2, fo, fm_)
    pasos = [
        ("ln(S/K)", "=LN(C5/C6)", f.num6, '="ln("&TEXT(C5,"0.00")&" / "&TEXT(C6,"0.00")&")"'),
        ("(r − q + σ²/2)·T", "=(C8-C9+C10^2/2)*C7", f.num6, '="("&TEXT(C8,"0.0000")&" − "&TEXT(C9,"0.0000")&" + "&TEXT(C10,"0.0000")&"²/2) × "&TEXT(C7,"0.0000")'),
        ("σ·√T", "=C10*SQRT(C7)", f.num6, '=TEXT(C10,"0.0000")&" × √"&TEXT(C7,"0.0000")'),
        ("d1", "=(C12+C13)/C14", f.num6, '="d1 = ("&TEXT(C12,"0.000000")&" + "&TEXT(C13,"0.000000")&") / "&TEXT(C14,"0.000000")'),
        ("d2", "=C15-C14", f.num6, '="d2 = d1 − σ√T = "&TEXT(C15,"0.000000")&" − "&TEXT(C14,"0.000000")'),
        ("N(d1)", "=NORMSDIST(C15)", f.num6, '="Normal estándar acumulada en "&TEXT(C15,"0.0000")'),
        ("N(d2)", "=NORMSDIST(C16)", f.num6, '="Normal estándar acumulada en "&TEXT(C16,"0.0000")'),
        ("N(−d1)", "=NORMSDIST(-C15)", f.num6, '="1 − N(d1)"'),
        ("N(−d2)", "=NORMSDIST(-C16)", f.num6, '="1 − N(d2)"'),
        ("e^(−qT)", "=EXP(-C9*C7)", f.num6, '="Descuento por dividendos"'),
        ("e^(−rT)", "=EXP(-C8*C7)", f.num6, '="Factor de descuento"'),
        ("PRIMA CALL", "=C5*C21*C17-C6*C22*C18", f.res4,
         '="C = "&TEXT(C5,"0.00")&"·"&TEXT(C21,"0.0000")&"·"&TEXT(C17,"0.0000")&" − "&TEXT(C6,"0.00")&"·"&TEXT(C22,"0.0000")&"·"&TEXT(C18,"0.0000")'),
        ("PRIMA PUT", "=C6*C22*C20-C5*C21*C19", f.res4,
         '="P = "&TEXT(C6,"0.00")&"·"&TEXT(C22,"0.0000")&"·"&TEXT(C20,"0.0000")&" − "&TEXT(C5,"0.00")&"·"&TEXT(C21,"0.0000")&"·"&TEXT(C19,"0.0000")'),
        ("Paridad: C − P", "=C23-C24", f.num6, '="Debe igualar S·e^(−qT) − K·e^(−rT)"'),
        ("S·e^(−qT) − K·e^(−rT)", "=C5*C21-C6*C22", f.num6, '="Diferencia: "&TEXT(C25-C26,"0.0000000")'),
    ]
    for k, (lab, fo, fm_, txt) in enumerate(pasos):
        r = 11 + k
        ws.write(r, 1, lab, f.lab_r); ws.write_formula(r, 2, fo, fm_); ws.write_formula(r, 3, txt, f.txt)
    # Griegas
    g0 = 28
    ws.merge_range(g0, 1, g0, 5, "SENSIBILIDADES (GRIEGAS)", f.head)
    for j, e in enumerate(["Griega", "Call", "Put", "Interpretación"]):
        ws.write(g0 + 1, 1 + j, e, f.head_t)
    nd1 = "(EXP(-C15^2/2)/SQRT(2*PI()))"
    gr = [("Delta", "=C21*C17", "=C21*(C17-1)", "Cambio de la prima por $1 de cambio en S"),
          ("Gamma", f"=C21*{nd1}/(C5*C14)", f"=C21*{nd1}/(C5*C14)", "Cambio de la delta por $1 de cambio en S"),
          ("Vega (por 1 punto de σ)", f"=C5*C21*{nd1}*SQRT(C7)/100", f"=C5*C21*{nd1}*SQRT(C7)/100", "Más volatilidad encarece calls y puts"),
          ("Theta (por día)", f"=(-C5*C21*{nd1}*C10/(2*SQRT(C7))-C8*C6*C22*C18+C9*C5*C21*C17)/365",
           f"=(-C5*C21*{nd1}*C10/(2*SQRT(C7))+C8*C6*C22*C20-C9*C5*C21*C19)/365", "El paso del tiempo reduce el valor (valor tiempo)"),
          ("Rho (por 1 punto de r)", "=C6*C7*C22*C18/100", "=-C6*C7*C22*C20/100", "Tasas más altas suben la call y bajan la put")]
    for k, (lab, fc, fp, txt) in enumerate(gr):
        r = g0 + 2 + k
        ws.write(r, 1, lab, f.lab_r); ws.write_formula(r, 2, fc, f.num6); ws.write_formula(r, 3, fp, f.num6); ws.write(r, 4, txt, f.txt)
    # Sensibilidad de la prima
    s0 = g0 + 9
    ws.merge_range(s0, 1, s0, 7, "¿CÓMO CAMBIA LA PRIMA? (una variable a la vez)", f.head)
    for j, e in enumerate(["Variable", "Cambio", "Valor usado", "Call", "Put", "Δ call vs base", "Δ put vs base"]):
        ws.write(s0 + 1, 1 + j, e, f.head_t)
    casos = [("Volatilidad", "σ − 10 pts", "=MAX(C10-0.1,0.01)", "sg"), ("Volatilidad", "σ + 10 pts", "=C10+0.1", "sg"),
             ("Tiempo", "T × 0.5", "=C7*0.5", "T"), ("Tiempo", "T × 2", "=C7*2", "T"),
             ("Subyacente", "S − 10%", "=C5*0.9", "S"), ("Subyacente", "S + 10%", "=C5*1.1", "S"),
             ("Tasa", "r − 1 pt", "=C8-0.01", "r"), ("Tasa", "r + 1 pt", "=C8+0.01", "r")]
    for k, (var, cam, val, cual) in enumerate(casos):
        r, R = s0 + 2 + k, s0 + 3 + k
        args = {"S": "C5", "T": "C7", "r": "C8", "sg": "C10"}
        args[cual] = f"D{R}"
        ws.write(r, 1, var, f.lab_r); ws.write(r, 2, cam, f.txt); ws.write_formula(r, 3, val, f.num4)
        ws.write_formula(r, 4, "=" + _bs("CALL", args["S"], "C6", args["T"], args["r"], "C9", args["sg"]), f.num4)
        ws.write_formula(r, 5, "=" + _bs("PUT", args["S"], "C6", args["T"], args["r"], "C9", args["sg"]), f.num4)
        ws.write_formula(r, 6, f"=E{R}-$C$23", f.num4); ws.write_formula(r, 7, f"=F{R}-$C$24", f.num4)
    ws.write(s0 + 11, 1, "Lectura: más volatilidad o más tiempo encarecen ambas opciones; un subyacente más alto sube la call y baja la put; "
                         "una tasa más alta sube la call y baja la put (el strike se descuenta más).", f.nota)
    # Prima contra S y contra σ (gráficas)
    p0 = s0 + 14
    ws.merge_range(p0, 1, p0, 4, "PRIMA CONTRA EL PRECIO DEL SUBYACENTE", f.head)
    ws.merge_range(p0, 6, p0, 9, "PRIMA CONTRA LA VOLATILIDAD", f.head)
    for j, e in enumerate(["S", "Call", "Put"]):
        ws.write(p0 + 1, 1 + j, e, f.head_t)
    for j, e in enumerate(["σ", "Call", "Put"]):
        ws.write(p0 + 1, 6 + j, e, f.head_t)
    for k in range(11):
        r, R = p0 + 2 + k, p0 + 3 + k
        ws.write_formula(r, 1, f"=$C$5*(0.75+0.05*{k})", f.num)
        ws.write_formula(r, 2, "=" + _bs("CALL", f"B{R}", "$C$6", "$C$7", "$C$8", "$C$9", "$C$10"), f.num4)
        ws.write_formula(r, 3, "=" + _bs("PUT", f"B{R}", "$C$6", "$C$7", "$C$8", "$C$9", "$C$10"), f.num4)
        ws.write_formula(r, 6, f"=0.1+0.05*{k}", f.pct)
        ws.write_formula(r, 7, "=" + _bs("CALL", "$C$5", "$C$6", "$C$7", "$C$8", "$C$9", f"G{R}"), f.num4)
        ws.write_formula(r, 8, "=" + _bs("PUT", "$C$5", "$C$6", "$C$7", "$C$8", "$C$9", f"G{R}"), f.num4)
    for titulo, cx, cy, pos, fmt in [("Prima vs S", "B", ("C", "D"), (p0 + 14, 1), "#,##0"), ("Prima vs σ", "G", ("H", "I"), (p0 + 14, 6), "0%")]:
        ch = _chart(wb, "line", titulo, 480, 280)
        for k, (cc, nom) in enumerate(zip(cy, ["Call", "Put"])):
            ch.add_series({"name": nom, "categories": f"={q(H_BSM)}!${cx}${p0 + 3}:${cx}${p0 + 13}",
                           "values": f"={q(H_BSM)}!${cc}${p0 + 3}:${cc}${p0 + 13}", "line": {"color": COLORES[k + 1], "width": 2.25}})
        ch.set_x_axis({"num_format": fmt, "label_position": "low"})
        ws.insert_chart(pos[0], pos[1], ch)
    ws.set_column("A:A", 2); ws.set_column("B:B", 30); ws.set_column("C:C", 16); ws.set_column("D:D", 62); ws.set_column("E:E", 46)
    ws.set_column("F:I", 14)


# ============================================================================ DIVERSIFICACIÓN
def hoja_diversificacion(wb, f, p, X):
    ws = wb.add_worksheet(H_DIV)
    pfs = p["perfiles"]
    ws.merge_range("B2:L2", "DIVERSIFICACIÓN — DISTRIBUCIÓN PORCENTUAL Y MONETARIA DEL CAPITAL", f.bloque)
    hdr = ["Perfil", "Renta fija $", "Capitales $", "Futuros (garantía) $", "Opciones (primas) $", "Total $", "Diferencia vs inversión",
           "% renta fija", "% capitales", "% futuros", "% opciones"]
    hw = _hw(wb); ws.set_row(3, 30)
    for j, e in enumerate(hdr):
        ws.write(3, 1 + j, e, hw)
    for k, pf in enumerate(pfs):
        r, R = 4 + k, 5 + k
        Rk, Rd = X["fila"][pf] + 1, X["fdiv"][pf] + 1
        ws.write(r, 1, pf, f.lab_r)
        for j, fo in enumerate([f"={N}!$F${Rk}", f"={N}!$G${Rd}", f"={N}!$J${Rd}", f"={N}!$K${Rd}"]):
            ws.write_formula(r, 2 + j, fo, f.mon)
        ws.write_formula(r, 6, f"=SUM(C{R}:F{R})", f.mon_b)
        ws.write_formula(r, 7, f"=G{R}-{N}!$E$4", f.mon)
        for j, c in enumerate("CDEF"):
            ws.write_formula(r, 8 + j, f"={c}{R}/$G{R}", f.pct)
    a, b = 5, 4 + len(pfs)
    ws.write(b, 1, "La diferencia debe ser 0: todo el capital queda asignado. El sobrante del tope de primas se suma a la renta fija.", f.nota)
    # Capitales por mercado
    m0 = b + 3
    A, B = X["a0"] + 1, X["a0"] + X["n_acc"]
    ws.merge_range(m0, 1, m0, 5, "CAPITALES POR MERCADO", f.head)
    for j, e in enumerate(["Perfil", "México (BMV/BIVA) $", "EE.UU. (NYSE/NASDAQ) $", "% EE.UU."]):
        ws.write(m0 + 1, 1 + j, e, f.head_t)
    for k, pf in enumerate(pfs):
        r, R = m0 + 2 + k, m0 + 3 + k
        L = COL(8 + k)
        ws.write(r, 1, pf, f.lab_r)
        ws.write_formula(r, 2, f'=SUMPRODUCT((({N}!$E${A}:$E${B}="BMV")+({N}!$E${A}:$E${B}="BIVA"))*{N}!{L}${A}:{L}${B})', f.mon)
        ws.write_formula(r, 3, f'=SUMPRODUCT((({N}!$E${A}:$E${B}="NYSE")+({N}!$E${A}:$E${B}="NASDAQ"))*{N}!{L}${A}:{L}${B})', f.mon)
        ws.write_formula(r, 4, f"=IF(C{R}+D{R}=0,0,D{R}/(C{R}+D{R}))", f.pct)
    # Capitales por sector
    sectores = sorted({a.get("sector", "") for a in p["acciones"] if a.get("sector")})
    s0 = m0 + len(pfs) + 4
    ws.merge_range(s0, 1, s0, 1 + len(pfs), "CAPITALES POR SECTOR ($)", f.head)
    ws.write(s0 + 1, 1, "Sector", f.head_t)
    for k, pf in enumerate(pfs):
        ws.write(s0 + 1, 2 + k, pf, f.head_t)
    for i, sec in enumerate(sectores):
        r = s0 + 2 + i
        ws.write(r, 1, sec, f.lab_r)
        for k in range(len(pfs)):
            L = COL(8 + k)
            ws.write_formula(r, 2 + k, f"=SUMIF({N}!$F${A}:$F${B},$B{r + 1},{N}!{L}${A}:{L}${B})", f.mon)
    # Futuros por clase de activo
    clases = ["Índice bursátil", "Divisa", "Tasa de interés", "Energético", "Metal", "Materia prima agrícola"]
    f0 = s0 + len(sectores) + 4
    ws.merge_range(f0, 1, f0, 1 + len(pfs), "FUTUROS POR CLASE DE ACTIVO (garantía depositada, $)", f.head)
    ws.write(f0 + 1, 1, "Clase", f.head_t)
    for k, pf in enumerate(pfs):
        ws.write(f0 + 1, 2 + k, pf, f.head_t)
    for i, cl in enumerate(clases):
        r = f0 + 2 + i
        ws.write(r, 1, cl, f.lab_r)
        for k, pf in enumerate(pfs):
            r1, r2 = X["fut"][pf]["rango"]
            fo = f"=SUMIF({q(H_FUT)}!$M${r1}:$M${r2},$B{r + 1},{q(H_FUT)}!$F${r1}:$F${r2})" if r2 >= r1 else "=0"
            ws.write_formula(r, 2 + k, fo, f.mon)
    # gráficas
    cc = _chart(wb, "bar", "Distribución del capital por perfil", 560, 300, "percent_stacked")
    for k, (lab, c) in enumerate([("Renta fija", "C"), ("Capitales", "D"), ("Futuros", "E"), ("Opciones", "F")]):
        cc.add_series({"name": lab, "categories": f"={q(H_DIV)}!$B${a}:$B${b}", "values": f"={q(H_DIV)}!${c}${a}:${c}${b}", "fill": {"color": COLORES[k]}})
    ws.insert_chart("N4", cc)
    pf = _pf_rec(p)
    rr = 5 + pfs.index(pf)
    pie = _chart(wb, "doughnut", f"Propuesta {pf}", 420, 300)
    pie.add_series({"name": pf, "categories": f"={q(H_DIV)}!$C$4:$F$4", "values": f"={q(H_DIV)}!$C${rr}:$F${rr}",
                    "points": [{"fill": {"color": c}} for c in COLORES[:4]], "data_labels": {"percentage": True}})
    ws.insert_chart("N20", pie)
    cm_ = _chart(wb, "column", "Capitales: México vs EE.UU.", 480, 280, "stacked")
    for k, (lab, c) in enumerate([("México", "C"), ("EE.UU.", "D")]):
        cm_.add_series({"name": lab, "categories": f"={q(H_DIV)}!$B${m0 + 3}:$B${m0 + 2 + len(pfs)}",
                        "values": f"={q(H_DIV)}!${c}${m0 + 3}:${c}${m0 + 2 + len(pfs)}", "fill": {"color": COLORES[k + 1]}})
    cm_.set_y_axis({"num_format": '"$"#,##0'})
    ws.insert_chart("N36", cm_)
    ws.set_column("A:A", 2); ws.set_column("B:B", 24); ws.set_column("C:L", 17)
    return {"fila": {pf: 5 + k for k, pf in enumerate(pfs)}, "mercado": {pf: m0 + 3 + k for k, pf in enumerate(pfs)}}


# ============================================================================ ESCENARIOS
def hoja_escenarios(wb, f, p, X):
    ws = wb.add_worksheet(H_ESC)
    pfs = p["perfiles"]
    ws.merge_range(1, 1, 1, 4 + 2 * len(pfs), "ESCENARIOS — ADVERSOS, NEUTRAL Y OPTIMISTAS (hipótesis sin probabilidad asignada)", f.bloque)
    hdr = ["Escenario", "z (σ)", "Δ tasas (pb)", "S subyacente"]
    for j, e in enumerate(hdr):
        ws.write(3, 1 + j, e, f.head)
    for k, pf in enumerate(pfs):
        ws.write(3, 5 + 2 * k, f"NE $ {pf}", f.head)
        ws.write(3, 6 + 2 * k, f"NE % {pf}", f.head)
    pf0 = pfs[0]
    for i, (nombre, z) in enumerate(nt.ESCENARIOS_Z):
        r = 4 + i
        R0 = X["filas_ne"][pf0][i]
        ws.write(r, 1, nombre, f.lab_r)
        ws.write_formula(r, 2, f"={N}!$F${R0}", f.num)
        ws.write_formula(r, 3, f"={N}!$G${R0}", f.num)
        ws.write_formula(r, 4, f"={N}!$H${R0}", f.num)
        for k, pf in enumerate(pfs):
            Rn = X["filas_ne"][pf][i]
            ws.write_formula(r, 5 + 2 * k, f"={N}!$M${Rn}", f.mon)
            ws.write_formula(r, 6 + 2 * k, f"={N}!$O${Rn}", f.pct_b)
    e_a, e_b = 5, 9
    for k in range(len(pfs)):
        ws.conditional_format(4, 6 + 2 * k, 8, 6 + 2 * k, {"type": "3_color_scale", "min_color": "#F1948A", "mid_color": "#FFFFFF", "max_color": "#82E0AA",
                                                           "mid_type": "num", "mid_value": 0})
    # Rendimiento potencial y pérdida posible
    r0 = 11
    ws.merge_range(r0, 1, r0, 6, "RENDIMIENTO POTENCIAL Y PÉRDIDA POSIBLE", f.head)
    for j, e in enumerate(["Perfil", "Mejor NE %", "Neutral NE %", "Peor NE %", "Rango (mejor − peor)", "Tolerancia / ¿dentro?"]):
        ws.write(r0 + 1, 1 + j, e, f.head_t)
    for k, pf in enumerate(pfs):
        r, R = r0 + 2 + k, r0 + 3 + k
        c = COL(6 + 2 * k)
        ws.write(r, 1, pf, f.lab_r)
        ws.write_formula(r, 2, f"=MAX({c}{e_a}:{c}{e_b})", f.pct)
        ws.write_formula(r, 3, f"={c}{e_a + 2}", f.pct)
        ws.write_formula(r, 4, f"=MIN({c}{e_a}:{c}{e_b})", f.pct)
        ws.write_formula(r, 5, f"=C{R}-E{R}", f.pct)
        ws.write_formula(r, 6, f"={q(H_PERFIL)}!$E$23" if pf == "PERSONALIZADO" else f"={N}!$P${X['ficha'][pf] + 1}", f.pct if pf == "PERSONALIZADO" else f.txt_c)
    ws.write(r0 + 3 + len(pfs), 1, "Para los perfiles de referencia se muestra si el escenario adverso moderado queda dentro de la tolerancia del cliente.", f.nota)
    # Desglose de la propuesta
    pf = _pf_rec(p)
    d0 = r0 + len(pfs) + 6
    ws.merge_range(d0, 1, d0, 7, f"DESGLOSE POR COMPONENTE — {pf}", f.head)
    for j, e in enumerate(["Escenario", "Renta fija", "Capitales", "Futuros", "Opciones", "NE", "Condiciones"]):
        ws.write(d0 + 1, 1 + j, e, f.head_t)
    for i, (nombre, z) in enumerate(nt.ESCENARIOS_Z):
        r, R = d0 + 2 + i, d0 + 3 + i
        Rn = X["filas_ne"][pf][i]
        ws.write(r, 1, nombre, f.lab_r)
        for j, c in enumerate("IJKLM"):
            ws.write_formula(r, 2 + j, f"={N}!${c}${Rn}", f.mon_b if c == "M" else f.mon)
        ws.write_formula(r, 7, f'="Tasas "&TEXT(D{5 + i},"+0;-0;0")&" pb · subyacente "&TEXT(E{5 + i},"#,##0.00")&" · IPC "&TEXT(C{5 + i},"+0.0;-0.0;0")&" σ"', f.txt)
    ws.write(d0 + 8, 1, "Renta fija: KRF·(1 + rend. al horizonte − duración·Δtasas). Acciones: rend. CAPM + β·z·σ_IPC·√T. Subyacente: S0·e^(μ + zσ√T). "
                        "Futuros: en escenarios adversos el movimiento va en contra de cada posición, con stop-loss.", f.nota)
    lc = _chart(wb, "line", "NE % por escenario y perfil", 600, 300)
    for k, pf_ in enumerate(pfs):
        c = COL(6 + 2 * k)
        lc.add_series({"name": pf_, "categories": f"={q(H_ESC)}!$B${e_a}:$B${e_b}", "values": f"={q(H_ESC)}!${c}${e_a}:${c}${e_b}",
                       "line": {"color": COLORES[k % 6], "width": 2.25}, "marker": {"type": "circle"}})
    lc.set_x_axis({"label_position": "low"})
    lc.set_y_axis({"num_format": "0%", "major_gridlines": {"visible": True, "line": {"color": "#E0E0E0"}}})
    ws.insert_chart(3, 7 + 2 * len(pfs), lc)
    bc = _chart(wb, "column", f"Contribución por componente — {pf}", 600, 300, "stacked")
    for k, (lab, c) in enumerate([("Renta fija", "C"), ("Capitales", "D"), ("Futuros", "E"), ("Opciones", "F")]):
        bc.add_series({"name": lab, "categories": f"={q(H_ESC)}!$B${d0 + 3}:$B${d0 + 7}", "values": f"={q(H_ESC)}!${c}${d0 + 3}:${c}${d0 + 7}",
                       "fill": {"color": COLORES[k]}})
    bc.set_y_axis({"num_format": '"$"#,##0'})
    ws.insert_chart(d0, 9, bc)
    ws.set_column("A:A", 2); ws.set_column("B:B", 22); ws.set_column("C:E", 13); ws.set_column("F:O", 16); ws.set_column("H:H", 60)
    return (e_a, e_b)


# ============================================================================ REPORTE EJECUTIVO
def hoja_reporte(wb, f, p, X, D, fecha_val: dt.date):
    ws = wb.add_worksheet(H_REP)
    pf = _pf_rec(p)
    R, Rd, Rf = X["fila"][pf] + 1, X["fdiv"][pf] + 1, X["ficha"][pf] + 1
    fl = X["filas_ne"][pf]
    Rdiv = D["fila"][pf]
    Rm = D["mercado"][pf]
    srow = _rf_sel_row(p, pf)
    dv = q(H_DIV)
    ws.merge_range("B2:F2", "REPORTE EJECUTIVO DE LA NOTA ESTRUCTURADA", f.bloque)
    ws.write("B3", "Fecha de elaboración", f.lab_r); ws.write_datetime("C3", dt.datetime.combine(fecha_val, dt.time()), f.fecha)
    secciones = [
        ("1. CLIENTE", [("Monto a invertir", f"={N}!$E$4", f.mon), ("Horizonte (días)", f"={N}!$E$5", f.ent),
                        ("Puntaje de riesgo", f"={q(H_PERFIL)}!$E$17", f.num4), ("Perfil de referencia", f"={q(H_PERFIL)}!$E$18", f.txt),
                        ("Objetivo de rendimiento anual", f"={q(H_PERFIL)}!$E$26", f.pct), ("Pérdida máxima tolerada", f"={q(H_PERFIL)}!$E$23", f.pct)]),
        (f"2. COMPOSICIÓN PROPUESTA ({pf})", [("Renta fija", f"={dv}!$C${Rdiv}", f.mon, f"={dv}!$I${Rdiv}"),
                                               ("Capitales", f"={dv}!$D${Rdiv}", f.mon, f"={dv}!$J${Rdiv}"),
                                               ("Futuros (garantía)", f"={dv}!$E${Rdiv}", f.mon, f"={dv}!$K${Rdiv}"),
                                               ("Opciones (primas)", f"={dv}!$F${Rdiv}", f.mon, f"={dv}!$L${Rdiv}")]),
        ("3. INSTRUMENTOS", [("Renta fija elegida", f"={N}!$G${R}", f.txt), ("Rendimiento de la renta fija al horizonte", f"={N}!$H${R}", f.pct),
                             ("Justificación", f"={q(H_RF)}!$J${srow}", f.txt),
                             ("Acciones de México / EE.UU. ($)", f'=TEXT({dv}!$C${Rm},"$#,##0")&" / "&TEXT({dv}!$D${Rm},"$#,##0")', f.txt),
                             ("Beta ponderada de la canasta", f"={q(H_CAP)}!{COL(19 + p['perfiles'].index(pf))}{D['cap_rt'] + 2}", f.num),
                             ("Contratos de futuros / nocional", f'=TEXT({X["fut"][pf]["contratos"]},"0")&" contratos · nocional "&TEXT({X["fut"][pf]["nocional"]},"$#,##0")', f.txt),
                             ("Estrategia de opciones / contratos", f'={N}!$L${Rd}&" · "&TEXT({N}!$M${X["fila_opc"][pf]},"0")&" contratos"', f.txt)]),
        ("4. RESULTADOS ESTIMADOS", [("Resultado neto base", f"={N}!$N${R}", f.mon), ("Rendimiento en el horizonte (base)", f"={N}!$O${R}", f.pct),
                                     ("Rendimiento anualizado (base)", f"={N}!$P${R}", f.pct), ("Mejor escenario", f"=MAX({N}!$M${fl[0]}:$M${fl[-1]})", f.mon),
                                     ("Peor escenario", f"={N}!$L${Rf}", f.mon), ("Piso por renta fija", f"={N}!$F${Rf}", f.pct),
                                     ("Protección del capital", f"={N}!$H${Rf}", f.txt), ("¿Cumple el objetivo?", f"={N}!$N${Rf}", f.txt_c),
                                     ("¿Pérdida dentro de la tolerancia?", f"={N}!$P${Rf}", f.txt_c)]),
    ]
    r = 4
    celdas = {}
    for titulo, filas in secciones:
        ws.merge_range(r, 1, r, 5, titulo, f.head)
        r += 1
        for fila in filas:
            lab, fo, fm_ = fila[:3]
            ws.write(r, 1, lab, f.lab_r)
            if lab == "Justificación":
                ws.merge_range(r, 2, r, 5, "", f.txt)
            ws.write_formula(r, 2, fo, fm_)
            if len(fila) > 3:
                ws.write_formula(r, 3, fila[3], f.pct)
            celdas[lab] = f"C{r + 1}"
            r += 1
        r += 1
    ws.merge_range(r, 1, r, 5, "5. RECOMENDACIÓN", f.head)
    cu, to = celdas["¿Cumple el objetivo?"], celdas["¿Pérdida dentro de la tolerancia?"]
    rec = (f'=IF(AND({cu}="SÍ",{to}="SÍ"),"Se recomienda la propuesta {pf}: en el escenario base alcanza el objetivo de rendimiento y en el '
           f'adverso moderado la pérdida queda dentro de la tolerancia del cliente.","La propuesta no cumple "&IF({cu}="NO","el objetivo de rendimiento","")'
           f'&IF(AND({cu}="NO",{to}="NO")," ni ","")&IF({to}="NO","la tolerancia a pérdidas","")&". Ajuste el % de renta fija (PERFIL), el tope de primas '
           f'(DASHBOARD) o la estrategia de opciones antes de recomendarla.")')
    ws.merge_range(r + 1, 1, r + 3, 5, "", wb.add_format({"text_wrap": True, "valign": "top", "font_name": "Arial", "font_size": 10, "border": 1}))
    ws.write_formula(r + 1, 1, rec, wb.add_format({"text_wrap": True, "valign": "top", "font_name": "Arial", "font_size": 10, "border": 1}))
    r += 5
    ws.merge_range(r, 1, r, 5, "6. RIESGOS Y CONDICIONES", f.head)
    riesgos = ["Mercado: acciones, futuros, opciones y bonos largos pueden perder valor; los escenarios no tienen probabilidad asignada.",
               "Apalancamiento: el nocional de los futuros es varias veces la garantía; las pérdidas pueden exceder el margen depositado.",
               "Tasa de interés: vender renta fija antes del vencimiento expone a pérdidas si suben las tasas.",
               "Tipo de cambio: las acciones de EE.UU. y los futuros en dólares dependen del USD/MXN.",
               "Liquidez y ejecución: el stop-loss es una orden hipotética; con brechas de precio puede ejecutarse peor.",
               "Protección: proviene sólo de la renta fija mantenida al vencimiento; la nota NO garantiza el capital contractualmente."]
    for i, t in enumerate(riesgos):
        ws.merge_range(r + 1 + i, 1, r + 1 + i, 5, "• " + t, f.txt)
    ws.write(r + 8, 1, "Fuentes: Banxico SIE y subastas primarias; Yahoo Finance; CITIC Securities (márgenes, 02/06/2026); Barchart; CME Group; BMV/MexDer. "
                       "Fechas de consulta en las hojas RENTA FIJA, MERCADO DE CAPITALES y FUTUROS MULTIACTIVO.", f.nota)
    ws.set_column("A:A", 2); ws.set_column("B:B", 40); ws.set_column("C:C", 30); ws.set_column("D:F", 16)


# ============================================================================ orquestación
def agregar_hojas(wb, f, p, X, fecha_val: dt.date | None = None):
    fecha_val = fecha_val or dt.date.today()
    hoja_dashboard(wb, f, p, {**X, "esc_tabla": (5, 9)}, p.get("fuente_rf", ""))
    cap = hoja_capitales(wb, f, p, X)
    O = hoja_opciones(wb, f, p, X, fecha_val)
    hoja_black_scholes(wb, f, O)
    D = hoja_diversificacion(wb, f, p, X)
    hoja_escenarios(wb, f, p, X)
    hoja_reporte(wb, f, p, X, {**D, "cap_rt": cap["rt"]}, fecha_val)


def ordenar(wb):
    """Coloca las hojas en el orden recomendado (las demás conservan su orden al final) y abre el DASHBOARD."""
    objs = wb.worksheets_objs
    por_nombre = {w.get_name(): w for w in objs}
    nuevo = [por_nombre[n] for n in ORDEN if n in por_nombre] + [w for w in objs if w.get_name() not in ORDEN]
    objs[:] = nuevo
    for i, w in enumerate(objs):
        w.index = i
        w.selected = 0
        w.hidden = 0
    if H_DASH in por_nombre:
        d = por_nombre[H_DASH]
        d.activate()
        d.set_first_sheet()
