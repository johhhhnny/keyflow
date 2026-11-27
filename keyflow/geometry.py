"""Stage 4 · Layout & Geometry Engineering.

Factual geometry auditing (out-of-bounds, text-fit estimation, and unexpected
sibling collisions). Never makes aesthetic or layout decisions on behalf of
the agent — only verifies geometric feasibility.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from keyflow.spec import (
    GroupSpec,
    SlideSpec,
    SizeSpec,
    TextboxSpec,
    TextSpec,
    VisualObjectSpec,
)


@dataclass
class GeometryIssue:
    """One factual geometry observation on a slide."""

    kind: str  # "out_of_bounds" | "text_overflow" | "overlap"
    object_id: str
    message: str
    other_id: str | None = None


@dataclass
class GeometryAudit:
    """Complete Stage 4 geometry report for a slide."""

    slide_index: int
    issues: list[GeometryIssue] = field(default_factory=list)

    @property
    def summary_notes(self) -> list[str]:
        return [f"slide {self.slide_index} [{i.kind}]: {i.message}" for i in self.issues]


def _char_display_width(ch: str) -> float:
    """Approximate width in ems: CJK ~1.0em, Latin/digits ~0.55em."""
    if ord(ch) > 0x2E80:
        return 1.0
    return 0.56


def estimate_text_height(text: TextSpec, box_w: float, padding_x: float = 0.0) -> float:
    """Estimate required height in points for a TextSpec inside width box_w."""
    avail_w = max(20.0, box_w - padding_x)
    total_h = 0.0

    if text.paragraphs is not None:
        for p in text.paragraphs:
            p_style = p.style or text.style
            p_spacing = p.line_spacing or text.line_spacing
            line_w = 0.0
            lines = 1
            max_font = p_style.size
            for r in p.runs:
                r_style = r.style or p_style
                max_font = max(max_font, r_style.size)
                for ch in r.text:
                    if ch == "\n":
                        lines += 1
                        line_w = 0.0
                        continue
                    cw = _char_display_width(ch) * r_style.size * (1.0 + max(0.0, r_style.tracking))
                    if line_w + cw > avail_w and line_w > 0:
                        lines += 1
                        line_w = cw
                    else:
                        line_w += cw
            total_h += lines * max_font * p_spacing + p.space_before + p.space_after
        return total_h

    raw = text.string or ""
    font_sz = text.style.size
    line_w = 0.0
    lines = 1
    for ch in raw:
        if ch == "\n":
            lines += 1
            line_w = 0.0
            continue
        cw = _char_display_width(ch) * font_sz * (1.0 + max(0.0, text.style.tracking))
        if line_w + cw > avail_w and line_w > 0:
            lines += 1
            line_w = cw
        else:
            line_w += cw
    return lines * font_sz * text.line_spacing


def _flatten_positioned(
    objects: list[VisualObjectSpec],
) -> list[tuple[str, VisualObjectSpec]]:
    out: list[tuple[str, VisualObjectSpec]] = []
    for idx, obj in enumerate(objects):
        oid = obj.id or f"{obj.type}_{idx}"
        if isinstance(obj, GroupSpec):
            out.extend(_flatten_positioned(obj.children))
        elif hasattr(obj, "geometry"):
            out.append((oid, obj))
    return out


def _is_ambient(obj: VisualObjectSpec) -> bool:
    return obj.semantic is not None and obj.semantic.hierarchy == "ambient"


def _contains(outer: VisualObjectSpec, inner: VisualObjectSpec) -> bool:
    og = outer.geometry  # type: ignore[attr-defined]
    ig = inner.geometry  # type: ignore[attr-defined]
    return (
        og.x <= ig.x + 2
        and og.y <= ig.y + 2
        and og.x + og.w >= ig.x + ig.w - 2
        and og.y + og.h >= ig.y + ig.h - 2
    )


def _intersection_area(a: VisualObjectSpec, b: VisualObjectSpec) -> float:
    ag = a.geometry  # type: ignore[attr-defined]
    bg = b.geometry  # type: ignore[attr-defined]
    ix0 = max(ag.x, bg.x)
    iy0 = max(ag.y, bg.y)
    ix1 = min(ag.x + ag.w, bg.x + bg.w)
    iy1 = min(ag.y + ag.h, bg.y + bg.h)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    return (ix1 - ix0) * (iy1 - iy0)


def audit_slide_geometry(
    slide: SlideSpec,
    slide_size: SizeSpec,
    slide_index: int = 0,
) -> GeometryAudit:
    """Run factual geometry checks on a single slide."""
    audit = GeometryAudit(slide_index=slide_index)
    positioned = _flatten_positioned(slide.objects)
    cw, ch = slide_size.w, slide_size.h

    for oid, obj in positioned:
        g = obj.geometry  # type: ignore[attr-defined]
        if not _is_ambient(obj):
            if g.x < 0 or g.y < 0 or g.x + g.w > cw or g.y + g.h > ch:
                audit.issues.append(
                    GeometryIssue(
                        kind="out_of_bounds",
                        object_id=oid,
                        message=(
                            f"{oid} ({g.x:.0f},{g.y:.0f} {g.w:.0f}x{g.h:.0f}) "
                            f"extends outside {cw:.0f}x{ch:.0f} canvas"
                        ),
                    )
                )

        if isinstance(obj, TextboxSpec) and not obj.shrink_to_fit:
            pad_x = obj.padding.left + obj.padding.right
            pad_y = obj.padding.top + obj.padding.bottom
            est_h = estimate_text_height(obj.text, g.w, pad_x)
            avail_h = max(1.0, g.h - pad_y)
            if est_h > avail_h * 1.15:
                audit.issues.append(
                    GeometryIssue(
                        kind="text_overflow",
                        object_id=oid,
                        message=(
                            f"{oid} estimated text height {math.ceil(est_h)}pt "
                            f"exceeds box height {avail_h:.0f}pt"
                        ),
                    )
                )

    # Unexpected sibling overlaps (skip ambient objects and intentional panel/card containment)
    for i in range(len(positioned)):
        id_a, obj_a = positioned[i]
        if _is_ambient(obj_a):
            continue
        for j in range(i + 1, len(positioned)):
            id_b, obj_b = positioned[j]
            if _is_ambient(obj_b):
                continue
            if _contains(obj_a, obj_b) or _contains(obj_b, obj_a):
                continue
            area = _intersection_area(obj_a, obj_b)
            if area <= 0.0:
                continue
            ag = obj_a.geometry  # type: ignore[attr-defined]
            bg = obj_b.geometry  # type: ignore[attr-defined]
            min_area = min(ag.w * ag.h, bg.w * bg.h)
            if min_area > 0 and (area / min_area) > 0.12:
                audit.issues.append(
                    GeometryIssue(
                        kind="overlap",
                        object_id=id_a,
                        other_id=id_b,
                        message=f"{id_a} overlaps {id_b} ({area / min_area * 100:.0f}% of smaller box)",
                    )
                )

    return audit
