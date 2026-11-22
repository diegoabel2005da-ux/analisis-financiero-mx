"""Nota estructurada por perfil (AGRESIVO, MODERADO, CONSERVADOR), basada en el modelo del usuario.

Estructura:
1. Renta fija libre de riesgo (KRF): %KRF × inversión, rendimiento simple a la tasa de Cetes con base ACT/360:
   KRF al vencimiento = KRF × (1 + r·días/360).
2. Porción de riesgo = inversión − KRF, dividida en mercado de capitales y derivados según el perfil.
3. Capitales: canasta de acciones con β (vs. S&P/BMV IPC) y rendimiento esperado al horizonte
   (CAPM: (rf + β·PRM)·días/365, o captura manual). Monto por acción = peso × monto de capitales.
4. Derivados: monto para futuros (se usa como garantía AIM) y para opciones (primas).
   - Futuros (largos): contratos = ENTERO(monto futuros / AIM por contrato); resultado = n·M·(S_h − F0).
     La AIM es un depósito recuperable, no un costo.
   - Opciones: estrategia por perfil (STG, BTF, FLOOR, CALL, COLLAR) con primas teóricas BSM al horizonte;
     contratos = ENTERO(monto opciones / (M · primas pagadas)); resultado al vencimiento = n·M·Σ pos·(payoff − prima).
5. Escenarios (5, iguales a los de la plataforma): para un choque z,
   subyacente S_h = S0·exp(μ + z·σ·√(días/365)) con μ = rendimiento CAPM del subyacente;
   acción i: r_i = rend_i + β_i·z·σ_IPC·√(días/365). z = 0 es el escenario base (estimación).
   Son hipótesis de simulación, sin probabilidades asignadas.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .options import bsm

PERFILES = ["AGRESIVO", "MODERADO", "CONSERVADOR"]
ESCENARIOS_Z = [("1. Estrés adverso severo", -2.5), ("2. Adverso moderado", -1.0), ("3. Base / estabilidad", 0.0),
                ("4. Favorable moderado", 1.0), ("5. Favorable extremo", 2.5)]
ESTRATEGIAS_NOTA = {
    "STG": "Long strangle (call OTM + put OTM)",
    "BTF": "Long call butterfly",
    "FLOOR": "Floor: put comprada (protección)",
    "CALL": "Call comprada (participación)",
    "COLLAR": "Collar: put comprada + call vendida",
}

# Valores iniciales tomados del archivo NOTA_ESTRUCTURADA del usuario
PARAMS_EJEMPLO = {
    "inversion": 2_000_000.0, "dias": 91, "rf_anual": 0.0669, "prm": 0.06,
    "krf_pct": {"AGRESIVO": 0.20, "MODERADO": 0.50, "CONSERVADOR": 0.70},
    "cap_pct": {"AGRESIVO": 0.20, "MODERADO": 0.50, "CONSERVADOR": 0.80},
    "fut_pct": {"AGRESIVO": 0.60, "MODERADO": 0.50, "CONSERVADOR": 0.40},
    "estrategia": {"AGRESIVO": "STG", "MODERADO": "BTF", "CONSERVADOR": "FLOOR"},
    "acciones": [
        {"nombre": "CEMEX", "simbolo": "CEMEXCPO.MX", "beta": 1.2, "rend_manual": 0.06,
         "pesos": {"CONSERVADOR": 100 / 480, "MODERADO": 100 / 500, "AGRESIVO": 0.0}},
        {"nombre": "BIMBOA", "simbolo": "BIMBOA.MX", "beta": 1.0, "rend_manual": 0.059,
         "pesos": {"CONSERVADOR": 80 / 480, "MODERADO": 50 / 500, "AGRESIVO": 0.0}},
        {"nombre": "PEÑOLES", "simbolo": "PE&OLES.MX", "beta": 0.4, "rend_manual": 0.04,
         "pesos": {"CONSERVADOR": 100 / 480, "MODERADO": 250 / 500, "AGRESIVO": 120 / 320}},
        {"nombre": "WALMEX", "simbolo": "WALMEX.MX", "beta": 0.5, "rend_manual": 0.03,
         "pesos": {"CONSERVADOR": 0.0, "MODERADO": 0.0, "AGRESIVO": 0.0}},
        {"nombre": "NVIDIA", "simbolo": "NVDA.MX", "beta": 0.7, "rend_manual": 0.022,
         "pesos": {"CONSERVADOR": 100 / 480, "MODERADO": 100 / 500, "AGRESIVO": 200 / 320}},
        {"nombre": "APPLE", "simbolo": "AAPL.MX", "beta": 0.9, "rend_manual": 0.03,
         "pesos": {"CONSERVADOR": 100 / 480, "MODERADO": 0.0, "AGRESIVO": 0.0}},
    ],
    "modo_rend": "manual",
}


def legs_estrategia(clave: str, S0: float, T: float, r: float, q: float, sigma: float, ancho: float = 0.05) -> list[dict]:
    """Legs por unidad de subyacente con primas teóricas BSM (vencimiento = horizonte de la nota)."""
    def leg(tipo, K, pos):
        return {"tipo": tipo, "K": K, "pos": pos, "prima": bsm(S0, K, T, r, q, sigma, "call" if tipo == "CALL" else "put")}
    a = ancho * S0
    if clave == "STG":
        return [leg("CALL", S0 + a, 1), leg("PUT", S0 - a, 1)]
    if clave == "BTF":
        return [leg("CALL", S0 - a, 1), leg("CALL", S0, -2), leg("CALL", S0 + a, 1)]
    if clave == "FLOOR":
        return [leg("PUT", S0 * 0.95, 1)]
    if clave == "CALL":
        return [leg("CALL", S0, 1)]
    if clave == "COLLAR":
        return [leg("PUT", S0 * 0.95, 1), leg("CALL", S0 * 1.05, -1)]
    raise ValueError(clave)


def rend_capm(rf: float, beta: float, prm: float, dias: int) -> float:
    return (rf + beta * prm) * dias / 365


def calcular(p: dict) -> dict:
    inv, dias, rf, prm = p["inversion"], p["dias"], p["rf_anual"], p["prm"]
    hy = dias / 365
    d = p["derivados"]
    S0, sig, sig_ipc = d["S0"], d["sigma"], p["sigma_ipc"]
    M_f, M_o = d["mult_fut"], d["mult_opc"]
    F0 = S0 * math.exp((d["r_cont"] - d["q"]) * hy)
    aim = d["aim_contrato"] if d.get("aim_contrato") else d["aim_pct"] * F0 * M_f
    mu_S = rend_capm(rf, d["beta"], prm, dias)
    acciones = p["acciones"]
    for a in acciones:
        a["rend"] = a["rend_manual"] if p.get("modo_rend") == "manual" else rend_capm(rf, a["beta"], prm, dias)

    res, div, der, fut, opc = [], [], [], [], []
    cap_tab = pd.DataFrame({"acción": [a["nombre"] for a in acciones], "beta": [a["beta"] for a in acciones],
                            "rendimiento": [a["rend"] for a in acciones]})
    esc = []
    for pf in PERFILES:
        krf = p["krf_pct"][pf] * inv
        krf_prof = krf * (1 + rf * dias / 360)
        ut_krf = krf_prof - krf
        riesgo = inv - krf
        cap = riesgo * p["cap_pct"][pf]
        dv = riesgo - cap
        montos = np.array([a["pesos"][pf] * cap for a in acciones])
        cap_tab[pf] = montos
        rends = np.array([a["rend"] for a in acciones])
        betas = np.array([a["beta"] for a in acciones])
        ut_cap = float((montos * rends).sum())
        m_fut = dv * p["fut_pct"][pf]
        m_opc = dv - m_fut
        n_fut = int(m_fut // aim) if aim > 0 else 0
        legs = p["legs"][pf]
        pagadas = sum(l["pos"] * l["prima"] for l in legs if l["pos"] > 0)
        costo_neto_u = sum(l["pos"] * l["prima"] for l in legs)
        n_opc = int(m_opc // (M_o * pagadas)) if pagadas > 0 else 0

        def g_fut(Sh):
            return n_fut * M_f * (Sh - F0)

        def g_opc(Sh):
            u = sum(l["pos"] * ((max(Sh - l["K"], 0) if l["tipo"] == "CALL" else max(l["K"] - Sh, 0)) - l["prima"]) for l in legs)
            return n_opc * M_o * u

        S_base = S0 * math.exp(mu_S)
        res.append({"perfil": pf, "%KRF": p["krf_pct"][pf], "KRF $": krf, "KRF al vencimiento": krf_prof, "UT KRF": ut_krf,
                    "CAPITALES": ut_cap, "DERIVADOS": g_fut(S_base) + g_opc(S_base),
                    "NE": ut_krf + ut_cap + g_fut(S_base) + g_opc(S_base)})
        res[-1]["NE %"] = res[-1]["NE"] / inv
        div.append({"perfil": pf, "RISK %": 1 - p["krf_pct"][pf], "RISK $": riesgo, "% capitales": p["cap_pct"][pf],
                    "$ capitales": cap, "% derivados": 1 - p["cap_pct"][pf], "$ derivados": dv})
        der.append({"perfil": pf, "monto": dv, "futuros (AIM) %": p["fut_pct"][pf], "monto futuros": m_fut,
                    "opciones (primas) %": 1 - p["fut_pct"][pf], "monto opciones": m_opc,
                    "estimación futuros": g_fut(S_base), "estimación opciones": g_opc(S_base)})
        fut.append({"perfil": pf, "subyacente": d["nombre"], "spot": S0, "F0 teórico": F0, "multiplicador": M_f,
                    "AIM por contrato": aim, "contratos": n_fut, "garantía depositada": n_fut * aim,
                    "efectivo sin usar": m_fut - n_fut * aim, "nocional": n_fut * M_f * F0, "nocional / inversión": n_fut * M_f * F0 / inv,
                    "estimación (base)": g_fut(S_base)})
        opc.append({"perfil": pf, "estrategia": p["estrategia"][pf], "descripción": ESTRATEGIAS_NOTA[p["estrategia"][pf]],
                    "legs": "; ".join(f"{'+' if l['pos'] > 0 else ''}{l['pos']} {l['tipo']} K={l['K']:.2f} prima={l['prima']:.4f}" for l in legs),
                    "primas pagadas por unidad": pagadas, "costo neto por unidad": costo_neto_u, "contratos": n_opc,
                    "prima neta total": n_opc * M_o * costo_neto_u, "efectivo sin usar": m_opc - n_opc * M_o * pagadas,
                    "estimación (base)": g_opc(S_base)})
        for nombre, z in ESCENARIOS_Z:
            Sh = S0 * math.exp(mu_S + z * sig * math.sqrt(hy))
            r_i = rends + betas * z * sig_ipc * math.sqrt(hy)
            uc = float((montos * r_i).sum())
            esc.append({"perfil": pf, "escenario": nombre, "z": z, "precio subyacente": Sh, "UT KRF": ut_krf, "CAPITALES": uc,
                        "FUTUROS": g_fut(Sh), "OPCIONES": g_opc(Sh), "NE": ut_krf + uc + g_fut(Sh) + g_opc(Sh)})
            esc[-1]["valor final"] = inv + esc[-1]["NE"]
            esc[-1]["NE %"] = esc[-1]["NE"] / inv
    return {"resumen": pd.DataFrame(res), "diversificacion": pd.DataFrame(div), "capitales": cap_tab,
            "derivados": pd.DataFrame(der), "futuros": pd.DataFrame(fut), "opciones": pd.DataFrame(opc),
            "escenarios": pd.DataFrame(esc), "F0": F0, "aim": aim, "mu_subyacente": mu_S}


def preparar(base: dict, nombre: str, S0: float, sigma: float, beta: float, r_cont: float, q: float, sigma_ipc: float,
             mult: float = 100, aim_pct: float = 0.15, aim_contrato: float | None = None, ancho: float = 0.05) -> dict:
    """Completa los parámetros de la nota con los datos del subyacente de derivados y las primas teóricas."""
    import copy
    p = copy.deepcopy(base)
    p["sigma_ipc"] = sigma_ipc
    p["derivados"] = {"nombre": nombre, "S0": S0, "sigma": sigma, "beta": beta, "r_cont": r_cont, "q": q,
                      "mult_fut": mult, "mult_opc": mult, "aim_pct": aim_pct, "aim_contrato": aim_contrato, "ancho": ancho}
    T = p["dias"] / 365
    p["legs"] = {pf: legs_estrategia(p["estrategia"][pf], S0, T, r_cont, q, sigma, ancho) for pf in PERFILES}
    return p
