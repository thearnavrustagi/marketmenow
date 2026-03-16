from __future__ import annotations

import asyncio
import shutil
import wave
from pathlib import Path
from uuid import uuid4

import numpy as np

from ..tts import SynthesisResult, _mp3_duration_estimate

_MODEL_FILENAME = "kokoro-v1.0.onnx"
_VOICES_FILENAME = "voices-v1.0.bin"


class KokoroTTS:
    """Local neural TTS backend powered by Kokoro (ONNX).

    Requires ``kokoro-onnx`` and ``soundfile`` packages plus the
    model files (``kokoro-v1.0.onnx``, ``voices-v1.0.bin``) located in
    *model_dir*.
    """

    def __init__(
        self,
        output_dir: Path,
        *,
        model_dir: Path | None = None,
        default_voice: str = "af_bella",
        speed: float = 1.0,
        lang: str = "en-us",
        voice_overrides: dict[str, str] | None = None,
        pitch_shift_semitones: dict[str, float] | None = None,
    ) -> None:
        self._output_dir = output_dir / "tts"
        self._output_dir.mkdir(parents=True, exist_ok=True)

        self._default_voice = default_voice
        self._speed = speed
        self._lang = lang
        self._voice_overrides = voice_overrides or {}
        self._pitch_shift_semitones = pitch_shift_semitones or {}

        if model_dir:
            resolved_model_dir = model_dir
        else:
            cwd_models = Path.cwd() / "models"
            resolved_model_dir = cwd_models if cwd_models.is_dir() else Path.cwd()
        model_path = resolved_model_dir / _MODEL_FILENAME
        voices_path = resolved_model_dir / _VOICES_FILENAME

        if not model_path.exists():
            raise FileNotFoundError(
                f"Kokoro model not found at {model_path}. "
                f"Download from https://github.com/thewh1teagle/kokoro-onnx/releases"
            )
        if not voices_path.exists():
            raise FileNotFoundError(
                f"Kokoro voices file not found at {voices_path}. "
                f"Download from https://github.com/thewh1teagle/kokoro-onnx/releases"
            )

        from kokoro_onnx import Kokoro

        self._kokoro = Kokoro(str(model_path), str(voices_path))

    def _resolve_voice(self, voice_id: str) -> str:
        if not voice_id:
            return self._default_voice
        return self._voice_overrides.get(voice_id, voice_id)

    async def synthesize(self, text: str, voice_id: str = "") -> SynthesisResult:
        voice = self._resolve_voice(voice_id)

        loop = asyncio.get_event_loop()
        samples, sample_rate = await loop.run_in_executor(
            None,
            lambda: self._kokoro.create(
                text, voice=voice, speed=self._speed, lang=self._lang
            ),
        )

        pitch_semitones = self._pitch_shift_semitones.get(voice, 0.0)
        if pitch_semitones:
            samples = _pitch_shift(samples, sample_rate, pitch_semitones)

        run_id = uuid4().hex
        wav_path = self._output_dir / f"{run_id}.wav"
        mp3_path = self._output_dir / f"{run_id}.mp3"

        import soundfile as sf

        sf.write(str(wav_path), samples, sample_rate)

        final_path: Path
        if shutil.which("ffmpeg"):
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-i", str(wav_path),
                "-codec:a", "libmp3lame", "-b:a", "192k",
                str(mp3_path),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode == 0:
                wav_path.unlink(missing_ok=True)
                final_path = mp3_path
            else:
                final_path = wav_path
        else:
            final_path = wav_path

        duration = len(samples) / sample_rate

        return SynthesisResult(
            audio_path=final_path,
            duration_seconds=duration,
            word_timings=[],
        )

    async def get_audio_duration(self, audio_path: Path) -> float:
        if audio_path.suffix == ".wav":
            return self._wav_duration(audio_path)
        return _mp3_duration_estimate(audio_path.read_bytes())

    @staticmethod
    def _wav_duration(path: Path) -> float:
        try:
            with wave.open(str(path), "rb") as wf:
                return wf.getnframes() / wf.getframerate()
        except Exception:
            return 2.0


def _pitch_shift(
    samples: np.ndarray, sample_rate: int, semitones: float
) -> np.ndarray:
    """Shift pitch by resampling (no external DSP library required).

    Positive *semitones* raises pitch; negative lowers it.  The output
    length is preserved so timing stays correct.
    """
    factor = 2.0 ** (semitones / 12.0)
    indices = np.arange(0, len(samples), factor)
    indices = indices[indices < len(samples)]
    shifted = np.interp(indices, np.arange(len(samples)), samples).astype(
        samples.dtype
    )
    if len(shifted) < len(samples):
        shifted = np.pad(shifted, (0, len(samples) - len(shifted)))
    else:
        shifted = shifted[: len(samples)]
    return shifted
