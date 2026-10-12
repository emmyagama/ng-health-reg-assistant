#!/usr/bin/env python3
"""
test_groq_api.py
Minimal test script for the Groq chat completions API.
Sends a single question about retrieval-augmented generation and prints
the response, token usage, and request latency.

Setup:
    1. Install dependencies:  pip install groq python-dotenv
    2. Create a file named `.env` in the SAME folder as this script containing:
           GROQ_API_KEY=your_actual_groq_api_key_here
       (Get a key from https://console.groq.com/keys — free tier available.)
"""

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
import groq  # For explicit Groq error types


# ---------------------------------------------------------------------------
# Load environment variables
# ---------------------------------------------------------------------------
# Load .env from the directory this script lives in (works even if you run
# the script from a different working directory).
SCRIPT_DIR = Path(__file__).resolve().parent
load_dotenv(SCRIPT_DIR / ".env")

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    print("❌ Error: GROQ_API_KEY environment variable not found.")
    print("   Create a .env file next to this script with the line:")
    print("   GROQ_API_KEY=your_groq_api_key")
    raise SystemExit(1)


# ---------------------------------------------------------------------------
# API request configuration
# ---------------------------------------------------------------------------
# NOTE: Groq retires/updates model names over time. If you get a
# "model not found" error, list what your key can access with
#   GET https://api.groq.com/openai/v1/models
# and update this constant accordingly.
MODEL = "openai/gpt-oss-120b"
USER_QUESTION = "In one sentence, what is retrieval-augmented generation?"


# ---------------------------------------------------------------------------
# Send request + handle errors
# ---------------------------------------------------------------------------
try:
    client = Groq(api_key=api_key)

    # Time ONLY the network/API call (not client initialization)
    start_time = time.perf_counter()
    chat_completion = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": USER_QUESTION}],
        temperature=0.0,  # Deterministic output for consistent testing
    )
    elapsed_seconds = time.perf_counter() - start_time

    # Extract response fields
    answer_text = chat_completion.choices[0].message.content.strip()
    input_tokens = chat_completion.usage.prompt_tokens
    output_tokens = chat_completion.usage.completion_tokens

    # Print results
    print("✅ Groq API call succeeded!\n")
    print(f"Response:       {answer_text}\n")
    print(f"Input tokens:   {input_tokens}")
    print(f"Output tokens:  {output_tokens}")
    print(f"Request time:   {elapsed_seconds:.2f} seconds")

except groq.AuthenticationError:
    print("❌ Authentication failed: Your GROQ_API_KEY is invalid or revoked.")
    print("   Double-check the key in your .env file, or generate a new one at")
    print("   https://console.groq.com/keys")
    raise SystemExit(1)

except groq.APIConnectionError:
    print("❌ Connection error: Could not reach the Groq API.")
    print("   Check your internet connection and that api.groq.com is not blocked.")
    raise SystemExit(1)

except groq.APIStatusError as e:
    # Catches 4xx/5xx errors: model not found, rate limits, bad requests, etc.
    print(f"❌ API returned an error (HTTP {e.status_code}): {e.message}")
    if e.status_code == 404:
        print(f"   Hint: The model '{MODEL}' may be deprecated. Check Groq's")
        print("         current model list at https://console.groq.com/docs/models")
    raise SystemExit(1)

except Exception as e:
    # Generic catch-all so users never see a raw traceback
    print(f"❌ Unexpected error: {type(e).__name__}: {e}")
    raise SystemExit(1)
