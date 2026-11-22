"""Hojas PERFIL, RENTA FIJA, FUTUROS y NOTA ESTRUCTURADA del Excel INTEGRAL (fórmulas vivas).

Lo que se escribe como valor (resultado de un algoritmo de la plataforma, documentado en la hoja): la selección del
instrumento de renta fija, la duración de bonos con cupón y el número de contratos de futuros (asignación entera voraz).
Todo lo demás (precios, rendimientos, primas Black-Scholes, escenarios, ficha de condiciones) son fórmulas.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from xlsxwriter.utility import xl_rowcol_to_cell as CELL, xl_col_to_name as COL

from . import nota as nt
from . import perfil as pfm
from .renta_fija import FICHAS, RIESGOS

H_NOTA, H_PERFIL, H_RF, H_FUT = "NOTA ESTRUCTURADA", "PERFIL", "RENTA FIJA", "FUTUROS MULTIACTIVO"
H_DASH, H_CAP = "DASHBOARD", "MERCADO DE CAPITALES"
CAP_R0 = 7  # primera fila (0-based) de acciones en MERCADO DE CAPITALES
# Entradas del cliente en el DASHBOARD (la NOTA las lee por fórmula)
IN_INV, IN_DIAS, IN_PRM, IN_RF, IN_TOPE = (f"'{H_DASH}'!$D$6", f"'{H_DASH}'!$D$7", f"'{H_DASH}'!$D$8", f"'{H_DASH}'!$D$9", f"'{H_DASH}'!$D$10")
IMG = Path(__file__).resolve().parents[1] / "data" / "img"
NIVEL = {1: "Bajo", 2: "Medio", 3: "Alto"}


def q(h):
    return f"'{h}'"


# ============================================================================ PERFIL
def hoja_perfil(wb, f, respuestas: dict, objetivo: float):
    ws = wb.add_worksheet(H_PERFIL)
    ws.merge_range("B2:H2", "PERFIL DEL INVERSIONISTA", f.bloque)
    for j, e in enumerate(["#", "Variable", "Respuesta", "Puntos (0–3)", "Opciones (0 → 3)"]):
        ws.write(3, 1 + j, e, f.head)
    for i, (k, lab, ops) in enumerate(pfm.PREGUNTAS):
        r = 4 + i
        pts = int(respuestas.get(k, 0))
        ws.write_number(r, 1, i + 1, f.ent)
        ws.write(r, 2, lab, f.lab_r)
        ws.write_formula(r, 3, f'=CHOOSE(E{r+1}+1,"{ops[0]}","{ops[1]}","{ops[2]}","{ops[3]}")', f.txt)
        ws.write_number(r, 4, pts, f.ent_in)
        ws.data_validation(r, 4, r, 4, {"validate": "integer", "criteria": "between", "minimum": 0, "maximum": 3,
                                        "error_message": "Capture un valor entre 0 y 3"})
        ws.write(r, 5, " | ".join(f"{n}: {o}" for n, o in enumerate(ops)), f.nota)
    r0 = 15
    filas = [("Total de puntos", "=SUM(E5:E14)", f.ent), ("Puntaje de riesgo (0–1)", "=E16/30", f.res4),
             ("Perfil de referencia", '=IF(E17<0.35,"CONSERVADOR",IF(E17<=0.65,"MODERADO","AGRESIVO"))', f.res),
             ("% renta fija (KRF)", "=MIN(0.85,MAX(0.15,0.8-0.65*E17))", f.pct_b),
             ("% capitales (de la porción de riesgo)", "=0.75-0.5*E17", f.pct_b),
             ("% futuros (de los derivados)", "=IF(E10=0,0,0.3+0.35*E17)", f.pct_b),
             ("Stop-loss de futuros", "=0.03+0.07*E17", f.pct_b),
             ("Pérdida máxima tolerada", "=CHOOSE(E8+1,0.02,0.05,0.1,0.2)", f.pct_b),
             ("Estrategia de opciones", '=IF(AND(E14=1,E17>0.65),"STG",CHOOSE(E14+1,"FLOOR","BTF","COLLAR","CALL"))', f.res)]
    for k, (lab, fo, fm_) in enumerate(filas):
        ws.write(r0 + k, 2, lab, f.lab_r)
        ws.write_formula(r0 + k, 4, fo, fm_)
    ws.write(r0 + 10, 2, "Objetivo de rendimiento anual", f.lab_r); ws.write_number(r0 + 10, 4, objetivo, f.pct_in)
    ws.write(r0 + 12, 2, "Reglas: puntaje = puntos/30; KRF = 0.80 − 0.65·s (15%–85%); capitales = 0.75 − 0.50·s; futuros = 0.30 + 0.35·s "
                         "(0 sin experiencia en derivados); estrategia según la expectativa de mercado.", f.nota)
    ws.set_column("A:A", 2); ws.set_column("B:B", 5); ws.set_column("C:C", 42); ws.set_column("D:D", 26); ws.set_column("E:E", 14)
    ws.set_column("F:F", 90)
    return {"krf": f"{q(H_PERFIL)}!$E$19", "cap": f"{q(H_PERFIL)}!$E$20", "fut": f"{q(H_PERFIL)}!$E$21", "stop": f"{q(H_PERFIL)}!$E$22",
            "tol": f"{q(H_PERFIL)}!$E$23", "obj": f"{q(H_PERFIL)}!$E$26"}


# ============================================================================ RENTA FIJA
def hoja_renta_fija(wb, f, p: dict, tabla, fuentes: dict):
    ws = wb.add_worksheet(H_RF)
    ws.merge_range("B2:Q2", "RENTA FIJA — COMPARADOR Y SELECCIÓN AUTOMÁTICA", f.bloque)
    ws.write("B4", "Horizonte (días)", f.lab_r); ws.write_formula("C4", f"={q(H_NOTA)}!$E$5", f.num_v)
    ws.write("B5", "Inflación esperada", f.lab_r); ws.write_number("C5", p["renta_fija_in"]["inflacion"], f.pct_in)
    ws.write("D5", fuentes.get("inflacion", ""), f.nota)
    ws.write("B6", "Valor de la UDI", f.lab_r); ws.write_number("C6", p["renta_fija_in"].get("udi") or 1.0, f.num_in)
    ws.write("D6", fuentes.get("udi", ""), f.nota)
    hdr = ["Tipo", "Instrumento", "Plazo (días)", "Valor nominal", "Tasa anual", "Tasa real", "Precio por título",
           "Rend. al horizonte", "Duración al vender", "Pérdida si +100 pb", "R. crédito", "R. mercado", "R. inflación",
           "R. reinversión", "R. liquidez", "Pagos", "Fuente de la tasa"]
    for j, e in enumerate(hdr):
        ws.write(7, 1 + j, e, f.head)
    filas = {}
    for i, row in tabla.reset_index(drop=True).iterrows():
        r = 8 + i
        R = r + 1
        filas[row["instrumento"]] = R
        tipo = row["tipo"]
        ws.write(r, 1, tipo, f.txt)
        ws.write(r, 2, row["instrumento"], f.lab_r)
        ws.write_number(r, 3, int(row["plazo_días"]), f.ent)
        tasa_cel = f"F{R}"
        if tipo == "CETES":
            ws.write_number(r, 4, 10, f.num)
            ws.write_number(r, 5, float(row["tasa_anual"]), f.pct_in)
            ws.write_formula(r, 7, f"=E{R}/(1+F{R}*D{R}/360)", f.num4)
            ws.write_formula(r, 8, f"=IF(D{R}<=$C$4,(1+F{R}*D{R}/360)^($C$4/D{R})-1,(1+F{R}*D{R}/360)/(1+F{R}*(D{R}-$C$4)/360)-1)", f.pct)
            ws.write_formula(r, 9, f"=IF(D{R}<=$C$4,0,((D{R}-$C$4)/360)/(1+F{R}*(D{R}-$C$4)/360))", f.num4)
        elif tipo == "BONOS M":
            ws.write_number(r, 4, 100, f.num)
            ws.write_number(r, 5, float(row["tasa_anual"]), f.pct_in)
            ws.write_number(r, 7, float(row["precio_título"]), f.num4)
            ws.write_formula(r, 8, f"=F{R}*$C$4/360", f.pct)
            ws.write_number(r, 9, float(row["duración_al_vender"]), f.num4)
        elif tipo == "BONDES F":
            ws.write_number(r, 4, 100, f.num)
            ws.write_number(r, 5, float(row["tasa_anual"]), f.pct_in)
            ws.write_number(r, 7, 100, f.num4)
            ws.write_formula(r, 8, f"=F{R}*$C$4/360", f.pct)
            ws.write_formula(r, 9, f"=(28/360)/(1+F{R}*28/360)", f.num4)
        else:  # UDIBONOS
            ws.write_formula(r, 4, "=100*$C$6", f.num)
            ws.write_number(r, 6, float(row["tasa_real"]), f.pct_in)
            ws.write_formula(r, 5, f"=(1+G{R})*(1+$C$5)-1", f.pct)
            ws.write_formula(r, 7, f"={float(row['precio_título'])/(p['renta_fija_in'].get('udi') or 1.0)}*$C$6", f.num4)
            ws.write_formula(r, 8, f"=F{R}*$C$4/360", f.pct)
            ws.write_number(r, 9, float(row["duración_al_vender"]), f.num4)
        ws.write_formula(r, 10, f"=-J{R}*0.01", f.pct)
        for j, k in enumerate(["riesgo_crédito", "riesgo_mercado", "riesgo_inflación", "riesgo_reinversión", "riesgo_liquidez"]):
            ws.write(r, 11 + j, NIVEL[int(row[k])], f.txt_c)
        ws.write(r, 16, row["pagos"], f.txt)
        ws.write(r, 17, fuentes.get(tipo, ""), f.nota)
    fin = 8 + len(tabla)
    ws.write(fin, 1, "Duración de Bonos M y Udibonos: Σ t·VP / P / (1 + y·182/360), calculada por la plataforma con flujos semestrales. "
                     "Precios de Bonos M y Udibonos de referencia emitidos a la par (cupón = rendimiento).", f.nota)
    # Selección por perfil
    s0 = fin + 3
    ws.merge_range(s0, 1, s0, 9, "SELECCIÓN AUTOMÁTICA POR PERFIL", f.head)
    for j, e in enumerate(["Perfil", "Instrumento elegido", "Rend. al horizonte", "Duración", "Precio por título", "Monto KRF",
                           "Títulos", "Sobrante", "Justificación"]):
        ws.write(s0 + 1, 1 + j, e, f.head_t)
    sel_cells = {}
    rng_i = f"$C$9:$C${fin}"
    for k, pf in enumerate(p["perfiles"]):
        r = s0 + 2 + k
        R = r + 1
        sel = p["renta_fija"][pf]
        ws.write(r, 1, pf, f.lab_r)
        ws.write(r, 2, sel["instrumento"], f.txt)
        ws.write_formula(r, 3, f"=INDEX($I$9:$I${fin},MATCH(C{R},{rng_i},0))", f.pct)
        ws.write_formula(r, 4, f"=INDEX($J$9:$J${fin},MATCH(C{R},{rng_i},0))", f.num4)
        ws.write_formula(r, 5, f"=INDEX($H$9:$H${fin},MATCH(C{R},{rng_i},0))", f.num4)
        ws.write_formula(r, 6, f"={q(H_NOTA)}!F{8 + k}", f.mon)
        ws.write_formula(r, 7, f"=INT(G{R}/F{R})", f.ent)
        ws.write_formula(r, 8, f"=G{R}-H{R}*F{R}", f.mon)
        ws.write(r, 9, sel["justificación"], f.nota)
        sel_cells[pf] = {"rend": f"{q(H_RF)}!$D${R}", "dur": f"{q(H_RF)}!$E${R}", "inst": f"{q(H_RF)}!$C${R}"}
    ws.write(s0 + 2 + len(p["perfiles"]) + 1, 1, "Algoritmo: (1) elegibilidad por perfil — conservador sólo instrumentos que vencen dentro del "
             "horizonte o de tasa variable; moderado hasta 3× el horizonte; agresivo todos. (2) puntaje = w_r·rendimiento − w_m·riesgo de "
             "mercado − w_reinv·reinversión − w_inf·inflación (normalizados). (3) se elige el mayor puntaje.", f.nota)
    # Fichas y riesgos
    t0 = s0 + 2 + len(p["perfiles"]) + 4
    ws.merge_range(t0, 1, t0, 9, "CARACTERÍSTICAS Y RIESGOS DE CADA INSTRUMENTO", f.head)
    for j, e in enumerate(["Instrumento", "Nombre", "Valor nominal", "Pago", "Convención", "Riesgo de mercado", "Riesgo de inflación",
                           "Riesgo de reinversión", "Justificación"]):
        ws.write(t0 + 1, 1 + j, e, f.head_t)
    for i, (k, v) in enumerate(FICHAS.items()):
        r = t0 + 2 + i
        ws.write(r, 1, k, f.lab_r)
        for j, x in enumerate([v["nombre"], v["valor_nominal"], v["pago"], v["convención"], RIESGOS[k]["mercado"][1],
                               RIESGOS[k]["inflación"][1], RIESGOS[k]["reinversión"][1], v["justificación"]]):
            ws.write(r, 2 + j, x, f.txt)
    ws.write(t0 + 7, 1, "Ningún instrumento gubernamental está libre de todo riesgo: el riesgo de crédito soberano es bajo, pero hay riesgo "
                        "de mercado, inflación, reinversión y liquidez. Fuente de características: Banxico, Mercado de valores gubernamentales, cap. II.", f.nota)
    ws.set_column("A:A", 2); ws.set_column("B:B", 12); ws.set_column("C:C", 20); ws.set_column("D:K", 13); ws.set_column("L:P", 11)
    ws.set_column("Q:Q", 34); ws.set_column("R:R", 50)
    return sel_cells


# ============================================================================ FUTUROS
def hoja_futuros_multi(wb, f, p: dict, res: dict, usdmxn: float, z_cells: list):
    ws = wb.add_worksheet(H_FUT)
    cat = p["futuros_cat"]
    ws.merge_range("B2:R2", "FUTUROS — CATÁLOGO, MÁRGENES Y DIVERSIFICACIÓN", f.bloque)
    ws.write("B4", "Tipo de cambio USD/MXN", f.lab_r); ws.write_number("C4", usdmxn, f.num_in)
    ws.write("D4", "Yahoo Finance (MXN=X), fecha de consulta del reporte", f.nota)
    ws.write("B5", "Horizonte T (años)", f.lab_r); ws.write_formula("C5", f"={q(H_NOTA)}!$E$5/365", f.num4)
    hdr = ["Clave", "Contrato", "Clase", "Bolsa", "Tamaño", "Vencimiento", "Precio", "Multiplicador", "¿Precio en MXN?",
           "Valor del contrato (MXN)", "Margen inicial (MXN)", "Margen mant. (MXN)", "Valor del tick (MXN)", "Apalancamiento",
           "Volatilidad anual", "Margen inicial (orig.)", "Moneda margen", "Fuente"]
    for j, e in enumerate(hdr):
        ws.write(6, 1 + j, e, f.head)
    fila_c = {}
    from .futuros_multi import CATALOGO
    orig = {c["clave"]: c for c in CATALOGO}
    for i, row in cat.reset_index(drop=True).iterrows():
        r = 7 + i
        R = r + 1
        fila_c[row["clave"]] = R
        o = orig[row["clave"]]
        ws.write(r, 1, row["clave"], f.lab_r); ws.write(r, 2, row["nombre"], f.txt); ws.write(r, 3, row["clase"], f.txt)
        ws.write(r, 4, row["bolsa"], f.txt); ws.write(r, 5, row["unidad"], f.txt); ws.write(r, 6, row["venc"], f.txt)
        if row["precio"] and not np.isnan(row["precio"]):
            ws.write_number(r, 7, float(row["precio"]), f.dato)
        ws.write_number(r, 8, float(row["multiplicador"]), f.num)
        ws.write(r, 9, "SÍ" if row["en_mxn"] else "NO", f.txt_c)
        ws.write_formula(r, 10, f'=IF(H{R}="","",H{R}*I{R}*IF(J{R}="SÍ",1,$C$4))', f.mon)
        mi = o["mi"]
        if row.get("margen_capturado"):
            mi = row["margen_inicial_MXN"] / (1 if o["moneda"] == "MXN" else usdmxn)
        if mi:
            ws.write_number(r, 16, float(mi), f.num_in)
            mm = o["mm"] or mi
            ws.write_formula(r, 11, f'=Q{R}*IF(R{R}="MXN",1,$C$4)', f.mon)
            ws.write_formula(r, 12, f'={float(mm)}*IF(R{R}="MXN",1,$C$4)', f.mon)
            ws.write_formula(r, 14, f'=IF(K{R}="","",K{R}/L{R})', f.num)
        else:
            ws.write(r, 11, "Capturar AIM", f.nota)
        ws.write(r, 17, o["moneda"], f.txt_c)
        if o.get("tick_usd"):
            ws.write_formula(r, 13, f"={o['tick_usd']}*$C$4", f.mon)
        elif o.get("tick") and row["en_mxn"]:
            ws.write_formula(r, 13, f"={o['tick']}*I{R}", f.mon)
        if not np.isnan(row["vol_anual"]):
            ws.write_number(r, 15, float(row["vol_anual"]), f.pct_in)
        ws.write(r, 18, o["fuente"], f.nota)
    fin = 7 + len(cat)
    ws.write(fin, 1, "El margen inicial es una garantía de cumplimiento, no el costo del activo: el valor del contrato es el nocional. "
                     "Márgenes de intermediario con fecha; actualícelos antes de operar. Volatilidad: desv. est. de rend. log diarios (Yahoo) × √252.", f.nota)
    # Bloques por perfil
    r = fin + 3
    totales = {}
    fut = res["futuros"]
    for pf in p["perfiles"]:
        stop = p["config"][pf].get("stop_pct") or 0
        ws.merge_range(r, 1, r, 15, f"PERFIL {pf} — monto para garantías: ver NOTA ESTRUCTURADA", f.head)
        ws.write(r + 1, 1, "Stop-loss", f.lab_r); ws.write_formula(r + 1, 2, f"={q(H_NOTA)}!{_cel_stop(p, pf)}", f.pct_v)
        hdr2 = ["Clave", "Peso objetivo", "Contratos", "Dirección (+1/−1)", "Garantía (MXN)", "Nocional (MXN)"] + [f"P&L {n.split('. ')[1]}" for n, _ in nt.ESCENARIOS_Z] + ["Clase"]
        for j, e in enumerate(hdr2):
            ws.write(r + 2, 1 + j, e, f.head_t)
        sub = fut[(fut.perfil == pf)] if not fut.empty else fut
        r0 = r + 3
        for i, (_, a) in enumerate(sub.iterrows()):
            rr = r0 + i
            R = rr + 1
            Rc = fila_c[a["clave"]]
            ws.write(rr, 1, a["clave"], f.lab_r)
            ws.write_number(rr, 2, float(a["peso"]), f.pct)
            ws.write_number(rr, 3, int(a["contratos"]), f.ent_in)
            ws.write_number(rr, 4, int(a["dirección"]), f.ent_in)
            ws.write_formula(rr, 5, f"=D{R}*$L${Rc}", f.mon)
            ws.write_formula(rr, 6, f"=D{R}*$K${Rc}", f.mon)
            ws.write_formula(rr, 12, f"=INDEX($D$8:$D${fin},MATCH(B{R},$B$8:$B${fin},0))", f.txt)
            for k, zc in enumerate(z_cells):
                mov = f"(EXP({zc}*$P${Rc}*SQRT($C$5))-1)"
                unit = f"IF({zc}<0,-ABS({mov}),E{R}*{mov})"
                ws.write_formula(rr, 7 + k, f"=D{R}*$K${Rc}*MAX({unit},-$C${r+2})" if stop else f"=D{R}*$K${Rc}*{unit}", f.mon)
        rt = r0 + len(sub)
        ws.write(rt, 1, "TOTAL", f.lab)
        for c in [3, 5, 6] + list(range(7, 12)):
            ws.write_formula(rt, c, f"=SUM({CELL(r0, c)}:{CELL(rt-1, c)})" if len(sub) else "=0", f.mon_b if c >= 5 else f.ent)
        totales[pf] = {"rango": (r0 + 1, rt), "contratos": f"{q(H_FUT)}!{CELL(rt, 3, True, True)}", "garantia": f"{q(H_FUT)}!{CELL(rt, 5, True, True)}",
                       "nocional": f"{q(H_FUT)}!{CELL(rt, 6, True, True)}",
                       "esc": [f"{q(H_FUT)}!{CELL(rt, 7 + k, True, True)}" for k in range(5)]}
        r = rt + 3
    ws.write(r, 1, "Contratos: asignación entera de la plataforma (objetivo por clase según el perfil y reparto voraz del sobrante por margen). "
                   "Escenarios: movimiento e^(zσ√T) − 1; en escenarios adversos se aplica en contra de cada posición (sin beneficio de diversificación) "
                   "y la pérdida por contrato se limita con el stop-loss (hipotético: puede ejecutarse peor por brechas).", f.nota)
    ws.set_column("A:A", 2); ws.set_column("B:B", 10); ws.set_column("C:C", 24); ws.set_column("D:D", 20); ws.set_column("E:E", 9)
    ws.set_column("F:F", 26); ws.set_column("G:G", 20); ws.set_column("H:Q", 15); ws.set_column("R:R", 9); ws.set_column("S:S", 48)
    return totales


def _cel_stop(p, pf):
    return f"$M${p['perfiles'].index(pf) + len(p['perfiles']) + 11}"


# ============================================================================ NOTA ESTRUCTURADA
def hoja_nota(wb, f, p: dict, ult_datos: int, hoja_datos="DATOS", hoja_bs="BS", respuestas=None, fuentes=None, usdmxn=18.0):
    res = nt.calcular(p)
    perfiles = p["perfiles"]
    n_pf = len(perfiles)
    ws = wb.add_worksheet(H_NOTA)
    # Las hojas auxiliares se crean después, pero se referencian por nombre
    ws.merge_range("D2:P2", "NOTA ESTRUCTURADA", f.bloque)
    ws.write("D4", "INVERSIÓN", f.lab_r); ws.write_formula("E4", f"={IN_INV}", f.num_v, p["inversion"])
    ws.write("D5", "TIEMPO (días)", f.lab_r); ws.write_formula("E5", f"={IN_DIAS}", f.num_v, p["dias"])
    ws.write("F4", "PRIMA DE MERCADO", f.lab_r); ws.write_formula("G4", f"={IN_PRM}", f.pct_v, p["prm"])
    ws.write("F5", "TASA LIBRE DE RIESGO (CAPM)", f.lab_r); ws.write_formula("G5", f"={IN_RF}", f.pct_v, p["rf_anual"])
    ws.write("D3", "Entradas del cliente: hoja DASHBOARD (celdas amarillas). Esta hoja es el motor de cálculo.", f.nota)
    ws.write("H5", p.get("fuente_rf", ""), f.nota)
    ws.write("I4", "TOPE DE PRIMAS (% inversión; 0 = sin tope)", f.lab_r); ws.write_formula("J4", f"={IN_TOPE}", f.pct_v, p.get("tope_primas_pct") or 0.0)
    # Resumen
    hdr = ["PERFIL", "%KRF", "KRF $", "RENTA FIJA", "REND. RF HORIZONTE", "KRF AL HORIZONTE", "UT KRF", "CAPITALES", "FUTUROS",
           "OPCIONES", "NE", "NE %", "NE ANUALIZADO"]
    for j, e in enumerate(hdr):
        ws.write(6, 3 + j, e, f.head)
    fila = {pf: 7 + k for k, pf in enumerate(perfiles)}   # 0-based; Excel = +1
    div0 = 7 + n_pf + 2
    fdiv = {pf: div0 + 1 + k for k, pf in enumerate(perfiles)}
    for pf in perfiles:
        r, R = fila[pf], fila[pf] + 1
        ws.write(r, 3, pf, f.lab_r)
        if pf == "PERSONALIZADO":
            ws.write_formula(r, 4, f"={q(H_PERFIL)}!$E$19", f.pct_v)
        else:
            ws.write_number(r, 4, p["config"][pf]["krf_pct"], f.pct_in)
        ws.write_formula(r, 5, f"=E{R}*$E$4+N{fdiv[pf]+1}", f.mon)
        ws.write_formula(r, 6, f"={q(H_RF)}!$C${_rf_sel_row(p, pf)}", f.txt)
        ws.write_formula(r, 7, f"={q(H_RF)}!$D${_rf_sel_row(p, pf)}", f.pct_v)
        ws.write_formula(r, 8, f"=F{R}*(1+H{R})", f.mon)
        ws.write_formula(r, 9, f"=I{R}-F{R}", f.mon)
        ws.write_formula(r, 13, f"=J{R}+K{R}+L{R}+M{R}", f.mon_b)
        ws.write_formula(r, 14, f"=N{R}/$E$4", f.pct_b)
        ws.write_formula(r, 15, f"=O{R}*365/$E$5", f.pct)
    # Diversificación
    hdr = ["DIVERSIFICACIÓN", "RISK $", "% CAPITALES", "$ CAPITALES", "$ DERIVADOS", "% FUTUROS", "$ FUTUROS (GARANTÍA)", "$ OPCIONES (PRIMAS)",
           "ESTRATEGIA OPCIONES", "STOP-LOSS FUTUROS", "SOBRANTE A RENTA FIJA"]
    for j, e in enumerate(hdr):
        ws.write(div0, 3 + j, e, f.head)
    for pf in perfiles:
        r, R, Rk = fdiv[pf], fdiv[pf] + 1, fila[pf] + 1
        cfg = p["config"][pf]
        ws.write(r, 3, pf, f.lab_r)
        ws.write_formula(r, 4, f"=$E$4*(1-E{Rk})", f.mon)
        if pf == "PERSONALIZADO":
            ws.write_formula(r, 5, f"={q(H_PERFIL)}!$E$20", f.pct_v)
            ws.write_formula(r, 8, f"={q(H_PERFIL)}!$E$21", f.pct_v)
            ws.write_formula(r, 12, f"={q(H_PERFIL)}!$E$22", f.pct_v)
        else:
            ws.write_number(r, 5, cfg["cap_pct"], f.pct_in)
            ws.write_number(r, 8, cfg["fut_pct"], f.pct_in)
            ws.write_number(r, 12, cfg.get("stop_pct") or 0, f.pct_in)
        ws.write_formula(r, 6, f"=E{R}*F{R}", f.mon)
        ws.write_formula(r, 7, f"=E{R}-G{R}", f.mon)
        ws.write_formula(r, 9, f"=H{R}*I{R}", f.mon)
        ws.write_formula(r, 10, f"=IF($J$4>0,MIN(H{R}-J{R},$J$4*$E$4),H{R}-J{R})", f.mon)
        ws.write_formula(r, 13, f"=H{R}-J{R}-K{R}", f.mon)
        ws.write(r, 11, cfg["estrategia"], f.txt_c)
    # Capitales
    acc = p["acciones"]
    n_acc = len(acc)
    c0 = div0 + n_pf + 3
    ws.merge_range(c0, 3, c0, 7 + n_pf, "MERCADO DE CAPITALES", f.bloque)
    hdr = ["ACCIÓN", "MERCADO", "SECTOR", "BETA", "RENDIMIENTO"] + perfiles
    for j, e in enumerate(hdr):
        ws.write(c0 + 1, 3 + j, e, f.head)
    a0 = c0 + 2
    w0 = a0 + n_acc + 7
    for i, a in enumerate(acc):
        r, R = a0 + i, a0 + i + 1
        ws.write(r, 3, a["nombre"], f.lab_r); ws.write(r, 4, a.get("mercado", ""), f.txt); ws.write(r, 5, a.get("sector", ""), f.txt)
        ws.write_formula(r, 6, f"={q(H_CAP)}!$L${CAP_R0 + 1 + i}", f.num_v, a["beta"])
        if p.get("modo_rend") == "manual":
            ws.write_number(r, 7, a["rend_manual"], f.pct_in)
        else:
            ws.write_formula(r, 7, f"=($G$5+G{R}*$G$4)*$E$5/365", f.pct)
        for j, pf in enumerate(perfiles):
            ws.write_formula(r, 8 + j, f"={CELL(w0 + 2 + i, 4 + j)}*$G${fdiv[pf]+1}", f.mon)
    A, B = a0 + 1, a0 + n_acc
    rs = a0 + n_acc
    for k, lab in enumerate(["SUMA", "VALOR AL HORIZONTE", "UTILIDADES", "ASIGNADO", "DIFERENCIA"]):
        ws.write(rs + k, 3, lab, f.lab)
    for j, pf in enumerate(perfiles):
        c = 8 + j
        L = COL(c)
        ws.write_formula(rs, c, f"=SUM({L}{A}:{L}{B})", f.mon)
        ws.write_formula(rs + 1, c, f"=SUMPRODUCT({L}{A}:{L}{B},1+$H${A}:$H${B})", f.mon)
        ws.write_formula(rs + 2, c, f"={L}{rs+2}-{L}{rs+1}", f.mon_b)
        ws.write_formula(rs + 3, c, f"=$G${fdiv[pf]+1}", f.mon)
        ws.write_formula(rs + 4, c, f"={L}{rs+1}-{L}{rs+4}", f.mon)
        ws.write_formula(fila[pf], 10, f"={L}{rs+3}", f.mon)
    ws.merge_range(w0, 3, w0, 3 + n_pf, "PESOS DE LA CANASTA (% del monto de capitales)", f.head)
    ws.write(w0 + 1, 3, "ACCIÓN", f.head_t)
    for j, pf in enumerate(perfiles):
        ws.write(w0 + 1, 4 + j, pf, f.head_t)
    for i, a in enumerate(acc):
        ws.write(w0 + 2 + i, 3, a["nombre"], f.lab_r)
        for j, pf in enumerate(perfiles):
            ws.write_number(w0 + 2 + i, 4 + j, a["pesos"].get(pf, 0.0), f.pct_in)
    wt = w0 + 2 + n_acc
    ws.write(wt, 3, "TOTAL (100%)", f.lab)
    for j in range(n_pf):
        ws.write_formula(wt, 4 + j, f"=SUM({CELL(w0+2, 4+j)}:{CELL(wt-1, 4+j)})", f.pct_b)
    # Parámetros del subyacente de opciones
    d = p["derivados"]
    pr0 = c0
    pc = 10 + n_pf  # columna de etiquetas
    ws.merge_range(pr0, pc, pr0, pc + 2, f"OPCIONES · {d['nombre']}", f.head)
    params = [("Spot", f"={hoja_datos}!U5", f.num_v), ("r (continua)", f"={hoja_bs}!C5", f.pct_v), ("q", f"={hoja_bs}!C6", f.pct_v),
              ("σ subyacente", f"={hoja_datos}!U6", f.pct_v), ("β subyacente", f"={hoja_datos}!R8", f.num_v),
              ("σ IPC", f"=STDEV({hoja_datos}!N3:N{ult_datos})*SQRT(252)", f.pct), ("μ (CAPM)", "", f.pct), ("T (años)", "=$E$5/365", f.num4),
              ("Multiplicador", d["mult_opc"], f.ent_in), ("S base = S0·e^μ", "", f.res), ("Ancho alas", d.get("ancho", 0.05), f.pct_in)]
    L1 = COL(pc + 1)
    cel = {}
    for k, (lab, v, fm_) in enumerate(params):
        r = pr0 + 1 + k
        ws.write(r, pc, lab, f.lab_r)
        cel[lab] = f"${L1}${r+1}"
    for k, (lab, v, fm_) in enumerate(params):
        r = pr0 + 1 + k
        if lab == "μ (CAPM)":
            v = f"=($G$5+{cel['β subyacente']}*$G$4)*$E$5/365"
        if lab == "S base = S0·e^μ":
            v = f"={cel['Spot']}*EXP({cel['μ (CAPM)']})"
        (ws.write_formula if isinstance(v, str) else ws.write)(r, pc + 1, v, fm_)
    S, sg, r_, q_, T, M, Sb, an = (cel["Spot"], cel["σ subyacente"], cel["r (continua)"], cel["q"], cel["T (años)"], cel["Multiplicador"],
                                   cel["S base = S0·e^μ"], cel["Ancho alas"])
    # Legs de opciones (3 filas por perfil)
    o0 = max(wt, pr0 + 13) + 3
    hdr = ["OPCIONES", "ESTRATEGIA", "TIPO", "STRIKE", "POSICIÓN", "PRIMA BSM", "RES. BASE /U", "PRIMAS PAGADAS", "CALLS NETAS", "CONTRATOS", "ESTIMACIÓN"]
    for j, e in enumerate(hdr):
        ws.write(o0, 3 + j, e, f.head)
    strikes = {"up": f"{S}*(1+{an})", "dn": f"{S}*(1-{an})", "S": S, "p95": f"{S}*0.95", "p105": f"{S}*1.05"}
    tabla_k = {"STG": [("CALL", "up", 1), ("PUT", "dn", 1)], "BTF": [("CALL", "dn", 1), ("CALL", "S", -2), ("CALL", "up", 1)],
               "FLOOR": [("PUT", "p95", 1)], "CAP": [("CALL", "p105", -1)], "CALL": [("CALL", "S", 1)],
               "COLLAR": [("PUT", "p95", 1), ("CALL", "p105", -1)], "STRADDLE": [("CALL", "S", 1), ("PUT", "S", 1)]}
    fila_opc = {}
    for k, pf in enumerate(perfiles):
        clave = p["config"][pf]["estrategia"]
        base = o0 + 1 + 3 * k
        Rb = base + 1
        fila_opc[pf] = Rb
        legs = tabla_k[clave]
        for i in range(3):
            r, R = base + i, base + i + 1
            tipo, kk, pos = legs[i] if i < len(legs) else ("CALL", "S", 0)
            ws.write(r, 3, pf if i == 0 else "", f.lab_r if i == 0 else f.txt)
            ws.write(r, 4, clave if i == 0 else "", f.txt)
            ws.write(r, 5, tipo, f.txt_c)
            ws.write_formula(r, 6, f"={strikes[kk]}", f.num)
            ws.write_number(r, 7, pos, f.ent_in)
            d1 = f"(LN({S}/G{R})+({r_}-{q_}+{sg}^2/2)*{T})/({sg}*SQRT({T}))"
            d2 = f"({d1}-{sg}*SQRT({T}))"
            call = f"{S}*EXP(-{q_}*{T})*NORMSDIST({d1})-G{R}*EXP(-{r_}*{T})*NORMSDIST({d2})"
            put = f"G{R}*EXP(-{r_}*{T})*NORMSDIST(-{d2})-{S}*EXP(-{q_}*{T})*NORMSDIST(-{d1})"
            ws.write_formula(r, 8, f'=IF(F{R}="CALL",{call},{put})', f.num4)
            ws.write_formula(r, 9, f'=H{R}*(IF(F{R}="CALL",MAX({Sb}-G{R},0),MAX(G{R}-{Sb},0))-I{R})', f.num4)
        rg = lambda c: f"{c}{Rb}:{c}{Rb+2}"
        ws.write_formula(base, 10, f"=SUMPRODUCT(({rg('H')}>0)*{rg('H')}*{rg('I')})", f.num4)
        ws.write_formula(base, 11, f'=SUMPRODUCT(({rg("F")}="CALL")*{rg("H")})', f.ent)
        Rd = fdiv[pf] + 1
        Lcap = COL(8 + perfiles.index(pf))
        npres = f"IF(K{Rb}>0,INT(K{Rd}/({M}*K{Rb})),10^9)"
        ncub = f"INT(G{Rd}/({S}*{M}))"
        ws.write_formula(base, 12, f"=IF(L{Rb}<0,MIN({npres},{ncub}),IF(K{Rb}>0,{npres},0))", f.ent)
        ws.write_formula(base, 13, f"=M{Rb}*{M}*SUM({rg('J')})", f.mon_b)
        ws.write_formula(fila[pf], 12, f"=N{Rb}", f.mon)
    ws.write(o0 + 1 + 3 * n_pf, 3, "Primas TEÓRICAS (Black-Scholes, vencimiento = horizonte). Contratos = monto de opciones / (M × primas pagadas); "
                                   "con calls vendidas netas (CAP, COLLAR) se limitan a lo que cubre la canasta: sin ventas en descubierto.", f.nota)
    # Escenarios
    e0 = o0 + 3 * n_pf + 4
    ws.merge_range(e0, 3, e0, 15, "ESCENARIOS: ADVERSOS, NEUTRAL Y OPTIMISTAS (hipótesis, sin probabilidades)", f.bloque)
    hdr = ["PERFIL", "ESCENARIO", "z (σ)", "Δ TASAS (pb)", "S SUBYACENTE", "RENTA FIJA", "CAPITALES", "FUTUROS", "OPCIONES", "NE",
           "VALOR FINAL", "NE %"]
    for j, e in enumerate(hdr):
        ws.write(e0 + 1, 3 + j, e, f.head)
    r = e0 + 2
    z_cells, filas_ne = [], {pf: [] for pf in perfiles}
    fut_tot_placeholder = {}
    for k, pf in enumerate(perfiles):
        for i, (nombre, z) in enumerate(nt.ESCENARIOS_Z):
            R = r + 1
            ws.write(r, 3, pf, f.lab_r); ws.write(r, 4, nombre, f.txt)
            if k == 0:
                ws.write_number(r, 5, z, f.num_in); z_cells.append(f"{q(H_NOTA)}!$F${R}")
            else:
                ws.write_formula(r, 5, f"=$F${e0 + 3 + i}", f.num)
            ws.write_formula(r, 6, f"={nt.BP_POR_Z}*F{R}", f.num)
            ws.write_formula(r, 7, f"={S}*EXP({cel['μ (CAPM)']}+F{R}*{sg}*SQRT({T}))", f.num)
            Rk = fila[pf] + 1
            ws.write_formula(r, 8, f"=F{Rk}*(H{Rk}-{q(H_RF)}!$E${_rf_sel_row(p, pf)}*G{R}/10000)", f.mon)
            Lc = COL(8 + perfiles.index(pf))
            ws.write_formula(r, 9, f"=SUMPRODUCT({Lc}${A}:{Lc}${B},$H${A}:$H${B}+$G${A}:$G${B}*F{R}*{cel['σ IPC']}*SQRT({T}))", f.mon)
            fut_tot_placeholder[(pf, i)] = (r, 10)
            Rb = fila_opc[pf]
            legs = "+".join(f'$H${Rb+j}*(IF($F${Rb+j}="CALL",MAX(H{R}-$G${Rb+j},0),MAX($G${Rb+j}-H{R},0))-$I${Rb+j})' for j in range(3))
            ws.write_formula(r, 11, f"=$M${Rb}*{M}*({legs})", f.mon)
            ws.write_formula(r, 12, f"=I{R}+J{R}+K{R}+L{R}", f.mon_b)
            ws.write_formula(r, 13, f"=$E$4+M{R}", f.mon)
            ws.write_formula(r, 14, f"=M{R}/$E$4", f.pct_b)
            filas_ne[pf].append(R)
            r += 1
    ws.write(r + 1, 3, "Renta fija: valor = KRF·(1 + rend. al horizonte − duración·Δtasas); Δtasas = −60 pb por unidad de z. Acciones: "
                       "r_i = rend_i + β_i·z·σ_IPC·√T. Subyacente: S0·e^(μ + zσ√T). Futuros: hoja FUTUROS MULTIACTIVO.", f.nota)
    # Ficha de condiciones
    t0 = r + 4
    ws.merge_range(t0, 3, t0, 15, "FICHA DE CONDICIONES (TERM SHEET)", f.bloque)
    hdr = ["PERFIL", "PLAZO (días)", "PISO POR RENTA FIJA", "KRF NECESARIO PARA 100%", "PROTECCIÓN DEL CAPITAL", "PARTICIPACIÓN EN ALZAS (CANASTA)",
           "BARRERA: STOP-LOSS", "LÍMITE: APALANCAMIENTO", "PEOR ESCENARIO (NE)", "OBJETIVO AL HORIZONTE", "¿CUMPLE OBJETIVO?",
           "PÉRDIDA ADV. MODERADO", "¿DENTRO DE TOLERANCIA?"]
    for j, e in enumerate(hdr):
        ws.write(t0 + 1, 3 + j, e, f.head)
    ficha_rows = {}
    for k, pf in enumerate(perfiles):
        rr = t0 + 2 + k
        R, Rk, Rd = rr + 1, fila[pf] + 1, fdiv[pf] + 1
        fl = filas_ne[pf]
        ficha_rows[pf] = rr
        ws.write(rr, 3, pf, f.lab_r)
        ws.write_formula(rr, 4, "=$E$5", f.ent)
        ws.write_formula(rr, 5, f"=I{Rk}/$E$4", f.pct)
        ws.write_formula(rr, 6, f"=1/(1+H{Rk})", f.pct)
        ws.write_formula(rr, 7, f'=IF(F{Rk}/$E$4>=G{R},"Total en el escenario base (no garantizada contractualmente)","PARCIAL: "&TEXT(F{R},"0.0%")&" del capital; NO garantizada")', f.txt)
        ws.write_formula(rr, 8, f"=G{Rd}/$E$4", f.pct)
        ws.write_formula(rr, 9, f"=M{Rd}", f.pct)
        ws.write_formula(rr, 11, f"=MIN(M{fl[0]}:M{fl[-1]})", f.mon)
        ws.write_formula(rr, 12, f"={q(H_PERFIL)}!$E$26*$E$5/365", f.pct)
        ws.write_formula(rr, 13, f'=IF(O{fl[2]}>=M{R},"SÍ","NO")', f.txt_c)
        ws.write_formula(rr, 14, f"=-MIN(O{fl[1]},0)", f.pct)
        ws.write_formula(rr, 15, f'=IF(O{R}<={q(H_PERFIL)}!$E$23,"SÍ","NO")', f.txt_c)
    ws.write(t0 + 3 + n_pf, 3, "Pago al vencimiento: valor final = renta fija al horizonte + valor de la canasta + resultado de futuros + resultado de opciones. "
                               "La protección proviene sólo de la renta fija mantenida al vencimiento y del riesgo soberano; ninguna estructura de esta "
                               "hoja garantiza el capital contractualmente. Las pérdidas de futuros pueden exceder la garantía depositada.", f.nota)
    # gráficas
    ch = wb.add_chart({"type": "column"})
    colores = ["#C0392B", "#14B8C4", "#0B1F3A", "#E8833A"]
    for k, pf in enumerate(perfiles):
        fl = filas_ne[pf]
        ch.add_series({"name": pf, "categories": f"={q(H_NOTA)}!$E${fl[0]}:$E${fl[-1]}", "values": f"={q(H_NOTA)}!$M${fl[0]}:$M${fl[-1]}",
                       "fill": {"color": colores[k % 4]}})
    ch.set_title({"name": "Resultado neto por escenario y perfil", "name_font": {"size": 11, "color": "#0B1F3A"}})
    ch.set_y_axis({"num_format": '"$"#,##0', "major_gridlines": {"visible": True, "line": {"color": "#E0E0E0"}}})
    ch.set_legend({"position": "bottom"}); ch.set_size({"width": 760, "height": 360})
    ws.insert_chart(e0 + 1, 17, ch)
    cc = wb.add_chart({"type": "bar", "subtype": "percent_stacked"})
    for lab, col in [("Renta fija", "F"), ("Capitales", "G"), ("Futuros (garantía)", "J"), ("Opciones (primas)", "K")]:
        refs = [f"{q(H_NOTA)}!${col}${(fila[pf] if col == 'F' else fdiv[pf]) + 1}" for pf in perfiles]
        cc.add_series({"name": lab, "categories": f"={q(H_NOTA)}!$D${fila[perfiles[0]]+1}:$D${fila[perfiles[-1]]+1}", "values": "=(" + ",".join(refs) + ")"})
    cc.set_title({"name": "Composición de la inversión por perfil", "name_font": {"size": 11, "color": "#0B1F3A"}})
    cc.set_legend({"position": "bottom"}); cc.set_size({"width": 560, "height": 300})
    ws.insert_chart(1, 17, cc)
    ws.set_column("A:C", 2); ws.set_column("D:D", 24); ws.set_column("E:E", 20); ws.set_column("F:P", 15); ws.set_column("G:G", 18)
    ws.set_column("K:K", 22)
    # hojas auxiliares
    hoja_perfil(wb, f, respuestas or {}, p.get("objetivo_rend", 0.0))
    hoja_renta_fija(wb, f, p, p["renta_fija_tabla"], fuentes or {})
    tot = hoja_futuros_multi(wb, f, p, res, usdmxn, z_cells)
    for pf in perfiles:
        ws.write_formula(fila[pf], 11, f"={tot[pf]['esc'][2]}", f.mon)
        for i in range(5):
            r, c = fut_tot_placeholder[(pf, i)]
            ws.write_formula(r, c, f"={tot[pf]['esc'][i]}", f.mon)
        ws.write_formula(ficha_rows[pf], 10, f"={tot[pf]['nocional']}/$E$4", f.num)
    res["excel"] = {"fila": fila, "fdiv": fdiv, "filas_ne": filas_ne, "ficha": ficha_rows, "cel": cel, "a0": a0, "n_acc": n_acc,
                    "fila_opc": fila_opc, "fut": tot, "cat_fin": 7 + len(p["futuros_cat"])}
    return res


def _rf_sel_row(p, pf):
    """Fila Excel de la selección de renta fija del perfil en la hoja RENTA FIJA (misma regla que hoja_renta_fija)."""
    n = len(p["renta_fija_tabla"])
    fin = 8 + n
    s0 = fin + 3
    return s0 + 2 + p["perfiles"].index(pf) + 1
