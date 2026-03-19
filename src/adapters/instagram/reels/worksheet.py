from __future__ import annotations

import asyncio
import base64
import json
import logging
import random
import shutil
import tempfile
import textwrap
from pathlib import Path

from .models import QuestionTypeDef, WorksheetConfig
from .pipeline_steps import PipelineContext

log = logging.getLogger(__name__)

# A4 at 200 DPI
_A4_WIDTH = 1654
_A4_HEIGHT = 2339

_DEFAULT_QUESTION_TYPES: list[dict[str, object]] = [
    {"type": "labeling", "description": "Label parts of a diagram", "needs_image_prompt": True},
    {"type": "match_the_following", "description": "Match items from column A to column B"},
    {"type": "fill_in_the_blanks", "description": "Fill in missing words in sentences"},
    {"type": "multiple_choice", "description": "Choose the correct answer from 4 options"},
    {"type": "short_answer", "description": "Brief 1-2 sentence written response"},
    {"type": "true_false", "description": "Mark statements as true or false"},
    {"type": "word_problem", "description": "Solve a math or science word problem"},
    {"type": "long_essay", "description": "Write a long-form paragraph essay response"},
]

_DEFAULT_SUBJECTS = [
    "Math",
    "Science",
    "History",
    "English",
    "Geography",
    "Biology",
    "Physics",
    "Chemistry",
]


def _has_pdflatex() -> bool:
    return shutil.which("pdflatex") is not None


def pick_questions(
    config: WorksheetConfig,
) -> tuple[list[QuestionTypeDef], str]:
    """Pick random question types and a subject from the worksheet config."""
    q_types = config.question_types
    if not q_types:
        q_types = [
            QuestionTypeDef(
                type=qt["type"],
                description=str(qt.get("description", "")),
                needs_image_prompt=bool(qt.get("needs_image_prompt", False)),
            )
            for qt in _DEFAULT_QUESTION_TYPES
        ]

    subjects = config.subjects or _DEFAULT_SUBJECTS

    count = random.randint(config.num_questions_min, config.num_questions_max)
    count = min(count, len(q_types))
    selected = random.sample(list(q_types), k=count)
    subject = random.choice(subjects)
    return selected, subject


# ---------------------------------------------------------------------------
# Gemini content generation
# ---------------------------------------------------------------------------


async def generate_worksheet_content(
    client: object,
    question_types: list[QuestionTypeDef],
    subject: str,
    model: str = "gemini-2.5-flash",
) -> dict[str, object]:
    """Call Gemini to produce worksheet content.

    Returns a dict with keys: ``latex``, ``title``, ``subject``,
    ``questions`` (list of dicts), and ``labeling_image_prompt``.
    """
    from google.genai import types as genai_types

    qtypes_desc = "\n".join(f"  - {qt.type}: {qt.description}" for qt in question_types)

    has_labeling = any(qt.needs_image_prompt for qt in question_types)
    labeling_instruction = ""
    if has_labeling:
        labeling_instruction = (
            "\nOne of the question types is 'labeling'. For this question, also output a "
            "field 'labeling_image_prompt' with a detailed text-to-image prompt that would "
            "generate the diagram/item to be labeled (e.g. 'A detailed scientific diagram of "
            "a human heart with blank label lines pointing to major parts'). Leave blank "
            "boxes/lines where students would write the labels."
        )

    system_prompt = (
        "You are a worksheet designer for school teachers. You produce worksheet "
        "content in a structured JSON format AND as clean LaTeX source code.\n\n"
        "LaTeX rules: must compile with pdflatex using only amsmath, geometry, "
        "enumitem, graphicx, and multicol packages. Use geometry for A4 paper with "
        "reasonable margins. Include title, subject header, name/date fields.\n\n"
        "Make the worksheet look like a real school assignment."
    )

    user_prompt = (
        f"Create a worksheet for the subject: {subject}\n\n"
        f"Include these question types:\n{qtypes_desc}\n\n"
        "Generate 2-4 questions per question type. Grade-school to middle-school "
        "level (ages 10-14). Real, substantive questions.\n"
        f"{labeling_instruction}\n\n"
        "Return JSON with these fields:\n"
        '  "title": worksheet title (e.g. "Science Quiz - Chapter 5")\n'
        '  "subject": the subject name\n'
        '  "questions": array of objects, each with:\n'
        '    "number": question number (int)\n'
        '    "type": the question type string\n'
        '    "text": the full question text\n'
        '    "options": array of option strings (for multiple_choice/match/true_false), '
        "or null\n"
        '    "answer_lines": how many blank lines for the answer (int, 1-8)\n'
        '  "latex": the complete LaTeX document source code (string)\n'
        '  "labeling_image_prompt": image generation prompt string, or ""\n\n'
        "Return ONLY valid JSON, no markdown fences."
    )

    response = await client.aio.models.generate_content(  # type: ignore[union-attr]
        model=model,
        contents=[
            genai_types.Content(
                role="user",
                parts=[genai_types.Part.from_text(text=user_prompt)],
            ),
        ],
        config=genai_types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            temperature=0.9,
        ),
    )

    data = json.loads(response.text)
    if isinstance(data, list):
        data = data[0]
    return data


# ---------------------------------------------------------------------------
# LaTeX renderer (requires pdflatex)
# ---------------------------------------------------------------------------


async def _render_with_latex(latex_code: str, output_dir: Path, dpi: int = 200) -> Path:
    import fitz  # PyMuPDF

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        tex_file = tmp_path / "worksheet.tex"
        tex_file.write_text(latex_code, encoding="utf-8")

        proc = await asyncio.create_subprocess_exec(
            "pdflatex",
            "-interaction=nonstopmode",
            "-halt-on-error",
            str(tex_file),
            cwd=str(tmp_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await proc.communicate()

        pdf_file = tmp_path / "worksheet.pdf"
        if not pdf_file.exists():
            log_file = tmp_path / "worksheet.log"
            log_text = log_file.read_text() if log_file.exists() else stderr.decode()
            raise RuntimeError(f"pdflatex failed:\n{log_text[-2000:]}")

        doc = fitz.open(str(pdf_file))
        page = doc[0]
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)

        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / "worksheet.png"
        pix.save(str(out_path))
        doc.close()

    return out_path


# ---------------------------------------------------------------------------
# Pillow renderer (fallback — no system deps needed)
# ---------------------------------------------------------------------------


def _render_with_pillow(content: dict[str, object], output_dir: Path) -> Path:
    """Render worksheet content to an A4-sized PNG using Pillow."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (_A4_WIDTH, _A4_HEIGHT), "white")
    draw = ImageDraw.Draw(img)

    title_size, heading_size, body_size, small_size = 48, 32, 24, 20

    try:
        title_font = ImageFont.truetype("Helvetica", title_size)
    except OSError:
        try:
            title_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", title_size)
        except OSError:
            title_font = ImageFont.load_default(size=title_size)

    try:
        heading_font = ImageFont.truetype("Helvetica-Bold", heading_size)
    except OSError:
        try:
            heading_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", heading_size)
        except OSError:
            heading_font = ImageFont.load_default(size=heading_size)

    try:
        body_font = ImageFont.truetype("Helvetica", body_size)
    except OSError:
        try:
            body_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", body_size)
        except OSError:
            body_font = ImageFont.load_default(size=body_size)

    try:
        small_font = ImageFont.truetype("Helvetica", small_size)
    except OSError:
        try:
            small_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", small_size)
        except OSError:
            small_font = ImageFont.load_default(size=small_size)

    margin_x = 120
    max_text_w = _A4_WIDTH - 2 * margin_x
    y = 100

    title = str(content.get("title", "Worksheet"))
    subject = str(content.get("subject", ""))

    draw.text((_A4_WIDTH // 2, y), title, fill="black", font=title_font, anchor="mt")
    y += title_size + 10

    draw.line([(margin_x, y), (_A4_WIDTH - margin_x, y)], fill="black", width=3)
    y += 20

    if subject:
        draw.text((margin_x, y), f"Subject: {subject}", fill="black", font=small_font)
    draw.text(
        (_A4_WIDTH - margin_x, y),
        "Name: ________________  Date: ________",
        fill="black",
        font=small_font,
        anchor="rt",
    )
    y += small_size + 30

    draw.line([(margin_x, y), (_A4_WIDTH - margin_x, y)], fill="gray", width=1)
    y += 20

    questions = content.get("questions", [])
    if not isinstance(questions, list):
        questions = []

    for q in questions:
        if y > _A4_HEIGHT - 200:
            break

        if not isinstance(q, dict):
            continue

        num = q.get("number", "")
        qtype = q.get("type", "")
        text = str(q.get("text", ""))
        options = q.get("options")
        answer_lines = int(q.get("answer_lines", 2))

        header = f"Q{num}."
        if qtype:
            header += f"  [{qtype.replace('_', ' ').title()}]"

        draw.text((margin_x, y), header, fill="#333333", font=heading_font)
        y += heading_size + 8

        wrapped = textwrap.wrap(text, width=int(max_text_w / (body_size * 0.55)))
        for line in wrapped:
            if y > _A4_HEIGHT - 150:
                break
            draw.text((margin_x + 20, y), line, fill="black", font=body_font)
            y += body_size + 6
        y += 8

        if isinstance(options, list) and options:
            labels = "abcdefghijklmnop"
            for i, opt in enumerate(options):
                if y > _A4_HEIGHT - 150:
                    break
                label = labels[i] if i < len(labels) else str(i + 1)
                opt_text = f"  {label})  {opt}"
                draw.text((margin_x + 40, y), opt_text, fill="black", font=body_font)
                y += body_size + 6
            y += 10

        line_y = y
        for _ in range(min(answer_lines, 6)):
            if line_y > _A4_HEIGHT - 100:
                break
            draw.line(
                [(margin_x + 20, line_y + body_size), (_A4_WIDTH - margin_x, line_y + body_size)],
                fill="#cccccc",
                width=1,
            )
            line_y += body_size + 12
        y = line_y + 20

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "worksheet.png"
    img.save(str(out_path), "PNG")
    return out_path


# ---------------------------------------------------------------------------
# Unified renderer — tries LaTeX, falls back to Pillow
# ---------------------------------------------------------------------------


async def render_worksheet_to_image(
    content: dict[str, object],
    output_dir: Path,
) -> Path:
    """Render a worksheet to an A4 PNG image.

    Tries pdflatex if installed; otherwise falls back to Pillow rendering.
    """
    latex_code = str(content.get("latex", ""))

    if latex_code and _has_pdflatex():
        try:
            return await _render_with_latex(latex_code, output_dir)
        except Exception as exc:
            log.warning("pdflatex rendering failed, falling back to Pillow: %s", exc)

    log.info("Using Pillow fallback to render worksheet image")
    return _render_with_pillow(content, output_dir)


# ---------------------------------------------------------------------------
# Gemini image editing — fill the worksheet
# ---------------------------------------------------------------------------


async def fill_worksheet_with_gemini(
    client: object,
    worksheet_image: Path,
    fill_prompt: str,
    output_dir: Path,
    vertex_project: str = "",
    vertex_location: str = "us-central1",
) -> Path:
    """Use Gemini 2.5 Flash Image to fill the worksheet with funny wrong answers."""
    from google import genai
    from google.genai import types as genai_types

    img_client = genai.Client(
        vertexai=True,
        project=vertex_project,
        location=vertex_location,
    )

    image_bytes = worksheet_image.read_bytes()

    response = await img_client.aio.models.generate_content(
        model="gemini-2.5-flash-image",
        contents=[
            genai_types.Content(
                role="user",
                parts=[
                    genai_types.Part.from_bytes(
                        data=image_bytes,
                        mime_type="image/png",
                    ),
                    genai_types.Part.from_text(text=fill_prompt),
                ],
            ),
        ],
        config=genai_types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
        ),
    )

    for candidate in getattr(response, "candidates", []):
        for part in getattr(candidate.content, "parts", []):
            inline = getattr(part, "inline_data", None)
            if inline and hasattr(inline, "mime_type") and inline.mime_type.startswith("image/"):
                img_data = inline.data
                if isinstance(img_data, str):
                    img_data = base64.b64decode(img_data)

                output_dir.mkdir(parents=True, exist_ok=True)
                out_path = output_dir / "worksheet_filled.png"
                out_path.write_bytes(img_data)
                return out_path

    raise RuntimeError("Gemini image model returned no image output for worksheet filling")


# ---------------------------------------------------------------------------
# Pipeline step functions
# ---------------------------------------------------------------------------


async def _worksheet_step(ctx: PipelineContext, inputs: dict[str, object]) -> object:
    """Generate a clean worksheet image.

    Reads worksheet config from ``ctx.services["worksheet_config"]``,
    picks random question types + subject, generates content via Gemini,
    renders to A4 PNG (LaTeX if available, Pillow fallback otherwise).
    """
    config: WorksheetConfig | None = ctx.services.get("worksheet_config")  # type: ignore[assignment]
    if config is None:
        config = WorksheetConfig()

    client = ctx.services.get("genai_client")
    if client is None:
        raise RuntimeError("genai_client not found in pipeline services")

    output_dir = Path(str(ctx.services.get("output_dir", "/tmp")))

    question_types, subject = pick_questions(config)

    content = await generate_worksheet_content(
        client=client,
        question_types=question_types,
        subject=subject,
    )

    worksheet_path = await render_worksheet_to_image(content, output_dir)

    labeling_prompt: str = str(content.get("labeling_image_prompt", ""))

    return {
        "worksheet_image": str(worksheet_path.resolve()),
        "labeling_image_prompt": labeling_prompt,
        "worksheet_subject": subject,
        "worksheet_question_types": [qt.type for qt in question_types],
    }


async def _fill_worksheet_step(ctx: PipelineContext, inputs: dict[str, object]) -> object:
    """Fill a clean worksheet with funny wrong answers using Gemini image editing."""
    client = ctx.services.get("genai_client")
    if client is None:
        raise RuntimeError("genai_client not found in pipeline services")

    worksheet_image = Path(str(inputs.get("worksheet_image", "")))
    if not worksheet_image.exists():
        raise FileNotFoundError(f"Worksheet image not found: {worksheet_image}")

    config: WorksheetConfig | None = ctx.services.get("worksheet_config")  # type: ignore[assignment]
    fill_prompt = inputs.get("fill_prompt", "")
    if not fill_prompt and config:
        fill_prompt = config.fill_prompt
    if not fill_prompt:
        fill_prompt = WorksheetConfig().fill_prompt

    output_dir = Path(str(ctx.services.get("output_dir", "/tmp")))
    vertex_project = str(ctx.services.get("vertex_project", ""))
    vertex_location = str(ctx.services.get("vertex_location", "us-central1"))

    try:
        filled_path = await asyncio.wait_for(
            fill_worksheet_with_gemini(
                client=client,
                worksheet_image=worksheet_image,
                fill_prompt=str(fill_prompt),
                output_dir=output_dir,
                vertex_project=vertex_project,
                vertex_location=vertex_location,
            ),
            timeout=90,
        )
    except Exception as exc:
        log.warning(
            "Gemini image fill failed, falling back to unfilled worksheet: %s",
            exc,
        )
        return str(worksheet_image.resolve())

    return str(filled_path.resolve())
