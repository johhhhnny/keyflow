"""Audit finding and report data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Sequence

Severity = Literal["error", "warning"]


@dataclass(frozen=True, slots=True)
class AuditFinding:
    """Single actionable geometry, stability, or readability finding on a slide."""

    severity: Severity
    category: str
    slide_num: int
    scene_id: str
    frame_index: int
    message: str
    suggestion: str
    target_id: str | None = None
    suggested_action: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "severity": self.severity,
            "category": self.category,
            "slide_num": self.slide_num,
            "scene_id": self.scene_id,
            "frame_index": self.frame_index,
            "message": self.message,
            "suggestion": self.suggestion,
        }
        if self.target_id is not None:
            payload["target_id"] = self.target_id
        if self.suggested_action is not None:
            payload["suggested_action"] = self.suggested_action
        return payload


@dataclass(slots=True)
class AuditReport:
    """Visual self-check summary across every resolved slide of a deck."""

    slide_count: int
    errors: list[AuditFinding] = field(default_factory=list)
    warnings: list[AuditFinding] = field(default_factory=list)
    review_slides: list[int] = field(default_factory=list)
    min_scale: float = 1.0

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0

    def to_dict(self, preview_paths: Sequence[Path | str] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "passed": self.passed,
            "slide_count": self.slide_count,
            "min_scale": round(self.min_scale, 3),
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": [f.to_dict() for f in self.errors],
            "warnings": [f.to_dict() for f in self.warnings],
            "review_slides": list(self.review_slides),
        }
        if preview_paths is not None:
            paths = [str(p) for p in preview_paths]
            payload["review_pngs"] = [
                paths[idx - 1]
                for idx in self.review_slides
                if 1 <= idx <= len(paths)
            ]
        return payload




def select_review_slides(
    scene_frame_ranges: list[tuple[str, int, int]],
    findings: Sequence[AuditFinding],
) -> list[int]:
    """Select key slides (all flagged slides + slide 1 + final frame of each scene) for PNG visual review."""
    chosen: set[int] = set()
    for f in findings:
        chosen.add(f.slide_num)
    if scene_frame_ranges:
        chosen.add(1)
    for _, first_slide, count in scene_frame_ranges:
        if count >= 1:
            chosen.add(first_slide + count - 1)
    return sorted(chosen)


_FACTUAL_BADGES = ("FACT", "REPORTED", "VERIFIED", "DATA", "事实", "已证实")


