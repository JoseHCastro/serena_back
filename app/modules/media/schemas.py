"""Pydantic schemas for the Media module (Cloudinary)."""

from pydantic import BaseModel, HttpUrl


class MediaUploadResponse(BaseModel):
    """Response returned after successfully uploading media to Cloudinary.

    Attributes:
        public_id: Cloudinary asset identifier used for deletion/transformation.
        secure_url: HTTPS URL for accessing the uploaded media.
        resource_type: Type of media (e.g., "video", "image").
        format: File format (e.g., "mp4", "jpg").
        duration: Video duration in seconds (None for images).
        bytes: File size in bytes.
    """

    public_id: str
    secure_url: str
    resource_type: str
    format: str
    duration: float | None = None
    bytes: int


class MediaDeleteResponse(BaseModel):
    """Response returned after deleting a Cloudinary asset."""

    public_id: str
    result: str
