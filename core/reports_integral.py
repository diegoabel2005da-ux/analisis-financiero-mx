"""Excel en formato INTEGRAL (basado en el archivo de ejemplo del usuario) + hojas de análisis de la plataforma.

Hojas del formato: DATOS · TENDENCIAS RSI · BS · STRADDLE CALL|PUT · STRANGLE CALL|PUT · COMPRA VTA FUT · BTFL CALL|PUT.
Todo lo calculable se escribe como FÓRMULA de Excel para que el libro se recalcule al cambiar un supuesto.
Convenciones de color: azul = dato capturado o supuesto editable; negro = fórmula; verde = vínculo a otra hoja.
"""
from __future__ import annotations

import io
import math

import numpy as np
import pandas as pd
from xlsxwriter.utility import xl_col_to_name as COL, xl_rowcol_to_cell as CELL

from . import reports as rp

AZUL, TURQ, GRIS = "#0B1F3A", "#14B8C4", "#F2F5F9"
H_DATOS, H_RSI, H_BS = "DATOS", "TENDENCIAS RSI", "BS"
H_STD, H_STG, H_FUT, H_BTF = "STRADDLE CALL|PUT", "STRANGLE CALL|PUT", "COMPRA VTA FUT", "BTFL CALL|PUT"


def q(h):  # referencia a hoja con comillas
    return f"'{h}'"


class F:
    """Catálogo de formatos."""

    def __init__(self, wb):
        b = {"font_name": "Arial", "font_size": 10}
        self.wb = wb
        self.head = wb.add_format({**b, "bold": True, "font_color": "white", "bg_color": AZUL, "border": 1,
                                   "align": "center", "valign": "vcenter", "text_wrap": True})
        self.head_t = wb.add_format({**b, "bold": True, "font_color": "white", "bg_color": TURQ, "border": 1, "align": "center"})
        self.titulo = wb.add_format({**b, "bold": True, "font_size": 14, "font_color": AZUL})
        self.bloque = wb.add_format({**b, "bold": True, "font_size": 16, "font_color": "white", "bg_color": AZUL,
                                     "align": "center", "valign": "vcenter", "border": 1})
        self.lab = wb.add_format({**b, "bold": True, "font_color": AZUL})
        self.lab_r = wb.add_format({**b, "bold": True, "font_color": AZUL, "bg_color": GRIS, "border": 1})
        self.txt = wb.add_format(b)
        self.nota = wb.add_format({**b, "italic": True, "font_color": "#666666", "font_size": 9})
        self.fecha = wb.add_format({**b, "num_format": "dd/mm/yyyy"})
        self.fecha_v = wb.add_format({**b, "num_format": "dd/mm/yyyy", "font_color": "#008000"})
        self.num = wb.add_format({**b, "num_format": "#,##0.00"})
        self.num4 = wb.add_format({**b, "num_format": "#,##0.0000"})
        self.num6 = wb.add_format({**b, "num_format": "0.000000"})
        self.num_v = wb.add_format({**b, "num_format": "#,##0.00", "font_color": "#008000"})
        self.num_in = wb.add_format({**b, "num_format": "#,##0.00", "font_color": "#0000FF", "bg_color": "#FFFF00", "border": 1})
        self.pct_in = wb.add_format({**b, "num_format": "0.00%", "font_color": "#0000FF", "bg_color": "#FFFF00", "border": 1})
        self.ent_in = wb.add_format({**b, "num_format": "#,##0", "font_color": "#0000FF", "bg_color": "#FFFF00", "border": 1})
        self.dato = wb.add_format({**b, "num_format": "#,##0.00", "font_color": "#0000FF"})
        self.dato_vol = wb.add_format({**b, "num_format": '0.00,,"M"', "font_color": "#0000FF"})
        self.vol_v = wb.add_format({**b, "num_format": '0.00,,"M"', "font_color": "#008000"})
        self.pct = wb.add_format({**b, "num_format": "0.00%"})
        self.pct_v = wb.add_format({**b, "num_format": "0.00%", "font_color": "#008000"})
        self.pct_b = wb.add_format({**b, "num_format": "0.00%", "bold": True})
        self.res = wb.add_format({**b, "num_format": "#,##0.00", "bold": True, "bg_color": "#E6F7F8", "border": 1})
        self.res4 = wb.add_format({**b, "num_format": "0.0000", "bold": True, "bg_color": "#E6F7F8", "border": 1})
        self.mon = wb.add_format({**b, "num_format": '"$"#,##0.00;[Red]-"$"#,##0.00'})
        self.mon_b = wb.add_format({**b, "num_format": '"$"#,##0.00;[Red]-"$"#,##0.00', "bold": True, "bg_color": "#E6F7F8"})
        self.ent = wb.add_format({**b, "num_format": "0"})
        self.txt_c = wb.add_format({**b, "align": "center"})


def _grafica_linea(wb, nombre, hoja, cat, vals, titulo, eje_x="", eje_y="", color=AZUL, extra=None, ancho=520, alto=290):
    ch = wb.add_chart({"type": "line"})
    ch.add_series({"name": nombre, "categories": f"={q(hoja)}!{cat}", "values": f"={q(hoja)}!{vals}",
                   "line": {"color": color, "width": 2}})
    for e in extra or []:
        ch.add_series({"categories": f"={q(hoja)}!{cat}", **e})
    ch.set_title({"name": titulo, "name_font": {"size": 11, "bold": True, "color": AZUL}})
    ch.set_x_axis({"name": eje_x, "num_format": "#,##0.00", "label_position": "low", "num_font": {"rotation": -45, "size": 8}})
    ch.set_y_axis({"name": eje_y, "num_format": "#,##0.00", "major_gridlines": {"visible": True, "line": {"color": "#E0E0E0"}}})
    ch.set_legend({"position": "bottom"})
    ch.set_size({"width": ancho, "height": alto})
    return ch


# ======================================================================== DATOS
def hoja_datos(wb, f, p):
    ws = wb.add_worksheet(H_DATOS)
    d = p["datos"]  # columnas: Close, Open, High, Low, Volume, IPC_Close, IPC_Open, IPC_High, IPC_Low, IPC_Volume
    n = len(d)
    ult = n + 1  # última fila Excel
    enc = ["Fecha", p["emisora"], "Apertura", "Máximo", "Mínimo", "Vol.", "% var.", "Fecha", "IPC", "Apertura", "Máximo",
           "Mínimo", "Vol.", "% var.", "#", "Rend. log"]
    for j, e in enumerate(enc):
        ws.write(0, j, e, f.head)
    for i, (fecha, r) in enumerate(d.iterrows()):
        x = i + 1
        ws.write_datetime(x, 0, fecha.to_pydatetime(), f.fecha)
        for j, c in enumerate(["Close", "Open", "High", "Low"]):
            ws.write_number(x, 1 + j, float(r[c]), f.dato)
        ws.write_number(x, 5, float(r["Volume"]), f.dato_vol)
        ws.write_datetime(x, 7, fecha.to_pydatetime(), f.fecha)
        for j, c in enumerate(["IPC_Close", "IPC_Open", "IPC_High", "IPC_Low"]):
            ws.write_number(x, 8 + j, float(r[c]), f.dato)
        ws.write_number(x, 12, float(r["IPC_Volume"]), f.dato_vol)
        ws.write_number(x, 14, i + 1, f.ent)
        if i == 0:
            ws.write(x, 6, "—", f.txt_c); ws.write(x, 13, "—", f.txt_c); ws.write(x, 15, "—", f.txt_c)
        else:
            ws.write_formula(x, 6, f"=B{x+1}/B{x}-1", f.pct)
            ws.write_formula(x, 13, f"=I{x+1}/I{x}-1", f.pct)
            ws.write_formula(x, 15, f"=LN(B{x+1}/B{x})", f.pct)
    ws.set_column("A:A", 11); ws.set_column("B:E", 11); ws.set_column("F:F", 9); ws.set_column("G:G", 8.5)
    ws.set_column("H:H", 11); ws.set_column("I:L", 11); ws.set_column("M:N", 9); ws.set_column("O:O", 5)
    ws.set_column("P:P", 9); ws.set_column("Q:Q", 24); ws.set_column("R:U", 13)
    ws.freeze_panes(1, 1)
    G, N = f"G3:G{ult}", f"N3:N{ult}"
    # Resumen beta general
    ws.write("Q5", "β GENERAL", f.lab); ws.write("T5", "SPOT", f.lab)
    ws.write_formula("U5", f"=LOOKUP(9.99E+307,B2:B{ult})", f.res)
    ws.write("Q6", "COVAR (muestral)", f.lab_r); ws.write_formula("R6", f"=COVAR({G},{N})*COUNT({G})/(COUNT({G})-1)", f.num6)
    ws.write("Q7", "VAR", f.lab_r); ws.write_formula("R7", f"=VAR({N})", f.num6)
    ws.write("Q8", "β", f.lab_r); ws.write_formula("R8", "=R6/R7", f.res4)
    ws.write("Q9", "R²", f.lab_r); ws.write_formula("R9", "=R10^2", f.res4)
    ws.write("Q10", "CORRELACION", f.lab_r); ws.write_formula("R10", f"=CORREL({G},{N})", f.res4)
    ws.write_formula("Q11", "=B1", f.lab)
    ws.write("T6", "VOL. ANUAL", f.lab); ws.write_formula("U6", f"=STDEV(P3:P{ult})*SQRT(252)", f.pct_b)
    ws.write("T7", "OBSERVACIONES", f.lab); ws.write_formula("U7", f"=COUNT({G})", f.ent)
    # Ciclos (4 tramos de igual tamaño sobre los rendimientos)
    filas = list(range(3, ult + 1))
    tramos = np.array_split(np.array(filas), 4)
    for k, tr in enumerate(tramos):
        a, b = int(tr[0]), int(tr[-1])
        r0 = 13 + 3 * k  # fila 0-based de la etiqueta: 14, 17, 20, 23 en Excel
        ws.write(r0, 16, f"CICLO {k+1} β", f.lab)
        ws.write_formula(r0 + 1, 16, f"=A{a}", f.fecha_v); ws.write_formula(r0 + 1, 17, f"=A{b}", f.fecha_v)
        for j, e in enumerate(["COVAR", "VAR", "β"]):
            ws.write(r0 + 1, 18 + j, e, f.head)
        g, nn = f"G{a}:G{b}", f"N{a}:N{b}"
        ws.write_formula(r0 + 2, 18, f"=COVAR({g},{nn})*COUNT({g})/(COUNT({g})-1)", f.num6)
        ws.write_formula(r0 + 2, 19, f"=VAR({nn})", f.num6)
        ws.write_formula(r0 + 2, 20, f"={CELL(r0+2,18)}/{CELL(r0+2,19)}", f.res4)
        ws.write(26 + k, 16, f"CICLO {k+1} CORRELACIONAL", f.lab)
        ws.write_formula(26 + k, 18, f"=CORREL({g},{nn})", f.res4)
    ws.write(31, 16, "Fuente: Yahoo Finance (proveedor secundario, con retraso). β con rendimientos simples diarios en fechas "
                     "comunes; covarianza ajustada a muestral para ser consistente con VAR (muestral).", f.nota)
    ch = _grafica_linea(wb, p["emisora"], H_DATOS, f"$A$2:$A${ult}", f"$B$2:$B${ult}", f"Precio {p['emisora']} (MXN)")
    ch.set_x_axis({"date_axis": True, "num_format": "mmm-yy", "num_font": {"size": 8}})
    ws.insert_chart("Q34", ch)
    sc = wb.add_chart({"type": "scatter"})
    sc.add_series({"name": "Rendimientos diarios", "categories": f"={q(H_DATOS)}!$N$3:$N${ult}",
                   "values": f"={q(H_DATOS)}!$G$3:$G${ult}", "marker": {"type": "circle", "size": 4, "fill": {"color": AZUL}},
                   "trendline": {"type": "linear", "display_equation": True, "display_r_squared": True}})
    sc.set_title({"name": f"Beta: {p['emisora']} vs IPC", "name_font": {"size": 11, "color": AZUL}})
    sc.set_x_axis({"name": "% var. IPC", "num_format": "0%"}); sc.set_y_axis({"name": f"% var. {p['emisora']}", "num_format": "0%"})
    sc.set_legend({"none": True}); sc.set_size({"width": 520, "height": 290})
    ws.insert_chart("Q50", sc)
    return {"ult": ult, "tramos": [(int(t[0]), int(t[-1])) for t in tramos]}


# ======================================================================== TENDENCIAS RSI
def hoja_rsi(wb, f, p, info):
    ws = wb.add_worksheet(H_RSI)
    d = p["datos"]
    m = 26  # últimas 26 observaciones (RSI 25 requiere 26 precios = 25 variaciones)
    tail = d.tail(m)
    for j, e in enumerate(["Fecha", "Precio (cierre)", "NUMERO"]):
        ws.write(0, j, e, f.head)
    for i, (fecha, r) in enumerate(tail.iterrows()):
        src = info["ult"] - m + 1 + i  # fila Excel en DATOS
        ws.write_formula(i + 1, 0, f"={H_DATOS}!A{src}", f.fecha_v)
        ws.write_formula(i + 1, 1, f"={H_DATOS}!B{src}", f.num_v)
        ws.write_number(i + 1, 2, m - i, f.ent)
    ws.write(m + 2, 0, "NUMERO: 1 = observación más reciente.", f.nota)
    rsi_cells = {}
    for (n, c0) in [(9, 4), (14, 10), (25, 16)]:
        # c0: columna 0-based de la cuenta regresiva (E, K, Q)
        cP, cV, cG, cL = c0 + 1, c0 + 2, c0 + 3, c0 + 4
        ws.merge_range(13, c0, 13, c0 + 3, f"RSI {n}", f.head)
        ws.write(14, c0, "datos", f.lab); ws.write(14, cP, "Precio", f.lab); ws.write(14, cV, "VARIACIÓN", f.lab)
        ws.write(15, cG, "GANANCIA", f.head_t); ws.write(15, cL, "PÉRDIDA", f.head_t)
        for k in range(n + 1):
            fila = 15 + k  # 0-based
            src = m + 1 - n + k  # fila Excel en esta hoja (col B)
            ws.write_number(fila, c0, n - k, f.ent)
            ws.write_formula(fila, cP, f"=B{src}", f.num)
            if k > 0:
                ws.write_formula(fila, cV, f"={CELL(fila, cP)}-{CELL(fila-1, cP)}", f.num)
                ws.write_formula(fila, cG, f"=IF({CELL(fila, cV)}>0,{CELL(fila, cV)},0)", f.num)
                ws.write_formula(fila, cL, f"=IF({CELL(fila, cV)}<0,{CELL(fila, cV)},0)", f.num)
        fs = 15 + n + 1
        ws.write_formula(fs, cV, f"=SUM({CELL(16, cV)}:{CELL(fs-1, cV)})", f.num)
        ws.write_formula(fs, cG, f"=SUM({CELL(16, cG)}:{CELL(fs-1, cG)})", f.res)
        ws.write_formula(fs, cL, f"=SUM({CELL(16, cL)}:{CELL(fs-1, cL)})", f.res)
        ws.write(fs + 2, cV, "ABSOLUTOS", f.lab)
        ws.write_formula(fs + 2, cG, f"={CELL(fs, cG)}", f.num)
        ws.write_formula(fs + 2, cL, f"=-{CELL(fs, cL)}", f.num)
        ws.write(fs + 4, cV, "RS", f.lab); ws.write(fs + 4, cG, "GANANCIA / PÉRDIDA", f.txt)
        ws.write_formula(fs + 4, cL, f'=IF({CELL(fs+2, cL)}=0,"N/A",{CELL(fs+2, cG)}/{CELL(fs+2, cL)})', f.num4)
        ws.write(fs + 5, cV, f"RSI {n}", f.lab); ws.write(fs + 5, cG, "100-(100/(1+RS))", f.txt)
        ws.write_formula(fs + 5, cL, f"=IF({CELL(fs+2, cL)}=0,100,100-(100/(1+{CELL(fs+4, cL)})))", f.res)
        ws.write_formula(13, c0 + 4, f"={CELL(fs+5, cL)}", f.res)
        rsi_cells[n] = CELL(fs + 5, cL, True, True)
    # resumen RSI
    ws.write("G35", "RSI", f.head); ws.write("H35", "Promedio simple (esta hoja)", f.head); ws.write("I35", "Wilder (plataforma)", f.head)
    for k, n in enumerate((9, 14, 25)):
        ws.write(35 + k, 6, f"rsi {n}", f.lab_r)
        ws.write_formula(35 + k, 7, f"={rsi_cells[n]}", f.res)
        w = p.get("rsi_wilder", {}).get(n)
        if w is not None and not (isinstance(w, float) and math.isnan(w)):
            ws.write_number(35 + k, 8, float(w), f.num)
    ws.write("G39", "La hoja calcula el RSI con sumas simples de ganancias y pérdidas de los últimos n días (como el archivo "
                    "de referencia). La plataforma usa el suavizado de Wilder sobre todo el período; por eso pueden diferir.", f.nota)
    # MACD (serie completa)
    ult = info["ult"]
    for j, e in enumerate(["Fecha", "Precio (cierre)", "NUMERO", "MEDIA 12", "MEDIA 26", "MACD (26-12)", "SIGNS (9)",
                           "HISTOGRAMA (MACD-SIGNS)", "POSTURAS"]):
        ws.write(0, 23 + j, e, f.head)
    X, Y, Z, AA, AB, AC, AD, AE, AF = range(23, 32)
    for i in range(ult - 1):
        r = i + 1
        er = r + 1  # fila Excel
        ws.write_formula(r, X, f"={H_DATOS}!A{er}", f.fecha_v)
        ws.write_formula(r, Y, f"={H_DATOS}!B{er}", f.num_v)
        ws.write_number(r, Z, i + 1, f.ent)
        if i >= 11:
            ws.write_formula(r, AA, f"=AVERAGE(Y{er-11}:Y{er})", f.num)
        if i >= 25:
            ws.write_formula(r, AB, f"=AVERAGE(Y{er-25}:Y{er})", f.num)
            ws.write_formula(r, AC, f"=AB{er}-AA{er}", f.num4)
        if i >= 33:
            ws.write_formula(r, AD, f"=AVERAGE(AC{er-8}:AC{er})", f.num4)
            ws.write_formula(r, AE, f"=AC{er}-AD{er}", f.num4)
            ws.write_formula(r, AF, f'=IF(AE{er}<0,"COMPRA",IF(AE{er}>0,"VENTA","NEUTRAL"))', f.txt_c)
    rng = lambda c: f"{COL(c)}2:{COL(c)}{ult}"
    filas = [("SEÑAL MX", f"=MAX({rng(AD)})"), ("SEÑAL PROMEDIO", f"=AVERAGE({rng(AD)})"), ("SEÑAL MÍNIMA", f"=MIN({rng(AD)})"),
             None, ("SPREAD PRICE", "=AJ4-AJ6"), ("SPREAD TENDENCIA", f"=STDEVP({rng(AD)})")]
    for k, x in enumerate(filas):
        if x:
            ws.write(3 + k, 34, x[0], f.lab_r); ws.write_formula(3 + k, 35, x[1], f.num4)
    ws.write("AI11", "COMPRA", f.lab_r); ws.write_formula("AJ11", f'=COUNTIF({rng(AF)},"COMPRA")', f.ent)
    ws.write_formula("AK11", "=IF(AJ13=0,0,AJ11/AJ13)", f.pct)
    ws.write("AI12", "VENTA", f.lab_r); ws.write_formula("AJ12", f'=COUNTIF({rng(AF)},"VENTA")', f.ent)
    ws.write_formula("AK12", "=IF(AJ13=0,0,AJ12/AJ13)", f.pct)
    ws.write("AI13", "TOTAL", f.lab_r); ws.write_formula("AJ13", "=SUM(AJ11:AJ12)", f.ent)
    ws.write("AI14", "POSTURA ACTUAL", f.lab_r); ws.write_formula("AJ14", f"=AF{ult}", f.res)
    resumen = [("rsi 9", f"={rsi_cells[9]}", f.num), ("rsi 14", f"={rsi_cells[14]}", f.num), ("rsi 25", f"={rsi_cells[25]}", f.num),
               ("promedio MACD", f"=AVERAGE({rng(AC)})", f.num4), ("% compra", "=AK11", f.pct), ("% venta", "=AK12", f.pct)]
    for k, (lab, fo, fm) in enumerate(resumen):
        ws.write(k, 39, lab, f.lab_r); ws.write_formula(k, 40, fo, fm)
    ws.write("AI16", "Convención del archivo de referencia: MACD = media 26 − media 12 (signo inverso al estándar). Por eso "
                     "histograma < 0 se lee como COMPRA (equivale a MACD estándar por encima de su señal). Medias simples. "
                     "Herramienta descriptiva: no es una orden ni una recomendación.", f.nota)
    ws.set_column("A:A", 11); ws.set_column("B:B", 13); ws.set_column("C:C", 9)
    ws.set_column("E:U", 11); ws.set_column("X:X", 11); ws.set_column("Y:AE", 12); ws.set_column("AF:AF", 11)
    ws.set_column("AI:AI", 18); ws.set_column("AJ:AK", 12); ws.set_column("AN:AN", 15); ws.set_column("AO:AO", 11)
    ch = _grafica_linea(wb, "Precio", H_RSI, f"$A$2:$A${m+1}", f"$B$2:$B${m+1}", f"Últimos {m} cierres", ancho=430, alto=250)
    ch.set_x_axis({"date_axis": True, "num_format": "dd-mmm", "num_font": {"size": 8, "rotation": -45}})
    ws.insert_chart("E1", ch)
    bc = wb.add_chart({"type": "column"})
    bc.add_series({"name": "RSI (promedio simple)", "categories": f"={q(H_RSI)}!$G$36:$G$38", "values": f"={q(H_RSI)}!$H$36:$H$38",
                   "fill": {"color": AZUL}, "data_labels": {"value": True, "num_format": "0.0"}})
    bc.add_series({"name": "RSI Wilder", "categories": f"={q(H_RSI)}!$G$36:$G$38", "values": f"={q(H_RSI)}!$I$36:$I$38",
                   "fill": {"color": TURQ}, "data_labels": {"value": True, "num_format": "0.0"}})
    bc.set_title({"name": "Comparativo RSI 9 · 14 · 25", "name_font": {"size": 11, "color": AZUL}})
    bc.set_y_axis({"min": 0, "max": 100, "major_gridlines": {"visible": True, "line": {"color": "#E0E0E0"}}})
    bc.set_legend({"position": "bottom"}); bc.set_size({"width": 430, "height": 250})
    ws.insert_chart("L1", bc)
    mc = _grafica_linea(wb, "MACD (26-12)", H_RSI, f"$X$2:$X${ult}", f"$AC$2:$AC${ult}", "MACD y señal", color=AZUL,
                        extra=[{"name": "SIGNS (9)", "values": f"={q(H_RSI)}!$AD$2:$AD${ult}", "line": {"color": TURQ, "width": 1.5}}],
                        ancho=620, alto=300)
    mc.set_x_axis({"date_axis": True, "num_format": "mmm-yy", "num_font": {"size": 8}})
    ws.insert_chart("AI19", mc)
    hc = wb.add_chart({"type": "column"})
    hc.add_series({"name": "Histograma", "categories": f"={q(H_RSI)}!$X$2:$X${ult}", "values": f"={q(H_RSI)}!$AE$2:$AE${ult}",
                   "fill": {"color": TURQ}, "invert_if_negative": False})
    hc.set_title({"name": "Histograma (MACD − señal)", "name_font": {"size": 11, "color": AZUL}})
    hc.set_x_axis({"date_axis": True, "num_format": "mmm-yy", "num_font": {"size": 8}})
    hc.set_legend({"none": True}); hc.set_size({"width": 620, "height": 260})
    ws.insert_chart("AI35", hc)


# ======================================================================== BS
def hoja_bs(wb, f, p, info):
    ws = wb.add_worksheet(H_BS)
    ws.write("B1", f"Black-Scholes-Merton — primas teóricas · {p['emisora']}", f.titulo)
    ent = [("Spot (S)", f"={H_DATOS}!U5", f.num_v, None),
           ("Volatilidad anual (σ)", f"={H_DATOS}!U6", f.pct_v, "Histórica: desv. est. de rend. log diarios × √252 (hoja DATOS)."),
           ("Tasa libre de riesgo (r, continua)", p["r"], f.pct_in, p.get("fuente_r", "")),
           ("Rend. por dividendo (q, continuo)", p["q"], f.pct_in, p.get("fuente_q", "")),
           ("Días al vencimiento", p["dias"], f.ent_in, p.get("fuente_dias", "")),
           ("T (años)", "=C7/365", f.num4, "Días / 365")]
    for k, (lab, v, fm, nota) in enumerate(ent):
        r = 2 + k
        ws.write(r, 1, lab, f.lab_r)
        (ws.write_formula if isinstance(v, str) and v.startswith("=") else ws.write)(r, 2, v, fm)
        if nota:
            ws.write(r, 3, nota, f.nota)
    hdr = ["Uso", "Strike (K)", "d1", "d2", "Call teórica", "Put teórica"]
    for j, h in enumerate(hdr):
        ws.write(10, 1 + j, h, f.head)
    filas = [("Straddle (K)", f"={q(H_STD)}!C2"), ("Strangle — K call", f"={q(H_STG)}!C2"), ("Strangle — K put", f"={q(H_STG)}!C3"),
             ("Mariposa — K bajo", f"={q(H_BTF)}!Q3"), ("Mariposa — K medio", f"={q(H_BTF)}!Q4"), ("Mariposa — K alto", f"={q(H_BTF)}!Q5")]
    celdas = {}
    for k, (lab, kref) in enumerate(filas):
        r = 11 + k
        R = r + 1
        ws.write(r, 1, lab, f.lab_r)
        ws.write_formula(r, 2, kref, f.num_v)
        ws.write_formula(r, 3, f"=(LN($C$3/C{R})+($C$5-$C$6+$C$4^2/2)*$C$8)/($C$4*SQRT($C$8))", f.num4)
        ws.write_formula(r, 4, f"=D{R}-$C$4*SQRT($C$8)", f.num4)
        ws.write_formula(r, 5, f"=$C$3*EXP(-$C$6*$C$8)*NORMSDIST(D{R})-C{R}*EXP(-$C$5*$C$8)*NORMSDIST(E{R})", f.res)
        ws.write_formula(r, 6, f"=C{R}*EXP(-$C$5*$C$8)*NORMSDIST(-E{R})-$C$3*EXP(-$C$6*$C$8)*NORMSDIST(-D{R})", f.res)
        celdas[lab] = (f"{q(H_BS)}!$F${R}", f"{q(H_BS)}!$G${R}")
    ws.write("B18", "Call = S·e^(−qT)·N(d1) − K·e^(−rT)·N(d2); Put = K·e^(−rT)·N(−d2) − S·e^(−qT)·N(−d1); "
                    "d1 = [ln(S/K) + (r − q + σ²/2)T]/(σ√T). Son primas TEÓRICAS, no cotizaciones de MexDer. Los strikes se "
                    "editan en cada hoja de estrategia.", f.nota)
    ws.set_column("B:B", 30); ws.set_column("C:G", 14)
    ws.write("B21", "STRADDLE LONG PUT", f.titulo)
    ws.write("I21", "STRADDLE LONG CALL", f.titulo)
    return celdas


# ======================================================================== STRADDLE / STRANGLE
def hoja_volatilidad(wb, f, p, celdas_bs, hoja, tipo):
    ws = wb.add_worksheet(hoja)
    S = p["spot"]
    for j, e in enumerate(["", "Precio de Mercado", "Strike Price", "Call", "Put"]):
        if e:
            ws.write(0, j, e, f.head)
    if tipo == "straddle":
        k_call = k_put = p["k_straddle"]
        bs_call, bs_put = celdas_bs["Straddle (K)"]
        bs_call2, bs_put2 = bs_call, bs_put
    else:
        k_call, k_put = p["k_call_strangle"], p["k_put_strangle"]
        bs_call, bs_put = celdas_bs["Strangle — K call"]
        bs_call2, bs_put2 = celdas_bs["Strangle — K put"]
    obs = p.get("primas_obs", {}).get(tipo, {})
    ws.write("A2", "BULL", f.lab); ws.write("A3", "BEAR", f.lab)
    ws.write_formula("B2", f"={H_DATOS}!U5", f.num_v); ws.write_formula("B3", f"={H_DATOS}!U5", f.num_v)
    ws.write_number("C2", k_call, f.num_in); ws.write_number("C3", k_put, f.num_in)
    for cel, ref, clave in [("D2", bs_call, "call_k1"), ("E2", bs_put, "put_k1"), ("D3", bs_call2, "call_k2"), ("E3", bs_put2, "put_k2")]:
        if obs.get(clave):
            ws.write_number(cel, obs[clave], f.num_in)
        else:
            ws.write_formula(cel, f"={ref}", f.num_v)
    ws.write("G2", "Primas en verde: teóricas (hoja BS). Capture primas observadas de MexDer encima si las tiene.", f.nota)
    ws.write("G3", "DIFF", f.lab); ws.write_number("H3", p["paso"], f.num_in)
    ws.write("A7", "SPOT", f.lab); ws.write_formula("B7", f"={H_DATOS}!U5", f.res)
    NC = 100
    c0 = 6  # G
    cf = c0 + NC - 1  # DB

    def rango(fila):
        return f"{CELL(fila, c0, True, True)}:{CELL(fila, cf, True, True)}"

    def bloque(r_linea, filas):
        ws.write(r_linea, 5, "LINEA", f.lab)
        ws.write(r_linea + 1, 5, "S", f.lab)
        for j in range(NC):
            c = c0 + j
            ws.write_number(r_linea, c, j + 1, f.ent)
            ws.write_formula(r_linea + 1, c, f"=$B$7+({CELL(r_linea, c)}-50)*$H$3", f.num)
        for (r0, titulo, prima, strike, res_fx, etiqueta) in filas:
            ws.merge_range(r0, 3, r0 + 3, 4, titulo, f.bloque)
            for k, lab in enumerate(["PRIMA", "K", "S", "RES NETOS"]):
                ws.write(r0 + k, 5, lab, f.lab)
            ws.write(r0 + 4, 5, etiqueta, f.nota)
            for j in range(NC):
                c = c0 + j
                Pc, Kc, Sc = CELL(r0, c), CELL(r0 + 1, c), CELL(r0 + 2, c)
                ws.write_formula(r0, c, f"={prima}", f.num)
                ws.write_formula(r0 + 1, c, f"={strike}", f.num)
                ws.write_formula(r0 + 2, c, f"={CELL(r_linea + 1, c)}", f.num)
                ws.write_formula(r0 + 3, c, res_fx(Pc, Kc, Sc), f.res)

    nombre = "STRADDLE" if tipo == "straddle" else "STRANGLE"
    bloque(5, [(7, "LONG CALL", "$D$2", "$C$2", lambda P, K, S: f"=MAX({S}-{K},0)-{P}", "máx(S−K,0) − P"),
               (13, "LONG PUT", "$E$3", "$C$3", lambda P, K, S: f"=MAX({K}-{S},0)-{P}", "máx(K−S,0) − P")])
    ws.write(19, 5, "RES NETOS", f.lab); ws.write(20, 5, "RCALL+RPUT", f.nota)
    ws.merge_range(19, 3, 20, 4, f"LONG {nombre}", f.head_t)
    for j in range(NC):
        c = c0 + j
        ws.write_formula(19, c, f"={CELL(10, c)}+{CELL(16, c)}", f.mon_b)
    bloque(23, [(25, "SHORT CALL", "$D$2", "$C$2", lambda P, K, S: f"={P}-MAX({S}-{K},0)", "P − máx(S−K,0)"),
                (31, "SHORT PUT", "$E$3", "$C$3", lambda P, K, S: f"={P}-MAX({K}-{S},0)", "P − máx(K−S,0)")])
    ws.write(37, 5, "RES NETOS", f.lab); ws.write(38, 5, "RCALL+RPUT", f.nota)
    ws.merge_range(37, 3, 38, 4, f"SHORT {nombre}", f.head_t)
    for j in range(NC):
        c = c0 + j
        ws.write_formula(37, c, f"={CELL(28, c)}+{CELL(34, c)}", f.mon_b)
    # Resumen
    r = 41
    ws.merge_range(r, 0, r, 4, f"{nombre}: resumen por unidad de subyacente", f.head)
    res = [("Costo neto LONG (primas pagadas)", "=D2+E3", f.mon), ("Punto de equilibrio inferior", "=C3-(D2+E3)", f.num),
           ("Punto de equilibrio superior", "=C2+(D2+E3)", f.num), ("Pérdida máxima LONG", "=-(D2+E3)", f.mon),
           ("Ganancia máxima SHORT", "=D2+E3", f.mon), ("Contratos (multiplicador)", p.get("mult", 100), f.ent_in),
           ("Costo neto LONG por contrato", "=B43*B48", f.mon)]
    for k, (lab, v, fm) in enumerate(res):
        ws.write(r + 1 + k, 0, lab, f.lab_r)
        (ws.write_formula if isinstance(v, str) else ws.write)(r + 1 + k, 1, v, fm)
    ws.write(r + 9, 0, "Ganancia LONG ilimitada al alza; pérdida SHORT ilimitada al alza y hasta K − primas a la baja. "
                       "Estrategia de VOLATILIDAD: no es una cobertura. Resultados al vencimiento (payoff terminal).", f.nota)
    ws.set_column("A:A", 30); ws.set_column("B:B", 16); ws.set_column("C:E", 12); ws.set_column("F:F", 13)
    ws.set_column(c0, cf, 9)
    ws.freeze_panes(0, 6)
    cat = rango(6)
    cat2 = rango(24)
    graf = [("LONG CALL", rango(10), cat, "G53"), ("LONG PUT", rango(16), cat, "P53"), (f"LONG {nombre}", rango(19), cat, "Y53"),
            ("SHORT CALL", rango(28), cat2, "G70"), ("SHORT PUT", rango(34), cat2, "P70"), (f"SHORT {nombre}", rango(37), cat2, "Y70")]
    charts = {}
    for titulo, vals, cats, pos in graf:
        ch = _grafica_linea(wb, titulo, hoja, cats, vals, titulo, "Precio del subyacente (S)", "Resultado por unidad",
                            color=TURQ if "SHORT" in titulo else AZUL, ancho=560, alto=300)
        ch.set_legend({"none": True})
        ch.set_x_axis({"name": "S", "num_format": "#,##0", "interval_unit": 10, "num_font": {"size": 8}})
        ws.insert_chart(pos, ch)
        charts[titulo] = (cats, vals)
    return charts


# ======================================================================== COMPRA VTA FUT
def hoja_futuros(wb, f, p, info):
    ws = wb.add_worksheet(H_FUT)
    ult = info["ult"]
    for j, e in enumerate(["Fecha", p["emisora"], "Apertura", "Máximo", "Mínimo", "Vol.", "% var."]):
        ws.write(0, j, e, f.head)
    for i in range(ult - 1):
        er = i + 2
        ws.write_formula(i + 1, 0, f"={H_DATOS}!A{er}", f.fecha_v)
        for j, c in enumerate("BCDE"):
            ws.write_formula(i + 1, 1 + j, f"={H_DATOS}!{c}{er}", f.num_v)
        ws.write_formula(i + 1, 5, f"={H_DATOS}!F{er}", f.vol_v)
        ws.write_formula(i + 1, 6, f"={H_DATOS}!G{er}", f.pct_v)
    G = f"G3:G{ult}"
    ws.merge_range("I3:K3", "Value at Risk (JP Morgan, paramétrico)", f.head)
    ws.write("L3", "(confianza editable)", f.nota)
    for j, e in enumerate(["ACTIVO", "RENTABILIDAD", "VARIANZA", "RIESGO", "CONFIANZA", "F(Z)", "MONTO", "TIEMPO días"]):
        ws.write(3, 8 + j, e, f.head)
    ws.write_formula("I5", "=B1", f.lab)
    ws.write_formula("J5", f"=AVERAGE({G})", f.pct); ws.write_formula("K5", f"=VAR({G})", f.num6)
    ws.write_formula("L5", "=SQRT(K5)", f.pct)
    ws.write_number("M5", p["confianza"], f.pct_in); ws.write_formula("N5", "=NORMSINV(M5)", f.num4)
    ws.write_number("O5", p["monto"], f.num_in); ws.write_number("P5", p["dias_var"], f.ent_in)
    for k, (s, t, ref) in enumerate([("σ", "riesgo", "=L5"), ("F", "confianza", "=N5"), ("S", "monto", "=O5"), ("t", "tiempo", "=P5")]):
        ws.write(6 + k, 8, s, f.lab); ws.write(6 + k, 9, t, f.txt); ws.write_formula(6 + k, 10, ref, f.num4 if k < 2 else f.num)
    ws.write("M7", "VaR = F·S·σ·√t", f.lab)
    ws.write("M9", "Value at Risk =", f.lab); ws.write_formula("N9", "=K8*K9*K7*SQRT(K10)", f.mon_b)
    ws.write("M10", "Pérdida que no se excedería con la confianza indicada en t días (supone normalidad y rendimientos "
                    "independientes; medida histórica, no pronóstico).", f.nota)
    for j, e in enumerate(["", "RENTABILIDAD", "VARIANZA", "RIESGO", "CONFIANZA", "F(Z)", "MONTO", "TIEMPO días", "VaR"]):
        if e:
            ws.write(11, 12 + j, e, f.head)
    for k, (a, b) in enumerate(info["tramos"]):
        r = 12 + k
        g = f"G{a}:G{b}"
        ws.write(r, 12, f"var ciclo {k+1}", f.lab_r)
        ws.write_formula(r, 13, f"=AVERAGE({g})", f.pct); ws.write_formula(r, 14, f"=VAR({g})", f.num6)
        ws.write_formula(r, 15, f"=SQRT({CELL(r, 14)})", f.pct); ws.write_formula(r, 16, "=$M$5", f.pct)
        ws.write_formula(r, 17, f"=NORMSINV({CELL(r, 16)})", f.num4); ws.write_formula(r, 18, "=$O$5", f.num)
        ws.write_formula(r, 19, "=$P$5", f.ent)
        ws.write_formula(r, 20, f"={CELL(r,17)}*{CELL(r,18)}*{CELL(r,15)}*SQRT({CELL(r,19)})", f.mon_b)
    ws.write("I18", "", f.txt)
    for j, e in enumerate(["CICLO", "BETAS", "CORR"]):
        ws.write(17, 8 + j, e, f.head)
    for k in range(4):
        ws.write(18 + k, 8, f"C{k+1}", f.lab_r)
        ws.write_formula(18 + k, 9, f"={H_DATOS}!U{16 + 3*k}", f.num4)
        ws.write_formula(18 + k, 10, f"={H_DATOS}!S{27 + k}", f.num4)
    # Futuros: compra y venta
    ws.merge_range("W3:Z3", "COMPRA / VENTA DE FUTUROS", f.head)
    ent = [("Spot (S)", f"={H_DATOS}!U5", f.num_v), ("r (continua)", f"={H_BS}!C5", f.pct_v), ("q (continuo)", f"={H_BS}!C6", f.pct_v),
           ("Días al vencimiento", f"={H_BS}!C7", f.num_v), ("Futuro teórico F0 = S·e^((r−q)T)", "=X4*EXP((X5-X6)*X7/365)", f.num4),
           ("Futuro OBSERVADO (0 = usar teórico)", p.get("f_obs", 0.0), f.num_in), ("F0 usado", "=IF(X9>0,X9,X8)", f.res),
           ("Multiplicador (acciones/contrato)", p.get("mult_fut", 100), f.ent_in), ("Contratos", p.get("n_fut", 1), f.ent_in),
           ("Paso de precio (%)", 0.01, f.pct_in)]
    for k, (lab, v, fm) in enumerate(ent):
        r = 3 + k
        ws.write(r, 22, lab, f.lab_r)
        (ws.write_formula if isinstance(v, str) else ws.write)(r, 23, v, fm)
    for j, e in enumerate(["Escenario", "Precio al vencimiento (S_T = F_T)", "Compra de futuros (P&L)", "Venta de futuros (P&L)"]):
        ws.write(15, 22 + j, e, f.head)
    nfil = 41
    for i in range(nfil):
        r = 16 + i
        R = r + 1
        ws.write_number(r, 22, i - 20, f.ent)
        ws.write_formula(r, 23, f"=$X$4*(1+W{R}*$X$13)", f.num)
        ws.write_formula(r, 24, f"=$X$12*$X$11*(X{R}-$X$10)", f.mon)
        ws.write_formula(r, 25, f"=-Y{R}", f.mon)
    ws.write(16 + nfil + 1, 22, "P&L = n·M·(F_T − F0); signo inverso en ventas. Excluye comisiones. La garantía (AIM) es un "
                                 "depósito, no un costo.", f.nota)
    cat = f"$X$17:$X${16+nfil}"
    for titulo, col, pos, color in [("Compra de futuros", "$Y", "AB3", AZUL), ("Venta de futuros", "$Z", "AB19", TURQ)]:
        ch = _grafica_linea(wb, titulo, H_FUT, cat, f"{col}$17:{col}${16+nfil}", titulo, "Precio al vencimiento", "P&L (MXN)",
                            color=color, ancho=520, alto=280)
        ch.set_legend({"none": True}); ws.insert_chart(pos, ch)
    ch = _grafica_linea(wb, "Compra", H_FUT, cat, f"$Y$17:$Y${16+nfil}", "Compra vs venta de futuros", "Precio al vencimiento",
                        "P&L (MXN)", extra=[{"name": "Venta", "values": f"={q(H_FUT)}!$Z$17:$Z${16+nfil}",
                                             "line": {"color": TURQ, "width": 2}}], ancho=520, alto=280)
    ws.insert_chart("AB35", ch)
    ws.set_column("A:A", 11); ws.set_column("B:E", 10); ws.set_column("F:G", 9); ws.set_column("I:I", 10)
    ws.set_column("J:U", 12); ws.set_column("W:W", 32); ws.set_column("X:Z", 16)
    ws.freeze_panes(1, 1)


# ======================================================================== BTFL
def hoja_mariposa(wb, f, p, info, celdas_bs):
    ws = wb.add_worksheet(H_BTF)
    ult = info["ult"]
    for j, e in enumerate(["Fecha", p["emisora"], "Apertura", "Máximo", "Mínimo", "Vol.", "% var."]):
        ws.write(0, j, e, f.head)
    for i in range(ult - 1):
        er = i + 2
        ws.write_formula(i + 1, 0, f"={H_DATOS}!A{er}", f.fecha_v)
        for j, c in enumerate("BCDE"):
            ws.write_formula(i + 1, 1 + j, f"={H_DATOS}!{c}{er}", f.num_v)
        ws.write_formula(i + 1, 5, f"={H_DATOS}!F{er}", f.vol_v)
        ws.write_formula(i + 1, 6, f"={H_DATOS}!G{er}", f.pct_v)
    ws.merge_range("J3:M3", "BUTTERFLY", f.bloque)
    ws.write("I29", "PRECIO TENDENCIA", f.lab_r); ws.write_number("J29", p["tendencia"], f.num_in)
    ws.write("K29", p.get("fuente_tendencia", ""), f.nota)
    ws.write("I30", "RIESGO", f.lab_r); ws.write_formula("J30", f"=STDEV(B2:B{ult})", f.num)
    ws.write("K30", "Desv. est. del precio en el período", f.nota)
    ws.write("I32", "SPREAD MAX", f.lab_r); ws.write_formula("J32", "=J29+J30", f.res)
    ws.write("I33", "SPREAD MIN", f.lab_r); ws.write_formula("J33", "=J29-J30", f.res)
    ng = 201

    def bloque(c_desc, tipo, titulo_merge, refs_prima):
        # c_desc: columna 0-based de DESCRIPTION (P=15 o AK=36)
        cK, cP, cPos, cCost = c_desc + 1, c_desc + 2, c_desc + 3, c_desc + 4
        for j, e in enumerate(["DESCRIPTION", "STRIKE", "PRIMA", "POSICION", "COSTO NETO"]):
            ws.write(1, c_desc + j, e, f.head)
        ws.merge_range(2, c_desc - 1, 4, c_desc - 1, titulo_merge, f.bloque)
        etiquetas = [f"LONG {tipo} BAJO", f"SHORT {tipo} MEDIO", f"LONG {tipo} ALTO"]
        strikes = ["=J33", "=J29", "=J32"]
        pos = [1, -2, 1]
        obs = p.get("primas_obs", {}).get(f"btfl_{tipo.lower()}", {})
        for k in range(3):
            ws.write(2 + k, c_desc, etiquetas[k], f.lab_r)
            ws.write_formula(2 + k, cK, strikes[k], f.num)
            if obs.get(k):
                ws.write_number(2 + k, cP, obs[k], f.num_in)
            else:
                ws.write_formula(2 + k, cP, f"={refs_prima[k]}", f.num_v)
            ws.write_number(2 + k, cPos, pos[k], f.ent_in)
        ws.merge_range(2, cCost, 4, cCost, "", f.mon_b)
        ws.write_formula(2, cCost, f"=SUMPRODUCT({CELL(2,cP)}:{CELL(4,cP)},{CELL(2,cPos)}:{CELL(4,cPos)})", f.mon_b)
        ws.write(5, cK, "EJERCICIO", f.lab); ws.write(5, cP, "B/S", f.lab); ws.write(5, cPos, "LONG (+)", f.txt)
        ws.write(6, cPos, "SHORT (−)", f.txt)
        ws.write(7, cPos, "# TOTAL CONTRATOS", f.lab)
        ws.write_formula(7, cCost, f"=ABS({CELL(2,cPos)})+ABS({CELL(3,cPos)})+ABS({CELL(4,cPos)})", f.ent)
        ws.write(9, cK, "SPOT", f.lab)
        ws.write_formula(9, cK + 1, f"=LOOKUP(9.99E+307,B2:B{ult})", f.num)
        ws.write(9, cPos, "POSITION=0", f.lab)
        ws.write_formula(9, cCost, f'=IF(SUM({CELL(2,cPos)}:{CELL(4,cPos)})=0,"OK","REVISAR")', f.txt_c)
        ws.write(11, cPos, "DIFF", f.lab); ws.write_number(11, cCost, p["paso_btfl"], f.num_in)
        ws.write(12, c_desc, "Costo neto > 0 = prima pagada. GANANCIA NETA = PAYOFF TOTAL − COSTO NETO.", f.nota)
        return cK, cP, cPos, cCost

    calls = [celdas_bs["Mariposa — K bajo"][0], celdas_bs["Mariposa — K medio"][0], celdas_bs["Mariposa — K alto"][0]]
    puts = [celdas_bs["Mariposa — K bajo"][1], celdas_bs["Mariposa — K medio"][1], celdas_bs["Mariposa — K alto"][1]]
    for (c_desc, c_grid, tipo, merge, refs) in [(15, 21, "CALL", "CALL", calls), (36, 42, "PUT", "PUT", puts)]:
        cK, cP, cPos, cCost = bloque(c_desc, tipo, merge, refs)
        hdr = ["BTFL", "PRECIO SUBYACENTE", f"PAYOFF {tipo} BAJO", f"PAYOFF {tipo} MEDIO", f"PAYOFF {tipo} ALTO",
               "PAYOFF TOTAL", "GANANCIA NETA"]
        for j, e in enumerate(hdr):
            ws.write(0, c_grid + j, e, f.head)
        spot = CELL(9, cK + 1, True, True)
        paso = CELL(11, cCost, True, True)
        for i in range(ng):
            r = 1 + i
            ws.write_number(r, c_grid, i + 1, f.ent)
            Sx = CELL(r, c_grid + 1)
            ws.write_formula(r, c_grid + 1, f"={spot}+({CELL(r, c_grid)}-{(ng+1)//2})*{paso}", f.num)
            for k in range(3):
                Kk = CELL(2 + k, cK, True, True)
                Pk = CELL(2 + k, cPos, True, True)
                pay = f"MAX(0,{Sx}-{Kk})" if tipo == "CALL" else f"MAX(0,{Kk}-{Sx})"
                ws.write_formula(r, c_grid + 2 + k, f"={pay}*{Pk}", f.num)
            ws.write_formula(r, c_grid + 5, f"=SUM({CELL(r, c_grid+2)}:{CELL(r, c_grid+4)})", f.num)
            ws.write_formula(r, c_grid + 6, f"={CELL(r, c_grid+5)}-{CELL(2, cCost, True, True)}", f.res)
        cat = f"{CELL(1, c_grid+1, True, True)}:{CELL(ng, c_grid+1, True, True)}"
        val = f"{CELL(1, c_grid+6, True, True)}:{CELL(ng, c_grid+6, True, True)}"
        ch = _grafica_linea(wb, f"Mariposa {tipo}", H_BTF, cat, val, f"Long {tipo.lower()} butterfly — ganancia neta",
                            "Precio del subyacente", "Resultado por unidad", color=AZUL if tipo == "CALL" else TURQ,
                            ancho=560, alto=320)
        ch.set_legend({"none": True}); ch.set_x_axis({"name": "S", "num_format": "#,##0", "interval_unit": 20, "num_font": {"size": 8}})
        ws.insert_chart(1, c_grid + 7 + 1, ch)
    ch = _grafica_linea(wb, p["emisora"], H_BTF, f"$A$2:$A${ult}", f"$B$2:$B${ult}", f"Precio {p['emisora']}", ancho=520, alto=300)
    ch.set_x_axis({"date_axis": True, "num_format": "mmm-yy", "num_font": {"size": 8}})
    ws.insert_chart("H6", ch)
    ws.set_column("A:A", 11); ws.set_column("B:G", 10); ws.set_column("I:I", 18); ws.set_column("J:M", 11)
    ws.set_column("O:O", 7); ws.set_column("P:P", 18); ws.set_column("Q:T", 13); ws.set_column("V:AB", 12)
    ws.set_column("AJ:AJ", 7); ws.set_column("AK:AK", 18); ws.set_column("AL:AO", 13); ws.set_column("AQ:AW", 12)


# ======================================================================== ensamblado
def excel_integral(estudio: dict, p: dict, incluir_plataforma: bool = True) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter", datetime_format="dd/mm/yyyy", date_format="dd/mm/yyyy") as xw:
        wb = xw.book
        f = F(wb)
        rp.escribir_hojas(xw, estudio, ["Portada"])
        info = hoja_datos(wb, f, p)
        hoja_rsi(wb, f, p, info)
        celdas = hoja_bs(wb, f, p, info)
        g_std = hoja_volatilidad(wb, f, p, celdas, H_STD, "straddle")
        hoja_volatilidad(wb, f, p, celdas, H_STG, "strangle")
        hoja_futuros(wb, f, p, info)
        hoja_mariposa(wb, f, p, info, celdas)
        if p.get("nota"):
            from .reports_nota import hoja_nota
            hoja_nota(wb, f, p["nota"], info["ult"])
        # gráficas de la hoja BS (straddle long put / long call), como en el archivo de referencia
        ws_bs = wb.get_worksheet_by_name(H_BS)
        for titulo, pos, color in [("LONG PUT", "B22", TURQ), ("LONG CALL", "I22", AZUL)]:
            cats, vals = g_std[titulo]
            ch = _grafica_linea(wb, titulo, H_STD, cats, vals, f"Straddle — {titulo.lower()}", "S", "Resultado", color=color,
                                ancho=480, alto=280)
            ch.set_legend({"none": True}); ch.set_x_axis({"num_format": "#,##0", "interval_unit": 10, "num_font": {"size": 8}})
            ws_bs.insert_chart(pos, ch)
        if incluir_plataforma:
            resto = [h for h in rp.HOJAS if h not in ("Portada", "Datos históricos")]
            rp.escribir_hojas(xw, estudio, resto)
    return buf.getvalue()


def datos_desde_df(df: pd.DataFrame, mk: pd.DataFrame) -> pd.DataFrame:
    """Une la emisora y el IPC en fechas comunes con las columnas que usa la hoja DATOS."""
    a = df[["Close", "Open", "High", "Low", "Volume"]].copy()
    b = mk[["Close", "Open", "High", "Low", "Volume"]].add_prefix("IPC_").copy()
    a["Volume"] = a["Volume"].fillna(0)
    b["IPC_Volume"] = b["IPC_Volume"].fillna(0)  # Yahoo no siempre publica volumen del índice
    return pd.concat([a, b], axis=1, join="inner").dropna()


def paso_redondo(spot: float, fraccion: float = 0.004) -> float:
    """Paso 'redondo' del eje de precios (≈0.4% del spot): 100 columnas cubren ≈ ±20%."""
    objetivo = spot * fraccion
    cands = [m * 10 ** e for e in range(-2, 5) for m in (1, 2, 2.5, 5)]
    return min(cands, key=lambda c: abs(c - objetivo))


def strike_redondo(x: float, spot: float) -> float:
    return round(round(x / paso_redondo(spot, 0.002)) * paso_redondo(spot, 0.002), 4)
