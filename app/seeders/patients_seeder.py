"""Patients seeder — creates realistic sample patient records using Faker."""

import random
from datetime import date

from faker import Faker
from faker.providers import person, address, phone_number
from loguru import logger
from sqlalchemy import func, select

from app.modules.patients.models import Patient
from app.modules.users.models import Role, User
from app.seeders.base_seeder import BaseSeeder

fake = Faker("es_MX")  # Mexican Spanish locale for realistic clinical data
PATIENT_COUNT = 15
GENDERS = ["Masculino", "Femenino", "No binario", "Prefiero no decir"]


class PatientsSeeder(BaseSeeder):
    """Seeds 15 realistic patient records distributed among therapists.

    Uses Faker with Mexican Spanish locale to generate realistic names,
    addresses, phone numbers, and clinical notes.
    """

    async def run(self) -> None:
        """Create sample patients if the table is empty."""
        existing_count_result = await self._db.execute(
            select(func.count()).select_from(Patient)
        )
        if existing_count_result.scalar_one() > 0:
            logger.debug("Patients already seeded, skipping.")
            return

        therapist_role_result = await self._db.execute(
            select(Role).where(Role.name == "therapist")
        )
        therapist_role = therapist_role_result.scalar_one_or_none()
        if not therapist_role:
            logger.warning("Therapist role not found, skipping patients seeder.")
            return

        therapists_result = await self._db.execute(
            select(User).where(User.role_id == therapist_role.id)
        )
        therapists = list(therapists_result.scalars().all())
        if not therapists:
            logger.warning("No therapists found, skipping patients seeder.")
            return

        for i in range(1, PATIENT_COUNT + 1):
            gender = random.choice(GENDERS)
            birth_date = fake.date_of_birth(minimum_age=18, maximum_age=75)
            therapist = random.choice(therapists)

            patient = Patient(
                code=f"PAC-{i:04d}",
                first_name=fake.first_name(),
                last_name=f"{fake.last_name()} {fake.last_name()}",
                birth_date=birth_date,
                gender=gender,
                phone=fake.phone_number()[:20],
                email=fake.email(),
                address=fake.address().replace("\n", ", "),
                emergency_contact_name=fake.name(),
                emergency_contact_phone=fake.phone_number()[:20],
                medical_notes=random.choice([
                    "Paciente presenta episodios de ansiedad generalizada. Se recomienda terapia cognitivo-conductual.",
                    "Historial de depresión mayor. Actualmente en proceso de duelo por pérdida familiar.",
                    "Trastorno de adaptación leve. Primera consulta psicológica.",
                    "Paciente con antecedentes de estrés postraumático. Requiere seguimiento cercano.",
                    "Fobia social diagnosticada. Trabajando en exposición gradual.",
                    None,
                ]),
                therapist_id=therapist.id,
                is_active=random.choice([True, True, True, False]),
            )
            self._db.add(patient)

        await self._db.flush()
        logger.info("Seeded {} patients", PATIENT_COUNT)
