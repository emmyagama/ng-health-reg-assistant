#!/usr/bin/env python3
"""
test_structured_output.py
Compares Groq chat-completion structured JSON extraction between:
  Run A — a short, minimal prompt
  Run B — a bloated prompt: the same extraction instructions repeated
          three times, preceded by ≥500 words of irrelevant filler text

Both runs ask the model to extract structured data from the same sentence
and return ONLY valid JSON matching a fixed schema.

Setup:
    pip install groq python-dotenv
    echo "GROQ_API_KEY=your_key_here" > .env
    python3 test_structured_output.py
"""

import json
import os
import sys
import time
from pathlib import Path

# Windows consoles default to cp1252, which cannot encode the check/cross
# glyphs used below. Force UTF-8 and degrade gracefully if a glyph is
# still unencodable instead of crashing with UnicodeEncodeError.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
from groq import Groq
import groq


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# NOTE: Groq may retire model names over time. If you hit a 404, check
# https://console.groq.com/docs/models for the current available list and
# update this constant. This key currently exposes only a restricted set;
# openai/gpt-oss-120b is the largest chat model available on it.
MODEL = "openai/gpt-oss-120b"

# The source sentence we want the model to extract structured data from.
SOURCE_SENTENCE = (
    "The Medical Laboratory Science Council of Nigeria requires annual "
    "facility inspections under Section 12 of its 2021 guidelines."
)

# The JSON schema described in natural language (kept identical across runs).
JSON_SCHEMA_INSTRUCTIONS = (
    'Return ONLY valid JSON (no markdown, no commentary, no code fences) '
    'matching exactly this shape: '
    '{"organisation": string, "requirement": string, '
    '"section_reference": string, "year": string}. '
    '"year" should be the 4-digit year as a string.'
)


# ---------------------------------------------------------------------------
# Load API key
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
load_dotenv(SCRIPT_DIR / ".env")

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    print("❌ Error: GROQ_API_KEY environment variable not found.")
    print("   Create a .env file next to this script containing:")
    print("   GROQ_API_KEY=your_groq_api_key")
    raise SystemExit(1)


# ---------------------------------------------------------------------------
# Prompt definitions
# ---------------------------------------------------------------------------
# Run A — short, minimal prompt
SHORT_PROMPT = f"""Extract structured information from the following sentence.

{JSON_SCHEMA_INSTRUCTIONS}

Sentence: "{SOURCE_SENTENCE}"
"""

# Run B — bloated prompt: long irrelevant filler + instruction repeated 3×.
# The filler text below is deliberately off-topic (weather, bread recipes,
# penguin facts, astronomy, etc.) so it adds tokens without giving away
# anything about the answer. It is well over 500 words.
FILLER_PARAGRAPHS = """
Before we get to the task, please take a moment to read through the
following background material. It is not directly relevant to the
question you will eventually be asked, but it is important that you
process it carefully and do not skip any portion of it.

The weather in coastal regions often depends on a complex interplay of
ocean currents, prevailing winds, and atmospheric pressure systems. On
an average Tuesday in a small seaside town, one might observe seagulls
circling above the fishing pier, a light mist rolling in from the
harbour, and the distant sound of a foghorn warning ships away from
shallow rocks. Fishermen carefully check their nets, mend frayed ropes,
and discuss the tides while drinking dark coffee from chipped mugs.
Tourists wander along the boardwalk, taking photographs of lighthouses
and purchasing saltwater taffy from vendors who have been in business
for three generations. Children build sandcastles and chase crabs
across the wet sand while their parents read newspapers under striped
umbrellas.

Baking sourdough bread is a deceptively simple art that rewards
patience and attentiveness. A mature starter, maintained daily with
equal parts flour and water by weight, develops a complex community of
wild yeasts and lactic-acid bacteria that leaven the dough and produce
the bread's characteristic tang. Bakers typically autolyse their flour
and water for thirty to sixty minutes before adding salt and starter,
allowing gluten to form naturally without vigorous kneading. Over the
next several hours the dough undergoes a series of gentle folds at
regular intervals, building strength while retaining gas. After bulk
fermentation the loaf is shaped, placed seam-side up in a floured
banneton, and retarded overnight in the refrigerator. The next morning
it is turned out onto a preheated Dutch oven, scored with a sharp lame,
and baked at high temperature under cover for the first twenty minutes
to trap steam, which allows the crust to expand dramatically before it
sets. The result is a loaf with a blistered, caramelised crust and an
open, airy crumb shot through with irregular holes.

Emperor penguins, the largest of all living penguin species, breed
during the brutal Antarctic winter, when temperatures routinely drop
below minus fifty degrees Celsius and winds can exceed two hundred
kilometres per hour. After a single egg is laid, the female transfers
it carefully to the male, who balances it on his feet, tucked beneath
a warm flap of abdominal skin, for more than two months while she
travels to the sea to feed. Throughout this period the males huddle
together in dense colonies, constantly rotating positions so that no
individual bears the full brunt of the wind for too long. When the
chicks finally hatch, the females return, their bellies full of fish
and squid to regurgitate for the newborns, and the emaciated males
make the long trek back to open water to feed themselves.

Astronomers measuring the expansion rate of the universe rely on a
cosmic distance ladder whose rungs connect nearby phenomena, such as
parallax measurements of Cepheid variable stars, to faraway
Type Ia supernovae whose intrinsic brightness is remarkably uniform.
Recent observations from the James Webb Space Telescope have refined
these measurements, producing a Hubble constant that remains in
tension with the value inferred from the cosmic microwave background,
a discrepancy now widely referred to as the Hubble tension. Whether
this tension points to new physics beyond the standard Lambda-CDM
model, or simply to unaccounted-for systematic errors in one or more
rungs of the ladder, is one of the most actively debated questions in
cosmology today.

Houseplants, when tended with care, can transform an otherwise sterile
indoor space into a lush and calming environment. Monsteras develop
their characteristic fenestrations only after producing several
mature leaves, a trait believed in the wild to help the plant
withstand heavy tropical rainfall and allow light to reach lower
foliage. Pothos vines, nearly indestructible, tolerate low light and
irregular watering, making them ideal for beginners. Snake plants,
native to arid regions of West Africa, store water in their thick
succulent leaves and prefer to dry out completely between waterings.
Fiddle-leaf figs, on the other hand, are notoriously finicky, reacting
badly to drafts, repositioning, over-watering, and under-watering
alike; their dramatic, violin-shaped leaves nevertheless make them a
popular statement piece in modern interior design.

With that background out of the way, please proceed carefully with
the actual task described below. Read every word of the instructions
and follow them precisely.

"""

# Repeat the extraction instructions three times for emphasis / padding.
REPEATED_INSTRUCTIONS = (
    (JSON_SCHEMA_INSTRUCTIONS + "\n\n") * 3
)

BLOATED_PROMPT = (
    FILLER_PARAGRAPHS
    + REPEATED_INSTRUCTIONS
    + f'\nNow please perform the extraction on this sentence: "{SOURCE_SENTENCE}"\n'
)


# ---------------------------------------------------------------------------
# Helper: run one extraction
# ---------------------------------------------------------------------------
def run_extraction(label: str, prompt: str) -> None:
    """Send one chat-completion request and print results."""
    print(f"\n{'='*60}")
    print(f"Run: {label}")
    print(f"Prompt length (chars): {len(prompt):,}")
    print(f"{'='*60}")

    parse_ok = False
    total_tokens = None
    answer_text = ""
    latency = None

    try:
        client = Groq(api_key=api_key)

        start = time.perf_counter()
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system",
                 "content": "You are a precise information-extraction assistant. "
                            "You output only valid JSON — absolutely nothing else."},
                {"role": "user", "content": prompt},
            ],
            # Setting temperature to 0 makes the model deterministic, which
            # helps when comparing output quality across runs.
            temperature=0.0,
            # response_format={"type": "json_object"} would enforce JSON at the
            # API level, but we deliberately do NOT use it so that we can also
            # exercise our own json.loads error-handling path.
        )
        latency = time.perf_counter() - start

        answer_text = completion.choices[0].message.content
        total_tokens = completion.usage.total_tokens

        # Try to parse
        parsed = json.loads(answer_text)
        parse_ok = True
        print("✅ JSON parsed successfully!")
        print(f"Parsed object: {json.dumps(parsed, indent=2)}")

    except json.JSONDecodeError:
        print("❌ The model did NOT return valid JSON.")
        print("--- Raw response returned by the model ---")
        print(answer_text)
        print("--- End raw response ---")
        print("Reason: response failed json.loads() — model did not follow "
              "the required JSON format.")

    except groq.AuthenticationError:
        print("❌ Authentication failed: GROQ_API_KEY is invalid or revoked.")
        print("   Check your .env file or get a new key at "
              "https://console.groq.com/keys")

    except groq.APIConnectionError:
        print("❌ Connection error: could not reach the Groq API. "
              "Check your network.")

    except groq.APIStatusError as e:
        print(f"❌ API error (HTTP {e.status_code}): {e.message}")
        if e.status_code == 404:
            print(f"   Hint: model '{MODEL}' may be deprecated. "
                  "Check https://console.groq.com/docs/models")

    except Exception as e:
        print(f"❌ Unexpected error: {type(e).__name__}: {e}")

    # Always print comparison metrics when we have them
    if total_tokens is not None:
        print(f"Total tokens used (in+out): {total_tokens}")
    else:
        print("Total tokens used: N/A (request did not complete)")

    if latency is not None:
        print(f"Latency: {latency:.3f} seconds")
    else:
        print("Latency: N/A (request did not complete)")

    print(f"JSON parse succeeded: {parse_ok}")


# ---------------------------------------------------------------------------
# Run both prompts and compare
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Sanity check that the filler is ≥ 500 words
    filler_word_count = len(FILLER_PARAGRAPHS.split())
    print(f"Filler text word count: {filler_word_count} "
          f"({'≥ 500 ✓' if filler_word_count >= 500 else '< 500 — TOO SHORT'})")

    run_extraction("A — short minimal prompt", SHORT_PROMPT)
    run_extraction("B — bloated prompt (filler + instructions repeated 3×)",
                   BLOATED_PROMPT)

    # Final summary line so the two runs are easy to compare side by side.
    print(f"\n{'='*60}")
    print("Done. Compare the token counts and latencies above.")
