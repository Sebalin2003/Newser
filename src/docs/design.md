### 2. Archivo: `docs/design.md`

```markdown
# UI/UX Design System: News Trend Analyzer
> **Filosofía: Dark-Canvas Editorial Dashboard**

## 1. Overview y Principios de Diseño
El sistema visual del "News Trend Analyzer" funciona como un panel de control corporativo y analítico. Prioriza la densidad de información limpia sobre la decoración. No hay sombras, no hay gradientes complejos y no hay elementos flotantes ("Flat Design"). La separación de las secciones se define estrictamente por el uso del espacio en blanco y componentes divisorios nativos.

El sistema opera bajo un único modo visual: **Dark Canvas Mode**, garantizando una inmersión analítica de alto contraste y previniendo la fatiga visual. 

**Regla de Oro de Arquitectura Frontend:** Todo el diseño debe construirse utilizando la API nativa de Streamlit (`st.components`). Queda estrictamente prohibida la inyección de bloques de CSS personalizados (`unsafe_allow_html=True`) que fuercen colores absolutos o sombras (`box-shadow`), ya que esto rompe el motor de renderizado responsivo de la librería.

---

## 2. Paleta de Colores y Configuración (config.toml)
La identidad visual corporativa ("Tech Blue") y el modo oscuro estricto se inyectan globalmente a través del archivo `.streamlit/config.toml`. La aplicación no debe hardcodear hexadecimales en `app.py`.

### Configuración Base (Obligatoria en `.streamlit/config.toml`):
```toml
[theme]
base = "dark"
primaryColor = "#1A73E8"
font = "sans serif"

```

### Paleta Semántica Resultante (Manejada por Streamlit):

| Componente Visual | Color Asignado / Filosofía |
| --- | --- |
| **Fondo Global (Canvas)** | Noche profunda (`#0E1117` nativo) |
| **Superficies Elevadas** | Gris oscuro para tarjetas y expanders (`#262730` nativo) |
| **Texto Principal (Ink)** | Blanco de alto contraste (`#FAFAFA`) |
| **Texto Secundario (Mute)** | Gris plata para metadatos (`#A0AEC0`) |
| **Acentos Analíticos** | Tech Blue para botones primarios y gráficos (`#1A73E8`) |

---

## 3. Layout y Grid System (Asimetría)

El espacio de pantalla es el recurso más valioso. El diseño no debe dejar grandes bloques de vacío.

* **Configuración Global:** `st.set_page_config(layout="wide")` es mandatorio.
* **Separación Lógica:** Usar `st.divider()` exclusivamente para separar los 3 bloques principales (Macro-Resumen IA -> Dashboard -> Exploración de Noticias).
* **Asimetría del Panel Central:** La visualización de gráficos y métricas se debe organizar en un esquema de columnas asimétrico de proporción 2:1.
* `col_main, col_stats = st.columns([2, 1], gap="large")`
* **Izquierda (`col_main`):** Gráficos de tendencias interactivas de gran tamaño.
* **Derecha (`col_stats`):** Tarjetas de resumen del corpus, deltas y métricas secundarias.



---

## 4. Tipografía y Jerarquía

La jerarquía tipográfica es ligera y aireada, delegada al motor Markdown de Streamlit. No importar fuentes externas (Google Fonts).

* **Display Header:** `st.title("📰 News Trend Analyzer")` con `st.caption` debajo para el subtítulo del pipeline.
* **Section Headers:** `st.subheader()` para títulos de módulos ("Análisis de Tendencias").
* **In-Card Strong:** Para los nombres de las fuentes en el listado de noticias, utilizar la sintaxis bold de Markdown: `[NOMBRE DIARIO]`.
* **Badges Semánticos:** Para las áreas de interés, utilizar OBLIGATORIAMENTE la sintaxis nativa de insignias de Streamlit:
* Formato exacto: `:blue-badge[{noticia['area']}]` o `:gray-badge[...]`.



---

## 5. Anatomía de Componentes (Component Library)

### 5.1 Call-to-Actions (Botones)

* **Primary CTA:** Botón para ejecutar el pipeline de datos (`st.button("Analizar Período", type="primary")`). Utiliza el Tech Blue corporativo.
* **Secondary CTA:** Botones de utilidad como la descarga del reporte (`st.download_button(...)`). Utilizan el diseño "outline" (transparente con borde).

### 5.2 Tarjetas de KPI (Metric Cards)

* Renderizadas horizontalmente utilizando `st.columns()`.
* Deben utilizar el componente nativo `st.metric(label, value, delta)`.
* La lógica de color del `delta` (verde positivo, rojo negativo) es delegada al motor interno de Streamlit.

### 5.3 Drill-Down Feed (El Módulo de Noticias)

Cada registro de noticia individual se encapsula en un contenedor interactivo (`st.expander`).

* **Estado Colapsado (Cabecera):** Debe mostrar la fuente, el título y el badge.
* *Ejemplo literal:* `st.expander(f"📰 [{noticia['fuente'].upper()}] — {noticia['titulo']} :blue-badge[{noticia['area']}]")`


* **Estado Expandido (Interior):**
* El primer elemento es el texto del LLM, precedido por el identificador en negrita: `Resumen Ejecutivo (AI): {noticia['resumen_ia']}`
* El bloque final es un hipervínculo semántico hacia la fuente original renderizado con `st.markdown("🔗 [Leer noticia completa ↗](url)")`.



### 5.4 Manejo de Fallbacks y Estados Vacíos

Se prohíbe mostrar mensajes de error en texto plano o gris apagado que perjudiquen la lectura.

* **Error Crítico (Fallo de fuente/API):** `st.error("🚨 Mensaje de error claro")`.
* **Dato Faltante (Sin resumen de IA):** `st.warning("⚠️ Resumen automático no disponible actualmente.")`.

---

## 6. Performance y Responsividad Visual (Rules of Engagement)

1. **Ajuste Dinámico de Gráficos:** Todo componente de renderizado visual, como `st.plotly_chart` y `st.dataframe`, debe incluir forzosamente el parámetro `use_container_width=True`.
2. **No Anidar Contenedores Visibles:** No colocar un `st.expander` dentro de otro `st.expander` ni abusar de `st.container(border=True)` de forma anidada, ya que genera líneas superpuestas que rompen la filosofía Flat.
3. **Sidebar Exclusivo para Controles:** El panel izquierdo (`st.sidebar`) está estrictamente reservado para inputs de usuario (fechas, multiselect de áreas). Nunca renderizar gráficos o resultados analíticos en la barra lateral.

```

```