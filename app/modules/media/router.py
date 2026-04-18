"""Media router — Cloudinary upload endpoints."""

from fastapi import APIRouter, UploadFile, File
from app.core.dependencies import CurrentUser, DbSession
from app.modules.media.schemas import MediaUploadResponse
from app.modules.media.service import MediaService

router = APIRouter(prefix="/media", tags=["Media"])


@router.post("/upload/video", response_model=MediaUploadResponse, status_code=201,
             summary="Upload session video to Cloudinary")
async def upload_video(
    file: UploadFile = File(..., description="Video file (mp4, webm, etc.)"),
    _: CurrentUser = None,
) -> MediaUploadResponse:
    """Upload a therapy session video to Cloudinary.

    Args:
        file: The multipart video file to upload.

    Returns:
        MediaUploadResponse: Cloudinary public_id and secure_url.
    """
    return await MediaService().upload_video(file)


@router.post("/upload/image", response_model=MediaUploadResponse, status_code=201,
             summary="Upload an image to Cloudinary")
async def upload_image(
    file: UploadFile = File(...),
    _: CurrentUser = None,
) -> MediaUploadResponse:
    """Upload an image (e.g., patient photo) to Cloudinary."""
    return await MediaService().upload_image(file)
