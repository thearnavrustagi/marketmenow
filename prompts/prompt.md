# How to Write Prompts for MarketMeNow

This guide explains how every prompt in MarketMeNow works, how to customize them for your brand, and includes a **meta-prompt** you can paste into ChatGPT / Claude to generate new prompts from scratch.

---

## How Prompts Work

Every prompt is a YAML file with two fields:

```yaml
system: |
  The persona, rules, and constraints the AI follows.
  This is where you define voice, tone, brand identity, and output format.

user: |
  The per-request instructions with {{ variables }} that get filled in at runtime.
  This is what changes every time the AI generates new content.
```

The `system` field is your brand's DNA. The `user` field is the task template. Variables use `{{ double_braces }}` (Jinja2) or `{single_braces}` (Python `.format()`).

---

## Prompt Inventory

| File | What it does | Key variables |
|------|-------------|---------------|
| `instagram/script_generation.yaml` | Writes the 2-character reel script (teacher roasts + Gradeasy grades) | `template_name`, `points_awarded`, `max_points`, `feedback`, `rubric_eval_text` |
| `instagram/carousel_top5.yaml` | Generates "Top 5" list carousel content with image prompts | (none -- the AI picks a fresh topic each run) |
| `instagram/autograde.yaml` | Grades a student assignment image against a rubric | `rubric_text` |
| `instagram/generate_rubric.yaml` | Creates a grading rubric from an assignment image | (none -- reads the image) |
| `twitter/thread_generation.yaml` | Writes a 7-tweet viral thread | `winning_posts`, `topic_hint` |
| `twitter/reply_generation.yaml` | Writes a single reply tweet in-character | `author_handle`, `post_text`, `reply_number`, `should_mention`, `mention_rate`, `winning_examples` |
| `linkedin/batch_generation.yaml` | Generates a batch of LinkedIn posts (text, poll, article) | `count` |
| `reddit/comment_generation.yaml` | Writes a Reddit comment as a helpful teacher | `subreddit`, `post_title`, `post_text`, `comment_number`, `should_mention`, `mention_rate` |
| `email/paraphrase.yaml` | Paraphrases email HTML so no two emails read identically | (receives raw HTML as user content) |

---

## Customizing for Your Brand

### Step 1: Find and Replace Brand References

Every prompt mentions **Gradeasy** (the default brand). To repurpose for your brand:

1. Open each YAML file in `prompts/`
2. Replace `Gradeasy` / `gradeasy.ai` with your brand name and URL
3. Replace the product description with yours
4. Keep the persona structure -- just change what the persona knows and promotes

Example -- in `twitter/reply_generation.yaml`, change:

```yaml
# Before
You ARE Gradeasy. You're the social media personality behind an AI grading
tool for teachers.

WHAT YOU KNOW:
- You're gradeasy.ai -- AI grading assistant for K-12
```

to:

```yaml
# After
You ARE CookBot. You're the social media personality behind an AI recipe
generator for home cooks.

WHAT YOU KNOW:
- You're cookbot.app -- AI recipe assistant that turns leftovers into meals
```

### Step 2: Adjust the Persona Voice

Each platform has a different voice:

| Platform | Current voice | Where to change it |
|----------|--------------|-------------------|
| **Instagram Reels** | Savage Gen-Z teacher + chill AI bro | `instagram/script_generation.yaml` -- the `CHARACTER 1` and `CHARACTER 2` sections |
| **Twitter Replies** | Unhinged-but-respectful edtech hot-take merchant | `twitter/reply_generation.yaml` -- the `YOUR PERSONALITY` section |
| **Twitter Threads** | Confident listicle strategist | `twitter/thread_generation.yaml` -- the `YOUR THREAD STYLE` section |
| **LinkedIn** | Professional founder with opinions | `linkedin/batch_generation.yaml` -- the `YOUR VOICE` section |
| **Reddit** | Helpful, experienced teacher (never salesy) | `reddit/comment_generation.yaml` -- the `YOUR PERSONA` section |
| **Email** | Casual-professional copywriter | `email/paraphrase.yaml` -- the entire `system` field |

### Step 3: Update Mention Strategy

Every social prompt has a `MENTION STRATEGY` section that controls how often and how naturally the brand gets plugged. The `mention_rate` variable (passed at runtime) controls the percentage. Adjust the example phrasings to match your brand's voice.

### Step 4: Change Content Topics

The prompts constrain what topics the AI covers. For example, `carousel_top5.yaml` says:

```yaml
Content must revolve around EDUCATION, TEACHING, and GRADING.
```

Change this to your domain:

```yaml
Content must revolve around COOKING, MEAL PREP, and KITCHEN HACKS.
```

---

## Reel Templates

Reel templates live in `src/adapters/instagram/reels/templates/` and define the full video structure -- scenes, transitions, audio, and the pipeline that generates the content. See the existing `can_ai_grade_this.yaml` for the complete schema.

To create a new reel format:

1. Copy `can_ai_grade_this.yaml` to a new file (e.g., `product_demo.yaml`)
2. Change the `id`, `name`, `caption_template`, `hashtags`, and `hook_lines`
3. Define your `pipeline.steps` (what content to generate and in what order)
4. Define your `beats` (the visual scenes and their audio)
5. Reference prompt files from `prompts/instagram/` in your pipeline's `llm` steps

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

## Examples of What You Can Generate

### New Reel Format

Use the meta-prompt above with:
- **Platform**: instagram reel
- **Content type**: "a product demo reel where a user tries to do something the hard way, then the AI tool does it instantly"
- **Voice**: "frustrated user character + smooth confident AI narrator"

Then create a matching reel template YAML in `src/adapters/instagram/reels/templates/`.

### New Twitter Persona

Use the meta-prompt with:
- **Platform**: twitter reply
- **Voice**: "chaotic-good dev tools evangelist who speaks in memes and actually helps people debug their code"
- **Mention strategy**: "only mention the product in 15% of replies, otherwise just be genuinely useful"

Save the output to `prompts/twitter/reply_generation.yaml` (replacing the existing one or creating a new variant).

### New Carousel Idea

Use the meta-prompt with:
- **Platform**: instagram carousel
- **Content type**: "before/after comparison carousel showing messy code vs clean code, 5 slides"
- **Voice**: "senior dev who's seen everything and gives advice like a tired but caring mentor"

Save to `prompts/instagram/carousel_before_after.yaml` and reference it in your carousel orchestrator.

### New LinkedIn Strategy

Use the meta-prompt with:
- **Platform**: linkedin post
- **Content type**: "mix of hot takes, polls, and storytelling posts about the startup journey"
- **Voice**: "transparent founder sharing real numbers, real struggles, occasional humor"

Save to `prompts/linkedin/batch_generation.yaml`.

---

## Tips

- **Test incrementally.** Change one section of a prompt, generate 3-5 outputs, and compare before changing more.
- **Use winning examples.** Twitter and Reddit prompts support `winning_examples` / `winning_posts` variables. Feed in your best-performing content so the AI learns your voice over time.
- **Keep personas specific.** "Funny and helpful" is too vague. "Unhinged-but-respectful edtech hot-take merchant who loves teachers and occasionally jokes about being a brand account" is a persona.
- **Vary the output.** Add explicit rules like "Never start two consecutive items the same way" and "Every run must pick a DIFFERENT topic."
- **Control brand mentions.** The `mention_rate` variable and `MENTION STRATEGY` section prevent the AI from sounding like an ad. Start low (15-20%) and increase only if engagement proves it works.
