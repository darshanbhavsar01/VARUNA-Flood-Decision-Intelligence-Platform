"""Build the SOP RAG index for the ResponsePlanner agent (§9).

Downloads real government flood-management SOP/guideline PDFs, extracts + chunks
the text, embeds each chunk with Gemini (gemini-embedding-001, 768-dim), and writes
a small self-contained index bundled into the backend container:
    backend/agents/sop_index.json

Runtime does cosine similarity over this (no vector DB, no extra infra — §6).

    python ingestion/build_sop_index.py
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from pypdf import PdfReader

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "data" / "raw" / "sops"
OUT = REPO / "backend" / "agents" / "sop_index.json"
EMBED_MODEL = "gemini-embedding-001"
EMBED_DIM = 768
CHUNK_CHARS = 1100
CHUNK_OVERLAP = 150
MAX_CHUNKS_PER_DOC = 100     # skip boilerplate-heavy tails; keep the index focused
EMBED_BATCH = 20             # contents per embed request
EMBED_SLEEP = 16             # seconds between batches -> < 100 contents/min free limit

# Real, public flood-management SOP / guideline PDFs. `cite` is the short label the
# agent uses in citations.
SOURCES = [
    {"name": "mohua_sop_urban_flooding.pdf",
     "cite": "MoHUA SOP for Urban Flooding (2017)",
     "url": "https://mohua.gov.in/upload/uploadfiles/files/SOP%20Urban%20flooding_5%20May%202017.pdf"},
    {"name": "ndma_urban_flooding_guidelines.pdf",
     "cite": "NDMA Guidelines: Management of Urban Flooding (2010)",
     "url": "https://nidm.gov.in/pdf/guidelines/new/management_urban_flooding.pdf"},
    {"name": "ndma_floods_guidelines.pdf",
     "cite": "NDMA Guidelines: Management of Floods (2008)",
     "url": "https://nidm.gov.in/pdf/guidelines/floods.pdf"},
]
HEADERS = {"User-Agent": "VARUNA-ingestion/0.1 (hackathon prototype)"}


def download(src) -> Path:
    dest = RAW / src["name"]
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  skip (exists): {dest.name}")
        return dest
    r = requests.get(src["url"], headers=HEADERS, timeout=120)
    r.raise_for_status()
    dest.write_bytes(r.content)
    print(f"  downloaded {len(r.content)//1024} KB: {dest.name}")
    return dest


def clean(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_pdf(path: Path, cite: str) -> list[dict]:
    reader = PdfReader(str(path))
    chunks = []
    for pno, page in enumerate(reader.pages, start=1):
        try:
            txt = clean(page.extract_text() or "")
        except Exception:  # noqa: BLE001
            txt = ""
        if len(txt) < 80:
            continue
        start = 0
        while start < len(txt):
            piece = txt[start:start + CHUNK_CHARS].strip()
            if len(piece) >= 120:
                chunks.append({"cite": cite, "page": pno, "text": piece})
            start += CHUNK_CHARS - CHUNK_OVERLAP
    return chunks


def embed_batch(client, texts: list[str]) -> list[list[float]]:
    from google.genai import types
    cfg = types.EmbedContentConfig(
        task_type="RETRIEVAL_DOCUMENT", output_dimensionality=EMBED_DIM)
    out = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i:i + EMBED_BATCH]
        for attempt in range(6):
            try:
                r = client.models.embed_content(model=EMBED_MODEL, contents=batch, config=cfg)
                out.extend([e.values for e in r.embeddings])
                break
            except Exception as e:  # noqa: BLE001 — honor 429 retry, else fail
                if attempt == 5:
                    raise
                wait = 20 if ("429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)) else 4
                time.sleep(wait)
        print(f"  embedded {min(i+EMBED_BATCH, len(texts))}/{len(texts)}")
        if i + EMBED_BATCH < len(texts):
            time.sleep(EMBED_SLEEP)      # stay under the 100 contents/min free limit
    return out


def main() -> int:
    load_dotenv(REPO / ".env")
    if not os.environ.get("GEMINI_API_KEY"):
        raise SystemExit("GEMINI_API_KEY not set")
    from google import genai
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    RAW.mkdir(parents=True, exist_ok=True)
    all_chunks = []
    print("Downloading + chunking SOP PDFs...")
    for src in SOURCES:
        try:
            path = download(src)
        except Exception as e:  # noqa: BLE001
            print(f"  FAILED {src['name']}: {e}")
            continue
        c = chunk_pdf(path, src["cite"])[:MAX_CHUNKS_PER_DOC]
        print(f"  {src['cite']}: {len(c)} chunks (capped {MAX_CHUNKS_PER_DOC})")
        all_chunks.extend(c)

    if not all_chunks:
        raise SystemExit("No chunks produced — check PDF downloads.")

    print(f"\nEmbedding {len(all_chunks)} chunks ({EMBED_MODEL}, {EMBED_DIM}d)...")
    vecs = embed_batch(client, [c["text"] for c in all_chunks])
    for i, (c, v) in enumerate(zip(all_chunks, vecs)):
        c["id"] = i
        c["embedding"] = [round(x, 6) for x in v]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    ingested_sources = sorted({c["cite"] for c in all_chunks})
    OUT.write_text(json.dumps({
        "model": EMBED_MODEL, "dim": EMBED_DIM,
        "sources": ingested_sources,           # only docs actually in the index
        "chunks": all_chunks,
    }), encoding="utf-8")
    size_mb = OUT.stat().st_size / 1e6
    print(f"\nWrote {OUT.relative_to(REPO)} — {len(all_chunks)} chunks, {size_mb:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
