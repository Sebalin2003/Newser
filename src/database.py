# =============================================================================
# src/database.py
# =============================================================================
"""
Módulo de base de datos.

Responsabilidades:
- Definir los modelos ORM: Noticia, Tendencia, Cluster, MacroResumen.
- Gestionar el engine SQLAlchemy y las sesiones.
- Proveer migrar_schema() para migraciones aditivas sin pérdida de datos.
- Exponer get_session() como context manager con commit/rollback automático.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Generator

from dotenv import load_dotenv
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
load_dotenv()


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
DEFAULT_DATABASE_URL = "sqlite:///news_analyzer.db"


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        return "postgresql+psycopg://" + database_url.removeprefix("postgres://")
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url.removeprefix("postgresql://")
    return database_url


DATABASE_URL: str = normalize_database_url(
    os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL).strip() or DEFAULT_DATABASE_URL
)


def is_sqlite_url(database_url: str = DATABASE_URL) -> bool:
    return database_url.startswith("sqlite")


def engine_kwargs(database_url: str = DATABASE_URL) -> dict:
    kwargs: dict = {"echo": False}
    if is_sqlite_url(database_url):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_pre_ping"] = True
    return kwargs


engine = create_engine(DATABASE_URL, **engine_kwargs(DATABASE_URL))

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
    resumen_ia_en: str = Column(Text, nullable=True)
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
    is_favorite: int = Column(Integer, nullable=False, default=0)
    favorited_at: datetime = Column(DateTime, nullable=True)
    media_url: str = Column(Text, nullable=True)
    media_type: str = Column(String(16), nullable=True)
    media_source_url: str = Column(Text, nullable=True)
    github_total_stars: int = Column(Integer, nullable=True)
    github_stars_period: int = Column(Integer, nullable=True)
    github_period_label: str = Column(String(32), nullable=True)
    github_metrics_updated_at: datetime = Column(DateTime, nullable=True)
    github_fresh_date: date = Column(Date, nullable=True)

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
# Modelo: DynamicKeyword
# ---------------------------------------------------------------------------
class DynamicKeyword(Base):
    """Runtime-learned emerging keyword used as a guarded scoring boost."""

    __tablename__ = "dynamic_keywords"

    term: str = Column(String(128), primary_key=True, index=True)
    frequency: int = Column(Integer, nullable=False, default=0)
    source_count: int = Column(Integer, nullable=False, default=0)
    momentum_score: float = Column(Float, nullable=False, default=0.0)
    is_active: int = Column(Integer, nullable=False, default=1)
    first_seen_at: datetime = Column(DateTime, nullable=True)
    last_seen_at: datetime = Column(DateTime, nullable=True)
    updated_at: datetime = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<DynamicKeyword term='{self.term}' momentum={self.momentum_score:.2f}>"


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
    texto_en: str = Column(Text, nullable=True)
    brief_json_en: str = Column(Text, nullable=True)
    modelo_en: str = Column(String(64), nullable=True)
    fecha_generacion_en: datetime = Column(DateTime, nullable=True)

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
    cutoff = (datetime.now(timezone.utc) - timedelta(days=dias_retencion)).replace(tzinfo=None)
    try:
        with engine.begin() as conn:
            r1 = conn.execute(
                text(
                    "DELETE FROM noticias "
                    "WHERE fecha_ingesta < :cutoff "
                    "AND COALESCE(is_favorite, 0) = 0"
                ),
                {"cutoff": cutoff},
            )
            resultado["noticias_eliminadas"] = r1.rowcount

            r2 = conn.execute(
                text("DELETE FROM clusters WHERE fecha_creacion < :cutoff"),
                {"cutoff": cutoff},
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


def _add_missing_columns(table_name: str, existing_cols: set[str], columns: dict[str, str]) -> None:
    with engine.begin() as conn:
        for col_name, column_sql in columns.items():
            if col_name not in existing_cols:
                try:
                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}"))
                    logger.info("Columna '%s' agregada a tabla '%s'.", col_name, table_name)
                except Exception as exc:
                    logger.warning("No se pudo agregar '%s' a '%s': %s", col_name, table_name, exc)


def migrar_schema() -> None:
    """
    Migración conservadora del schema.

    - Crea las tablas nuevas (clusters, macro_resumenes) si no existen.
    - En SQLite, agrega columnas nuevas sin destruir datos existentes.
    - Idempotente: detecta columnas existentes antes de ejecutar ALTER TABLE.
    """
    sqlite = is_sqlite_url()
    datetime_type = "DATETIME" if sqlite else "TIMESTAMP"
    float_type = "FLOAT" if sqlite else "DOUBLE PRECISION"

    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    # Agregar columnas v2.0 a tabla 'noticias' si ya existe
    if "noticias" in existing_tables:
        existing_cols = {col["name"] for col in inspector.get_columns("noticias")}

        nuevas_columnas = {
            "discussion_url": "discussion_url TEXT",
            "cluster_id": "cluster_id INTEGER",
            "entidades_json": "entidades_json TEXT",
            "sentimiento": "sentimiento VARCHAR(32) DEFAULT 'neutral'",
            "ranking": "ranking INTEGER",
            "num_comentarios": "num_comentarios INTEGER",
            "score": "score INTEGER",
            "selected_score": f"selected_score {float_type}",
            "score_components_json": "score_components_json TEXT",
            "tags_json": "tags_json TEXT",
            "selection_reason": "selection_reason TEXT",
            "scored_at": f"scored_at {datetime_type}",
            "score_version": "score_version VARCHAR(64)",
            "is_favorite": "is_favorite INTEGER NOT NULL DEFAULT 0",
            "favorited_at": f"favorited_at {datetime_type}",
            "media_url": "media_url TEXT",
            "media_type": "media_type VARCHAR(16)",
            "media_source_url": "media_source_url TEXT",
            "resumen_ia_en": "resumen_ia_en TEXT",
            "github_total_stars": "github_total_stars INTEGER",
            "github_stars_period": "github_stars_period INTEGER",
            "github_period_label": "github_period_label VARCHAR(32)",
            "github_metrics_updated_at": f"github_metrics_updated_at {datetime_type}",
            "github_fresh_date": "github_fresh_date DATE",
        }

        _add_missing_columns("noticias", existing_cols, nuevas_columnas)

    if "clusters" in existing_tables:
        existing_cols_cl = {col["name"] for col in inspector.get_columns("clusters")}
        
        nuevas_columnas_cl = {
            "sentimiento": "sentimiento VARCHAR(32) DEFAULT 'neutral'",
        }
        _add_missing_columns("clusters", existing_cols_cl, nuevas_columnas_cl)

    if "macro_resumenes" in existing_tables:
        existing_cols_mr = {col["name"] for col in inspector.get_columns("macro_resumenes")}

        nuevas_columnas_mr = {
            "brief_json": "brief_json TEXT",
            "texto_en": "texto_en TEXT",
            "brief_json_en": "brief_json_en TEXT",
            "modelo_en": "modelo_en VARCHAR(64)",
            "fecha_generacion_en": f"fecha_generacion_en {datetime_type}",
        }
        _add_missing_columns("macro_resumenes", existing_cols_mr, nuevas_columnas_mr)

    # Crear todas las tablas nuevas (Cluster, MacroResumen) si no existen
    if not sqlite:
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_noticias_search_fts "
                "ON noticias USING GIN (to_tsvector('simple', "
                "coalesce(titulo, '') || ' ' || coalesce(descripcion_original, '')))"
            ))
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
