
import logging

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.database.connection import get_engine

logger = logging.getLogger(__name__)


def check_connection() -> bool:
    """Comprueba la conexión con PostgreSQL."""
    try:
        engine = get_engine()

        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            return result.scalar_one() == 1

    except (SQLAlchemyError, OSError, RuntimeError):
        logger.error("No fue posible establecer conexión con PostgreSQL.")
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    if check_connection():
        print("Conexión con PostgreSQL exitosa.")
    else:
        print("No se pudo conectar con PostgreSQL.")
