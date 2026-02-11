"""Video transcription service using faster-whisper.

Optimized for local GPU acceleration (CUDA) with RTX 4060.
Uses faster-whisper for efficient transcription with good accuracy.
"""

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

import numpy as np

from .config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


class TranscriptionService:
    """
    Service for transcribing video/audio files using faster-whisper.

    The extracted text is used for:
    - RAG searchability (search video content)
    - Quiz generation (questions from video material)
    - Student progress assessment (did they understand?)
    - Gap analysis (what topics did they miss from videos)

    Uses faster-whisper with CUDA optimization for RTX 4060:
    - 2-4x faster than openai-whisper
    - Lower memory usage
    - Same accuracy
    - GPU-optimized inference
    """

    def __init__(self):
        self.service = settings.TRANSCRIPTION_SERVICE
        self.api_key = settings.TRANSCRIPTION_API_KEY
        # Backward compatible with older envs that used TRANSCRIPTION_MODEL.
        # Current config uses TRANSCRIPTION_OPENAI_MODEL for OpenAI fallback.
        self.model = getattr(
            settings,
            "TRANSCRIPTION_MODEL",
            getattr(settings, "TRANSCRIPTION_OPENAI_MODEL", "whisper-1"),
        )
        self.language = settings.TRANSCRIPTION_LANGUAGE

        # Model options for faster-whisper:
        # - tiny: fastest, least accurate (~32x speedup)
        # - base: fast, good accuracy (~16x speedup)
        # - small: balanced (~10x speedup)
        # - medium: slower, more accurate (~5x speedup)
        # - large-v2: slowest, most accurate (~2x speedup)
        # - large-v3: best accuracy, slightly slower than v2
        self.model_size = getattr(settings, "TRANSCRIPTION_MODEL_SIZE", "base")
        self.device = getattr(settings, "TRANSCRIPTION_DEVICE", "cuda")  # cuda or cpu
        self.compute_type = getattr(settings, "TRANSCRIPTION_COMPUTE_TYPE", "float16")  # float16 for GPU
        self.timeout_seconds = int(getattr(settings, "TRANSCRIPTION_TIMEOUT_SECONDS", 1200))
        self.max_file_size_mb = int(getattr(settings, "TRANSCRIPTION_MAX_FILE_SIZE_MB", 500))
        self.max_duration_seconds = int(getattr(settings, "TRANSCRIPTION_MAX_DURATION_SECONDS", 7200))
        self.ffprobe_timeout_seconds = int(getattr(settings, "TRANSCRIPTION_FFPROBE_TIMEOUT_SECONDS", 30))
        self.word_timestamps = bool(getattr(settings, "TRANSCRIPTION_WORD_TIMESTAMPS", False))
        self.max_segments_metadata = int(getattr(settings, "TRANSCRIPTION_MAX_SEGMENTS_METADATA", 400))

    async def transcribe(
        self,
        file_path: str,
        language: Optional[str] = None,
    ) -> dict:
        """
        Transcribe a video/audio file.

        Args:
            file_path: Path to the video/audio file
            language: Optional language code (overrides default)

        Returns:
            Dict with:
                - text: Full transcript
                - language: Detected/specified language
                - duration: Audio duration in seconds
                - segments: List of timestamped segments with word-level timestamps
                - service: Which service was used
        """
        try:
            if self.service == "whisper_local":
                coroutine = self._transcribe_with_faster_whisper(file_path, language)
            elif self.service == "openai":
                coroutine = self._transcribe_with_openai(file_path, language)
            else:
                logger.warning(f"Transcription service '{self.service}' not configured")
                return {
                    "text": "",
                    "language": None,
                    "duration": 0,
                    "segments": [],
                    "error": "Transcription service not configured. Set TRANSCRIPTION_SERVICE='whisper_local'",
                }

            return await asyncio.wait_for(coroutine, timeout=self.timeout_seconds)
        except asyncio.TimeoutError:
            logger.error(
                "Transcription timed out for %s after %ss",
                file_path,
                self.timeout_seconds,
            )
            return {
                "text": "",
                "language": None,
                "duration": 0,
                "segments": [],
                "error": (
                    f"Transcription timed out after {self.timeout_seconds}s. "
                    "Try a shorter file or reduce transcription load."
                ),
            }

    async def _transcribe_with_faster_whisper(
        self,
        file_path: str,
        language: Optional[str] = None,
    ) -> dict:
        """
        Transcribe using faster-whisper with GPU optimization.

        faster-whisper advantages:
        - Uses CTranslate2 for efficient inference
        - CUDA optimization for RTX GPUs
        - Lower memory footprint
        - Same model weights as openai-whisper
        """
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            logger.error(
                "faster-whisper not installed. "
                "Run: pip install faster-whisper"
            )
            return {
                "text": "",
                "language": None,
                "duration": 0,
                "segments": [],
                "error": "faster-whisper not installed. Run: pip install faster-whisper",
            }

        try:
            # Check if file exists
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Video file not found: {file_path}")

            # Determine language
            lang = language or self.language
            if lang == "auto" or not lang:
                lang = None  # Auto-detect

            # Check file size to determine processing strategy
            file_size = os.path.getsize(file_path)
            file_size_mb = file_size / (1024 * 1024)
            if file_size_mb > self.max_file_size_mb:
                logger.warning(
                    "Skipping transcription for %s (%.1fMB > max %dMB)",
                    file_path,
                    file_size_mb,
                    self.max_file_size_mb,
                )
                return {
                    "text": "",
                    "language": None,
                    "duration": 0,
                    "segments": [],
                    "error": (
                        f"File too large for local transcription ({file_size_mb:.1f}MB). "
                        f"Configured max is {self.max_file_size_mb}MB."
                    ),
                }

            media_duration = await self._probe_media_duration(file_path)
            if (
                media_duration is not None
                and media_duration > self.max_duration_seconds
            ):
                logger.warning(
                    "Skipping transcription for %s (duration %.1fs > max %ss)",
                    file_path,
                    media_duration,
                    self.max_duration_seconds,
                )
                return {
                    "text": "",
                    "language": None,
                    "duration": media_duration,
                    "segments": [],
                    "error": (
                        f"Video duration ({media_duration:.0f}s) exceeds max "
                        f"allowed transcription duration ({self.max_duration_seconds}s)."
                    ),
                }

            logger.info(
                f"Loading faster-whisper model '{self.model_size}' "
                f"on {self.device} with {self.compute_type}"
            )

            # Initialize model (this is cached, so subsequent calls are fast)
            model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )

            logger.info(f"Transcribing {file_path} ({file_size_mb:.1f}MB)...")

            # For large files, use chunked processing to avoid memory issues
            CHUNK_THRESHOLD_MB = 50  # Process files larger than 50MB in chunks

            if file_size_mb > CHUNK_THRESHOLD_MB:
                return await self._transcribe_large_file_chunked(
                    model, file_path, lang, file_size_mb
                )
            else:
                # Standard processing for smaller files
                return await self._transcribe_standard(
                    model, file_path, lang
                )

        except FileNotFoundError as e:
            logger.error(f"File not found: {e}")
            return {
                "text": "",
                "language": None,
                "duration": 0,
                "segments": [],
                "error": str(e),
            }
        except Exception as e:
            logger.error(f"faster-whisper transcription failed: {e}")
            return {
                "text": "",
                "language": None,
                "duration": 0,
                "segments": [],
                "error": str(e),
            }

    async def _transcribe_standard(
        self,
        model,
        file_path: str,
        language: Optional[str] = None,
    ) -> dict:
        """Standard transcription for smaller files."""
        loop = asyncio.get_event_loop()

        def run_transcription():
            segments_iter, info = model.transcribe(
                file_path,
                language=language,
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(
                    min_silence_duration_ms=500,
                    speech_pad_ms=30,
                ),
                word_timestamps=self.word_timestamps,
            )
            segments_list = list(segments_iter)
            return segments_list, info

        segments_list, info = await loop.run_in_executor(None, run_transcription)
        return self._format_transcription_result(segments_list, info, language)

    async def _transcribe_large_file_chunked(
        self,
        model,
        file_path: str,
        language: Optional[str] = None,
        file_size_mb: float = 0,
    ) -> dict:
        """Transcribe large files in chunks to avoid memory errors."""
        try:
            CHUNK_DURATION_SEC = 30  # Process in 30-second chunks

            logger.info(f"Large file detected ({file_size_mb:.1f}MB), using chunked processing")

            # Get audio duration first
            loop = asyncio.get_event_loop()

            def get_audio_info():
                # Use ffmpeg to extract audio info
                import subprocess
                result = subprocess.run(
                    [
                        "ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "default=noprint_wrappers=1",
                        "-i", file_path
                    ],
                    capture_output=True,
                    text=True,
                    timeout=self.ffprobe_timeout_seconds,
                )
                for line in result.stdout.split('\n'):
                    if "duration=" in line:
                        duration_str = line.split("duration=")[1].split(",")[0]
                        return float(duration_str)
                return 0.0

            duration = await loop.run_in_executor(None, get_audio_info)
            num_chunks = int(np.ceil(duration / CHUNK_DURATION_SEC))

            logger.info(f"Processing in {num_chunks} chunks of {CHUNK_DURATION_SEC}s each")

            all_segments = []
            all_text = []

            # Process each chunk
            for i in range(num_chunks):
                start_time = i * CHUNK_DURATION_SEC
                end_time = min((i + 1) * CHUNK_DURATION_SEC, duration)

                logger.info(f"Processing chunk {i+1}/{num_chunks}: {start_time:.1f}s-{end_time:.1f}s")

                # Extract audio chunk using ffmpeg
                chunk_result = await self._extract_audio_chunk(
                    file_path, start_time, end_time - start_time
                )

                if "error" in chunk_result:
                    logger.warning(f"Failed to extract chunk {i+1}: {chunk_result['error']}")
                    continue

                chunk_path = chunk_result["path"]

                # Transcribe the chunk
                def transcribe_chunk():
                    try:
                        chunk_segments, chunk_info = model.transcribe(
                            chunk_path,
                            language=language,
                            beam_size=5,
                            vad_filter=True,
                            vad_parameters=dict(
                                min_silence_duration_ms=500,
                                speech_pad_ms=30,
                            ),
                            word_timestamps=self.word_timestamps,
                        )
                        return chunk_segments, chunk_info, None
                    except Exception as e:
                        return None, None, str(e)

                chunk_segments, chunk_info, error = await loop.run_in_executor(None, transcribe_chunk)

                # Clean up temp chunk file
                if os.path.exists(chunk_path):
                    os.unlink(chunk_path)

                if error:
                    logger.warning(f"Failed to transcribe chunk {i+1}: {error}")
                    continue

                # Adjust timestamps to global timeline
                time_offset = start_time
                for segment in chunk_segments:
                    segment.start += time_offset
                    segment.end += time_offset
                    all_segments.append(segment)
                    all_text.append(segment.text)

            # Combine all info
            combined_info = type('obj', (object,), {'duration': duration})()
            combined_info.duration = duration
            if all_segments and hasattr(all_segments[0], 'language'):
                combined_info.language = all_segments[0].language

            return self._format_transcription_result(all_segments, combined_info, language)

        except Exception as e:
            logger.error(f"Chunked transcription failed: {e}")
            # Fallback to empty result
            return {
                "text": "",
                "language": language,
                "duration": 0,
                "segments": [],
                "error": f"Chunked processing failed: {str(e)}. File may be too large.",
            }

    async def _probe_media_duration(self, file_path: str) -> Optional[float]:
        """Probe media duration using ffprobe if available."""
        import subprocess

        def run_probe() -> Optional[float]:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    file_path,
                ],
                capture_output=True,
                text=True,
                timeout=self.ffprobe_timeout_seconds,
                check=False,
            )
            if result.returncode != 0:
                return None
            raw = (result.stdout or "").strip()
            if not raw:
                return None
            try:
                return float(raw)
            except ValueError:
                return None

        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(None, run_probe)
        except Exception:
            return None

    async def _extract_audio_chunk(
        self,
        video_path: str,
        start_time: float,
        duration_sec: float,
    ) -> dict:
        """Extract audio chunk from video using ffmpeg."""
        import subprocess

        output_path = tempfile.mktemp(suffix=".wav")

        try:
            # Use ffmpeg to extract audio segment
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    [
                        "ffmpeg", "-y", "-v", "error",
                        "-ss", str(start_time),
                        "-t", str(duration_sec),
                        "-i", video_path,
                        "-vn",  # No video
                        "-acodec", "pcm_s16le",  # PCM 16-bit signed little-endian
                        "-ar", "16000",  # 16kHz sample rate
                        "-ac", "1",  # Mono
                        output_path
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=True,
                ),
            )

            if result.returncode != 0:
                return {"error": f"ffmpeg failed: {result.stderr}"}

            return {"path": output_path}

        except Exception as e:
            return {"error": str(e)}

    def _format_transcription_result(
        self,
        segments_list: list,
        info: Any,
        language: Optional[str] = None,
    ) -> dict:
        """Format transcription result into standard dict."""
        # Build segment data and transcript
        formatted_segments = []
        total_segments = len(segments_list)
        max_segments = max(0, self.max_segments_metadata)
        include_all_segments = max_segments == 0

        if include_all_segments:
            segments_for_metadata = segments_list
        else:
            segments_for_metadata = segments_list[:max_segments]

        for segment in segments_for_metadata:
            # Build segment with word-level details
            words = []
            if self.word_timestamps and hasattr(segment, 'words') and segment.words:
                for word in segment.words:
                    words.append({
                        "word": word.word,
                        "start": word.start,
                        "end": word.end,
                        "probability": word.probability,
                    })

            formatted_segments.append({
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip(),
                "words": words,
            })

        duration = info.duration if hasattr(info, 'duration') else 0
        detected_language = info.language if hasattr(info, 'language') else language

        result = {
            "text": " ".join(getattr(segment, "text", "") for segment in segments_list),
            "language": detected_language,
            "duration": duration,
            "segments": formatted_segments,
            "segments_truncated": (not include_all_segments and total_segments > max_segments),
            "segments_total": total_segments,
            "service": "faster_whisper",
            "model": self.model_size,
            "device": self.device,
        }

        logger.info(
            f"Transcription complete: {len(result['text'])} chars, "
            f"{duration:.1f}s, language={detected_language}"
        )

        return result

    async def _transcribe_with_openai(
        self,
        file_path: str,
        language: Optional[str] = None,
    ) -> dict:
        """
        Transcribe using OpenAI Whisper API (fallback option).

        Requires OpenAI API key. Kept for users who prefer cloud-based.
        """
        try:
            import httpx
        except ImportError:
            return {
                "text": "",
                "language": None,
                "duration": 0,
                "segments": [],
                "error": "httpx not installed. Run: pip install httpx",
            }

        try:
            # Check if file exists
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Video file not found: {file_path}")

            # Get file size (max 25MB for Whisper API)
            file_size = os.path.getsize(file_path)
            if file_size > 25 * 1024 * 1024:
                logger.warning(f"File {file_path} exceeds 25MB limit for Whisper API")
                return {
                    "text": "",
                    "language": None,
                    "duration": 0,
                    "segments": [],
                    "error": "File too large for OpenAI Whisper API (max 25MB). "
                           "Use whisper_local for larger files.",
                }

            # Determine language
            lang = language or self.language
            if lang == "auto":
                lang = None

            # Prepare API request
            url = "https://api.openai.com/v1/audio/transcriptions"

            headers = {
                "Authorization": f"Bearer {self.api_key}",
            }

            filename = Path(file_path).name
            with open(file_path, "rb") as f:
                files = {
                    "file": (filename, f, "video/mp4"),
                }

                data = {
                    "model": self.model,
                }

                if lang:
                    data["language"] = lang

                data["timestamp_granularities[]"] = "word"

                async with httpx.AsyncClient(timeout=300.0) as client:
                    response = await client.post(
                        url,
                        headers=headers,
                        files=files,
                        data=data,
                    )

                    if response.status_code != 200:
                        error_msg = response.text
                        logger.error(f"OpenAI transcription error: {error_msg}")
                        return {
                            "text": "",
                            "language": None,
                            "duration": 0,
                            "segments": [],
                            "error": f"OpenAI API failed: {error_msg}",
                        }

                    result = response.json()

                    return {
                        "text": result.get("text", ""),
                        "language": result.get("language"),
                        "duration": result.get("duration", 0),
                        "segments": result.get("segments", []),
                        "service": "openai",
                    }

        except Exception as e:
            logger.error(f"OpenAI transcription failed: {e}")
            return {
                "text": "",
                "language": None,
                "duration": 0,
                "segments": [],
                "error": str(e),
            }


# Singleton instance with model caching
_transcription_service: Optional[TranscriptionService] = None


def get_transcription_service() -> TranscriptionService:
    """Get or create the transcription service singleton."""
    global _transcription_service
    if _transcription_service is None:
        _transcription_service = TranscriptionService()
    return _transcription_service


async def transcribe_video(
    file_path: str,
    language: Optional[str] = None,
) -> dict:
    """
    Convenience function to transcribe a video file.

    Args:
        file_path: Path to video/audio file
        language: Optional language code (e.g., "en", "es", "auto")

    Returns:
        Dict with transcription results including full text and segments
    """
    service = get_transcription_service()
    return await service.transcribe(file_path, language)
