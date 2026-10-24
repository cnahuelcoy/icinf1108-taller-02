
import os
from collections.abc import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


# Cargar variables del archivo .env durante el desarrollo local.
load_dotenv()


def get_database_url() -> str:
    """Obtener la URL de conexión desde las variables de entorno."""
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "La variable de entorno DATABASE_URL no está configurada."
        )

    if not database_url.startswith("postgresql+psycopg://"):
        raise RuntimeError(
            "DATABASE_URL debe utilizar el controlador postgresql+psycopg."
        )

    return database_url



def create_db_engine() -> Engine:
    """Crear el motor de conexión a PostgreSQL."""
    return create_engine(
        get_database_url(),
        pool_pre_ping=True,
        pool_recycle=1800,
        hide_parameters=True,
        connect_args={"connect_timeout": 5},
    )



# Motor creado de forma diferida para permitir importar el módulo
# sin necesitar PostgreSQL disponible inmediatamente.
_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Obtener el motor compartido de SQLAlchemy."""
    global _engine

    if _engine is None:
        _engine = create_db_engine()

    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Obtener la fábrica de sesiones de SQLAlchemy."""
    global _session_factory

    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            expire_on_commit=False,
        )

    return _session_factory


def get_db() -> Generator[Session, None, None]:
    """Proporcionar una sesión y cerrarla al terminar."""
    session = get_session_factory()()

    try:
        yield session
    finally:
        session.close()
