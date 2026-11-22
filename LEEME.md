# Plataforma de análisis financiero, derivados y coberturas — Mercado mexicano

Aplicación web en Python/Streamlit. Consulta Yahoo Finance cada vez que se abre (historia máxima: 1 año),
analiza cualquier subyacente accionario de MexDer (o cualquier símbolo `.MX`) y valora futuros, opciones,
caps y floors con escenarios por perfil de riesgo.

## Cómo obtener tu link (sin programar, unos 20 minutos)

### 1. Crea una cuenta en GitHub
1. Entra a https://github.com y elige **Sign up**. Confirma tu correo.

### 2. Crea un repositorio y sube los archivos
1. En GitHub, botón **+** (arriba a la derecha) → **New repository**.
2. Nombre: `analisis-financiero-mx`. Marca **Private** si no quieres que se vea el código. Clic en **Create repository**.
3. En la página nueva, clic en el enlace **uploading an existing file**.
4. Descomprime el ZIP en tu computadora. Abre la carpeta `plataforma` y **arrastra TODO su contenido**
   (las carpetas `core`, `ui`, `data`, `tests` y los archivos `app.py`, `requirements.txt`, etc.) a la página de GitHub.
   - La carpeta `.streamlit` está oculta en Mac/Windows; si no se sube no pasa nada (sólo define el color turquesa).
5. Abajo, clic en **Commit changes**.

### 3. Publica la app en Streamlit Community Cloud (gratis)
1. Entra a https://share.streamlit.io y elige **Continue with GitHub**. Autoriza el acceso.
2. Clic en **Create app** → **Deploy a public app from GitHub** (o la opción equivalente para tu repositorio).
3. Repository: `tu-usuario/analisis-financiero-mx` · Branch: `main` · Main file path: `app.py`.
4. En **Advanced settings** elige Python 3.12.
5. Clic en **Deploy**. En 2–5 minutos tendrás un link como `https://analisis-financiero-mx.streamlit.app`.

### 4. Controla quién entra
En tu app, **Share** (arriba a la derecha): puedes limitar el acceso a correos específicos o dejarla para
cualquiera que tenga el link. No aparece en buscadores mientras no la promuevas.

### 5. (Opcional) Claves
En la app: **⋮ → Settings → Secrets**, pega:
```
BANXICO_TOKEN = "tu_token"          # gratis en https://www.banxico.org.mx/SieAPIRest/service/v1/token
ANTHROPIC_API_KEY = "tu_clave"      # sólo si quieres respuestas libres del asistente de IA
```
Sin token de Banxico puedes capturar o importar la curva de tasas manualmente. Sin clave de Anthropic el asistente
explica los resultados con reglas fijas.

## Qué se actualiza solo
- Precios, estados financieros y dividendos (Yahoo) cada vez que se abre la página.
- Con `BANXICO_TOKEN` en Secrets: tasa libre de riesgo (Cetes 28 días, convertida a tasa continua), tasa de largo plazo del
  DCF (Bono M 10 años si Banxico confirma la serie; si no, Cetes 364), curva de tasas (TIIE de Fondeo + Cetes) y
  volatilidad histórica de tasas. Caché de 6 horas.
- Rendimiento por dividendo: pagos de los últimos 12 meses (Yahoo) / último precio.
- Vencimientos de MexDer: se calculan por regla (tercer viernes de marzo, junio, septiembre y diciembre, o el día hábil
  anterior). Si un tercer viernes es día inhábil, agrégalo a `data/dias_inhabiles.csv` (columnas `fecha,descripcion`).
- Todos estos valores siguen siendo editables en pantalla y muestran su fuente.

Lo único manual: precios observados de futuros, primas de opciones y AIM de MexDer (no hay fuente gratuita automática).

## Qué hace cada sección
1 Inicio · 2 Emisoras (catálogo MexDer + tablero) · 3 Datos históricos (7 periodicidades, validación, reconciliación) ·
4 Análisis y valuación (ROC, Williams, estocástico, RSI 9/14/25, Fibonacci, DCF/WACC, múltiplos) · 5 Estados financieros ·
6 Patrones y riesgos (tendencias, beta, VaR/ES, correlaciones, liquidez) · 7 Análisis gráfico (chartismo + dibujo manual) ·
8 Futuros (AIM y ajustes diarios) · 9 Opciones (BSM, griegas, CRR, volatilidad implícita) · 10 Derivados de tasas
(Banxico, curvas) · 11 Caps y floors (Black-76/Bachelier, sensibilidades, escenarios) · 12 Estrategias · 13 Coberturas ·
14 Perfiles y escenarios (3 perfiles × estrategias × 5 escenarios) · 15 Reportes (IA; Excel en formato INTEGRAL con nota estructurada o estándar de 17 hojas; PDF) ·
16 Estudios guardados y auditoría · 17 Nota estructurada: perfilador de 10 preguntas (perfil PERSONALIZADO además de los 3 de referencia), comparador de renta fija (Cetes, Bonos M, Bondes F, Udibonos) con selección automática, acciones de BMV y NYSE/NASDAQ con betas y correlaciones, 16 futuros de 6 clases de activo diversificados por margen, estrategias con opciones (straddle, strangle, collar, cap, floor, butterfly, call), stop-loss, escenarios adversos/neutral/optimistas, ficha de condiciones, tope de primas opcional y reporte ejecutivo en PDF.

**Excel de la nota (formato INTEGRAL):** abre en la hoja DASHBOARD, donde se capturan monto, horizonte, prima de mercado, tasa y tope de primas. Siguen las 10 hojas recomendadas por el Proyecto Integrador (PERFIL, RENTA FIJA, MERCADO DE CAPITALES, FUTUROS MULTIACTIVO, OPCIONES Y ESTRATEGIAS, BLACK-SCHOLES, DIVERSIFICACIÓN, ESCENARIOS DE LA NOTA y REPORTE EJECUTIVO), el motor NOTA ESTRUCTURADA y las hojas del formato del curso. Todo está conectado por fórmulas.

## Fuentes y limitaciones (importante)
- **Precios:** Yahoo Finance es un proveedor secundario con retraso; no es el cierre oficial de la BMV. Puedes reconciliar
  contra un archivo oficial en *Datos históricos*.
- **MexDer:** no hay acceso gratuito automático a cotizaciones de futuros, primas de opciones ni AIM. Se capturan a mano;
  sin captura, la plataforma muestra valores **teóricos** etiquetados.
- **Catálogo:** `data/catalogo_mexder.csv`, revisado el 2026-11-21 con las páginas de contratos de bmv.com.mx. Para
  actualizarlo, edita el archivo en GitHub; la app se actualiza sola.
- **Caps/floors:** instrumentos OTC; valuación teórica con la curva y volatilidad que indiques.
- Los estados financieros del proveedor pueden diferir de los reportes oficiales a BMV/CNBV.

## Para desarrolladores
```
pip install -r requirements.txt
streamlit run app.py
pytest            # 37 pruebas matemáticas con valores de referencia
```
Estructura: `core/` motores de cálculo puros (sin interfaz) · `ui/` páginas Streamlit · `tests/` pruebas.
