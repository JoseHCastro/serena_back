"""Reports router — PDF and Excel download endpoints."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.core.dependencies import CurrentUser, DbSession, require_roles
from app.modules.reports.service import ReportService

router = APIRouter(prefix="/reports", tags=["Reports"])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get(
    "/sessions/{session_id}/pdf",
    summary="Download PDF report for a session",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def download_session_report(
    session_id: uuid.UUID, db: DbSession, _: CurrentUser
) -> Response:
    pdf_bytes = await ReportService(db).generate_session_pdf(session_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=session_{session_id}.pdf"},
    )


@router.get(
    "/patients/{patient_id}/pdf",
    summary="Download PDF clinical report for a patient",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def download_patient_pdf(
    patient_id: uuid.UUID, db: DbSession, _: CurrentUser
) -> Response:
    pdf_bytes = await ReportService(db).generate_patient_pdf(patient_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=paciente_{patient_id}.pdf"},
    )


@router.get(
    "/patients/{patient_id}/excel",
    summary="Download Excel clinical report for a patient",
    response_class=Response,
    responses={200: {"content": {_XLSX: {}}}},
)
async def download_patient_excel(
    patient_id: uuid.UUID, db: DbSession, _: CurrentUser
) -> Response:
    xlsx_bytes = await ReportService(db).generate_patient_excel(patient_id)
    return Response(
        content=xlsx_bytes,
        media_type=_XLSX,
        headers={"Content-Disposition": f"attachment; filename=paciente_{patient_id}.xlsx"},
    )


@router.get(
    "/admin/pdf",
    summary="Download admin PDF report for a date range",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
    dependencies=[Depends(require_roles("admin"))],
)
async def download_admin_pdf(
    db: DbSession,
    _: CurrentUser,
    date_from: date = Query(..., description="Start date (YYYY-MM-DD)"),
    date_to: date = Query(..., description="End date (YYYY-MM-DD)"),
) -> Response:
    pdf_bytes = await ReportService(db).generate_admin_pdf(date_from, date_to)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=admin_{date_from}_{date_to}.pdf"
        },
    )


@router.get(
    "/admin/excel",
    summary="Download admin Excel report for a date range",
    response_class=Response,
    responses={200: {"content": {_XLSX: {}}}},
    dependencies=[Depends(require_roles("admin"))],
)
async def download_admin_excel(
    db: DbSession,
    _: CurrentUser,
    date_from: date = Query(..., description="Start date (YYYY-MM-DD)"),
    date_to: date = Query(..., description="End date (YYYY-MM-DD)"),
) -> Response:
    xlsx_bytes = await ReportService(db).generate_admin_excel(date_from, date_to)
    return Response(
        content=xlsx_bytes,
        media_type=_XLSX,
        headers={
            "Content-Disposition": f"attachment; filename=admin_{date_from}_{date_to}.xlsx"
        },
    )
