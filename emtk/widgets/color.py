"""The colour family: a swatch, a numeric editor and a saturation/value picker.

What this is a port of
----------------------
The reference implementation's ``ColorEdit``/``ColorPicker``/``ColorButton``
section, translated to this chrome's six painter operations and to its gesture
vocabulary -- a press, a drag, a release, and nothing else. No right-click, no
modifier keys, no context menu, so every option the reference hides behind its
options popup is either a constructor argument or a visible control.

Why the hue *bar* and not the hue *wheel*
-----------------------------------------
The reference offers both, and the wheel is the prettier one. It is also an
annulus of six shaded arcs plus a rotating triangle, and
:class:`~emtk.painter.Painter` has no arc, no circle and no
triangle -- everything it can express is an axis-aligned rectangle. A wheel
approximated out of rectangles is a worse wheel than a correct square, so the
wheel is deliberately **not** ported. What is ported is the reference's own
default, ``PickerHueBar``: a saturation/value square with a hue bar beside it.

The hue-state bug this is written to avoid
------------------------------------------
Hue and saturation are not recoverable from RGB at the edges: every fully
desaturated colour has the same RGB whatever its hue, and black has the same
RGB whatever its saturation. A picker that keeps its colour as RGB and converts
on every event therefore *snaps to red* the moment the user drags into the
white edge or the black bottom of the square -- the classic failure, and the
reason the reference carries ``ColorEditRestoreHS`` and a saved hue in its
context. Here the fix is structural rather than a repair: :class:`ColorState`
holds **H, S, V and the byte triple** side by side, so a drag on the hue bar
writes H and touches nothing else, and a colour handed in as RGB restores the
undefined components from what the widget already had.
"""
from __future__ import annotations

from collections.abc import Sequence

from ..painter import ALIGN_CENTER, ALIGN_LEFT, ALIGN_VCENTER, Colour, Painter
from ..style import BORDER, DIM, FRAME_BG, GOLD, TEXT, clamp, fit_text, hit

__all__ = [
    "rgb_to_hsv",
    "hsv_to_rgb",
    "floats_to_rgba",
    "rgba_to_floats",
    "ColorState",
    "ColorButton",
    "ColorEditRGB",
    "ColorEditRGBA",
    "ColorPicker3",
    "ColorPicker4",
]

#: The three ways the numeric editor can show a colour, in cycling order.
DISPLAY_MODES: tuple[str, ...] = ("RGB", "HSV", "HEX")

#: The two greys of the transparency checkerboard, from the reference's
#: ``RenderColorRectWithAlphaCheckerboard``.
_CHECK_DARK = (128, 128, 128, 255)
_CHECK_LIGHT = (204, 204, 204, 255)

#: The cursor drawn on the saturation/value square and on the bars. The
#: reference draws circles; rectangles are what this painter has, so the SV
#: cursor is a hollow square and a bar cursor is a full-width line, each with a
#: dark ring behind a light core so it stays visible on any colour underneath.
_CURSOR_DARK = (0, 0, 0, 255)
_CURSOR_LIGHT = (255, 255, 255, 255)

#: Gap between the square and the bars, and between a swatch and its fields.
_GAP = 4.0

#: The reference's ``1e-20f`` guard, which is what makes its RGB-to-HSV
#: branchless at chroma zero instead of dividing by it.
_EPS = 1e-20


# --------------------------------------------------------------------------
# Conversions -- ported from the reference's imgui.cpp
# --------------------------------------------------------------------------
def rgb_to_hsv(r: float, g: float, b: float) -> tuple[float, float, float]:
    """Convert RGB floats to HSV floats, the reference's way.

    A literal port of ``ColorConvertRGBtoHSV`` (Foley & van Dam p592, in the
    "fast RGB to HSV" arrangement): two conditional swaps accumulate a
    quadrant constant ``K``, and the chroma divisions are guarded by a tiny
    epsilon rather than by a branch. Ported rather than replaced by
    :func:`colorsys.rgb_to_hsv` so the edge cases match the reference exactly:
    grey and black both come out with ``h = 0`` and ``s = 0`` instead of
    raising or returning something undefined.

    Parameters
    ----------
    r, g, b : float
        The channels, ``0.0-1.0``.

    Returns
    -------
    tuple of float
        ``(h, s, v)``, each ``0.0-1.0``. ``h`` is undefined-but-zero for a
        grey, and ``s`` is undefined-but-zero for black -- which is exactly
        why callers must not round-trip through RGB to keep them.
    """
    k = 0.0
    if g < b:
        g, b = b, g
        k = -1.0
    if r < g:
        r, g = g, r
        k = -2.0 / 6.0 - k
    chroma = r - (g if g < b else b)
    h = abs(k + (g - b) / (6.0 * chroma + _EPS))
    s = chroma / (r + _EPS)
    return (h, s, r)


def hsv_to_rgb(h: float, s: float, v: float) -> tuple[float, float, float]:
    """Convert HSV floats to RGB floats, the reference's way.

    A literal port of ``ColorConvertHSVtoRGB`` (Foley & van Dam p593),
    including its early return for ``s == 0`` -- a grey is ``(v, v, v)``
    whatever the hue says, and the sector arithmetic would otherwise have to
    be trusted to agree.

    Parameters
    ----------
    h : float
        Hue. Taken modulo one, so ``1.0`` is red again.
    s, v : float
        Saturation and value, ``0.0-1.0``.

    Returns
    -------
    tuple of float
        ``(r, g, b)``, each ``0.0-1.0``.
    """
    if s == 0.0:
        return (v, v, v)
    h = (h % 1.0) / (60.0 / 360.0)
    i = int(h)
    f = h - float(i)
    p = v * (1.0 - s)
    q = v * (1.0 - s * f)
    t = v * (1.0 - s * (1.0 - f))
    if i == 0:
        return (v, t, p)
    if i == 1:
        return (q, v, p)
    if i == 2:
        return (p, v, t)
    if i == 3:
        return (p, q, v)
    if i == 4:
        return (t, p, v)
    return (v, p, q)


def floats_to_rgba(values: Sequence[float]) -> tuple[int, int, int, int]:
    """Pack ``0.0-1.0`` floats into the chrome's ``0-255`` int tuple.

    The reference's ``ColorConvertFloat4ToU32`` with its ``IM_F32_TO_INT8_SAT``
    rounding -- saturate, scale, add a half, truncate -- rather than Python's
    banker's rounding, which would put ``0.5/255`` on the other side.

    Parameters
    ----------
    values : sequence of float
        One to four channels. Missing alpha is opaque.

    Returns
    -------
    tuple of int
        ``(r, g, b, a)``, each ``0-255``.
    """
    out = [int(clamp(float(v), 0.0, 1.0) * 255.0 + 0.5) for v in values[:4]]
    while len(out) < 3:
        out.append(0)
    if len(out) < 4:
        out.append(255)
    return (out[0], out[1], out[2], out[3])


def rgba_to_floats(rgba: Colour) -> tuple[float, float, float, float]:
    """Unpack a ``0-255`` int tuple into ``0.0-1.0`` floats.

    The reference's ``ColorConvertU32ToFloat4``.

    Parameters
    ----------
    rgba : Colour
        Three or four channels, ``0-255``. Missing alpha is opaque.

    Returns
    -------
    tuple of float
        ``(r, g, b, a)``, each ``0.0-1.0``.
    """
    c = tuple(float(v) for v in rgba)
    if len(c) < 4:
        c = c + (255.0,) * (4 - len(c))
    return (c[0] / 255.0, c[1] / 255.0, c[2] / 255.0, c[3] / 255.0)


def _opaque(colour: Colour) -> tuple[int, int, int, int]:
    """``colour`` with its alpha forced to 255.

    Parameters
    ----------
    colour : Colour
        Three or four channels.

    Returns
    -------
    tuple of int
        ``(r, g, b, 255)``.
    """
    c = tuple(colour)
    return (int(c[0]), int(c[1]), int(c[2]), 255)


def _strips(size: float) -> int:
    """How many horizontal strips a vertical ramp is drawn as.

    :meth:`~emtk.painter.Painter.gradient_rect` interpolates
    left to right only, so anything that varies *down* the box is a stack of
    strips -- and the stack is what the frame pays for, so it is capped.

    Parameters
    ----------
    size : float
        Height of the ramp, in pixels.

    Returns
    -------
    int
        Strip count, between 8 and 48.
    """
    return int(clamp(round(size), 8.0, 48.0))


def _checkerboard(p: Painter, x: float, y: float, w: float, h: float, step: float) -> None:
    """Paint the transparency checkerboard a translucent colour sits on.

    Parameters
    ----------
    p : Painter
        The surface.
    x, y, w, h : float
        The box.
    step : float
        Cell size, in pixels.
    """
    if w <= 0.0 or h <= 0.0:
        return
    step = max(float(step), 2.0)
    p.push_clip(x, y, w, h)
    p.fill_rect(x, y, w, h, _CHECK_DARK)
    row = 0
    cy = y
    while cy < y + h:
        cx = x + (row % 2) * step
        while cx < x + w:
            p.fill_rect(cx, cy, min(step, x + w - cx), min(step, y + h - cy), _CHECK_LIGHT)
            cx += step * 2.0
        cy += step
        row += 1
    p.pop_clip()


# --------------------------------------------------------------------------
# The state every colour control shares
# --------------------------------------------------------------------------
class ColorState:
    """A colour held as H, S, V *and* bytes at once, so neither is lost.

    The whole point is that the two representations are kept side by side
    rather than derived on demand. Hue is undefined for a grey and saturation
    is undefined for black, so a control that stores only bytes and converts
    per event throws those components away and silently rewrites the user's
    colour the moment a drag reaches an edge of the picker.

    Parameters
    ----------
    rgba : Colour, optional
        The starting colour, ``0-255``. Three channels are taken as opaque.
    """

    def __init__(self, rgba: Colour = (255, 255, 255, 255)) -> None:
        self._h = 0.0
        self._s = 0.0
        self._v = 1.0
        self._rgb: tuple[int, int, int] = (255, 255, 255)
        self._a = 255
        self.set_rgba(rgba)

    # -- reading -------------------------------------------------------- #
    @property
    def rgb(self) -> tuple[int, int, int]:
        """The colour without its alpha, ``0-255``."""
        return self._rgb

    @property
    def rgba(self) -> tuple[int, int, int, int]:
        """The colour with its alpha, ``0-255``."""
        return (self._rgb[0], self._rgb[1], self._rgb[2], self._a)

    @property
    def hsv(self) -> tuple[float, float, float]:
        """The colour as ``(h, s, v)``, each ``0.0-1.0``, edges included."""
        return (self._h, self._s, self._v)

    @property
    def alpha(self) -> int:
        """Opacity, ``0-255``."""
        return self._a

    @property
    def floats(self) -> tuple[float, float, float, float]:
        """The colour as ``(r, g, b, a)`` floats, ``0.0-1.0``."""
        return rgba_to_floats(self.rgba)

    def hex(self, alpha: bool = True) -> str:
        """Render the colour as ``#RRGGBB`` or ``#RRGGBBAA``.

        Parameters
        ----------
        alpha : bool, optional
            Whether to append the alpha byte.

        Returns
        -------
        str
            Upper-case, with the leading hash the reference writes.
        """
        r, g, b, a = self.rgba
        return f"#{r:02X}{g:02X}{b:02X}{a:02X}" if alpha else f"#{r:02X}{g:02X}{b:02X}"

    # -- writing -------------------------------------------------------- #
    def set_rgba(self, rgba: Colour) -> tuple[int, int, int, int]:
        """Set the colour from bytes, restoring what RGB cannot carry.

        This is the reference's ``ColorEditRestoreHS``: when the incoming
        colour is a grey the hue it came in with is meaningless, so the hue
        already held is kept; when it is black the saturation is meaningless
        too. Without this a picker resets to red every time the user reaches
        the white edge or the black bottom of the square.

        Parameters
        ----------
        rgba : Colour
            Three or four channels, ``0-255``. Three is taken as opaque.

        Returns
        -------
        tuple of int
            The stored ``(r, g, b, a)``.
        """
        c = tuple(int(clamp(float(v), 0.0, 255.0)) for v in rgba)
        if len(c) < 4:
            c = c + (255,) * (4 - len(c))
        h, s, v = rgb_to_hsv(c[0] / 255.0, c[1] / 255.0, c[2] / 255.0)
        if s == 0.0 or (h == 0.0 and self._h == 1.0):
            h = self._h
        if v == 0.0:
            s = self._s
        self._h, self._s, self._v = h, s, v
        self._rgb = (c[0], c[1], c[2])
        self._a = c[3]
        return self.rgba

    def set_hsv(
        self,
        h: float | None = None,
        s: float | None = None,
        v: float | None = None,
    ) -> tuple[int, int, int, int]:
        """Set any of hue, saturation and value, leaving the others alone.

        Parameters
        ----------
        h, s, v : float, optional
            The components to change, ``0.0-1.0``, clamped. Omitted ones keep
            the value they had -- which is how the hue bar can move hue
            without disturbing a saturation of zero.

        Returns
        -------
        tuple of int
            The resulting ``(r, g, b, a)``.
        """
        if h is not None:
            self._h = clamp(float(h), 0.0, 1.0)
        if s is not None:
            self._s = clamp(float(s), 0.0, 1.0)
        if v is not None:
            self._v = clamp(float(v), 0.0, 1.0)
        self._rgb = floats_to_rgba(hsv_to_rgb(self._h, self._s, self._v))[:3]
        return self.rgba

    def set_alpha(self, alpha: int) -> int:
        """Set the opacity and nothing else.

        Parameters
        ----------
        alpha : int
            ``0-255``, clamped.

        Returns
        -------
        int
            The stored alpha.
        """
        self._a = int(clamp(float(alpha), 0.0, 255.0))
        return self._a

    def set_hex(self, text: str) -> bool:
        """Set the colour from ``#RRGGBB`` or ``#RRGGBBAA``.

        Parses the way the reference's hex field does: leading hashes and
        blanks skipped, alpha defaulting to opaque when only six digits are
        given.

        Parameters
        ----------
        text : str
            The digits, with or without a leading hash.

        Returns
        -------
        bool
            Whether the text parsed. A rejected string leaves the colour as
            it was rather than raising -- a half-typed field is the normal
            state of a field being typed into.
        """
        digits = str(text).strip().lstrip("#").strip()
        if len(digits) not in (6, 8):
            return False
        try:
            values = [int(digits[i:i + 2], 16) for i in range(0, len(digits), 2)]
        except ValueError:
            return False
        if len(values) == 3:
            values.append(self._a)
        self.set_rgba(tuple(values))
        return True


# --------------------------------------------------------------------------
# ColorButton
# --------------------------------------------------------------------------
class ColorButton:
    """A colour swatch that reports its clicks.

    Alpha is drawn as the **checkerboard** behind a translucent fill, not as
    the reference's split preview. The reference offers both -- a half-and-half
    rectangle (opaque left, checkered right) and the plain checkerboard -- and
    the checkerboard is the one chosen here for two reasons: it shows *how*
    transparent the colour is rather than only that it is, and the split needs
    the swatch to be wide enough for two readable halves, which a swatch drawn
    at row height is not. The checkerboard itself is small
    :meth:`~emtk.painter.Painter.fill_rect` calls, which is all
    the painter has; the reference's diagonal-triangle preview from its older
    versions is not expressible at all, there being no triangle operation.

    Parameters
    ----------
    color : Colour, optional
        The swatch colour, ``0-255``.
    label : str, optional
        Caption drawn after the swatch. The reference shows the description
        only in a tooltip; this chrome has no hover, so a caption that is
        wanted is drawn.
    show_alpha : bool, optional
        Whether the swatch shows its transparency at all. False draws the
        colour opaque, which is the reference's ``AlphaOpaque``.
    """

    def __init__(
        self,
        color: Colour = (255, 255, 255, 255),
        label: str = "",
        show_alpha: bool = True,
    ) -> None:
        self.state = ColorState(color)
        self.label = label
        self.show_alpha = bool(show_alpha)
        self._held = False

    @property
    def color(self) -> tuple[int, int, int, int]:
        """The swatch colour, ``(r, g, b, a)``."""
        return self.state.rgba

    @color.setter
    def color(self, value: Colour) -> None:
        self.state.set_rgba(value)

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the swatch, its transparency backdrop and its caption.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The box. The swatch is the leading square of it.
        """
        size = min(max(h, 1.0), max(w, 1.0))
        rgba = self.color
        if self.show_alpha and rgba[3] < 255:
            _checkerboard(p, x, y, size, size, size / 2.99)
            p.fill_rect(x, y, size, size, rgba)
        else:
            p.fill_rect(x, y, size, size, _opaque(rgba))
        p.stroke_rect(x, y, size, size, GOLD if self._held else BORDER, None)
        room = w - size - _GAP
        if self.label and room > 0.0:
            p.text(x + size + _GAP, y, room, h, ALIGN_VCENTER | ALIGN_LEFT,
                   fit_text(p, self.label, room), TEXT)

    def press(
        self,
        x: float,
        y: float,
        box_x: float,
        box_y: float,
        box_w: float,
        box_h: float,
    ) -> bool:
        """Take a press.

        Parameters
        ----------
        x, y : float
            The point.
        box_x, box_y, box_w, box_h : float
            The box the swatch was drawn into.

        Returns
        -------
        bool
            Whether the press landed on the control -- the reference's
            "returns true when clicked".
        """
        self._held = hit(x, y, box_x, box_y, box_w, box_h)
        return self._held

    def release(self) -> None:
        """Let go of the swatch."""
        self._held = False


# --------------------------------------------------------------------------
# ColorEdit
# --------------------------------------------------------------------------
class ColorEditRGBA:
    """A swatch, a row of numeric fields and a display-mode tag.

    The reference's ``ColorEdit4``. The name differs because
    :mod:`.widgets` already owns ``ColorEdit4`` for a bare swatch with a
    caption, which is a different control with the same reference name; two
    classes called ``ColorEdit4`` in one package is the kind of collision that
    is only ever discovered by importing the wrong one.

    Three display modes, cycled by pressing the tag at the right-hand end:
    ``RGB`` and ``HSV`` show four numeric fields each, ``HEX`` shows the
    ``#RRGGBBAA`` string. The reference puts this choice in a right-click
    options popup; this chrome has no right-click, so the choice is a visible
    control. HSV components are shown ``0-255`` exactly as the reference's
    ``H:%3d`` format does, not in degrees and percent.

    A field is edited by **dragging** it, one unit per pixel, which is the
    reference's ``DragInt`` at its default speed.

    Parameters
    ----------
    label : str, optional
        Caption. Drawn only if there is room left after the controls.
    color : Colour, optional
        The starting colour, ``0-255``.
    mode : str, optional
        Initial display mode, one of :data:`DISPLAY_MODES`.
    alpha : bool, optional
        Whether the alpha component is shown and editable. False is the
        reference's ``ColorEdit3``; :class:`ColorEditRGB` is that spelling.
    """

    def __init__(
        self,
        label: str = "",
        color: Colour = (255, 255, 255, 255),
        mode: str = "RGB",
        alpha: bool = True,
    ) -> None:
        self.label = label
        self.state = ColorState(color)
        self.alpha = bool(alpha)
        self.mode = mode if mode in DISPLAY_MODES else "RGB"
        self.swatch = ColorButton(self.state.rgba, show_alpha=self.alpha)
        self._drag_field: int | None = None
        self._drag_x = 0.0
        self._drag_start = 0
        #: Widths of the caption and the mode tag as the last :meth:`draw`
        #: measured them. Both are sized from the *font*, which :meth:`press`
        #: has no painter to ask, so the drawn widths are remembered rather
        #: than guessed a second time -- two copies of a layout is how a
        #: control ends up responding a control-width from where it painted.
        self._label_w = 0.0
        self._tag_w = 24.0

    # -- the colour ----------------------------------------------------- #
    @property
    def color(self) -> tuple[int, int, int, int]:
        """The edited colour, ``(r, g, b, a)``."""
        return self.state.rgba

    @color.setter
    def color(self, value: Colour) -> None:
        self.state.set_rgba(value)
        self.swatch.color = self.state.rgba

    @property
    def components(self) -> int:
        """How many numeric fields the row has: three, or four with alpha."""
        return 4 if self.alpha else 3

    def cycle_mode(self, step: int = 1) -> str:
        """Move to the next display mode, wrapping.

        Parameters
        ----------
        step : int, optional
            How far to move.

        Returns
        -------
        str
            The new mode.
        """
        index = (DISPLAY_MODES.index(self.mode) + int(step)) % len(DISPLAY_MODES)
        self.mode = DISPLAY_MODES[index]
        return self.mode

    def values(self) -> tuple[int, ...]:
        """Read the numbers the fields currently show, ``0-255``.

        Returns
        -------
        tuple of int
            ``(r, g, b[, a])`` or ``(h, s, v[, a])`` depending on the mode.
            HSV is read from the widget's own state, never re-derived from
            the bytes, so a grey still reports the hue it was set to.
        """
        if self.mode == "HSV":
            h, s, v = self.state.hsv
            out = [int(clamp(c, 0.0, 1.0) * 255.0 + 0.5) for c in (h, s, v)]
        else:
            out = list(self.state.rgb)
        if self.alpha:
            out.append(self.state.alpha)
        return tuple(out)

    def set_value(self, index: int, value: int) -> tuple[int, int, int, int]:
        """Set one numeric field, in whatever the current mode means.

        Parameters
        ----------
        index : int
            Which field, ``0`` upwards. Out-of-range indices are ignored.
        value : int
            The new number, ``0-255``, clamped.

        Returns
        -------
        tuple of int
            The resulting colour.
        """
        if not (0 <= index < self.components):
            return self.color
        value = int(clamp(float(value), 0.0, 255.0))
        if self.alpha and index == 3:
            self.state.set_alpha(value)
        elif self.mode == "HSV":
            fraction = value / 255.0
            self.state.set_hsv(**{("h", "s", "v")[index]: fraction})
        else:
            rgb = list(self.state.rgb)
            rgb[index] = value
            self.state.set_rgba(tuple(rgb) + (self.state.alpha,))
        self.swatch.color = self.state.rgba
        return self.color

    def set_hex(self, text: str) -> bool:
        """Set the colour from a hex string; see :meth:`ColorState.set_hex`.

        Parameters
        ----------
        text : str
            ``#RRGGBB`` or ``#RRGGBBAA``.

        Returns
        -------
        bool
            Whether it parsed.
        """
        changed = self.state.set_hex(text)
        if changed:
            self.swatch.color = self.state.rgba
        return changed

    # -- layout --------------------------------------------------------- #
    def _layout(
        self, p: Painter, x: float, y: float, w: float, h: float
    ) -> tuple[float, float, float, float, float, float]:
        """Where the caption, the swatch, the fields and the mode tag go.

        Parameters
        ----------
        p : Painter
            Used to measure the caption and the mode tag.
        x, y, w, h : float
            The box.

        Returns
        -------
        tuple of float
            ``(label_w, swatch_size, fields_x, fields_w, tag_x, tag_w)``.
        """
        label_w = min(p.text_width(self.label) + _GAP * 2.0, w * 0.3) if self.label else 0.0
        self._label_w = label_w
        swatch = min(max(h, 1.0), max(w - label_w, 1.0))
        tag_w = min(p.text_width("HSV") + 10.0, max(w * 0.25, 1.0))
        self._tag_w = tag_w
        fields_x = x + label_w + swatch + _GAP
        tag_x = x + w - tag_w
        fields_w = max(tag_x - _GAP - fields_x, 1.0)
        return (label_w, swatch, fields_x, fields_w, tag_x, tag_w)

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the swatch, the fields (or the hex string) and the mode tag.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The box.
        """
        label_w, swatch, fields_x, fields_w, tag_x, tag_w = self._layout(p, x, y, w, h)
        if label_w > 0.0:
            p.text(x, y, label_w - _GAP, h, ALIGN_VCENTER | ALIGN_LEFT,
                   fit_text(p, self.label, label_w - _GAP), TEXT)
        self.swatch.color = self.state.rgba
        self.swatch.show_alpha = self.alpha
        self.swatch.draw(p, x + label_w, y, swatch, h)

        p.push_clip(fields_x, y, fields_w, h)
        if self.mode == "HEX":
            p.stroke_rect(fields_x, y, fields_w, h, BORDER, FRAME_BG)
            p.text(fields_x, y, fields_w, h, ALIGN_CENTER,
                   fit_text(p, self.state.hex(self.alpha), fields_w - 6.0), TEXT)
        else:
            count = self.components
            cell = fields_w / count
            prefixes = ("R", "G", "B", "A") if self.mode == "RGB" else ("H", "S", "V", "A")
            hide_prefix = cell <= p.text_width("M:000")
            for index, value in enumerate(self.values()):
                cell_x = fields_x + index * cell
                held = self._drag_field == index
                p.stroke_rect(cell_x, y, cell - 1.0, h, BORDER, FRAME_BG)
                shown = f"{value:d}" if hide_prefix else f"{prefixes[index]}:{value:d}"
                p.text(cell_x, y, cell - 1.0, h, ALIGN_CENTER,
                       fit_text(p, shown, cell - 3.0), GOLD if held else TEXT)
        p.pop_clip()

        p.stroke_rect(tag_x, y, tag_w, h, BORDER, FRAME_BG)
        p.text(tag_x, y, tag_w, h, ALIGN_CENTER, self.mode, DIM)

    # -- input ---------------------------------------------------------- #
    def press(
        self,
        x: float,
        y: float,
        box_x: float,
        box_y: float,
        box_w: float,
        box_h: float,
    ) -> str | None:
        """Take a press: the swatch, a field, the mode tag, or nothing.

        Parameters
        ----------
        x, y : float
            The point.
        box_x, box_y, box_w, box_h : float
            The box the row was drawn into.

        Returns
        -------
        str or None
            ``"swatch"`` -- the host should open a :class:`ColorPicker4`, which
            is what the reference does; ``"mode"`` -- the display mode has just
            been cycled; ``"field"`` -- a numeric field is now being dragged;
            ``"hex"`` -- the hex string was pressed, and the host should route
            typing to :meth:`set_hex`; ``None`` -- the press missed, or the
            caption was pressed, which is not a control.
        """
        self._drag_field = None
        if not hit(x, y, box_x, box_y, box_w, box_h):
            self.swatch.release()
            return None
        label_w = min(self._label_w, box_w * 0.3)
        swatch = min(max(box_h, 1.0), max(box_w - label_w, 1.0))
        if x < box_x + label_w:
            return None
        if x <= box_x + label_w + swatch:
            self.swatch.press(x, y, box_x + label_w, box_y, swatch, box_h)
            return "swatch"
        tag_w = min(self._tag_w, max(box_w * 0.25, 1.0))
        if x >= box_x + box_w - tag_w:
            self.cycle_mode(1)
            return "mode"
        if self.mode == "HEX":
            return "hex"
        fields_x = box_x + label_w + swatch + _GAP
        fields_w = max(box_x + box_w - tag_w - _GAP - fields_x, 1.0)
        index = int((x - fields_x) / max(fields_w / self.components, 1e-6))
        if not (0 <= index < self.components):
            return None
        self._drag_field = index
        self._drag_x = x
        self._drag_start = self.values()[index]
        return "field"

    def drag(
        self,
        x: float,
        y: float,
        box_x: float,
        box_y: float,
        box_w: float,
        box_h: float,
    ) -> bool:
        """Continue a field drag: one unit per pixel, the reference's speed.

        Parameters
        ----------
        x, y : float
            The point.
        box_x, box_y, box_w, box_h : float
            The box, unused -- a drag is not confined to the field it started
            in, which is what makes a one-unit-per-pixel drag usable in a
            twenty-pixel cell.

        Returns
        -------
        bool
            Whether the colour changed.
        """
        if self._drag_field is None:
            return False
        before = self.color
        self.set_value(self._drag_field, self._drag_start + int(round(x - self._drag_x)))
        return self.color != before

    def release(self) -> None:
        """End a field drag."""
        self._drag_field = None
        self.swatch.release()


class ColorEditRGB(ColorEditRGBA):
    """The three-component editor: :class:`ColorEditRGBA` without alpha.

    The reference spells this ``ColorEdit3`` and implements it as ``ColorEdit4``
    with ``NoAlpha``; this is the same arrangement.

    Parameters
    ----------
    label : str, optional
        Caption.
    color : Colour, optional
        Starting colour; any alpha given is kept but neither shown nor edited.
    mode : str, optional
        Initial display mode.
    """

    def __init__(
        self,
        label: str = "",
        color: Colour = (255, 255, 255, 255),
        mode: str = "RGB",
    ) -> None:
        super().__init__(label=label, color=color, mode=mode, alpha=False)


# --------------------------------------------------------------------------
# ColorPicker
# --------------------------------------------------------------------------
class ColorPicker4:
    """The saturation/value square, the hue bar, and an optional alpha bar.

    The reference's ``ColorPicker4`` in its default ``PickerHueBar`` form. Its
    other form, the hue wheel with a rotating saturation/value triangle, is not
    ported: the painter draws axis-aligned rectangles and nothing else, so an
    annulus and a triangle have no expression here that would not be a worse
    version of the square.

    How the square is approximated
    ------------------------------
    The reference paints it as two four-cornered gradients: white to hue
    across, transparent to black down.
    :meth:`~emtk.painter.Painter.gradient_rect` interpolates
    **left to right only**, so the square is instead a stack of horizontal
    strips, each one a single gradient from grey to the hue at that strip's
    value. Along a strip this is exact -- at fixed hue and value, every RGB
    channel is affine in saturation -- so the only approximation is that value
    is quantised down the column, into :func:`_strips` bands. The hue and alpha
    bars are the same stack, one flat strip each.

    Why hue survives the corners
    ----------------------------
    H, S and V live in a :class:`ColorState` rather than being recovered from
    RGB per event. Dragging to the white edge (S = 0) or the black bottom
    (V = 0) makes hue and saturation unrecoverable from the bytes, and a
    picker that recovers them anyway snaps to red -- the bug this class is
    arranged to make impossible. The hue bar writes H alone; the square writes
    S and V alone.

    Parameters
    ----------
    color : Colour, optional
        The starting colour, ``0-255``.
    alpha_bar : bool, optional
        Whether the third bar is drawn. The reference's ``AlphaBar``.
    label : str, optional
        Caption drawn under the square, if there is room.
    """

    def __init__(
        self,
        color: Colour = (255, 0, 0, 255),
        alpha_bar: bool = True,
        label: str = "",
    ) -> None:
        self.state = ColorState(color)
        self.alpha_bar = bool(alpha_bar)
        self.label = label
        self._zone: str | None = None

    # -- the colour ----------------------------------------------------- #
    @property
    def color(self) -> tuple[int, int, int, int]:
        """The picked colour, ``(r, g, b, a)``."""
        return self.state.rgba

    @color.setter
    def color(self, value: Colour) -> None:
        self.state.set_rgba(value)

    @property
    def hsv(self) -> tuple[float, float, float]:
        """The picked colour as ``(h, s, v)``, straight from the state."""
        return self.state.hsv

    @property
    def zone(self) -> str | None:
        """Which part is being dragged: ``"sv"``, ``"hue"``, ``"alpha"``, or ``None``."""
        return self._zone

    # -- layout --------------------------------------------------------- #
    def _layout(
        self, x: float, y: float, w: float, h: float
    ) -> tuple[float, float, float, float]:
        """Where the square and the bars go.

        Computed rather than remembered so :meth:`press` and :meth:`draw`
        cannot drift apart: the layout is a pure function of the box, and a
        second copy of it is how a control ends up responding a bar to the
        left of where it drew one.

        Parameters
        ----------
        x, y, w, h : float
            The box.

        Returns
        -------
        tuple of float
            ``(square, bar_w, hue_x, alpha_x)``. ``alpha_x`` is meaningless
            when there is no alpha bar.
        """
        bar_w = clamp(round(h * 0.12), 8.0, 20.0)
        bars = 2 if self.alpha_bar else 1
        square = max(min(h, w - bars * (bar_w + _GAP)), 1.0)
        hue_x = x + square + _GAP
        return (square, bar_w, hue_x, hue_x + bar_w + _GAP)

    # -- drawing -------------------------------------------------------- #
    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the square, the bars, their cursors and the caption.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The box.
        """
        square, bar_w, hue_x, alpha_x = self._layout(x, y, w, h)
        hue, sat, val = self.state.hsv
        rows = _strips(square)
        band = square / rows

        # The saturation/value square: one grey-to-hue gradient per band.
        p.push_clip(x, y, square, square)
        for row in range(rows):
            level = 1.0 - (row + 0.5) / rows
            grey = floats_to_rgba((level, level, level))
            tint = floats_to_rgba(hsv_to_rgb(hue, 1.0, level))
            p.gradient_rect(x, y + row * band, square, band + 1.0, [grey, tint])
        p.pop_clip()
        p.stroke_rect(x, y, square, square, BORDER, None)
        self._draw_square_cursor(p, x, y, square, sat, val)

        # The hue bar: one flat strip per band.
        p.push_clip(hue_x, y, bar_w, square)
        for row in range(rows):
            level = (row + 0.5) / rows
            p.fill_rect(hue_x, y + row * band, bar_w, band + 1.0,
                        floats_to_rgba(hsv_to_rgb(level, 1.0, 1.0)))
        p.pop_clip()
        p.stroke_rect(hue_x, y, bar_w, square, BORDER, None)
        self._draw_bar_cursor(p, hue_x, y, bar_w, square, hue)

        # The alpha bar: the colour fading to nothing over a checkerboard.
        if self.alpha_bar:
            _checkerboard(p, alpha_x, y, bar_w, square, bar_w / 2.0)
            rgb = self.state.rgb
            p.push_clip(alpha_x, y, bar_w, square)
            for row in range(rows):
                level = 1.0 - (row + 0.5) / rows
                p.fill_rect(alpha_x, y + row * band, bar_w, band + 1.0,
                            (rgb[0], rgb[1], rgb[2], int(level * 255.0 + 0.5)))
            p.pop_clip()
            p.stroke_rect(alpha_x, y, bar_w, square, BORDER, None)
            self._draw_bar_cursor(p, alpha_x, y, bar_w, square,
                                  1.0 - self.state.alpha / 255.0)

        room = h - square - _GAP
        if self.label and room > p.line_height() * 0.5:
            p.text(x, y + square + _GAP, w, room, ALIGN_VCENTER | ALIGN_LEFT,
                   fit_text(p, self.label, w), TEXT)

    def _draw_square_cursor(
        self, p: Painter, x: float, y: float, square: float, sat: float, val: float
    ) -> None:
        """Mark the picked point on the square.

        The reference draws two concentric circles; there is no circle here,
        so it is two concentric hollow squares -- dark outside, light inside,
        so the mark reads against both the white corner and the black edge.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, square : float
            The square's corner and size.
        sat, val : float
            Where the mark goes, ``0.0-1.0``.
        """
        arm = max(3.0, square * 0.03)
        cx = x + clamp(sat, 0.0, 1.0) * square
        cy = y + (1.0 - clamp(val, 0.0, 1.0)) * square
        cx = clamp(cx, x + arm, x + square - arm)
        cy = clamp(cy, y + arm, y + square - arm)
        p.stroke_rect(cx - arm, cy - arm, arm * 2.0, arm * 2.0, _CURSOR_DARK, None)
        p.stroke_rect(cx - arm + 1.0, cy - arm + 1.0, arm * 2.0 - 2.0, arm * 2.0 - 2.0,
                      _CURSOR_LIGHT, None)

    def _draw_bar_cursor(
        self, p: Painter, x: float, y: float, w: float, h: float, fraction: float
    ) -> None:
        """Mark a position down a vertical bar.

        The reference draws four arrows pointing in from the sides; arrows are
        triangles, so this is a full-width line with a dark line above and
        below it, which reads the same and costs three quads.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The bar.
        fraction : float
            Where down the bar the mark goes, ``0.0-1.0``.
        """
        at = y + clamp(fraction, 0.0, 1.0) * h
        at = clamp(at, y + 1.0, y + h - 2.0)
        p.fill_rect(x - 1.0, at - 2.0, w + 2.0, 5.0, _CURSOR_DARK)
        p.fill_rect(x - 1.0, at - 0.5, w + 2.0, 2.0, _CURSOR_LIGHT)

    # -- input ---------------------------------------------------------- #
    def press(
        self,
        x: float,
        y: float,
        box_x: float,
        box_y: float,
        box_w: float,
        box_h: float,
    ) -> str | None:
        """Take a press and start a drag in whichever part was hit.

        Parameters
        ----------
        x, y : float
            The point.
        box_x, box_y, box_w, box_h : float
            The box the picker was drawn into.

        Returns
        -------
        str or None
            ``"sv"``, ``"hue"``, ``"alpha"`` -- the part now being dragged and
            already updated from this press -- or ``None`` if the press missed.
        """
        square, bar_w, hue_x, alpha_x = self._layout(box_x, box_y, box_w, box_h)
        self._zone = None
        if hit(x, y, box_x, box_y, square, square):
            self._zone = "sv"
        elif hit(x, y, hue_x, box_y, bar_w, square):
            self._zone = "hue"
        elif self.alpha_bar and hit(x, y, alpha_x, box_y, bar_w, square):
            self._zone = "alpha"
        if self._zone is None:
            return None
        self._apply(x, y, box_x, box_y, box_w, box_h)
        return self._zone

    def drag(
        self,
        x: float,
        y: float,
        box_x: float,
        box_y: float,
        box_w: float,
        box_h: float,
    ) -> bool:
        """Continue the drag started by :meth:`press`.

        The point is **not** re-tested against the boxes: a drag that has left
        the square still moves saturation and value, clamped at the edges,
        which is what the reference's held-item behaviour does and what stops
        the picker letting go every time the mouse overshoots.

        Parameters
        ----------
        x, y : float
            The point.
        box_x, box_y, box_w, box_h : float
            The box the picker was drawn into.

        Returns
        -------
        bool
            Whether the colour changed.
        """
        if self._zone is None:
            return False
        before = self.color
        self._apply(x, y, box_x, box_y, box_w, box_h)
        return self.color != before

    def release(self) -> None:
        """End the drag."""
        self._zone = None

    def _apply(
        self,
        x: float,
        y: float,
        box_x: float,
        box_y: float,
        box_w: float,
        box_h: float,
    ) -> None:
        """Write the held zone's component (and only that one) from a point.

        Parameters
        ----------
        x, y : float
            The point.
        box_x, box_y, box_w, box_h : float
            The box the picker was drawn into.
        """
        square, _bar_w, _hue_x, _alpha_x = self._layout(box_x, box_y, box_w, box_h)
        span = max(square - 1.0, 1.0)
        down = clamp((y - box_y) / span, 0.0, 1.0)
        if self._zone == "sv":
            self.state.set_hsv(s=clamp((x - box_x) / span, 0.0, 1.0), v=1.0 - down)
        elif self._zone == "hue":
            self.state.set_hsv(h=down)
        elif self._zone == "alpha":
            self.state.set_alpha(int((1.0 - down) * 255.0 + 0.5))


class ColorPicker3(ColorPicker4):
    """The picker without the alpha bar.

    The reference spells this ``ColorPicker3`` and implements it as
    ``ColorPicker4`` with ``NoAlpha``; this is the same arrangement. The
    colour keeps whatever alpha it was given -- the bar is gone, not the
    channel.

    Parameters
    ----------
    color : Colour, optional
        The starting colour.
    label : str, optional
        Caption drawn under the square.
    """

    def __init__(self, color: Colour = (255, 0, 0, 255), label: str = "") -> None:
        super().__init__(color=color, alpha_bar=False, label=label)
