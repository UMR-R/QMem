"""Thin ChromaDB wrapper for retrieval-only benchmarks."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class ChromaRetrievalIndex:
    """Small utility around a Chroma collection for benchmark retrieval."""

    def __init__(
        self,
        collection_name: str,
        *,
        persist_dir: Path | None = None,
        model_cache_dir: Path | None = None,
    ) -> None:
        try:
            import chromadb  # noqa: PLC0415
            from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import (  # noqa: PLC0415
                ONNXMiniLM_L6_V2,
            )
        except ImportError as exc:
            raise ImportError(
                "chromadb is required for the Chroma retrieval benchmark. "
                'Install it with: pip install chromadb'
            ) from exc

        if persist_dir is not None:
            persist_dir.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(persist_dir))
        else:
            self._client = chromadb.EphemeralClient()
        embedding_function = ONNXMiniLM_L6_V2()
        if model_cache_dir is not None:
            model_cache_dir.mkdir(parents=True, exist_ok=True)
            embedding_function.DOWNLOAD_PATH = str(model_cache_dir / "all-MiniLM-L6-v2")
        try:
            self._client.delete_collection(name=collection_name)
        except Exception:
            pass
        self._collection = self._client.create_collection(
            name=collection_name,
            embedding_function=embedding_function,
        )

    def add_documents(self, documents: list[dict[str, Any]]) -> None:
        if not documents:
            return
        ids = [str(doc["doc_id"]) for doc in documents]
        texts = [str(doc["text"]) for doc in documents]
        metadatas: list[dict[str, Any]] = []
        for doc in documents:
            metadata = {}
            for key, value in doc.items():
                if key in {"doc_id", "text"}:
                    continue
                if isinstance(value, (str, int, float, bool)) or value is None:
                    metadata[key] = value if value is not None else ""
                elif isinstance(value, list):
                    metadata[key] = " | ".join(str(item) for item in value)
                else:
                    metadata[key] = str(value)
            metadatas.append(metadata)
        self._collection.add(ids=ids, documents=texts, metadatas=metadatas)

    def query(self, query_text: str, *, n_results: int) -> list[dict[str, Any]]:
        result = self._collection.query(
            query_texts=[query_text],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )
        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        rows: list[dict[str, Any]] = []
        for doc_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
            row = {
                "doc_id": doc_id,
                "text": document,
                "distance": distance,
            }
            if isinstance(metadata, dict):
                row.update(metadata)
            rows.append(row)
        return rows
