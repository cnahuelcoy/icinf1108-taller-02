from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.pets.pets_repository import PetsRepository
from app.pets.pets_schemas import CreatePetDto, Pet, PetList, UpdatePetDto
from app.pets.pets_service import PetsService
from app.shared.exceptions import conflict

router = APIRouter(
    prefix="/api/students/{studentId}/pets",
    tags=["Pets"],
)


def get_pets_service(db: Annotated[Session, Depends(get_db)]) -> PetsService:
    return PetsService(PetsRepository(db))


PetsServiceDependency = Annotated[PetsService, Depends(get_pets_service)]


@contextmanager
def _pet_transaction(db: Session) -> Iterator[None]:
    """Confirmar la escritura completa o deshacerla antes de responder."""
    try:
        with db.begin():
            yield
    except IntegrityError as exc:
        diagnostic = getattr(exc.orig, "diag", None)
        constraint = getattr(diagnostic, "constraint_name", None)

        if constraint == "uq_pets_student_name":
            raise conflict(
                {"name": {"message": "Ya tienes una mascota con ese nombre"}}
            ) from exc

        if constraint == "pets_student_id_fkey":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Estudiante no encontrado",
            ) from exc

        raise


@router.get("")
def find_all(studentId: str, service: PetsServiceDependency) -> PetList:
    return service.find_all_for_student(studentId)


@router.post("", status_code=201)
def create(studentId: str, body: CreatePetDto, service: PetsServiceDependency) -> Pet:
    with _pet_transaction(service.repository.session):
        return service.create(studentId, body)


@router.patch("/{petId}")
def update(
    studentId: str,
    petId: str,
    body: UpdatePetDto,
    service: PetsServiceDependency,
) -> Pet:
    with _pet_transaction(service.repository.session):
        return service.update(studentId, petId, body)


@router.delete("/{petId}")
def delete(studentId: str, petId: str, service: PetsServiceDependency) -> Pet:
    with _pet_transaction(service.repository.session):
        return service.delete(studentId, petId)
