"""Reporte ejecutivo (PDF) de la nota estructurada."""
from __future__ import annotations

import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from . import perfil as pfm  # noqa: E402


def pdf(p: dict, r: dict, recomendado: str, fecha: str, fuentes: list[str]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=1.6 * cm, rightMargin=1.6 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                            title="Reporte ejecutivo — Nota estructurada")
    st = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=st["Heading1"], textColor=colors.HexColor("#0B1F3A"))
    h2 = ParagraphStyle("h2", parent=st["Heading2"], textColor=colors.HexColor("#0E7C86"))
    body = ParagraphStyle("b", parent=st["BodyText"], fontSize=9.5, leading=12.5)
    small = ParagraphStyle("s", parent=body, fontSize=7.5, leading=9.5)
    head = ParagraphStyle("hd", parent=small, textColor=colors.white, fontName="Helvetica-Bold")
    E = []

    def tabla(df, cols=None, fmt=None):
        d = df[cols] if cols else df
        fmt = fmt or {}
        def f(c, v):
            if c in fmt:
                try:
                    return fmt[c].format(v)
                except Exception:
                    return str(v)
            if isinstance(v, (float, np.floating)):
                return "—" if np.isnan(v) else (f"{v:,.2f}" if abs(v) < 1e6 else f"{v:,.0f}")
            return str(v)
        data = [[Paragraph(str(c), head) for c in d.columns]] + [[Paragraph(f(c, v), small) for c, v in zip(d.columns, row)] for row in d.values]
        t = Table(data, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B1F3A")), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#B0B7C3")),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F5F9")]), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        E.append(t)

    res = r["resumen"].set_index("perfil")
    rec = res.loc[recomendado]
    E += [Paragraph("Reporte ejecutivo — Nota estructurada", h1),
          Paragraph(f"[Nombre de la institución] · Fecha de elaboración: {fecha} · Inversión: ${p['inversion']:,.0f} MXN · Horizonte: {p['dias']} días", body),
          Spacer(1, 8)]
    if p.get("puntaje") is not None:
        E.append(Paragraph(f"<b>Perfil del inversionista:</b> puntaje {p['puntaje']*100:.0f}/100 → referencia {pfm.perfil_referencia(p['puntaje'])}. "
                           f"Propuesta recomendada: <b>{recomendado}</b>.", body))
    E.append(Paragraph(f"<b>Resultado neto estimado (escenario neutral):</b> ${rec['NE']:,.0f} ({rec['NE %']*100:.2f}% en el horizonte; "
                       f"{rec['NE anualizado %']*100:.2f}% anualizado). Renta fija elegida: {rec['renta fija']}.", body))
    ch = r["chequeo"].set_index("perfil").loc[recomendado]
    E.append(Paragraph(f"<b>Objetivo y tolerancia:</b> objetivo al horizonte {ch['objetivo (horizonte) %']*100:.2f}% → "
                       f"{'se cumple' if ch['cumple objetivo'] else 'NO se cumple'} en el escenario neutral; pérdida en el escenario adverso moderado "
                       f"{ch['pérdida adverso moderado %']*100:.2f}% frente a una tolerancia de {ch['pérdida tolerada %']*100:.1f}% → "
                       f"{'dentro' if ch['dentro de tolerancia'] else 'FUERA'} de tolerancia.", body))
    E.append(Spacer(1, 6))
    E.append(Paragraph("Composición del capital", h2))
    tabla(r["diversificacion"], ["perfil", "renta fija %", "capitales %", "futuros %", "opciones %"],
          {k: "{:.1%}" for k in ["renta fija %", "capitales %", "futuros %", "opciones %"]})
    fig, ax = plt.subplots(figsize=(7.2, 2.6))
    dv = r["diversificacion"].set_index("perfil")[["renta fija %", "capitales %", "futuros %", "opciones %"]]
    left = np.zeros(len(dv))
    for col, c in zip(dv.columns, ["#0B1F3A", "#14B8C4", "#E8833A", "#8FA9BC"]):
        ax.barh(dv.index, dv[col], left=left, color=c, label=col.replace(" %", ""))
        left += dv[col].values
    ax.legend(ncol=4, fontsize=7, loc="lower center", bbox_to_anchor=(0.5, -0.38)); ax.set_xlim(0, 1)
    b = io.BytesIO(); fig.savefig(b, format="png", dpi=140, bbox_inches="tight"); plt.close(fig)
    E.append(Image(io.BytesIO(b.getvalue()), width=17 * cm, height=6 * cm))
    E.append(Paragraph("Escenarios (adverso, neutral y optimista)", h2))
    piv = r["escenarios"].pivot(index="escenario", columns="perfil", values="NE").reset_index()
    tabla(piv, None, {c: "${:,.0f}" for c in piv.columns if c != "escenario"})
    fig, ax = plt.subplots(figsize=(7.2, 2.8))
    pv = r["escenarios"].pivot(index="escenario", columns="perfil", values="NE")
    pv.plot(kind="bar", ax=ax, color=["#C0392B", "#14B8C4", "#0B1F3A", "#E8833A"][:pv.shape[1]])
    ax.tick_params(axis="x", rotation=0, labelsize=6); ax.legend(fontsize=7); ax.grid(alpha=.3); ax.set_xlabel("")
    b = io.BytesIO(); fig.savefig(b, format="png", dpi=140, bbox_inches="tight"); plt.close(fig)
    E.append(Image(io.BytesIO(b.getvalue()), width=17 * cm, height=6.4 * cm))
    E.append(PageBreak())
    E.append(Paragraph("Ficha de condiciones", h2))
    fi = r["ficha"].set_index("perfil").loc[recomendado]
    for k in ["renta fija", "pago al vencimiento", "protección del capital", "KRF necesario para 100%", "participación en alzas de la canasta",
              "barrera (stop-loss futuros)", "límite de apalancamiento", "peor escenario (NE)"]:
        v = fi[k]
        if isinstance(v, float):
            v = f"{v:.1%}" if k not in ("peor escenario (NE)", "límite de apalancamiento") else (f"${v:,.0f}" if "NE" in k else f"{v:.2f}×")
        etiqueta = {"KRF necesario para 100%": "Renta fija necesaria para proteger 100%"}.get(k, k[0].upper() + k[1:])
        E.append(Paragraph(f"<b>{etiqueta}:</b> {v}", body))
    E.append(Paragraph("La protección proviene sólo de la renta fija mantenida al vencimiento y del riesgo soberano; esta estructura no "
                       "garantiza el capital contractualmente. Las pérdidas de futuros pueden exceder la garantía depositada y el stop-loss "
                       "puede ejecutarse a un precio peor por brechas de mercado.", body))
    E.append(Paragraph("Renta fija", h2))
    E.append(Paragraph(p["renta_fija"][recomendado]["justificación"] if p.get("renta_fija") else "Tasa capturada.", body))
    E.append(Paragraph("Derivados", h2))
    tabla(r["derivados"], ["perfil", "monto futuros", "contratos futuros", "nocional futuros", "apalancamiento (nocional/inversión)", "monto opciones"],
          {"apalancamiento (nocional/inversión)": "{:.2f}×"})
    E.append(Spacer(1, 4))
    tabla(r["opciones"], ["perfil", "estrategia", "contratos", "costo neto por unidad", "break-even"])
    E.append(Paragraph("Riesgos principales", h2))
    for t in ["Mercado: precios de acciones, futuros y opciones pueden moverse en contra; los escenarios son hipótesis, no pronósticos.",
              "Tasas: la renta fija que se vende antes de su vencimiento pierde valor si suben las tasas (duración).",
              "Apalancamiento: el nocional de futuros puede superar la inversión; las garantías pueden requerir aportaciones adicionales.",
              "Liquidez y ejecución: márgenes, primas y stops pueden diferir de los supuestos.",
              "Cambiario: las acciones de EE.UU. se valúan en dólares convertidos a pesos."]:
        E.append(Paragraph("• " + t, body))
    E.append(Paragraph("Fuentes y fechas", h2))
    for f_ in fuentes:
        E.append(Paragraph("• " + f_, small))
    E.append(Paragraph("Herramienta de análisis. No es una recomendación personalizada de inversión ni una oferta de valores.", small))
    doc.build(E)
    return buf.getvalue()
