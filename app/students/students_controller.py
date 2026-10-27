"""Rutas de estudiantes con una sesión de SQLAlchemy por petición."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.students.students_schemas import (
    CreateStudentDto,
    Student,
    StudentList,
    UpdateStudentDto,
)
from app.students.students_service import StudentsService

router = APIRouter(prefix="/api/students", tags=["Students"])


@router.get("")
def find_all(db: Session = Depends(get_db)) -> StudentList:
    return StudentsService(db).find_all()


@router.get("/{studentId}")
def find_by_id(studentId: str, db: Session = Depends(get_db)) -> Student:
    return StudentsService(db).find_by_id(studentId)


@router.post("", status_code=201)
def create(body: CreateStudentDto, db: Session = Depends(get_db)) -> Student:
    return StudentsService(db).create(body)


@router.patch("/{studentId}")
def update(
    studentId: str,
    body: UpdateStudentDto,
    db: Session = Depends(get_db),
) -> Student:
    return StudentsService(db).update(studentId, body)


@router.delete("/{studentId}")
def delete(studentId: str, db: Session = Depends(get_db)) -> Student:
    # StudentModel.pets tiene cascada delete-orphan; no eliminar en memoria.
    return StudentsService(db).delete(studentId)
