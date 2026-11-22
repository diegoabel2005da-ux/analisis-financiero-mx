"""Perfilador del inversionista: cuestionario de 10 variables → puntaje 0–100 → perfil y asignación personalizada.

Las reglas son explícitas y lineales para poder auditarlas (no hay puntuaciones opacas):
- Puntaje s = Σ puntos / 30 (cada pregunta vale 0 a 3).
- Perfil de referencia: s < 0.35 CONSERVADOR · 0.35 ≤ s ≤ 0.65 MODERADO · s > 0.65 AGRESIVO.
- Asignación personalizada (continua en s):
  KRF = 0.80 − 0.65·s (acotado a 15%–85%) · capitales = 0.75 − 0.50·s de la porción de riesgo ·
  futuros = 0.30 + 0.35·s de los derivados (0 si no tiene experiencia con derivados) · stop-loss = 3% + 7%·s.
- Estrategia de opciones según la expectativa de mercado: bajista → FLOOR; lateral → BTF; alcista moderada → COLLAR;
  alcista fuerte → CALL; con s > 0.65 y expectativa lateral (volatilidad esperada) → STG.
"""
from __future__ import annotations

PREGUNTAS = [
    ("edad", "Edad", ["60 años o más", "45 a 59", "30 a 44", "Menos de 30"]),
    ("horizonte", "Horizonte de inversión", ["Hasta 3 meses", "3 a 12 meses", "1 a 3 años", "Más de 3 años"]),
    ("objetivo", "Objetivo principal", ["Preservar el capital", "Generar ingreso estable", "Crecimiento", "Máximo crecimiento"]),
    ("perdida", "Pérdida máxima que tolera en el horizonte", ["Hasta 2%", "Hasta 5%", "Hasta 10%", "Más de 10%"]),
    ("reaccion", "Si su inversión cae 20%, usted…", ["Vende todo", "Vende una parte", "Mantiene", "Compra más"]),
    ("experiencia", "Experiencia con derivados", ["Ninguna", "Básica", "Intermedia", "Avanzada"]),
    ("patrimonio", "Proporción de su patrimonio que invierte", ["Más de 50%", "25% a 50%", "10% a 25%", "Menos de 10%"]),
    ("liquidez", "Necesidad de disponer del dinero antes del plazo", ["Alta", "Media", "Baja", "Nula"]),
    ("ingresos", "Estabilidad de sus ingresos", ["Inestables", "Variables", "Estables", "Muy estables"]),
    ("mercado", "Expectativa de mercado para el horizonte", ["Bajista", "Lateral", "Alcista moderada", "Alcista fuerte"]),
]
PERDIDA_TOLERADA = [0.02, 0.05, 0.10, 0.20]


def puntaje(respuestas: dict) -> float:
    return sum(int(respuestas.get(k, 0)) for k, _, _ in PREGUNTAS) / 30


def perfil_referencia(s: float) -> str:
    return "CONSERVADOR" if s < 0.35 else ("MODERADO" if s <= 0.65 else "AGRESIVO")


def asignacion(respuestas: dict) -> dict:
    s = puntaje(respuestas)
    krf = min(0.85, max(0.15, 0.80 - 0.65 * s))
    cap = 0.75 - 0.50 * s
    fut = 0.0 if int(respuestas.get("experiencia", 0)) == 0 else 0.30 + 0.35 * s
    exp = int(respuestas.get("mercado", 1))
    estrategia = {0: "FLOOR", 1: "BTF", 2: "COLLAR", 3: "CALL"}[exp]
    if exp == 1 and s > 0.65:
        estrategia = "STG"
    return {"puntaje": s, "perfil_referencia": perfil_referencia(s), "krf_pct": krf, "cap_pct": cap, "fut_pct": fut,
            "estrategia": estrategia, "stop_pct": 0.03 + 0.07 * s,
            "perdida_tolerada": PERDIDA_TOLERADA[int(respuestas.get("perdida", 1))]}
