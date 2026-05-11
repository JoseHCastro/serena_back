"""Face detection module using MediaPipe.

Provides lightweight face detection and cropping suitable for real-time
webcam streams and batch video processing. MediaPipe's BlazeFace model
runs efficiently on CPU with sub-10ms latency per frame.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import cv2
import mediapipe as mp
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
        self._detector = mp.solutions.face_detection.FaceDetection(
            model_selection=model_selection,
            min_detection_confidence=min_confidence,
        )

    def detect_and_crop(
        self,
        image: np.ndarray,
        target_size: tuple[int, int] = (224, 224),
    ) -> np.ndarray | None:
        """Detect the primary face in an image and return a cropped, resized version.

        If multiple faces are detected, the one with the highest confidence
        score is selected (typically the largest / closest face).

        Args:
            image: Input image as a NumPy array in BGR format (OpenCV convention).
            target_size: Output (width, height) for the cropped face.

        Returns:
            A resized face crop as a NumPy array in RGB format, or None
            if no face was detected.
        """
        h, w = image.shape[:2]
        # MediaPipe expects RGB
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results = self._detector.process(rgb)

        if not results.detections:
            return None

        # Pick the detection with the highest confidence
        best = max(results.detections, key=lambda d: d.score[0])
        bbox = best.location_data.relative_bounding_box

        # Convert relative coords to absolute pixels with padding
        pad_w = bbox.width * self._padding
        pad_h = bbox.height * self._padding

        x1 = max(0, int((bbox.xmin - pad_w) * w))
        y1 = max(0, int((bbox.ymin - pad_h) * h))
        x2 = min(w, int((bbox.xmin + bbox.width + pad_w) * w))
        y2 = min(h, int((bbox.ymin + bbox.height + pad_h) * h))

        # Validate crop dimensions
        if x2 - x1 < 10 or y2 - y1 < 10:
            logger.warning("Face crop too small ({w}x{h}), skipping", w=x2 - x1, h=y2 - y1)
            return None

        face_crop = rgb[y1:y2, x1:x2]
        face_resized = cv2.resize(face_crop, target_size, interpolation=cv2.INTER_AREA)

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
