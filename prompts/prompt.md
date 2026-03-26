# How to Write Prompts for MarketMeNow

This guide explains how every prompt in MarketMeNow works, how to customize them for your brand, and includes a **meta-prompt** you can paste into ChatGPT / Claude to generate new prompts from scratch.

---

## How Prompts Work

MarketMeNow uses a **decomposed prompt architecture** that separates *who your account is* (persona) from *what it's doing* (function) and *what it learned* (in-context learning).

### Prompt Building Blocks

1. **Persona** (`projects/{slug}/prompts/persona.yaml` or `projects/{slug}/prompts/{platform}/persona.yaml`) -- the brand voice, personality, product knowledge. Lives in the project directory because it's product-specific.
2. **Function** (`prompts/{platform}/functions/{function}.yaml`) -- the task-specific instructions (reply, thread, comment, etc.). Lives in the global `prompts/` directory because it's product-agnostic.
3. **ICL Block** (`prompts/{platform}/icl_block.yaml`) -- the in-context learning template that injects winning examples.

The `PromptBuilder` assembles these at runtime. Resolution order:
1. `projects/{slug}/prompts/{platform}/{file}` (project + platform override)
2. `projects/{slug}/prompts/{file}` (project-level default)
3. `prompts/{platform}/{file}` (global default)

### Legacy Mode

If you prefer a single monolithic YAML file (the old way), that still works. Place a `reply_generation.yaml` or `thread_generation.yaml` in `prompts/{platform}/` or your project's `prompts/{platform}/` directory and the system falls back to it.

### YAML Structure

Each prompt YAML has two fields:

```yaml
system: |
  The persona, rules, and constraints the AI follows.
  Uses {{ jinja2_variables }} for brand/persona data.

user: |
  The per-request instructions with {{ variables }} filled at runtime.
```

Variables use `{{ double_braces }}` (Jinja2) or `{single_braces}` (Python `.format()`).

---

## Prompt Inventory

| File | What it does | Key variables |
|------|-------------|---------------|
| `instagram/script_generation.yaml` | Writes a 2-character reel script | `template_name`, `points_awarded`, `max_points`, `feedback`, `rubric_eval_text` |
| `instagram/carousel_top5.yaml` | Generates "Top 5" list carousel content with image prompts | (none -- the AI picks a fresh topic each run) |
| `instagram/autograde.yaml` | Evaluates submitted work against a rubric | `rubric_text` |
| `instagram/generate_rubric.yaml` | Creates an evaluation rubric from an image | (none -- reads the image) |
| `instagram/worksheet_generation.yaml` | Generates worksheet content (JSON + LaTeX) for school subjects | `subject`, `qtypes_desc`, `labeling_instruction` |
| `instagram/worksheet_fill.yaml` | Image-edit instruction to fill a worksheet with funny wrong answers | (none -- receives worksheet image) |
| `instagram/carousel_image_fallback.yaml` | Imagen safety fallback and simplify templates for carousel images | `words` (in simplify template) |
| `twitter/functions/reply.yaml` | Reply function template (mention strategy, format rules) | `author_handle`, `post_text`, `reply_number`, `mention_rate`, `directive` |
| `twitter/functions/thread.yaml` | Thread function template (7-tweet structure, CTA) | `winning_posts`, `topic_hint` |
| `twitter/reply_generation.yaml` | Legacy single-file reply prompt | `author_handle`, `post_text`, `reply_number`, `should_mention`, `mention_rate`, `winning_examples` |
| `twitter/thread_generation.yaml` | Legacy single-file thread prompt | `winning_posts`, `topic_hint` |
| `twitter/icl_block.yaml` | In-context learning example block | `examples` |
| `linkedin/batch_generation.yaml` | Generates a batch of LinkedIn posts (text, poll, article) | `count` |
| `reddit/functions/comment.yaml` | Reddit comment function template | `subreddit`, `post_text`, `comment_number`, `directive` |
| `reddit/comment_generation.yaml` | Legacy single-file Reddit comment prompt | `subreddit`, `post_title`, `post_text`, `comment_number`, `should_mention`, `mention_rate` |
| `email/paraphrase.yaml` | Paraphrases email HTML so no two emails read identically | (receives raw HTML as user content) |
| `icl_block_default.yaml` | Default ICL block template (used when platform-specific one is missing) | `examples` |
| `templates/twitter_persona.yaml` | Onboarding template for Twitter persona (copied to new projects) | `persona_description`, `persona_voice`, `persona_tone`, `phrases_block` |
| `templates/reddit_persona.yaml` | Onboarding template for Reddit persona | `persona_description`, `persona_voice`, `persona_tone` |
| `templates/instagram_script.yaml` | Onboarding template for Instagram reel script prompt | `brand_name`, `brand_url`, `brand_tagline`, `features_block`, `persona_*`, `phrases_block` |

---

## Onboarding Templates (`prompts/templates/`)

These YAML files are used by `mmn project add` to generate project-specific persona prompts. They contain placeholder tokens like `{{ persona_description }}` that are replaced with the actual brand/persona values during onboarding. The Jinja2 runtime variables (like `{{ brand.name }}`) are left intact so they resolve at prompt-render time.

| Template | Used by | Output location |
|----------|---------|-----------------|
| `templates/twitter_persona.yaml` | `generate_twitter_prompt()` | `projects/{slug}/prompts/twitter/persona.yaml` |
| `templates/reddit_persona.yaml` | `generate_reddit_prompt()` | `projects/{slug}/prompts/reddit/persona.yaml` |
| `templates/instagram_script.yaml` | `generate_instagram_prompt()` | `projects/{slug}/prompts/instagram/script_generation.yaml` |

---

## Customizing for Your Brand

### Step 1: Create Your Project

```bash
mmn project add my-product
```

The onboarding wizard generates a persona YAML in `projects/my-product/prompts/persona.yaml` (or platform-specific ones like `projects/my-product/prompts/twitter/persona.yaml`).

### Step 2: Edit the Persona

The persona defines **who** your account is. Edit the generated YAML or write one from scratch:

```yaml
system: |
  You ARE {{ brand.name }}. You're the social media personality behind
  {{ brand.tagline }}.

  YOUR PERSONALITY:
  - {{ persona.voice }}
  - {{ persona.tone }}
  - You use phrases like: {{ persona.example_phrases | join(', ') }}

  WHAT YOU KNOW (but rarely say outright):
  - You're {{ brand.url }} -- {{ brand.tagline }}
  {% for feat in brand.features %}
  - {{ feat }}
  {% endfor %}
```

### Step 3: Adjust the Persona Voice

Each platform can have a different persona override:

| Platform | Where to change it |
|----------|-------------------|
| **Twitter Replies** | `projects/{slug}/prompts/twitter/persona.yaml` |
| **Twitter Threads** | Same as above (shared persona) |
| **Reddit** | `projects/{slug}/prompts/reddit/persona.yaml` |
| **LinkedIn** | `projects/{slug}/prompts/linkedin/persona.yaml` |
| **Instagram** | `projects/{slug}/prompts/instagram/persona.yaml` |
| **Email** | `email/paraphrase.yaml` (system field) |

### Step 4: Update Mention Strategy

The function templates in `prompts/{platform}/functions/` have a `MENTION STRATEGY` section. The `mention_rate` variable (passed at runtime) controls the percentage. These are product-agnostic -- they use `{{ brand.name }}` to plug in your brand.

### Step 5: Change Content Topics

For thread generation, put your topic hints in `projects/{slug}/topics.yaml`:

```yaml
twitter:
  - "5 mistakes your audience doesn't realise they're making"
  - "tools every professional in your space should know about"
  - "hot takes that will spark debate"
```

---

## Reel Templates

Reel templates live in `src/adapters/instagram/reels/templates/` and define the full video structure -- scenes, transitions, audio, and the content-generation pipeline. **For your product, you'll want your own reel concept** -- different narrative, different scenes, different voice.

### Quick route: use the meta-prompt

The fastest way to create a reel template for your product is the **meta-prompt** in [`src/adapters/instagram/reels/templates/prompt.md`](../src/adapters/instagram/reels/templates/prompt.md). Paste it into ChatGPT or Claude, fill in your brand details and reel concept, and it generates both:

1. The **template YAML** (the video structure -- scenes, beats, transitions, pipeline)
2. The **companion prompt YAML** (the AI persona that writes the script)

### Manual route: build it yourself

1. **Define your concept.** What's the story? Before/after demo? User challenge? Meme format? Tutorial speedrun?
2. **Create a prompt YAML** in `prompts/instagram/` for your script. This defines the voice, characters, and what JSON fields the LLM returns.
3. **Create a template YAML** in `src/adapters/instagram/reels/templates/`:
   - Set `id`, `name`, `default_visual` (your brand colors/name)
   - Set `caption_template`, `hashtags`, `hook_lines`
   - Define `pipeline.steps` -- at minimum one `llm` step referencing your prompt
   - Define `beats` -- 6-12 scenes with audio and transitions (30-60 second reel)
4. **Test it:** `mmn reel create --template your_template_id`

The full schema reference (every scene, every prop, every transition, every pipeline step) is in [`src/adapters/instagram/reels/templates/prompt.md`](../src/adapters/instagram/reels/templates/prompt.md).

---

## Meta-Prompt: Generate a New Prompt from Scratch

**Copy-paste the block below into ChatGPT or Claude to generate a new MarketMeNow prompt YAML file for any platform, brand, or content type.**

---

````
I need you to write a MarketMeNow prompt YAML file. MarketMeNow is an
open-source tool that auto-generates and publishes social media content
across platforms using AI.

Each prompt is a YAML file with two fields:
- system: the AI's persona, voice, rules, output format, and brand identity
- user: the per-request template with {{ variables }} for dynamic content

Here's what I need:

PLATFORM: [instagram reel / instagram carousel / twitter thread / twitter reply / linkedin post / reddit comment / email]

MY BRAND:
- Name: [your brand name]
- URL: [your URL]
- What it does: [one sentence]
- Target audience: [who you're talking to]

CONTENT TYPE: [describe what kind of content -- e.g., "a carousel post listing 5 productivity tips for remote workers"]

VOICE/TONE: [e.g., "sarcastic and funny Gen-Z energy", "professional but warm founder", "helpful Reddit commenter who happens to use the product"]

MENTION STRATEGY: [e.g., "mention the brand in ~20% of outputs, always natural, never salesy"]

OUTPUT FORMAT: [describe the JSON schema the AI should return -- what fields, what constraints]

RULES:
- The system prompt should be detailed (30-80 lines) with specific examples of the voice
- Include example phrasings the AI should use and avoid
- The user prompt should have clear {{ variable }} placeholders
- Output must be valid YAML with system: | and user: | block scalars
- Include a MENTION STRATEGY section in the system prompt
- Include specific content domain constraints (what topics to cover)

Generate the complete YAML file. Make the persona feel like a real human,
not a corporate account. The voice should be so specific that two different
runs produce content that sounds like the same person wrote it.
````

---

## Tips

- **Test incrementally.** Change one section of a prompt, generate 3-5 outputs, and compare before changing more.
- **Use winning examples.** Twitter prompts support ICL (in-context learning) via the epsilon-greedy system. The more you post, the better the AI learns your voice.
- **Keep personas specific.** "Funny and helpful" is too vague. "Chaotic-good dev tools evangelist who speaks in memes and actually helps people debug their code" is a persona.
- **Vary the output.** Add explicit rules like "Never start two consecutive items the same way" and "Every run must pick a DIFFERENT topic."
- **Control brand mentions.** The `mention_rate` variable and `MENTION STRATEGY` section prevent the AI from sounding like an ad. Start low (15-20%) and increase only if engagement proves it works.
