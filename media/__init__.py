"""
Phase 4 — Multimodal Media Processing Package.

Modules:
    ingestion   - Media download, validation, and storage
    stt         - Multilingual speech-to-text transcription
    vision      - Agricultural image analysis
    video       - Video frame extraction and analysis
    orchestrator - Multimodal reasoning integration with Phase 3 pipeline
"""
from .ingestion import MediaIngestionService
from .stt import SpeechToTextService
from .vision import AgriculturalVisionService
from .video import VideoAnalysisService
from .orchestrator import MultimodalOrchestrator

__all__ = [
    "MediaIngestionService",
    "SpeechToTextService",
    "AgriculturalVisionService",
    "VideoAnalysisService",
    "MultimodalOrchestrator",
]
