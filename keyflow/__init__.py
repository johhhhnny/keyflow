"""KeyFlow: Cognitive-first progressive Keynote (.keyx) compiler."""

from keyflow.compiler import compile_deck, export_slide_pngs
from keyflow.outline import extract_markdown_outline, extract_outline_from_file
from keyflow.pace import expand_scene_frames, pace_deck
from keyflow.schema import DeckSpec, ValidationResult, parse_deck, validate_deck
from keyflow.themes import THEMES, ThemePreset, get_theme

__version__ = "1.0.0"

__all__ = [
    "__version__",
    "THEMES",
    "ThemePreset",
    "DeckSpec",
    "ValidationResult",
    "compile_deck",
    "expand_scene_frames",
    "export_slide_pngs",
    "extract_markdown_outline",
    "extract_outline_from_file",
    "get_theme",
    "pace_deck",
    "parse_deck",
    "validate_deck",
]
