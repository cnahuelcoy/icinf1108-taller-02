from uuid import uuid4

from fastapi import HTTPException, status

from app.database.models import PetModel
from app.pets.pets_repository import PetsRepository
from app.pets.pets_schemas import CreatePetDto, Pet, PetList, UpdatePetDto
from app.shared.datetimes import utc_now
from app.shared.exceptions import conflict


class PetsService:
    def __init__(self, repository: PetsRepository) -> None:
        self.repository = repository

    def find_all_for_student(self, student_id: str) -> PetList:
        self.assert_student_exists(student_id)

        pets = self.repository.find_all_by_student(student_id)

        return PetList(
            total=len(pets),
            items=[Pet.model_validate(pet) for pet in pets],
        )

    def create(self, student_id: str, data: CreatePetDto) -> Pet:
        self.assert_student_exists(student_id)
        self.assert_no_conflicts(student_id, data)

        now = utc_now()
        pet = PetModel(
            id=str(uuid4()),
            studentId=student_id,
            name=data.name,
            species=data.species,
            age=data.age,
            createdAt=now,
            updatedAt=now,
        )

        saved = self.repository.save(pet)

        return Pet.model_validate(saved)

    def update(
        self,
        student_id: str,
        pet_id: str,
        data: UpdatePetDto,
    ) -> Pet:
        existing = self.find_owned(student_id, pet_id)
        self.assert_no_conflicts(student_id, data, except_id=pet_id)

        for field, value in data.model_dump(exclude_none=True).items():
            setattr(existing, field, value)

        existing.updatedAt = utc_now()
        saved = self.repository.save(existing)

        return Pet.model_validate(saved)

    def delete(self, student_id: str, pet_id: str) -> Pet:
        existing = self.find_owned(student_id, pet_id)
        response = Pet.model_validate(existing)

        self.repository.delete(pet_id)

        return response

    def delete_all_for_student(self, student_id: str) -> None:
        self.repository.delete_by_student(student_id)

    def find_owned(self, student_id: str, pet_id: str) -> PetModel:
        self.assert_student_exists(student_id)

        pet = self.repository.find_by_id(pet_id)

        if pet is None or pet.studentId != student_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Mascota no encontrada",
            )

        return pet

    def assert_student_exists(self, student_id: str) -> None:
        if not self.repository.student_exists(student_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Estudiante no encontrado",
            )

    def assert_no_conflicts(
        self,
        student_id: str,
        data: CreatePetDto | UpdatePetDto,
        except_id: str | None = None,
    ) -> None:
        if data.name is None:
            return

        existing = self.repository.find_by_student_and_name(
            student_id,
            data.name,
        )

        if existing is not None and existing.id != except_id:
            raise conflict(
                {"name": {"message": "Ya tienes una mascota con ese nombre"}}
            )
