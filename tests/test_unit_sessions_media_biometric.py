"""
Pruebas UNITARIAS — Sesiones, Media (subida de video) y Análisis Emocional.

Cada sección aísla un componente distinto usando mocks, de forma que las
pruebas corren sin base de datos, sin Cloudinary real y sin modelo ONNX.

Organización:
    1. SessionService   — agendar, iniciar, finalizar sesiones y timeline
    2. MediaService     — subida y eliminación de video en Cloudinary
    3. BiometricService — snapshots, alertas y análisis post-sesión
    4. EmotionEngine    — softmax, resultado neutro, mock, analyze_base64
    5. Schemas          — validaciones de SnapshotCreate y MicroexpressionCreate
"""

import uuid
import base64
import pytest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, call

# ============================================================================
# SECCIÓN 1 — SESSION SERVICE: agendar y ciclo de vida de sesiones
# ============================================================================

from app.modules.sessions.service import SessionService
from app.modules.sessions.models import SessionStatus
from app.core.exceptions import BadRequestError, NotFoundError


def _make_db():
    """Crea un mock de AsyncSession para inyectar en los servicios."""
    db = AsyncMock()
    db.refresh = AsyncMock()
    return db


def _make_session_mock(status: SessionStatus = SessionStatus.SCHEDULED) -> MagicMock:
    """
    Construye un mock de un objeto Session de SQLAlchemy.
    Se reutiliza en varias pruebas para no repetir configuración.
    """
    session = MagicMock()
    session.id = uuid.uuid4()
    session.patient_id = uuid.uuid4()
    session.therapist_id = uuid.uuid4()
    session.scheduled_at = datetime.now(UTC) + timedelta(days=1)
    session.started_at = None
    session.ended_at = None
    session.status = status
    session.video_url = None
    session.video_public_id = None
    session.notes = None
    session.created_at = datetime.now(UTC)
    session.updated_at = datetime.now(UTC)
    # Relaciones embebidas (PatientSummary / UserSummary) que Pydantic necesita
    session.patient = MagicMock()
    session.patient.id = session.patient_id
    session.patient.code = "PAC-001"
    session.patient.full_name = "María González"
    session.patient.is_active = True
    session.therapist = MagicMock()
    session.therapist.id = session.therapist_id
    session.therapist.full_name = "Dr. García"
    session.therapist.email = "doctor@serena.com"
    return session


def _build_session_service() -> SessionService:
    """Construye SessionService con todos sus repositorios mockeados."""
    service = SessionService(db=_make_db())
    service._repo = AsyncMock()
    service._patient_repo = AsyncMock()
    return service


class TestSessionServiceSchedule:
    """Pruebas para schedule_session (agendar nueva sesión)."""

    @pytest.mark.asyncio
    async def test_schedule_session_raises_not_found_when_patient_missing(self):
        """
        Si el paciente no existe en la BD, schedule_session debe lanzar
        NotFoundError. No se debe crear la sesión si el paciente es inválido.
        """
        service = _build_session_service()
        service._patient_repo.get_by_id.return_value = None  # paciente no existe

        from app.modules.sessions.schemas import SessionCreate
        payload = SessionCreate(
            patient_id=uuid.uuid4(),
            scheduled_at=datetime.now(UTC) + timedelta(days=1),
        )
        current_user = MagicMock()
        current_user.id = uuid.uuid4()

        with pytest.raises(NotFoundError) as exc_info:
            await service.schedule_session(payload, current_user)

        # Verificar que el mensaje menciona "Patient"
        assert "Patient" in str(exc_info.value.detail)
        # El repositorio de sesiones NO debe ser llamado si el paciente no existe
        service._repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_schedule_session_creates_with_scheduled_status(self):
        """
        Si el paciente existe, schedule_session debe crear la sesión
        en estado SCHEDULED y asignar el therapist_id del usuario actual.
        """
        service = _build_session_service()

        # Paciente existente
        patient_id = uuid.uuid4()
        mock_patient = MagicMock()
        mock_patient.id = patient_id
        service._patient_repo.get_by_id.return_value = mock_patient

        # Sesión que retornará el repositorio al crear
        created_session = _make_session_mock(SessionStatus.SCHEDULED)
        created_session.patient_id = patient_id
        service._repo.create.return_value = created_session

        from app.modules.sessions.schemas import SessionCreate
        payload = SessionCreate(
            patient_id=patient_id,
            scheduled_at=datetime.now(UTC) + timedelta(days=1),
            notes="Primera sesión de evaluación.",
        )
        current_user = MagicMock()
        current_user.id = uuid.uuid4()

        result = await service.schedule_session(payload, current_user)

        # Verificar que se llamó create con el estado SCHEDULED
        service._repo.create.assert_awaited_once()
        call_kwargs = service._repo.create.call_args.kwargs
        assert call_kwargs["status"] == SessionStatus.SCHEDULED
        # El therapist_id debe ser el del usuario autenticado
        assert call_kwargs["therapist_id"] == current_user.id
        # El resultado debe ser un SessionResponse válido
        assert result.id == created_session.id


class TestSessionServiceLifecycle:
    """Pruebas para el ciclo de vida de una sesión: iniciar y finalizar."""

    @pytest.mark.asyncio
    async def test_start_session_raises_not_found_when_session_missing(self):
        """
        start_session debe lanzar NotFoundError si la sesión no existe en la BD.
        """
        service = _build_session_service()
        service._repo.get_by_id.return_value = None  # sesión no existe

        with pytest.raises(NotFoundError):
            await service.start_session(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_start_session_raises_bad_request_when_not_scheduled(self):
        """
        Solo se puede iniciar una sesión que esté en estado SCHEDULED.
        Si ya está ACTIVE o COMPLETED, debe lanzar BadRequestError.

        CÓMO HACER FALLAR A PROPÓSITO:
            Cambiar SessionStatus.ACTIVE por SessionStatus.SCHEDULED en la
            línea del mock — la excepción NO se lanzará y el test fallará.
        """
        service = _build_session_service()
        # Sesión ya activa (estado incorrecto para iniciar)
        already_active = _make_session_mock(status=SessionStatus.ACTIVE)
        service._repo.get_by_id.return_value = already_active

        with pytest.raises(BadRequestError) as exc_info:
            await service.start_session(already_active.id)

        assert "Cannot start" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_start_session_updates_status_to_active(self):
        """
        Con una sesión en SCHEDULED, start_session debe:
        - Actualizar el status a ACTIVE
        - Registrar el timestamp de inicio (started_at)
        """
        service = _build_session_service()
        scheduled_session = _make_session_mock(SessionStatus.SCHEDULED)
        service._repo.get_by_id.return_value = scheduled_session

        # El update retorna la sesión ya actualizada con status ACTIVE
        active_session = _make_session_mock(SessionStatus.ACTIVE)
        active_session.id = scheduled_session.id
        active_session.started_at = datetime.now(UTC)
        service._repo.update.return_value = active_session

        result = await service.start_session(scheduled_session.id)

        # Verificar que update fue llamado con status=ACTIVE y started_at definido
        call_kwargs = service._repo.update.call_args.kwargs
        assert call_kwargs["status"] == SessionStatus.ACTIVE
        assert "started_at" in call_kwargs

    @pytest.mark.asyncio
    async def test_end_session_raises_bad_request_when_not_active(self):
        """
        Solo se puede finalizar una sesión que esté ACTIVE.
        Una sesión COMPLETED no puede terminarse de nuevo.
        """
        service = _build_session_service()
        completed_session = _make_session_mock(status=SessionStatus.COMPLETED)
        service._repo.get_by_id.return_value = completed_session

        with pytest.raises(BadRequestError) as exc_info:
            await service.end_session(completed_session.id)

        assert "Only active sessions" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_end_session_updates_status_and_notes(self):
        """
        end_session debe actualizar el status a COMPLETED, registrar ended_at
        y guardar las notas clínicas si se proporcionan.
        """
        service = _build_session_service()
        active_session = _make_session_mock(SessionStatus.ACTIVE)
        service._repo.get_by_id.return_value = active_session

        completed = _make_session_mock(SessionStatus.COMPLETED)
        completed.id = active_session.id
        completed.notes = "Sesión completada exitosamente."
        service._repo.update.return_value = completed

        result = await service.end_session(
            active_session.id, notes="Sesión completada exitosamente."
        )

        call_kwargs = service._repo.update.call_args.kwargs
        assert call_kwargs["status"] == SessionStatus.COMPLETED
        assert call_kwargs["notes"] == "Sesión completada exitosamente."
        assert "ended_at" in call_kwargs

    @pytest.mark.asyncio
    async def test_get_session_raises_not_found_when_missing(self):
        """
        get_session debe lanzar NotFoundError si la sesión no existe.
        """
        service = _build_session_service()
        service._repo.get_by_id.return_value = None

        with pytest.raises(NotFoundError):
            await service.get_session(uuid.uuid4())


class TestSessionEmotionalTimeline:
    """Pruebas para get_emotional_timeline."""

    @pytest.mark.asyncio
    async def test_timeline_raises_not_found_when_session_missing(self):
        """
        get_emotional_timeline debe lanzar NotFoundError si la sesión no existe.
        """
        service = _build_session_service()
        service._repo.get_by_id.return_value = None

        with pytest.raises(NotFoundError):
            await service.get_emotional_timeline(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_timeline_returns_empty_points_when_no_snapshots(self):
        """
        Si la sesión existe pero no tiene snapshots de análisis emocional,
        el timeline debe retornar una lista vacía de puntos.
        """
        service = _build_session_service()
        completed_session = _make_session_mock(SessionStatus.COMPLETED)
        service._repo.get_by_id.return_value = completed_session

        # El import es local dentro de get_emotional_timeline, así que el patch
        # debe apuntar al módulo fuente donde se define la clase.
        with patch(
            "app.modules.biometric.repository.EmotionalSnapshotRepository"
        ) as MockSnapshotRepo:
            mock_repo = AsyncMock()
            mock_repo.list_by_session.return_value = []
            MockSnapshotRepo.return_value = mock_repo
            result = await service.get_emotional_timeline(completed_session.id)

        assert result.total_snapshots == 0
        assert result.points == []
        assert result.session_id == completed_session.id

    @pytest.mark.asyncio
    async def test_timeline_calculates_duration_from_snapshots(self):
        """
        Cuando hay snapshots, la duración debe calcularse como el máximo
        timestamp_offset entre todos los puntos.
        """
        service = _build_session_service()
        session = _make_session_mock(SessionStatus.COMPLETED)
        service._repo.get_by_id.return_value = session

        # Crear 2 snapshots mock con diferentes offsets
        snap1 = MagicMock()
        snap1.timestamp_offset = 10.5
        snap1.happiness = 0.7
        snap1.sadness = 0.05
        snap1.anger = 0.02
        snap1.fear = 0.03
        snap1.disgust = 0.05
        snap1.surprise = 0.10
        snap1.neutral = 0.05
        snap1.dominant_emotion = "happiness"
        snap1.confidence = 0.7
        snap1.raw_data = None

        snap2 = MagicMock()
        snap2.timestamp_offset = 25.0  # ← este es el mayor
        snap2.happiness = 0.2
        snap2.sadness = 0.3
        snap2.anger = 0.1
        snap2.fear = 0.2
        snap2.disgust = 0.05
        snap2.surprise = 0.05
        snap2.neutral = 0.10
        snap2.dominant_emotion = "sadness"
        snap2.confidence = 0.3
        snap2.raw_data = None

        with patch(
            "app.modules.biometric.repository.EmotionalSnapshotRepository"
        ) as MockSnapshotRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.list_by_session.return_value = [snap1, snap2]
            MockSnapshotRepo.return_value = mock_repo_instance

            result = await service.get_emotional_timeline(session.id)

        assert result.total_snapshots == 2
        # La duración debe ser el offset máximo: 25.0
        assert result.duration_seconds == 25.0
        assert len(result.points) == 2


# ============================================================================
# SECCIÓN 2 — MEDIA SERVICE: subida y eliminación de video (Cloudinary)
# ============================================================================

from app.modules.media.service import MediaService


class TestMediaServiceUploadVideo:
    """
    Pruebas para upload_video.
    Se mockea cloudinary.uploader.upload para no hacer llamadas reales a la API.
    """

    @pytest.mark.asyncio
    async def test_upload_video_returns_correct_response(self):
        """
        upload_video debe retornar un MediaUploadResponse con public_id y
        secure_url extraídos del resultado de Cloudinary.

        Se usa patch para interceptar la llamada a cloudinary.uploader.upload
        y retornar datos falsos sin tocar la API real.

        CÓMO HACER FALLAR A PROPÓSITO:
            Cambiar el assert a assert result.format == "avi" cuando
            el mock retorna "mp4" — el test fallará por formato incorrecto.
        """
        service = MediaService()

        # Simular el resultado que devolvería la API de Cloudinary
        cloudinary_response = {
            "public_id": "serena/sessions/video_abc123",
            "secure_url": "https://res.cloudinary.com/test/video/upload/serena/sessions/video_abc123.mp4",
            "resource_type": "video",
            "format": "mp4",
            "duration": 120.5,
            "bytes": 15_000_000,
        }

        # Mock del archivo UploadFile de FastAPI
        mock_file = AsyncMock()
        mock_file.read.return_value = b"fake_video_bytes_content"

        with patch("app.modules.media.service.cloudinary.uploader.upload") as mock_upload:
            mock_upload.return_value = cloudinary_response

            result = await service.upload_video(mock_file, folder="serena/sessions")

        # Verificar que el resultado mapea correctamente los campos de Cloudinary
        assert result.public_id == "serena/sessions/video_abc123"
        assert result.resource_type == "video"
        assert result.format == "mp4"
        assert result.duration == 120.5
        assert result.bytes == 15_000_000

    @pytest.mark.asyncio
    async def test_upload_video_reads_file_content_once(self):
        """
        upload_video debe leer el contenido del archivo exactamente una vez.
        Leer más de una vez podría causar que el stream ya esté consumido.
        """
        service = MediaService()
        mock_file = AsyncMock()
        mock_file.read.return_value = b"video_content"

        cloudinary_response = {
            "public_id": "serena/sessions/vid",
            "secure_url": "https://res.cloudinary.com/vid.mp4",
            "resource_type": "video",
            "format": "mp4",
            "duration": None,
            "bytes": 100,
        }

        with patch("app.modules.media.service.cloudinary.uploader.upload") as mock_upload:
            mock_upload.return_value = cloudinary_response
            await service.upload_video(mock_file)

        # file.read() debe haberse llamado exactamente una vez
        mock_file.read.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upload_video_calls_cloudinary_with_video_resource_type(self):
        """
        upload_video debe llamar a cloudinary.uploader.upload con
        resource_type='video'. Si se usa 'image', el video no se procesará
        correctamente por Cloudinary.
        """
        service = MediaService()
        mock_file = AsyncMock()
        mock_file.read.return_value = b"video"

        fake_result = {
            "public_id": "vid",
            "secure_url": "https://res.cloudinary.com/vid.mp4",
            "resource_type": "video",
            "format": "mp4",
            "duration": 30.0,
            "bytes": 500,
        }

        with patch("app.modules.media.service.cloudinary.uploader.upload") as mock_upload:
            mock_upload.return_value = fake_result
            await service.upload_video(mock_file, folder="serena/sessions")

            # Verificar los argumentos con los que se llamó a Cloudinary
            _, call_kwargs = mock_upload.call_args
            assert call_kwargs["resource_type"] == "video"
            assert call_kwargs["folder"] == "serena/sessions"

    @pytest.mark.asyncio
    async def test_upload_video_propagates_cloudinary_error(self):
        """
        Si Cloudinary lanza una excepción (timeout, límite de almacenamiento, etc.),
        el servicio debe dejar que se propague. No queremos silenciar errores
        reales de la API de media.
        """
        service = MediaService()
        mock_file = AsyncMock()
        mock_file.read.return_value = b"video"

        with patch("app.modules.media.service.cloudinary.uploader.upload") as mock_upload:
            # Simular un error de la API de Cloudinary
            mock_upload.side_effect = Exception("Cloudinary API timeout")

            with pytest.raises(Exception, match="Cloudinary API timeout"):
                await service.upload_video(mock_file)

    @pytest.mark.asyncio
    async def test_delete_asset_returns_result_field(self):
        """
        delete_asset debe retornar un MediaDeleteResponse con el resultado
        de la API de Cloudinary ('ok' cuando se eliminó correctamente).
        """
        service = MediaService()
        public_id = "serena/sessions/video_abc123"

        with patch("app.modules.media.service.cloudinary.uploader.destroy") as mock_destroy:
            mock_destroy.return_value = {"result": "ok"}

            result = await service.delete_asset(public_id, resource_type="video")

        assert result.public_id == public_id
        assert result.result == "ok"
        # Verificar que se llamó con el public_id correcto
        mock_destroy.assert_called_once_with(public_id, resource_type="video")


# ============================================================================
# SECCIÓN 3 — BIOMETRIC SERVICE: snapshots, alertas y análisis post-sesión
# ============================================================================

from app.modules.biometric.service import (
    BiometricService,
    ANXIETY_THRESHOLD,
    STRESS_THRESHOLD,
    CRITICAL_EMOTION_THRESHOLD,
)
from app.modules.biometric.schemas import SnapshotCreate


def _build_biometric_service() -> BiometricService:
    """Construye BiometricService con todos sus repositorios mockeados."""
    service = BiometricService(db=_make_db())
    service._session_repo = AsyncMock()
    service._snapshot_repo = AsyncMock()
    service._micro_repo = AsyncMock()
    service._job_repo = AsyncMock()
    service._alert_repo = AsyncMock()
    return service


def _active_session_mock() -> MagicMock:
    """Crea un mock de sesión en estado ACTIVE con patient_id asignado."""
    s = _make_session_mock(SessionStatus.ACTIVE)
    s.patient_id = uuid.uuid4()
    return s


class TestBiometricServiceSnapshots:
    """Pruebas para save_snapshot y la validación de sesión activa."""

    @pytest.mark.asyncio
    async def test_save_snapshot_raises_not_found_when_session_missing(self):
        """
        save_snapshot debe lanzar NotFoundError si la sesión no existe.
        No se deben guardar snapshots huérfanos.
        """
        service = _build_biometric_service()
        service._session_repo.get_by_id.return_value = None

        snapshot_data = SnapshotCreate(
            timestamp_offset=5.0,
            happiness=0.8,
            sadness=0.05,
            anger=0.02,
            fear=0.03,
            disgust=0.05,
            surprise=0.03,
            neutral=0.02,
            dominant_emotion="happiness",
            confidence=0.8,
        )

        with pytest.raises(NotFoundError):
            await service.save_snapshot(uuid.uuid4(), snapshot_data)

    @pytest.mark.asyncio
    async def test_save_snapshot_raises_bad_request_for_non_active_session(self):
        """
        No se pueden guardar snapshots de una sesión que no esté ACTIVE.
        Una sesión SCHEDULED o COMPLETED no debería recibir datos biométricos.

        CÓMO HACER FALLAR A PROPÓSITO:
            Cambiar SessionStatus.COMPLETED a SessionStatus.ACTIVE en el mock —
            la BadRequestError no se lanzará y el test fallará.
        """
        service = _build_biometric_service()
        completed_session = _make_session_mock(SessionStatus.COMPLETED)
        service._session_repo.get_by_id.return_value = completed_session

        snapshot_data = SnapshotCreate(
            timestamp_offset=0.0,
            happiness=0.5,
            sadness=0.1,
            anger=0.1,
            fear=0.1,
            disgust=0.1,
            surprise=0.05,
            neutral=0.05,
            dominant_emotion="happiness",
            confidence=0.5,
        )

        with pytest.raises(BadRequestError) as exc_info:
            await service.save_snapshot(uuid.uuid4(), snapshot_data)

        assert "active sessions" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_save_snapshot_persists_and_returns_response(self):
        """
        Con sesión activa, save_snapshot debe:
        1. Llamar al repositorio para persistir el snapshot
        2. Evaluar alertas
        3. Retornar el SnapshotResponse con los datos guardados
        """
        service = _build_biometric_service()
        active = _active_session_mock()
        service._session_repo.get_by_id.return_value = active

        # Snapshot que retornará el repositorio tras crear
        saved_snapshot = MagicMock()
        saved_snapshot.id = uuid.uuid4()
        saved_snapshot.session_id = active.id
        saved_snapshot.timestamp_offset = 3.0
        saved_snapshot.happiness = 0.8
        saved_snapshot.sadness = 0.05
        saved_snapshot.anger = 0.02
        saved_snapshot.fear = 0.03
        saved_snapshot.disgust = 0.05
        saved_snapshot.surprise = 0.03
        saved_snapshot.neutral = 0.02
        saved_snapshot.dominant_emotion = "happiness"
        saved_snapshot.confidence = 0.8
        saved_snapshot.raw_data = None
        saved_snapshot.created_at = datetime.now(UTC)
        service._snapshot_repo.create.return_value = saved_snapshot

        snapshot_data = SnapshotCreate(
            timestamp_offset=3.0,
            happiness=0.8,
            sadness=0.05,
            anger=0.02,
            fear=0.03,
            disgust=0.05,
            surprise=0.03,
            neutral=0.02,
            dominant_emotion="happiness",
            confidence=0.8,
        )

        result = await service.save_snapshot(active.id, snapshot_data)

        service._snapshot_repo.create.assert_awaited_once()
        assert result.dominant_emotion == "happiness"
        assert result.confidence == 0.8


class TestBiometricServiceAlerts:
    """
    Pruebas para _check_and_create_alerts.
    Verifican que las alertas se generan cuando los umbrales se superan.
    """

    @pytest.mark.asyncio
    async def test_high_anxiety_alert_created_when_threshold_exceeded(self):
        """
        Cuando fear + sadness >= ANXIETY_THRESHOLD (0.70), se debe crear
        una alerta de tipo HIGH_ANXIETY. Esto notifica al terapeuta en tiempo real.

        CÓMO HACER FALLAR A PROPÓSITO:
            Cambiar los valores a fear=0.1, sadness=0.1 (suma < 0.70) —
            la alerta no se creará y assert_awaited() fallará.
        """
        service = _build_biometric_service()
        mock_session = _active_session_mock()

        # fear=0.4 + sadness=0.4 = 0.8 >= ANXIETY_THRESHOLD (0.70)
        high_anxiety_snapshot = SnapshotCreate(
            timestamp_offset=10.0,
            happiness=0.05,
            sadness=0.40,  # ← contribuye al anxiety score
            anger=0.05,
            fear=0.40,    # ← contribuye al anxiety score
            disgust=0.05,
            surprise=0.02,
            neutral=0.03,
            dominant_emotion="fear",
            confidence=0.4,
        )

        await service._check_and_create_alerts(mock_session, high_anxiety_snapshot)

        # Debe haberse creado al menos una alerta (HIGH_ANXIETY)
        service._alert_repo.create.assert_awaited()

    @pytest.mark.asyncio
    async def test_no_alert_when_scores_below_thresholds(self):
        """
        Si todas las emociones están por debajo de los umbrales,
        no se deben crear alertas. Evita falsos positivos.
        """
        service = _build_biometric_service()
        mock_session = _active_session_mock()

        # Todos los scores bajos: fear=0.05 + sadness=0.05 = 0.10 < 0.70
        calm_snapshot = SnapshotCreate(
            timestamp_offset=5.0,
            happiness=0.75,
            sadness=0.05,
            anger=0.05,
            fear=0.05,
            disgust=0.03,
            surprise=0.04,
            neutral=0.03,
            dominant_emotion="happiness",
            confidence=0.75,  # < 0.85 (CRITICAL_EMOTION_THRESHOLD)
        )

        await service._check_and_create_alerts(mock_session, calm_snapshot)

        # No se deben crear alertas
        service._alert_repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_critical_emotion_alert_when_confidence_above_threshold(self):
        """
        Cuando la confianza de una emoción dominante >= 0.85 (CRITICAL_EMOTION_THRESHOLD),
        se debe crear una alerta CRITICAL_EMOTION independientemente de cuál sea la emoción.
        """
        service = _build_biometric_service()
        mock_session = _active_session_mock()

        critical_snapshot = SnapshotCreate(
            timestamp_offset=20.0,
            happiness=0.02,
            sadness=0.03,
            anger=0.88,  # dominante con alta confianza
            fear=0.02,
            disgust=0.02,
            surprise=0.01,
            neutral=0.02,
            dominant_emotion="anger",
            confidence=0.88,  # >= 0.85 → crítico
        )

        await service._check_and_create_alerts(mock_session, critical_snapshot)

        service._alert_repo.create.assert_awaited()

    @pytest.mark.asyncio
    async def test_stress_alert_created_when_threshold_exceeded(self):
        """
        anger + fear >= STRESS_THRESHOLD (0.65) debe generar alerta de HIGH_STRESS.
        """
        service = _build_biometric_service()
        mock_session = _active_session_mock()

        # anger=0.40 + fear=0.30 = 0.70 >= STRESS_THRESHOLD (0.65)
        stress_snapshot = SnapshotCreate(
            timestamp_offset=15.0,
            happiness=0.05,
            sadness=0.10,
            anger=0.40,   # contribuye al stress score
            fear=0.30,    # contribuye al stress score
            disgust=0.05,
            surprise=0.05,
            neutral=0.05,
            dominant_emotion="anger",
            confidence=0.40,
        )

        await service._check_and_create_alerts(mock_session, stress_snapshot)

        service._alert_repo.create.assert_awaited()


class TestBiometricServicePostSessionAnalysis:
    """Pruebas para trigger_post_session_analysis (análisis post-sesión con Celery)."""

    @pytest.mark.asyncio
    async def test_trigger_analysis_raises_not_found_when_session_missing(self):
        """
        Si la sesión no existe, no se puede encolar el análisis post-sesión.
        """
        service = _build_biometric_service()
        service._session_repo.get_by_id.return_value = None

        with pytest.raises(NotFoundError):
            await service.trigger_post_session_analysis(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_trigger_analysis_raises_bad_request_when_no_video_url(self):
        """
        Para analizar una sesión, esta debe tener un video_url grabado.
        Si no tiene video, se lanza BadRequestError.

        CÓMO HACER FALLAR A PROPÓSITO:
            Asignar session.video_url = "https://url.mp4" en lugar de None —
            BadRequestError no se lanzará y el test fallará.
        """
        service = _build_biometric_service()

        session_without_video = _make_session_mock(SessionStatus.COMPLETED)
        session_without_video.video_url = None  # ← sin video
        service._session_repo.get_by_id.return_value = session_without_video

        with pytest.raises(BadRequestError) as exc_info:
            await service.trigger_post_session_analysis(session_without_video.id)

        assert "no video" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_trigger_analysis_enqueues_celery_task(self):
        """
        Cuando la sesión tiene video_url, debe encolar la tarea Celery
        'analyze_session_video' y retornar un AnalysisJobResponse con
        el estado PENDING.
        """
        service = _build_biometric_service()

        session_with_video = _make_session_mock(SessionStatus.COMPLETED)
        session_with_video.video_url = "https://res.cloudinary.com/serena/sessions/vid.mp4"
        service._session_repo.get_by_id.return_value = session_with_video

        # No existe job previo → se crea uno nuevo
        service._job_repo.get_by_session.return_value = None

        mock_job = MagicMock()
        mock_job.id = uuid.uuid4()
        mock_job.session_id = session_with_video.id
        mock_job.celery_task_id = "celery-task-id-123"
        mock_job.status = "pending"
        mock_job.result_summary = None
        mock_job.error_message = None
        mock_job.created_at = datetime.now(UTC)
        mock_job.updated_at = datetime.now(UTC)
        service._job_repo.create.return_value = mock_job
        service._job_repo.update_status.return_value = mock_job
        service._db.refresh = AsyncMock()

        with patch(
            "app.modules.biometric.tasks.analyze_session_video"
        ) as mock_celery_task:
            # Simular el retorno de .delay() de Celery
            mock_celery_task.delay.return_value = MagicMock(id="celery-task-id-123")

            result = await service.trigger_post_session_analysis(session_with_video.id)

        # Verificar que la tarea Celery fue encolada con los argumentos correctos
        mock_celery_task.delay.assert_called_once_with(
            str(session_with_video.id), session_with_video.video_url
        )


# ============================================================================
# SECCIÓN 4 — EMOTION ENGINE: softmax, resultado neutro y modo mock
# ============================================================================

import numpy as np
from app.modules.biometric.emotion_engine import EmotionEngine, EMOTIONS


class TestEmotionEnginePureFunctions:
    """
    Pruebas para los métodos estáticos y puros del EmotionEngine.
    No requieren modelo ONNX ni base de datos.
    """

    def test_softmax_output_sums_to_one(self):
        """
        _softmax debe convertir logits a probabilidades que sumen exactamente 1.0.
        Esta es la propiedad fundamental de softmax: una distribución de probabilidad.
        """
        logits = np.array([2.0, 1.0, 0.5, -0.5, 1.5, 0.0, -1.0], dtype=np.float32)

        result = EmotionEngine._softmax(logits)

        # La suma debe ser 1.0 (con tolerancia numérica de punto flotante)
        assert abs(result.sum() - 1.0) < 1e-6, (
            f"Softmax debe sumar 1.0, obtuvo {result.sum()}"
        )
        # Todos los valores deben estar entre 0 y 1
        assert all(0.0 <= p <= 1.0 for p in result)

    def test_softmax_preserves_order(self):
        """
        El elemento con mayor logit debe tener mayor probabilidad después de softmax.
        Si el logit de 'happiness' es mayor, debe ser la emoción dominante.
        """
        # happiness (índice 3 en EMOTIONS) tiene el logit más alto
        logits = np.array([0.1, 0.2, 0.1, 3.0, 0.1, 0.1, 0.1], dtype=np.float32)

        probs = EmotionEngine._softmax(logits)
        dominant_idx = int(np.argmax(probs))

        # El índice de 'happiness' en EMOTIONS es 3
        assert EMOTIONS[dominant_idx] == "happiness"

    def test_neutral_result_has_one_for_neutral_emotion(self):
        """
        _neutral_result debe retornar neutral=1.0 y todas las demás emociones en 0.0.
        Se usa cuando no se detecta ninguna cara en el frame.
        """
        result = EmotionEngine._neutral_result()

        assert result["neutral"] == 1.0
        assert result["dominant_emotion"] == "neutral"
        assert result["confidence"] == 1.0
        # Todas las demás emociones deben ser 0
        for emotion in EMOTIONS:
            if emotion != "neutral":
                assert result[emotion] == 0.0, (
                    f"Emoción '{emotion}' debe ser 0.0 en resultado neutro"
                )

    def test_neutral_result_contains_all_seven_emotions(self):
        """
        El resultado neutro debe incluir las 7 emociones reconocidas por el modelo.
        Si falta alguna, el frontend podría romperse al intentar renderizar el chart.
        """
        result = EmotionEngine._neutral_result()

        for emotion in EMOTIONS:
            assert emotion in result, f"Emoción '{emotion}' falta en el resultado neutro"

    def test_mock_result_probabilities_sum_to_one(self):
        """
        _mock_result genera datos aleatorios normalizados que también deben sumar ~1.
        Se usa cuando el modelo ONNX no está disponible (entorno de desarrollo).
        """
        result = EmotionEngine._mock_result()

        emotion_values = [result[e] for e in EMOTIONS]
        total = sum(emotion_values)

        # La normalización puede tener pequeños errores de redondeo
        assert abs(total - 1.0) < 0.01, (
            f"Los scores del mock deben sumar ~1.0, obtuvo {total}"
        )

    def test_mock_result_dominant_emotion_is_valid(self):
        """
        La emoción dominante del resultado mock debe ser una de las 7 emociones válidas.
        """
        result = EmotionEngine._mock_result()

        assert result["dominant_emotion"] in EMOTIONS, (
            f"'{result['dominant_emotion']}' no es una emoción válida"
        )

    def test_analyze_base64_uses_mock_when_model_not_available(self):
        """
        Si el modelo ONNX no está disponible (_use_mock=True), analyze_base64
        debe retornar un resultado mock en lugar de lanzar una excepción.
        Esto garantiza que el endpoint funcione en entornos sin modelo entrenado.

        CÓMO HACER FALLAR A PROPÓSITO:
            Cambiar engine._use_mock = False sin tener un modelo ONNX instalado —
            el engine intentará usar el modelo real y fallará con AttributeError.
        """
        engine = EmotionEngine.get_instance()
        # Forzar modo mock independientemente del estado real del motor
        original_use_mock = engine._use_mock
        engine._use_mock = True

        try:
            # Un frame base64 cualquiera (no necesita ser imagen válida en modo mock)
            fake_frame = base64.b64encode(b"fake_image_data").decode()
            result = engine.analyze_base64(fake_frame)

            # El resultado debe tener todas las claves de emoción esperadas
            for emotion in EMOTIONS:
                assert emotion in result, f"Falta '{emotion}' en el resultado"
            assert "dominant_emotion" in result
            assert "confidence" in result
        finally:
            # Restaurar el estado original del singleton
            engine._use_mock = original_use_mock

    def test_emotion_engine_is_singleton(self):
        """
        EmotionEngine.get_instance() debe retornar siempre el mismo objeto.
        Si retornara instancias distintas, el modelo ONNX se cargaría múltiples
        veces en memoria, consumiendo recursos innecesariamente.
        """
        instance1 = EmotionEngine.get_instance()
        instance2 = EmotionEngine.get_instance()

        # Mismo objeto en memoria (no solo iguales, sino idénticos)
        assert instance1 is instance2, (
            "EmotionEngine debe ser un singleton. "
            "get_instance() retornó objetos distintos."
        )


# ============================================================================
# SECCIÓN 5 — SCHEMAS: validación de datos biométricos y de sesión
# ============================================================================

from pydantic import ValidationError
from app.modules.biometric.schemas import SnapshotCreate, MicroexpressionCreate
from app.modules.sessions.schemas import SessionCreate


class TestSnapshotCreateSchema:
    """Pruebas para las restricciones de rango en SnapshotCreate."""

    def test_valid_snapshot_passes_validation(self):
        """
        Un snapshot con todos los valores dentro del rango [0.0, 1.0] y
        timestamp_offset >= 0 debe pasar la validación sin errores.
        """
        snap = SnapshotCreate(
            timestamp_offset=5.5,
            happiness=0.70,
            sadness=0.05,
            anger=0.05,
            fear=0.05,
            disgust=0.05,
            surprise=0.05,
            neutral=0.05,
            dominant_emotion="happiness",
            confidence=0.70,
        )
        assert snap.dominant_emotion == "happiness"

    def test_negative_timestamp_offset_is_rejected(self):
        """
        timestamp_offset debe ser >= 0 (no puede haber frames antes de que empiece
        la sesión). Definido con Field(..., ge=0).

        CÓMO HACER FALLAR A PROPÓSITO:
            Cambiar -1.0 a 0.0 — la validación pasará y pytest.raises fallará.
        """
        with pytest.raises(ValidationError) as exc_info:
            SnapshotCreate(
                timestamp_offset=-1.0,  # ← negativo, no permitido
                happiness=0.5,
                sadness=0.1,
                anger=0.1,
                fear=0.1,
                disgust=0.1,
                surprise=0.05,
                neutral=0.05,
                dominant_emotion="happiness",
                confidence=0.5,
            )

        errores = exc_info.value.errors()
        campos = [e["loc"][0] for e in errores]
        assert "timestamp_offset" in campos

    def test_emotion_score_above_one_is_rejected(self):
        """
        Los scores de emoción deben estar en [0.0, 1.0]. Un valor de 1.5
        no es una probabilidad válida.
        """
        with pytest.raises(ValidationError):
            SnapshotCreate(
                timestamp_offset=0.0,
                happiness=1.5,  # ← mayor que 1.0, inválido
                sadness=0.0,
                anger=0.0,
                fear=0.0,
                disgust=0.0,
                surprise=0.0,
                neutral=0.0,
                dominant_emotion="happiness",
                confidence=1.5,
            )

    def test_negative_emotion_score_is_rejected(self):
        """
        Los scores de emoción deben ser >= 0.0. Una probabilidad negativa
        no tiene sentido estadístico.
        """
        with pytest.raises(ValidationError):
            SnapshotCreate(
                timestamp_offset=0.0,
                happiness=-0.1,  # ← negativo, inválido
                sadness=0.5,
                anger=0.2,
                fear=0.2,
                disgust=0.1,
                surprise=0.0,
                neutral=0.1,
                dominant_emotion="sadness",
                confidence=0.5,
            )


class TestMicroexpressionCreateSchema:
    """Pruebas para MicroexpressionCreate (eventos de microexpresiones)."""

    def test_duration_above_500ms_is_rejected(self):
        """
        Por definición, las microexpresiones duran menos de 500ms.
        El campo duration_ms tiene la restricción le=500.
        Un valor de 600ms debe ser rechazado.
        """
        with pytest.raises(ValidationError) as exc_info:
            MicroexpressionCreate(
                timestamp_offset=10.0,
                emotion_detected="disgust",
                intensity=0.8,
                duration_ms=600,  # ← demasiado largo para ser microexpresión
            )

        errores = exc_info.value.errors()
        campos = [e["loc"][0] for e in errores]
        assert "duration_ms" in campos

    def test_zero_duration_is_rejected(self):
        """
        duration_ms debe ser > 0 (gt=0). Una duración de 0ms no es válida.
        """
        with pytest.raises(ValidationError):
            MicroexpressionCreate(
                timestamp_offset=10.0,
                emotion_detected="surprise",
                intensity=0.6,
                duration_ms=0,  # ← debe ser mayor que 0
            )

    def test_valid_microexpression_passes_validation(self):
        """
        Una microexpresión con duración entre 1-500ms y demás campos válidos
        debe pasar la validación.
        """
        micro = MicroexpressionCreate(
            timestamp_offset=3.0,
            emotion_detected="surprise",
            intensity=0.65,
            duration_ms=150,  # ← duración típica de microexpresión
        )
        assert micro.emotion_detected == "surprise"
        assert micro.duration_ms == 150


class TestSessionCreateSchema:
    """Pruebas para el esquema SessionCreate."""

    def test_valid_session_create_passes(self):
        """
        Un UUID de paciente y una fecha futura válida deben pasar la validación.
        """
        session = SessionCreate(
            patient_id=uuid.uuid4(),
            scheduled_at=datetime.now(UTC) + timedelta(days=7),
            notes="Evaluación inicial del paciente.",
        )
        assert session.notes == "Evaluación inicial del paciente."

    def test_session_create_without_notes_passes(self):
        """
        Las notas son opcionales; se puede crear una sesión sin ellas.
        """
        session = SessionCreate(
            patient_id=uuid.uuid4(),
            scheduled_at=datetime.now(UTC) + timedelta(hours=2),
        )
        assert session.notes is None
