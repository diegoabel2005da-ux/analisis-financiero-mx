"""Hoja NOTA ESTRUCTURADA del Excel INTEGRAL (layout del archivo del usuario, con fórmulas vivas)."""
from __future__ import annotations

from pathlib import Path

from xlsxwriter.utility import xl_rowcol_to_cell as CELL

from .nota import PERFILES, ESCENARIOS_Z, ESTRATEGIAS_NOTA

H_NOTA = "NOTA ESTRUCTURADA"
IMG = Path(__file__).resolve().parents[1] / "data" / "img"


def _strike_formula(clave: str, idx: int) -> tuple[str, str, int]:
    """(tipo, fórmula del strike, posición) para cada leg; S0 en $U$26 y ancho en $U$41."""
    S, up, dn = "$U$26", "$U$26*(1+$U$41)", "$U$26*(1-$U$41)"
    tabla = {
        "STG": [("CALL", up, 1), ("PUT", dn, 1)],
        "BTF": [("CALL", dn, 1), ("CALL", S, -2), ("CALL", up, 1)],
        "FLOOR": [("PUT", f"{S}*0.95", 1)],
        "CALL": [("CALL", S, 1)],
        "COLLAR": [("PUT", f"{S}*0.95", 1), ("CALL", f"{S}*1.05", -1)],
    }[clave]
    return tabla[idx] if idx < len(tabla) else ("CALL", S, 0)


def hoja_nota(wb, f, p: dict, ult_datos: int, hoja_datos="DATOS", hoja_bs="BS"):
    ws = wb.add_worksheet(H_NOTA)
    n_acc = len(p["acciones"])
    ws.merge_range("D3:K3", "NOTA ESTRUCTURADA", f.bloque)
    ws.write("D4", "INVERSIÓN", f.lab_r); ws.write_number("E4", p["inversion"], f.num_in)
    for j, e in enumerate(["PERFIL", "KRF", "$", "KRF PROF", "UT KRF", "CAPITALES", "DERIVADOS", "NE", "NE %"]):
        ws.write(4, 3 + j, e, f.head)
    fila_pf = {"AGRESIVO": 5, "MODERADO": 6, "CONSERVADOR": 7}
    for pf, r in fila_pf.items():
        R = r + 1
        ws.write(r, 3, pf, f.lab_r)
        ws.write_number(r, 4, p["krf_pct"][pf], f.pct_in)
        ws.write_formula(r, 5, f"=E{R}*$E$4", f.mon)
        ws.write_formula(r, 6, f"=F{R}*(1+$G$10)", f.mon)
        ws.write_formula(r, 7, f"=G{R}-F{R}", f.mon)
        ws.write_formula(r, 10, f"=H{R}+I{R}+J{R}", f.mon_b)
        ws.write_formula(r, 11, f"=K{R}/$E$4", f.pct_b)
    ws.write("D10", "TIEMPO (días)", f.lab_r); ws.write_number("E10", p["dias"], f.ent_in)
    ws.write_number("F10", p["rf_anual"], f.pct_in); ws.write_formula("G10", "=(F10/360)*E10", f.pct)
    ws.write("H10", f"Tasa KRF: {p.get('fuente_rf', 'capturada por el usuario')}. Base ACT/360 (convención de Cetes).", f.nota)
    ws.write("D11", "PRIMA DE MERCADO", f.lab_r); ws.write_number("E11", p["prm"], f.pct_in)
    ws.write("F11", "Supuesto del analista para el CAPM: rendimiento = (rf + β·PRM)·días/365", f.nota)
    # Diversificación
    for j, e in enumerate(["DIVERSIFICACIÓN", "RISK", "$", "MERCADO CAPITALES", "$ MKDO CAPITALES", "DERIVADOS", "$ DERIVADOS"]):
        ws.write(11, 3 + j, e, f.head)
    fila_div = {"AGRESIVO": 12, "MODERADO": 13, "CONSERVADOR": 14}
    for pf, r in fila_div.items():
        R, Rk = r + 1, fila_pf[pf] + 1
        ws.write(r, 3, pf, f.lab_r)
        ws.write_formula(r, 4, f"=1-E{Rk}", f.pct)
        ws.write_formula(r, 5, f"=E{R}*$E$4", f.mon)
        ws.write_number(r, 6, p["cap_pct"][pf], f.pct_in)
        ws.write_formula(r, 7, f"=F{R}*G{R}", f.mon)
        ws.write_formula(r, 8, f"=1-G{R}", f.pct)
        ws.write_formula(r, 9, f"=F{R}*I{R}", f.mon)
    # Capitales
    ws.merge_range("D24:I24", "MKDO CAPITALES", f.bloque)
    for j, e in enumerate(["ACCIÓN", "BETA", "RENDIMIENTO", "CONSERVADOR", "MODERADO", "AGRESIVO"]):
        ws.write(24, 3 + j, e, f.head)
    ws.write("D26", "ACCIONES", f.lab)
    a0 = 26  # primera fila 0-based de acciones (Excel 27)
    w0 = a0 + n_acc + 12  # bloque de pesos
    for i, a in enumerate(p["acciones"]):
        r = a0 + i
        R = r + 1
        ws.write(r, 3, a["nombre"], f.lab_r)
        ws.write_number(r, 4, a["beta"], f.num_in)
        if p.get("modo_rend") == "manual":
            ws.write_number(r, 5, a["rend_manual"], f.pct_in)
        else:
            ws.write_formula(r, 5, f"=($F$10+E{R}*$E$11)*$E$10/365", f.pct)
        for j, (pf, fila_cap) in enumerate([("CONSERVADOR", 15), ("MODERADO", 14), ("AGRESIVO", 13)]):
            ws.write_formula(r, 6 + j, f"={CELL(w0 + 2 + i, 4 + j)}*$H${fila_cap}", f.mon)
    rs = a0 + n_acc  # fila 0-based de SUMA
    A, B = a0 + 1, a0 + n_acc  # filas Excel del rango de acciones
    ws.write(rs, 3, "SUMA", f.lab)
    ws.write(rs + 1, 3, "VALOR AL HORIZONTE", f.lab)
    ws.write(rs + 2, 3, "UTILIDADES", f.lab)
    ws.write(rs + 3, 3, "ASIGNADO (diversificación)", f.lab)
    ws.write(rs + 4, 3, "DIFERENCIA", f.lab)
    for j, (col, fila_cap) in enumerate([("G", 15), ("H", 14), ("I", 13)]):
        c = 6 + j
        ws.write_formula(rs, c, f"=SUM({col}{A}:{col}{B})", f.mon)
        ws.write_formula(rs + 1, c, f"=SUMPRODUCT({col}{A}:{col}{B},1+$F${A}:$F${B})", f.mon)
        ws.write_formula(rs + 2, c, f"={col}{rs+2}-{col}{rs+1}", f.mon_b)
        ws.write_formula(rs + 3, c, f"=$H${fila_cap}", f.mon)
        ws.write_formula(rs + 4, c, f"={col}{rs+1}-{col}{rs+4}", f.mon)
    ut = {"CONSERVADOR": f"G{rs+3}", "MODERADO": f"H{rs+3}", "AGRESIVO": f"I{rs+3}"}
    for pf, r in fila_pf.items():
        ws.write_formula(r, 8, f"={ut[pf]}", f.mon)  # corrige el vínculo del conservador del archivo original
    ws.write(rs + 6, 3, "Rendimiento: " + ("capturado por el usuario (azul)" if p.get("modo_rend") == "manual" else
                                          "CAPM con β calculada contra el S&P/BMV IPC") + ". Montos = peso × $ capitales del perfil.", f.nota)
    # Pesos
    ws.merge_range(w0, 3, w0, 6, "PESOS DE LA CANASTA (% del monto de capitales)", f.head)
    for j, e in enumerate(["ACCIÓN", "CONSERVADOR", "MODERADO", "AGRESIVO"]):
        ws.write(w0 + 1, 3 + j, e, f.head_t)
    for i, a in enumerate(p["acciones"]):
        ws.write(w0 + 2 + i, 3, a["nombre"], f.lab_r)
        for j, pf in enumerate(["CONSERVADOR", "MODERADO", "AGRESIVO"]):
            ws.write_number(w0 + 2 + i, 4 + j, a["pesos"][pf], f.pct_in)
    wt = w0 + 2 + n_acc
    ws.write(wt, 3, "TOTAL (debe ser 100%)", f.lab)
    for j in range(3):
        c = 4 + j
        ws.write_formula(wt, c, f"=SUM({CELL(w0+2, c)}:{CELL(wt-1, c)})", f.pct_b)
    # Derivados
    ws.merge_range("K24:R24", "DERIVADOS", f.bloque)
    for j, e in enumerate(["PERFIL", "MONTO", "FUTUROS (AIM)%", "MONTO FUT", "OPCIONES (PRIMAS) %", "MONTO OPC",
                           "ESTIMACIONES FUTUROS", "ESTIMACIONES EN OPCIONES"]):
        ws.write(24, 10 + j, e, f.head)
    fila_der = {"AGRESIVO": 25, "MODERADO": 26, "CONSERVADOR": 27}
    for pf, r in fila_der.items():
        R, Rk, Rd = r + 1, fila_pf[pf] + 1, fila_div[pf] + 1
        ws.write(r, 10, pf, f.lab_r)
        ws.write_formula(r, 11, f"=$E$4-F{Rk}-H{Rd}", f.mon)
        ws.write_number(r, 12, p["fut_pct"][pf], f.pct_in)
        ws.write_formula(r, 13, f"=L{R}*M{R}", f.mon)
        ws.write_formula(r, 14, f"=1-M{R}", f.pct)
        ws.write_formula(r, 15, f"=L{R}*O{R}", f.mon)
    # Parámetros de derivados
    d = p["derivados"]
    ws.merge_range("T25:V25", f"PARÁMETROS DERIVADOS · {d['nombre']}", f.head)
    params = [
        ("Spot del subyacente", f"={hoja_datos}!U5", f.num_v, "Último cierre (hoja DATOS)"),
        ("r (continua)", f"={hoja_bs}!C5", f.pct_v, "Hoja BS"),
        ("q (continuo)", f"={hoja_bs}!C6", f.pct_v, "Hoja BS"),
        ("σ subyacente (anual)", f"={hoja_datos}!U6", f.pct_v, "Histórica 1 año"),
        ("β subyacente", f"={hoja_datos}!R8", f.num_v, "vs S&P/BMV IPC"),
        ("σ IPC (anual)", f"=STDEV({hoja_datos}!N3:N{ult_datos})*SQRT(252)", f.pct, "Rend. simples del IPC × √252"),
        ("μ subyacente (CAPM, horizonte)", "=($F$10+U30*$E$11)*$E$10/365", f.pct, "Rendimiento esperado base"),
        ("T (años)", "=$E$10/365", f.num4, "Vencimiento de futuros y opciones = horizonte de la nota"),
        ("F0 teórico", "=U26*EXP((U27-U28)*U33)", f.num4, "S·e^((r−q)T); sin cotización MexDer"),
        ("Multiplicador futuros", d["mult_fut"], f.ent_in, "100 acciones por contrato (BMV)"),
        ("AIM % del nocional (supuesto)", d["aim_pct"], f.pct_in, "Verificar AIM real con Asigna/MexDer"),
        ("AIM por contrato capturada (0 = usar %)", d.get("aim_contrato") or 0.0, f.num_in, "MXN"),
        ("AIM usada por contrato", "=IF(U37>0,U37,U36*U34*U35)", f.res, "Depósito recuperable, no costo"),
        ("Multiplicador opciones", d["mult_opc"], f.ent_in, "100 acciones por contrato"),
        ("S estimado (escenario base)", "=U26*EXP(U32)", f.res, "S0·e^μ"),
        ("Ancho de alas STG/BTF", d.get("ancho", 0.05), f.pct_in, "% del spot"),
    ]
    for k, (lab, v, fm, nota) in enumerate(params):
        r = 25 + k
        ws.write(r, 19, lab, f.lab_r)
        (ws.write_formula if isinstance(v, str) else ws.write)(r, 20, v, fm)
        ws.write(r, 21, nota, f.nota)
    # Futuros detalle
    fr0 = 30
    for j, e in enumerate(["FUTUROS", "SUBYACENTE", "CONTRATOS", "GARANTÍA (AIM)", "NOCIONAL", "EFECTIVO SIN USAR", "ESTIMACIÓN",
                           "NOCIONAL / INVERSIÓN"]):
        ws.write(fr0, 10 + j, e, f.head)
    fila_fut = {}
    for k, pf in enumerate(PERFILES):
        r = fr0 + 1 + k
        R, Rd = r + 1, fila_der[pf] + 1
        fila_fut[pf] = R
        ws.write(r, 10, pf, f.lab_r)
        ws.write(r, 11, d["nombre"], f.txt)
        ws.write_formula(r, 12, f"=IF($U$38>0,INT(N{Rd}/$U$38),0)", f.ent)
        ws.write_formula(r, 13, f"=M{R}*$U$38", f.mon)
        ws.write_formula(r, 14, f"=M{R}*$U$35*$U$34", f.mon)
        ws.write_formula(r, 15, f"=N{Rd}-N{R}", f.mon)
        ws.write_formula(r, 16, f"=M{R}*$U$35*($U$40-$U$34)", f.mon_b)
        ws.write_formula(r, 17, f"=O{R}/$E$4", f.pct)
        ws.write_formula(fila_der[pf], 16, f"=Q{R}", f.mon)
    ws.write(fr0 + 4, 10, "Posición larga en futuros; resultado = contratos·M·(S estimado − F0). La garantía se recupera al cerrar.", f.nota)
    # Opciones detalle (3 legs por perfil)
    or0 = 42
    for j, e in enumerate(["OPCIONES", "ESTRATEGIA", "LEG", "TIPO", "STRIKE", "POSICIÓN", "PRIMA BSM", "RES. BASE /U",
                           "PRIMAS PAGADAS", "CONTRATOS", "ESTIMACIÓN"]):
        ws.write(or0, 10 + j, e, f.head)
    S, sig, r_, q_, T = "$U$26", "$U$29", "$U$27", "$U$28", "$U$33"
    fila_opc = {}
    for k, pf in enumerate(PERFILES):
        clave = p["estrategia"][pf]
        base = or0 + 1 + 3 * k
        Rb = base + 1
        fila_opc[pf] = Rb
        for i in range(3):
            r = base + i
            R = r + 1
            tipo, kf, pos = _strike_formula(clave, i)
            ws.write(r, 10, pf if i == 0 else "", f.lab_r if i == 0 else f.txt)
            ws.write(r, 11, f"{clave} — {ESTRATEGIAS_NOTA[clave]}" if i == 0 else "", f.txt)
            ws.write_number(r, 12, i + 1, f.ent)
            ws.write(r, 13, tipo, f.txt_c)
            ws.write_formula(r, 14, f"={kf}", f.num)
            ws.write_number(r, 15, pos, f.ent_in)
            d1 = f"(LN({S}/O{R})+({r_}-{q_}+{sig}^2/2)*{T})/({sig}*SQRT({T}))"
            d2 = f"({d1}-{sig}*SQRT({T}))"
            call = f"{S}*EXP(-{q_}*{T})*NORMSDIST({d1})-O{R}*EXP(-{r_}*{T})*NORMSDIST({d2})"
            put = f"O{R}*EXP(-{r_}*{T})*NORMSDIST(-{d2})-{S}*EXP(-{q_}*{T})*NORMSDIST(-{d1})"
            ws.write_formula(r, 16, f'=IF(N{R}="CALL",{call},{put})', f.num4)
            ws.write_formula(r, 17, f'=P{R}*(IF(N{R}="CALL",MAX($U$40-O{R},0),MAX(O{R}-$U$40,0))-Q{R})', f.num4)
        rng = lambda c: f"{c}{Rb}:{c}{Rb+2}"
        ws.write_formula(base, 18, f"=SUMPRODUCT(({rng('P')}>0)*{rng('P')}*{rng('Q')})", f.num4)
        ws.write_formula(base, 19, f"=IF(S{Rb}>0,INT(P{fila_der[pf]+1}/($U$39*S{Rb})),0)", f.ent)
        ws.write_formula(base, 20, f"=T{Rb}*$U$39*SUM({rng('R')})", f.mon_b)
        ws.write_formula(fila_der[pf], 17, f"=U{Rb}", f.mon)
    ws.write(or0 + 10, 10, "Primas TEÓRICAS (BSM, vencimiento = horizonte). Contratos = monto de opciones / (M × primas pagadas); "
                          "las primas vendidas (posición negativa) se reciben como ingreso. Resultado al vencimiento.", f.nota)
    for pf, r in fila_pf.items():
        ws.write_formula(r, 9, f"=Q{fila_der[pf]+1}+R{fila_der[pf]+1}", f.mon)
    # Escenarios
    e0 = max(wt, or0 + 11) + 3
    ws.merge_range(e0, 3, e0, 13, "ESCENARIOS DE LA NOTA (hipótesis de simulación, sin probabilidades)", f.bloque)
    for j, e in enumerate(["PERFIL", "ESCENARIO", "z (σ)", "S SUBYACENTE", "UT KRF", "CAPITALES", "FUTUROS", "OPCIONES",
                           "NE", "VALOR FINAL", "NE %"]):
        ws.write(e0 + 1, 3 + j, e, f.head)
    cap_col = {"CONSERVADOR": "G", "MODERADO": "H", "AGRESIVO": "I"}
    r = e0 + 2
    filas_ne = {pf: [] for pf in PERFILES}
    z_cells = []
    for k, pf in enumerate(PERFILES):
        for i, (nombre, z) in enumerate(ESCENARIOS_Z):
            R = r + 1
            ws.write(r, 3, pf, f.lab_r)
            ws.write(r, 4, nombre, f.txt)
            if k == 0:
                ws.write_number(r, 5, z, f.num_in)
                z_cells.append(f"$F${R}")
            else:
                ws.write_formula(r, 5, f"={z_cells[i]}", f.num)
            ws.write_formula(r, 6, f"=$U$26*EXP($U$32+F{R}*$U$29*SQRT($U$33))", f.num)
            ws.write_formula(r, 7, f"=$H${fila_pf[pf]+1}", f.mon)
            c = cap_col[pf]
            ws.write_formula(r, 8, f"=SUMPRODUCT({c}${A}:{c}${B},$F${A}:$F${B}+$E${A}:$E${B}*F{R}*$U$31*SQRT($U$33))", f.mon)
            ws.write_formula(r, 9, f"=$M${fila_fut[pf]}*$U$35*(G{R}-$U$34)", f.mon)
            Rb = fila_opc[pf]
            legs = "+".join(f'$P${Rb+i_}*(IF($N${Rb+i_}="CALL",MAX(G{R}-$O${Rb+i_},0),MAX($O${Rb+i_}-G{R},0))-$Q${Rb+i_})'
                            for i_ in range(3))
            ws.write_formula(r, 10, f"=$T${Rb}*$U$39*({legs})", f.mon)
            ws.write_formula(r, 11, f"=H{R}+I{R}+J{R}+K{R}", f.mon_b)
            ws.write_formula(r, 12, f"=$E$4+L{R}", f.mon)
            ws.write_formula(r, 13, f"=L{R}/$E$4", f.pct_b)
            filas_ne[pf].append(R)
            r += 1
    ws.write(r + 1, 3, "S_h = S0·e^(μ + z·σ·√T); acciones: r_i = rendimiento_i + β_i·z·σ_IPC·√T. z = 0 reproduce la estimación base.", f.nota)
    # Gráficas
    ch = wb.add_chart({"type": "column"})
    for pf, color in zip(PERFILES, ["#C0392B", "#14B8C4", "#0B1F3A"]):
        fl = filas_ne[pf]
        ch.add_series({"name": pf, "categories": f"='{H_NOTA}'!$E${fl[0]}:$E${fl[-1]}",
                       "values": f"='{H_NOTA}'!$L${fl[0]}:$L${fl[-1]}", "fill": {"color": color}})
    ch.set_title({"name": "Resultado neto (NE) por escenario y perfil", "name_font": {"size": 11, "color": "#0B1F3A"}})
    ch.set_y_axis({"num_format": '"$"#,##0', "major_gridlines": {"visible": True, "line": {"color": "#E0E0E0"}}})
    ch.set_x_axis({"num_font": {"size": 8}}); ch.set_legend({"position": "bottom"}); ch.set_size({"width": 720, "height": 340})
    ws.insert_chart(e0 + 1, 15, ch)
    cc = wb.add_chart({"type": "bar", "subtype": "stacked"})
    for lab, col in [("KRF", "F"), ("Capitales", "H"), ("Futuros (AIM)", "N"), ("Opciones (primas)", "P")]:
        vals = ([f"{col}{fila_pf[pf]+1}" for pf in PERFILES] if col == "F" else
                [f"{col}{fila_div[pf]+1}" for pf in PERFILES] if col == "H" else [f"{col}{fila_der[pf]+1}" for pf in PERFILES])
        cc.add_series({"name": lab, "categories": f"='{H_NOTA}'!$D$6:$D$8",
                       "values": "=(" + ",".join(f"'{H_NOTA}'!${v[0]}${v[1:]}" for v in vals) + ")"})
    cc.set_title({"name": "Composición de la inversión por perfil", "name_font": {"size": 11, "color": "#0B1F3A"}})
    cc.set_x_axis({"num_format": '"$"#,##0'}); cc.set_legend({"position": "bottom"}); cc.set_size({"width": 520, "height": 255})
    ws.insert_chart("M10", cc)
    # Imágenes del modelo original
    for nombre, pos, esc in [("nota_krf_xrisk.png", "D17", 0.26), ("nota_perfiles.png", "T3", 0.22), ("nota_dificultad.png", "V3", 0.25)]:
        ruta = IMG / nombre
        if ruta.exists():
            ws.insert_image(pos, str(ruta), {"x_scale": esc, "y_scale": esc, "object_position": 3})
    ws.set_column("A:C", 2); ws.set_column("D:D", 26); ws.set_column("E:E", 24); ws.set_column("F:J", 15); ws.set_column("K:K", 14)
    ws.set_column("L:L", 34); ws.set_column("M:S", 15); ws.set_column("T:T", 36); ws.set_column("U:U", 15); ws.set_column("V:V", 30)
    return {"filas_ne": filas_ne}
