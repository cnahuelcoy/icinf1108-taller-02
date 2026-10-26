"""Persistencia SQLAlchemy de estudiantes, sin controlar el commit.

La transacción pertenece al caso de uso que invoca al repositorio.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import StudentModel


class StudentsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_all(self) -> list[StudentModel]:
        statement = select(StudentModel).order_by(StudentModel.createdAt.desc())
        return list(self.session.scalars(statement).all())

    def find_by_id(self, student_id: str) -> StudentModel | None:
        return self.session.get(StudentModel, student_id)

    def find_by_email(self, email: str) -> StudentModel | None:
        statement = select(StudentModel).where(StudentModel.email == email)
        return self.session.scalar(statement)

    def find_by_username(self, username: str) -> StudentModel | None:
        statement = select(StudentModel).where(StudentModel.username == username)
        return self.session.scalar(statement)

    def save(self, student: StudentModel) -> StudentModel:
        self.session.add(student)
        self.session.flush()
        return student

    def delete(self, student: StudentModel) -> None:
        self.session.delete(student)
        self.session.flush()
