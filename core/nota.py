"""Nota estructurada por perfil: renta fija + mercado de capitales + futuros + opciones.

Estructura de cálculo (todas las reglas son explícitas):
1. Renta fija (KRF): %KRF × inversión invertido en el instrumento que elige el algoritmo de renta_fija.seleccionar
   para el perfil y el horizonte. Valor al horizonte = KRF × (1 + rendimiento al horizonte − duración × Δtasa).
2. Porción de riesgo = inversión − KRF → capitales (canasta de acciones MX y EE.UU.) y derivados.
3. Derivados → futuros (el monto es garantía: margen inicial) y opciones (primas).
   - Futuros: canasta multiactivo (futuros_multi.asignar) con stop-loss hipotético.
   - Opciones: estrategia por perfil sobre el subyacente elegido, primas teóricas Black-Scholes al horizonte.
4. Escenarios: z ∈ {−2.5, −1, 0, +1, +2.5}. Acciones: r_i = rend_i + β_i·z·σ_IPC·√T. Subyacente de opciones:
   S0·e^(μ + zσ√T). Futuros: movimiento e^(zσ_i√T) − 1 (en estrés, en contra de cada posición). Tasas: Δ = −60·z pb
   (alzas de tasas en escenarios adversos). Son hipótesis, sin probabilidades.
5. Ficha de condiciones: pago al vencimiento, protección (sólo la que da la renta fija mantenida al vencimiento;
   nunca garantizada contractualmente aquí), participación, barreras (stop-loss) y límites (apalancamiento).
"""
from __future__ import annotations

import copy
import math

import numpy as np
import pandas as pd

from .options import bsm
from . import futuros_multi as fm
from . import renta_fija as rfj

PERFILES = ["AGRESIVO", "MODERADO", "CONSERVADOR"]
ESCENARIOS_Z = [("1. Adverso severo", -2.5), ("2. Adverso moderado", -1.0), ("3. Neutral (base)", 0.0),
                ("4. Optimista moderado", 1.0), ("5. Optimista extremo", 2.5)]
BP_POR_Z = -60  # Δ tasas en pb por unidad de z
ESTRATEGIAS_NOTA = {
    "STG": "Long strangle (call OTM + put OTM): gana con movimientos grandes",
    "BTF": "Long call butterfly: gana si el precio se queda cerca del centro",
    "FLOOR": "Floor: put comprada (protege contra caídas)",
    "CAP": "Cap: call vendida OTM (limita la ganancia a cambio de prima)",
    "CALL": "Call comprada (participa en alzas con pérdida limitada a la prima)",
    "COLLAR": "Collar: put comprada + call vendida (banda de protección de bajo costo)",
    "STRADDLE": "Long straddle (call + put ATM): gana con volatilidad",
}

CONFIG_EJEMPLO = {
    "AGRESIVO": {"krf_pct": 0.20, "cap_pct": 0.20, "fut_pct": 0.60, "estrategia": "STG", "stop_pct": 0.10},
    "MODERADO": {"krf_pct": 0.50, "cap_pct": 0.50, "fut_pct": 0.50, "estrategia": "BTF", "stop_pct": 0.06},
    "CONSERVADOR": {"krf_pct": 0.70, "cap_pct": 0.80, "fut_pct": 0.40, "estrategia": "FLOOR", "stop_pct": 0.03},
}
ACCIONES_EJEMPLO = [
    {"nombre": "CEMEX", "simbolo": "CEMEXCPO.MX", "mercado": "BMV", "sector": "Materiales", "beta": 1.2, "rend_manual": 0.06,
     "pesos": {"CONSERVADOR": 100 / 480, "MODERADO": 100 / 500, "AGRESIVO": 0.0}},
    {"nombre": "BIMBO", "simbolo": "BIMBOA.MX", "mercado": "BMV", "sector": "Consumo básico", "beta": 1.0, "rend_manual": 0.059,
     "pesos": {"CONSERVADOR": 80 / 480, "MODERADO": 50 / 500, "AGRESIVO": 0.0}},
    {"nombre": "PEÑOLES", "simbolo": "PE&OLES.MX", "mercado": "BMV", "sector": "Minería", "beta": 0.4, "rend_manual": 0.04,
     "pesos": {"CONSERVADOR": 100 / 480, "MODERADO": 250 / 500, "AGRESIVO": 120 / 320}},
    {"nombre": "WALMEX", "simbolo": "WALMEX.MX", "mercado": "BMV", "sector": "Consumo básico", "beta": 0.5, "rend_manual": 0.03,
     "pesos": {"CONSERVADOR": 0.0, "MODERADO": 0.0, "AGRESIVO": 0.0}},
    {"nombre": "NVIDIA", "simbolo": "NVDA", "mercado": "NASDAQ", "sector": "Tecnología", "beta": 0.7, "rend_manual": 0.022,
     "pesos": {"CONSERVADOR": 100 / 480, "MODERADO": 100 / 500, "AGRESIVO": 200 / 320}},
    {"nombre": "APPLE", "simbolo": "AAPL", "mercado": "NASDAQ", "sector": "Tecnología", "beta": 0.9, "rend_manual": 0.03,
     "pesos": {"CONSERVADOR": 100 / 480, "MODERADO": 0.0, "AGRESIVO": 0.0}},
]
PARAMS_EJEMPLO = {"inversion": 2_000_000.0, "dias": 91, "rf_anual": 0.0669, "prm": 0.06, "modo_rend": "manual",
                  "perfiles": list(PERFILES), "config": CONFIG_EJEMPLO, "acciones": ACCIONES_EJEMPLO,
                  "objetivo_rend": 0.03, "perdida_tolerada": 0.05}


def legs_estrategia(clave: str, S0: float, T: float, r: float, q: float, sigma: float, ancho: float = 0.05) -> list[dict]:
    def leg(tipo, K, pos):
        return {"tipo": tipo, "K": K, "pos": pos, "prima": bsm(S0, K, T, r, q, sigma, "call" if tipo == "CALL" else "put")}
    a = ancho * S0
    return {
        "STG": lambda: [leg("CALL", S0 + a, 1), leg("PUT", S0 - a, 1)],
        "BTF": lambda: [leg("CALL", S0 - a, 1), leg("CALL", S0, -2), leg("CALL", S0 + a, 1)],
        "FLOOR": lambda: [leg("PUT", S0 * 0.95, 1)],
        "CAP": lambda: [leg("CALL", S0 * 1.05, -1)],
        "CALL": lambda: [leg("CALL", S0, 1)],
        "COLLAR": lambda: [leg("PUT", S0 * 0.95, 1), leg("CALL", S0 * 1.05, -1)],
        "STRADDLE": lambda: [leg("CALL", S0, 1), leg("PUT", S0, 1)],
    }[clave]()


def resumen_estrategia(legs: list[dict], S0: float) -> dict:
    """Pérdida y ganancia máximas, y puntos de equilibrio al vencimiento, por unidad (evaluado en una malla amplia)."""
    S = np.linspace(0.01, S0 * 3, 6001)
    pay = sum(l["pos"] * ((np.maximum(S - l["K"], 0) if l["tipo"] == "CALL" else np.maximum(l["K"] - S, 0)) - l["prima"]) for l in legs)
    calls_netas = sum(l["pos"] for l in legs if l["tipo"] == "CALL")
    gan = np.inf if calls_netas > 0 else float(pay.max())
    per = -np.inf if calls_netas < 0 else float(pay.min())
    be = [float(S[i]) for i in range(1, len(S)) if pay[i - 1] * pay[i] < 0]
    return {"ganancia_max": gan, "perdida_max": per, "break_even": be, "costo_neto": sum(l["pos"] * l["prima"] for l in legs)}


def rend_capm(rf: float, beta: float, prm: float, dias: int) -> float:
    return (rf + beta * prm) * dias / 365


def preparar(base: dict, nombre: str, S0: float, sigma: float, beta: float, r_cont: float, q: float, sigma_ipc: float,
             mult: float = 100, ancho: float = 0.05, renta_fija: dict | None = None, futuros_cat: pd.DataFrame | None = None,
             personalizado: dict | None = None) -> dict:
    """Completa los parámetros: subyacente de opciones, legs con primas BSM, selección de renta fija y canasta de futuros por perfil."""
    p = copy.deepcopy(base)
    if personalizado:
        p["config"]["PERSONALIZADO"] = {k: personalizado[k] for k in ("krf_pct", "cap_pct", "fut_pct", "estrategia", "stop_pct")}
        p["puntaje"] = personalizado["puntaje"]
        if "PERSONALIZADO" not in p["perfiles"]:
            p["perfiles"].append("PERSONALIZADO")
        for a in p["acciones"]:
            a["pesos"].setdefault("PERSONALIZADO", a["pesos"].get(personalizado["perfil_referencia"], 0.0))
    p["sigma_ipc"] = sigma_ipc
    p["derivados"] = {"nombre": nombre, "S0": S0, "sigma": sigma, "beta": beta, "r_cont": r_cont, "q": q, "mult_opc": mult, "ancho": ancho}
    T = p["dias"] / 365
    p["legs"] = {pf: legs_estrategia(p["config"][pf]["estrategia"], S0, T, r_cont, q, sigma, ancho) for pf in p["perfiles"]}
    p["renta_fija"] = {}
    p["renta_fija_in"] = renta_fija
    if renta_fija:
        tabla = rfj.evaluar(renta_fija["tasas"], p["dias"], p["inversion"], renta_fija["inflacion"], renta_fija.get("udi"))
        p["renta_fija_tabla"] = tabla
        for pf in p["perfiles"]:
            _, sel = rfj.seleccionar(tabla, p["dias"], pf, p.get("puntaje") if pf == "PERSONALIZADO" else None,
                                     forzar=(p.get("rf_manual") or {}).get(pf))
            p["renta_fija"][pf] = sel
    p["futuros"] = {}
    if futuros_cat is not None:
        p["futuros_cat"] = futuros_cat
        for pf in p["perfiles"]:
            mez = fm.mezcla_personalizada(p["puntaje"]) if pf == "PERSONALIZADO" else fm.MEZCLA[pf]
            p["futuros"][pf] = mez
    return p


def calcular(p: dict) -> dict:
    inv, dias, rf, prm = p["inversion"], p["dias"], p["rf_anual"], p["prm"]
    hy = dias / 365
    d = p["derivados"]
    S0, sig, sig_ipc, M_o = d["S0"], d["sigma"], p["sigma_ipc"], d["mult_opc"]
    mu_S = rend_capm(rf, d["beta"], prm, dias)
    acciones = p["acciones"]
    for a in acciones:
        a["rend"] = a["rend_manual"] if p.get("modo_rend") == "manual" else rend_capm(rf, a["beta"], prm, dias)
    rends = np.array([a["rend"] for a in acciones])
    betas = np.array([a["beta"] for a in acciones])
    cap_tab = pd.DataFrame({"acción": [a["nombre"] for a in acciones], "mercado": [a.get("mercado", "") for a in acciones],
                            "sector": [a.get("sector", "") for a in acciones], "beta": betas, "rendimiento": rends})
    res, div, der, fut_det, opc, esc, ficha = [], [], [], [], [], [], []
    for pf in p["perfiles"]:
        cfg = p["config"][pf]
        sel = p["renta_fija"].get(pf) or {"instrumento": "Cetes (tasa capturada)", "rend_horizonte": rf * dias / 360, "duración": 0.0,
                                          "tasa_anual": rf, "justificación": "Sin comparador: tasa capturada"}
        riesgo = inv * (1 - cfg["krf_pct"])
        cap = riesgo * cfg["cap_pct"]
        dv = riesgo - cap
        montos = np.array([a["pesos"].get(pf, 0.0) * cap for a in acciones])
        cap_tab[pf] = montos
        m_fut = dv * cfg["fut_pct"]
        m_opc = dv - m_fut
        tope = p.get("tope_primas_pct") or 0.0
        sobrante = 0.0
        if tope > 0 and m_opc > tope * inv:  # tope de primas: el excedente se invierte en la renta fija seleccionada
            sobrante = m_opc - tope * inv
            m_opc = tope * inv
        krf = cfg["krf_pct"] * inv + sobrante
        krf_h = krf * (1 + sel["rend_horizonte"])
        asig = fm.asignar(p["futuros_cat"], m_fut, p["futuros"][pf], stop_pct=cfg.get("stop_pct")) if p.get("futuros_cat") is not None else pd.DataFrame()
        legs = p["legs"][pf]
        pagadas = sum(l["pos"] * l["prima"] for l in legs if l["pos"] > 0)
        costo_u = sum(l["pos"] * l["prima"] for l in legs)
        calls_netas = sum(l["pos"] for l in legs if l["tipo"] == "CALL")
        n_presup = int(m_opc // (M_o * pagadas)) if pagadas > 0 else 10 ** 9
        n_cubierto = int(cap // (S0 * M_o))  # calls vendidas netas: sólo cubiertas por el valor de la canasta (sin ventas en descubierto)
        n_opc = min(n_presup, n_cubierto) if calls_netas < 0 else (n_presup if pagadas > 0 else 0)

        def g_opc(Sh):
            u = sum(l["pos"] * ((max(Sh - l["K"], 0) if l["tipo"] == "CALL" else max(l["K"] - Sh, 0)) - l["prima"]) for l in legs)
            return n_opc * M_o * u

        def g_fut(z):
            return fm.pnl(asig, z, dias, cfg.get("stop_pct"))[0] if not asig.empty else 0.0

        S_base = S0 * math.exp(mu_S)
        base_fut, base_opc = g_fut(0.0), g_opc(S_base)
        ut_krf = krf_h - krf
        ut_cap = float((montos * rends).sum())
        ne = ut_krf + ut_cap + base_fut + base_opc
        res.append({"perfil": pf, "renta fija": sel["instrumento"], "%KRF": cfg["krf_pct"], "KRF $": krf, "rend. RF horizonte": sel["rend_horizonte"],
                    "KRF al horizonte": krf_h, "UT KRF": ut_krf, "CAPITALES": ut_cap, "FUTUROS": base_fut, "OPCIONES": base_opc,
                    "NE": ne, "NE %": ne / inv, "NE anualizado %": ne / inv * 365 / dias})
        div.append({"perfil": pf, "renta fija $": krf, "capitales $": cap, "futuros (garantía) $": m_fut, "opciones (primas) $": m_opc, "sobrante a renta fija $": sobrante,
                    "renta fija %": krf / inv, "capitales %": cap / inv, "futuros %": m_fut / inv, "opciones %": m_opc / inv})
        nocional = float(asig["nocional_MXN"].sum()) if not asig.empty else 0.0
        der.append({"perfil": pf, "monto derivados": dv, "futuros %": cfg["fut_pct"], "monto futuros": m_fut, "monto opciones": m_opc,
                    "contratos futuros": int(asig["contratos"].sum()) if not asig.empty else 0, "nocional futuros": nocional,
                    "apalancamiento (nocional/inversión)": nocional / inv, "estimación futuros": base_fut, "estimación opciones": base_opc})
        if not asig.empty:
            a2 = asig.copy(); a2.insert(0, "perfil", pf); fut_det.append(a2)
        rs = resumen_estrategia(legs, S0)
        opc.append({"perfil": pf, "estrategia": cfg["estrategia"], "descripción": ESTRATEGIAS_NOTA[cfg["estrategia"]],
                    "legs": "; ".join(f"{'+' if l['pos'] > 0 else ''}{l['pos']} {l['tipo']} K={l['K']:.2f} prima={l['prima']:.4f}" for l in legs),
                    "contratos": n_opc, "costo neto por unidad": costo_u, "prima neta total": n_opc * M_o * costo_u,
                    "pérdida máx. por unidad": rs["perdida_max"], "ganancia máx. por unidad": rs["ganancia_max"],
                    "break-even": ", ".join(f"{x:.2f}" for x in rs["break_even"]), "estimación (base)": base_opc})
        peor = None
        for nombre, z in ESCENARIOS_Z:
            Sh = S0 * math.exp(mu_S + z * sig * math.sqrt(hy))
            dbp = BP_POR_Z * z
            v_rf = rfj.valor_escenario(sel, krf, dbp) - krf
            uc = float((montos * (rends + betas * z * sig_ipc * math.sqrt(hy))).sum())
            f_ = g_fut(z)
            o_ = g_opc(Sh)
            ne_z = v_rf + uc + f_ + o_
            esc.append({"perfil": pf, "escenario": nombre, "z": z, "Δ tasas pb": dbp, "precio subyacente": Sh, "RENTA FIJA": v_rf,
                        "CAPITALES": uc, "FUTUROS": f_, "OPCIONES": o_, "NE": ne_z, "valor final": inv + ne_z, "NE %": ne_z / inv})
            peor = ne_z if peor is None else min(peor, ne_z)
        prot = krf_h / inv
        krf_100 = 1 / (1 + sel["rend_horizonte"])
        ficha.append({"perfil": pf, "plazo (días)": dias, "inversión": inv, "renta fija": sel["instrumento"],
                      "protección (piso por renta fija)": prot,
                      "protección del capital": ("Total en el escenario base si la renta fija se mantiene al vencimiento" if krf / inv >= krf_100
                                                 else f"PARCIAL: la renta fija cubre {prot*100:.1f}% del capital; NO garantizada"),
                      "KRF necesario para 100%": krf_100,
                      "participación en alzas de la canasta": cap / inv,
                      "barrera (stop-loss futuros)": cfg.get("stop_pct"),
                      "límite de apalancamiento": nocional / inv,
                      "pago al vencimiento": "Valor final = renta fija al horizonte + valor de la canasta + resultado de futuros + resultado de opciones",
                      "peor escenario (NE)": peor})
    escdf = pd.DataFrame(esc)
    chequeo = []
    for pf in p["perfiles"]:
        e = escdf[escdf.perfil == pf].set_index("z")
        base_pct = e.loc[0.0, "NE %"]
        obj = p.get("objetivo_rend")
        tol = p.get("perdida_tolerada")
        chequeo.append({"perfil": pf, "rend. base %": base_pct,
                        "objetivo (horizonte) %": obj * dias / 365 if obj is not None else np.nan,
                        "cumple objetivo": (base_pct >= obj * dias / 365) if obj is not None else None,
                        "pérdida adverso moderado %": -min(e.loc[-1.0, "NE %"], 0),
                        "pérdida tolerada %": tol,
                        "dentro de tolerancia": (-min(e.loc[-1.0, "NE %"], 0) <= tol) if tol is not None else None})
    return {"resumen": pd.DataFrame(res), "diversificacion": pd.DataFrame(div), "capitales": cap_tab, "derivados": pd.DataFrame(der),
            "futuros": pd.concat(fut_det) if fut_det else pd.DataFrame(), "opciones": pd.DataFrame(opc), "escenarios": escdf,
            "ficha": pd.DataFrame(ficha), "chequeo": pd.DataFrame(chequeo), "mu_subyacente": mu_S}


def krf_para_tolerancia(p: dict, perfil: str, paso: float = 0.01) -> float | None:
    """Menor %KRF (con la misma mezcla del resto) cuya pérdida en el escenario adverso moderado no supera la tolerancia."""
    tol = p.get("perdida_tolerada")
    if tol is None:
        return None
    q = copy.deepcopy(p)
    k = q["config"][perfil]["krf_pct"]
    while k <= 1.0001:
        q["config"][perfil]["krf_pct"] = k
        r = calcular(q)
        e = r["escenarios"]
        perd = -min(e[(e.perfil == perfil) & (e.z == -1.0)]["NE %"].iloc[0], 0)
        if perd <= tol:
            return round(k, 4)
        k += paso
    return None


CUANDO_CONVIENE = {
    "STG": ("Ganar con un movimiento grande en cualquier dirección", "Se espera alta volatilidad (resultados, noticias) sin saber la dirección"),
    "BTF": ("Ganar si el precio termina cerca del strike central, con pérdida limitada", "Se espera estabilidad del precio (mercado lateral)"),
    "FLOOR": ("Proteger contra caídas pagando una prima", "Se tiene exposición larga y se teme una baja"),
    "CAP": ("Cobrar una prima a cambio de limitar la ganancia", "Se espera un alza limitada o lateralidad y se posee el activo"),
    "CALL": ("Participar en alzas arriesgando sólo la prima", "Se espera un alza y se quiere limitar la pérdida"),
    "COLLAR": ("Banda de protección de bajo costo: piso con la put y techo con la call", "Se posee el activo y se acepta ceder parte del alza por proteger la baja"),
    "STRADDLE": ("Ganar con volatilidad alta alrededor del precio actual", "Se espera un movimiento fuerte inminente"),
}


CLAVES_REQUERIDAS = ("perfiles", "config", "acciones", "inversion", "dias", "prm", "rf_anual", "sigma_ipc", "derivados", "legs",
                     "renta_fija", "renta_fija_in", "renta_fija_tabla", "futuros_cat", "futuros")


def params_completos(p) -> bool:
    """True si p tiene todo lo que necesitan calcular() y el Excel (p. ej. parámetros guardados por una versión anterior no)."""
    return isinstance(p, dict) and all(k in p for k in CLAVES_REQUERIDAS) and all(pf in p["config"] for pf in p["perfiles"])

