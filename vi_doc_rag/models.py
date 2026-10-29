"""Các kiểu dữ liệu dùng chung trong module ingestion."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

@dataclass
class RawDocument:
    source: str
    pages: List[str]
    has_pages: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Chunk:
    id: str
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Chunk":
        return cls(id=data["id"], text=data["text"], metadata=data.get("metadata", {}))
