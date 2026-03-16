from __future__ import annotations

import asyncio
import shutil
import struct
import wave
from pathlib import Path
from uuid import uuid4

from ..tts import SynthesisResult, WordTiming, _mp3_duration_estimate


class LocalTTS:
    """Offline TTS fallback using macOS ``say`` or ``espeak-ng``.

    Produces a WAV via the system TTS, then converts to MP3 with ffmpeg
    if available (falls back to raw WAV otherwise).  Useful for testing
    the pipeline without any API keys.
    """

    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir / "tts"
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._engine = self._detect_engine()

    async def synthesize(self, text: str, voice_id: str = "") -> SynthesisResult:
        run_id = uuid4().hex
        wav_path = self._output_dir / f"{run_id}.wav"
        mp3_path = self._output_dir / f"{run_id}.mp3"

        if self._engine == "say":
            cmd = ["say", "-o", str(wav_path), "--data-format=LEI16@22050"]
            if voice_id:
                cmd.extend(["-v", voice_id])
            cmd.append(text)
            await self._run(cmd)
        elif self._engine == "espeak-ng":
            cmd = ["espeak-ng", "-w", str(wav_path)]
            if voice_id:
                cmd.extend(["-v", voice_id])
            cmd.append(text)
            await self._run(cmd)
        else:
            self._generate_silence(wav_path, duration_sec=max(1.0, len(text) * 0.06))

        final_path: Path
        if shutil.which("ffmpeg"):
            await self._run([
                "ffmpeg", "-y", "-i", str(wav_path),
                "-codec:a", "libmp3lame", "-b:a", "128k",
                str(mp3_path),
            ])
            wav_path.unlink(missing_ok=True)
            final_path = mp3_path
        else:
            final_path = wav_path

        duration = self._wav_duration(final_path) if final_path.suffix == ".wav" else _mp3_duration_estimate(final_path.read_bytes())

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
    def _detect_engine() -> str:
        if shutil.which("say"):
            return "say"
        if shutil.which("espeak-ng"):
            return "espeak-ng"
        return "silence"

    @staticmethod
    async def _run(cmd: list[str]) -> None:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{stderr.decode()}")

    @staticmethod
    def _generate_silence(path: Path, duration_sec: float) -> None:
        """Write a silent WAV file as a last-resort fallback."""
        sample_rate = 22050
        n_frames = int(sample_rate * duration_sec)
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(b"\x00\x00" * n_frames)

    @staticmethod
    def _wav_duration(path: Path) -> float:
        try:
            with wave.open(str(path), "rb") as wf:
                return wf.getnframes() / wf.getframerate()
        except Exception:
            return 2.0
