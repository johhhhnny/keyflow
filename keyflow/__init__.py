"""KeyFlow: Cognitive-first progressive Keynote (.keyx) compiler."""

from keyflow.audit import AuditFinding, AuditReport, audit_deck, select_review_slides
from keyflow.compiler import compile_deck
from keyflow.exporter import export_slide_pngs
from keyflow.outline import extract_markdown_outline, extract_outline_from_file
from keyflow.pace import expand_scene_frames, pace_deck
from keyflow.schema import DeckSpec, ValidationResult, parse_deck, validate_deck
from keyflow.snippets import instantiate_snippet, list_snippets, load_snippet
from keyflow.themes import THEMES, ThemePreset, get_theme

__version__ = "0.3.0"

__all__ = [
    "__version__",
    "AuditFinding",
    "AuditReport",
    "THEMES",
    "ThemePreset",
    "DeckSpec",
    "ValidationResult",
    "audit_deck",
    "compile_deck",
    "expand_scene_frames",
    "export_slide_pngs",
    "extract_markdown_outline",
    "extract_outline_from_file",
    "get_theme",
    "instantiate_snippet",
    "list_snippets",
    "load_snippet",
    "pace_deck",
    "parse_deck",
    "select_review_slides",
    "validate_deck",
]
