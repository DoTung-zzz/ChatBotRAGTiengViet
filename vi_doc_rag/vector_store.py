"""Local embedding and Chroma vector-store module for vi_doc_rag JSONL chunks."""
from __future__ import annotations

import argparse
import json
import logging
import math
from pathlib import Path
from typing import Any

DEFAULT_MODEL = "AITeamVN/Vietnamese_Embedding_v2"
DEFAULT_COLLECTION = "tai_lieu_tieng_viet"
LOGGER = logging.getLogger("vi_doc_rag.vector_store")
E5_QUERY_INSTRUCTION = "Given a question in Vietnamese, retrieve passages that answer the question"


def load_chunks(jsonl_path: str | Path) -> list[dict[str, Any]]:
    """Read and validate the ingestion module's one-Chunk-per-line JSONL."""
    path = Path(jsonl_path)
    chunks: list[dict[str, Any]] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSONL lỗi ở dòng {line_no}: {exc}") from exc
            if not isinstance(row, dict) or not row.get("id") or not isinstance(row.get("text"), str):
                raise ValueError(f"Dòng {line_no} cần có 'id' và 'text' dạng chuỗi.")
            if row["id"] in seen:
                raise ValueError(f"ID chunk bị trùng ở dòng {line_no}: {row['id']}")
            if not row["text"].strip():
                LOGGER.warning("Bỏ qua chunk rỗng ở dòng %d (id=%s)", line_no, row["id"])
                continue
            metadata = row.get("metadata") or {}
            if not isinstance(metadata, dict):
                raise ValueError(f"metadata ở dòng {line_no} phải là object JSON.")
            seen.add(str(row["id"]))
            chunks.append({"id": str(row["id"]), "text": row["text"], "metadata": metadata})
    if not chunks:
        raise ValueError(f"Không có chunk hợp lệ trong {path}")
    return chunks


def _chroma_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Chroma metadata accepts scalar values; omit nulls and serialize complex values."""
    result: dict[str, Any] = {}
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            if isinstance(value, float) and not math.isfinite(value):
                continue
            result[str(key)] = value
        else:
            result[str(key)] = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return result


class LocalVectorStore:
    """Sentence Transformers encoder + persistent Chroma collection."""

    def __init__(
        self,
        db_path: str | Path = "vector_db",
        collection_name: str = DEFAULT_COLLECTION,
        model_name: str = DEFAULT_MODEL,
        batch_size: int = 8,
        device: str | None = None,
        query_instruction: str = E5_QUERY_INSTRUCTION,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size phải >= 1")
        try:
            import chromadb
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Thiếu thư viện. Cài bằng: python -m pip install -r vi_doc_rag\\requirements-embedding.txt"
            ) from exc

        self.model_name = model_name
        self.batch_size = batch_size
        self.query_instruction = query_instruction
        self.model = SentenceTransformer(model_name, device=device) if device else SentenceTransformer(model_name)
        self.max_seq_length = int(self.model.max_seq_length)
        self.tokenizer = self.model.tokenizer
        self.client = chromadb.PersistentClient(path=str(Path(db_path).resolve()))

        # Normalized vectors make cosine ranking equivalent to dot-product ranking.
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine", "embedding_model": model_name},
        )
        existing_model = (self.collection.metadata or {}).get("embedding_model")
        if existing_model and existing_model != model_name:
            raise ValueError(
                f"Collection đang chứa model {existing_model!r}, không phải {model_name!r}. "
                "Hãy dùng tên collection/đường dẫn DB mới hoặc xóa chỉ mục cũ rồi tạo lại."
            )
        if not existing_model:
            self.collection.modify(metadata={**(self.collection.metadata or {}), "embedding_model": model_name})

    def _check_length(self, texts: list[str], labels: list[str]) -> None:
        for text, label in zip(texts, labels):
            token_count = len(self.tokenizer.encode(text, add_special_tokens=True))
            if token_count > self.max_seq_length:
                raise ValueError(
                    f"{label} dài {token_count} token, vượt giới hạn model {self.max_seq_length}. "
                    "Hãy chia lại chunk; module không âm thầm cắt mất nội dung."
                )

    def _encode(self, texts: list[str], labels: list[str]) -> list[list[float]]:
        self._check_length(texts, labels)
        vectors = self.model.encode(
            texts,
            batch_size=self.batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return vectors.tolist()

    def index_chunks(self, chunks: list[dict[str, Any]], replace_sources: bool = True) -> int:
        """Index chunks; replace old chunks for each source to avoid stale results."""
        by_source: dict[str, list[dict[str, Any]]] = {}
        for chunk in chunks:
            source = str(chunk["metadata"].get("source") or chunk["metadata"].get("filename") or "")
            by_source.setdefault(source, []).append(chunk)
        total = 0
        for source, source_chunks in by_source.items():
            # Create every vector for this source before replacing its old index.
            # If tokenization/encoding fails, the existing source remains searchable.
            encoded_batches: list[tuple[list[dict[str, Any]], list[list[float]]]] = []
            for start in range(0, len(source_chunks), self.batch_size):
                batch = source_chunks[start:start + self.batch_size]
                vectors = self._encode(
                    [item["text"] for item in batch],
                    [f"chunk {item['id']}" for item in batch],
                )
                encoded_batches.append((batch, vectors))

            if replace_sources and source:
                self.collection.delete(where={"source": source})
            for batch, vectors in encoded_batches:
                metadatas = []
                for item in batch:
                    metadata = dict(item["metadata"])
                    metadata.setdefault("source", metadata.get("filename") or "")
                    metadata["chunk_id"] = item["id"]
                    metadata["embedding_model"] = self.model_name
                    metadatas.append(_chroma_metadata(metadata))
                self.collection.upsert(
                    ids=[item["id"] for item in batch],
                    embeddings=vectors,
                    documents=[item["text"] for item in batch],
                    metadatas=metadatas,
                )
                total += len(batch)
                LOGGER.info("Đã index %d/%d chunk", total, len(chunks))
        return total

    def index_jsonl(self, jsonl_path: str | Path) -> int:
        chunks = load_chunks(jsonl_path)
        return self.index_chunks(chunks)

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        if not query.strip():
            raise ValueError("Câu truy vấn không được để trống.")
        if top_k < 1:
            raise ValueError("top_k phải >= 1")
        model_query = query
        if "e5-large-instruct" in self.model_name.lower():
            model_query = f"Instruct: {self.query_instruction}\nQuery: {query}"
        query_vector = self._encode([model_query], ["câu hỏi"])[0]
        count = self.collection.count()
        if count == 0:
            return []
        found = self.collection.query(
            query_embeddings=[query_vector],
            n_results=min(top_k, count),
            include=["documents", "metadatas", "distances"],
        )
        results = []
        for i, text in enumerate(found["documents"][0]):
            distance = float(found["distances"][0][i])
            results.append({
                "text": text,
                "metadata": found["metadatas"][0][i] or {},
                "distance": distance,
                "similarity": 1.0 - distance,
            })
        return results


def _print_results(results: list[dict[str, Any]]) -> None:
    if not results:
        print("Vector database chưa có chunk nào. Hãy chạy lệnh index trước.")
        return
    for rank, item in enumerate(results, 1):
        metadata = item["metadata"]
        source = metadata.get("filename") or metadata.get("source", "không rõ nguồn")
        page_start = metadata.get("page_start")
        page_end = metadata.get("page_end")
        pages = f"trang {page_start}" if page_start == page_end else f"trang {page_start}-{page_end}"
        if page_start is None:
            pages = "không có số trang"
        print("=" * 78)
        print(f"#{rank} | cosine similarity: {item['similarity']:.4f} | {source} | {pages}")
        if metadata.get("section"):
            print(f"Mục: {metadata['section']}")
        print("-" * 78)
        print(item["text"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Tạo embedding cục bộ và tìm chunk trong ChromaDB")
    parser.add_argument("--db-path", default="vector_db", help="Thư mục lưu ChromaDB (mặc định: ./vector_db)")
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--query-instruction", default=E5_QUERY_INSTRUCTION,
                        help="Chỉ dẫn query cho multilingual-e5-large-instruct")
    parser.add_argument("--device", default=None, help="cpu hoặc cuda; mặc định để thư viện tự chọn")
    subparsers = parser.add_subparsers(dest="command", required=True)

    index_parser = subparsers.add_parser("index", help="Nhúng chunks từ JSONL và lưu vào ChromaDB")
    index_parser.add_argument("jsonl", help="Đường dẫn JSONL xuất từ vi_doc_rag")

    search_parser = subparsers.add_parser("search", help="Tìm chunk gần nhất với câu hỏi")
    search_parser.add_argument("query", help="Câu hỏi tiếng Việt")
    search_parser.add_argument("--top-k", type=int, default=5)

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    store = LocalVectorStore(args.db_path, args.collection, args.model, args.batch_size, args.device,
                             args.query_instruction)
    if args.command == "index":
        total = store.index_jsonl(args.jsonl)
        print(f"Đã lưu {total} chunk vào collection '{args.collection}'.")
        print(f"DB: {Path(args.db_path).resolve()}")
        print(f"Embedding model: {args.model}")
    else:
        _print_results(store.search(args.query, args.top_k))


if __name__ == "__main__":
    main()
