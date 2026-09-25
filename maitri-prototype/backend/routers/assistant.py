"""
routers/assistant.py — RAG-based clinical protocol assistant.

POST /assistant/ask
  Accepts a free-text query from the CHW and returns the most relevant
  verbatim excerpt(s) from the antenatal protocol document.

  IMPORTANT: This endpoint performs pure retrieval — it never generates
  free text.  All returned content is verbatim from the protocol file.

Module startup:
  - Loads protocols/antenatal_protocol_excerpts.md relative to this file.
  - Parses sections by '## ' headings.
  - Embeds each section with sentence-transformers (all-MiniLM-L6-v2).
  - Builds a FAISS flat cosine index.
  - Caches everything in module-level variables.
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, HTTPException

from backend.schemas import AssistantQuery, AssistantResponse

router = APIRouter(prefix="/assistant", tags=["Clinical Assistant"])

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# protocols/ lives two levels up from this file: backend/routers/ → backend/ → project root
_ROUTER_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_ROUTER_DIR)
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)
_PROTOCOL_PATH = os.path.join(_PROJECT_ROOT, "protocols", "antenatal_protocol_excerpts.md")

# ---------------------------------------------------------------------------
# Module-level cache (populated lazily on first request)
# ---------------------------------------------------------------------------

_sections: list[dict] = []          # [{"id": "section_0", "label": "...", "text": "..."}]
_embeddings = None                   # np.ndarray shape (N, D)
_faiss_index = None                  # faiss.IndexFlatIP
_model = None                        # SentenceTransformer instance
_init_error: Optional[str] = None   # human-readable startup error if any


def _load_protocol() -> None:
    """
    Parse the protocol markdown file into sections and build a FAISS index.

    Sections are split on '## ' headings.  The first segment (before any
    heading) is discarded if it is empty.  Called lazily on first /ask request.
    """
    global _sections, _embeddings, _faiss_index, _model, _init_error

    # Guard: only initialise once
    if _sections or _init_error:
        return

    # 1. Check the protocol file exists
    if not os.path.isfile(_PROTOCOL_PATH):
        _init_error = (
            f"Protocol file not found at '{_PROTOCOL_PATH}'. "
            "Please create protocols/antenatal_protocol_excerpts.md before "
            "using the assistant."
        )
        return

    # 2. Parse into sections
    with open(_PROTOCOL_PATH, "r", encoding="utf-8") as fh:
        raw = fh.read()

    parts = raw.split("\n## ")
    parsed = []
    for i, part in enumerate(parts):
        if i == 0:
            # First segment — may have a leading '## ' or be the file preamble
            text = part.lstrip("# ").strip()
            if not text:
                continue
            # Try to extract heading from first line
            lines = text.splitlines()
            label = lines[0].lstrip("# ").strip()
            body = "\n".join(lines[1:]).strip()
        else:
            lines = part.splitlines()
            label = lines[0].strip()
            body = "\n".join(lines[1:]).strip()

        if body:
            parsed.append({
                "id": f"section_{i}",
                "label": label,
                "text": body,
            })

    if not parsed:
        _init_error = "Protocol file exists but contains no parseable '## ' sections."
        return

    _sections = parsed

    # 3. Import heavy dependencies (only when needed, so backend starts fast)
    try:
        import numpy as np
        from sentence_transformers import SentenceTransformer
        import faiss  # type: ignore
    except ImportError as exc:
        _init_error = (
            f"Missing dependency for assistant: {exc}. "
            "Install with: pip install sentence-transformers faiss-cpu"
        )
        _sections = []
        return

    # 4. Embed sections
    print("[assistant] Loading sentence-transformers model (all-MiniLM-L6-v2)…")
    _model = SentenceTransformer("all-MiniLM-L6-v2")
    texts = [s["text"] for s in _sections]
    _embeddings = _model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)

    # 5. Build FAISS flat inner-product index (cosine sim on normalised vecs)
    dim = _embeddings.shape[1]
    _faiss_index = faiss.IndexFlatIP(dim)
    _faiss_index.add(_embeddings.astype("float32"))

    print(f"[assistant] Indexed {len(_sections)} protocol sections.")


# ---------------------------------------------------------------------------
# POST /assistant/ask
# ---------------------------------------------------------------------------


@router.post("/ask", response_model=AssistantResponse, summary="Ask a clinical question")
def ask(query_body: AssistantQuery):
    """
    Retrieve the most relevant protocol section(s) for a clinical question.

    This endpoint is strictly retrieval-only — no text is generated.
    The top-2 matching sections are concatenated and returned verbatim.

    Returns 503 if the protocol file or required libraries are unavailable.
    """
    # Lazy initialisation
    _load_protocol()

    if _init_error:
        raise HTTPException(status_code=503, detail=_init_error)

    if not _sections or _faiss_index is None or _model is None:
        raise HTTPException(
            status_code=503, detail="Assistant not initialised. Please check server logs."
        )

    import numpy as np

    # Embed the query (normalise for cosine similarity)
    query_vec = _model.encode(
        [query_body.query], convert_to_numpy=True, normalize_embeddings=True
    ).astype("float32")

    # Retrieve top-2 matches
    top_k = min(2, len(_sections))
    distances, indices = _faiss_index.search(query_vec, top_k)

    top_indices = indices[0]  # shape (top_k,)
    retrieved = [_sections[idx] for idx in top_indices if 0 <= idx < len(_sections)]

    if not retrieved:
        raise HTTPException(status_code=500, detail="Retrieval returned no results.")

    # Combine multiple excerpts with a separator
    primary = retrieved[0]
    if len(retrieved) > 1:
        combined_text = primary["text"] + "\n\n---\n\n" + retrieved[1]["text"]
        combined_label = f"{primary['label']} + {retrieved[1]['label']}"
    else:
        combined_text = primary["text"]
        combined_label = primary["label"]

    return AssistantResponse(
        answer=combined_text,
        source_excerpt_id=primary["id"],
        excerpt_label=combined_label,
    )
