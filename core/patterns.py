"""Detección algorítmica de figuras chartistas.

Todas las reglas se basan en pivotes (ver technical.pivotes). Las figuras son descriptivas:
no generan órdenes ni implican rentabilidad. Cada detección informa puntos, fechas,
estado (En formación / Confirmada / Invalidada) y el criterio aplicado.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .technical import pivotes


def _estado_bajista(close_desp: pd.Series, cuello: float, invalida: float):
    """Figura bajista: se confirma con cierre < cuello; se invalida con cierre > nivel de invalidación."""
    for f, c in close_desp.items():
        if c > invalida:
            return "Invalidada", f
        if c < cuello:
            return "Confirmada", f
    return "En formación", None


def _estado_alcista(close_desp: pd.Series, cuello: float, invalida: float):
    for f, c in close_desp.items():
        if c < invalida:
            return "Invalidada", f
        if c > cuello:
            return "Confirmada", f
    return "En formación", None


def dobles(df: pd.DataFrame, ventana=5, tolerancia=0.03, profundidad=0.03) -> list[dict]:
    """Doble techo: dos pivotes altos consecutivos con diferencia ≤ tolerancia y un valle intermedio
    al menos `profundidad` por debajo del menor de ellos. Cuello = valle. Doble suelo: simétrico."""
    pv = pivotes(df["High"], df["Low"], ventana)
    out = []
    for i in range(len(pv) - 2):
        a, m, b = pv.iloc[i], pv.iloc[i + 1], pv.iloc[i + 2]
        if a["tipo"] == "alto" and m["tipo"] == "bajo" and b["tipo"] == "alto":
            if abs(a["precio"] - b["precio"]) / max(a["precio"], b["precio"]) <= tolerancia and \
               m["precio"] <= min(a["precio"], b["precio"]) * (1 - profundidad):
                post = df["Close"][df.index > b["fecha"]]
                est, f = _estado_bajista(post, m["precio"], max(a["precio"], b["precio"]) * (1 + tolerancia))
                out.append({"figura": "Doble techo", "sesgo": "Bajista", "inicio": a["fecha"], "fin": b["fecha"],
                            "puntos": [(a["fecha"], a["precio"]), (m["fecha"], m["precio"]), (b["fecha"], b["precio"])],
                            "cuello": m["precio"], "estado": est, "fecha_estado": f,
                            "criterio": f"Picos dentro de ±{tolerancia:.0%}, valle ≥{profundidad:.0%} bajo los picos; "
                                        f"confirma cierre bajo el cuello; invalida cierre sobre el pico +{tolerancia:.0%}"})
        if a["tipo"] == "bajo" and m["tipo"] == "alto" and b["tipo"] == "bajo":
            if abs(a["precio"] - b["precio"]) / max(a["precio"], b["precio"]) <= tolerancia and \
               m["precio"] >= max(a["precio"], b["precio"]) * (1 + profundidad):
                post = df["Close"][df.index > b["fecha"]]
                est, f = _estado_alcista(post, m["precio"], min(a["precio"], b["precio"]) * (1 - tolerancia))
                out.append({"figura": "Doble suelo", "sesgo": "Alcista", "inicio": a["fecha"], "fin": b["fecha"],
                            "puntos": [(a["fecha"], a["precio"]), (m["fecha"], m["precio"]), (b["fecha"], b["precio"])],
                            "cuello": m["precio"], "estado": est, "fecha_estado": f,
                            "criterio": f"Valles dentro de ±{tolerancia:.0%}, pico intermedio ≥{profundidad:.0%} "
                                        f"sobre los valles; confirma cierre sobre el cuello"})
    return out


def hch(df: pd.DataFrame, ventana=5, tolerancia_hombros=0.04, realce_cabeza=0.02) -> list[dict]:
    """Hombro-cabeza-hombro: secuencia alto-bajo-alto-bajo-alto donde el alto central excede a ambos
    hombros por ≥ realce_cabeza y los hombros difieren ≤ tolerancia. Cuello = recta entre los dos valles,
    evaluada en cada fecha posterior. HCH invertido: simétrico con bajos."""
    pv = pivotes(df["High"], df["Low"], ventana)
    out = []
    pos = {f: i for i, f in enumerate(df.index)}
    for i in range(len(pv) - 4):
        s = pv.iloc[i:i + 5]
        tipos = list(s["tipo"])
        p = list(s["precio"])
        f = list(s["fecha"])
        for inv in (False, True):
            patron = ["bajo", "alto", "bajo", "alto", "bajo"] if inv else ["alto", "bajo", "alto", "bajo", "alto"]
            if tipos != patron:
                continue
            h1, v1, cab, v2, h2 = p
            if not inv:
                ok = cab >= max(h1, h2) * (1 + realce_cabeza) and abs(h1 - h2) / max(h1, h2) <= tolerancia_hombros
            else:
                ok = cab <= min(h1, h2) * (1 - realce_cabeza) and abs(h1 - h2) / max(h1, h2) <= tolerancia_hombros
            if not ok:
                continue
            x1, x2 = pos[f[1]], pos[f[3]]
            pend = (v2 - v1) / (x2 - x1) if x2 != x1 else 0.0
            post = df["Close"][df.index > f[4]]
            est, fe = "En formación", None
            for fecha, c in post.items():
                cuello = v1 + pend * (pos[fecha] - x1)
                if (not inv and c > cab) or (inv and c < cab):
                    est, fe = "Invalidada", fecha
                    break
                if (not inv and c < cuello) or (inv and c > cuello):
                    est, fe = "Confirmada", fecha
                    break
            out.append({"figura": "Hombro-cabeza-hombro invertido" if inv else "Hombro-cabeza-hombro",
                        "sesgo": "Alcista" if inv else "Bajista", "inicio": f[0], "fin": f[4],
                        "puntos": list(zip(f, p)), "cuello": v1 + pend * (pos[f[4]] - x1), "estado": est,
                        "fecha_estado": fe,
                        "criterio": f"Cabeza ≥{realce_cabeza:.0%} más extrema que hombros; hombros ±{tolerancia_hombros:.0%}; "
                                    "confirma cierre que cruza la línea de cuello; invalida cierre más allá de la cabeza"})
    return out


def _ajuste(xs, ys):
    if len(xs) < 2:
        return None
    b = np.polyfit(xs, ys, 1)
    return b[0], b[1]


def geometricas(df: pd.DataFrame, ventana=5, n_pivotes=3, umbral_plano=0.0005) -> dict | None:
    """Clasifica la estructura reciente con rectas ajustadas (MCO) sobre los últimos n pivotes altos y bajos.

    Pendientes normalizadas por el precio (cambio relativo por barra):
    - Canal: ambas pendientes con el mismo signo y diferencia relativa < 30 %.
    - Triángulo simétrico: altos descendentes y bajos ascendentes.
    - Triángulo ascendente: altos planos (|m| < umbral) y bajos ascendentes. Descendente: simétrico.
    - Cuña ascendente/descendente: ambas con el mismo signo y convergentes.
    """
    pv = pivotes(df["High"], df["Low"], ventana)
    pos = {f: i for i, f in enumerate(df.index)}
    alt = pv[pv["tipo"] == "alto"].tail(n_pivotes)
    baj = pv[pv["tipo"] == "bajo"].tail(n_pivotes)
    if len(alt) < 2 or len(baj) < 2:
        return None
    fa = _ajuste([pos[f] for f in alt["fecha"]], list(alt["precio"]))
    fb = _ajuste([pos[f] for f in baj["fecha"]], list(baj["precio"]))
    ref = float(df["Close"].iloc[-1])
    ma, mb = fa[0] / ref, fb[0] / ref
    plano_a, plano_b = abs(ma) < umbral_plano, abs(mb) < umbral_plano
    if plano_a and mb > umbral_plano:
        fig = "Triángulo ascendente"
    elif plano_b and ma < -umbral_plano:
        fig = "Triángulo descendente"
    elif ma < -umbral_plano and mb > umbral_plano:
        fig = "Triángulo simétrico"
    elif np.sign(ma) == np.sign(mb) and not (plano_a and plano_b):
        if abs(ma - mb) / max(abs(ma), abs(mb)) < 0.3:
            fig = "Canal alcista" if ma > 0 else "Canal bajista"
        elif (ma > 0 and mb > ma) or (ma < 0 and mb > ma):
            fig = "Cuña ascendente" if ma > 0 else "Cuña descendente"
        else:
            fig = "Estructura divergente (ensanchamiento)"
    elif plano_a and plano_b:
        fig = "Canal lateral (rango)"
    else:
        fig = "Estructura divergente (ensanchamiento)"
    x0 = min(pos[alt["fecha"].iloc[0]], pos[baj["fecha"].iloc[0]])
    x1 = len(df) - 1
    linea = lambda f, x: f[0] * x + f[1]
    sup = linea(fa, x1)
    inf = linea(fb, x1)
    c = df["Close"].iloc[-1]
    est = "Ruptura al alza" if c > sup else ("Ruptura a la baja" if c < inf else "Dentro de la figura")
    return {"figura": fig, "inicio": df.index[x0], "fin": df.index[x1],
            "linea_superior": [(df.index[x0], linea(fa, x0)), (df.index[x1], sup)],
            "linea_inferior": [(df.index[x0], linea(fb, x0)), (df.index[x1], inf)],
            "pend_sup_%barra": ma * 100, "pend_inf_%barra": mb * 100, "estado": est,
            "criterio": f"Rectas MCO sobre los últimos {n_pivotes} pivotes altos y bajos (ventana {ventana}); "
                        f"umbral de pendiente plana {umbral_plano*100:.3f}% por barra"}


def banderas(df: pd.DataFrame, mastil_barras=10, mastil_min=0.08, consolidacion=(5, 20)) -> list[dict]:
    """Bandera/banderín: movimiento previo (mástil) ≥ mastil_min en ≤ mastil_barras barras, seguido de
    una consolidación de 5–20 barras con rango < 50 % del mástil. Bandera = consolidación con canal en
    contra de la tendencia (pendientes paralelas); banderín = rectas convergentes."""
    c = df["Close"]
    out = []
    lo, hi = consolidacion
    n = len(df)
    for L in range(lo, hi + 1):
        fin_mastil = n - 1 - L
        ini = fin_mastil - mastil_barras
        if ini < 0:
            continue
        mov = c.iloc[fin_mastil] / c.iloc[ini] - 1
        if abs(mov) < mastil_min:
            continue
        seg = df.iloc[fin_mastil:]
        rango = seg["High"].max() - seg["Low"].min()
        if rango >= 0.5 * abs(c.iloc[fin_mastil] - c.iloc[ini]):
            continue
        x = np.arange(len(seg))
        ma = np.polyfit(x, seg["High"].values, 1)[0] / c.iloc[-1]
        mb = np.polyfit(x, seg["Low"].values, 1)[0] / c.iloc[-1]
        conv = (ma < 0 < mb)
        tipo = "Banderín" if conv else "Bandera"
        sesgo = "Alcista" if mov > 0 else "Bajista"
        if tipo == "Bandera" and np.sign(ma) == np.sign(mov) and abs(ma) > 0.0005:
            continue  # una bandera debe inclinarse en contra (o lateral) del mástil
        borde = seg["High"].max() if mov > 0 else seg["Low"].min()
        est = "Confirmada" if (mov > 0 and c.iloc[-1] >= borde) or (mov < 0 and c.iloc[-1] <= borde) else "En formación"
        out.append({"figura": f"{tipo} {sesgo.lower()}", "sesgo": sesgo, "inicio": df.index[ini], "fin": df.index[-1],
                    "mastil_%": mov * 100, "barras_consolidación": L, "estado": est,
                    "criterio": f"Mástil ≥{mastil_min:.0%} en {mastil_barras} barras; consolidación {L} barras con rango "
                                "< 50% del mástil"})
        break
    return out


def soportes_resistencias(df: pd.DataFrame, ventana=5, tolerancia=0.015, toques_min=2) -> pd.DataFrame:
    """Agrupa niveles de pivotes que distan ≤ tolerancia entre sí; un nivel con ≥ toques_min toques es zona.
    Soporte si está por debajo del último cierre; resistencia si está por encima."""
    pv = pivotes(df["High"], df["Low"], ventana).sort_values("precio")
    grupos = []
    for _, r in pv.iterrows():
        if grupos and abs(r["precio"] - np.mean(grupos[-1]["precios"])) / r["precio"] <= tolerancia:
            grupos[-1]["precios"].append(r["precio"])
            grupos[-1]["fechas"].append(r["fecha"])
        else:
            grupos.append({"precios": [r["precio"]], "fechas": [r["fecha"]]})
    c = df["Close"].iloc[-1]
    filas = []
    for g in grupos:
        if len(g["precios"]) >= toques_min:
            nivel = float(np.mean(g["precios"]))
            filas.append({"nivel": nivel, "tipo": "Soporte" if nivel < c else "Resistencia", "toques": len(g["precios"]),
                          "primer_toque": min(g["fechas"]), "último_toque": max(g["fechas"]),
                          "distancia_%": (nivel / c - 1) * 100})
    return pd.DataFrame(filas)
