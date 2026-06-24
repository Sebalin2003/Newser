# =============================================================================
# src/database.py
# =============================================================================
"""
Módulo de base de datos.

Responsabilidades:
- Definir los modelos ORM: Noticia, Tendencia, Cluster, MacroResumen.
- Gestionar el engine SQLite y las sesiones.
- Proveer migrar_schema() para migraciones aditivas sin pérdida de datos.
- Exponer get_session() como context manager con commit/rollback automático.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import date, datetime
from typing import Generator

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
DATABASE_URL: str = "sqlite:///news_analyzer.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,  # evita DetachedInstanceError
)


# ---------------------------------------------------------------------------
# Base declarativa
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Modelo: Noticia
# ---------------------------------------------------------------------------
class Noticia(Base):
    """
    Noticia individual ingerida desde un feed RSS.

    Columnas nuevas (v2.0):
        cluster_id:     FK soft a clusters.id (nullable, sin enforcement).
        entidades_json: JSON list[str] de entidades ORG/PRODUCT extraídas por spaCy.
    """

    __tablename__ = "noticias"

    id: str = Column(String(64), primary_key=True, index=True)
    titulo: str = Column(String(512), nullable=False)
    url: str = Column(Text, nullable=False)
    discussion_url: str = Column(Text, nullable=True)
    fuente: str = Column(String(128), nullable=False)
    fecha_publicacion: datetime = Column(DateTime, nullable=True)
    descripcion_original: str = Column(Text, nullable=True)
    resumen_ia: str = Column(Text, nullable=True, default="Resumen no disponible")
    area_matcheada: str = Column(String(128), nullable=True)
    fecha_ingesta: datetime = Column(DateTime, nullable=False, default=datetime.utcnow)
    # v2.0 — nullable para compatibilidad con datos existentes
    cluster_id: int = Column(Integer, nullable=True, index=True)
    entidades_json: str = Column(Text, nullable=True)
    sentimiento: str = Column(String(32), nullable=True, default="neutral")
    ranking: int = Column(Integer, nullable=True)  # posición en la fuente original (1-based)
    num_comentarios: int = Column(Integer, nullable=True)
    score: int = Column(Integer, nullable=True)
    selected_score: float = Column(Float, nullable=True)
    score_components_json: str = Column(Text, nullable=True)
    tags_json: str = Column(Text, nullable=True)
    selection_reason: str = Column(Text, nullable=True)
    scored_at: datetime = Column(DateTime, nullable=True)
    score_version: str = Column(String(64), nullable=True)

    def __repr__(self) -> str:
        return f"<Noticia id={self.id[:8]}... titulo='{self.titulo[:40]}'>"


# ---------------------------------------------------------------------------
# Modelo: Tendencia
# ---------------------------------------------------------------------------
class Tendencia(Base):
    """Top N términos NLP calculados desde todos los títulos en DB."""

    __tablename__ = "tendencias"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    palabra: str = Column(String(128), nullable=False, index=True)
    frecuencia: int = Column(Integer, nullable=False, default=0)
    fecha_analisis: datetime = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<Tendencia palabra='{self.palabra}' frecuencia={self.frecuencia}>"


# ---------------------------------------------------------------------------
# Modelo: Cluster (v2.0)
# ---------------------------------------------------------------------------
class Cluster(Base):
    """
    Grupo de noticias similares (evento multi-fuente) generado por clustering TF-IDF.

    Atributos:
        titulo_representativo:  Título de la noticia con mayor densidad de keywords.
        fecha_cluster:          Día de creación (Date, para query diaria).
        score:                  Score de relevancia: decay × autoridad × volumen.
        n_noticias:             Total de artículos en el clúster.
        n_fuentes:              Número de fuentes únicas en el clúster.
        area:                   Área temática dominante.
        entidades_json:         JSON list[str] de entidades combinadas del clúster.
        fecha_creacion:         Timestamp de proceso.
    """

    __tablename__ = "clusters"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    titulo_representativo: str = Column(String(512), nullable=False)
    fecha_cluster: date = Column(Date, nullable=False, index=True)
    score: float = Column(Float, nullable=False, default=0.0)
    n_noticias: int = Column(Integer, nullable=False, default=1)
    n_fuentes: int = Column(Integer, nullable=False, default=1)
    area: str = Column(String(128), nullable=True)
    entidades_json: str = Column(Text, nullable=True)
    fecha_creacion: datetime = Column(DateTime, nullable=False, default=datetime.utcnow)
    sentimiento: str = Column(String(32), nullable=True, default="neutral")

    def __repr__(self) -> str:
        return (
            f"<Cluster id={self.id} area='{self.area}' "
            f"score={self.score:.3f} n={self.n_noticias}>"
        )


# ---------------------------------------------------------------------------
# Modelo: MacroResumen (v2.0)
# ---------------------------------------------------------------------------
class MacroResumen(Base):
    """
    Resumen ejecutivo diario generado por Gemini (pre-calculado en backend).

    Un único registro por día (unique constraint en fecha).
    Si hay < 3 noticias en el día, se guarda un string de fallback sin llamar a la API.
    """

    __tablename__ = "macro_resumenes"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    fecha: date = Column(Date, nullable=False, unique=True, index=True)
    texto: str = Column(Text, nullable=False)
    n_noticias: int = Column(Integer, nullable=False, default=0)
    n_clusters: int = Column(Integer, nullable=False, default=0)
    modelo: str = Column(String(64), nullable=True)
    brief_json: str = Column(Text, nullable=True)
    fecha_generacion: datetime = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<MacroResumen fecha={self.fecha} n_noticias={self.n_noticias}>"


# ---------------------------------------------------------------------------
# Inicialización y migración
# ---------------------------------------------------------------------------
def init_db() -> None:
    """
    Inicializa la base de datos aplicando la migración de schema.
    Idempotente: puede llamarse múltiples veces sin efectos secundarios.
    """
    migrar_schema()


def limpiar_datos_antiguos(dias_retencion: int = 30) -> dict[str, int]:
    """
    Elimina registros de noticias y clústers con más de `dias_retencion` días de antigüedad.

    Implementa la política de privacidad (GDPR / Ley 25.326) y optimización de espacio.
    Se ejecuta automáticamente en init_db().

    Returns:
        dict con la cantidad de filas eliminadas por tabla.
    """
    resultado = {"noticias_eliminadas": 0, "clusters_eliminados": 0}
    try:
        with engine.begin() as conn:
            r1 = conn.execute(
                text(f"DELETE FROM noticias WHERE fecha_ingesta < datetime('now', '-{dias_retencion} days')")
            )
            resultado["noticias_eliminadas"] = r1.rowcount

            r2 = conn.execute(
                text(f"DELETE FROM clusters WHERE fecha_creacion < datetime('now', '-{dias_retencion} days')")
            )
            resultado["clusters_eliminados"] = r2.rowcount

        if resultado["noticias_eliminadas"] or resultado["clusters_eliminados"]:
            logger.info(
                "Limpieza de retención (%dd): %d noticia(s) y %d clúster(s) eliminados.",
                dias_retencion,
                resultado["noticias_eliminadas"],
                resultado["clusters_eliminados"],
            )
    except Exception as exc:
        logger.warning("Error al limpiar datos antiguos: %s", exc)

    return resultado


def migrar_schema() -> None:
    """
    Migración conservadora del schema SQLite.

    - Crea las tablas nuevas (clusters, macro_resumenes) si no existen.
    - Agrega columnas nuevas a la tabla 'noticias' sin destruir datos existentes.
    - Idempotente: detecta columnas existentes antes de ejecutar ALTER TABLE.
    """
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    # Agregar columnas v2.0 a tabla 'noticias' si ya existe
    if "noticias" in existing_tables:
        existing_cols = {col["name"] for col in inspector.get_columns("noticias")}

        nuevas_columnas = {
            "discussion_url": "ALTER TABLE noticias ADD COLUMN discussion_url TEXT",
            "cluster_id":    "ALTER TABLE noticias ADD COLUMN cluster_id INTEGER",
            "entidades_json": "ALTER TABLE noticias ADD COLUMN entidades_json TEXT",
            "sentimiento":    "ALTER TABLE noticias ADD COLUMN sentimiento VARCHAR(32) DEFAULT 'neutral'",
            "ranking":        "ALTER TABLE noticias ADD COLUMN ranking INTEGER",
            "num_comentarios": "ALTER TABLE noticias ADD COLUMN num_comentarios INTEGER",
            "score":          "ALTER TABLE noticias ADD COLUMN score INTEGER",
            "selected_score": "ALTER TABLE noticias ADD COLUMN selected_score FLOAT",
            "score_components_json": "ALTER TABLE noticias ADD COLUMN score_components_json TEXT",
            "tags_json": "ALTER TABLE noticias ADD COLUMN tags_json TEXT",
            "selection_reason": "ALTER TABLE noticias ADD COLUMN selection_reason TEXT",
            "scored_at": "ALTER TABLE noticias ADD COLUMN scored_at DATETIME",
            "score_version": "ALTER TABLE noticias ADD COLUMN score_version VARCHAR(64)",
        }

        with engine.begin() as conn:
            for col_name, ddl in nuevas_columnas.items():
                if col_name not in existing_cols:
                    try:
                        conn.execute(text(ddl))
                        logger.info("Columna '%s' agregada a tabla 'noticias'.", col_name)
                    except Exception as exc:
                        logger.warning("No se pudo agregar '%s' a 'noticias': %s", col_name, exc)

    if "clusters" in existing_tables:
        existing_cols_cl = {col["name"] for col in inspector.get_columns("clusters")}
        
        nuevas_columnas_cl = {
            "sentimiento": "ALTER TABLE clusters ADD COLUMN sentimiento VARCHAR(32) DEFAULT 'neutral'",
        }
        with engine.begin() as conn:
            for col_name, ddl in nuevas_columnas_cl.items():
                if col_name not in existing_cols_cl:
                    try:
                        conn.execute(text(ddl))
                        logger.info("Columna '%s' agregada a tabla 'clusters'.", col_name)
                    except Exception as exc:
                        logger.warning("No se pudo agregar '%s' a 'clusters': %s", col_name, exc)

    if "macro_resumenes" in existing_tables:
        existing_cols_mr = {col["name"] for col in inspector.get_columns("macro_resumenes")}

        nuevas_columnas_mr = {
            "brief_json": "ALTER TABLE macro_resumenes ADD COLUMN brief_json TEXT",
        }
        with engine.begin() as conn:
            for col_name, ddl in nuevas_columnas_mr.items():
                if col_name not in existing_cols_mr:
                    try:
                        conn.execute(text(ddl))
                        logger.info("Columna '%s' agregada a tabla 'macro_resumenes'.", col_name)
                    except Exception as exc:
                        logger.warning("No se pudo agregar '%s' a 'macro_resumenes': %s", col_name, exc)

    # Crear todas las tablas nuevas (Cluster, MacroResumen) si no existen
    Base.metadata.create_all(bind=engine)
    logger.info("Schema migrado correctamente — versión 2.0.")


# ---------------------------------------------------------------------------
# Context Manager de sesión
# ---------------------------------------------------------------------------
@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Provee una sesión con commit automático al salir y rollback ante error.

    Uso:
        with get_session() as session:
            session.add(mi_objeto)
    """
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error("Error en sesión DB, rollback aplicado: %s", exc)
        raise
    finally:
        session.close()
