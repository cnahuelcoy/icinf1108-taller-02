"""Casos de uso de estudiantes respaldados por PostgreSQL."""

from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.connection import get_session_factory
from app.database.models import PetModel, StudentModel
from app.shared.datetimes import utc_now
from app.shared.exceptions import conflict
from app.shared.types import FieldErrors
from app.students.students_repository import StudentsRepository
from app.students.students_schemas import (
    CreateStudentDto,
    Student,
    StudentList,
    UpdateStudentDto,
)


def _student_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Estudiante no encontrado",
    )


def _convert_integrity_error(exc: IntegrityError) -> HTTPException | None:
    """Traducir únicamente restricciones conocidas, sin exponer SQL ni claves."""
    original = exc.orig
    if getattr(original, "sqlstate", None) != "23505":
        return None

    diag = getattr(original, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None)
    field = {
        "students_email_key": "email",
        "students_username_key": "username",
    }.get(constraint_name)

    if field == "email":
        return conflict({"email": {"message": "El correo electrónico ya está en uso"}})
    if field == "username":
        return conflict({"username": {"message": "El nombre de usuario ya está en uso"}})
    return None


class StudentsService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = StudentsRepository(session)

    def find_all(self) -> StudentList:
        students = self.repository.find_all()
        return StudentList(
            total=len(students),
            items=[Student.model_validate(student) for student in students],
        )

    def find_by_id(self, student_id: str) -> Student:
        student = self.repository.find_by_id(student_id)
        if student is None:
            raise _student_not_found()
        return Student.model_validate(student)

    def create(self, data: CreateStudentDto) -> Student:
        try:
            with self.session.begin():
                self.assert_no_conflicts(data)
                now = utc_now()
                student = StudentModel(
                    id=str(uuid4()),
                    name=data.name,
                    username=data.username,
                    email=str(data.email),
                    age=data.age,
                    createdAt=now,
                    updatedAt=now,
                )
                self.repository.save(student)

                # La creación anidada comparte la transacción del estudiante.
                # La integración de los demás endpoints Pets requiere coordinación.
                names: set[str] = set()
                for pet_data in data.pets:
                    if pet_data.name in names:
                        raise conflict(
                            {"name": {"message": "Ya tienes una mascota con ese nombre"}}
                        )
                    names.add(pet_data.name)
                    pet_now = utc_now()
                    self.session.add(
                        PetModel(
                            id=str(uuid4()),
                            studentId=student.id,
                            name=pet_data.name,
                            species=pet_data.species,
                            age=pet_data.age,
                            createdAt=pet_now,
                            updatedAt=pet_now,
                        )
                    )
                self.session.flush()
                result = Student.model_validate(student)
            return result
        except IntegrityError as exc:
            mapped = _convert_integrity_error(exc)
            if mapped is not None:
                raise mapped from None
            raise

    def update(self, student_id: str, data: UpdateStudentDto) -> Student:
        try:
            with self.session.begin():
                student = self.repository.find_by_id(student_id)
                if student is None:
                    raise _student_not_found()
                self.assert_no_conflicts(data, except_id=student_id)
                for name, value in data.model_dump(exclude_none=True).items():
                    setattr(student, name, value)
                student.updatedAt = utc_now()
                self.repository.save(student)
                result = Student.model_validate(student)
            return result
        except IntegrityError as exc:
            mapped = _convert_integrity_error(exc)
            if mapped is not None:
                raise mapped from None
            raise

    def delete(self, student_id: str) -> Student:
        with self.session.begin():
            student = self.repository.find_by_id(student_id)
            if student is None:
                raise _student_not_found()
            result = Student.model_validate(student)
            self.repository.delete(student)
        return result

    def assert_no_conflicts(
        self,
        data: CreateStudentDto | UpdateStudentDto,
        except_id: str | None = None,
    ) -> None:
        errors: FieldErrors = {}
        if data.email:
            existing = self.repository.find_by_email(str(data.email))
            if existing is not None and existing.id != except_id:
                errors["email"] = {"message": "El correo electrónico ya está en uso"}
        if data.username:
            existing = self.repository.find_by_username(data.username)
            if existing is not None and existing.id != except_id:
                errors["username"] = {"message": "El nombre de usuario ya está en uso"}
        if errors:
            raise conflict(errors)


class _StudentsLookupForLegacyPets:
    """Puente de lectura temporal para PetsService hasta su migración ORM."""

    def find_by_id(self, student_id: str) -> Student:
        with get_session_factory()() as session:
            return StudentsService(session).find_by_id(student_id)


# PetsService importa este nombre en su módulo actual.
students_service = _StudentsLookupForLegacyPets()
