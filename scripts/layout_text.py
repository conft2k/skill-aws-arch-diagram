"""Scoped typography for a complete layout/check pass.

The engine and checker share layout_const. Scaling those metrics together lets the
existing solvers reserve room for larger glyphs, including note wrapping and badges.
The scope restores every value, even after a rejected solve. CLI/corpus renders are
serialized within a process; corpus parallelism uses separate worker processes.
"""
from __future__ import annotations

import math
import sys
import threading
from contextlib import contextmanager
from dataclasses import replace
from functools import wraps

import layout_const as K

_LOCK = threading.RLock()
_KEY = (1.0, ())
# Scale glyph offsets and their containing header/note slots, retaining icon sizes,
# canvas margins, routing clearances and media thresholds.
_LENGTHS = (
    "NODE_LABEL_DY", "SUB_PITCH", "TEXT_TITLE_SIZE", "TITLE_DY", "CLOUD_TITLE_DY", "CIDR_DY",
    "BADGE_R", "BADGE_DY", "BADGE_TEXT_DY", "VBADGE_DX",
    "PANEL_FIRST", "PANEL_PITCH", "PANEL_LAST", "PANEL_BADGE_CX", "PANEL_HOP_X",
    "PANE_FIRST_CY", "PANE_BADGE_CX", "PANE_HOP_X", "PANE_DESC_DY", "PANE_DESC_PITCH",
    "PANE_WRAP_INSET", "PANE_NEXT_HOP", "PANE_END",
    "LINES_BADGE_DX", "LINES_TEXT_DX", "LINES_FIRST_CY", "LINES_TEXT_ONLY_DY",
    "LINES_ROW_PITCH", "LINES_TEXT_PITCH", "LINES_END",
)
_BASE = {name: getattr(K, name) for name in _LENGTHS}
_STYLES = {name: value for name, value in vars(K).items() if isinstance(value, K.TextStyle)}
_GROUPS = K.GROUP_STYLES
_MODES = K.MODES
_LABEL_SIZE = K.label_size
_CIDR_BOX, _CIDR_ICON = K.CIDR_TOP_BOX, K.CIDR_TOP_ICON
_CHECKERS = []


def register_checker(module):
    """The checker may run as check_layout or as __main__; both cache header metrics."""
    if module not in _CHECKERS:
        _CHECKERS.append(module)


def rounded(value: float, factor: float) -> int:
    return max(1, math.floor(value * factor + 0.5))


def font_size(value: float, factor: float, steps=()) -> int:
    """Fixed scaling rounds once; automatic passes round the previous integer size."""
    if not steps:
        return rounded(value, factor)
    for step in steps:
        value = rounded(value, step)
    return value


def svg_steps(root):
    try:
        steps = tuple(float(v) for v in root.get("data-text-steps", "").split(",") if v)
        return steps if all(math.isfinite(v) and v > 0 for v in steps) else ()
    except ValueError:
        return ()


def svg_factor(root) -> float:
    """Invalid/untrusted SVG metadata never controls the checker's metrics."""
    try:
        value = float(root.get("data-text-scale", "1"))
        return value if math.isfinite(value) and value > 0 else 1.0
    except (ValueError, TypeError):
        return 1.0


@contextmanager
def font_context(factor: float, steps=()):
    """Use one font multiplier consistently through solve, draw and check."""
    global _KEY
    with _LOCK:
        key = (factor, tuple(steps))
        if key == _KEY:
            yield
            return
        changed = []

        def set_(obj, name, value):
            changed.append((obj, name, getattr(obj, name)))
            setattr(obj, name, value)

        previous = _KEY
        try:
            _KEY = key
            for name, value in _BASE.items():
                set_(K, name, rounded(value, factor))
            for name, value in _STYLES.items():
                set_(K, name, replace(value, size=font_size(value.size, factor, steps)))
            set_(K, "TEXT_TITLE_SIZE", font_size(_BASE["TEXT_TITLE_SIZE"], factor, steps))
            # Keep the badge/label's gap from its connector fixed as glyphs grow.
            set_(K, "BADGE_DY", K.BADGE_R + (_BASE["BADGE_DY"] - _BASE["BADGE_R"]))
            set_(K, "VBADGE_DX", K.BADGE_R + (_BASE["VBADGE_DX"] - _BASE["BADGE_R"]))
            set_(K, "label_size", lambda size=K.S_DEFAULT: font_size(_LABEL_SIZE(size), factor, steps))
            set_(K, "GROUP_STYLES", {
                name: replace(st, top_box=tuple(rounded(v, factor) for v in st.top_box),
                              top_icon=tuple(rounded(v, factor) for v in st.top_icon))
                for name, st in _GROUPS.items()
            })
            set_(K, "CIDR_TOP_BOX", tuple(rounded(v, factor) for v in _CIDR_BOX))
            set_(K, "CIDR_TOP_ICON", tuple(rounded(v, factor) for v in _CIDR_ICON))
            set_(K, "MODES", {
                name: replace(mode, mask_extra=rounded(mode.mask_extra, factor),
                              label_bottom=rounded(mode.label_bottom, factor),
                              label_above=mode.label_above + K.GLYPH_DESCENT * (
                                  K.TEXT_PROTO.size - _STYLES["TEXT_PROTO"].size),
                              label_below=mode.label_below + K.GLYPH_ASCENT * (
                                  K.TEXT_PROTO.size - _STYLES["TEXT_PROTO"].size))
                for name, mode in _MODES.items()
            })
            note = sys.modules.get("layout_note")
            if note is not None:
                set_(note, "SIZE", K.TEXT_NOTE.size)
                set_(note.wrap, "__defaults__", (K.TEXT_NOTE.size,))
            for checker in _CHECKERS:
                # check_layout caches these values at import time.
                for name in ("NODE_LABEL_DY", "SUB_PITCH"):
                    set_(checker, name, getattr(K, name))
                for name, value in {
                    "TITLE_SIZES": (K.TEXT_TITLE_SIZE, K.TEXT_CLOUD_TITLE.size),
                    "TITLE_ROW": K.CLOUD_TITLE_DY + 4,
                    "CIDR_PITCH": K.CIDR_DY - K.TITLE_DY,
                    "NESTED_TOP": min(v for st in K.GROUP_STYLES.values() for v in st.top_box),
                    "NESTED_TOP_CIDR": max(K.CIDR_TOP_BOX),
                    "STACK_REACH": K.NODE_LABEL_DY + K.SUB_PITCH + 10,
                    "STACK_STEP": K.SUB_PITCH + 4,
                }.items():
                    set_(checker, name, value)
            yield
        finally:
            for obj, name, value in reversed(changed):
                setattr(obj, name, value)
            _KEY = previous


def scaled_svg(function):
    """Wrap a checker entry point whose first argument is an SVG root."""
    @wraps(function)
    def wrapped(root, *args, **kwargs):
        with font_context(svg_factor(root), svg_steps(root)):
            return function(root, *args, **kwargs)
    return wrapped


def scaled_spec(function):
    """Wrap a rule checker whose first argument is an expanded spec."""
    @wraps(function)
    def wrapped(spec, *args, **kwargs):
        with font_context(getattr(spec, "font_factor", 1.0), getattr(spec, "font_steps", ())):
            return function(spec, *args, **kwargs)
    return wrapped


def scaled_advisor(cls):
    """Keep direct Advisor calls and CLI fixes in the SVG's typography scope."""
    for name, function in list(vars(cls).items()):
        if isinstance(function, (staticmethod, classmethod)) or not callable(function):
            continue
        @wraps(function)
        def wrapped(self, *args, _function=function, _name=name, **kwargs):
            root = (args[0] if args else kwargs["root"]) if _name == "__init__" else self.root
            with font_context(svg_factor(root), svg_steps(root)):
                return _function(self, *args, **kwargs)
        setattr(cls, name, wrapped)
    return cls
