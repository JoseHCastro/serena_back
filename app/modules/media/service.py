"""Cloudinary media service — upload and delete media assets."""

import cloudinary
import cloudinary.uploader
from fastapi import UploadFile
from loguru import logger

from app.core.config import settings
from app.modules.media.schemas import MediaDeleteResponse, MediaUploadResponse

# Configure Cloudinary SDK once at import time
cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
    secure=True,
)


class MediaService:
    """Service for uploading and deleting media assets on Cloudinary.

    All session videos and therapy-related images are stored on Cloudinary.
    The DB stores only the public_id and secure_url for each asset.
    """

    async def upload_video(
        self, file: UploadFile, folder: str = "serena/sessions"
    ) -> MediaUploadResponse:
        """Upload a video file to Cloudinary under the sessions folder.

        Args:
            file: The uploaded video file from a multipart form request.
            folder: Cloudinary folder path to organize assets.

        Returns:
            MediaUploadResponse: Upload result with public_id and secure_url.

        Raises:
            Exception: Re-raises Cloudinary API errors.
        """
        logger.info("Uploading video to Cloudinary | folder={}", folder)
        contents = await file.read()
        result = cloudinary.uploader.upload(
            contents,
            resource_type="video",
            folder=folder,
            chunk_size=6_000_000,  # 6 MB chunks for large files
        )
        logger.info("Video uploaded | public_id={}", result["public_id"])
        return MediaUploadResponse(
            public_id=result["public_id"],
            secure_url=result["secure_url"],
            resource_type=result["resource_type"],
            format=result["format"],
            duration=result.get("duration"),
            bytes=result["bytes"],
        )

    async def upload_image(
        self, file: UploadFile, folder: str = "serena/images"
    ) -> MediaUploadResponse:
        """Upload an image file to Cloudinary.

        Args:
            file: The uploaded image file.
            folder: Cloudinary folder path.

        Returns:
            MediaUploadResponse: Upload result.
        """
        logger.info("Uploading image to Cloudinary | folder={}", folder)
        contents = await file.read()
        result = cloudinary.uploader.upload(
            contents,
            resource_type="image",
            folder=folder,
        )
        return MediaUploadResponse(
            public_id=result["public_id"],
            secure_url=result["secure_url"],
            resource_type=result["resource_type"],
            format=result["format"],
            bytes=result["bytes"],
        )

    async def delete_asset(
        self, public_id: str, resource_type: str = "video"
    ) -> MediaDeleteResponse:
        """Delete an asset from Cloudinary by its public_id.

        Args:
            public_id: The Cloudinary asset public identifier.
            resource_type: Type of asset ("video" or "image").

        Returns:
            MediaDeleteResponse: Deletion result from the Cloudinary API.
        """
        logger.info("Deleting Cloudinary asset | public_id={}", public_id)
        result = cloudinary.uploader.destroy(public_id, resource_type=resource_type)
        return MediaDeleteResponse(public_id=public_id, result=result.get("result", "unknown"))
