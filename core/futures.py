"""Futuros sobre acciones/índice. Los futuros no tienen estilo de ejercicio (americano/europeo)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def precio_teorico(S, r, q, T) -> float:
    """Costo de acarreo con capitalización continua: F = S·e^((r−q)T). Es un precio TEÓRICO,
    no una cotización de MexDer."""
    return S * np.exp((r - q) * T)


def pnl(n, M, F_ini, F_fin, posicion="larga") -> float:
    """P&L bruto = n·M·(F_final − F_inicial); signo invertido para posiciones cortas."""
    s = 1 if posicion == "larga" else -1
    return s * n * M * (F_fin - F_ini)


def resultado_agregado(acciones, S0, ST, n, M, F0, FT, posicion_futuro, comisiones=0.0) -> dict:
    sub = acciones * (ST - S0)
    fut = pnl(n, M, F0, FT, posicion_futuro)
    return {"subyacente": sub, "futuro": fut, "comisiones": -comisiones, "total": sub + fut - comisiones}


def razon_cobertura(acciones, M, beta_cobertura=1.0) -> float:
    """Número de contratos para cubrir: N = β·acciones/M (β=1 para futuro sobre la misma acción)."""
    return beta_cobertura * acciones / M


def margen_diario(precios_futuro: pd.Series, n, M, posicion, aim_por_contrato, minimo_mant_pct=1.0) -> pd.DataFrame:
    """Simulación de ajustes diarios (marcaje a mercado) sobre una trayectoria de precios del futuro.

    AIM = aportación inicial mínima (dato que debe verificarse con MexDer/Asigna; aquí lo introduce el
    usuario). La garantía NO es una pérdida: es un depósito. Si el saldo cae bajo AIM×minimo_mant_pct se
    registra una llamada de margen para restituirlo a la AIM.
    """
    s = 1 if posicion == "larga" else -1
    saldo = aim_por_contrato * n
    filas = []
    prev = precios_futuro.iloc[0]
    acumulado = 0.0
    for f, p in precios_futuro.iloc[1:].items():
        ajuste = s * n * M * (p - prev)
        acumulado += ajuste
        saldo += ajuste
        llamada = 0.0
        if saldo < aim_por_contrato * n * minimo_mant_pct:
            llamada = aim_por_contrato * n - saldo
            saldo += llamada
        filas.append({"fecha": f, "precio_futuro": p, "ajuste_diario": ajuste, "pyg_acumulada": acumulado,
                      "llamada_margen": llamada, "saldo_garantía": saldo})
        prev = p
    return pd.DataFrame(filas)


def stop_loss_terminal(F0, FT, stop, posicion, deslizamiento_pct=0.0) -> tuple[float, bool]:
    """Precio de salida HIPOTÉTICO con stop sobre un escenario terminal (trayectoria lineal supuesta).

    Si el precio final cruza el stop, se supone ejecución en stop·(1∓deslizamiento). Advertencia: en la
    realidad pueden existir brechas (gaps) y el stop puede ejecutarse peor o no ejecutarse. Si la trayectoria
    real toca el stop y luego se recupera, este cálculo terminal no lo captura.
    """
    if posicion == "larga" and FT <= stop:
        return stop * (1 - deslizamiento_pct), True
    if posicion == "corta" and FT >= stop:
        return stop * (1 + deslizamiento_pct), True
    return FT, False
