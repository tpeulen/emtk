"""One font configuration for every piece of text emtk draws.

Why this exists
---------------
The type scale (:mod:`emtk.type_scale`) fixed *how big* each kind of text is
relative to the body. What it could not say is *which face* a role is set in,
or anything about how text is put on screen: the interface face was the baked
atlas, the editor drew in whatever the painter happened to hold, the
documentation's prose face was a constant, and nothing could magnify the whole
interface for a user who sits far from the screen. Each of those was a choice
made where the text was drawn, so an application had no single place to offer
them as settings.

This module is that place. A :class:`FontConfig` holds, per **role**, a family
(with a fallback chain), a size and a weight, plus the settings that apply to
all text:

``zoom``
    Interface magnification. Every host built on :class:`emtk.app.ControlSurface`
    lays the interface out ``zoom`` times smaller and draws it ``zoom`` times
    larger, so *everything* -- text, paddings, icons, plots -- grows together,
    the way a browser's zoom does. Pointer input is mapped back.
``oversample``
    Glyph raster scale for real (system) fonts. ``1`` rasterises one texel per
    device pixel and places glyphs on the device grid (sharpest); ``2`` draws
    twice-resolution glyphs scaled down (smoother, softer on a 1x display).
    The baked interface face is a fixed bitmap and is not affected.
``antialias``
    Grey-scale anti-aliasing of real-font glyphs; off draws bi-level glyphs.
    The rasteriser (FreeType through Pillow) offers no hinting control, so
    there is no hinting setting.

Roles
-----
========  ===================================================================
role      what is set in it
========  ===================================================================
ui        the interface chrome: buttons, labels, tables, menus, tooltips
code      editors, consoles, code blocks (must be monospaced: the editor's
          columns assume it)
prose     documentation and help running text
heading   documentation and help headings (sized by ``heading_step``)
math      formulas (``auto`` picks the first installed STIX/Times face)
caption   figure captions and footnotes
========  ===================================================================

A size of ``0`` means *follow*: ``ui`` follows :data:`emtk.font.DEFAULT_FONT_PT`
(or ``$EMTK_FONT_PT``); ``code``, ``prose`` and ``math`` follow the interface
size; ``heading`` and ``caption`` follow ``prose`` by their steps of the scale.

Families
--------
A family is a name (``"Menlo"``), a generic (``"monospace"`` -- the baked
interface face --, ``"prose"``, ``"sans-serif"``, ``"serif"``) or a
comma-separated chain (``"Inter, Verdana, prose"``). The first available entry
is the face; the others are tried, in order, for any character the face does
not have, before the system's coverage faces (:data:`emtk.dynamic_font.FONT_CANDIDATES`)
-- so a role's fallbacks are its own. :attr:`FontConfig.fallbacks` is appended
to every role's chain.

Applying
--------
:func:`apply` (or :func:`update`) takes effect on the next frame: it clears the
glyph, measurement and formula caches and bumps :func:`generation`, which every
host compares to rebuild its painter. Nothing needs a restart.

Persisting
----------
:meth:`FontConfig.to_dict` / :meth:`FontConfig.from_dict` round-trip a plain dict
of strings, numbers and booleans, ready for YAML or JSON. Unknown keys are
ignored and out-of-range values clamped, so a hand-edited settings file can
never stop the interface from starting.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, fields, replace
from typing import Any

__all__ = [
    "ROLES",
    "RoleFont",
    "FontConfig",
    "config",
    "apply",
    "update",
    "reset",
    "generation",
    "zoom",
    "oversample",
    "antialias",
    "role_family",
    "role_size_pt",
    "role_font",
    "family_chain",
    "system_families",
    "measure",
    "invalidate_caches",
    "MIN_ZOOM",
    "MAX_ZOOM",
]

#: The roles a configuration names, in the order a settings page lists them.
ROLES: tuple[str, ...] = ("ui", "code", "prose", "heading", "math", "caption")

#: Interface magnification bounds.
MIN_ZOOM = 0.5
MAX_ZOOM = 3.0
#: Glyph oversampling bounds.
MIN_OVERSAMPLE = 1.0
MAX_OVERSAMPLE = 4.0
#: Heading step bounds (1.0 = headings at the body size).
MIN_STEP = 1.0
MAX_STEP = 1.6
#: Size bounds of a role, in emtk points (0 = follow).
MIN_PT = 4.0
MAX_PT = 48.0


@dataclass(frozen=True)
class RoleFont:
    """The face, size and weight of one role.

    Parameters
    ----------
    family : str
        A family, a generic, or a comma-separated fallback chain.
    size : float
        Points; ``0`` follows (see the module docstring).
    bold : bool
        Weight: bold or regular.
    """

    family: str = "monospace"
    size: float = 0.0
    bold: bool = False

    def to_dict(self) -> dict:
        """``{"family", "size", "bold"}``."""
        return {
            "family": self.family,
            "size": float(self.size),
            "bold": bool(self.bold),
        }

    @classmethod
    def from_dict(cls, data: Any, default: RoleFont) -> RoleFont:
        """A role from *data*, every bad or missing field taken from *default*."""
        if isinstance(data, str):
            data = {"family": data}
        if not isinstance(data, dict):
            return default
        family = data.get("family", default.family)
        if not isinstance(family, str) or not family.strip():
            family = default.family
        size = _number(data.get("size", default.size), default.size)
        size = 0.0 if size <= 0 else min(MAX_PT, max(MIN_PT, size))
        bold = data.get("bold", default.bold)
        return cls(
            family.strip(), size, bold if isinstance(bold, bool) else default.bold
        )


def _number(value: Any, default: float) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return float(default)
    return value if math.isfinite(value) else float(default)


def _default_ui() -> RoleFont:
    return RoleFont("monospace", 0.0)


@dataclass(frozen=True)
class FontConfig:
    """Every font setting, as one value. See the module docstring."""

    ui: RoleFont = field(default_factory=_default_ui)
    code: RoleFont = field(default_factory=lambda: RoleFont("monospace", 0.0))
    prose: RoleFont = field(default_factory=lambda: RoleFont("prose", 0.0))
    heading: RoleFont = field(default_factory=lambda: RoleFont("prose", 0.0, True))
    math: RoleFont = field(default_factory=lambda: RoleFont("auto", 0.0))
    caption: RoleFont = field(default_factory=lambda: RoleFont("prose", 0.0))
    #: Ratio between neighbouring heading sizes (h4 = prose x step, h1 = x step^4).
    heading_step: float = 1.125
    zoom: float = 1.0
    oversample: float = 1.0
    antialias: bool = True
    #: Families tried for a missing character after a role's own chain.
    fallbacks: tuple[str, ...] = ()

    def role(self, name: str) -> RoleFont:
        """The :class:`RoleFont` of role *name*."""
        if name not in ROLES:
            raise ValueError(f"unknown font role {name!r}; one of {ROLES}")
        return getattr(self, name)

    def to_dict(self) -> dict:
        """A plain dict (YAML/JSON-ready) that :meth:`from_dict` reads back."""
        out: dict[str, Any] = {name: self.role(name).to_dict() for name in ROLES}
        out.update(
            heading_step=float(self.heading_step),
            zoom=float(self.zoom),
            oversample=float(self.oversample),
            antialias=bool(self.antialias),
            fallbacks=list(self.fallbacks),
        )
        return out

    @classmethod
    def from_dict(cls, data: Any) -> FontConfig:
        """A configuration from a (possibly partial or hand-edited) dict."""
        base = cls()
        if not isinstance(data, dict):
            return base
        roles = {
            name: RoleFont.from_dict(data.get(name), base.role(name)) for name in ROLES
        }
        raw = data.get("fallbacks", ())
        if isinstance(raw, str):
            raw = [part for part in raw.split(",")]
        fallbacks = tuple(
            str(f).strip()
            for f in (raw if isinstance(raw, (list, tuple)) else ())
            if str(f).strip()
        )
        antialias = data.get("antialias", base.antialias)
        return cls(
            **roles,
            heading_step=_clamp(
                _number(data.get("heading_step"), base.heading_step), MIN_STEP, MAX_STEP
            ),
            zoom=_clamp(_number(data.get("zoom"), base.zoom), MIN_ZOOM, MAX_ZOOM),
            oversample=_clamp(
                _number(data.get("oversample"), base.oversample),
                MIN_OVERSAMPLE,
                MAX_OVERSAMPLE,
            ),
            antialias=antialias if isinstance(antialias, bool) else base.antialias,
            fallbacks=fallbacks,
        )


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, float(value)))


_config = FontConfig()
_generation = 0


def config() -> FontConfig:
    """The configuration in force; ``ui.size`` is always the live interface size."""
    from .type_scale import ui_font_pt  # noqa: PLC0415

    return replace(_config, ui=replace(_config.ui, size=float(ui_font_pt())))


def generation() -> int:
    """A counter bumped by every :func:`apply` that changed how text is drawn.

    Hosts compare it with the value their painter was built at.
    """
    return _generation


def apply(value: FontConfig | dict | None = None) -> FontConfig:
    """Make *value* the configuration in force (``None``: the defaults).

    Clears the glyph, layout and formula caches and bumps :func:`generation`
    when anything that changes drawn text changed, so the next frame draws with
    it. Returns the configuration in force (validated).
    """
    global _config, _generation
    from .type_scale import set_ui_font_pt  # noqa: PLC0415

    if value is None:
        cfg = FontConfig()
    elif isinstance(value, FontConfig):
        cfg = FontConfig.from_dict(value.to_dict())
    else:
        cfg = FontConfig.from_dict(value)
    before = config()
    _config = cfg
    from .font import DEFAULT_FONT_PT  # noqa: PLC0415

    set_ui_font_pt(cfg.ui.size if cfg.ui.size > 0 else _env_or_default(DEFAULT_FONT_PT))
    after = config()
    if after != before:
        invalidate_caches()
        _generation += 1
    return after


def _env_or_default(default: float) -> float:
    import os  # noqa: PLC0415

    from .type_scale import ENV  # noqa: PLC0415

    try:
        return float(os.environ.get(ENV, "") or default)
    except ValueError:
        return float(default)


def update(**changes: Any) -> FontConfig:
    """Change some settings and :func:`apply`.

    A role takes a dict of the fields to change (``code={"family": "Menlo"}``)
    or a family string; anything else is a top-level setting (``zoom=1.25``).
    """
    data = config().to_dict()
    for key, value in changes.items():
        if key in ROLES:
            if isinstance(value, str):
                value = {"family": value}
            if isinstance(value, RoleFont):
                value = value.to_dict()
            data[key] = {**data[key], **dict(value)}
        elif key in {f.name for f in fields(FontConfig)}:
            data[key] = list(value) if isinstance(value, tuple) else value
        else:
            raise ValueError(f"unknown font setting {key!r}")
    return apply(data)


def reset() -> FontConfig:
    """Back to the defaults (today's look)."""
    return apply(None)


def zoom() -> float:
    """Interface magnification in force."""
    return float(_config.zoom)


def oversample() -> float:
    """Glyph raster scale for real fonts."""
    return float(_config.oversample)


def antialias() -> bool:
    """Whether real-font glyphs are anti-aliased."""
    return bool(_config.antialias)


def heading_step() -> float:
    """Ratio between neighbouring heading sizes."""
    return float(_config.heading_step)


def role_family(role: str) -> str:
    """The family string of *role* (``"auto"`` for an automatic math face)."""
    return _config.role(role).family


def role_size_pt(role: str) -> float:
    """The size *role* is drawn at, in emtk points, with ``0`` resolved.

    ``heading`` and ``caption`` resolve to the *base* their scale steps start
    from (the prose size); :func:`emtk.type_scale.text_font` applies the steps.
    """
    from .type_scale import ui_font_pt  # noqa: PLC0415

    cfg = _config.role(role)
    if role == "ui":
        return float(ui_font_pt())
    if cfg.size > 0:
        return float(cfg.size)
    if role in {"heading", "caption"}:
        return role_size_pt("prose")
    return float(ui_font_pt())


def role_font(role: str) -> dict:
    """The font dict (for ``im.push_font`` / ``painter.set_font``) of *role*.

    The size is in the painter's spec units (relative to the baked interface
    size, which the painter scales by ``ui_font_pt / baked``), so drawing with
    it yields :func:`role_size_pt` points.
    """
    from .type_scale import _baked_pt, ui_font_pt  # noqa: PLC0415

    cfg = _config.role(role)
    family = cfg.family if role != "math" or cfg.family != "auto" else "serif"
    return {
        "family": family,
        "size": _baked_pt() * role_size_pt(role) / float(ui_font_pt()),
        "bold": bool(cfg.bold),
    }


def family_chain(family: str) -> tuple[str, ...]:
    """*family* split into its comma-separated chain, empty entries dropped."""
    return tuple(part.strip() for part in str(family).split(",") if part.strip())


def system_families(monospace: bool = False) -> tuple[str, ...]:
    """Installed families a picker may offer, plus the generics.

    Parameters
    ----------
    monospace : bool
        Only fixed-advance families (and ``monospace``): for the ``code`` role,
        whose editor lays columns out at a fixed advance.

    Returns
    -------
    tuple of str
        ``monospace`` first, then (unless *monospace*) ``prose``,
        ``sans-serif`` and ``serif``, then every installed family, sorted.
        Discovery scans the platform font folders once (macOS, Linux and
        Windows), caches the result per file, and costs nothing afterwards.
    """
    from .font_render import available_fonts  # noqa: PLC0415

    found = available_fonts(monospaced=monospace)
    generics = (
        ("monospace",) if monospace else ("monospace", "prose", "sans-serif", "serif")
    )
    return generics + tuple(name for name in found if name not in generics)


def measure(role: str, text: str) -> float:
    """Width of *text* in *role*'s font, in logical pixels at zoom 1.

    What a layout at the current settings measures: the baked face for
    ``monospace``, the real face (with its fallback chain) otherwise.
    """
    from .font import load_atlas  # noqa: PLC0415
    from .font_render import font_spec, text_width  # noqa: PLC0415
    from .type_scale import _baked_pt, ui_font_pt  # noqa: PLC0415

    spec_dict = role_font(role)
    painter_scale = float(ui_font_pt()) / _baked_pt()
    spec = font_spec(spec_dict)
    if spec.family == "monospace":
        atlas = load_atlas()
        return atlas.advance(text) * painter_scale * spec.size / atlas.font_pt
    return text_width(spec, text, painter_scale)


def invalidate_caches() -> None:
    """Drop every cached glyph, layout and formula, so the next frame re-rasterises."""
    from . import font_render, tex  # noqa: PLC0415

    for name in (
        "_face",
        "_layout_metrics",
        "_face_for",
        "_runs",
        "_layout_width",
        "text_width",
        "_glyph",
        "_positions",
        "_family_face",
        "_resolve_family",
    ):
        cached = getattr(font_render, name, None)
        clear = getattr(cached, "cache_clear", None)
        if clear is not None:
            clear()
    for name in ("_families", "_bold_family"):
        clear = getattr(getattr(tex, name, None), "cache_clear", None)
        if clear is not None:
            clear()
    try:
        from .mathtext import _GLOBAL_MATH_CACHE  # noqa: PLC0415

        _GLOBAL_MATH_CACHE.clear()
    except Exception:  # noqa: BLE001 - no formula engine, nothing cached
        pass
