from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database.models import PetModel, StudentModel


class PetsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def student_exists(self, student_id: str) -> bool:
        return self.session.get(StudentModel, student_id) is not None

    def find_all_by_student(self, student_id: str) -> list[PetModel]:
        statement = (
            select(PetModel)
            .where(PetModel.studentId == student_id)
            .order_by(PetModel.createdAt.desc())
        )

        return list(self.session.scalars(statement).all())

    def find_by_id(self, pet_id: str) -> PetModel | None:
        return self.session.get(PetModel, pet_id)

    def find_by_student_and_name(
        self,
        student_id: str,
        name: str,
    ) -> PetModel | None:
        statement = select(PetModel).where(
            PetModel.studentId == student_id,
            PetModel.name == name,
        )

        return self.session.scalars(statement).one_or_none()

    def save(self, pet: PetModel) -> PetModel:
        self.session.add(pet)
        self.session.flush()

        return pet

    def delete(self, pet_id: str) -> None:
        pet = self.find_by_id(pet_id)

        if pet is not None:
            self.session.delete(pet)
            self.session.flush()

    def delete_by_student(self, student_id: str) -> None:
        statement = delete(PetModel).where(PetModel.studentId == student_id)

        self.session.execute(statement)
        self.session.flush()
