# -*- coding: utf-8 -*-
"""Request/response models for the DsideOS content-pipeline API."""
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

Font = Literal["krutidev", "unicode"]
PaperFormat = Literal["format-1", "format-2"]


class BuildMeta(BaseModel):
    """The format-setup block present in every build workflow (frontend choices)."""
    paper_name: str = Field("Paper", description="Client-facing base name for outputs")
    format: PaperFormat = "format-1"
    font: Font = "krutidev"
    title_hindi: str = ""
    subtitle_hindi: str = ""
    solution_title: str = ""
    solution_subtitle: str = ""
    answer_source: Optional[str] = None         # "official_key" when a key is provided
    generate_explanations: bool = False          # W2: also write विस्तृत व्याख्या


class Question(BaseModel):
    n: int
    stem: str = Field(max_length=8000)
    options: list[str] = Field(default=[], max_length=12)
    answer: Optional[str] = None
    reason: Optional[str] = None
    solution: Optional[str] = None
    sources: Optional[list[str]] = None
    flag: Optional[str] = None
    image: Optional[str] = None
    option_images: Optional[list[str]] = None


class BuildRequest(BaseModel):
    # cap the list so a single request can't enqueue thousands of LLM calls
    # (build/answer-key/solutions; solutions does one Sonnet call per question).
    questions: list[Question] = Field(min_length=1, max_length=200)
    meta: BuildMeta = BuildMeta()


class JobAccepted(BaseModel):
    job_id: str
    status: str = "QUEUED"


class OutputFile(BaseModel):
    name: str
    size: int


class JobStatus(BaseModel):
    job_id: str
    status: str                       # QUEUED | RUNNING | DONE | FAILED
    stage: Optional[str] = None
    n_questions: Optional[int] = None
    outputs: list[OutputFile] = []
    error: Optional[str] = None
    created_at: Optional[int] = None
    extra: dict[str, Any] = {}
