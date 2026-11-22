"""Generación de reportes Excel (XLSX) y PDF a partir de los MISMOS resultados que muestra la interfaz."""
from __future__ import annotations

import io

import numpy as np
import pandas as pd

HOJAS = ["Portada", "Fuentes y fechas", "Datos históricos", "Estados financieros", "Ratios", "DCF",
         "Análisis técnico", "Indicadores de riesgo", "Futuros", "Opciones", "Curvas de tasas", "Caps y floors",
         "Estrategias", "Perfiles de riesgo", "Escenarios", "Comparativas", "Fórmulas y supuestos"]

FORMULAS = pd.DataFrame([
    ("Rendimiento simple", "R_t = P_t / P_(t−1) − 1"),
    ("Rendimiento logarítmico", "r_t = ln(P_t / P_(t−1))"),
    ("Volatilidad anualizada", "σ = desv.est.(r_t, ddof=1) × √252 (diaria)"),
    ("Drawdown", "DD_t = P_t / máx(P_0..P_t) − 1"),
    ("ROC", "ROC(n) = [(P_t / P_(t−n)) − 1] × 100"),
    ("Williams %R", "−100 × (Máx_n − Cierre) / (Máx_n − Mín_n)"),
    ("Estocástico", "%K = 100 × (C − Mín_n)/(Máx_n − Mín_n); %D = SMA(%K)"),
    ("RSI (Wilder)", "RSI = 100 − 100/(1 + AG/AL), AG_t = (AG_(t−1)(n−1) + G_t)/n"),
    ("Beta", "β = Cov(R_a, R_m) / Var(R_m)"),
    ("VaR histórico", "VaR = −cuantil_(1−α)(R)"),
    ("Expected Shortfall", "ES = −E[R | R ≤ cuantil_(1−α)]"),
    ("CAPM", "Ke = rf + β·PRM + prima adicional"),
    ("WACC", "E/V·Ke + D/V·Kd·(1−t)"),
    ("DCF", "EV = Σ FCFF_t/(1+WACC)^t + VT/(1+WACC)^N; VT = FCFF_N(1+g)/(WACC−g)"),
    ("BSM call", "S e^(−qT) N(d1) − K e^(−rT) N(d2)"),
    ("CRR", "u = e^(σ√Δt), d = 1/u, p = (e^((r−q)Δt) − d)/(u − d)"),
    ("Futuro teórico", "F = S e^((r−q)T)"),
    ("P&L futuros", "n·M·(F_final − F_inicial); signo inverso en cortos"),
    ("Caplet (flujo)", "N·α·máx(R − K, 0)"),
    ("Floorlet (flujo)", "N·α·máx(K − R, 0)"),
    ("Black-76 caplet", "N·α·DF·[F N(d1) − K N(d2)]"),
    ("Bachelier caplet", "N·α·DF·[(F−K)N(d) + σ√T φ(d)]"),
    ("Forward simple", "F = (DF(t0)/DF(t1) − 1)/α"),
], columns=["concepto", "fórmula"])


def _limpiar(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    for c in d.columns:
        if pd.api.types.is_datetime64_any_dtype(d[c]):
            d[c] = d[c].dt.tz_localize(None) if getattr(d[c].dt, "tz", None) is not None else d[c]
        elif d[c].dtype == object:
            d[c] = d[c].apply(lambda x: str(x) if isinstance(x, (list, dict, tuple)) else x)
    d = d.replace([np.inf, -np.inf], np.nan)
    return d


def excel(estudio: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter", datetime_format="yyyy-mm-dd", date_format="yyyy-mm-dd") as xw:
        wb = xw.book
        tit = wb.add_format({"bold": True, "font_size": 16, "font_color": "#0B1F3A"})
        neg = wb.add_format({"bold": True})
        num = wb.add_format({"num_format": "#,##0.00"})
        pct = wb.add_format({"num_format": "0.00%"})
        nota = wb.add_format({"italic": True, "font_color": "#666666", "text_wrap": True})
        for nombre in HOJAS:
            if nombre == "Portada":
                ws = wb.add_worksheet(nombre)
                m = estudio.get("meta", {})
                ws.write(0, 0, "Informe de análisis financiero — Mercado mexicano", tit)
                fila = 2
                for k, v in m.items():
                    ws.write(fila, 0, str(k), neg); ws.write(fila, 1, str(v)); fila += 1
                ws.write(fila + 1, 0, "Aviso: herramienta de análisis. No ejecuta órdenes ni constituye recomendación. "
                         "Los valores teóricos y simulaciones no son cotizaciones oficiales.", nota)
                ws.set_column(0, 0, 32); ws.set_column(1, 1, 70)
                continue
            if nombre == "Fórmulas y supuestos":
                f = FORMULAS.copy()
                sup = estudio.get("supuestos")
                f.to_excel(xw, sheet_name=nombre, index=False)
                if isinstance(sup, pd.DataFrame) and not sup.empty:
                    _limpiar(sup).to_excel(xw, sheet_name=nombre, index=False, startrow=len(f) + 3)
                xw.sheets[nombre].set_column(0, 1, 60)
                continue
            if nombre == "Datos históricos":
                h = estudio.get("historico")
                if isinstance(h, pd.DataFrame) and not h.empty:
                    h = h.reset_index().rename(columns={"index": "Fecha", "Date": "Fecha"})
                    cols = [c for c in ["Fecha", "Open", "High", "Low", "Close", "Adj Close", "Volume"] if c in h]
                    h = h[cols]
                    _limpiar(h).to_excel(xw, sheet_name=nombre, index=False)
                    ws = xw.sheets[nombre]
                    ci = cols.index("Close")
                    col_letra = chr(ord("A") + ci)
                    j = len(cols)
                    ws.write(0, j, "Rend. simple (fórmula)", neg)
                    ws.write(0, j + 1, "Rend. log (fórmula)", neg)
                    for i in range(2, len(h) + 1):
                        ws.write_formula(i, j, f"={col_letra}{i+1}/{col_letra}{i}-1", pct)
                        ws.write_formula(i, j + 1, f"=LN({col_letra}{i+1}/{col_letra}{i})", pct)
                    ws.set_column(0, 0, 12); ws.set_column(1, j + 1, 14, num)
                    ws.freeze_panes(1, 1)
                    continue
            if nombre == "DCF":
                d = estudio.get("dcf")
                ws = wb.add_worksheet(nombre)
                if d:
                    p = d["parametros"]
                    filas = [("FCFF base", p["fcff0"]), ("WACC", p["wacc"]), ("g terminal", p["g"]),
                             ("Deuda neta", p["deuda_neta"]), ("Acciones", p["acciones"])]
                    for i, (k, v) in enumerate(filas):
                        ws.write(i, 0, k, neg); ws.write_number(i, 1, float(v), pct if k in ("WACC", "g terminal") else num)
                    r0 = 7
                    for c, h_ in enumerate(["Año", "Crecimiento", "FCFF", "Factor descuento", "VP"]):
                        ws.write(r0, c, h_, neg)
                    N = len(p["crecimientos"])
                    for i, g in enumerate(p["crecimientos"]):
                        r = r0 + 1 + i
                        ws.write_number(r, 0, i + 1)
                        ws.write_number(r, 1, g, pct)
                        prev = "B1" if i == 0 else f"C{r}"
                        ws.write_formula(r, 2, f"={prev}*(1+B{r+1})", num)
                        ws.write_formula(r, 3, f"=1/(1+$B$2)^(A{r+1}-0.5)" if p.get("medio") else f"=1/(1+$B$2)^A{r+1}", num)
                        ws.write_formula(r, 4, f"=C{r+1}*D{r+1}", num)
                    rl = r0 + N
                    ws.write(rl + 2, 0, "Valor terminal", neg); ws.write_formula(rl + 2, 1, f"=C{rl+1}*(1+B3)/(B2-B3)", num)
                    ws.write(rl + 3, 0, "VP valor terminal", neg); ws.write_formula(rl + 3, 1, f"=B{rl+3}/(1+B2)^{N}", num)
                    ws.write(rl + 4, 0, "Valor empresa", neg); ws.write_formula(rl + 4, 1, f"=SUM(E{r0+2}:E{rl+1})+B{rl+4}", num)
                    ws.write(rl + 5, 0, "Valor del capital", neg); ws.write_formula(rl + 5, 1, f"=B{rl+5}-B4", num)
                    ws.write(rl + 6, 0, "Valor por acción", neg); ws.write_formula(rl + 6, 1, f"=B{rl+6}/B5", num)
                    ws.write(rl + 8, 0, f"Valor por acción calculado por la plataforma: {d['resultado']['valor_por_accion']:.4f} "
                             "(debe coincidir con la fórmula de arriba)", nota)
                    ws.set_column(0, 4, 20)
                else:
                    ws.write(0, 0, "No calculado en esta sesión.", nota)
                continue
            clave = {"Fuentes y fechas": "fuentes", "Estados financieros": "estados", "Ratios": "ratios",
                     "Análisis técnico": "tecnico", "Indicadores de riesgo": "riesgo", "Futuros": "futuros",
                     "Opciones": "opciones", "Curvas de tasas": "curva", "Caps y floors": "caps",
                     "Estrategias": "estrategias", "Perfiles de riesgo": "perfiles", "Escenarios": "escenarios",
                     "Comparativas": "comparativas"}[nombre]
            obj = estudio.get(clave)
            if isinstance(obj, dict):  # varios bloques en una hoja
                fila = 0
                ws = wb.add_worksheet(nombre)
                xw.sheets[nombre] = ws
                for k, df in obj.items():
                    if isinstance(df, pd.DataFrame) and not df.empty:
                        ws.write(fila, 0, str(k), neg)
                        d = _limpiar(df.reset_index() if not isinstance(df.index, pd.RangeIndex) else df)
                        d.columns = [str(c) for c in d.columns]
                        d.to_excel(xw, sheet_name=nombre, index=False, startrow=fila + 1)
                        fila += len(d) + 4
                if fila == 0:
                    ws.write(0, 0, "No calculado en esta sesión o no disponible en la fuente.", nota)
                ws.set_column(0, 30, 16)
            elif isinstance(obj, pd.DataFrame) and not obj.empty:
                d = _limpiar(obj)
                d.columns = [str(c) for c in d.columns]
                d.to_excel(xw, sheet_name=nombre, index=False)
                ws = xw.sheets[nombre]
                ws.set_column(0, len(d.columns), 16)
                ws.freeze_panes(1, 0)
                ws.set_landscape(); ws.fit_to_pages(1, 0)
            else:
                ws = wb.add_worksheet(nombre)
                ws.write(0, 0, "No calculado en esta sesión o no disponible en la fuente.", nota)
    return buf.getvalue()


def pdf(estudio: dict, graficas: dict[str, bytes] | None = None) -> bytes:
    """PDF con secciones; graficas = {titulo: png_bytes}."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(letter), leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.5 * cm, title="Informe de análisis financiero")
    st = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=st["Heading1"], textColor=colors.HexColor("#0B1F3A"))
    h2 = ParagraphStyle("h2", parent=st["Heading2"], textColor=colors.HexColor("#0E7C86"))
    body = ParagraphStyle("b", parent=st["BodyText"], fontSize=9.5, leading=12)
    small = ParagraphStyle("s", parent=body, fontSize=7.5, leading=9)
    head = ParagraphStyle("hd", parent=small, textColor=colors.white, fontName="Helvetica-Bold")
    E = []

    def tabla(df: pd.DataFrame, max_filas=30, max_cols=10):
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            E.append(Paragraph("No calculado en esta sesión o no disponible en la fuente.", body)); return
        d = _limpiar(df.reset_index() if not isinstance(df.index, pd.RangeIndex) else df).iloc[:max_filas, :max_cols]
        def fmt(x):
            if isinstance(x, (float, np.floating)):
                return "—" if np.isnan(x) else f"{x:,.4g}" if abs(x) < 1e4 else f"{x:,.0f}"
            if isinstance(x, pd.Timestamp):
                return x.strftime("%Y-%m-%d")
            return str(x)[:40]
        data = [[Paragraph(str(c)[:30], head) for c in d.columns]] + [[Paragraph(fmt(v), small) for v in r] for r in d.values]
        t = Table(data, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B1F3A")),
                               ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                               ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#B0B7C3")),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F5F9")]),
                               ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        E.append(t)
        if len(df) > max_filas or df.shape[1] > max_cols:
            E.append(Paragraph(f"Se muestran {min(len(df), max_filas)} de {len(df)} filas; el detalle completo está en el Excel.", small))

    m = estudio.get("meta", {})
    E += [Paragraph("Informe de análisis financiero y coberturas", h1),
          Paragraph(f"{m.get('Activo', '')} — generado {m.get('Fecha de generación', '')}", body), Spacer(1, 8)]
    for k, v in m.items():
        E.append(Paragraph(f"<b>{k}:</b> {v}", body))
    E.append(Spacer(1, 10))
    E.append(Paragraph("<b>Aviso:</b> herramienta de análisis e investigación. No ejecuta órdenes, no promete resultados y no "
                       "presenta simulaciones como cotizaciones oficiales. Datos de mercado de Yahoo Finance (proveedor "
                       "secundario); deben reconciliarse con la BMV para usos oficiales.", body))
    E.append(PageBreak())
    E.append(Paragraph("Resumen ejecutivo", h2))
    E.append(Paragraph(estudio.get("resumen_ejecutivo", "No generado.").replace("**", "").replace("\n", "<br/>"), body))
    secciones = [("Metodología", "metodologia"), ("Fuentes y fechas", "fuentes"), ("Datos históricos (últimas filas)", "historico_tail"),
                 ("Ratios financieros", "ratios"), ("Valuación DCF", "dcf_tabla"), ("Análisis técnico", "tecnico_resumen"),
                 ("Patrones detectados", "patrones"), ("Riesgos", "riesgo_resumen"), ("Futuros", "futuros"),
                 ("Opciones", "opciones"), ("Caps y floors", "caps"), ("Estrategias de cobertura", "estrategias"),
                 ("Comparativas", "comparativas"), ("Cinco escenarios por perfil y estrategia", "escenarios"),
                 ("Limitaciones", "limitaciones")]
    for titulo, clave in secciones:
        E.append(Paragraph(titulo, h2))
        obj = estudio.get(clave)
        if isinstance(obj, str):
            E.append(Paragraph(obj.replace("\n", "<br/>"), body))
        elif isinstance(obj, dict):
            for k, df in obj.items():
                E.append(Paragraph(f"<b>{k}</b>", body)); tabla(df)
        else:
            tabla(obj, max_filas=45 if clave == "escenarios" else 30)
        if graficas and titulo in graficas:
            E.append(Spacer(1, 6))
            E.append(Image(io.BytesIO(graficas[titulo]), width=22 * cm, height=9 * cm))
        E.append(Spacer(1, 8))
    E.append(PageBreak())
    E.append(Paragraph("Anexo de fórmulas", h2))
    tabla(FORMULAS, max_filas=60)
    doc.build(E)
    return buf.getvalue()


def png_matplotlib(fig) -> bytes:
    b = io.BytesIO()
    fig.savefig(b, format="png", dpi=130, bbox_inches="tight")
    return b.getvalue()
