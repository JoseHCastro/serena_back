"""Reports service — PDF generation for clinical reports."""

import uuid
from datetime import datetime

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.biometric.repository import EmotionalSnapshotRepository, MicroexpressionRepository
from app.modules.patients.repository import PatientRepository
from app.modules.sessions.repository import SessionRepository

# HTML template for the session PDF report
_SESSION_REPORT_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <style>
    body {{ font-family: Arial, sans-serif; font-size: 12px; color: #333; margin: 40px; }}
    h1 {{ color: #4A5568; border-bottom: 2px solid #4A5568; padding-bottom: 8px; }}
    h2 {{ color: #2D3748; margin-top: 24px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
    th {{ background: #4A5568; color: white; padding: 8px; text-align: left; }}
    td {{ padding: 6px 8px; border-bottom: 1px solid #E2E8F0; }}
    tr:nth-child(even) {{ background: #F7FAFC; }}
    .alert-high {{ color: #C53030; font-weight: bold; }}
    .alert-medium {{ color: #D69E2E; }}
    .footer {{ margin-top: 40px; font-size: 10px; color: #718096; text-align: center; }}
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px;
              background: #EBF8FF; color: #2B6CB0; font-weight: bold; }}
  </style>
</head>
<body>
  <h1>Reporte de Sesión Clínica — Serena</h1>
  <p><strong>Paciente:</strong> {patient_name} ({patient_code})</p>
  <p><strong>Terapeuta:</strong> {therapist_name}</p>
  <p><strong>Fecha de sesión:</strong> {scheduled_at}</p>
  <p><strong>Duración:</strong> {duration}</p>
  <p><strong>Estado:</strong> <span class="badge">{status}</span></p>

  <h2>Notas del Terapeuta</h2>
  <p>{notes}</p>

  <h2>Análisis Emocional — Resumen</h2>
  <table>
    <tr><th>Emoción</th><th>Promedio</th></tr>
    <tr><td>Felicidad</td><td>{avg_happiness:.1%}</td></tr>
    <tr><td>Tristeza</td><td>{avg_sadness:.1%}</td></tr>
    <tr><td>Enojo</td><td>{avg_anger:.1%}</td></tr>
    <tr><td>Miedo</td><td>{avg_fear:.1%}</td></tr>
    <tr><td>Asco</td><td>{avg_disgust:.1%}</td></tr>
    <tr><td>Sorpresa</td><td>{avg_surprise:.1%}</td></tr>
    <tr><td>Neutral</td><td>{avg_neutral:.1%}</td></tr>
  </table>
  <p><strong>Emoción dominante:</strong> {dominant_emotion} | <strong>Total snapshots:</strong> {snapshot_count}</p>

  <h2>Microexpresiones Detectadas ({micro_count})</h2>
  {micro_table}

  <div class="footer">
    Generado el {generated_at} por Serena Sistema de Análisis Biométrico.
    Documento confidencial — solo para uso clínico.
  </div>
</body>
</html>
"""


class ReportService:
    """Business logic for generating clinical PDF reports.

    Args:
        db: The active AsyncSession injected via FastAPI dependency.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._session_repo = SessionRepository(db)
        self._patient_repo = PatientRepository(db)
        self._snapshot_repo = EmotionalSnapshotRepository(db)
        self._micro_repo = MicroexpressionRepository(db)

    async def generate_session_pdf(self, session_id: uuid.UUID) -> bytes:
        """Generate a PDF report for a single therapy session.

        Collects session metadata, emotional analysis averages, and
        microexpression events, renders them into an HTML template,
        and converts to PDF using WeasyPrint.

        Args:
            session_id: UUID of the session to report on.

        Returns:
            bytes: The rendered PDF as raw bytes.

        Raises:
            NotFoundError: If the session does not exist.
        """
        from weasyprint import HTML

        session = await self._session_repo.get_by_id(session_id)
        if not session:
            raise NotFoundError("Session")

        averages = await self._snapshot_repo.get_session_averages(session_id)
        microexpressions = await self._micro_repo.list_by_session(session_id)

        duration = "N/A"
        if session.started_at and session.ended_at:
            secs = int((session.ended_at - session.started_at).total_seconds())
            duration = f"{secs // 60}m {secs % 60}s"

        micro_rows = "".join(
            f"<tr><td>{m.timestamp_offset:.1f}s</td>"
            f"<td>{m.emotion_detected}</td>"
            f"<td>{m.intensity:.2f}</td>"
            f"<td>{m.duration_ms}ms</td></tr>"
            for m in microexpressions
        )
        micro_table = (
            f"<table><tr><th>Tiempo</th><th>Emoción</th><th>Intensidad</th><th>Duración</th></tr>"
            f"{micro_rows}</table>"
            if microexpressions
            else "<p>No se detectaron microexpresiones en esta sesión.</p>"
        )

        html_content = _SESSION_REPORT_TEMPLATE.format(
            patient_name=session.patient.full_name,
            patient_code=session.patient.code,
            therapist_name=session.therapist.full_name,
            scheduled_at=session.scheduled_at.strftime("%d/%m/%Y %H:%M"),
            duration=duration,
            status=session.status.value.upper(),
            notes=session.notes or "Sin notas registradas.",
            avg_happiness=averages["avg_happiness"],
            avg_sadness=averages["avg_sadness"],
            avg_anger=averages["avg_anger"],
            avg_fear=averages["avg_fear"],
            avg_disgust=averages["avg_disgust"],
            avg_surprise=averages["avg_surprise"],
            avg_neutral=averages["avg_neutral"],
            dominant_emotion=averages["dominant_overall"].upper(),
            snapshot_count=averages["snapshot_count"],
            micro_count=len(microexpressions),
            micro_table=micro_table,
            generated_at=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        )

        logger.info("Generating PDF report | session={}", session_id)
        pdf_bytes: bytes = HTML(string=html_content).write_pdf()
        return pdf_bytes
