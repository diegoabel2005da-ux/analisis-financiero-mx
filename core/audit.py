"""Bitácora de auditoría: cada cálculo registra fuente, parámetros, fórmula y resultado."""
from __future__ import annotations

import datetime as dt
import hashlib
import json

import numpy as np
import pandas as pd

from .data import ahora_mx

VERSION_MOTOR = "1.0.0"


def _serializable(o):
    if isinstance(o, (pd.Timestamp, dt.date, dt.datetime)):
        return o.isoformat()
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, pd.DataFrame):
        return {"filas": len(o), "columnas": list(map(str, o.columns))}
    if isinstance(o, pd.Series):
        return {"n": len(o)}
    if isinstance(o, float) and np.isnan(o):
        return None
    return str(o)


def a_json(obj) -> str:
    return json.dumps(obj, default=_serializable, ensure_ascii=False, indent=2)


def huella(df: pd.DataFrame | None) -> str | None:
    """Huella SHA-256 de los datos de entrada para reproducir el análisis."""
    if df is None or len(df) == 0:
        return None
    return hashlib.sha256(pd.util.hash_pandas_object(df, index=True).values.tobytes()).hexdigest()[:16]


def registrar(bitacora: list, modulo: str, entradas: dict, formula: str, resultado, fuente: str | None = None,
              huella_datos: str | None = None):
    ent = json.loads(a_json(entradas))
    res = json.loads(a_json(resultado))
    for prev in reversed(bitacora):
        if prev["modulo"] == modulo:
            if prev["entradas"] == ent and prev["resultado"] == res and prev["huella_datos"] == huella_datos:
                return  # mismo cálculo repetido por recarga de la página
            break
    bitacora.append({"marca_tiempo": ahora_mx().isoformat(timespec="seconds"), "version_motor": VERSION_MOTOR,
                     "modulo": modulo, "fuente": fuente, "huella_datos": huella_datos,
                     "entradas": ent, "formula": formula, "resultado": res})
    if len(bitacora) > 2000:
        del bitacora[:-2000]
