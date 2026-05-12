"""Emotion Detection Engine — ONNX Runtime inference for facial emotion classification.

This module provides a singleton engine that loads a trained ONNX model once
and exposes a simple `analyze()` method for classifying emotions from face images.

The engine handles:
    - Model loading (lazy singleton)
    - Image preprocessing (normalization to match training transforms)
    - ONNX Runtime inference
    - Softmax conversion to probability distribution
    - Graceful fallback to mock when no model file is available

Architecture:
    MobileNetV2 fine-tuned on FER-2013 → ONNX export → ONNX Runtime inference

Usage:
    from app.modules.biometric.emotion_engine import EmotionEngine

    engine = EmotionEngine.get_instance()
    result = engine.analyze(face_image_rgb)
    # result = {"happiness": 0.82, "sadness": 0.03, ..., "dominant_emotion": "happiness", "confidence": 0.82}
"""

from __future__ import annotations

import base64
import random
import threading
from pathlib import Path

import cv2
import numpy as np
from loguru import logger

from app.modules.biometric.face_detector import FaceDetector

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Must match the order used during training (alphabetical by class folder)
EMOTIONS = ["anger", "disgust", "fear", "happiness", "neutral", "sadness", "surprise"]

# ImageNet normalization values used during training
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# Model file path
MODEL_DIR = Path(__file__).resolve().parent.parent.parent.parent / "models"
MODEL_PATH = MODEL_DIR / "emotion_model.onnx"

# Input image size expected by the model
IMAGE_SIZE = 224


class EmotionEngine:
    """Singleton engine for facial emotion classification using ONNX Runtime.

    The engine is loaded lazily on first use and shared across all requests.
    Thread-safe initialization via double-checked locking.

    Attributes:
        _session: ONNX Runtime inference session (None if model not available).
        _face_detector: MediaPipe face detector instance.
        _use_mock: Whether to fall back to mock results (no model file).
    """

    _instance: EmotionEngine | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        """Initialize the engine. Use get_instance() instead of calling directly."""
        self._session = None
        self._face_detector = FaceDetector()
        self._use_mock = False

        if MODEL_PATH.exists():
            try:
                import onnxruntime as ort
                import shutil
                import tempfile

                # Copy to /tmp to avoid file descriptor issues with Docker volumes
                tmp_model_path = Path(tempfile.gettempdir()) / "emotion_model.onnx"
                if not tmp_model_path.exists():
                    shutil.copy2(MODEL_PATH, tmp_model_path)
                    
                # Check if there is an external data file and copy it too
                data_model_path = MODEL_PATH.with_name(MODEL_PATH.name + ".data")
                tmp_data_path = tmp_model_path.with_name(tmp_model_path.name + ".data")
                if data_model_path.exists() and not tmp_data_path.exists():
                    shutil.copy2(data_model_path, tmp_data_path)

                # Use CPU provider (safe for all environments)
                self._session = ort.InferenceSession(
                    str(tmp_model_path),
                    providers=["CPUExecutionProvider"],
                )
                self._input_name = self._session.get_inputs()[0].name
                self._output_name = self._session.get_outputs()[0].name

                model_size_mb = MODEL_PATH.stat().st_size / (1024 * 1024)
                logger.info(
                    "EmotionEngine loaded ONNX model | path={} size={:.1f}MB",
                    MODEL_PATH,
                    model_size_mb,
                )
            except Exception as exc:
                logger.error("Failed to load ONNX model: {}", exc)
                self._use_mock = True
        else:
            logger.warning(
                "ONNX model not found at {}. Using mock analysis. "
                "Train the model with: python scripts/train_emotion_model.py",
                MODEL_PATH,
            )
            self._use_mock = True

    @classmethod
    def get_instance(cls) -> EmotionEngine:
        """Return the singleton EmotionEngine instance (lazy, thread-safe).

        Returns:
            EmotionEngine: The shared engine instance.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def analyze_base64(self, frame_base64: str) -> dict:
        """Analyze a base64-encoded image frame for facial emotions.

        This is the primary entry point used by the WebSocket handler.

        Args:
            frame_base64: Base64-encoded image (JPEG/PNG), without data URI prefix.

        Returns:
            dict: Emotion scores, dominant emotion, and confidence.
                  Keys: happiness, sadness, anger, fear, disgust, surprise,
                  neutral, dominant_emotion, confidence.
                  Returns mock data if face detection fails or model is unavailable.
        """
        if self._use_mock:
            return self._mock_result()

        try:
            # Decode base64 → bytes → numpy array
            image_bytes = base64.b64decode(frame_base64)
            return self.analyze_bytes(image_bytes)
        except Exception as exc:
            logger.warning("Failed to analyze base64 frame: {}", exc)
            return self._mock_result()

    def analyze_bytes(self, image_bytes: bytes) -> dict:
        """Analyze raw image bytes for facial emotions.

        Args:
            image_bytes: Raw image bytes (JPEG, PNG, etc.).

        Returns:
            dict: Emotion scores and dominant emotion.
        """
        if self._use_mock:
            return self._mock_result()

        # Detect and crop face
        face = self._face_detector.detect_and_crop_from_bytes(
            image_bytes, target_size=(IMAGE_SIZE, IMAGE_SIZE)
        )
        if face is None:
            logger.debug("No face detected in frame")
            return self._neutral_result()

        return self._classify(face)

    def analyze_numpy(self, image_bgr: np.ndarray) -> dict:
        """Analyze an OpenCV BGR image for facial emotions.

        Used by the Celery worker when processing video frames.

        Args:
            image_bgr: Input image as NumPy array in BGR format.

        Returns:
            dict: Emotion scores and dominant emotion.
        """
        if self._use_mock:
            return self._mock_result()

        face = self._face_detector.detect_and_crop(
            image_bgr, target_size=(IMAGE_SIZE, IMAGE_SIZE)
        )
        if face is None:
            return self._neutral_result()

        return self._classify(face)

    def _classify(self, face_rgb: np.ndarray) -> dict:
        """Run ONNX inference on a preprocessed face image.

        Args:
            face_rgb: Face image as NumPy array, shape (224, 224, 3), RGB, uint8.

        Returns:
            dict: Emotion probability distribution and dominant emotion.
        """
        # Preprocess: normalize to match training transforms
        img = face_rgb.astype(np.float32) / 255.0
        img = (img - IMAGENET_MEAN) / IMAGENET_STD

        # Convert HWC → CHW and add batch dimension → (1, 3, 224, 224)
        img = np.transpose(img, (2, 0, 1))
        img = np.expand_dims(img, axis=0)

        # Run inference
        logits = self._session.run(
            [self._output_name],
            {self._input_name: img},
        )[0]

        # Apply softmax to get probabilities
        probs = self._softmax(logits[0])

        # Build result dict
        result = {emotion: round(float(prob), 4) for emotion, prob in zip(EMOTIONS, probs)}
        dominant_idx = int(np.argmax(probs))
        result["dominant_emotion"] = EMOTIONS[dominant_idx]
        result["confidence"] = round(float(probs[dominant_idx]), 4)

        return result

    @staticmethod
    def _softmax(logits: np.ndarray) -> np.ndarray:
        """Compute softmax probabilities from raw logits.

        Args:
            logits: Raw model output scores.

        Returns:
            Probability distribution summing to 1.0.
        """
        exp = np.exp(logits - np.max(logits))
        return exp / exp.sum()

    @staticmethod
    def _mock_result() -> dict:
        """Generate random mock emotion scores for development/testing.

        Returns:
            dict: Random emotion scores normalized to sum to 1.0.
        """
        scores = [random.random() for _ in EMOTIONS]
        total = sum(scores)
        normalized = [round(s / total, 4) for s in scores]
        dominant_idx = normalized.index(max(normalized))
        result = {emotion: score for emotion, score in zip(EMOTIONS, normalized)}
        result["dominant_emotion"] = EMOTIONS[dominant_idx]
        result["confidence"] = normalized[dominant_idx]
        return result

    @staticmethod
    def _neutral_result() -> dict:
        """Return a neutral result when no face is detected.

        This avoids sending random data when the subject is not visible.

        Returns:
            dict: Neutral-dominant emotion scores.
        """
        result = {emotion: 0.0 for emotion in EMOTIONS}
        result["neutral"] = 1.0
        result["dominant_emotion"] = "neutral"
        result["confidence"] = 1.0
        return result
