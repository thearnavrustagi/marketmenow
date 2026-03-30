from __future__ import annotations

import random

AITA_SCENARIOS: list[str] = [
    # --- Grading & Assessment ---
    "giving a student a zero for using ChatGPT on their essay",
    "refusing to round up a 89.4 to an A",
    "marking a student wrong for getting the right answer but showing no work",
    "failing a student who plagiarized their entire final project",
    "giving different grades to two students who submitted nearly identical work",
    "not accepting a late assignment even though the student had a family emergency",
    "deducting points for messy handwriting on a math test",
    "refusing to let a student retake an exam they slept through",
    "giving a pop quiz the day after a school dance",
    "marking answers wrong because students didn't follow the exact format I asked for",
    "grading participation and giving a quiet student a C",
    "not curving a test where the class average was 42%",
    "calling out a student for clearly copying homework word-for-word",
    "refusing to give extra credit at the end of the semester",
    "giving a B+ to the valedictorian candidate and ruining their 4.0",

    # --- Classroom Management ---
    "confiscating a student's phone during a test and their parent called the principal",
    "kicking a student out of class for being disruptive during a group presentation",
    "not letting a student go to the bathroom during a timed test",
    "moving a student's seat away from their best friend for talking too much",
    "banning snacks from my classroom after ants became a problem",
    "making the whole class stay after the bell because nobody would stop talking",
    "telling a student their excuse for missing homework wasn't believable",
    "refusing to let a student present late because they weren't prepared on the due date",
    "sending a student to the office for arguing with me in front of the class",
    "not letting students listen to music while working on assignments",

    # --- Parent Interactions ---
    "telling a parent their child is not gifted, just average",
    "refusing to change a grade after a parent emailed me five times",
    "telling a parent I can't make their kid do homework at home",
    "cc'ing the principal on a reply to an aggressive parent email",
    "telling a parent their child is the bully, not the victim",
    "refusing a parent-teacher conference at 7am because it's before my contract hours",
    "telling helicopter parents to stop doing their kid's science project",
    "sending home a note about hygiene for a student and the parent was furious",
    "declining to write a college recommendation letter for a student I barely know",
    "telling a parent their child needs professional help and it's beyond what I can do",

    # --- Colleague Drama ---
    "reporting a fellow teacher for never actually teaching and just showing movies",
    "refusing to cover a colleague's class on my planning period again",
    "telling a new teacher their lesson plan won't work and they got upset",
    "not sharing my lesson plans with a colleague who never makes their own",
    "going to admin about a colleague who grades everything with a rubber stamp A",
    "declining to join the party planning committee for the fourth year in a row",
    "telling my department head their new curriculum idea is terrible",
    "eating lunch alone instead of in the teacher's lounge because the gossip is toxic",
    "refusing to write a positive peer review for a teacher I think is ineffective",
    "pushing back on a team decision to pass a student who didn't meet any standards",

    # --- Technology & Modern Teaching ---
    "banning laptops in class after catching students on social media",
    "requiring handwritten notes instead of typed ones",
    "telling students they can't use Google Translate for their Spanish homework",
    "refusing to post grades online every single week like admin wants",
    "making students do a presentation in person instead of submitting a video",
    "not using the textbook the school provided because it's outdated",
    "letting students use AI tools for brainstorming but not for final drafts",
    "recording my lectures and a student's parent complained about privacy",
    "switching to digital-only submissions and a student without reliable internet struggled",
    "refusing to accept a Google Doc shared at 11:59pm as 'on time'",

    # --- Workload & Boundaries ---
    "leaving school at contract time instead of staying late like everyone else",
    "not answering parent emails on weekends",
    "telling my principal I can't take on another extracurricular activity",
    "using my sick days for mental health and a colleague made a comment",
    "saying no to chaperoning prom because I wanted a Saturday to myself",
    "not attending a student's sports game even though they personally invited me",
    "telling admin that 35 students per class is too many and I need support",
    "taking a personal day the Friday before a long weekend",
    "refusing to tutor a student for free after school when I have my own kids to pick up",
    "setting an auto-reply on email after 5pm",

    # --- Student Situations ---
    "calling home when a student fell asleep in class for the third time",
    "recommending a student for a lower-level class next year",
    "not nominating a popular student for a leadership award because they have poor character",
    "telling a student their career goal is unrealistic and suggesting a backup plan",
    "making a student redo an assignment because I know they can do better",
    "privately asking a student if everything is okay at home after noticing changes",
    "pairing a struggling student with the class overachiever for a group project",
    "giving a student an incomplete instead of a failing grade to buy them time",
    "not writing 'great job!' on every paper and a student's parent said I'm discouraging",
    "telling a senior they might not graduate on time",
]

assert len(AITA_SCENARIOS) >= 70, f"Expected 70+ scenarios, got {len(AITA_SCENARIOS)}"


def pick_random_aita() -> str:
    """Return a randomly selected AITA teaching scenario."""
    return random.choice(AITA_SCENARIOS)
