from __future__ import annotations

import asyncio
import json
import math
import os
from pathlib import Path
from uuid import uuid4

from jinja2 import Environment

from marketmenow.models.content import MediaAsset, VideoPost

from ..grading.models import RubricItem
from ..grading.service import SimpleGradingService
from ..settings import InstagramSettings
from .models import AudioType, BeatDefinition, ReelScript, ResolvedBeat
from .script import ReelScriptGenerator
from .template_loader import ReelTemplateLoader
from .tts import TTSProvider, TTSService
from .tts_backends import create_tts_service

_JINJA_ENV = Environment()


def _ensure_vertex_credentials(settings: InstagramSettings) -> None:
    """Export GOOGLE_APPLICATION_CREDENTIALS so the genai SDK picks it up."""
    creds = settings.google_application_credentials
    if creds and creds.exists():
        os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", str(creds.resolve()))


def _merge_default_visual(
    beat_visual: dict[str, object],
    default_visual: dict[str, object],
) -> dict[str, object]:
    """Return beat visual with defaults filled in for missing keys."""
    merged = dict(default_visual)
    merged.update(beat_visual)
    return merged


class ReelOrchestrator:
    """End-to-end pipeline: template + assignment image -> rendered .mp4 VideoPost."""

    def __init__(self, settings: InstagramSettings) -> None:
        self._settings = settings
        self._output_dir = settings.output_dir / "reels"
        self._output_dir.mkdir(parents=True, exist_ok=True)

        _ensure_vertex_credentials(settings)

        self._loader = ReelTemplateLoader()
        self._grader = SimpleGradingService(
            project=settings.vertex_ai_project,
            location=settings.vertex_ai_location,
        )
        self._script_gen = ReelScriptGenerator(
            grading_service=self._grader,
            vertex_project=settings.vertex_ai_project,
            vertex_location=settings.vertex_ai_location,
        )
        kokoro_voice_overrides: dict[str, str] | None = None
        kokoro_pitch_shift: dict[str, float] | None = None
        if settings.tts_provider == "kokoro":
            kokoro_voice_overrides = {
                "gradeasy": settings.kokoro_gradeasy_voice,
                "kid": settings.kokoro_child_voice,
            }
            kokoro_pitch_shift = {
                settings.kokoro_child_voice: settings.kokoro_child_pitch_semitones,
            }

        self._tts: TTSService = create_tts_service(
            provider=TTSProvider(settings.tts_provider),
            output_dir=settings.output_dir,
            elevenlabs_api_key=settings.elevenlabs_api_key,
            elevenlabs_voice_id=settings.elevenlabs_voice_id,
            openai_api_key=settings.openai_api_key,
            openai_voice=settings.openai_tts_voice,
            openai_model=settings.openai_tts_model,
            kokoro_model_dir=(
                Path(settings.kokoro_model_dir) if settings.kokoro_model_dir else None
            ),
            kokoro_default_voice=settings.kokoro_teacher_voice,
            kokoro_speed=settings.kokoro_speed,
            kokoro_lang=settings.kokoro_lang,
            kokoro_voice_overrides=kokoro_voice_overrides,
            kokoro_pitch_shift_semitones=kokoro_pitch_shift,
        )
        self._remotion_dir = settings.remotion_project_dir

    async def create_reel(
        self,
        assignment_image: Path | None = None,
        template_id: str = "can_ai_grade_this",
        rubric_items: list[RubricItem] | None = None,
        caption: str = "",
        hashtags: list[str] | None = None,
        reaction_image: Path | None = None,
        comment_username: str = "",
        comment_avatar: Path | None = None,
        comment_text: str = "",
        student_name: str = "",
    ) -> VideoPost:
        """Full pipeline: grade -> script -> TTS -> render -> VideoPost model.

        When *assignment_image* is ``None`` and the template has a ``worksheet``
        config, the pipeline auto-generates a worksheet and fills it in.
        """
        template = self._loader.load(template_id)

        extra_services: dict[str, object] = {
            "output_dir": str(self._output_dir),
            "vertex_project": self._settings.vertex_ai_project,
            "vertex_location": self._settings.vertex_ai_location,
        }
        if template.worksheet is not None:
            extra_services["worksheet_config"] = template.worksheet

        variables, resolved_beats = await self._script_gen.generate(
            template=template,
            assignment_image=assignment_image,
            rubric_items=rubric_items,
            extra_services=extra_services,
        )

        if reaction_image and reaction_image.exists():
            variables["reaction_image"] = str(reaction_image.resolve())
        elif not variables.get("reaction_image"):
            picked = self._pick_reaction_image()
            if picked:
                variables["reaction_image"] = str(picked.resolve())

        if comment_username:
            variables["comment_username"] = comment_username
        elif not variables.get("comment_username") or variables["comment_username"] == "student":
            variables["comment_username"] = self._pick_random_username()
        if comment_text:
            variables["comment_text"] = comment_text
        elif not variables.get("comment_text") and template.hook_lines:
            import random

            variables["comment_text"] = random.choice(template.hook_lines)
        if comment_avatar and comment_avatar.exists():
            variables["comment_avatar"] = str(comment_avatar.resolve())
        elif not variables.get("comment_avatar"):
            picked_avatar = self._pick_random_avatar()
            if picked_avatar:
                variables["comment_avatar"] = str(picked_avatar.resolve())

        variables["student_name"] = (
            student_name or comment_username or variables.get("comment_username", "Student")
        )

        if self._settings.tts_provider == "kokoro":
            variables["gradeasy_voice_id"] = "gradeasy"
            variables["kid_voice_id"] = "kid"
        elif self._settings.tts_provider == "local":
            variables["gradeasy_voice_id"] = self._settings.local_tts_gradeasy_voice
            variables["kid_voice_id"] = self._settings.local_tts_kid_voice
        else:
            variables["gradeasy_voice_id"] = (
                self._settings.elevenlabs_gradeasy_voice_id or self._settings.elevenlabs_voice_id
            )
            variables["kid_voice_id"] = self._settings.elevenlabs_voice_id

        resolved_beats = self._script_gen._resolve_beats(template.beats, variables)

        # Merge default_visual from template into each beat
        if template.default_visual:
            resolved_beats = [
                beat.model_copy(
                    update={"visual": _merge_default_visual(beat.visual, template.default_visual)}
                )
                for beat in resolved_beats
            ]

        beats_with_audio = await self._synthesize_all(resolved_beats, template.fps)

        reel_script = ReelScript(
            template_id=template.id,
            fps=template.fps,
            aspect_ratio=template.aspect_ratio,
            composition_id=template.composition_id,
            total_duration_frames=sum(b.duration_frames for b in beats_with_audio),
            beats=beats_with_audio,
            variables=variables,
        )

        output_path = await self._render(reel_script)

        video_asset = MediaAsset(
            uri=str(output_path.resolve()),
            mime_type="video/mp4",
            width=1080,
            height=1920,
        )

        # Render caption from template's caption_template or use caller-provided / default
        final_caption = caption
        if not final_caption and template.caption_template:
            try:
                tmpl = _JINJA_ENV.from_string(template.caption_template)
                final_caption = tmpl.render(**variables)
            except Exception:
                final_caption = template.caption_template

        if not final_caption:
            final_caption = (
                "Can our AI grade this?\n"
                "\n"
                "Drop your assignments in the comments and we'll grade them too\n"
                "\n"
                "Try Gradeasy now at gradeasy.ai"
            )

        final_hashtags = (
            hashtags
            or template.hashtags
            or [
                "AIGrading",
                "EdTech",
                "Gradeasy",
                "AI",
                "SchoolHacks",
            ]
        )

        return VideoPost(
            video=video_asset,
            caption=final_caption,
            hashtags=final_hashtags,
        )

    async def _synthesize_all(
        self,
        beats: list[BeatDefinition],
        fps: int,
    ) -> list[ResolvedBeat]:
        """Synthesize TTS / resolve SFX for each beat, computing frame durations."""
        resolved: list[ResolvedBeat] = []

        for beat in beats:
            audio_path = ""

            if beat.audio.type == AudioType.TTS and beat.audio.text:
                synth = await self._tts.synthesize(beat.audio.text, voice_id=beat.audio.voice)
                audio_path = str(synth.audio_path.resolve())
                audio_duration = synth.duration_seconds
            elif beat.audio.type == AudioType.SFX and beat.audio.file:
                sfx_path = self._resolve_sfx_path(beat.audio.file)
                audio_path = str(sfx_path)
                audio_duration = await self._tts.get_audio_duration(sfx_path)
            else:
                audio_duration = 0.0

            if beat.duration == "fixed" and beat.fixed_seconds > 0:
                duration_sec = beat.fixed_seconds
            elif audio_duration > 0:
                duration_sec = audio_duration + beat.pad_seconds
            else:
                duration_sec = 2.0 + beat.pad_seconds

            duration_frames = max(1, math.ceil(duration_sec * fps))

            subtitle = beat.audio.text if beat.audio.type == AudioType.TTS else ""

            resolved.append(
                ResolvedBeat(
                    id=beat.id,
                    scene=beat.scene,
                    audio_path=audio_path,
                    duration_seconds=duration_sec,
                    duration_frames=duration_frames,
                    visual=beat.visual,
                    subtitle=subtitle,
                    entry_transition=beat.entry_transition,
                    exit_transition=beat.exit_transition,
                )
            )

        return resolved

    def _pick_reaction_image(self) -> Path | None:
        """Pick a random reaction image from the assets/reactions/ directory."""
        import random

        reactions_dir = Path(__file__).resolve().parent / "assets" / "reactions"
        if not reactions_dir.is_dir():
            return None
        images = [
            f
            for f in reactions_dir.iterdir()
            if f.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp"}
        ]
        return random.choice(images) if images else None

    @staticmethod
    def _pick_random_username() -> str:
        import random

        usernames_file = Path(__file__).resolve().parent / "assets" / "usernames.txt"
        if not usernames_file.exists():
            return "student"
        names = [line.strip() for line in usernames_file.read_text().splitlines() if line.strip()]
        return random.choice(names) if names else "student"

    @staticmethod
    def _pick_random_avatar() -> Path | None:
        import random

        avatars_dir = Path(__file__).resolve().parent / "assets" / "avatars"
        if not avatars_dir.is_dir():
            return None
        images = [
            f
            for f in avatars_dir.iterdir()
            if f.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        ]
        return random.choice(images) if images else None

    def _resolve_sfx_path(self, relative_path: str) -> Path:
        """Resolve an SFX file path relative to the reels package directory.

        Falls back to generating a short silent WAV if the file is missing
        (allows the pipeline to run even when SFX assets are absent).
        """
        base = Path(__file__).resolve().parent
        candidate = base / relative_path
        if candidate.exists():
            return candidate
        absolute = Path(relative_path)
        if absolute.exists():
            return absolute

        import wave

        fallback = self._output_dir / f"missing_sfx_{Path(relative_path).stem}.wav"
        if not fallback.exists():
            fallback.parent.mkdir(parents=True, exist_ok=True)
            sample_rate = 22050
            n_frames = int(sample_rate * 0.5)
            with wave.open(str(fallback), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(b"\x00\x00" * n_frames)
        return fallback

    async def _render(self, script: ReelScript) -> Path:
        """Write props JSON and invoke Remotion CLI to render the video."""
        import shutil

        run_id = uuid4().hex[:8]
        public_assets = self._remotion_dir / "public" / "assets" / run_id
        public_assets.mkdir(parents=True, exist_ok=True)

        def _stage_file(file_path: str) -> str:
            """Copy a file into public/assets/<run_id>/ and return relative path."""
            src = Path(file_path)
            if not src.exists():
                return file_path
            dest = public_assets / src.name
            shutil.copy2(src, dest)
            return f"assets/{run_id}/{src.name}"

        _image_keys = {"image", "reaction_image", "avatar", "comment_image", "background_image"}

        def _rewrite_visual(visual: dict[str, object]) -> dict[str, object]:
            """Replace absolute file paths in visual props with public-relative paths."""
            out: dict[str, object] = {}
            for k, v in visual.items():
                if k in _image_keys and isinstance(v, str) and v and Path(v).is_absolute():
                    out[k] = _stage_file(v)
                else:
                    out[k] = v
            return out

        def _transition_to_dict(t: object) -> dict[str, object]:
            if hasattr(t, "model_dump"):
                return t.model_dump()  # type: ignore[union-attr]
            return {"type": "none", "durationFrames": 0, "direction": "", "easing": ""}

        beat_props: list[dict[str, object]] = []
        for b in script.beats:
            audio_src = ""
            if b.audio_path:
                audio_src = _stage_file(b.audio_path)

            entry_t = _transition_to_dict(b.entry_transition)
            exit_t = _transition_to_dict(b.exit_transition)
            # Normalize Python snake_case to JS camelCase
            entry_t = {
                "type": entry_t.get("type", "none"),
                "durationFrames": entry_t.get("duration_frames", 0),
                "direction": entry_t.get("direction", ""),
                "easing": entry_t.get("easing", ""),
            }
            exit_t = {
                "type": exit_t.get("type", "none"),
                "durationFrames": exit_t.get("duration_frames", 0),
                "direction": exit_t.get("direction", ""),
                "easing": exit_t.get("easing", ""),
            }

            beat_props.append(
                {
                    "id": b.id,
                    "scene": b.scene,
                    "audioSrc": audio_src,
                    "durationFrames": b.duration_frames,
                    "visual": _rewrite_visual(b.visual),
                    "subtitle": b.subtitle,
                    "entryTransition": entry_t,
                    "exitTransition": exit_t,
                }
            )

        props = {"fps": script.fps, "beats": beat_props}

        props_path = self._output_dir / f"props_{run_id}.json"
        props_path.write_text(json.dumps(props, indent=2, default=str))

        output_path = self._output_dir / f"reel_{run_id}.mp4"

        composition_id = script.composition_id or "ReelFromTemplate"

        cmd = [
            "npx",
            "remotion",
            "render",
            "src/index.ts",
            composition_id,
            str(output_path.resolve()),
            "--props",
            str(props_path.resolve()),
            "--width",
            "1080",
            "--height",
            "1920",
            "--codec",
            "h264",
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(self._remotion_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(
                f"Remotion render failed (exit {proc.returncode}):\n{stderr.decode()}"
            )

        return output_path
