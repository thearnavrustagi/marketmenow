# How to Create a Reel Template for Your Product

A reel template is a single YAML file that defines your entire video — the narrative structure, scenes, audio, transitions, and the content-generation pipeline. To make reels for **your** product, you create a template with your own story and scenes.

This guide explains the template schema so you can build one by hand, or you can skip to the [meta-prompt](#meta-prompt) at the bottom and paste it into ChatGPT / Claude to generate one automatically.

---

## Template anatomy

Every template YAML has these sections:

```yaml
# ─── Metadata ───
id: my_template               # Unique slug (used in CLI: mmn reel create --template my_template)
name: "My Reel Concept"       # Human-readable name
aspect_ratio: "9:16"          # Always 9:16 for Reels/Shorts
fps: 30
composition_id: ReelFromTemplate

# ─── Brand identity ───
default_visual:
  brand_color: "#FF6B35"      # Your primary brand color
  brand_name: "CookBot"       # Displayed in branded scenes
  brand_suffix: ".app"        # Appended to brand name (e.g. CookBot.app)
  font_family: "system-ui, sans-serif"
  panel_background: "#0A0A0A"
  frame_background: "#E0E0E0"

# ─── Post copy ───
caption_template: |
  Your caption with {{ variables }} from the pipeline.
  Visit yourbrand.com

hashtags:
  - YourHashtag
  - Niche
  - Trending

hook_lines:
  - "comment text option 1"
  - "comment text option 2"

# ─── Content pipeline (what to generate) ───
pipeline:
  steps:
    - id: step_name
      type: llm            # or: worksheet, fill_worksheet, rubric, grading
      inputs: { ... }
      output_var: result_var
      output_fields: [field1, field2]

# ─── Variables the pipeline produces ───
variables:
  - field1
  - field2

# ─── Beats (the video timeline) ───
beats:
  - id: beat_name
    scene: SceneName
    audio: { type: tts, text: "{{ field1 }}" }
    duration: from_audio
    visual: { ... }
    entry_transition: { type: fade, duration_frames: 8 }
```

---

## Available scenes

Each beat references a scene component. Here's every scene and what visual props it accepts:

### `HookScene` — Full-screen text on a gradient
| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `text_overlay` | string | `""` | The hook text |
| `background` | string | gradient | CSS background |
| `text_color` | string | `#fff` | |
| `font_size` | number | `52` | |
| `font_weight` | number | `800` | |
| `font_family` | string | `system-ui` | |
| `text_shadow` | string | shadow | CSS text-shadow |

### `TikTokCommentScene` — Fake comment card with optional image
| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `username` | string | `"user"` | Commenter handle |
| `avatar` | image path | | Profile picture |
| `comment_text` | string | | The comment body |
| `comment_image` | image path | | Attached image |
| `show_image` | bool | `false` | Whether to show the image |
| `background` | string | `#000` | |
| `card_background` | string | `#fff` | |
| `font_size` | number | `28` | Comment text size |
| `username_font_size` | number | `22` | |

### `RevealScene` — Spring-animated image reveal
| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `image` | image path | | The image to reveal |
| `background` | string | `#000` | |
| `border_radius` | number | `16` | |
| `spring_damping` | number | `12` | |
| `spring_stiffness` | number | `100` | |

### `FlashRevealScene` — White flash then image appears
| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `image` | image path | | |
| `flash_color` | string | `#ffffff` | |
| `flash_duration` | number | `0.3` | Seconds |
| `background` | string | `#000` | |

### `RoastScene` — Image top + branded panel bottom
| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `image` | image path | | |
| `text_overlay` | string | | (rendered as subtitle, not in scene) |
| `brand_color` | string | from default_visual | |
| `brand_name` | string | from default_visual | |
| `brand_suffix` | string | from default_visual | |
| `panel_background` | string | `#0A0A0A` | |
| `frame_background` | string | `#E0E0E0` | |

### `BrandResponseScene` — Brand logo + text response (generic, works for any product)
| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `text_overlay` | string | `"I gotchu bro"` | |
| `brand_color` | string | from default_visual | |
| `brand_name` | string | from default_visual | |
| `brand_suffix` | string | from default_visual | |
| `background` | string | `#0A0A0A` | |
| `font_size` | number | `48` | |

### `SegmentationScene` — Image with scanning animation + status text
| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `image` | image path | | |
| `status_text` | string | `"Analyzing..."` | Pulsing status text |
| `brand_color` | string | from default_visual | |
| `brand_name` | string | from default_visual | |
| `brand_suffix` | string | from default_visual | |

### `TransitionScene` — Image top + brand panel bottom with slide-in
| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `image` | image path | | |
| `brand_color` | string | from default_visual | |
| `brand_name` | string | from default_visual | |
| `brand_suffix` | string | from default_visual | |

### `RubricScene` — Card with staggered rubric items
| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `rubric_items` | array/JSON | `[]` | `[{name, description, max_points}]` |
| `header_text` | string | `"Rubric"` | |
| `background` | string | gradient | |
| `card_background` | string | `#fff` | |
| `text_color` | string | `#1a1a1a` | |

### `GradingScene` — Rubric breakdown with progress bars
| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `grading_result` | object/JSON | | Full grading result with `rubric_evaluations` |
| `student_name` | string | | |
| `background` | string | gradient | |
| `card_background` | string | `#fff` | |

### `ResultScene` — Circular score ring + feedback
| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `grade` | string | `"?/?"` | Format: `"85/100"` |
| `feedback` | string | | |
| `brand_name` | string | from default_visual | Shown at bottom |

### `CustomScene` — Fully declarative layers (most flexible)
| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `background` | string | `#000` | |
| `layers` | array | `[]` | Array of layer objects (see below) |

**Layer types:**
- `image`: `{type: "image", src: "path", position: {top, left}, size: {width, height}, animation: {...}}`
- `text`: `{type: "text", content: "Hello", position: {...}, style: {font_size, color, ...}, animation: {...}}`
- `box`: `{type: "box", position: {...}, size: {...}, style: {background, border_radius, ...}}`

**Animation types for layers:** `fade`, `spring`, `slide_up`, `slide_down`, `scale`

---

## Available transitions

Applied per-beat as `entry_transition` / `exit_transition`:

| Type | Props | Description |
|------|-------|-------------|
| `none` | | No transition |
| `fade` | `duration_frames` | Opacity fade |
| `slide` | `duration_frames`, `direction` (up/down/left/right) | Slide in from direction |
| `scale` | `duration_frames` | Scale up from small |
| `spring` | `duration_frames` | Bouncy scale-in |
| `wipe` | `duration_frames`, `direction` | Wipe reveal |

---

## Audio types

Each beat has an `audio` block:

```yaml
# Text-to-speech (generated at render time)
audio:
  type: tts
  text: "{{ variable_name }}"
  voice: "{{ voice_id_variable }}"    # optional

# Sound effect (static file)
audio:
  type: sfx
  file: assets/sfx/whoosh.mp3         # relative to reels/ directory

# Silent (no audio)
audio:
  type: sfx
  file: ""
```

---

## Duration modes

```yaml
duration: from_audio     # Beat lasts as long as its audio
pad_seconds: 0.3        # Extra padding after audio ends

duration: fixed          # Beat lasts a fixed time
fixed_seconds: 1.2
```

---

## Pipeline steps

The pipeline generates content before the video renders. Steps run in order, each writing to variables that later beats can reference with `{{ var_name }}`.

### Built-in step types

| Type | What it does | Inputs | Outputs |
|------|-------------|--------|---------|
| `llm` | Calls an LLM with a prompt YAML from `prompts/instagram/` | `prompt`, `model`, `temperature`, `context`, `output_fields` | Dict of fields |
| `worksheet` | Generates a worksheet image | (reads from `worksheet` config) | `worksheet_image`, `labeling_image_prompt`, etc. |
| `fill_worksheet` | Fills in a worksheet image with fake answers | `worksheet_image` | `assignment_image` |
| `rubric` | Creates grading rubric from an image | `assignment_image` | `rubric_items` |
| `grading` | Grades an image against a rubric | `assignment_image`, `rubric_items` | `grading_result` |

### The `llm` step (most important for custom templates)

The `llm` step is your main tool. It calls an LLM with a prompt file and returns structured JSON.

```yaml
- id: write_script
  type: llm
  inputs:
    prompt: my_script_prompt          # loads prompts/instagram/my_script_prompt.yaml
    model: gemini-2.5-flash
    temperature: 0.8
    context:                          # variables passed into the prompt's {{ }} placeholders
      product_name: "{{ brand_name }}"
      user_input: "{{ user_screenshot }}"
    output_fields:                    # which JSON keys to extract
      - hook_text
      - demo_narration
      - cta_text
```

Your prompt YAML (`prompts/instagram/my_script_prompt.yaml`) should instruct the LLM to return JSON with exactly those fields.

---

## Step-by-step: creating a template for your product

### 1. Define your reel concept

What's the story? Examples:
- **Before/After**: User struggles → your product solves it instantly
- **Challenge**: "Can [product] handle this?" → dramatic result
- **React & Review**: Show user-submitted content → your product's take
- **Tutorial speedrun**: 60-second "how to do X with [product]"
- **Meme format**: Trending audio + your product's twist

### 2. Write the prompt YAML

Create `prompts/instagram/your_script.yaml` with `system:` and `user:` fields. The system prompt defines the voice and characters. The user prompt has `{variables}` filled at runtime.

### 3. Sketch the beats

Map your story to a sequence of scenes:
```
Hook (TikTokCommentScene) → Problem reveal (RevealScene) → Reaction (FlashRevealScene)
→ Product intro (BrandResponseScene) → Product working (SegmentationScene)
→ Result (ResultScene)
```

### 4. Write the template YAML

Combine your beats, pipeline, and brand config into a single YAML file in `src/adapters/instagram/reels/templates/`.

### 5. Test it

```bash
mmn reel create --template your_template_id
```

---

## Meta-prompt

**Copy-paste the block below into ChatGPT / Claude to generate a complete reel template YAML for your product.**

It will generate both the template YAML and the companion prompt YAML.

---

````
I need you to generate a MarketMeNow reel template — a YAML file that
defines an Instagram Reel (short-form vertical video) for my product.

MarketMeNow renders reels using Remotion (React). Each reel is defined by
a template YAML that specifies: brand identity, a content-generation
pipeline, and a sequence of "beats" (scenes with audio and transitions).

Below is the COMPLETE schema reference you must follow.

─── MY PRODUCT ───

Brand name: [YOUR BRAND NAME]
Brand suffix: [e.g. ".ai", ".app", ".io", ""]
Brand color (hex): [e.g. "#FF6B35"]
URL: [e.g. "cookbot.app"]
What it does: [one sentence — e.g. "AI recipe generator that turns fridge photos into meals"]
Target audience: [e.g. "home cooks, college students, busy parents"]

─── REEL CONCEPT ───

Describe the reel format you want. Be specific about the narrative arc:
[e.g. "Someone posts a photo of their sad fridge contents as a comment,
CookBot scans it and generates a gourmet recipe in real-time, then shows
the final dish. Tone: funny and impressive, like a cooking competition reveal."]

─── VOICE / CHARACTERS ───

Describe the voice(s) in the reel:
[e.g. "Character 1: A dramatic food critic who roasts the fridge contents.
Character 2: CookBot, a confident and chill AI chef who says things like
'watch me work' and 'chef's kiss'."]

─── AVAILABLE SCENES ───

You MUST only use these scene components. Each scene is a React component
that receives visual props:

1. HookScene — Full-screen text on gradient background
   Props: text_overlay, background, text_color, font_size, font_weight

2. TikTokCommentScene — Fake social media comment card with optional image
   Props: username, avatar, comment_text, comment_image, show_image,
          background, card_background, font_size

3. RevealScene — Spring-animated image reveal on dark background
   Props: image, background, border_radius, spring_damping, spring_stiffness

4. FlashRevealScene — White flash then image appears (shock/surprise moment)
   Props: image, flash_color, flash_duration, background

5. RoastScene — Image in top half + branded dark panel bottom half
   Props: image, text_overlay, brand_color, brand_name, brand_suffix,
          panel_background, frame_background

6. BrandResponseScene — Brand logo animation + text response
   Props: text_overlay, brand_color, brand_name, brand_suffix, background,
          font_size (use this as your "product speaks" scene)

7. SegmentationScene — Image with scanning line animation + pulsing status
   Props: image, status_text, brand_color, brand_name, brand_suffix

8. TransitionScene — Image top + brand panel bottom with slide-in animation
   Props: image, brand_color, brand_name, brand_suffix

9. RubricScene — White card with staggered list items
   Props: rubric_items (array of {name, description, max_points}),
          header_text, background, card_background

10. GradingScene — Evaluation breakdown with colored progress bars
    Props: grading_result (object with rubric_evaluations), student_name,
           background, card_background

11. ResultScene — Circular animated score ring + feedback text + brand
    Props: grade ("85/100" format), feedback, brand_name, background

12. CustomScene — Fully declarative: define layers of images, text, boxes
    Props: background, layers (array of {type, src/content, position, size,
           style, animation})
    Layer types: "image", "text", "box"
    Animation types: "fade", "spring", "slide_up", "slide_down", "scale"

─── TRANSITIONS ───

Each beat can have entry_transition and exit_transition:
- { type: "none" }
- { type: "fade", duration_frames: 8 }
- { type: "slide", duration_frames: 10, direction: "up" }
- { type: "scale", duration_frames: 6 }
- { type: "spring", duration_frames: 10 }
- { type: "wipe", duration_frames: 8, direction: "left" }

─── AUDIO ───

Each beat has an audio block:
- TTS: { type: tts, text: "{{ variable }}", voice: "{{ voice_var }}" }
- SFX: { type: sfx, file: "assets/sfx/filename.mp3" }
  Available SFX: bruh.mp3, tinnitus.mp3, whoosh.mp3
  (or use file: "" for silence)

Duration modes:
- duration: from_audio (+ optional pad_seconds)
- duration: fixed, fixed_seconds: 1.2

─── PIPELINE ───

The pipeline generates content BEFORE rendering. The most useful step is
"llm" which calls an AI model with a prompt file:

    - id: write_script
      type: llm
      inputs:
        prompt: my_prompt_name          # → prompts/instagram/my_prompt_name.yaml
        model: gemini-2.5-flash
        temperature: 0.8
        context:
          key: "{{ variable }}"         # pass pipeline variables into prompt
        output_fields:
          - field1
          - field2

Other built-in steps (use only if relevant):
- worksheet: generates a worksheet image
- fill_worksheet: fills in a worksheet with fake answers
- rubric: creates grading rubric from image
- grading: grades an image against rubric items

─── WHAT TO GENERATE ───

Generate TWO files:

FILE 1: The reel template YAML (goes in src/adapters/instagram/reels/templates/)
- Must have: id, name, aspect_ratio (9:16), fps (30), composition_id (ReelFromTemplate)
- Must have: default_visual with brand_color, brand_name, brand_suffix
- Must have: caption_template with {{ variables }}, hashtags, hook_lines
- Must have: pipeline with at least one llm step
- Must have: variables listing all pipeline outputs
- Must have: beats array (6-12 beats for a 30-60 second reel)
- Beats must use ONLY the scenes listed above
- Every {{ variable }} in beats must be produced by a pipeline step
- Total reel should be 30-60 seconds (mix of from_audio and fixed durations)

FILE 2: The companion prompt YAML (goes in prompts/instagram/)
- Must have system: | and user: | fields
- system: defines the AI's persona, voice, characters, and output rules
- user: has {variable} placeholders and instructs the AI to return JSON
  with exactly the fields listed in the pipeline's output_fields
- The persona should feel like a REAL human, not a corporate account
- Include example phrasings for the voice
- Keep every text field SHORT (1-2 sentences) — these become TTS audio

─── EXAMPLE (for reference only, DO NOT copy this concept) ───

Here's a simplified example of how the pieces fit together. This is the
existing "Can AI Grade This" template (built for a specific product).
YOUR template should have a COMPLETELY DIFFERENT concept for YOUR product:

```yaml
id: can_ai_grade_this
name: "Can Our AI Grade This"
aspect_ratio: "9:16"
fps: 30
composition_id: ReelFromTemplate

default_visual:
  brand_color: "#4A8DF8"
  brand_name: "YourBrand"
  brand_suffix: ".ai"

caption_template: |
  Can our AI grade this?
  {{ result_comment }}
  Try {{ brand_name }} now at yourbrand.com

hashtags: [YourIndustry, YourProduct, RelevantTag]

hook_lines:
  - "can you grade my assignment twin?"
  - "bro rate my homework fr fr"

pipeline:
  steps:
    - id: write_script
      type: llm
      inputs:
        prompt: script_generation
        model: gemini-2.5-flash
        temperature: 0.8
        context:
          template_name: "{{ name }}"
        output_fields:
          - reaction_text
          - roast_text
          - result_comment

variables:
  - reaction_text
  - roast_text
  - result_comment

beats:
  - id: hook
    scene: TikTokCommentScene
    audio: { type: tts, text: "{{ comment_text }}" }
    duration: from_audio
    visual: { username: "{{ comment_username }}", comment_text: "{{ comment_text }}" }
    entry_transition: { type: fade, duration_frames: 8 }

  - id: reveal
    scene: RevealScene
    audio: { type: sfx, file: assets/sfx/bruh.mp3 }
    duration: fixed
    fixed_seconds: 1.2
    visual: { image: "{{ assignment_image }}" }

  - id: product_response
    scene: BrandResponseScene
    audio: { type: tts, text: "{{ brand_response }}" }
    duration: from_audio
    visual: { text_overlay: "{{ brand_response }}" }

  - id: result
    scene: ResultScene
    audio: { type: tts, text: "{{ result_comment }}" }
    duration: from_audio
    visual: { grade: "85/100", feedback: "{{ result_comment }}" }
```

─── RULES ───

- The template MUST be valid YAML
- Every {{ variable }} in beats MUST be defined in the variables list
  and produced by a pipeline step
- Scene names MUST exactly match one of the 12 scenes listed above
- Keep the reel between 6-12 beats (30-60 seconds total)
- Audio text should be SHORT (1-2 sentences each) since it becomes speech
- The concept should be VIRAL-WORTHY — think about what makes people
  watch, share, and comment
- Include at least one beat where the product/brand is prominently featured
- End with a CTA that encourages engagement (comments, follows, visits)
- Make the hook_lines feel authentic (like real user comments)
- The caption_template should include relevant {{ variables }} and the brand URL

Generate both files now. Format the template YAML and prompt YAML in
separate code blocks, clearly labeled.
````

---

## Tips

- **Start simple.** A 6-beat reel with one `llm` pipeline step is enough. You can always add complexity later.
- **Use `CustomScene` for unique layouts.** If none of the built-in scenes fit your concept, `CustomScene` lets you define arbitrary layers of images, text, and boxes with per-layer animations.
- **Test with `--dry-run` first.** Check that the pipeline produces all required variables before doing a full render.
- **Reuse scenes creatively.** `BrandResponseScene` works for any "product speaks" moment — it shows brand logo + text. `SegmentationScene` works for any "product is processing" moment.
- **Add your own SFX.** Drop `.mp3` files into `assets/sfx/` and reference them in beats.
- **Multiple templates.** You can have as many templates as you want. Use `--template your_id` to pick one at render time.
