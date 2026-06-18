# newser

## Project Description

Producto: News Trend Analyzer (Pivot: Developer Pulse Edition)
Estado: MVP para Entorno de Producción


1. Visión y Propósito
El News Trend Analyzer es una herramienta de inteligencia competitiva y monitoreo tecnológico. Tras un refinamiento de alcance, el producto abandona el enfoque de "agregador de noticias generalistas" para convertirse en un radar de alta fidelidad enfocado estrictamente en la comunidad de desarrolladores.

Problema: Los ingenieros de software, tech leads y analistas sufren de "infoxicación" al intentar seguir el ritmo de frameworks, vulnerabilidades y debates en múltiples foros técnicos. Leer hilos interminables en Reddit o revisar repositorios en GitHub consume demasiado tiempo.
Solución: Un sistema autónomo que ingesta la actividad principal de las tres plataformas más relevantes (GitHub, Hacker News, Reddit), agrupa semánticamente los temas de los que habla la comunidad (para eliminar el ruido), y utiliza IA generativa local para presentar un mapa visual interactivo y resúmenes ejecutivos con análisis de sentimiento.

2. Público Objetivo
Ingenieros de Software / Tech Leads: Que necesitan mantenerse actualizados con las herramientas en tendencia (GitHub) y los debates arquitectónicos (HN/Reddit).

Analistas de Datos / Ciberseguridad: Que buscan alertas tempranas sobre vulnerabilidades o lanzamientos de modelos sin tener que monitorear foros manualmente.

3. Alcance de las Fuentes de Datos (Ingesta)
El sistema operará exclusivamente sobre las siguientes plataformas, utilizando una arquitectura mixta (API REST JSON y feeds RSS) para evitar bloqueos por Rate Limiting:

Hacker News: Extracción de "Top Stories" (ej. >100 puntos) para capturar el debate del ecosistema de Silicon Valley.

Reddit: Extracción de los posts "Top del día" de subreddits estrictamente técnicos (ej. r/programming, r/MachineLearning, r/dataengineering).

GitHub: Monitoreo de "Trending Repositories" y/o "Releases" de proyectos clave para identificar la adopción de nuevas tecnologías.

4. Requerimientos Funcionales (Core Features)
4.1. Motor de Procesamiento y NLP
Clustering Semántico: El sistema debe agrupar posts/repositorios que traten el mismo evento utilizando embeddings vectoriales multilingües (paraphrase-multilingual-MiniLM-L12-v2).

Validación de Entidades (Veto): Uso de spaCy (NER) para evitar que dos noticias con alta similitud semántica pero que hablan de entidades distintas (ej. "Lanzamiento de React" vs "Lanzamiento de Vue") se agrupen por error.

Análisis Cualitativo IA (JSON): Utilización de Gemini para generar por cada clúster:

Un resumen ejecutivo (3 líneas máximo).

Análisis de sentimiento clasificado estrictamente como positivo, negativo o neutral.

4.2. Interfaz Gráfica (Streamlit UI)
La experiencia de usuario debe ser Visual-First, interactiva y basada en el patrón Dark-Canvas.

A. Dashboard Operativo (Últimas 24 Horas):

Visualización Principal: Un gráfico de dispersión (Scatter/Bubble Plot) interactivo.

Eje X: Línea de tiempo de las últimas 24 horas.

Eje Y / Tamaño: Score de impacto (basado en interacciones, upvotes, estrellas).

Puntos: Clústers semánticos.

Drill-Down Interactivo: Al hacer clic en una burbuja del gráfico, la interfaz debe renderizar dinámicamente debajo la ficha del evento: Título representativo, emoji de sentimiento (🟢🔴⚪), el resumen generado por IA y los enlaces directos a las fuentes originales.

B. Dashboard Analítico (Últimos 7 Días):

Análisis Macro: Un gráfico de líneas mostrando la evolución temporal de los clústers o áreas temáticas. El Eje X debe mostrar fechas explícitas (ej. 18 May - 25 May).

Macro-Resumen IA: Un bloque de texto consolidado donde la IA resume las narrativas tecnológicas más importantes de toda la semana.

Distribución de Sentimiento: Gráfico de anillo (Dona) mostrando el balance de eventos positivos vs. negativos de la semana.

5. Requerimientos No Funcionales (Ingeniería y Rendimiento)
UI No Bloqueante (Asincronismo): La ejecución del pipeline ETL (scraping y NLP) debe ejecutarse en un hilo secundario (background thread) para permitir que el usuario siga navegando y visualizando el histórico sin que Streamlit se congele. Feedback de progreso debe mostrarse mediante st.status.

Concurrencia de Red (I/O Bound): La descarga de datos de las APIs y las peticiones de resumen a la IA deben paralelizarse utilizando ThreadPoolExecutor para minimizar el tiempo de espera.

Resiliencia: Si Gemini no está configurado o falla, el sistema debe omitir el enriquecimiento IA sin interrumpir el servicio. Si una fuente HTTP da timeout, el sistema debe aislar el error, omitir esa fuente e informar al usuario en la UI.

Optimización de Memoria (DB Pushdown): El filtrado de información (por fechas o áreas) debe realizarse directamente a nivel de base de datos mediante SQLAlchemy (cláusulas WHERE), prohibiendo cargar tablas enteras en la memoria RAM con Pandas para evitar riesgos de Out-Of-Memory (OOM).

6. Arquitectura Técnica
Backend & Concurrencia: Python 3.12, threading, concurrent.futures.

Frontend: Streamlit, Plotly Express (para visualizaciones interactivas).

Persistencia: SQLite, SQLAlchemy (ORM).

MLOps (NLP & IA): * sentence-transformers (Embeddings en CPU local).

spaCy (NER).

Gemini API via `google-genai`.

## Product Requirements Document
# Product Requirements Document: News Trend Analyzer (Developer Pulse Edition)

## 1. Visión y Propósito
El News Trend Analyzer es una plataforma de inteligencia competitiva diseñada para ingenieros de software, tech leads y analistas. El sistema ingesta, filtra y resume datos de las fuentes de mayor relevancia técnica (GitHub, Hacker News, Reddit), eliminando el "ruido" de la infoxicación mediante clustering semántico y análisis con IA generativa.

## 2. Público Objetivo
- Ingenieros de Software y Tech Leads: Seguimiento de frameworks emergentes, cambios en el ecosistema y debates arquitectónicos.
- Analistas de Datos y Ciberseguridad: Detección temprana de vulnerabilidades y lanzamientos críticos.

## 3. Alcance de Fuentes de Datos
- Hacker News: Top Stories (>100 puntos) para capturar el debate de alto nivel.
- Reddit: Posts "Top del día" en comunidades curadas (r/programming, r/MachineLearning, r/dataengineering).
- GitHub: Trending Repositories y Releases de proyectos clave para medir adopción técnica.

## 4. Requerimientos Funcionales
### 4.1. Motor de Procesamiento (NLP/IA)
- Clustering Semántico: Agrupación de eventos mediante `paraphrase-multilingual-MiniLM-L12-v2`.
- Validación de Entidades: Uso de spaCy (NER) para prevenir agrupaciones cruzadas erróneas entre tecnologías distintas.
- Análisis Cualitativo: Generación de resúmenes ejecutivos (máx. 3 líneas) y sentimiento (positivo/negativo/neutral) vía Gemini.

### 4.2. Interfaz (Streamlit UI)
- Dashboard Operativo (24h): Scatter Plot interactivo con drill-down (burbujas representativas de clústers).
- Dashboard Analítico (7 días): Gráficos de tendencia temporal, distribución de sentimiento y resumen macro semanal.
- Diseño: Dark-Canvas, componentes nativos, diseño responsivo y sin inyección de CSS arbitrario.

## 5. Requerimientos No Funcionales
- Arquitectura Asíncrona: Pipeline ETL fuera del hilo principal (background tasks).
- Resiliencia: Fallback automático entre APIs comerciales y modelos locales.
- Eficiencia: Pushdown de queries vía SQLAlchemy para evitar OOM (Out-of-Memory).
- Seguridad y Privacidad: Eliminación de metadatos (PII) en la ingesta y retención estricta de 30 días (GDPR/Ley 25.326).

## 6. Arquitectura Técnica
- Stack: Python 3.12, Streamlit, Plotly, SQLite, SQLAlchemy.
- ML/IA: sentence-transformers, spaCy, Gemini API.
- Infraestructura: Docker + VPS (AWS EC2 / DigitalOcean).

## 7. Estrategia de Datos y Priorización
- Source Weighting: GitHub (1.5x) > Hacker News (1.2x) > Reddit (0.8x).
- ETL Scheduler: Ejecución automatizada (cada 3-6 horas) mediante APScheduler.
- Concurrencia: Diseño optimizado para hasta 25 usuarios concurrentes (lectura pura).

## 8. Hoja de Ruta
- Sprint 1: Frontend "Visual-First" (Mockups, gráficos de radar, UI interactiva).
- Sprint 2: Motor Core (ORM, APIs, NLP robusto con prompt "One-Shot").
- Sprint 3: Automatización y Despliegue (Docker, Scheduler, Soft Launch).

## 9. Lineamientos de Diseño (UI/UX)
- Configuración: `layout="wide"` obligatorio.
- Paleta: Basada en `config.toml` (Primary: #1A73E8, Background: #0E1117).
- Limitaciones: No usar `unsafe_allow_html=True`. Todo componente debe ser nativo de Streamlit para garantizar consistencia técnica y responsividad.

## Technology Stack
# DOCUMENTO DE ARQUITECTURA: TECH STACK - NEWSER

## 1. Stack Tecnológico de Referencia

La arquitectura de Newser ha sido seleccionada para equilibrar la velocidad de desarrollo (Time-to-Market), la eficiencia en el procesamiento de lenguaje natural (NLP) y la mantenibilidad a largo plazo en un entorno de servidor VPS.

### 1.1 Backend y Lógica de Negocio
* **Lenguaje:** Python 3.12+ (aprovechando tipado estático y mejoras de rendimiento en concurrencia).
* **Gestión de Concurrencia:** `concurrent.futures` (ThreadPoolExecutor) para tareas I/O Bound y `threading` para la ejecución del pipeline ETL en background.
* **Scheduling:** `APScheduler` para la automatización del ciclo de vida de los datos (ejecución cada 4 horas).

### 1.2 Frontend (Interfaz de Usuario)
* **Framework:** Streamlit (patrón de diseño "Flat-UI" con `st.set_page_config(layout="wide")`).
* **Visualización de Datos:** Plotly Express (integración nativa para gráficos interactivos de dispersión y series temporales).
* **Gestión de Configuración:** `.streamlit/config.toml` (para asegurar la identidad visual "Dark Canvas" y evitar inyección CSS insegura).

### 1.3 Almacenamiento y Persistencia
* **Base de Datos:** SQLite (optimizada mediante SQLAlchemy ORM).
* **Estrategia de Datos:** Implementación de "Database Pushdown". Todo el filtrado de datos se realiza en el motor de base de datos (`SELECT ... WHERE fecha > ?`) para prevenir errores de Out-Of-Memory (OOM) en el servidor.
* **Política de Retención:** Hard delete automático a los 30 días para cumplimiento de privacidad (GDPR/Ley 25.326) y optimización de espacio.

### 1.4 Procesamiento de Lenguaje Natural (NLP) e IA
* **Embeddings:** `sentence-transformers` con modelo `paraphrase-multilingual-MiniLM-L12-v2` (ejecución local en CPU para baja latencia).
* **Entidades (NER):** `spaCy` (modelo `en_core_web_sm`) para validación y filtrado de entidades técnicas.
* **Motor de IA Generativa:**
    * **Primary:** Gemini.
    * **Integración:** Prompting "One-Shot" para forzar respuesta JSON estricta.

---

## 2. Justificación de Herramientas

| Tecnología | Justificación |
| :--- | :--- |
| **Python 3.12** | Ecosistema imbatible para NLP (spaCy/Sentence-Transformers) y manipulación de APIs. |
| **Streamlit** | Reduce el tiempo de creación del dashboard de semanas a días, manteniendo el enfoque en el backend de datos. |
| **SQLAlchemy** | Abstracción de base de datos necesaria para realizar consultas complejas y filtrado eficiente sin cargar dataframes masivos en RAM. |
| **SQLite** | Ideal para un MVP bajo demanda (10-25 usuarios concurrentes). Elimina la sobrecarga de gestión de un servidor de BD externo. |
| **Gemini** | Provee resúmenes ejecutivos y clasificación de sentimiento mediante API cloud. |

---

## 3. Infraestructura y Despliegue
* **Contenerización:** Docker + Docker Compose para la app Streamlit.
* **Hosting:** VPS (instancia con mínimo 16GB de RAM para soportar el modelo Llama 3 y la carga de embeddings).
* **Seguridad:** Ingesta mediante User-Agents configurados, uso de environment variables (`.env`) para keys y estricto cumplimiento de los ToS de las APIs mediante el borrado de metadatos PII (nombres, avatares, IDs de usuario) antes del almacenamiento.

---

## 4. Pipeline de Datos y Flujo de Trabajo
1. **Ingesta:** Paralelización de peticiones HTTP (Hacker News API, Reddit RSS, GitHub API).
2. **Transformación:** Limpieza de datos (stripping PII) y clustering semántico mediante vectores de similitud.
3. **Enriquecimiento:** Inferencia mediante LLM para extraer "palabra_clave" y "resumen" en formato JSON.
4. **Almacenamiento:** Persistencia en SQLite.
5. **Presentación:** Renderizado en el dashboard mediante queries SQLAlchemy asíncronas para el usuario final.

## Project Structure
# PROJECTSTRUCTURE: News Trend Analyzer (Developer Pulse Edition)

## 1. Visión General del Sistema
El proyecto sigue una arquitectura modular en Python 3.12, diseñada para la separación estricta entre la capa de ingesta (ETL), la capa de procesamiento inteligente (IA/NLP) y la capa de presentación (UI). La estructura busca minimizar el acoplamiento y facilitar el despliegue mediante contenedores.

## 2. Árbol de Directorios
newser/
├── .streamlit/             # Configuración del diseño y tema (config.toml)
├── data/                   # Volumen persistente para SQLite (se mapea a Docker)
├── src/
│   ├── __init__.py
│   ├── app.py              # Punto de entrada de la UI (Streamlit)
│   ├── config.py           # Gestión de variables de entorno y constantes
│   ├── database/           # Módulo de persistencia (SQLAlchemy)
│   │   ├── models.py       # Definición de esquemas de tablas
│   │   └── session.py      # Gestor de conexiones a SQLite
│   ├── ingestors/          # Lógica de scraping y APIs
│   │   ├── github.py       # Cliente API para tendencias
│   │   ├── hn.py           # Cliente API para Hacker News
│   │   └── reddit.py       # Cliente API/RSS para subreddits
│   ├── engine/             # Procesamiento semántico
│   │   ├── classifier.py   # Implementación de spaCy (NER)
│   │   └── llm_bridge.py   # Cliente Gemini
│   └── utils/              # Funciones auxiliares y logging
├── tests/                  # Tests unitarios para validación de prompts y parsers
├── Dockerfile              # Definición de la imagen del contenedor
├── docker-compose.yml      # Orquestación de servicios
├── requirements.txt        # Dependencias del proyecto
└── README.md               # Documentación general

## 3. Descripción de Módulos Críticos

### 3.1. Layer: Ingestors (`src/ingestors/`)
Cada archivo implementa una clase base para asegurar consistencia. Responsables de filtrar PII (datos personales) en la fuente y normalizar los datos a un formato interno antes de la inserción.
*   **github.py / hn.py / reddit.py**: Gestionan el control de rate-limiting y la asignación de pesos (1.5x, 1.2x, 0.8x) para la priorización de impacto.

### 3.2. Layer: Engine (`src/engine/`)
*   **classifier.py**: Contiene el pipeline de `sentence-transformers` para el clustering. Utiliza el modelo `paraphrase-multilingual-MiniLM-L12-v2` cargado en memoria al inicio.
*   **llm_bridge.py**: Implementa la lógica de "One-Shot Prompting" con Gemini. Si Gemini no está configurado, el enriquecimiento IA se omite sin bloquear el resto del pipeline.

### 3.3. Layer: Database (`src/database/`)
Utiliza SQLAlchemy con SQLite para un acceso rápido y eficiente. 
*   **models.py**: Define las tablas `Noticia` y `Cluster`.
*   **Retention Logic**: Contiene las rutinas de limpieza (cron jobs) que ejecutan `DELETE FROM Noticia WHERE fecha < date('now', '-30 days')`.

### 3.4. Layer: UI (`src/app.py`)
Maneja la presentación.
*   **Asincronismo**: Implementa `st.status` para feedback visual durante la ejecución de tareas.
*   **Visualización**: Integra `plotly` para el gráfico de dispersión y el panel de evolución temporal.
*   **Limitaciones**: Prohibido el uso de `unsafe_allow_html=True`. Toda la jerarquía visual se rige por `config.toml` y componentes nativos de Streamlit.

## 4. Estrategia de Despliegue y Concurrencia
*   **Background Jobs**: La ingesta no ocurre en `app.py`. Se utiliza una instancia separada o un planificador (`APScheduler`) integrado en un proceso independiente para mantener la UI "Read-Only".
*   **Contenerización**: El `docker-compose.yml` expone el servicio web y monta un volumen persistente para `/data`, garantizando que la base de datos sobreviva a los reinicios del contenedor.
*   **Escalabilidad**: Dada la limitación de SQLite, se implementan consultas de "pushdown" (filtros en la cláusula SQL) para evitar la carga de datasets completos en RAM.

## Database Schema Design
### 1. Modelo de Datos (Esquema Relacional)

La base de datos se estructura en torno a tres tablas principales para mantener el rendimiento y la integridad bajo el modelo de retención a 30 días. Se utiliza SQLite con SQLAlchemy como ORM.

**A. Tabla: `fuentes` (Configuración)**
Almacena los metadatos de los endpoints de ingesta.
* `id` (INTEGER, PK): Identificador único.
* `nombre` (TEXT): Ej: "GitHub", "Hacker News", "Reddit".
* `peso` (FLOAT): Factor de ponderación para el cálculo de impacto (1.5, 1.2, 0.8).
* `url_base` (TEXT): Endpoint de consulta.

**B. Tabla: `noticias` (Capa Operativa)**
Contiene el contenido bruto y procesado. Tras 30 días, se ejecuta un script de limpieza automática (cron).
* `id` (INTEGER, PK): Identificador único.
* `fuente_id` (INTEGER, FK): Relación con la tabla fuentes.
* `titulo` (TEXT): Título del post o repo.
* `url_original` (TEXT): Enlace a la fuente.
* `raw_content` (TEXT): Descripción original (stripped de metadatos PII).
* `score_original` (INTEGER): Upvotes o estrellas recibidas.
* `fecha_ingesta` (DATETIME): Timestamp de creación.
* `es_procesada` (BOOLEAN): Flag para el motor de NLP.

**C. Tabla: `clusters` (Resultado del Análisis)**
Resultado de la agrupación semántica y la inferencia del LLM.
* `id` (INTEGER, PK): Identificador único.
* `fecha_creacion` (DATETIME): Para filtrado de tendencias semanales.
* `palabra_clave` (TEXT): Categoría técnica central (ej. "Docker").
* `resumen` (TEXT): Texto generado por el LLM (máx. 3 líneas).
* `sentimiento` (TEXT): Clasificación (Positivo, Negativo, Neutral).
* `score_impacto` (FLOAT): Cálculo ponderado: (score_original * peso_fuente).

---

### 2. Diagrama de Relaciones y Flujo (SQLAlchemy Logic)

Las entidades están conectadas mediante relaciones de uno a muchos (One-to-Many):

`Fuente (1) ----> (N) Noticias`
`Noticia (N) ----> (1) Cluster`

**Estrategia de Índices (Optimización de Rendimiento):**
Para garantizar que la UI no sufra bloqueos (OOM) y cumpla con el requerimiento de "DB Pushdown", se definen los siguientes índices:
1. `idx_noticias_fecha`: Sobre `fecha_ingesta` para el Dashboard de 24 horas.
2. `idx_clusters_fecha`: Sobre `fecha_creacion` para el Dashboard analítico de 7 días.
3. `idx_clusters_keyword`: Para la búsqueda rápida y generación de gráficos de series temporales.

---

### 3. Integridad y Privacidad (Privacy by Design)

Para dar cumplimiento a las leyes de protección de datos (GDPR/Ley 25.326) y las políticas de los proveedores:

* **Saneamiento de PII:** La capa de ingesta (ETL) ejecuta un método `_sanitize_record()` que descarta campos como `author`, `username`, `avatar_url` y `email` antes de cualquier operación `INSERT` en la tabla `noticias`.
* **Políticas de Eliminación:** Se implementará un job de limpieza que ejecuta periódicamente: 
  `DELETE FROM noticias WHERE fecha_ingesta < datetime('now', '-30 days');`
  `DELETE FROM clusters WHERE fecha_creacion < datetime('now', '-30 days');`
* **Inmutabilidad de Salida:** El motor de IA tiene prohibido por prompt recuperar datos de autoría del texto original, asegurando que solo el resumen abstracto persista en la base de datos.

---

### 4. Consultas Críticas (ORM Pushdown)

Para evitar cargar dataframes completos en RAM, se prohíben los métodos `.to_pandas()` sobre tablas completas. Se utilizarán las siguientes operaciones directas de SQLAlchemy:

* **Query de Dashboard (Últimas 24hs):**
  `session.query(Cluster).filter(Cluster.fecha_creacion >= (datetime.utcnow() - timedelta(hours=24))).all()`
* **Query de Agregación Semanal:**
  `session.query(Cluster.palabra_clave, func.count(Cluster.id)).group_by(Cluster.palabra_clave).filter(Cluster.fecha_creacion >= (datetime.utcnow() - timedelta(days=7))).all()`

Este diseño asegura que solo los datos necesarios para la vista actual sean cargados en la memoria del proceso de Streamlit, manteniendo la escalabilidad del sistema hasta el límite de 50 usuarios concurrentes.

## User Flow
# USERFLOW: NEWS TREND ANALYZER (DEVELOPER PULSE EDITION)

## 1. INTRODUCCIÓN Y CICLO DE VIDA DEL USUARIO
El flujo de usuario está diseñado para minimizar el tiempo de "Time-to-Insight". El sistema opera bajo un modelo de carga asíncrona: el usuario no espera a que el sistema procese datos, sino que consume el estado persistente más reciente generado por los workers en background.

## 2. MAPA DE NAVEGACIÓN Y PUNTOS DE ACCESO
El usuario accede a una interfaz única dividida en tres zonas funcionales:

### ZONA A: Sidebar de Control (Filtros Globales)
*   **Selector de Rango Temporal:** Filtro de fecha para el Dashboard Analítico.
*   **Selector de Categorías:** Filtro multiselect para filtrar por áreas (ej. Ciberseguridad, Frameworks, Datos).
*   **Monitor de Estado:** Indicador visual (dot) que muestra el status de los últimos procesos ETL (ej. 🟢 Última actualización hace 45m).

### ZONA B: Dashboard Operativo (24 Horas)
*   **Elemento Principal:** Scatter Plot (Plotly) que muestra los clústers detectados en el último día.
*   **Interacción:** 
    1. El usuario hace hover sobre una burbuja (burbujas más grandes indican mayor impacto/score).
    2. Al hacer clic (callback), el sistema actualiza el estado de `st.session_state` con el ID del clúster seleccionado.
    3. El área de "Ficha de Evento" (debajo del gráfico) se refresca dinámicamente con los detalles del clúster, el sentimiento y los enlaces fuente.

### ZONA C: Dashboard Analítico (Macro-Tendencias)
*   **Elemento Principal:** Gráfico de líneas (Evolución de eventos) y Gráfico de dona (Sentimiento semanal).
*   **Interacción:** Al hacer clic en una sección del gráfico de dona, la lista de noticias inferior se filtra automáticamente para mostrar solo los eventos positivos, negativos o neutros.

## 3. DESCRIPCIÓN DE WIREFRAMES E INTERACCIONES

### 3.1. Estado Inicial (Dashboard "Clean Load")
Al cargar, el usuario recibe:
1. Header: "News Trend Analyzer" + Subtítulo técnico.
2. `st.metric` cards: Cantidad de repositorios nuevos, debates HN activos y posts técnicos en Reddit.
3. Gráfico de Dispersión centrado en `col_main`.
4. Panel de "Resumen Ejecutivo de la Semana" en `col_stats`.

### 3.2. Drill-Down Pattern (Detalle de Evento)
Cuando el usuario selecciona un punto del gráfico, se activa el `st.expander` de detalle:
*   **Header:** "[TIPO FUENTE] — Título del evento :badge[Área]"
*   **Cuerpo:** 
    *   `st.write` con el resumen generado por IA.
    *   `st.metric` (opcional) con el sentimiento detectado (ej. "Sentimiento: 🟢 Positivo").
    *   Enlaces (Links) con botón de estilo secundario: "🔗 Ver fuente original".

## 4. PATRONES DE INTERACCIÓN Y FEEDBACK (UX)

### 4.1. Carga de Datos (No bloqueante)
*   Se utiliza `st.status` para informar al usuario si se está forzando una actualización manual.
*   Mientras el proceso corre en el background, el usuario puede seguir navegando, filtrando y haciendo clic en elementos existentes.

### 4.2. Manejo de Fallbacks Visuales
*   Si el LLM no pudo generar un resumen, el contenedor muestra un `st.warning` nativo: "Resumen ejecutivo en curso de generación, por favor intente en unos minutos."
*   Si una API de origen (ej. Reddit) presenta un timeout, el sistema muestra un `st.error` compacto en la parte superior, permitiendo al usuario continuar viendo los datos de GitHub y Hacker News.

## 5. FLUJO LÓGICO DE DATOS (Background Pipeline)
1. **Trigger:** APScheduler despierta el worker.
2. **Ingesta:** Los scrapers extraen datos de APIs (Rate limiting controlado).
3. **NLP Pipeline:** 
    *   `spaCy` limpia metadatos (Privacidad by design: PII eliminado).
    *   `Sentence-transformers` genera embeddings locales.
    *   `Clustering` agrupa los items.
4. **IA Generativa:** Se consulta Gemini para cada clúster. Si la respuesta no es válida o Gemini no está configurado, el pipeline conserva el resumen como pendiente.
5. **Persistencia:** Se realiza el `INSERT` en SQLite mediante `SQLAlchemy`.
6. **UI Refresh:** El dashboard de Streamlit, que está conectado a la base de datos, refresca la vista en el siguiente tick del usuario (o mediante un auto-reloader suave).

## 6. REGLAS DE ORO DEL UI
1. **Cero CSS:** No se permite inyección de HTML custom; se utiliza el tema base "Dark" de Streamlit para mantener la consistencia.
2. **Prioridad de Espacio:** El gráfico de dispersión debe ocupar al menos el 60% de la altura de la pantalla en `col_main`.
3. **Escalabilidad de Lectura:** El uso de `st.expander` es obligatorio para evitar saturar al usuario con texto, manteniendo el "Dark Canvas" limpio.

## Styling Guidelines
# STYLING: Guía de Estilo y Sistema de Diseño - "newser"

## 1. Overview y Principios de Diseño
El News Trend Analyzer adopta una filosofía de "Panel de Control Operativo" de alta densidad. El diseño prioriza la claridad técnica, la legibilidad de datos y la eliminación de fricciones visuales.

Principios rectores:
- Flat Design: Prohibición estricta de sombras, gradientes, bordes redondeados excesivos o animaciones decorativas.
- Dark Canvas Mode: Interfaz oscura inmersiva por defecto para reducir la fatiga visual en entornos de alta carga de trabajo técnica.
- Prioridad de Contenido: El contenido generado por IA y las fuentes técnicas ocupan el protagonismo visual sobre los elementos decorativos.
- Arquitectura Nativa: Uso estricto de componentes de Streamlit (st.components). Prohibido el uso de CSS inyectado (`unsafe_allow_html=True`) que comprometa la responsividad.

## 2. Paleta de Colores (config.toml)
La identidad visual es inyectada globalmente mediante `config.toml`. No se permite el uso de colores hardcodeados en el código fuente.

Configuración obligatoria:
[theme]
base = "dark"
primaryColor = "#1A73E8"
font = "sans serif"

Paleta Semántica:
- Fondo Global: #0E1117 (Noche profunda)
- Superficies: #262730 (Gris oscuro para tarjetas)
- Texto Principal: #FAFAFA (Blanco alta visibilidad)
- Texto Mute: #A0AEC0 (Gris plata para metadatos)
- Acentos (Tech Blue): #1A73E8 (Botones y gráficos)

## 3. Layout y Grid System
El diseño debe maximizar el aprovechamiento de pantalla (Wide Mode).

- Configuración Global: `st.set_page_config(layout="wide")` es obligatorio en todas las vistas.
- Separación Lógica: Uso exclusivo de `st.divider()` para delimitar: Macro-Resumen IA, Dashboard Gráfico y Exploración de Noticias.
- Esquema Asimétrico: Se utilizará la proporción 2:1 para el panel central.
  - Columna Principal (2): Gráficos interactivos de tendencias.
  - Columna de Métricas (1): Estadísticas de sentimiento y deltas semanales.

## 4. Tipografía y Jerarquía
Se utiliza el motor de renderizado Markdown de Streamlit para asegurar consistencia.

- Títulos: `st.title()` para el nombre del producto, `st.caption()` para estados de pipeline.
- Subtítulos: `st.subheader()` para etiquetas de módulos (ej. "Narrativas de la Semana").
- Énfasis: Uso de negritas en nombres de fuentes: [GITHUB], [HACKER NEWS], [REDDIT].
- Badges: Uso de insignias nativas para áreas técnicas: `:blue-badge[{area}]` o `:gray-badge[...]`.

## 5. Anatomía de Componentes (Component Library)

5.1. Call-to-Actions (CTAs)
- Primary: `st.button("...", type="primary")` para acciones de ejecución (Tech Blue).
- Secondary: Botones con diseño outline para funciones de exportación.

5.2. Drill-Down Feed
Cada noticia se encapsula en `st.expander`.
- Header: `[FUENTE] — {titulo} :badge[...]`
- Body: Incluye "Resumen Ejecutivo (AI): {resumen}" y enlace directo "🔗 [Leer noticia completa ↗](url)".

5.3. Visualización de Datos
- Gráficos (Plotly): Uso estricto de `use_container_width=True`.
- Métricas: Uso del componente `st.metric(label, value, delta)` para indicadores de impacto.

## 6. Manejo de Errores y Fallbacks
Se prohíbe el texto plano para mensajes de estado.
- Error Crítico: `st.error("🚨 Mensaje claro")` para fallos de API.
- Dato Faltante: `st.warning("⚠️ Resumen automático no disponible")`.
- Feedback de Carga: Obligatorio el uso de `st.status` para procesos ETL en segundo plano.

## 7. Reglas de Engagement (Responsividad)
- No anidar contenedores: Prohibido colocar `st.expander` dentro de otro.
- Sidebar: Reservado exclusivamente para controles (filtros de fecha, selectores). Prohibido renderizar gráficos en la barra lateral.
- Consistencia: El diseño debe mantenerse "plano". La jerarquía visual se define exclusivamente por el espaciado y los divisores, nunca por sombras proyectadas.
