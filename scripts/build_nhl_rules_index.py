from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
DEFAULT_SOURCE_DIR = ROOT_DIR / "data" / "nhl"
DEFAULT_OUTPUT_DIR = DEFAULT_SOURCE_DIR / "processed"
DEFAULT_CHROMA_DIR = DEFAULT_SOURCE_DIR / "vector_store" / "chroma"
DEFAULT_CHROMA_COLLECTION = "nhl_rules"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"

SOURCE_DOCUMENTS = {
    "rulebook": {
        "title": "NHL Rulebook",
        "filename": "nhl_rulebook.pdf",
    },
}


@dataclass(frozen=True)
class PageRecord:
    document: str
    title: str
    source_path: Path
    page: int
    text: str


@dataclass(frozen=True)
class ChunkRecord:
    chunk_id: str
    document: str
    title: str
    source_path: Path
    page_start: int
    page_end: int
    text: str
    token_count: int


@dataclass(frozen=True)
class VectorBuildResult:
    chroma_path: Path
    collection_name: str
    embedding_model: str
    inserted_count: int


def normalize_text(value: str) -> str:
    cleaned = value.replace("\x00", " ")
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT_DIR.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def project_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT_DIR / path


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def jsonl_write(path: Path, records: Iterable[dict]) -> int:
    count = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True))
            handle.write("\n")
            count += 1
    return count


def chunk_metadata(chunk: ChunkRecord) -> dict[str, str | int]:
    return {
        "chunk_id": chunk.chunk_id,
        "document": chunk.document,
        "page_end": chunk.page_end,
        "page_start": chunk.page_start,
        "source_path": relative_path(chunk.source_path),
        "title": chunk.title,
        "token_count": chunk.token_count,
    }


def embed_texts(
    *,
    texts: list[str],
    embedding_model: str,
    batch_size: int,
) -> list[list[float]]:
    if not texts:
        return []

    try:
        from backend.app.config import get_settings
        from openai import OpenAI
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "The OpenAI SDK and backend settings are required for embedding generation. "
            "Install backend requirements before running this script."
        ) from error

    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required to build the NHL rules Chroma vector index.")

    client = OpenAI(api_key=settings.openai_api_key)
    embeddings: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        response = client.embeddings.create(model=embedding_model, input=batch)
        embeddings.extend(item.embedding for item in response.data)

    if len(embeddings) != len(texts):
        raise RuntimeError(
            f"Embedding count mismatch: expected {len(texts)}, received {len(embeddings)}."
        )

    return embeddings


def build_chroma_collection(
    *,
    chunks: list[ChunkRecord],
    chroma_path: Path,
    collection_name: str,
    embedding_model: str,
    embedding_batch_size: int,
) -> VectorBuildResult:
    if not chunks:
        raise RuntimeError("No chunks were created, so the Chroma vector index cannot be built.")

    try:
        import chromadb
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "ChromaDB is required for vector index creation. Install backend requirements before running this script."
        ) from error

    chroma_path.mkdir(parents=True, exist_ok=True)
    texts = [chunk.text for chunk in chunks]
    embeddings = embed_texts(
        texts=texts,
        embedding_model=embedding_model,
        batch_size=embedding_batch_size,
    )

    client = chromadb.PersistentClient(path=str(chroma_path))
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass
    collection = client.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )
    collection.add(
        ids=[chunk.chunk_id for chunk in chunks],
        documents=texts,
        embeddings=embeddings,
        metadatas=[chunk_metadata(chunk) for chunk in chunks],
    )

    inserted_count = collection.count()
    if inserted_count != len(chunks):
        raise RuntimeError(
            f"Chroma collection count mismatch: expected {len(chunks)}, found {inserted_count}."
        )

    return VectorBuildResult(
        chroma_path=chroma_path,
        collection_name=collection_name,
        embedding_model=embedding_model,
        inserted_count=inserted_count,
    )


def validate_sources(source_dir: Path) -> dict[str, Path]:
    sources: dict[str, Path] = {}
    missing: list[str] = []

    for document, metadata in SOURCE_DOCUMENTS.items():
        path = source_dir / metadata["filename"]
        if path.exists():
            sources[document] = path
        else:
            missing.append(relative_path(path))

    if missing:
        formatted = ", ".join(missing)
        raise FileNotFoundError(f"Missing NHL rules source PDF(s): {formatted}")

    return sources


def extract_pages(source_dir: Path) -> list[PageRecord]:
    try:
        import fitz
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "PyMuPDF is required for PDF extraction. Install backend requirements before running this script."
        ) from error

    if hasattr(fitz, "TOOLS"):
        fitz.TOOLS.mupdf_display_errors(False)

    sources = validate_sources(source_dir)
    pages: list[PageRecord] = []

    for document, path in sources.items():
        title = SOURCE_DOCUMENTS[document]["title"]
        with fitz.open(path) as pdf:
            for page_index, page in enumerate(pdf, start=1):
                text = normalize_text(page.get_text("text"))
                pages.append(
                    PageRecord(
                        document=document,
                        title=title,
                        source_path=path,
                        page=page_index,
                        text=text,
                    )
                )

    return pages


def page_record_to_json(page: PageRecord) -> dict:
    return {
        "document": page.document,
        "page": page.page,
        "source_path": relative_path(page.source_path),
        "text": page.text,
        "title": page.title,
    }


def chunk_pages(
    pages: list[PageRecord],
    *,
    target_tokens: int,
    overlap_tokens: int,
) -> list[ChunkRecord]:
    chunks: list[ChunkRecord] = []

    pages_by_document: dict[str, list[PageRecord]] = {}
    for page in pages:
        pages_by_document.setdefault(page.document, []).append(page)

    for document, document_pages in pages_by_document.items():
        word_stream: list[tuple[str, int]] = []
        title = SOURCE_DOCUMENTS[document]["title"]
        source_path = document_pages[0].source_path

        for page in document_pages:
            word_stream.extend((word, page.page) for word in page.text.split())

        if not word_stream:
            continue

        chunk_index = 1
        step = max(1, target_tokens - overlap_tokens)

        for start in range(0, len(word_stream), step):
            window = word_stream[start : start + target_tokens]
            if not window:
                continue

            text = " ".join(word for word, _page in window).strip()
            if not text:
                continue

            page_start = min(page for _word, page in window)
            page_end = max(page for _word, page in window)
            chunks.append(
                ChunkRecord(
                    chunk_id=f"{document}:p{page_start:04d}:{chunk_index:04d}",
                    document=document,
                    title=title,
                    source_path=source_path,
                    page_start=page_start,
                    page_end=page_end,
                    text=text,
                    token_count=len(window),
                )
            )
            chunk_index += 1

    return chunks


def chunk_record_to_json(chunk: ChunkRecord) -> dict:
    return {
        "chunk_id": chunk.chunk_id,
        "document": chunk.document,
        "page_end": chunk.page_end,
        "page_start": chunk.page_start,
        "source_path": relative_path(chunk.source_path),
        "text": chunk.text,
        "title": chunk.title,
        "token_count": chunk.token_count,
    }


def write_index_meta(
    *,
    source_dir: Path,
    output_dir: Path,
    pages: list[PageRecord],
    chunks: list[ChunkRecord],
    documents_count: int,
    chunks_count: int,
    target_tokens: int,
    overlap_tokens: int,
    vector_build: VectorBuildResult,
) -> None:
    sources = validate_sources(source_dir)
    source_page_counts = {
        document: sum(1 for page in pages if page.document == document)
        for document in SOURCE_DOCUMENTS
    }
    text_page_counts = {
        document: sum(1 for page in pages if page.document == document and page.text)
        for document in SOURCE_DOCUMENTS
    }
    chunk_counts = {
        document: sum(1 for chunk in chunks if chunk.document == document)
        for document in SOURCE_DOCUMENTS
    }
    metadata = {
        "build_stage": "phase_3_vector_db_build",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "documents_jsonl": relative_path(output_dir / "documents.jsonl"),
        "chunks_jsonl": relative_path(output_dir / "chunks.jsonl"),
        "documents_count": documents_count,
        "chunks_count": chunks_count,
        "source_page_counts": source_page_counts,
        "text_page_counts": text_page_counts,
        "chunk_counts": chunk_counts,
        "warnings": [
            f"{SOURCE_DOCUMENTS[document]['title']} produced no extractable text and will need OCR before retrieval."
            for document, text_page_count in text_page_counts.items()
            if text_page_count == 0
        ],
        "chunking": {
            "target_tokens": target_tokens,
            "overlap_tokens": overlap_tokens,
            "token_estimate": "whitespace_words",
        },
        "embedding": {
            "model": vector_build.embedding_model,
            "provider": "openai",
        },
        "vector_store": {
            "collection_name": vector_build.collection_name,
            "inserted_count": vector_build.inserted_count,
            "path": relative_path(vector_build.chroma_path),
            "type": "chromadb",
        },
        "sources": {
            document: {
                "path": relative_path(path),
                "sha256": file_sha256(path),
                "title": SOURCE_DOCUMENTS[document]["title"],
            }
            for document, path in sources.items()
        },
    }
    path = output_dir / "index_meta.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_index(
    *,
    source_dir: Path,
    output_dir: Path,
    chroma_path: Path,
    collection_name: str,
    embedding_model: str,
    embedding_batch_size: int,
    target_tokens: int,
    overlap_tokens: int,
) -> None:
    if overlap_tokens >= target_tokens:
        raise ValueError("overlap_tokens must be smaller than target_tokens.")

    validate_sources(source_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pages = extract_pages(source_dir)
    chunks = chunk_pages(
        pages,
        target_tokens=target_tokens,
        overlap_tokens=overlap_tokens,
    )

    documents_count = jsonl_write(output_dir / "documents.jsonl", (page_record_to_json(page) for page in pages))
    chunks_count = jsonl_write(output_dir / "chunks.jsonl", (chunk_record_to_json(chunk) for chunk in chunks))
    vector_build = build_chroma_collection(
        chunks=chunks,
        chroma_path=chroma_path,
        collection_name=collection_name,
        embedding_model=embedding_model,
        embedding_batch_size=embedding_batch_size,
    )
    write_index_meta(
        source_dir=source_dir,
        output_dir=output_dir,
        pages=pages,
        chunks=chunks,
        documents_count=documents_count,
        chunks_count=chunks_count,
        target_tokens=target_tokens,
        overlap_tokens=overlap_tokens,
        vector_build=vector_build,
    )

    print(f"Source PDFs found: {', '.join(relative_path(path) for path in validate_sources(source_dir).values())}")
    print(f"Extracted pages: {documents_count}")
    print(f"Created chunks: {chunks_count}")
    for document in SOURCE_DOCUMENTS:
        document_pages = [page for page in pages if page.document == document]
        document_chunks = [chunk for chunk in chunks if chunk.document == document]
        text_pages = [page for page in document_pages if page.text]
        print(
            f"{document}: pages={len(document_pages)}, text_pages={len(text_pages)}, chunks={len(document_chunks)}"
        )
    print(f"Wrote documents: {relative_path(output_dir / 'documents.jsonl')}")
    print(f"Wrote chunks: {relative_path(output_dir / 'chunks.jsonl')}")
    print(f"Embedding model: {vector_build.embedding_model}")
    print(f"Chroma collection: {vector_build.collection_name}")
    print(f"Chroma path: {relative_path(vector_build.chroma_path)}")
    print(f"Chroma records inserted: {vector_build.inserted_count}")
    print(f"Wrote metadata: {relative_path(output_dir / 'index_meta.json')}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Stage 1 NHL rules PDF text and chunk artifacts.")
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
        help="Directory containing nhl_rulebook.pdf.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where processed artifacts will be written.",
    )
    parser.add_argument(
        "--chroma-path",
        type=Path,
        default=DEFAULT_CHROMA_DIR,
        help="Persistent ChromaDB directory for the NHL rules vector collection.",
    )
    parser.add_argument(
        "--collection-name",
        default=DEFAULT_CHROMA_COLLECTION,
        help="ChromaDB collection name for NHL rules chunks.",
    )
    parser.add_argument(
        "--embedding-model",
        default=DEFAULT_EMBEDDING_MODEL,
        help="OpenAI embedding model used for chunk vectors.",
    )
    parser.add_argument(
        "--embedding-batch-size",
        type=int,
        default=64,
        help="Number of chunks to embed in each OpenAI embedding request.",
    )
    parser.add_argument(
        "--target-tokens",
        type=int,
        default=1100,
        help="Approximate chunk size measured by whitespace-delimited words.",
    )
    parser.add_argument(
        "--overlap-tokens",
        type=int,
        default=180,
        help="Approximate chunk overlap measured by whitespace-delimited words.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build_index(
        source_dir=args.source_dir,
        output_dir=args.output_dir,
        chroma_path=project_path(args.chroma_path),
        collection_name=args.collection_name,
        embedding_model=args.embedding_model,
        embedding_batch_size=args.embedding_batch_size,
        target_tokens=args.target_tokens,
        overlap_tokens=args.overlap_tokens,
    )


if __name__ == "__main__":
    main()
