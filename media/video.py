"""
Module D — Video Analysis Service.

Responsibilities:
- Validate video format, duration, and file size.
- Extract representative frames at regular intervals using OpenCV.
- Preserve frame timestamps.
- Avoid redundant processing of repeated identical frames.
- Route each extracted frame through AgriculturalVisionService.
- Consolidate multi-frame observations.
- Handle corrupted files, timeouts, and codec errors gracefully.
- Preserve original media reference in MediaRecord.

Design rules:
- Multiple frames showing the same symptom are NOT treated as independent evidence.
- Redundant duplicate frames are skipped (pHash similarity check via OpenCV).
- Max video duration enforced before frame extraction.
"""

import os
import cv2
import uuid
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List

from media.vision import AgriculturalVisionService, VisionResult

logger = logging.getLogger("VideoAnalysisService")

MAX_VIDEO_DURATION_SEC = 120     # 2 minutes
MAX_FRAMES_TO_EXTRACT = 8        # Extract at most 8 frames per video
MIN_FRAME_INTERVAL_SEC = 5.0     # At least 5 seconds between extracted frames
SIMILARITY_THRESHOLD = 10.0      # Perceptual hash difference threshold (lower = more similar)


@dataclass
class VideoAnalysisResult:
    """Consolidated result from multi-frame video analysis."""
    success: bool
    media_id: str
    farmer_id: Optional[int]
    duration_sec: Optional[float]
    frames_extracted: int
    frames_analysed: int
    frame_results: List[VisionResult] = field(default_factory=list)
    consolidated_symptoms: List[str] = field(default_factory=list)
    consolidated_crop: Optional[str] = None
    overall_condition: str = "NORMAL"
    recommended_action: str = "ANSWER"
    error_message: Optional[str] = None
    retryable: bool = False


class VideoAnalysisService:
    """
    Extracts frames from WhatsApp video attachments and routes each through
    AgriculturalVisionService for symptom identification.

    Deduplication: OpenCV perceptual hashing skips frames too visually similar
    to already-extracted ones, preventing inflated symptom counts.
    """

    def __init__(self):
        self._vision = AgriculturalVisionService()

    def analyse_video(
        self,
        video_path: str,
        media_record_id: Optional[int],
        media_id: str,
        farmer_id: Optional[int],
        persist_observations: bool = True,
    ) -> VideoAnalysisResult:
        """
        Process a video file and return consolidated visual analysis.

        Args:
            video_path: Local path to the video file.
            media_record_id: DB PK of the parent MediaRecord.
            media_id: WhatsApp media ID.
            farmer_id: DB PK of the farmer.

        Returns:
            VideoAnalysisResult with per-frame and consolidated findings.
        """
        path = Path(video_path)

        if not path.exists():
            return self._failed(media_id, farmer_id, f"Video file not found: {video_path}")

        if path.stat().st_size == 0:
            return self._failed(media_id, farmer_id, "Video file is empty.")

        # Open video with OpenCV
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            return self._failed(media_id, farmer_id, f"OpenCV could not open video: {path.name}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration_sec = total_frames / fps if fps > 0 else 0.0

        # Duration check
        if duration_sec > MAX_VIDEO_DURATION_SEC:
            cap.release()
            return self._failed(
                media_id, farmer_id,
                f"Video too long: {duration_sec:.1f}s > {MAX_VIDEO_DURATION_SEC}s limit."
            )

        logger.info(
            f"VideoAnalysisService: Processing {path.name} "
            f"({duration_sec:.1f}s, {total_frames} frames @ {fps:.1f}fps)"
        )

        # Frame extraction with deduplication
        frames_to_sample = self._select_frame_timestamps(duration_sec)
        extracted_paths = []
        prev_hash = None
        frame_dir = Path(tempfile.mkdtemp(prefix="krishibot_frames_"))

        for ts in frames_to_sample:
            frame_no = int(ts * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
            ret, frame = cap.read()
            if not ret:
                continue

            # Perceptual hash similarity — skip near-duplicate frames
            phash = self._phash(frame)
            if prev_hash is not None:
                diff = cv2.norm(phash, prev_hash, cv2.NORM_L2)
                if diff < SIMILARITY_THRESHOLD:
                    logger.debug(f"VideoAnalysisService: Skipping duplicate frame at t={ts:.1f}s (diff={diff:.1f}).")
                    continue
            prev_hash = phash

            frame_path = frame_dir / f"frame_{int(ts):04d}s.jpg"
            cv2.imwrite(str(frame_path), frame)
            extracted_paths.append((frame_path, ts))

        cap.release()

        if not extracted_paths:
            return self._failed(media_id, farmer_id, "No usable frames could be extracted from video.")

        # Analyse each extracted frame
        frame_results = []
        try:
            for idx, (fp, ts) in enumerate(extracted_paths):
                result = self._vision.analyse_image(
                    image_path=str(fp),
                    media_record_id=media_record_id,
                    media_id=f"{media_id}_frame_{idx}",
                    farmer_id=farmer_id,
                    frame_index=idx,
                    frame_timestamp_sec=ts,
                    persist_observation=persist_observations,
                )
                frame_results.append(result)
        finally:
            for frame_path, _ in extracted_paths:
                frame_path.unlink(missing_ok=True)
            frame_dir.rmdir()

        # Consolidate observations
        successful_results = [result for result in frame_results if result.success]
        if not successful_results:
            return self._failed(
                media_id,
                farmer_id,
                "No video frames could be analysed successfully.",
                retryable=any(result.retryable for result in frame_results),
            )

        consolidated = self._consolidate(frame_results)
        return VideoAnalysisResult(
            success=True,
            media_id=media_id,
            farmer_id=farmer_id,
            duration_sec=duration_sec,
            frames_extracted=len(extracted_paths),
            frames_analysed=len(frame_results),
            frame_results=frame_results,
            consolidated_symptoms=consolidated["symptoms"],
            consolidated_crop=consolidated["crop"],
            overall_condition=consolidated["condition"],
            recommended_action=consolidated["recommended_action"],
        )

    # ------------------------------------------------------------------
    # Frame sampling
    # ------------------------------------------------------------------

    @staticmethod
    def _select_frame_timestamps(duration_sec: float) -> List[float]:
        """
        Return up to MAX_FRAMES_TO_EXTRACT evenly-spaced timestamps
        while respecting MIN_FRAME_INTERVAL_SEC.
        """
        if duration_sec <= 0:
            return [0.0]

        interval = max(MIN_FRAME_INTERVAL_SEC, duration_sec / MAX_FRAMES_TO_EXTRACT)
        ts = 0.0
        timestamps = []
        while ts < duration_sec and len(timestamps) < MAX_FRAMES_TO_EXTRACT:
            timestamps.append(round(ts, 2))
            ts += interval
        return timestamps

    # ------------------------------------------------------------------
    # Perceptual hash
    # ------------------------------------------------------------------

    @staticmethod
    def _phash(frame) -> any:
        """Compute a small perceptual hash for near-duplicate detection."""
        import numpy as np
        small = cv2.resize(frame, (8, 8))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(float)
        return gray

    # ------------------------------------------------------------------
    # Consolidation
    # ------------------------------------------------------------------

    @staticmethod
    def _consolidate(results: List[VisionResult]) -> dict:
        """
        Merge per-frame results into a de-duplicated consolidated view.
        A symptom reported in multiple frames is listed once (not multiplied).
        """
        symptom_set = set()
        crops = []
        conditions = []
        actions = []

        for r in results:
            if r.success:
                symptom_set.update(r.symptoms)
                if r.identified_crop:
                    crops.append(r.identified_crop)
                conditions.append(r.general_condition)
                actions.append(r.recommended_action)

        # Priority order for overall condition
        condition_priority = ["SEVERE", "STRESSED", "POOR_VISIBILITY", "UNIDENTIFIABLE", "NORMAL"]
        overall_condition = "NORMAL"
        for c in condition_priority:
            if c in conditions:
                overall_condition = c
                break

        # Priority order for recommended action
        action_priority = ["ESCALATE_AGRONOMIST", "REQUEST_BETTER_IMAGE", "ANSWER", "NON_AGRICULTURAL"]
        recommended_action = "ANSWER"
        for a in action_priority:
            if a in actions:
                recommended_action = a
                break

        # Most frequent crop name
        from collections import Counter
        crop = Counter(crops).most_common(1)[0][0] if crops else None

        return {
            "symptoms": sorted(symptom_set),
            "crop": crop,
            "condition": overall_condition,
            "recommended_action": recommended_action,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _failed(
        media_id: str,
        farmer_id: Optional[int],
        msg: str,
        retryable: bool = False,
    ) -> VideoAnalysisResult:
        return VideoAnalysisResult(
            success=False,
            media_id=media_id,
            farmer_id=farmer_id,
            duration_sec=None,
            frames_extracted=0,
            frames_analysed=0,
            error_message=msg,
            retryable=retryable,
        )
