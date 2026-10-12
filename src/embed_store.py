#!/usr/bin/env python3
"""
embed_store.py
=============
Build (and query) a local ChromaDB vector store for document chunks
produced by src/chunker.py.

Workflow
--------
1. build_vector_store()  - load chunk JSON, embed with all-MiniLM-L6-v2,
                           persist to Chroma; idempotent (skips already-seen ids).
2. query_store()         - embed a question, retrieve top-n chunks.

When run as a script:
  * Builds the store from data/processed/all_chunks.json -> chroma_db/
  * Runs a demo question and pretty-prints the top 5 hits.
  * First run downloads the ~80MB all-MiniLM-L6-v2 model into the local
    Hugging Face cache (free, one-time, then reused offline).

Dependencies: sentence-transformers, chromadb (+ what they pull in).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from sentence_transformers import SentenceTransformer
import chromadb


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CHUNKS_PATH = ROOT / "data" / "processed" / "all_chunks.json"
DEFAULT_PERSIST_DIR = str(ROOT / "chroma_db")
COLLECTION_NAME = "ng_health_regs"
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"

# Re-used across calls within a process so we don't re-load the model
# every time query_store() is called.
_model: Optional[SentenceTransformer] = None

# ---------------------------------------------------------------------------
# Query-side acronym expansion (bucket C)
# ---------------------------------------------------------------------------
# Appended to the question before encoding. Stored chunks are never modified.
QUERY_ACRONYM_EXPANSIONS: dict[str, str] = {
    "CSHIS": "Contributory Social Health Insurance Scheme",
    "HIUOR": "Health Insurance Under One Roof",
    "BHCPF": "Basic Health Care Provision Fund",
    "QMS": "Quality Management System",
    "MLSCN": "Medical Laboratory Science Council of Nigeria",
    "NDPC": "Nigeria Data Protection Commission",
    "NDPA": "Nigeria Data Protection Act",
    "NHIA": "National Health Insurance Authority",
    "HEFAMAA": "Health Facilities Monitoring and Accreditation Agency",
}

# Internal over-fetch so the per-doc diversity filter can still fill
# the requested number of results when one document dominates the top-10.
# 3/doc on an 8-doc corpus: 2 was too aggressive and evicted a doc's own
# best chunk (regressed Q3/Q5/Q10, pulled MLSCN/WHO noise into Q27).
INTERNAL_FETCH_K = 10
MAX_PER_DOC = 3


def _expand_query(question: str) -> str:
    """Append spelled-out forms for standalone acronyms in the question."""
    expansions = []
    for acronym, spelled in QUERY_ACRONYM_EXPANSIONS.items():
        if re.search(rf"\b{re.escape(acronym)}\b", question):
            expansions.append(spelled)
    if not expansions:
        return question
    return f"{question} (also: {'; '.join(expansions)})"


def _get_model() -> SentenceTransformer:
    """Lazily load (and cache) the sentence-transformers embedding model."""
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBED_MODEL_NAME)
    return _model


# ---------------------------------------------------------------------------
# 1. Build the vector store
# ---------------------------------------------------------------------------
def build_vector_store(
    chunks_path: str = str(DEFAULT_CHUNKS_PATH),
    persist_dir: str = DEFAULT_PERSIST_DIR,
) -> int:
    """Embed all chunks and add them to a persistent Chroma collection.

    Parameters
    ----------
    chunks_path : path to the all_chunks.json file written by src/chunker.py.
    persist_dir : directory where Chroma will persist the database on disk.

    Returns
    -------
    Total number of chunks now in the collection.
    """
    chunks_path_p = Path(chunks_path)
    if not chunks_path_p.exists():
        raise FileNotFoundError(
            f"Chunks file not found: {chunks_path_p}. "
            "Run src/chunker.py first to generate it."
        )

    with chunks_path_p.open("r", encoding="utf-8") as f:
        chunks = json.load(f)

    print(f"Loaded {len(chunks)} chunk(s) from {chunks_path_p}")

    # Init Chroma (persistent, on disk) and get / create the collection.
    client = chromadb.PersistentClient(path=persist_dir)
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "l2"},  # explicit L2 so it's obvious; this is also default
    )

    # Find which chunk_ids are already in the collection so we can skip them.
    existing_ids: set[str] = set()
    if collection.count() > 0:
        # Chroma's .get() returns all ids; chunking by offset in case of huge stores.
        offset = 0
        limit = 1000
        while True:
            batch = collection.get(limit=limit, offset=offset)
            ids_batch = batch.get("ids", [])
            if not ids_batch:
                break
            existing_ids.update(ids_batch)
            if len(ids_batch) < limit:
                break
            offset += limit

    # Filter to chunks not yet added.
    new_chunks = [c for c in chunks if c["chunk_id"] not in existing_ids]
    skipped = len(chunks) - len(new_chunks)

    if not new_chunks:
        print(f"No new chunks to add ({skipped} already present).")
        print(f"Collection '{COLLECTION_NAME}' now contains {collection.count()} chunk(s).")
        return collection.count()

    # Embed only the new chunks.
    texts = [c["text"] for c in new_chunks]
    ids = [c["chunk_id"] for c in new_chunks]
    metadatas = [
        {
            "doc_id": c.get("doc_id", ""),
            "doc_title": c.get("doc_title", ""),
            "section_label": c.get("section_label", ""),
        }
        for c in new_chunks
    ]

    print(f"Embedding {len(new_chunks)} new chunk(s) with '{EMBED_MODEL_NAME}'...")
    model = _get_model()
    embeddings = model.encode(
        texts,
        show_progress_bar=True,
        normalize_embeddings=False,  # keep raw embeddings consistent with L2 metric
    ).tolist()

    # Chroma recommends batching large adds; we'll do batches of 500.
    batch_size = 500
    for i in range(0, len(ids), batch_size):
        collection.add(
            ids=ids[i : i + batch_size],
            embeddings=embeddings[i : i + batch_size],
            documents=texts[i : i + batch_size],
            metadatas=metadatas[i : i + batch_size],
        )

    total = collection.count()
    print(f"Added {len(new_chunks)} new chunk(s); skipped {skipped} already-existing.")
    print(f"Collection '{COLLECTION_NAME}' now contains {total} chunk(s).")
    return total


# ---------------------------------------------------------------------------
# 2. Query the store
# ---------------------------------------------------------------------------
def query_store(
    question: str,
    n_results: int = 5,
    persist_dir: str = DEFAULT_PERSIST_DIR,
) -> list[dict]:
    """Embed a question and return the top-n most similar chunks.

    Retrieval strategy
    ------------------
    1. Expand acronyms in the question (QUERY_ACRONYM_EXPANSIONS).
    2. Ask Chroma for INTERNAL_FETCH_K neighbours.
    3. Keep at most MAX_PER_DOC chunks per doc_id (closest first) so one
       document cannot flood the result list.
    4. Return the first n_results of that diversity-filtered list
       (still ordered by ascending distance).

    Returns
    -------
    List of dicts with keys: chunk_id, doc_id, doc_title, section_label,
    text, distance.

    Distance note (Chroma default / this collection):
        The collection uses L2 (squared Euclidean) distance.
        -> LOWER distance = MORE similar (0 = identical embedding).
    """
    client = chromadb.PersistentClient(path=persist_dir)
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "l2"},
    )

    if collection.count() == 0:
        print("WARNING: the collection is empty. Run build_vector_store() first.")
        return []

    model = _get_model()
    expanded = _expand_query(question)
    q_embedding = model.encode([expanded]).tolist()

    total = collection.count()
    picked: list[dict] = []
    fetch_k = max(INTERNAL_FETCH_K, n_results)

    while True:
        results = collection.query(
            query_embeddings=q_embedding,
            n_results=min(fetch_k, total),
            include=["documents", "metadatas", "distances"],
        )
        hits = []
        for chunk_id, doc, meta, dist in zip(
            results["ids"][0],
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            hits.append(
                {
                    "chunk_id": chunk_id,
                    "doc_id": meta.get("doc_id", ""),
                    "doc_title": meta.get("doc_title", ""),
                    "section_label": meta.get("section_label", ""),
                    "text": doc,
                    "distance": dist,
                }
            )

        per_doc: dict[str, int] = {}
        picked = []
        for hit in hits:  # Chroma returns these sorted by ascending distance
            count = per_doc.get(hit["doc_id"], 0)
            if count >= MAX_PER_DOC:
                continue
            per_doc[hit["doc_id"]] = count + 1
            picked.append(hit)

        # Over-fetch only when the diversity filter could not fill n_results
        # (e.g. a query where the top-10 all come from one or two documents).
        if len(picked) < min(n_results, total) and fetch_k < total:
            fetch_k = min(fetch_k * 3, total)
            continue
        break

    return picked[:n_results]


# ---------------------------------------------------------------------------
# 3. __main__: build + demo query
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    build_vector_store()

    question = "What does HEFAMAA require for facility accreditation?"
    print(f"\nQuerying: {question!r}")
    print("-" * 72)
    hits = query_store(question, n_results=5)

    if not hits:
        print("(no results)")
    else:
        for rank, h in enumerate(hits, start=1):
            print(f"\n#{rank}  distance={h['distance']:.4f}")
            print(f"    doc_title:     {h['doc_title']}")
            print(f"    section_label: {h['section_label']}")
            snippet = h["text"].replace("\n", " ")
            if len(snippet) > 200:
                snippet = snippet[:200] + "..."
            print(f"    snippet:       {snippet}")
