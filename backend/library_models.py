"""Validated inputs for the library. No model response can execute operations."""
from __future__ import annotations

import re
import unicodedata
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LibrarySource(StrictModel):
    name: str = Field(min_length=1, max_length=150)
    root: str = Field(min_length=1, max_length=2000)
    kind: Literal["pc", "nas"] = "pc"
    writable: bool = False
    backup: bool = False
    watch: bool = False


class Metadata(StrictModel):
    tags: list[str] = Field(default_factory=list, max_length=50)
    description: str = Field(default="", max_length=12000)

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, tags):
        result = {}
        for tag in tags:
            tag = unicodedata.normalize("NFC", tag.strip())
            if not tag or len(tag) > 80 or any(ord(c) < 32 for c in tag):
                raise ValueError("Tags müssen 1–80 Zeichen lang sein, ohne Steuerzeichen.")
            result.setdefault(tag.casefold(), tag)
        return list(result.values())


class AIProposal(Metadata):
    target_id: str = ""
    suggested_name: str = Field(default="", max_length=240)
    evidence: str = Field(default="", max_length=2000)


class LibraryItem(StrictModel):
    id: str
    revision: int


class ChangeProposal(StrictModel):
    items: list[LibraryItem] = Field(min_length=1, max_length=500)
    metadata: Metadata | None = None


class FileOperation(StrictModel):
    items: list[LibraryItem] = Field(min_length=1, max_length=500)
    action: Literal["copy", "move", "rename"] = "copy"
    target_id: str = ""
    name: str = ""


class Job(StrictModel):
    kind: Literal["scan", "analyze", "hash", "index", "backup"]
    source_id: str = ""
    items: list[str] = Field(default_factory=list, max_length=100000)


class Approval(StrictModel):
    revision: int
    confirm: Literal[True]


class LibraryError(ValueError):
    pass
