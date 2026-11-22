"""Componente libre de riesgo: comparador de instrumentos gubernamentales y selección automática.

Instrumentos (características según Banxico, "Mercado de valores gubernamentales", cap. II, y SHCP):
- CETES: cupón cero, valor nominal $10, se compran a descuento; plazos 28, 91, 182 y 364 días.
- BONOS M: tasa fija, valor nominal $100, cupón cada 182 días; plazos 3, 5, 10, 20 y 30 años.
- BONDES F: tasa variable, valor nominal $100, cupón cada 28 días referido a la TIIE de Fondeo; plazos 1 a 5 años.
- UDIBONOS: tasa real fija, valor nominal 100 UDIS, cupón cada 182 días; plazos 3, 10 y 30 años.

Ningún instrumento está "libre de todo riesgo": el riesgo de crédito es soberano (bajo), pero existen riesgo de
mercado (cambio de precio si se vende antes del vencimiento), de inflación, de reinversión y de liquidez.

Rendimiento al horizonte h (días), suponiendo tasas sin cambio (escenario base):
- Instrumento que vence en o antes de h: se reinvierte a la misma tasa (riesgo de reinversión).
- Instrumento que vence después de h: se vende a precio de mercado (riesgo de mercado, medido con la duración).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

# Niveles de riesgo cualitativos (1 bajo · 2 medio · 3 alto) y su justificación
RIESGOS = {
    "CETES": {"crédito": (1, "Gobierno Federal"), "mercado": (1, "Plazo corto, duración baja"),
              "inflación": (2, "Tasa nominal fija: la inflación puede superarla"),
              "reinversión": (3, "Vence pronto: hay que reinvertir a la tasa que haya entonces"), "liquidez": (1, "Muy líquido")},
    "BONOS M": {"crédito": (1, "Gobierno Federal"), "mercado": (3, "Duración larga: su precio cae si suben las tasas"),
                "inflación": (3, "Tasa nominal fija por muchos años"),
                "reinversión": (2, "Los cupones semestrales se reinvierten a tasas futuras"), "liquidez": (1, "Muy líquido")},
    "BONDES F": {"crédito": (1, "Gobierno Federal"), "mercado": (1, "Tasa revisable cada 28 días; sólo la sobretasa mueve el precio"),
                 "inflación": (2, "Sigue a la TIIE de Fondeo, que acompaña a la política monetaria"),
                 "reinversión": (2, "Cupón variable"), "liquidez": (2, "Liquidez media")},
    "UDIBONOS": {"crédito": (1, "Gobierno Federal"), "mercado": (3, "Duración real larga"),
                 "inflación": (1, "Indexado a la UDI: protege contra inflación"),
                 "reinversión": (2, "Cupones semestrales"), "liquidez": (2, "Liquidez media")},
}

FICHAS = {
    "CETES": {"nombre": "Certificados de la Tesorería de la Federación", "valor_nominal": "$10", "pago": "Cupón cero (a descuento)",
              "convención": "Rendimiento simple ACT/360", "justificación": "Base de liquidez y preservación; sin riesgo de precio si se mantiene al vencimiento."},
    "BONOS M": {"nombre": "Bonos de Desarrollo del Gobierno Federal a tasa fija", "valor_nominal": "$100", "pago": "Cupón cada 182 días",
                "convención": "Rendimiento al vencimiento, periodos de 182 días", "justificación": "Fija una tasa alta por más tiempo; útil si se esperan bajas de tasas."},
    "BONDES F": {"nombre": "Bonos de Desarrollo del Gobierno Federal a tasa variable", "valor_nominal": "$100", "pago": "Cupón cada 28 días (TIIE de Fondeo)",
                 "convención": "TIIE de Fondeo compuesta + sobretasa", "justificación": "Protege contra alzas de tasas con poca variación de precio."},
    "UDIBONOS": {"nombre": "Bonos de Desarrollo del Gobierno Federal denominados en UDIS", "valor_nominal": "100 UDIS", "pago": "Cupón cada 182 días (tasa real)",
                 "convención": "Tasa real + inflación (UDI)", "justificación": "Cubre el poder adquisitivo en horizontes largos."},
}

PESOS_PERFIL = {  # rendimiento, riesgo de mercado, reinversión, inflación (ponderaciones del puntaje)
    "CONSERVADOR": (0.30, 0.50, 0.10, 0.10),
    "MODERADO": (0.50, 0.30, 0.10, 0.10),
    "AGRESIVO": (0.70, 0.15, 0.05, 0.10),
}


def pesos_desde_puntaje(s: float) -> tuple:
    """Interpola las ponderaciones según el puntaje de riesgo del perfilador (0 = conservador, 1 = agresivo)."""
    a, b = np.array(PESOS_PERFIL["CONSERVADOR"]), np.array(PESOS_PERFIL["AGRESIVO"])
    return tuple(a + (b - a) * min(max(s, 0), 1))


def precio_cete(r: float, dias: int, vn: float = 10.0) -> float:
    """P = VN / (1 + r·d/360)  (Banxico, anexo de CETES)."""
    return vn / (1 + r * dias / 360)


def flujos_bono(cupon: float, anios: float, vn: float = 100.0, periodo: int = 182):
    n = max(1, int(round(anios * 364 / periodo)))
    c = vn * cupon * periodo / 360
    return [(k * periodo, c + (vn if k == n else 0.0)) for k in range(1, n + 1)]


def precio_y_duracion(flujos, y: float, periodo: int = 182) -> tuple[float, float]:
    """Precio = Σ F_k / (1 + y·periodo/360)^k ; duración modificada en años."""
    f = 1 + y * periodo / 360
    pv = [cf / f ** (i + 1) for i, (_, cf) in enumerate(flujos)]
    P = sum(pv)
    mac = sum((d / 360) * v for (d, _), v in zip(flujos, pv)) / P
    return P, mac / f


def evaluar(tasas: dict, horizonte: int, monto: float, inflacion: float, udi: float | None = None) -> pd.DataFrame:
    """Evalúa todas las alternativas. `tasas`: cetes {28,91,182,364}, bono_m {años: ytm}, bondes_f_sobretasa,
    tiie_fondeo, udibono_real {años: tasa real}. Todas en decimales anuales."""
    filas = []
    h = horizonte
    for d, r in sorted(tasas.get("cetes", {}).items()):
        P = precio_cete(r, d)
        if d <= h:
            ret = (1 + r * d / 360) ** (h / d) - 1
            dur_venta = 0.0
            reinv = 3
        else:
            ret = (1 + r * d / 360) / (1 + r * (d - h) / 360) - 1
            dur_venta = ((d - h) / 360) / (1 + r * (d - h) / 360)
            reinv = 1
        filas.append(_fila("CETES", f"CETES {d} días", d, P, r, ret, dur_venta, reinv, monto, 10.0, "Cada 28 días o al vencimiento"
                           if d <= h else "Venta antes del vencimiento"))
    for anios, y in sorted(tasas.get("bono_m", {}).items()):
        fl = flujos_bono(y, anios)  # bono emitido a la par (cupón = rendimiento) como referencia
        P, dmod = precio_y_duracion(fl, y)
        d = int(anios * 364)
        ret = y * h / 360
        rest = [(dd - h, cf) for dd, cf in fl if dd > h]
        dur_venta = precio_y_duracion(rest, y)[1] if rest else 0.0
        filas.append(_fila("BONOS M", f"BONO M {anios} años", d, P, y, ret, dur_venta, 2 if d > h else 3, monto, 100.0, "Cupón cada 182 días"))
    sob, tf = tasas.get("bondes_f_sobretasa"), tasas.get("tiie_fondeo")
    if sob is not None and tf is not None:
        for anios in (1, 3, 5):
            d = int(anios * 364)
            y = tf + sob
            ret = y * h / 360
            dur_venta = (28 / 360) / (1 + y * 28 / 360)  # el cupón se revisa cada 28 días: la tasa base casi no mueve el precio
            filas.append(_fila("BONDES F", f"BONDES F {anios} años", d, 100.0, y, ret, dur_venta, 2, monto, 100.0,
                               "Cupón cada 28 días (TIIE de Fondeo + sobretasa)", sens_extra=f"Sensibilidad a la sobretasa ≈ {max(d-h,0)/360:.1f} años"))
    for anios, rr in sorted(tasas.get("udibono_real", {}).items()):
        d = int(anios * 364)
        fl = flujos_bono(rr, anios)
        P_udis, dmod = precio_y_duracion(fl, rr)
        rest = [(dd - h, cf) for dd, cf in fl if dd > h]
        dur_venta = precio_y_duracion(rest, rr)[1] if rest else 0.0
        nominal = (1 + rr) * (1 + inflacion) - 1
        ret = nominal * h / 360
        P = P_udis * (udi or 1.0)
        filas.append(_fila("UDIBONOS", f"UDIBONO {anios} años", d, P, nominal, ret, dur_venta, 2, monto, 100.0 * (udi or 1.0),
                           "Cupón cada 182 días (tasa real)", tasa_real=rr))
    return pd.DataFrame(filas)


def _fila(tipo, nombre, dias, precio, tasa, ret_h, dur_venta, reinv, monto, vn, pagos, sens_extra="", tasa_real=None):
    titulos = int(monto // precio) if precio > 0 else 0
    rk = RIESGOS[tipo]
    return {"tipo": tipo, "instrumento": nombre, "plazo_días": dias, "precio_título": precio, "valor_nominal": vn,
            "tasa_anual": tasa, "tasa_real": tasa_real, "rend_horizonte": ret_h,
            "duración_al_vender": dur_venta, "pérdida_+100pb": -dur_venta * 0.01,
            "riesgo_crédito": rk["crédito"][0], "riesgo_mercado": rk["mercado"][0] if dur_venta > 0.05 else 1,
            "riesgo_inflación": rk["inflación"][0], "riesgo_reinversión": reinv, "riesgo_liquidez": rk["liquidez"][0],
            "pagos": pagos, "títulos": titulos, "monto_invertido": titulos * precio, "sobrante": monto - titulos * precio,
            "nota": sens_extra}


def seleccionar(tabla: pd.DataFrame, horizonte: int, perfil: str, puntaje: float | None = None) -> tuple[pd.DataFrame, dict]:
    """Algoritmo de selección (reglas explícitas):
    1. Elegibilidad por perfil: CONSERVADOR sólo instrumentos que venzan dentro del horizonte (+30 días) o de tasa variable;
       MODERADO hasta 3× el horizonte o tasa variable; AGRESIVO todos.
    2. Puntaje = w_r·z(rendimiento) − w_m·z(pérdida ante +100 pb) − w_reinv·(riesgo de reinversión/3) − w_inf·(riesgo de inflación/3),
       con ponderaciones del perfil (o interpoladas con el puntaje del perfilador). z = normalización mín-máx.
    3. Se elige el puntaje más alto.
    """
    t = tabla.copy()
    if perfil == "CONSERVADOR":
        ok = (t["plazo_días"] <= horizonte + 30) | (t["tipo"] == "BONDES F")
    elif perfil == "MODERADO":
        ok = (t["plazo_días"] <= 3 * horizonte) | (t["tipo"] == "BONDES F")
    elif perfil == "PERSONALIZADO" and puntaje is not None:
        lim = horizonte * (1 + 9 * puntaje)  # de 1× a 10× el horizonte
        ok = (t["plazo_días"] <= lim + 30) | (t["tipo"] == "BONDES F")
    else:
        ok = pd.Series(True, index=t.index)
    t["elegible"] = ok
    w = pesos_desde_puntaje(puntaje) if perfil == "PERSONALIZADO" and puntaje is not None else PESOS_PERFIL.get(perfil, PESOS_PERFIL["MODERADO"])
    e = t[t.elegible]
    if e.empty:
        e = t
        t["elegible"] = True
    nz = lambda s: (s - s.min()) / (s.max() - s.min()) if s.max() > s.min() else s * 0
    t["puntaje"] = np.nan
    t.loc[e.index, "puntaje"] = (w[0] * nz(e["rend_horizonte"]) - w[1] * nz(e["duración_al_vender"])
                                 - w[2] * e["riesgo_reinversión"] / 3 - w[3] * e["riesgo_inflación"] / 3)
    i = t["puntaje"].idxmax()
    t["seleccionado"] = t.index == i
    s = t.loc[i]
    just = (f"Para un perfil {perfil.lower()} y un horizonte de {horizonte} días se elige {s['instrumento']}: rendimiento esperado al "
            f"horizonte de {s['rend_horizonte']*100:.2f}% con tasas sin cambio, pérdida aproximada de {abs(s['pérdida_+100pb'])*100:.2f}% "
            f"si las tasas suben 100 pb antes de venderlo, riesgo de reinversión {['','bajo','medio','alto'][int(s['riesgo_reinversión'])]} "
            f"y de inflación {['','bajo','medio','alto'][int(s['riesgo_inflación'])]}. Ponderaciones del puntaje: rendimiento {w[0]:.2f}, "
            f"riesgo de mercado {w[1]:.2f}, reinversión {w[2]:.2f}, inflación {w[3]:.2f}.")
    return t, {"instrumento": s["instrumento"], "tipo": s["tipo"], "rend_horizonte": float(s["rend_horizonte"]),
               "tasa_anual": float(s["tasa_anual"]), "precio_título": float(s["precio_título"]), "duración": float(s["duración_al_vender"]),
               "justificación": just, "pesos": w}


def valor_escenario(sel: dict, monto: float, choque_bp: float) -> float:
    """Valor de la renta fija al horizonte ante un cambio paralelo de tasas (aprox. por duración)."""
    return monto * (1 + sel["rend_horizonte"] - sel["duración"] * choque_bp / 10000)
