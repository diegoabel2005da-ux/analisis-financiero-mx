"""Derivados sobre tasas de interés: curvas, caps y floors (Black-76 y Bachelier).

Los caps/floors en México se negocian principalmente en el mercado extrabursátil (OTC). Este módulo
produce valuaciones TEÓRICAS a partir de una curva y una volatilidad que el usuario identifica como
importadas, históricas o hipotéticas. No son primas cotizadas.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import norm

# Claves del Sistema de Información Económica (SIE) de Banxico
SERIES_BANXICO = {
    "SF61745": "Tasa objetivo de Banxico",
    "SF331451": "TIIE de Fondeo a un día hábil",
    "SF43783": "TIIE a 28 días",
    "SF43878": "TIIE a 91 días",
    "SF111916": "TIIE a 182 días",
    "SF43936": "Cetes 28 días (rendimiento)",
    "SF43939": "Cetes 91 días (rendimiento)",
    "SF43942": "Cetes 182 días (rendimiento)",
    "SF43945": "Cetes 364 días (rendimiento)",
}
PLAZO_CETES = {"SF43936": 28, "SF43939": 91, "SF43942": 182, "SF43945": 364}


def banxico_series(ids: list[str], token: str, inicio: dt.date | None = None, fin: dt.date | None = None) -> pd.DataFrame:
    """Consulta el SIE-API de Banxico (requiere token gratuito). Devuelve filas: serie, titulo, fecha, valor.
    Datos 'N/E' (no existe) se omiten; nunca se rellenan."""
    import requests
    base = "https://www.banxico.org.mx/SieAPIRest/service/v1/series/" + ",".join(ids) + "/datos"
    url = base + (f"/{inicio.isoformat()}/{fin.isoformat()}" if inicio and fin else "/oportuno")
    resp = requests.get(url, headers={"Bmx-Token": token, "Accept": "application/json"}, timeout=30)
    resp.raise_for_status()
    filas = []
    for s in resp.json().get("bmx", {}).get("series", []):
        for d in s.get("datos", []) or []:
            v = str(d.get("dato", "")).replace(",", "")
            try:
                val = float(v)
            except ValueError:
                continue
            filas.append({"serie": s["idSerie"], "titulo": s.get("titulo", SERIES_BANXICO.get(s["idSerie"], "")),
                          "fecha": pd.to_datetime(d["fecha"], dayfirst=True), "valor_%": val})
    return pd.DataFrame(filas)


# ------------------------------------------------------------------ convenciones
def fraccion_año(d0: dt.date, d1: dt.date, base: str = "ACT/360") -> float:
    dias = (pd.Timestamp(d1) - pd.Timestamp(d0)).days
    if base == "ACT/360":
        return dias / 360
    if base == "ACT/365":
        return dias / 365
    if base == "30/360":
        a, b = pd.Timestamp(d0), pd.Timestamp(d1)
        dd0, dd1 = min(a.day, 30), (min(b.day, 30) if a.day >= 30 else b.day)
        return ((b.year - a.year) * 360 + (b.month - a.month) * 30 + (dd1 - dd0)) / 360
    raise ValueError(base)


def calendario(inicio: dt.date, fin: dt.date, periodo: str = "28D") -> list[tuple[dt.date, dt.date]]:
    """Genera períodos [inicio, fin). '28D' = cada 28 días; '1M','3M','6M' = meses. El último período se recorta
    a la fecha final. No ajusta por días inhábiles (limitación informada)."""
    fechas = [pd.Timestamp(inicio)]
    while fechas[-1] < pd.Timestamp(fin):
        if periodo.endswith("D"):
            nxt = fechas[-1] + pd.Timedelta(days=int(periodo[:-1]))
        else:
            nxt = pd.Timestamp(inicio) + pd.DateOffset(months=int(periodo[:-1]) * len(fechas))
        fechas.append(min(nxt, pd.Timestamp(fin)))
    return [(fechas[i].date(), fechas[i + 1].date()) for i in range(len(fechas) - 1)]


# ------------------------------------------------------------------ curva
@dataclass
class Curva:
    """Curva de descuento a partir de nodos (días, tasa %, convención).

    Convenciones admitidas por nodo: 'simple ACT/360' (mercado de dinero: Cetes, TIIE),
    'cero continua ACT/365'. Cada nodo se convierte a factor de descuento y a tasa cero continua
    z = −ln(DF)/t (t en ACT/365). Interpolación LINEAL en z; extrapolación plana. DF(0)=1.
    """
    nodos: pd.DataFrame  # columnas: dias, tasa_pct, convencion
    fecha: dt.date
    fuente: str = "Introducida por el usuario"
    desplazamiento_bp: object = 0.0  # float o función t->bp

    def __post_init__(self):
        n = self.nodos.dropna().sort_values("dias")
        n = n[n["dias"] > 0]
        if len(n) < 1:
            raise ValueError("La curva necesita al menos un nodo con plazo > 0.")
        t = n["dias"].values / 365
        z = []
        for d, r, c in zip(n["dias"], n["tasa_pct"], n["convencion"]):
            r = r / 100
            if str(c).startswith("simple"):
                df = 1 / (1 + r * d / 360)
            else:
                df = np.exp(-r * d / 365)
            z.append(-np.log(df) / (d / 365))
        self._t = t
        self._z = np.array(z)

    def cero(self, t):
        t = np.atleast_1d(np.asarray(t, dtype=float))
        z = np.interp(t, self._t, self._z, left=self._z[0], right=self._z[-1])
        b = self.desplazamiento_bp
        z = z + (b(t) if callable(b) else b) / 10000
        return z

    def df(self, t):
        t = np.atleast_1d(np.asarray(t, dtype=float))
        return np.where(t <= 0, 1.0, np.exp(-self.cero(t) * t))

    def desplazada(self, bp):
        return Curva(self.nodos, self.fecha, self.fuente, bp)

    def forward_simple(self, t0, t1, alfa):
        """F = (DF(t0)/DF(t1) − 1)/α : tasa forward simple consistente con la curva."""
        return (self.df(t0) / self.df(t1) - 1) / alfa


# ------------------------------------------------------------------ fórmulas
def black76(F, K, T, sigma, tipo="cap"):
    """Valor sin descontar por unidad de nocional·α. Requiere F>0, K>0 (lognormal)."""
    F, K = float(F), float(K)
    if T <= 0 or sigma <= 0:
        return max(F - K, 0) if tipo == "cap" else max(K - F, 0)
    if F <= 0 or K <= 0:
        return np.nan
    d1 = (np.log(F / K) + 0.5 * sigma ** 2 * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if tipo == "cap":
        return F * norm.cdf(d1) - K * norm.cdf(d2)
    return K * norm.cdf(-d2) - F * norm.cdf(-d1)


def bachelier(F, K, T, sigma_n, tipo="cap"):
    """Modelo normal. sigma_n en unidades de tasa (0.01 = 100 pb). Admite tasas negativas."""
    if T <= 0 or sigma_n <= 0:
        return max(F - K, 0) if tipo == "cap" else max(K - F, 0)
    s = sigma_n * np.sqrt(T)
    d = (F - K) / s
    if tipo == "cap":
        return (F - K) * norm.cdf(d) + s * norm.pdf(d)
    return (K - F) * norm.cdf(-d) + s * norm.pdf(d)


def tiempo_efectivo(t_ini, t_fin, fijacion):
    """Tiempo para la volatilidad.
    - 'al inicio' (in advance, p. ej. TIIE a plazo): T = t_inicio (fecha de fijación).
    - 'compuesta en atraso' (TIIE de Fondeo compuesta): la tasa se conoce al final; la varianza acumulada
      bajo el supuesto de Lyashenko-Mercurio (2019) es T = t_inicio + (t_fin − t_inicio)/3 para t_inicio ≥ 0.
    """
    if fijacion == "al inicio":
        return max(t_ini, 0.0)
    return max(t_ini, 0.0) + (t_fin - max(t_ini, 0.0)) / 3


def valuar_cap_floor(curva: Curva, fecha_val: dt.date, periodos, nocionales, K, sigma, modelo="Black-76",
                     tipo="cap", base="ACT/360", fijacion="al inicio", tasa_fijada_primer=None,
                     incluir_primero=True) -> pd.DataFrame:
    """Valúa cada caplet/floorlet y devuelve la tabla. Valor total = suma de valores presentes.

    VP_i = N_i·α_i·DF(t_pago)·Black/Bachelier(F_i, K, T_i, σ). Pago al final del período.
    Si la tasa del primer período ya está fijada (fijación al inicio con inicio ≤ fecha de valuación) se usa
    el valor intrínseco con la tasa fijada.
    """
    filas = []
    for i, ((d0, d1), N) in enumerate(zip(periodos, nocionales)):
        a = fraccion_año(d0, d1, base)
        t0 = (pd.Timestamp(d0) - pd.Timestamp(fecha_val)).days / 365
        t1 = (pd.Timestamp(d1) - pd.Timestamp(fecha_val)).days / 365
        if t1 <= 0:
            continue
        if t0 < 0:
            # Período en curso: se proyecta con el forward desde hoy (limitación: en composición en atraso
            # no se incorporan las fijaciones ya observadas).
            F = float(curva.forward_simple(0.0, t1, fraccion_año(fecha_val, d1, base))[0])
        else:
            F = float(curva.forward_simple(t0, t1, a)[0])
        T = tiempo_efectivo(t0, t1, fijacion)
        fijada = fijacion == "al inicio" and t0 <= 0
        if fijada and tasa_fijada_primer is not None:
            F = tasa_fijada_primer
        if fijada:
            T = 0.0
        if modelo == "Black-76":
            u = black76(F, K, T, sigma, tipo)
        else:
            u = bachelier(F, K, T, sigma, tipo)
        DFp = float(curva.df(t1)[0])
        vp = N * a * DFp * u
        intr = N * a * DFp * (max(F - K, 0) if tipo == "cap" else max(K - F, 0))
        incluir = incluir_primero or i > 0
        filas.append({"periodo": i + 1, "inicio": d0, "fin": d1, "nocional": N, "alfa": a, "t_fijacion": t0,
                      "T_vol": T, "forward_%": F * 100, "strike_%": K * 100, "DF_pago": DFp,
                      "valor_presente": vp if incluir else 0.0, "valor_intrinseco": intr if incluir else 0.0,
                      "valor_tiempo": (vp - intr) if incluir else 0.0, "incluido": incluir,
                      "tipo": "caplet" if tipo == "cap" else "floorlet"})
    return pd.DataFrame(filas)


def sensibilidades(curva, fecha_val, periodos, nocionales, K, sigma, modelo, tipo, base, fijacion, **kw) -> dict:
    """DV01 (cambio de VP por +1 pb paralelo en la curva cero), vega (+1 punto de vol: 1% Black, 1 pb Bachelier),
    theta (1 día calendario: fecha de valuación +1 con la misma curva), y choques no paralelos
    (empinamiento: −10 pb en t=0 a +10 pb en el último plazo; aplanamiento: inverso; mariposa: +10 pb al centro)."""
    base_v = valuar_cap_floor(curva, fecha_val, periodos, nocionales, K, sigma, modelo, tipo, base, fijacion, **kw)["valor_presente"].sum()
    v = lambda c=curva, s=sigma, f=fecha_val: valuar_cap_floor(c, f, periodos, nocionales, K, s, modelo, tipo, base, fijacion, **kw)["valor_presente"].sum()
    tmax = max((pd.Timestamp(p[1]) - pd.Timestamp(fecha_val)).days / 365 for p in periodos)
    dv = 0.01 if modelo == "Black-76" else 0.0001
    res = {
        "valor": base_v,
        "DV01_+1pb": v(curva.desplazada(1.0)) - base_v,
        "vega_+1pt": v(s=sigma + dv) - base_v,
        "theta_1dia": v(f=(pd.Timestamp(fecha_val) + pd.Timedelta(days=1)).date()) - base_v,
        "empinamiento_±10pb": v(curva.desplazada(lambda t: -10 + 20 * np.asarray(t) / tmax)) - base_v,
        "aplanamiento_±10pb": v(curva.desplazada(lambda t: 10 - 20 * np.asarray(t) / tmax)) - base_v,
        "mariposa_+10pb_centro": v(curva.desplazada(lambda t: 10 * (1 - np.abs(2 * np.asarray(t) / tmax - 1)))) - base_v,
    }
    return res


def vol_historica_tasa(serie_pct: pd.Series) -> dict:
    """Vol normal anualizada (pb) = desv. est. de cambios diarios en pb × √252.
    Vol lognormal = desv. est. de ln(r_t/r_(t−1)) × √252. Ambas HISTÓRICAS, no implícitas."""
    s = serie_pct.dropna()
    s = s[s > 0]
    cambios_bp = s.diff().dropna() * 100
    lnr = np.log(s / s.shift(1)).dropna()
    return {"normal_bp": float(cambios_bp.std(ddof=1) * np.sqrt(252)) if len(cambios_bp) > 2 else np.nan,
            "lognormal": float(lnr.std(ddof=1) * np.sqrt(252)) if len(lnr) > 2 else np.nan, "n": len(s)}


def nocionales_amortizacion(N, n_periodos, tipo="bullet", lista=None):
    if tipo == "bullet":
        return [N] * n_periodos
    if tipo == "lineal":
        return [N * (1 - i / n_periodos) for i in range(n_periodos)]
    if tipo == "personalizada" and lista:
        return list(lista)[:n_periodos] + [lista[-1]] * max(0, n_periodos - len(lista))
    return [N] * n_periodos


def flujos_exposicion(tabla_fwd: pd.DataFrame, choque_bp, spread, posicion, coberturas: list[dict]) -> pd.DataFrame:
    """Flujos por período en un escenario.

    Tasa realizada R_i = forward_i + choque_i (choque en pb, escalar o lista). Exposición:
    pasivo → intereses pagados = −N·α·(R+spread); activo → recibidos = +N·α·(R+spread).
    Cada cobertura: {'tipo': cap|floor, 'K', 'signo' (+1 comprado, −1 vendido), 'proporcion'} con
    pago = signo·prop·N·α·max(R−K,0) (cap) o max(K−R,0) (floor). Primas se tratan en el resumen.
    """
    df = tabla_fwd[["periodo", "inicio", "fin", "nocional", "alfa", "forward_%", "DF_pago"]].copy()
    ch = np.asarray(choque_bp if np.ndim(choque_bp) else [choque_bp] * len(df), dtype=float)
    R = df["forward_%"].values / 100 + ch / 10000
    df["tasa_realizada_%"] = R * 100
    s = -1 if posicion == "pasivo" else 1
    df["flujo_exposicion"] = s * df["nocional"] * df["alfa"] * (R + spread)
    total_cob = np.zeros(len(df))
    for j, c in enumerate(coberturas):
        if c["tipo"] == "cap":
            pago = np.maximum(R - c["K"], 0)
        else:
            pago = np.maximum(c["K"] - R, 0)
        f = c["signo"] * c.get("proporcion", 1.0) * df["nocional"].values * df["alfa"].values * pago
        df[f"cobertura_{j+1}_{c['tipo']}"] = f
        total_cob += f
    df["flujo_coberturas"] = total_cob
    df["flujo_neto"] = df["flujo_exposicion"] + df["flujo_coberturas"]
    return df
