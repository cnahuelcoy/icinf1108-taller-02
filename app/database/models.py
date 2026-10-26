from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)

from app.shared.datetimes import utc_now


class Base(DeclarativeBase):
    pass


class StudentModel(Base):
    __tablename__ = "students"

    __table_args__ = (
        CheckConstraint(
            "age BETWEEN 18 AND 99",
            name="ck_students_age",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    username: Mapped[str] = mapped_column(
        String(30), unique=True, nullable=False
    )

    email: Mapped[str] = mapped_column(
        String(254), unique=True, nullable=False
    )

    age: Mapped[int] = mapped_column(Integer, nullable=False)

    createdAt: Mapped[datetime] = mapped_column(
        "created_at",
        DateTime(timezone=True),
        default=utc_now,
    )

    updatedAt: Mapped[datetime] = mapped_column(
        "updated_at",
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    pets: Mapped[list["PetModel"]] = relationship(
        back_populates="student",
        cascade="all, delete-orphan",
    )


class PetModel(Base):
    __tablename__ = "pets"

    __table_args__ = (
        CheckConstraint(
            "age BETWEEN 0 AND 100",
            name="ck_pets_age",
        ),
        UniqueConstraint(
            "student_id",
            "name",
            name="uq_pets_student_name",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
    )

    studentId: Mapped[str] = mapped_column(
        "student_id",
        String(36),
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    species: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    age: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    createdAt: Mapped[datetime] = mapped_column(
        "created_at",
        DateTime(timezone=True),
        default=utc_now,
    )

    updatedAt: Mapped[datetime] = mapped_column(
        "updated_at",
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    student: Mapped["StudentModel"] = relationship(
        back_populates="pets",
    )