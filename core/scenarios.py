"""Motor central de escenarios: perfiles × estrategias × escenarios (mínimo 5 por combinación).

Reglas:
- Dentro de un perfil, el MISMO conjunto de choques de mercado se aplica a todas las estrategias comparadas.
- 'Adverso' y 'favorable' se definen respecto de la exposición: para una posición larga en acciones un
  descenso es adverso; para un pasivo a tasa variable un alza de tasas es adversa.
- Los choques son hipótesis de simulación (múltiplos de la volatilidad histórica o puntos base), no
  predicciones ni probabilidades.
"""
from __future__ import annotations

import copy
import math

import numpy as np
import pandas as pd

from . import strategies as stg
from . import rates as rt

ESCENARIOS = ["1. Estrés adverso severo", "2. Adverso moderado", "3. Base / estabilidad",
              "4. Favorable moderado", "5. Favorable extremo"]

PERFILES_ACCIONES = {
    "Conservador": {"descripcion": "Prioriza reducir pérdidas; acepta costos y límites a la ganancia.",
                    "k_put": 0.95, "k_call": 1.05, "cobertura_futuros": 1.00,
                    "z": [-2.5, -1.0, 0.0, 1.0, 2.5], "vol_pts": [10.0, 3.0, 0.0, -2.0, 0.0]},
    "Equilibrado": {"descripcion": "Balance entre costo, protección y participación al alza.",
                    "k_put": 0.90, "k_call": 1.10, "cobertura_futuros": 0.75,
                    "z": [-2.5, -1.0, 0.0, 1.0, 2.5], "vol_pts": [10.0, 3.0, 0.0, -2.0, 0.0]},
    "Agresivo": {"descripcion": "Tolera más exposición residual; protección sólo ante caídas grandes.",
                 "k_put": 0.85, "k_call": 1.15, "cobertura_futuros": 0.50,
                 "z": [-2.5, -1.0, 0.0, 1.0, 2.5], "vol_pts": [10.0, 3.0, 0.0, -2.0, 0.0]},
}

PERFILES_TASAS = {
    "Conservador": {"descripcion": "Strike del cap/floor cerca del forward promedio (protección amplia).",
                    "offset_strike_bp": 0, "choques_bp": [300, 100, 0, -100, -300], "pendiente_bp": [50, 0, 0, 0, -50]},
    "Equilibrado": {"descripcion": "Strike 100 pb fuera del dinero.",
                    "offset_strike_bp": 100, "choques_bp": [300, 100, 0, -100, -300], "pendiente_bp": [50, 0, 0, 0, -50]},
    "Agresivo": {"descripcion": "Strike 200 pb fuera del dinero; protección sólo ante alzas grandes.",
                 "offset_strike_bp": 200, "choques_bp": [300, 100, 0, -100, -300], "pendiente_bp": [50, 0, 0, 0, -50]},
}


# =================================================================== ACCIONES
def estrategias_compatibles(direccion: str) -> dict[str, str]:
    if direccion == "larga":
        return {"Sin cobertura": "Exposición original", "Protective Put": "Cobertura directa",
                "Collar accionario": "Cobertura directa", "Covered Call": "Ingreso por primas (cobertura parcial)",
                "Venta de futuros": "Cobertura directa (proporción según perfil)",
                "Long Straddle": "Estrategia de volatilidad (no es cobertura)"}
    return {"Sin cobertura": "Exposición original", "Compra de call": "Cobertura directa",
            "Venta de put": "Ingreso por primas (cobertura parcial)",
            "Compra de futuros": "Cobertura directa (proporción según perfil)",
            "Long Straddle": "Estrategia de volatilidad (no es cobertura)"}


def legs_cobertura(nombre, direccion, acciones, S0, T, r, q, sigma, perfil, mult_opc, mult_fut, primas_obs=None):
    contratos = max(1, round(acciones / mult_opc))
    cf = max(1, round(acciones * perfil["cobertura_futuros"] / mult_fut))
    prem = lambda K, t: (primas_obs or {}).get((t, round(K, 4)), None) or stg.bsm(S0, K, T, r, q, sigma, t)
    o = lambda t, K, c: stg.Leg(t, c, mult_opc, K, T, prem(K, t))
    F0 = stg.precio_teorico(S0, r, q, T)
    kp, kc = S0 * perfil["k_put"], S0 * perfil["k_call"]
    if direccion == "larga":
        m = {"Sin cobertura": [], "Protective Put": [o("put", kp, contratos)],
             "Collar accionario": [o("put", kp, contratos), o("call", kc, -contratos)],
             "Covered Call": [o("call", kc, -contratos)],
             "Venta de futuros": [stg.Leg("futuro", -cf, mult_fut, vencimiento_años=T, precio_inicial=F0)],
             "Long Straddle": [o("call", S0, contratos), o("put", S0, contratos)]}
    else:
        kc_s, kp_s = S0 * (2 - perfil["k_put"]), S0 * (2 - perfil["k_call"])
        m = {"Sin cobertura": [], "Compra de call": [o("call", kc_s, contratos)],
             "Venta de put": [o("put", kp_s, -contratos)],
             "Compra de futuros": [stg.Leg("futuro", cf, mult_fut, vencimiento_años=T, precio_inicial=F0)],
             "Long Straddle": [o("call", S0, contratos), o("put", S0, contratos)]}
    return m[nombre]


def matriz_acciones(S0, acciones, direccion, horizonte_años, venc_años, r, q, sigma, perfiles=None,
                    estrategias=None, mult_opc=100, mult_fut=100, primas_obs=None) -> pd.DataFrame:
    """Evalúa perfiles × estrategias × 5 escenarios. S_h = S0·exp(s·z·σ·√h), s=+1 larga / −1 corta (para que
    z<0 sea siempre adverso). σ del escenario = σ + choque de volatilidad (pts)."""
    perfiles = perfiles or PERFILES_ACCIONES
    compat = estrategias_compatibles(direccion)
    estrategias = estrategias or list(compat)
    s = 1 if direccion == "larga" else -1
    expo = stg.Leg("accion", s * acciones, 1, precio_inicial=S0)
    filas = []
    for pn, pf in perfiles.items():
        if len(pf["z"]) < 5:
            raise ValueError("Cada perfil requiere al menos cinco escenarios.")
        for en in estrategias:
            hl = legs_cobertura(en, direccion, acciones, S0, venc_años, r, q, sigma, pf, mult_opc, mult_fut, primas_obs)
            costo = stg.costo_inicial(hl)
            base_comb = None
            res_esc = []
            for k, (z, dv) in enumerate(zip(pf["z"], pf["vol_pts"])):
                Sh = S0 * math.exp(s * z * sigma * math.sqrt(horizonte_años))
                sig_h = max(sigma + dv / 100, 0.01)
                p_expo = stg.pnl_estrategia([expo], S0, Sh, horizonte_años, r, q, sig_h)
                p_der = stg.pnl_estrategia(hl, S0, Sh, horizonte_años, r, q, sig_h) if hl else 0.0
                comb = p_expo + p_der
                res_esc.append((k, z, dv, Sh, sig_h, p_expo, p_der, comb))
                if k == 2:
                    base_comb = comb
            for k, z, dv, Sh, sig_h, p_expo, p_der, comb in res_esc:
                nombre_esc = ESCENARIOS[k] if k < 5 else f"Escenario {k+1}"
                filas.append({
                    "perfil": pn, "estrategia": en, "función_económica": compat.get(en, ""), "escenario": nombre_esc,
                    "choque_z_σ": z, "choque_vol_pts": dv, "precio_inicial": S0, "precio_final": Sh,
                    "cambio_%": (Sh / S0 - 1) * 100, "vol_escenario_%": sig_h * 100,
                    "exposición_valor_inicial": s * acciones * S0,
                    "resultado_sin_cobertura": p_expo, "resultado_derivado": p_der, "resultado_combinado": comb,
                    "costo_cobertura_inicial": costo,
                    "protección_conseguida": comb - p_expo,
                    "exposición_remanente_%": (comb / p_expo * 100) if p_expo < 0 else np.nan,
                    "variación_vs_base": comb - base_comb,
                    "riesgos_no_cubiertos": _riesgos(en, direccion),
                    "estado": "Simulación teórica (primas BSM salvo que se indiquen observadas)",
                })
    return pd.DataFrame(filas)


def _riesgos(estr, direccion):
    base = "Riesgo de base, liquidez del contrato, ejecución y contraparte. "
    return base + {
        "Sin cobertura": "Exposición total al precio.",
        "Protective Put": "Pérdida hasta el strike más la prima; costo de la prima.",
        "Collar accionario": "Pérdida hasta el strike de la put; ganancia limitada al strike de la call.",
        "Covered Call": "Protección limitada a la prima recibida; pérdidas grandes no se cubren.",
        "Venta de futuros": "Riesgo residual por proporción no cubierta, ajustes diarios y garantías.",
        "Compra de futuros": "Riesgo residual por proporción no cubierta, ajustes diarios y garantías.",
        "Long Straddle": "No es cobertura: pierde la prima si el precio no se mueve; depende de la volatilidad.",
        "Compra de call": "Pérdida hasta el strike más la prima.",
        "Venta de put": "Protección limitada a la prima; obligación de compra.",
    }.get(estr, "")


def resumen_comparativo(m: pd.DataFrame) -> pd.DataFrame:
    """Matriz comparativa por perfil y estrategia (criterios cuantitativos explícitos, sin puntuaciones opacas)."""
    g = m.groupby(["perfil", "estrategia", "función_económica"])
    out = g.agg(costo_inicial=("costo_cobertura_inicial", "first"),
                peor_resultado=("resultado_combinado", "min"),
                mejor_resultado=("resultado_combinado", "max"),
                resultado_base=("resultado_combinado", lambda x: x.iloc[2]),
                protección_en_estrés=("protección_conseguida", lambda x: x.iloc[0])).reset_index()
    out["rango_resultados"] = out["mejor_resultado"] - out["peor_resultado"]
    return out


# =================================================================== TASAS
def estrategias_tasas(posicion):
    if posicion == "pasivo":
        return {"Sin cobertura": "Exposición original", "Cap comprado": "Cobertura directa",
                "Cap comprado 50%": "Cobertura parcial",
                "Collar de tasas (cap comprado + floor vendido)": "Cobertura directa con costo reducido"}
    return {"Sin cobertura": "Exposición original", "Floor comprado": "Cobertura directa",
            "Floor comprado 50%": "Cobertura parcial",
            "Collar de tasas (floor comprado + cap vendido)": "Cobertura directa con costo reducido"}


def matriz_tasas(curva, fecha_val, periodos, nocionales, posicion, spread, sigma, modelo, fijacion, base="ACT/360",
                 perfiles=None, ancho_collar_bp=200) -> tuple[pd.DataFrame, dict]:
    """Para cada perfil: strike = forward promedio ± offset. Prima = VP teórico con la curva base.
    Resultado del escenario = VP (con DF base) de los flujos netos, menos/más primas pagadas/recibidas.
    Choque por período = choque paralelo + pendiente·(t/t_max). Para un activo, los signos del choque se invierten
    para que el escenario 1 siempre sea adverso para la exposición."""
    perfiles = perfiles or PERFILES_TASAS
    tabla0 = rt.valuar_cap_floor(curva, fecha_val, periodos, nocionales, 0.05, 0.2 if modelo == "Black-76" else 0.01,
                                 modelo, "cap", base, fijacion)
    fwd_prom = float(np.average(tabla0["forward_%"], weights=tabla0["nocional"] * tabla0["alfa"])) / 100
    t_fin = (tabla0["fin"].apply(lambda d: (pd.Timestamp(d) - pd.Timestamp(fecha_val)).days / 365)).values
    tmax = t_fin.max()
    sgn = 1 if posicion == "pasivo" else -1
    compat = estrategias_tasas(posicion)
    filas, primas = [], {}
    for pn, pf in perfiles.items():
        off = pf["offset_strike_bp"] / 10000
        if posicion == "pasivo":
            Kc = fwd_prom + off
            Kf = Kc - ancho_collar_bp / 10000
            defs = {"Sin cobertura": [],
                    "Cap comprado": [{"tipo": "cap", "K": Kc, "signo": 1, "proporcion": 1.0}],
                    "Cap comprado 50%": [{"tipo": "cap", "K": Kc, "signo": 1, "proporcion": 0.5}],
                    "Collar de tasas (cap comprado + floor vendido)": [{"tipo": "cap", "K": Kc, "signo": 1, "proporcion": 1.0},
                                                                       {"tipo": "floor", "K": Kf, "signo": -1, "proporcion": 1.0}]}
        else:
            Kf = max(fwd_prom - off, 0.0001)
            Kc = Kf + ancho_collar_bp / 10000
            defs = {"Sin cobertura": [],
                    "Floor comprado": [{"tipo": "floor", "K": Kf, "signo": 1, "proporcion": 1.0}],
                    "Floor comprado 50%": [{"tipo": "floor", "K": Kf, "signo": 1, "proporcion": 0.5}],
                    "Collar de tasas (floor comprado + cap vendido)": [{"tipo": "floor", "K": Kf, "signo": 1, "proporcion": 1.0},
                                                                       {"tipo": "cap", "K": Kc, "signo": -1, "proporcion": 1.0}]}
        for en, cobs in defs.items():
            prima = 0.0
            for c in cobs:
                v = rt.valuar_cap_floor(curva, fecha_val, periodos, nocionales, c["K"], sigma, modelo, c["tipo"], base,
                                        fijacion)["valor_presente"].sum()
                prima += c["signo"] * c["proporcion"] * v
            primas[(pn, en)] = {"prima_neta_pagada": prima, "strikes": [(c["tipo"], c["K"] * 100) for c in cobs]}
            base_res = None
            tmp = []
            for k in range(len(pf["choques_bp"])):
                choque = sgn * (pf["choques_bp"][k] + pf["pendiente_bp"][k] * t_fin / tmax)
                fl = rt.flujos_exposicion(tabla0, choque, spread, posicion, cobs)
                vp_expo = float((fl["flujo_exposicion"] * fl["DF_pago"]).sum())
                vp_cob = float((fl["flujo_coberturas"] * fl["DF_pago"]).sum())
                nominal_cob = float(fl["flujo_coberturas"].sum())
                comb = vp_expo + vp_cob - prima
                tmp.append((k, choque, fl, vp_expo, vp_cob, nominal_cob, comb))
                if k == 2:
                    base_res = comb
            for k, choque, fl, vp_expo, vp_cob, nominal_cob, comb in tmp:
                filas.append({"perfil": pn, "estrategia": en, "función_económica": compat[en],
                              "escenario": ESCENARIOS[k] if k < 5 else f"Escenario {k+1}",
                              "choque_paralelo_bp": sgn * pf["choques_bp"][k], "pendiente_bp": sgn * pf["pendiente_bp"][k],
                              "tasa_promedio_realizada_%": float(fl["tasa_realizada_%"].mean()),
                              "strikes_%": ", ".join(f"{t} {k_:.2f}%" for t, k_ in primas[(pn, en)]["strikes"]) or "—",
                              "VP_flujos_exposición": vp_expo, "VP_pagos_derivado": vp_cob,
                              "pagos_derivado_nominales": nominal_cob, "prima_neta_pagada": prima,
                              "resultado_combinado_VP": comb, "costo_cobertura": prima,
                              "protección_conseguida": vp_cob - prima,
                              "variación_vs_base": comb - base_res,
                              "estado": "Valuación teórica (curva y volatilidad indicadas por el usuario)"})
    return pd.DataFrame(filas), {"forward_promedio_%": fwd_prom * 100, "primas": primas}
