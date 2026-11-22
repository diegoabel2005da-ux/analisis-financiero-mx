"""Servicio de datos de mercado.

Fuente automática: Yahoo Finance (vía la librería yfinance), proveedor SECUNDARIO.
Yahoo no es la fuente oficial de la BMV; sus cifras pueden diferir del cierre
oficial publicado por la Bolsa. Por eso cada serie lleva metadatos de
procedencia y puede reconciliarse contra un archivo oficial importado.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field, asdict
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

TZ_MX = ZoneInfo("America/Mexico_City")
FUENTE_YAHOO = "Yahoo Finance (proveedor secundario, vía yfinance)"
MAX_DIAS_HISTORIA = 366  # requisito del usuario: periodicidad máxima de 1 año

# Definiciones explícitas de cada tipo de precio que maneja la plataforma.
TIPOS_PRECIO = {
    "Close": "Cierre del proveedor (Yahoo), ajustado por splits, NO por dividendos. "
             "No equivale necesariamente al cierre oficial BMV.",
    "Adj Close": "Cierre ajustado por splits y dividendos (Yahoo). Sólo para rendimientos totales.",
    "Open": "Apertura del proveedor.",
    "High": "Máximo del período del proveedor.",
    "Low": "Mínimo del período del proveedor.",
}


@dataclass
class MetaSerie:
    instrumento: str
    simbolo: str
    mercado: str
    fuente: str
    tipo_cotizacion: str
    moneda: str
    fecha_inicio: str
    fecha_fin_solicitada: str
    ultima_fecha_disponible: str | None
    fecha_consulta: str
    zona_horaria: str = "America/Mexico_City"
    precision: str = "2 decimales (precisión publicada por el proveedor puede variar)"
    estado: str = "No disponible"
    observaciones: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def ahora_mx() -> dt.datetime:
    return dt.datetime.now(TZ_MX)


def estado_actualizacion(ultima_fecha: pd.Timestamp | None, ahora: dt.datetime | None = None) -> str:
    """Clasifica el estado de la última observación.

    BMV opera de 8:30 a 15:00 hora de Ciudad de México (lunes a viernes).
    Yahoo publica datos de BMV con retraso (no son tiempo real).
    """
    ahora = ahora or ahora_mx()
    if ultima_fecha is None or pd.isna(ultima_fecha):
        return "No disponible"
    ultima = pd.Timestamp(ultima_fecha).date()
    hoy = ahora.date()
    if ultima == hoy:
        if ahora.time() < dt.time(15, 0):
            return "Intradía / preliminar (retrasado, no tiempo real)"
        return "Cierre del día según proveedor (preliminar hasta confirmar contra BMV)"
    # Días hábiles (lun-vie) transcurridos desde la última barra. No incluye
    # el calendario de días inhábiles de BMV: se informa como posible causa.
    # busday_count excluye el día final; si hoy es hábil y la sesión ya cerró, hoy también cuenta.
    habiles = int(np.busday_count(ultima + dt.timedelta(days=1), hoy))
    if np.is_busday(hoy) and ahora.time() >= dt.time(15, 0):
        habiles += 1
    if habiles <= 1:
        return "Histórico: último cierre disponible del proveedor"
    return f"Desactualizado: {habiles} días hábiles sin datos (verificar día inhábil o suspensión)"


def validar_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Devuelve una tabla de incidencias de calidad. severidad: CRITICA / ADVERTENCIA."""
    inc = []
    if df.empty:
        return pd.DataFrame([{"fecha": None, "regla": "Serie vacía", "severidad": "CRITICA", "detalle": ""}])
    if df.index.has_duplicates:
        for f in df.index[df.index.duplicated()]:
            inc.append((f, "Fecha duplicada", "CRITICA", ""))
    for col in ["Open", "High", "Low", "Close"]:
        if col in df:
            bad = df[col].isna()
            for f in df.index[bad]:
                inc.append((f, f"{col} faltante", "ADVERTENCIA", "La cifra no se sustituye: queda vacía"))
            nonpos = df[col] <= 0
            for f in df.index[nonpos.fillna(False)]:
                inc.append((f, f"{col} no positivo", "CRITICA", str(df.at[f, col])))
    if {"High", "Low", "Open", "Close"} <= set(df.columns):
        tol = 1e-9
        hl = df["High"] + tol < df["Low"]
        for f in df.index[hl.fillna(False)]:
            inc.append((f, "Máximo < Mínimo", "CRITICA", ""))
        fuera = (df["Close"] > df["High"] + 1e-6) | (df["Close"] < df["Low"] - 1e-6)
        for f in df.index[fuera.fillna(False)]:
            inc.append((f, "Cierre fuera del rango máx-mín", "CRITICA", ""))
    if "Volume" in df:
        cero = df["Volume"] == 0
        for f in df.index[cero.fillna(False)]:
            inc.append((f, "Volumen cero", "ADVERTENCIA", "Posible día sin operación o dato incompleto"))
    if not df.index.is_monotonic_increasing:
        inc.append((None, "Fechas no ordenadas", "ADVERTENCIA", "Se ordenaron"))
    return pd.DataFrame(inc, columns=["fecha", "regla", "severidad", "detalle"])


def hay_criticas(incidencias: pd.DataFrame) -> bool:
    return (not incidencias.empty) and (incidencias["severidad"] == "CRITICA").any()


def descargar_historico(simbolo: str, inicio: dt.date, fin: dt.date, nombre: str | None = None):
    """Descarga OHLCV diario desde Yahoo Finance sin ajuste automático.

    Devuelve (df, meta). `fin` es inclusivo. Lanza ValueError si el rango excede 1 año.
    """
    if (fin - inicio).days > MAX_DIAS_HISTORIA:
        raise ValueError("El rango máximo permitido es de 1 año.")
    import yfinance as yf  # importación diferida: no se requiere para las pruebas

    consulta = ahora_mx()
    tk = yf.Ticker(simbolo)
    df = tk.history(start=inicio.isoformat(), end=(fin + dt.timedelta(days=1)).isoformat(),
                    interval="1d", auto_adjust=False, actions=True)
    obs = []
    if df is None or df.empty:
        meta = MetaSerie(nombre or simbolo, simbolo, "BMV", FUENTE_YAHOO, "Diario OHLCV", "MXN",
                         inicio.isoformat(), fin.isoformat(), None, consulta.isoformat(timespec="seconds"),
                         estado="No disponible",
                         observaciones=["Yahoo no devolvió datos para este símbolo/rango. Verifique el símbolo "
                                        "o importe un archivo CSV validado."])
        return pd.DataFrame(), meta
    df.index = pd.DatetimeIndex(df.index).tz_localize(None).normalize()
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]
    keep = [c for c in ["Open", "High", "Low", "Close", "Adj Close", "Volume", "Dividends", "Stock Splits"] if c in df]
    df = df[keep].copy()
    if "Adj Close" not in df:
        obs.append("El proveedor no entregó 'Adj Close'; los rendimientos totales no están disponibles.")
    moneda = "MXN"
    try:
        moneda = (tk.fast_info.get("currency") or "MXN")
    except Exception:
        obs.append("No fue posible confirmar la moneda con el proveedor; se asume MXN por cotizar en BMV.")
    ultima = df.index.max()
    meta = MetaSerie(nombre or simbolo, simbolo, "BMV", FUENTE_YAHOO, "Diario OHLCV (sin ajustar por dividendos)",
                     moneda, inicio.isoformat(), fin.isoformat(), ultima.date().isoformat(),
                     consulta.isoformat(timespec="seconds"), estado=estado_actualizacion(ultima, consulta),
                     observaciones=obs)
    return df, meta


def importar_csv_precios(archivo) -> pd.DataFrame:
    """Importa un CSV/Excel con columnas fecha + Close (y opcionalmente OHLCV)."""
    nombre = getattr(archivo, "name", "")
    if str(nombre).lower().endswith((".xlsx", ".xls")):
        raw = pd.read_excel(archivo)
    else:
        raw = pd.read_csv(archivo)
    cols = {c: c.strip().lower() for c in raw.columns}
    raw = raw.rename(columns=cols)
    mapa = {"fecha": "Date", "date": "Date", "apertura": "Open", "open": "Open", "maximo": "High", "máximo": "High",
            "high": "High", "minimo": "Low", "mínimo": "Low", "low": "Low", "cierre": "Close", "close": "Close",
            "precio": "Close", "volumen": "Volume", "volume": "Volume"}
    raw = raw.rename(columns={c: mapa[c] for c in raw.columns if c in mapa})
    if "Date" not in raw or "Close" not in raw:
        raise ValueError("El archivo debe tener columnas 'fecha' y 'cierre'.")
    raw["Date"] = pd.to_datetime(raw["Date"], dayfirst=True, errors="coerce")
    if raw["Date"].isna().any():
        raise ValueError("Hay fechas que no se pudieron interpretar.")
    out = raw.set_index("Date").sort_index()
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        if c in out:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def reconciliar(proveedor: pd.Series, oficial: pd.Series, decimales: int = 2) -> pd.DataFrame:
    """Compara cierres del proveedor contra una referencia oficial (mismo instrumento y definición).

    La coincidencia se evalúa a la precisión publicada (`decimales`). No se fuerza
    ninguna coincidencia: las diferencias se registran.
    """
    a = proveedor.round(decimales).rename("proveedor")
    b = oficial.round(decimales).rename("oficial")
    df = pd.concat([a, b], axis=1)
    df["estado"] = np.where(df["proveedor"].isna(), "Falta en proveedor",
                    np.where(df["oficial"].isna(), "Falta en oficial",
                    np.where(np.isclose(df["proveedor"], df["oficial"], atol=0.5 * 10 ** -decimales),
                             "Coincide", "DISCREPANCIA")))
    df["diferencia"] = df["proveedor"] - df["oficial"]
    return df


def remuestrear(df: pd.DataFrame, frecuencia: str) -> pd.DataFrame:
    """Agrega OHLCV diario a otra frecuencia: primera apertura, máximo, mínimo, último cierre, volumen total.

    Frecuencias: D, W, M, 2M, Q, 6M, A. La agrupación bimestral y semestral es por
    meses calendario consecutivos a partir de enero (ene-feb, mar-abr... / ene-jun, jul-dic).
    """
    if frecuencia == "D" or df.empty:
        return df.copy()
    agg = {}
    for c, f in [("Open", "first"), ("High", "max"), ("Low", "min"), ("Close", "last"),
                 ("Adj Close", "last"), ("Volume", "sum"), ("Dividends", "sum")]:
        if c in df:
            agg[c] = f
    reglas = {"W": "W-FRI", "M": "ME", "Q": "QE", "A": "YE"}
    if frecuencia in reglas:
        regla = reglas[frecuencia]
        out = df.resample(regla).agg(agg)
        ult = df.index.to_series().resample(regla).max()
        out = out.loc[out["Close"].notna()]
        out.index = pd.DatetimeIndex(ult.reindex(out.index).values, name="Date")
        return out
    elif frecuencia in ("2M", "6M"):
        meses = 2 if frecuencia == "2M" else 6
        clave = df.index.year * 100 + ((df.index.month - 1) // meses)
        out = df.groupby(clave).agg(agg)
        fechas = df.index.to_series().groupby(clave).max()
        out.index = pd.DatetimeIndex(fechas.values, name="Date")
        return out
    raise ValueError(f"Frecuencia no soportada: {frecuencia}")


FACTOR_ANUAL = {"D": 252, "W": 52, "M": 12, "2M": 6, "Q": 4, "6M": 2, "A": 1}


def descargar_info(simbolo: str) -> dict:
    """Datos de perfil y fundamentales del proveedor. Todo lo que falte se deja ausente."""
    import yfinance as yf
    tk = yf.Ticker(simbolo)
    out = {"consulta": ahora_mx().isoformat(timespec="seconds"), "fuente": FUENTE_YAHOO}
    for nombre, attr in [("info", "info"), ("income_a", "income_stmt"), ("income_q", "quarterly_income_stmt"),
                         ("balance_a", "balance_sheet"), ("balance_q", "quarterly_balance_sheet"),
                         ("cash_a", "cashflow"), ("cash_q", "quarterly_cashflow"), ("dividends", "dividends"),
                         ("targets", "analyst_price_targets"), ("earnings_dates", "earnings_dates"),
                         ("calendar", "calendar")]:
        try:
            v = getattr(tk, attr)
            out[nombre] = v
        except Exception as e:  # el proveedor no siempre ofrece cada bloque
            out[nombre] = None
            out.setdefault("errores", []).append(f"{attr}: {type(e).__name__}")
    return out
