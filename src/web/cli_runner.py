from __future__ import annotations

import asyncio
import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from web.events import ProgressEvent, hub

logger = logging.getLogger(__name__)

UV_BIN = "uv"

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\r")

# ── Progress pattern matchers ────────────────────────────────────────

_PATTERNS: list[tuple[re.Pattern[str], Callable[[re.Match[str]], ProgressEvent]]] = [
    # Twitter / Reddit wait
    (
        re.compile(r"[Ww]aiting\s+(\d+)\s*s", re.IGNORECASE),
        lambda m: ProgressEvent(
            event_type="wait",
            message=m.group(0),
            phase="waiting",
            wait_seconds=int(m.group(1)),
        ),
    ),
    # Generating reply N/M or comment N/M
    (
        re.compile(r"[Gg]enerating\s+(?:reply|comment)\s+(\d+)\s*/\s*(\d+)"),
        lambda m: ProgressEvent(
            event_type="progress",
            message=m.group(0),
            phase="generation",
            current=int(m.group(1)),
            total=int(m.group(2)),
        ),
    ),
    # Generic "Generating" without counts
    (
        re.compile(r"[Gg]enerating\s+(reply|comment|thread|reel|carousel|post)", re.IGNORECASE),
        lambda m: ProgressEvent(
            event_type="phase",
            message=m.group(0),
            phase="generation",
        ),
    ),
    # Posted reply/comment N/M
    (
        re.compile(r"[Pp]osted\s+(?:reply|comment)\s+(\d+)\s*/\s*(\d+)"),
        lambda m: ProgressEvent(
            event_type="progress",
            message=m.group(0),
            phase="posting",
            current=int(m.group(1)),
            total=int(m.group(2)),
        ),
    ),
    # Generic posted
    (
        re.compile(r"[Pp]osted?\s+(?:reply|comment|content|thread|successfully)", re.IGNORECASE),
        lambda m: ProgressEvent(
            event_type="phase",
            message=m.group(0),
            phase="posting",
        ),
    ),
    # Discovery: found N posts / Discovered N posts
    (
        re.compile(r"[Dd]iscover(?:y|ed)[:\s]+.*?(\d+)\s+posts?"),
        lambda m: ProgressEvent(
            event_type="phase",
            message=m.group(0),
            phase="discovery",
            total=int(m.group(1)),
        ),
    ),
    # Discovery start
    (
        re.compile(r"[Dd]iscovering", re.IGNORECASE),
        lambda m: ProgressEvent(
            event_type="phase",
            message=m.group(0),
            phase="discovery",
        ),
    ),
    # Engagement/generation complete
    (
        re.compile(r"(?:engagement|generation|pipeline)\s+complete", re.IGNORECASE),
        lambda m: ProgressEvent(
            event_type="done",
            message=m.group(0),
        ),
    ),
    # Saved N replies/comments
    (
        re.compile(r"[Ss]aved\s+(\d+)\s+(?:replies|comments)\s+to\s+(\S+)"),
        lambda m: ProgressEvent(
            event_type="done",
            message=m.group(0),
            total=int(m.group(1)),
        ),
    ),
    # Handles N/M  Hashtags N/M  Posts N (Rich progress subtitle)
    (
        re.compile(r"Handles\s+(\d+)/(\d+)\s+Hashtags\s+(\d+)/(\d+)\s+Posts\s+(\d+)"),
        lambda m: ProgressEvent(
            event_type="progress",
            message=m.group(0),
            phase="discovery",
            current=int(m.group(1)) + int(m.group(3)),
            total=int(m.group(2)) + int(m.group(4)),
        ),
    ),
    # Error / traceback / exception
    (
        re.compile(r"(?:ERROR|Traceback|Exception|FAILED|CAPTCHA)", re.IGNORECASE),
        lambda m: ProgressEvent(
            event_type="error",
            message=m.group(0),
        ),
    ),
]


def _parse_progress(line: str) -> ProgressEvent | None:
    """Try to extract a structured progress event from a log line."""
    for pattern, factory in _PATTERNS:
        m = pattern.search(line)
        if m:
            return factory(m)
    return None


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


@dataclass(frozen=True)
class CliResult:
    exit_code: int
    stdout: str
    stderr: str
    output_files: list[str] = field(default_factory=list)


def _find_output_files(stdout: str, stderr: str, output_dir: str | None) -> list[str]:
    """Scan CLI output for generated file paths."""
    files: list[str] = []

    combined = stdout + "\n" + stderr
    for match in re.finditer(
        r"(?:saved|wrote|created|output|generated|rendered)[:\s]+([^\s]+\.(?:mp4|png|jpg|jpeg|webp|csv|json))",
        combined,
        re.IGNORECASE,
    ):
        candidate = match.group(1).strip("'\"")
        if os.path.isfile(candidate):
            files.append(candidate)

    if output_dir and os.path.isdir(output_dir):
        for entry in sorted(
            Path(output_dir).rglob("*"), key=lambda p: p.stat().st_mtime, reverse=True
        ):
            if entry.is_file() and entry.suffix.lower() in {
                ".mp4",
                ".png",
                ".jpg",
                ".jpeg",
                ".webp",
                ".csv",
                ".json",
            }:
                path_str = str(entry)
                if path_str not in files:
                    files.append(path_str)

    return files


async def run_cli(
    command_parts: list[str],
    *,
    output_dir: str | None = None,
    timeout: float = 600,
    cwd: str | None = None,
) -> CliResult:
    """Execute an mmn CLI command via subprocess and capture results."""
    full_cmd = [UV_BIN, "run", *command_parts]
    logger.info("Running: %s", " ".join(full_cmd))

    proc = await asyncio.create_subprocess_exec(
        *full_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.communicate()
        return CliResult(
            exit_code=-1,
            stdout="",
            stderr=f"Command timed out after {timeout}s",
        )

    stdout = stdout_bytes.decode(errors="replace")
    stderr = stderr_bytes.decode(errors="replace")
    exit_code = proc.returncode or 0

    output_files = _find_output_files(stdout, stderr, output_dir) if exit_code == 0 else []

    logger.info(
        "Finished (exit=%d): %s | files=%s",
        exit_code,
        " ".join(full_cmd),
        output_files,
    )

    return CliResult(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        output_files=output_files,
    )


# ── Streaming variant ────────────────────────────────────────────────


async def _read_stream(
    stream: asyncio.StreamReader,
    item_id: UUID,
    lines_acc: list[str],
    is_stderr: bool,
) -> None:
    """Read a subprocess stream line-by-line, publishing to the EventHub."""
    while True:
        raw = await stream.readline()
        if not raw:
            break
        line = _strip_ansi(raw.decode(errors="replace")).rstrip("\n\r")
        if not line:
            continue
        lines_acc.append(line)

        progress = _parse_progress(line)
        if progress:
            hub.publish(item_id, progress)

        hub.publish(
            item_id,
            ProgressEvent(
                event_type="stderr" if is_stderr else "log",
                message=line,
            ),
        )


async def run_cli_streaming(
    command_parts: list[str],
    *,
    item_id: UUID,
    output_dir: str | None = None,
    timeout: float = 3600,
    cwd: str | None = None,
) -> CliResult:
    """Like ``run_cli`` but streams output line-by-line to the EventHub.

    Long-running commands (Twitter ``all``, Reddit ``reply``) benefit from
    the longer default timeout (1 hour) and real-time progress events.
    """
    full_cmd = [UV_BIN, "run", *command_parts]
    logger.info("Running (streaming): %s", " ".join(full_cmd))
    hub.publish(
        item_id, ProgressEvent(event_type="phase", message="Starting: " + " ".join(command_parts))
    )

    proc = await asyncio.create_subprocess_exec(
        *full_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )

    assert proc.stdout is not None
    assert proc.stderr is not None

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    try:
        await asyncio.wait_for(
            asyncio.gather(
                _read_stream(proc.stdout, item_id, stdout_lines, is_stderr=False),
                _read_stream(proc.stderr, item_id, stderr_lines, is_stderr=True),
            ),
            timeout=timeout,
        )
        await proc.wait()
    except TimeoutError:
        proc.kill()
        await proc.communicate()
        hub.publish(
            item_id,
            ProgressEvent(event_type="error", message=f"Command timed out after {timeout}s"),
        )
        return CliResult(exit_code=-1, stdout="", stderr=f"Command timed out after {timeout}s")

    stdout = "\n".join(stdout_lines)
    stderr = "\n".join(stderr_lines)
    exit_code = proc.returncode or 0

    output_files = _find_output_files(stdout, stderr, output_dir) if exit_code == 0 else []

    if exit_code == 0:
        hub.publish(
            item_id, ProgressEvent(event_type="done", message="Command completed successfully")
        )
    else:
        hub.publish(
            item_id,
            ProgressEvent(event_type="error", message=f"Exited with code {exit_code}"),
        )

    logger.info(
        "Finished streaming (exit=%d): %s | files=%s", exit_code, " ".join(full_cmd), output_files
    )

    return CliResult(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        output_files=output_files,
    )


# ── Platform metadata (JSON-serializable, sent to templates) ─────────

PLATFORM_META: dict[str, dict[str, dict]] = {
    "instagram": {
        "reel": {
            "label": "Instagram Reel",
            "modality": "video",
            "params": [
                {
                    "name": "template",
                    "type": "text",
                    "required": False,
                    "help": "Template name (leave blank for default)",
                },
                {
                    "name": "assignment",
                    "type": "textarea",
                    "required": False,
                    "help": "Student assignment text",
                },
                {"name": "rubric", "type": "textarea", "required": False, "help": "Grading rubric"},
                {"name": "caption", "type": "text", "required": False, "help": "Caption text"},
                {
                    "name": "hashtags",
                    "type": "text",
                    "required": False,
                    "help": "Comma-separated hashtags",
                },
                {
                    "name": "tts",
                    "type": "select",
                    "required": False,
                    "options": ["elevenlabs", "openai", "kokoro"],
                    "help": "TTS provider",
                },
            ],
        },
        "carousel": {
            "label": "Instagram Carousel",
            "modality": "image",
            "params": [
                {"name": "caption", "type": "text", "required": False, "help": "Caption text"},
                {
                    "name": "hashtags",
                    "type": "text",
                    "required": False,
                    "help": "Comma-separated hashtags",
                },
            ],
        },
    },
    "linkedin": {
        "post": {
            "label": "LinkedIn Post",
            "modality": "text_post",
            "params": [
                {
                    "name": "text",
                    "type": "textarea",
                    "required": False,
                    "help": "Post text (leave blank for AI-generated)",
                },
                {
                    "name": "hashtags",
                    "type": "text",
                    "required": False,
                    "help": "Comma-separated hashtags",
                },
                {"name": "image", "type": "text", "required": False, "help": "Path to image file"},
            ],
        },
    },
    "twitter": {
        "all": {
            "label": "Twitter All (Replies + Thread)",
            "modality": "thread",
            "params": [
                {
                    "name": "max_replies",
                    "type": "number",
                    "required": False,
                    "help": "Max replies (0 = default)",
                },
            ],
        },
        "thread": {
            "label": "Twitter Thread",
            "modality": "thread",
            "params": [
                {
                    "name": "topic",
                    "type": "textarea",
                    "required": True,
                    "help": "Thread topic / prompt",
                },
            ],
        },
        "engage": {
            "label": "Twitter Replies",
            "modality": "reply",
            "params": [
                {
                    "name": "max_replies",
                    "type": "number",
                    "required": False,
                    "help": "Max replies to generate",
                },
            ],
        },
    },
    "reddit": {
        "engage": {
            "label": "Reddit Comments",
            "modality": "reply",
            "params": [
                {
                    "name": "max_comments",
                    "type": "number",
                    "required": False,
                    "help": "Max comments to generate",
                },
            ],
        },
    },
    "email": {
        "send": {
            "label": "Email Outreach",
            "modality": "direct_message",
            "params": [
                {
                    "name": "template",
                    "type": "text",
                    "required": True,
                    "help": "Path to Jinja2 email template",
                },
                {
                    "name": "file",
                    "type": "text",
                    "required": True,
                    "help": "Path to recipients CSV",
                },
                {"name": "subject", "type": "text", "required": True, "help": "Email subject line"},
            ],
        },
    },
    "youtube": {
        "short": {
            "label": "YouTube Short",
            "modality": "video",
            "params": [
                {
                    "name": "title",
                    "type": "text",
                    "required": False,
                    "help": "Video title (leave blank for auto-generated)",
                },
                {
                    "name": "description",
                    "type": "textarea",
                    "required": False,
                    "help": "Video description",
                },
                {
                    "name": "hashtags",
                    "type": "text",
                    "required": False,
                    "help": "Comma-separated hashtags (#shorts is always added)",
                },
                {
                    "name": "privacy",
                    "type": "select",
                    "required": False,
                    "options": ["private", "unlisted", "public"],
                    "help": "Privacy status",
                },
            ],
        },
    },
}

# ── Command builders (not serializable, used server-side only) ───────

CommandBuilder = Callable[[dict, str], list[str]]


def _build_reel_generate(params: dict, output_dir: str) -> list[str]:
    cmd = ["mmn", "reel", "create", "--output-dir", output_dir]
    if params.get("template"):
        cmd.extend(["--template", params["template"]])
    if params.get("assignment"):
        cmd.extend(["--assignment", params["assignment"]])
    if params.get("rubric"):
        cmd.extend(["--rubric", params["rubric"]])
    if params.get("caption"):
        cmd.extend(["--caption", params["caption"]])
    if params.get("hashtags"):
        cmd.extend(["--hashtags", params["hashtags"]])
    if params.get("tts"):
        cmd.extend(["--tts", params["tts"]])
    return cmd


def _build_reel_publish(params: dict, output_dir: str) -> list[str]:
    cmd = _build_reel_generate(params, output_dir)
    cmd.append("--publish")
    return cmd


def _build_carousel_generate(params: dict, output_dir: str) -> list[str]:
    return ["mmn", "carousel", "generate", "--output-dir", output_dir]


def _build_carousel_publish(params: dict, output_dir: str) -> list[str]:
    cmd = _build_carousel_generate(params, output_dir)
    cmd.append("--publish")
    return cmd


def _build_linkedin_generate(params: dict, _output_dir: str) -> list[str]:
    return ["mmn", "linkedin", "all", "--count", "1", "--dry-run"]


def _build_linkedin_publish(params: dict, _output_dir: str) -> list[str]:
    if params.get("text") or params.get("image"):
        cmd = ["mmn", "linkedin", "post"]
        if params.get("text"):
            cmd.extend(["--text", params["text"]])
        if params.get("hashtags"):
            cmd.extend(["--hashtags", params["hashtags"]])
        if params.get("image"):
            cmd.extend(["--image", params["image"]])
        return cmd
    return ["mmn", "linkedin", "all", "--count", "1"]


def _build_twitter_thread_generate(params: dict, _output_dir: str) -> list[str]:
    cmd = ["mmn", "twitter", "thread"]
    if params.get("topic"):
        cmd.extend(["--topic", params["topic"]])
    return cmd


def _build_twitter_thread_publish(params: dict, _output_dir: str) -> list[str]:
    cmd = _build_twitter_thread_generate(params, _output_dir)
    cmd.append("--post")
    return cmd


def _build_twitter_all_generate(params: dict, output_dir: str) -> list[str]:
    """Preview: generate replies to CSV so the user can review targets."""
    cmd = ["mmn", "twitter", "engage", "-o", os.path.join(output_dir, "replies.csv"), "--headless"]
    if params.get("max_replies"):
        cmd.extend(["--max-replies", str(params["max_replies"])])
    return cmd


def _build_twitter_all_publish(params: dict, _output_dir: str) -> list[str]:
    """Publish: run the full pipeline (replies + thread)."""
    cmd = ["mmn", "twitter", "all"]
    if params.get("max_replies"):
        cmd.extend(["--max-replies", str(params["max_replies"])])
    return cmd


def _build_twitter_engage_generate(params: dict, output_dir: str) -> list[str]:
    cmd = ["mmn", "twitter", "engage", "-o", os.path.join(output_dir, "replies.csv")]
    if params.get("max_replies"):
        cmd.extend(["--max-replies", str(params["max_replies"])])
    return cmd


def _build_twitter_engage_publish(_params: dict, output_dir: str) -> list[str]:
    return ["mmn", "twitter", "reply", "-f", os.path.join(output_dir, "replies.csv")]


def _build_reddit_engage_generate(params: dict, output_dir: str) -> list[str]:
    cmd = ["mmn", "reddit", "engage", "-o", os.path.join(output_dir, "comments.csv")]
    if params.get("max_comments"):
        cmd.extend(["--max-comments", str(params["max_comments"])])
    return cmd


def _build_reddit_engage_publish(_params: dict, output_dir: str) -> list[str]:
    return ["mmn", "reddit", "reply", "-f", os.path.join(output_dir, "comments.csv")]


_YT_TITLE_VARIANTS = [
    "Can our AI grade this? #chatgpt #artificialintelligence #education #shorts #shortvideo #tiktok",
    "Can AI actually grade your homework? #chatgpt #artificialintelligence #education #shorts #shortvideo #tiktok",
    "We let AI grade this assignment #chatgpt #artificialintelligence #education #shorts #shortvideo #tiktok",
    "AI vs. Teacher: Who grades better? #chatgpt #artificialintelligence #education #shorts #shortvideo #tiktok",
    "This AI just graded a real assignment #chatgpt #artificialintelligence #education #shorts #shortvideo #viral",
    "Watch AI grade this in seconds #chatgpt #artificialintelligence #education #shorts #shortvideo #tiktok",
    "POV: AI is now your teacher #chatgpt #artificialintelligence #education #shorts #shortvideo #tiktok",
]

_YT_DEFAULT_DESCRIPTION = (
    "Our AI looked at this assignment and said 'hold my coffee' ☕🤖\n"
    "Watch it roast — sorry, GRADE — a real student submission with zero mercy and 100% accuracy.\n"
    "Teachers are shaking. Students are vibing. The future is here.\n"
    "\n"
    "Check Gradeasy out at https://gradeasy.ai\n"
    "\n"
    "#chatgpt #artificialintelligence #education #shorts #shortvideo #tiktok "
    "#ai #edtech #grading #teacher #student #school #homework #viral"
)


def _pick_yt_title() -> str:
    import random

    return random.choice(_YT_TITLE_VARIANTS)


def _build_youtube_short_generate(params: dict, output_dir: str) -> list[str]:
    """Preview: just echo the params (no generation step for YouTube Shorts)."""
    cmd = ["mmn", "youtube", "upload", os.path.join(output_dir, "*.mp4")]
    title = params.get("title") or _pick_yt_title()
    cmd.extend(["--title", title])
    description = params.get("description") or _YT_DEFAULT_DESCRIPTION
    cmd.extend(["--description", description])
    if params.get("hashtags"):
        cmd.extend(["--hashtags", params["hashtags"]])
    if params.get("privacy"):
        cmd.extend(["--privacy", params["privacy"]])
    return cmd


def _build_youtube_short_publish(params: dict, output_dir: str) -> list[str]:
    cmd = ["mmn", "youtube", "upload"]
    latest_mp4 = os.path.join(output_dir, "latest.mp4")
    cmd.append(latest_mp4)
    title = params.get("title") or _pick_yt_title()
    cmd.extend(["--title", title])
    description = params.get("description") or _YT_DEFAULT_DESCRIPTION
    cmd.extend(["--description", description])
    if params.get("hashtags"):
        cmd.extend(["--hashtags", params["hashtags"]])
    if params.get("privacy"):
        cmd.extend(["--privacy", params["privacy"]])
    return cmd


def _build_email_generate(params: dict, _output_dir: str) -> list[str]:
    cmd = ["mmn", "email", "send", "--dry-run"]
    if params.get("template"):
        cmd.extend(["-t", params["template"]])
    if params.get("file"):
        cmd.extend(["-f", params["file"]])
    if params.get("subject"):
        cmd.extend(["-s", params["subject"]])
    return cmd


def _build_email_publish(params: dict, _output_dir: str) -> list[str]:
    cmd = ["mmn", "email", "send"]
    if params.get("template"):
        cmd.extend(["-t", params["template"]])
    if params.get("file"):
        cmd.extend(["-f", params["file"]])
    if params.get("subject"):
        cmd.extend(["-s", params["subject"]])
    return cmd


BUILDERS: dict[str, dict[str, tuple[CommandBuilder, CommandBuilder]]] = {
    "instagram": {
        "reel": (_build_reel_generate, _build_reel_publish),
        "carousel": (_build_carousel_generate, _build_carousel_publish),
    },
    "linkedin": {
        "post": (_build_linkedin_generate, _build_linkedin_publish),
    },
    "twitter": {
        "all": (_build_twitter_all_generate, _build_twitter_all_publish),
        "thread": (_build_twitter_thread_generate, _build_twitter_thread_publish),
        "engage": (_build_twitter_engage_generate, _build_twitter_engage_publish),
    },
    "reddit": {
        "engage": (_build_reddit_engage_generate, _build_reddit_engage_publish),
    },
    "email": {
        "send": (_build_email_generate, _build_email_publish),
    },
    "youtube": {
        "short": (_build_youtube_short_generate, _build_youtube_short_publish),
    },
}


def get_builders(platform: str, command_type: str) -> tuple[CommandBuilder, CommandBuilder] | None:
    return BUILDERS.get(platform, {}).get(command_type)


def get_meta(platform: str, command_type: str) -> dict | None:
    return PLATFORM_META.get(platform, {}).get(command_type)
