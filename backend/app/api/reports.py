from fastapi import APIRouter
from fastapi.responses import FileResponse

from ..models.schemas import ReportRequest, ReportResponse
from ..services import report_service

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("", response_model=ReportResponse)
def create_report(request: ReportRequest) -> ReportResponse:
    report_id, file_name, _ = report_service.generate_report(request)
    return ReportResponse(
        report_id=report_id,
        file_name=file_name,
        download_url=f"/api/reports/{report_id}/download",
    )


@router.get("/{report_id}/download")
def download_report(report_id: str) -> FileResponse:
    path = report_service.report_file(report_id)
    return FileResponse(path, media_type="application/pdf", filename=path.name)
