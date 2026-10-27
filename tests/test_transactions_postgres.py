"""Pruebas de transacciones entre Students y Pets contra PostgreSQL.

Se ejecutan sobre una base de pruebas aislada (por defecto, la base de
DATABASE_URL con el sufijo ``_test``, por ejemplo ``students_pets_test``).
Nunca sobre la base de desarrollo: si el nombre no termina en ``_test``,
las pruebas se detienen.

Preparación (una sola vez) y ejecución: ver la sección
"Pruebas de persistencia y transacciones" del README.

    uv run pytest tests/test_transactions_postgres.py -v
"""

import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

import app.students.students_service as students_service_module
from app.database.connection import get_db
from app.database.models import PetModel, StudentModel
from app.main import create_app
from app.pets.pets_schemas import CreatePetDto
from app.students.students_repository import StudentsRepository
from app.students.students_schemas import CreateStudentDto
from app.students.students_service import StudentsService

pytestmark = pytest.mark.postgres


# ---------------------------------------------------------------------------
# Base de datos de pruebas aislada
# ---------------------------------------------------------------------------


def _test_database_url() -> str:
    """Obtener la URL de la base de pruebas sin tocar la de desarrollo."""
    load_dotenv()
    explicit = os.getenv("TEST_DATABASE_URL")
    if explicit:
        url = make_url(explicit)
    else:
        base = os.getenv("DATABASE_URL")
        if not base:
            pytest.skip("No hay DATABASE_URL ni TEST_DATABASE_URL configuradas.")
        url = make_url(base)
        url = url.set(database=f"{url.database}_test")

    if not (url.database or "").endswith("_test"):
        pytest.exit(
            "Por seguridad, la base de pruebas debe terminar en '_test' "
            f"(se recibió '{url.database}').",
            returncode=2,
        )
    return url.render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    url = _test_database_url()
    test_engine = create_engine(url, hide_parameters=True)
    try:
        with test_engine.connect():
            pass
    except OperationalError:
        test_engine.dispose()
        pytest.skip(
            "No se pudo conectar a la base de pruebas. Inicia Docker "
            "(docker compose up -d) y crea students_pets_test (ver README)."
        )

    tables = set(inspect(test_engine).get_table_names())
    if not {"students", "pets"} <= tables:
        test_engine.dispose()
        pytest.fail(
            "La base de pruebas no tiene las tablas students y pets. "
            "Aplica las migraciones con Alembic sobre students_pets_test."
        )

    yield test_engine
    test_engine.dispose()


@pytest.fixture
def factory(engine: Engine) -> Iterator[sessionmaker[Session]]:
    """Fábrica de sesiones con la base vacía al iniciar cada prueba."""
    with engine.begin() as connection:
        connection.execute(
            text("TRUNCATE TABLE pets, students RESTART IDENTITY CASCADE")
        )
    yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def client(factory: sessionmaker[Session]) -> Iterator[TestClient]:
    app = create_app()

    def override_get_db() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def student_payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "Ana Pérez",
        "username": "ana_perez",
        "email": "ana@example.com",
        "age": 21,
    }
    payload.update(changes)
    return payload


def count_rows(factory: sessionmaker[Session]) -> tuple[int, int]:
    """Contar estudiantes y mascotas desde una sesión nueva e independiente."""
    with factory() as session:
        students = session.scalar(select(func.count()).select_from(StudentModel))
        pets = session.scalar(select(func.count()).select_from(PetModel))
    return students or 0, pets or 0


def count_orphan_pets(factory: sessionmaker[Session]) -> int:
    """Mascotas cuyo student_id no existe en students."""
    with factory() as session:
        return (
            session.scalar(
                text(
                    "SELECT count(*) FROM pets p "
                    "LEFT JOIN students s ON s.id = p.student_id "
                    "WHERE s.id IS NULL"
                )
            )
            or 0
        )


# ---------------------------------------------------------------------------
# Creación de estudiante con mascotas
# ---------------------------------------------------------------------------


def test_create_student_with_pets_commits_everything(client, factory):
    """Transacción exitosa: el estudiante y sus mascotas quedan guardados juntos."""
    response = client.post(
        "/api/students",
        json=student_payload(
            pets=[
                {"name": "Michi", "species": "gato", "age": 3},
                {"name": "Firulais", "species": "perro"},
            ]
        ),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["code"] == 201 and body["success"] is True
    student_id = body["data"]["id"]

    # Una sesión distinta lee lo que quedó confirmado (commit) en PostgreSQL.
    with factory() as session:
        student = session.get(StudentModel, student_id)
        assert student is not None
        assert sorted(pet.name for pet in student.pets) == ["Firulais", "Michi"]
        assert all(pet.studentId == student_id for pet in student.pets)

    assert count_rows(factory) == (1, 2)
    assert count_orphan_pets(factory) == 0


def test_rollback_when_pets_are_duplicated_in_request(client, factory):
    """Transacción fallida por regla de negocio: no queda el estudiante."""
    response = client.post(
        "/api/students",
        json=student_payload(
            pets=[
                {"name": "Michi", "species": "gato"},
                {"name": "Michi", "species": "gato"},
            ]
        ),
    )

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == 409 and body["success"] is False
    assert count_rows(factory) == (0, 0)


def test_rollback_when_database_rejects_a_pet(factory):
    """Error intencional en PostgreSQL al insertar una mascota.

    Se omite la validación de Pydantic para enviar una edad que viola la
    restricción CHECK ck_pets_age. El estudiante ya se había enviado a la
    base (flush), por lo que la prueba demuestra un rollback real.
    """
    invalid_pet = CreatePetDto.model_construct(name="Rex", species="perro", age=150)
    data = CreateStudentDto.model_construct(
        name="Ana Pérez",
        username="ana_perez",
        email="ana@example.com",
        age=21,
        pets=[CreatePetDto(name="Michi", species="gato"), invalid_pet],
    )

    with factory() as session:
        with pytest.raises(IntegrityError) as error:
            StudentsService(session).create(data)

    assert "ck_pets_age" in str(error.value.orig)
    assert count_rows(factory) == (0, 0)
    assert count_orphan_pets(factory) == 0


def test_rollback_when_second_pet_fails_after_first_was_flushed(factory, monkeypatch):
    """Error intencional a mitad de la transacción (clave primaria repetida).

    Se fuerza que dos mascotas reciban el mismo id. Para entonces el
    estudiante y la primera mascota ya se enviaron a PostgreSQL; nada debe
    quedar guardado.
    """
    student_id = str(uuid4())
    repeated_pet_id = str(uuid4())
    ids = iter([student_id, repeated_pet_id, repeated_pet_id])
    monkeypatch.setattr(students_service_module, "uuid4", lambda: next(ids))

    data = CreateStudentDto(
        **student_payload(
            pets=[
                {"name": "Michi", "species": "gato"},
                {"name": "Firulais", "species": "perro"},
            ]
        )
    )

    with factory() as session:
        with pytest.raises(IntegrityError):
            StudentsService(session).create(data)

    with factory() as session:
        assert session.get(StudentModel, student_id) is None
        assert session.get(PetModel, repeated_pet_id) is None
    assert count_rows(factory) == (0, 0)


def test_failed_request_does_not_affect_existing_data(client, factory):
    """Un rollback solo deshace su propia transacción."""
    first = client.post(
        "/api/students",
        json=student_payload(pets=[{"name": "Michi", "species": "gato"}]),
    )
    assert first.status_code == 201

    failed = client.post(
        "/api/students",
        json=student_payload(
            username="otra_persona",
            email="otra@example.com",
            pets=[
                {"name": "Toby", "species": "perro"},
                {"name": "Toby", "species": "perro"},
            ],
        ),
    )
    assert failed.status_code == 409
    assert count_rows(factory) == (1, 1)


# ---------------------------------------------------------------------------
# Eliminación de estudiante con mascotas
# ---------------------------------------------------------------------------


def test_delete_student_removes_its_pets_and_keeps_others(client, factory):
    """Transacción exitosa de eliminación, sin mascotas huérfanas."""
    target = client.post(
        "/api/students",
        json=student_payload(
            pets=[
                {"name": "Michi", "species": "gato"},
                {"name": "Firulais", "species": "perro"},
            ]
        ),
    ).json()["data"]["id"]
    other = client.post(
        "/api/students",
        json=student_payload(
            username="otra_persona",
            email="otra@example.com",
            pets=[{"name": "Luna", "species": "gato"}],
        ),
    ).json()["data"]["id"]
    assert count_rows(factory) == (2, 3)

    response = client.delete(f"/api/students/{target}")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True and body["data"]["id"] == target
    with factory() as session:
        assert session.get(StudentModel, target) is None
        remaining = session.scalars(select(PetModel)).all()
        assert [(pet.name, pet.studentId) for pet in remaining] == [("Luna", other)]
    assert count_orphan_pets(factory) == 0


def test_rollback_when_delete_fails_keeps_student_and_pets(
    client, factory, monkeypatch
):
    """Error intencional después de borrar: el estudiante y sus mascotas vuelven."""
    student_id = client.post(
        "/api/students",
        json=student_payload(
            pets=[
                {"name": "Michi", "species": "gato"},
                {"name": "Firulais", "species": "perro"},
            ]
        ),
    ).json()["data"]["id"]

    original_delete = StudentsRepository.delete

    def delete_then_fail(self, student):
        original_delete(self, student)  # El DELETE ya se envió a PostgreSQL.
        raise RuntimeError("Fallo intencional después de eliminar")

    monkeypatch.setattr(StudentsRepository, "delete", delete_then_fail)

    response = client.delete(f"/api/students/{student_id}")

    assert response.status_code == 500
    assert response.json()["success"] is False
    with factory() as session:
        student = session.get(StudentModel, student_id)
        assert student is not None
        assert len(student.pets) == 2
    assert count_rows(factory) == (1, 2)


# ---------------------------------------------------------------------------
# Integridad de las relaciones en la base de datos
# ---------------------------------------------------------------------------


def test_database_rejects_pet_without_existing_student(factory):
    """La clave foránea impide crear mascotas huérfanas."""
    with factory() as session:
        session.add(
            PetModel(
                id=str(uuid4()), studentId=str(uuid4()), name="Rex", species="perro"
            )
        )
        with pytest.raises(IntegrityError) as error:
            session.commit()

    assert getattr(error.value.orig, "sqlstate", None) == "23503"
    assert count_rows(factory) == (0, 0)


def test_database_cascade_deletes_pets_outside_the_orm(client, factory):
    """ON DELETE CASCADE también protege si se borra directamente en SQL."""
    student_id = client.post(
        "/api/students",
        json=student_payload(pets=[{"name": "Michi", "species": "gato"}]),
    ).json()["data"]["id"]

    with factory() as session, session.begin():
        session.execute(text("DELETE FROM students WHERE id = :id"), {"id": student_id})

    assert count_rows(factory) == (0, 0)
    assert count_orphan_pets(factory) == 0
