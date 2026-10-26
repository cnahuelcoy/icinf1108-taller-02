"""Pruebas aisladas del contrato HTTP y las transacciones de estudiantes.

Ejecutar: uv run pytest tests/test_students_sqlalchemy.py -q
No reemplazan las pruebas reales posteriores contra PostgreSQL.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.connection import get_db
from app.database.models import Base, PetModel, StudentModel
from app.main import create_app


@pytest.fixture
def client_and_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    app = create_app()

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        yield client, factory
    app.dependency_overrides.clear()
    engine.dispose()


def student_payload(**changes):
    payload = {
        "name": "Ana Pérez",
        "username": "ana_perez",
        "email": "ana@example.com",
        "age": 21,
    }
    payload.update(changes)
    return payload


def test_crud_and_http_envelope(client_and_session):
    client, factory = client_and_session
    created = client.post("/api/students", json=student_payload())
    assert created.status_code == 201
    body = created.json()
    assert body["code"] == 201 and body["success"] is True
    student_id = body["data"]["id"]

    listed = client.get("/api/students")
    assert listed.status_code == 200
    assert listed.json()["data"]["total"] == 1
    assert client.get(f"/api/students/{student_id}").status_code == 200

    updated = client.patch(
        f"/api/students/{student_id}", json={"name": "Ana María"}
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["name"] == "Ana María"

    # Una segunda sesión encuentra el dato persistido en la BD.
    with factory() as session:
        assert session.get(StudentModel, student_id).name == "Ana María"

    deleted = client.delete(f"/api/students/{student_id}")
    assert deleted.status_code == 200
    assert deleted.json()["data"]["id"] == student_id
    assert client.get(f"/api/students/{student_id}").status_code == 404


def test_unique_fields_and_validation(client_and_session):
    client, _ = client_and_session
    assert client.post("/api/students", json=student_payload()).status_code == 201

    same_email = client.post(
        "/api/students",
        json=student_payload(username="other_user"),
    )
    assert same_email.status_code == 409
    assert "email" in same_email.json()["errors"]

    same_username = client.post(
        "/api/students",
        json=student_payload(email="other@example.com"),
    )
    assert same_username.status_code == 409
    assert "username" in same_username.json()["errors"]

    invalid = client.post("/api/students", json=student_payload(age=17))
    assert invalid.status_code == 400
    assert invalid.json()["success"] is False


def test_nested_pets_one_transaction_and_rollback(client_and_session):
    client, factory = client_and_session
    payload = student_payload(
        pets=[
            {"name": "Michi", "species": "gato"},
            {"name": "Firulais", "species": "perro"},
        ]
    )
    created = client.post("/api/students", json=payload)
    assert created.status_code == 201
    student_id = created.json()["data"]["id"]
    with factory() as session:
        pets = session.scalars(
            select(PetModel).where(PetModel.studentId == student_id)
        ).all()
        assert len(pets) == 2

    duplicate = client.post(
        "/api/students",
        json=student_payload(
            username="otra_persona",
            email="otra@example.com",
            pets=[
                {"name": "Michi", "species": "gato"},
                {"name": "Michi", "species": "gato"},
            ],
        ),
    )
    assert duplicate.status_code == 409
    with factory() as session:
        assert session.scalar(
            select(StudentModel).where(StudentModel.username == "otra_persona")
        ) is None

    deleted = client.delete(f"/api/students/{student_id}")
    assert deleted.status_code == 200
    with factory() as session:
        assert not session.scalars(
            select(PetModel).where(PetModel.studentId == student_id)
        ).all()
