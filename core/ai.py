"""Asistente explicativo. Recibe ÚNICAMENTE resultados estructurados del motor matemático.

Si existe una clave de API de Anthropic en los 'secrets' de la aplicación, se usa Claude para redactar
explicaciones. Sin clave, se genera una explicación con reglas fijas a partir de los mismos datos.
En ningún caso el asistente produce cifras nuevas: sólo interpreta las que recibe.
"""
from __future__ import annotations

import json

import numpy as np

SISTEMA = """Eres un analista financiero que explica resultados de una plataforma de análisis del mercado mexicano.
Reglas obligatorias:
1. Usa sólo las cifras del JSON proporcionado. No inventes primas, tasas, volatilidades, cotizaciones ni probabilidades.
2. Si una cifra no está en el JSON, di explícitamente que no está disponible y qué módulo debe ejecutarse.
3. Distingue datos observados (proveedor/fuente) de supuestos del usuario y de valores teóricos de modelos.
4. No des recomendaciones de inversión personalizadas ni prometas resultados. Es una herramienta de análisis.
5. Una estrategia de volatilidad no es una cobertura; dilo cuando aplique.
6. Responde en español, con claridad, en no más de 350 palabras salvo que se pida un resumen ejecutivo."""

MODELO = "claude-sonnet-5-5"


def preguntar_claude(contexto: dict, pregunta: str, api_key: str, modelo: str = MODELO) -> str:
    import requests
    cuerpo = {
        "model": modelo, "max_tokens": 1200, "system": SISTEMA,
        "messages": [{"role": "user", "content": "Resultados del motor (JSON):\n" +
                      json.dumps(contexto, ensure_ascii=False, default=str)[:60000] + "\n\nPregunta: " + pregunta}],
    }
    r = requests.post("https://api.anthropic.com/v1/messages", json=cuerpo, timeout=90,
                      headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    r.raise_for_status()
    return "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")


def _f(x, d=2, pct=False):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "no disponible"
    return f"{x*100:.{d}f}%" if pct else f"{x:,.{d}f}"


def explicacion_reglas(ctx: dict) -> str:
    """Explicación determinista basada sólo en los resultados recibidos."""
    p = []
    a = ctx.get("activo", {})
    if a:
        p.append(f"**Activo:** {a.get('nombre')} ({a.get('simbolo')}). Último cierre del proveedor: "
                 f"{_f(a.get('ultimo_cierre'))} MXN al {a.get('ultima_fecha')} — estado: {a.get('estado')}.")
    r = ctx.get("riesgo", {})
    if r:
        p.append(f"**Riesgo histórico:** volatilidad anualizada {_f(r.get('volatilidad'), pct=True)}; "
                 f"máximo drawdown {_f(r.get('max_drawdown'), pct=True)}; VaR 95% diario histórico "
                 f"{_f(r.get('var95'), pct=True)} y ES {_f(r.get('es95'), pct=True)}. Beta vs IPC "
                 f"{_f(r.get('beta'))} (R² {_f(r.get('r2'))}). Son medidas del pasado, no pronósticos.")
    t = ctx.get("tecnico", {})
    if t:
        p.append(f"**Indicadores técnicos:** RSI14 {_f(t.get('rsi14'),1)} "
                 f"({'zona de sobrecompra (>70)' if (t.get('rsi14') or 0) > 70 else 'zona de sobreventa (<30)' if (t.get('rsi14') or 100) < 30 else 'zona neutral'}); "
                 f"Williams %R {_f(t.get('williams'),1)}; ROC {_f(t.get('roc'),2)}%. Tendencias: {t.get('tendencias','no calculadas')}.")
    v = ctx.get("valuacion", {})
    if v:
        p.append(f"**Valuación DCF (supuestos del usuario):** valor por acción {_f(v.get('valor_por_accion'))} MXN con WACC "
                 f"{_f(v.get('wacc'), pct=True)} y crecimiento terminal {_f(v.get('g'), pct=True)}; el valor terminal pesa "
                 f"{_f(v.get('peso_vt'),1)}% del valor empresa. Un valor teórico no implica que el precio lo alcance.")
    e = ctx.get("escenarios_resumen")
    if e:
        p.append("**Escenarios (acciones):** en el estrés adverso severo, por perfil, la alternativa con mejor resultado "
                 "combinado fue: " + "; ".join(f"{k}: {x['estrategia']} ({_f(x['resultado'])} MXN vs "
                                                 f"{_f(x['sin_cobertura'])} sin cobertura)" for k, x in e.items()) +
                 ". Las estrategias de volatilidad (straddle) no se consideran coberturas.")
    c = ctx.get("caps", {})
    if c:
        p.append(f"**Cap/Floor:** valor teórico {_f(c.get('valor'))} MXN ({c.get('modelo')}); DV01 {_f(c.get('dv01'))} MXN "
                 f"por pb; vega {_f(c.get('vega'))} MXN por punto. La volatilidad usada es {c.get('origen_vol')}.")
    if not p:
        return "Aún no hay resultados calculados en esta sesión. Ejecute primero los módulos de análisis."
    p.append("_Explicación generada con reglas fijas (sin modelo de lenguaje). Para respuestas a preguntas libres "
             "configure una clave de API de Anthropic en los secrets de la aplicación._")
    return "\n\n".join(p)
