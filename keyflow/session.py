"""Iterative slide/deck design session for creating, composing, and modifying objects."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from keyflow.compiler import CompileResult, compile_deck
from keyflow.renderer import is_render_enabled, render_keyx_to_pngs
from keyflow.spec import (
    DeckSpec,
    FillValue,
    GroupSpec,
    SizeSpec,
    SlideSpec,
    VisualObjectSpec,
)

_OBJECT_ADAPTER = TypeAdapter(VisualObjectSpec)


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = _deep_merge(merged[k], v)
        else:
            merged[k] = v
    return merged


def _ensure_id(obj: VisualObjectSpec) -> VisualObjectSpec:
    if obj.id is None:
        obj = obj.model_copy(update={"id": f"{obj.type}_{uuid.uuid4().hex[:8]}"})
    if isinstance(obj, GroupSpec):
        obj = obj.model_copy(
            update={"children": [_ensure_id(c) for c in obj.children]}
        )
    return obj


def _find_and_update(
    objects: list[VisualObjectSpec],
    object_id: str,
    patch: dict[str, Any],
) -> tuple[list[VisualObjectSpec], bool]:
    updated: list[VisualObjectSpec] = []
    found = False
    for obj in objects:
        if obj.id == object_id:
            raw = obj.model_dump(mode="json")
            merged = _deep_merge(raw, patch)
            merged["id"] = object_id
            updated.append(_ensure_id(_OBJECT_ADAPTER.validate_python(merged)))
            found = True
        elif isinstance(obj, GroupSpec):
            new_children, child_found = _find_and_update(obj.children, object_id, patch)
            if child_found:
                found = True
                updated.append(obj.model_copy(update={"children": new_children}))
            else:
                updated.append(obj)
        else:
            updated.append(obj)
    return updated, found


def _find_and_remove(
    objects: list[VisualObjectSpec],
    object_id: str,
) -> tuple[list[VisualObjectSpec], bool]:
    remaining: list[VisualObjectSpec] = []
    found = False
    for obj in objects:
        if obj.id == object_id:
            found = True
            continue
        if isinstance(obj, GroupSpec):
            new_children, child_found = _find_and_remove(obj.children, object_id)
            if child_found:
                found = True
                remaining.append(obj.model_copy(update={"children": new_children}))
            else:
                remaining.append(obj)
        else:
            remaining.append(obj)
    return remaining, found


def _add_to_group(
    objects: list[VisualObjectSpec],
    group_id: str,
    new_obj: VisualObjectSpec,
) -> tuple[list[VisualObjectSpec], bool]:
    updated: list[VisualObjectSpec] = []
    found = False
    for obj in objects:
        if obj.id == group_id and isinstance(obj, GroupSpec):
            updated.append(obj.model_copy(update={"children": [*obj.children, new_obj]}))
            found = True
        elif isinstance(obj, GroupSpec):
            new_children, child_found = _add_to_group(obj.children, group_id, new_obj)
            if child_found:
                found = True
                updated.append(obj.model_copy(update={"children": new_children}))
            else:
                updated.append(obj)
        else:
            updated.append(obj)
    return updated, found


def _summarize_object(obj: VisualObjectSpec, depth: int = 0) -> dict[str, Any]:
    info: dict[str, Any] = {
        "id": obj.id,
        "type": obj.type,
        "depth": depth,
    }
    if hasattr(obj, "geometry"):
        g = obj.geometry
        info["geometry"] = {"x": g.x, "y": g.y, "w": g.w, "h": g.h, "angle": g.angle}
    if obj.type == "textbox":
        raw = obj.text.string or " ".join(
            r.text for p in (obj.text.paragraphs or []) for r in p.runs
        )
        info["text_preview"] = raw[:80]
    elif obj.type == "shape":
        info["shape"] = obj.shape
    elif obj.type == "chart":
        info["chart_type"] = obj.chart_type
    elif obj.type == "connection":
        info["from_point"] = obj.from_point
        info["to_point"] = obj.to_point
    elif obj.type == "group":
        info["title"] = obj.title
        info["children"] = [_summarize_object(c, depth + 1) for c in obj.children]
    return info


class DesignSession:
    """Stateful slide/deck design session supporting incremental object authoring."""

    def __init__(self, deck: DeckSpec) -> None:
        self.deck = deck

    @classmethod
    def create(
        cls,
        *,
        width: float = 1920.0,
        height: float = 1080.0,
        background: FillValue = "#0F172A",
        note: str | None = None,
        theme: str = "White",
    ) -> "DesignSession":
        deck = DeckSpec(
            slide_size=SizeSpec(w=width, h=height),
            theme=theme,
            slides=[SlideSpec(background=background, objects=[], note=note)],
        )
        return cls(deck)

    @classmethod
    def from_file(cls, path: str | Path) -> "DesignSession":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if "slides" in data:
            deck = DeckSpec.model_validate(data)
        else:
            deck = DeckSpec(slides=[SlideSpec.model_validate(data)])
        return cls(deck)

    def save_spec(self, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(self.deck.model_dump_json(indent=2), encoding="utf-8")
        return out.resolve()

    def _slide(self, slide_index: int) -> SlideSpec:
        if slide_index < 0 or slide_index >= len(self.deck.slides):
            raise IndexError(
                f"slide_index {slide_index} out of range (0..{len(self.deck.slides) - 1})"
            )
        return self.deck.slides[slide_index]

    def add_slide(
        self,
        *,
        background: FillValue = "#0F172A",
        note: str | None = None,
        index: int | None = None,
    ) -> int:
        slide = SlideSpec(background=background, objects=[], note=note)
        if index is None:
            self.deck.slides.append(slide)
            return len(self.deck.slides) - 1
        self.deck.slides.insert(index, slide)
        return index

    def set_background(self, slide_index: int, background: FillValue) -> None:
        self._slide(slide_index).background = background

    def set_note(self, slide_index: int, note: str | None) -> None:
        self._slide(slide_index).note = note

    def add_object(
        self,
        slide_index: int,
        obj: VisualObjectSpec | dict[str, Any],
        *,
        index: int | None = None,
        group_id: str | None = None,
    ) -> str:
        slide = self._slide(slide_index)
        parsed = _ensure_id(
            obj if isinstance(obj, BaseModel) else _OBJECT_ADAPTER.validate_python(obj)
        )
        if group_id is not None:
            new_objs, found = _add_to_group(slide.objects, group_id, parsed)
            if not found:
                raise KeyError(f"Group '{group_id}' not found on slide {slide_index}")
            slide.objects = new_objs
        elif index is None:
            slide.objects.append(parsed)
        else:
            slide.objects.insert(index, parsed)
        assert parsed.id is not None
        return parsed.id

    def update_object(
        self,
        slide_index: int,
        object_id: str,
        patch: dict[str, Any],
    ) -> None:
        slide = self._slide(slide_index)
        new_objs, found = _find_and_update(slide.objects, object_id, patch)
        if not found:
            raise KeyError(f"Object '{object_id}' not found on slide {slide_index}")
        slide.objects = new_objs

    def remove_object(self, slide_index: int, object_id: str) -> None:
        slide = self._slide(slide_index)
        new_objs, found = _find_and_remove(slide.objects, object_id)
        if not found:
            raise KeyError(f"Object '{object_id}' not found on slide {slide_index}")
        slide.objects = new_objs

    def reorder_object(
        self,
        slide_index: int,
        object_id: str,
        position: str | int,
    ) -> None:
        slide = self._slide(slide_index)
        idx = next((i for i, o in enumerate(slide.objects) if o.id == object_id), None)
        if idx is None:
            raise KeyError(f"Top-level object '{object_id}' not found on slide {slide_index}")
        obj = slide.objects.pop(idx)
        if isinstance(position, int):
            target = max(0, min(len(slide.objects), position))
        elif position == "front":
            target = len(slide.objects)
        elif position == "back":
            target = 0
        elif position == "forward":
            target = min(len(slide.objects), idx + 1)
        elif position == "backward":
            target = max(0, idx - 1)
        else:
            slide.objects.insert(idx, obj)
            raise ValueError(f"Invalid position: {position!r}")
        slide.objects.insert(target, obj)

    def group_objects(
        self,
        slide_index: int,
        object_ids: list[str],
        *,
        group_id: str | None = None,
        title: str | None = None,
    ) -> str:
        slide = self._slide(slide_index)
        id_set = set(object_ids)
        children: list[VisualObjectSpec] = []
        remaining: list[VisualObjectSpec] = []
        insert_at: int | None = None
        for i, obj in enumerate(slide.objects):
            if obj.id in id_set:
                if insert_at is None:
                    insert_at = i
                children.append(obj)
            else:
                remaining.append(obj)
        if len(children) != len(object_ids):
            found_ids = {c.id for c in children}
            missing = [oid for oid in object_ids if oid not in found_ids]
            raise KeyError(f"Objects not found at top level of slide {slide_index}: {missing}")
        gid = group_id or f"group_{uuid.uuid4().hex[:8]}"
        group = GroupSpec(id=gid, title=title, children=children)
        assert insert_at is not None
        remaining.insert(min(insert_at, len(remaining)), group)
        slide.objects = remaining
        return gid

    def ungroup_object(self, slide_index: int, group_id: str) -> list[str]:
        slide = self._slide(slide_index)
        idx = next(
            (i for i, o in enumerate(slide.objects) if o.id == group_id and isinstance(o, GroupSpec)),
            None,
        )
        if idx is None:
            raise KeyError(f"Group '{group_id}' not found at top level of slide {slide_index}")
        group = slide.objects.pop(idx)
        assert isinstance(group, GroupSpec)
        for offset, child in enumerate(group.children):
            slide.objects.insert(idx + offset, child)
        return [c.id for c in group.children if c.id is not None]

    def inspect(self, slide_index: int | None = None) -> dict[str, Any]:
        slides_to_show = (
            [(slide_index, self._slide(slide_index))]
            if slide_index is not None
            else list(enumerate(self.deck.slides))
        )
        return {
            "slide_size": {"w": self.deck.slide_size.w, "h": self.deck.slide_size.h},
            "slide_count": len(self.deck.slides),
            "slides": [
                {
                    "index": idx,
                    "object_count": len(s.objects),
                    "note": s.note,
                    "objects": [_summarize_object(o) for o in s.objects],
                }
                for idx, s in slides_to_show
            ],
        }

    def compile(self, output_path: str | Path) -> CompileResult:
        return compile_deck(self.deck, output_path)

    def compile_and_render(
        self,
        output_path: str | Path,
        png_dir: str | Path | None = None,
        *,
        render_png: bool | None = None,
        strict_render: bool = False,
    ) -> tuple[CompileResult, list[Path]]:
        res = self.compile(output_path)
        if not is_render_enabled(render_png):
            return res, []
        target_dir = Path(png_dir) if png_dir is not None else res.keyx_path.with_name(f"{res.keyx_path.stem}_previews")
        try:
            pngs = render_keyx_to_pngs(res.keyx_path, target_dir)
        except RuntimeError:
            if strict_render:
                raise
            return res, []
        return res, pngs


# BaseModel imported for isinstance check in add_object
from pydantic import BaseModel  # noqa: E402
