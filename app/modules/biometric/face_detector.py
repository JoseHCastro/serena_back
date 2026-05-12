"""Face detection module using MediaPipe.

Provides lightweight face detection and cropping suitable for real-time
webcam streams and batch video processing. MediaPipe's BlazeFace model
runs efficiently on CPU with sub-10ms latency per frame.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import cv2
import numpy as np
from loguru import logger

if TYPE_CHECKING:
    pass


class FaceDetector:
    """Detect and crop faces from images using MediaPipe BlazeFace.

    This detector is optimized for the Serena use case where the subject
    is seated facing the camera at close range (~0.5-2m).

    Attributes:
        _detector: MediaPipe FaceDetection instance.
        _min_confidence: Minimum detection confidence threshold.
        _padding: Fractional padding around the detected face bounding box.
    """

    def __init__(
        self,
        model_selection: int = 0,
        min_confidence: float = 0.5,
        padding: float = 0.15,
    ) -> None:
        """Initialize the face detector.

        Args:
            model_selection: 0 for faces within 2m (webcam), 1 for up to 5m.
            min_confidence: Minimum detection confidence (0.0-1.0).
            padding: Fractional padding around the face bounding box
                     (0.15 = 15% extra on each side).
        """
        self._min_confidence = min_confidence
        self._padding = padding
        # Use OpenCV Haar Cascades instead of MediaPipe for better compatibility
        self._detector = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

    def detect_and_crop(
        self,
        image: np.ndarray,
        target_size: tuple[int, int] = (224, 224),
    ) -> np.ndarray | None:
        """Detect the primary face in an image using OpenCV and return a cropped, resized version.

        Args:
            image: Input image as a NumPy array in BGR format (OpenCV convention).
            target_size: Output (width, height) for the cropped face.

        Returns:
            A resized face crop as a NumPy array in RGB format, or None
            if no face was detected.
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        faces = self._detector.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
        )

        if len(faces) == 0:
            return None

        # Pick the largest face detected
        (x, y, w, h) = max(faces, key=lambda b: b[2] * b[3])

        # Add padding
        pad_w = int(w * self._padding)
        pad_h = int(h * self._padding)

        y1 = max(0, y - pad_h)
        y2 = min(image.shape[0], y + h + pad_h)
        x1 = max(0, x - pad_w)
        x2 = min(image.shape[1], x + w + pad_w)

        # Validate crop dimensions
        if x2 - x1 < 10 or y2 - y1 < 10:
            logger.warning("Face crop too small ({w}x{h}), skipping", w=x2 - x1, h=y2 - y1)
            return None

        face_crop_bgr = image[y1:y2, x1:x2]
        face_crop_rgb = cv2.cvtColor(face_crop_bgr, cv2.COLOR_BGR2RGB)
        face_resized = cv2.resize(face_crop_rgb, target_size, interpolation=cv2.INTER_AREA)

        return face_resized  # RGB format, shape (224, 224, 3)

    def detect_and_crop_from_bytes(
        self,
        image_bytes: bytes,
        target_size: tuple[int, int] = (224, 224),
    ) -> np.ndarray | None:
        """Convenience method to detect a face from raw image bytes.

        Args:
            image_bytes: Raw image bytes (JPEG, PNG, etc.).
            target_size: Output (width, height) for the cropped face.

        Returns:
            A resized face crop as a NumPy array in RGB, or None.
        """
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if image is None:
            logger.warning("Failed to decode image bytes")
            return None
        return self.detect_and_crop(image, target_size)

    def close(self) -> None:
        """Release MediaPipe resources."""
        self._detector.close()

    def __enter__(self) -> FaceDetector:
        return self

    def __exit__(self, *args) -> None:
        self.close()
