from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class FakeMilvusTransport:
    def __init__(self):
        self.description: str | None = None
        self.dimension: int | None = None
        self.rows: list[dict[str, Any]] = []
        self.last_filter = ""
        self.collection_exists = False

    def has_collection(self, collection_name: str) -> bool:
        del collection_name
        return self.collection_exists

    def create_collection(self, collection_name: str, *, dimension: int, description: str):
        del collection_name
        self.collection_exists = True
        self.dimension = dimension
        self.description = description

    def insert(self, collection_name: str, data: list[dict[str, Any]]):
        del collection_name
        self.rows.extend(data)
        return {"insert_count": len(data)}

    def flush(self, collection_name: str):
        del collection_name

    def load_collection(self, collection_name: str):
        del collection_name

    def describe_collection(self, collection_name: str) -> Mapping[str, Any]:
        del collection_name
        names = (
            "chunk_id", "embedding", "document_id", "tenant_id", "visibility",
            "library_scope_ids", "is_active", "payload",
        )
        return {"description": self.description, "fields": [{"name": name} for name in names]}

    def get_collection_stats(self, collection_name: str) -> Mapping[str, Any]:
        del collection_name
        return {"row_count": len(self.rows)}

    def search(
        self,
        collection_name: str,
        *,
        vector: Sequence[float],
        filter_expression: str,
        limit: int,
    ):
        del collection_name, vector
        self.last_filter = filter_expression
        return [[
            {"distance": 0.9 - position * 0.1, "entity": {"payload": row["payload"]}}
            for position, row in enumerate(self.rows[:limit])
        ]]
