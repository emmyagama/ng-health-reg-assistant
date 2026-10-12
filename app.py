#!/usr/bin/env python3
"""
app.py
======
Streamlit prototype for the Nigerian health-sector regulation
retrieval-augmented Q&A system.

Layout:
  Sidebar       -> project name, one-line description, prototype notice
  Main area     -> text input + "Get answer" button
                 -> answer_text (prominent)
                 -> "Sources" bulleted list of (doc_title, section_label)
                 -> small grey caption with latency + model used

Integration
-----------
Wired to the real pipeline: query_store from src/embed_store.py and
generate_answer from src/answer.py.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from embed_store import query_store
from answer import generate_answer


# ---------------------------------------------------------------------------
# Page config + sidebar
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Nigeria Health Regs Q&A",
    page_icon="⚕️",
    layout="centered",
)

with st.sidebar:
    st.markdown("## ⚕️ Nigeria Health Regs QA")
    st.caption(
        "Ask questions about Nigerian health-sector regulation and get "
        "cited answers drawn from official acts, guidelines and WHO guidance."
    )
    st.divider()
    st.caption(
        "This is a prototype for portfolio demonstration. See README for "
        "scope and limitations."
    )


# ---------------------------------------------------------------------------
# Main UI
# ---------------------------------------------------------------------------
st.title("Ask a question about Nigerian health-sector regulation")

question = st.text_input(
    label="Your question",
    placeholder="e.g. What does HEFAMAA require for facility accreditation?",
    label_visibility="collapsed",
)
submitted = st.button("Get answer", type="primary", use_container_width=True)

if submitted:
    if not question.strip():
        st.error("Please enter a question before submitting.")
    else:
        try:
            with st.spinner("Retrieving relevant passages…"):
                chunks = query_store(question, n_results=5)
            if not chunks:
                st.warning(
                    "No relevant documents were found in the corpus for that "
                    "question."
                )
            else:
                try:
                    with st.spinner("Generating answer…"):
                        result = generate_answer(question, chunks)
                except Exception as e:
                    st.error(
                        f"Answer generation failed: {type(e).__name__}: {e}\n\n"
                        "Check your GROQ_API_KEY and network connectivity."
                    )
                    # Still show retrieved sources so the user gets *something*.
                    with st.expander("Retrieved passages (shown because generation failed)"):
                        for c in chunks:
                            st.markdown(
                                f"**{c['doc_title']}** — {c['section_label']}  "
                                f"`dist={c['distance']:.3f}`"
                            )
                            st.write(c["text"])
                    result = None

                if result is not None:
                    st.markdown("### Answer")
                    st.markdown(result["answer_text"])

                    st.divider()
                    st.markdown("### Sources")
                    for c in chunks:
                        st.markdown(
                            f"- **{c['doc_title']}** — {c['section_label']}"
                        )

                    st.caption(
                        f"model: `{result['model_used']}` · "
                        f"latency: {result['latency_seconds']}s · "
                        f"tokens: {result['input_tokens']} in / {result['output_tokens']} out"
                    )

        except Exception as e:
            st.error(
                f"Retrieval failed: {type(e).__name__}: {e}\n\n"
                "Check that the vector store (chroma_db/) exists and that "
                "embed_store is importable."
            )
            with st.expander("Debug trace"):
                st.code(traceback.format_exc())
else:
    st.info(
        "Type a question above and click **Get answer**. Example: "
        "_What does HEFAMAA require for facility accreditation?_"
    )
