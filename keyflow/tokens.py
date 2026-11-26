"""Shared design tokens and geometry thresholds for KeyFlow.

Single source of truth consumed by layout, compiler, and audit modules so
readability limits, chart spacing, and default style values never drift apart.
"""

from __future__ import annotations

# Standard Keynote 16:9 slide canvas dimensions (in points).
SLIDE_WIDTH: int = 1920
SLIDE_HEIGHT: int = 1080

# Slide header & safe area margins (in points).
TITLE_MARGIN_X: float = 160.0
SUBTITLE_MARGIN_X: float = 260.0
SAFE_AREA_BOTTOM_MARGIN: float = 72.0
PINNED_FLOW_GAP_BELOW: float = 20.0

# Default style_config values (used when deck/scene style_config omits a field).
DEFAULT_TITLE_MAX_SIZE: float = 58.0
DEFAULT_TITLE_MIN_SIZE: float = 40.0
DEFAULT_SUBTITLE_SIZE: float = 28.0
DEFAULT_CARD_CORNER_PX: float = 15.0
DEFAULT_ARROW_WIDTH: float = 4.5

# Color & contrast tokens.
MUTED_CARD_ALPHA: float = 0.72
MIN_CONTRAST_RATIO: float = 3.0

# Layout & visual audit thresholds.
MIN_READABLE_SCALE: float = 0.72
ANCHOR_JITTER_TOLERANCE_PT: float = 0.5
OVERLAP_TOLERANCE_PT: float = 4.0

# Chart spacing & label thresholds.
CHART_MIN_CATEGORY_WIDTH_PT: float = 56.0
CHART_BAR_SLOT_STEP_PT: float = 44.0
CHART_GROUP_PAD_PT: float = 28.0
CHART_Y_LABEL_MIN_W_PT: float = 56.0
CHART_Y_LABEL_MAX_W_PT: float = 96.0
