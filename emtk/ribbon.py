"""``emtk.ribbon`` -- a ribbon bar: tabs of grouped command buttons, drawn with :mod:`emtk.im`.

A ribbon is a tab strip over a band of **groups**; each group is a captioned run
of buttons. A button is *large* (its icon above its label, as tall as the band)
or *small* (icon and label on one line, three stacked per column). The model is
plain data a host rebuilds whenever it likes:

.. code-block:: python

    ribbon = Ribbon([
        RibbonTab("Home", [
            RibbonGroup("Project", [
                RibbonButton("save", "Save", icon="💾", tooltip="Save the project."),
                RibbonButton("open", "Open…", icon="📂"),
            ]),
        ]),
    ])
    # every frame, inside an im window:
    pressed = ribbon.draw((x, y, width, ribbon.height()))
    if pressed == "save":
        save()

A button may carry its own ``on_press`` instead; :meth:`Ribbon.draw` calls it and
still returns the key.

**When the groups do not fit** the width they are given, the rightmost group is
drawn *collapsed*: one button with the group's icon and caption that opens the
group's buttons as a menu. Groups collapse from the right until the rest fits,
and if even the collapsed groups do not fit, the ones that are left over go
behind one ``»`` button at the end, whose menu lists them under their captions.
No button is ever unreachable, at any width.

**The tab row** also holds a search field (typing filters every tab's buttons
into one band of results, grouped by where they live), a toggle that folds the
band away (a folded ribbon shows the band again when a tab is clicked, until a
button of it is pressed), a **pin** (a pinned ribbon stays as the user left it;
an unpinned one folds itself again after every button pressed -- *auto-fold*;
:meth:`Ribbon.state` / :meth:`Ribbon.restore` let a host keep a pinned ribbon's
fold and tab between sessions), and a *corner* the host may draw into (help, a
language switch).

Labels, captions and tooltips are English source text and go through
:func:`emtk.i18n.tr` when drawn, as every emtk widget's do.

Every drawn control is in :attr:`Ribbon.item_rects` (``ribbon.tab.<title>``,
``ribbon.button.<key>``, ``ribbon.group.<tab>.<group>``, ``ribbon.overflow``,
``ribbon.search``, ``ribbon.fold``, ``ribbon.pin``), so a :class:`emtk.testing.Driver` can press
them by name.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from . import im_widgets as _w
from .i18n import mark, tr
from .icons import draw_icon, icon_box
from .im_core import Col, get_current_context

__all__ = ["Ribbon", "RibbonButton", "RibbonGroup", "RibbonTab", "SMALL_ROWS"]

#: Small buttons stacked in one column of a group.
SMALL_ROWS = 3
#: Padding inside a group, left and right of its buttons.
GROUP_PAD = 6.0
#: Gap between two columns of a group.
COLUMN_GAP = 4.0
#: Width of the search field in the tab row.
SEARCH_WIDTH = 160.0
#: The overflow button's glyph and the collapsed group's drop marker.
OVERFLOW = "»"
DROP = "▾"

mark("Search…")
mark("Fold the ribbon: show only its tabs.")
mark("Unfold the ribbon: show its buttons again.")
mark("Unpin the ribbon: it folds away after each command (auto-fold).")
mark("Pin the ribbon: it stays as you leave it, also at the next start.")
mark("More")
mark("No tool matches the search.")


@dataclass
class RibbonButton:
    """One command of the ribbon.

    Parameters
    ----------
    key : str
        Stable identifier; returned by :meth:`Ribbon.draw` when pressed.
    label : str
        English source caption (translated when drawn).
    icon : str
        A pictogram, normally an emoji.
    tooltip : str
        English source text shown on hover; the label when empty.
    large : bool
        Draw the icon above the label, as tall as the band.
    enabled : bool or callable
        A disabled button is drawn dimmed and does not fire; a callable is asked every frame.
    on_press : callable, optional
        Called when the button is pressed.
    """

    key: str
    label: str
    icon: str = ""
    tooltip: str = ""
    large: bool = False
    enabled: bool | Callable[[], bool] = True
    on_press: Callable[[], Any] | None = None

    def is_enabled(self) -> bool:
        """Whether the button fires now."""
        return bool(self.enabled() if callable(self.enabled) else self.enabled)


@dataclass
class RibbonGroup:
    """A captioned run of buttons inside a tab."""

    title: str
    buttons: list[RibbonButton] = field(default_factory=list)

    @property
    def icon(self) -> str:
        """The icon a collapsed group shows: its first button's."""
        return next((button.icon for button in self.buttons if button.icon), "")


@dataclass
class RibbonTab:
    """One tab of the ribbon: its groups, left to right."""

    title: str
    groups: list[RibbonGroup] = field(default_factory=list)


def _col(which):
    return _w._col(which)


class Ribbon:
    """The ribbon bar. See the module docstring.

    Parameters
    ----------
    tabs : sequence of RibbonTab
        The tabs, left to right. :attr:`tabs` may be replaced at any time.
    name : str
        Prefix of the ids and popups (two ribbons in one frame need two names).
    search : bool
        Whether the tab row has the search field.
    pin : bool
        Whether the tab row has the pin toggle (:attr:`pinned`).
    """

    def __init__(self, tabs: Sequence[RibbonTab] = (), *, name: str = "ribbon",
                 search: bool = True, pin: bool = False) -> None:
        self.tabs: list[RibbonTab] = list(tabs)
        self.name = name
        self.search = search
        self.pin = pin
        #: A pinned ribbon stays as the user left it; an unpinned one folds again after every pick.
        self.pinned = True
        #: The selected tab's title (the first tab when empty or unknown).
        self.current = ""
        #: Whether the band is folded away (only the tab row is shown).
        self.folded = False
        #: A folded ribbon whose band is shown for one pick after a tab click.
        self.peek = False
        #: The search text.
        self.query = ""
        #: Named rectangles of the last frame (canvas coordinates).
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        #: How each group of the current tab was drawn last frame: ``"full"``, ``"collapsed"`` or ``"overflow"``.
        self.group_modes: dict[str, str] = {}
        #: Whether one of the ribbon's menus (a collapsed group, the overflow) is open: a host
        #: keeps the pointer from the content under it while it is.
        self.menu_open = False
        #: Line and frame height of the last frame drawn, for :meth:`height` between frames.
        self._last_metrics = (16.0, 22.0)

    # -- geometry ------------------------------------------------------------- #
    def _metrics(self) -> tuple[float, float]:
        """``(line height, frame height)`` of the current frame, or of the last one outside a frame."""
        try:
            ctx = get_current_context()
        except RuntimeError:
            return self._last_metrics
        line = ctx.p.line_height()
        self._last_metrics = (line, line + ctx.style.frame_padding[1] * 2.0)
        return self._last_metrics

    def _frame_height(self) -> float:
        return self._metrics()[1]

    def tab_row_height(self) -> float:
        """Height of the tab row."""
        return self._frame_height() + 2.0

    def band_height(self) -> float:
        """Height of the band of groups: three small rows and the caption row."""
        line, frame = self._metrics()
        return frame * SMALL_ROWS + line + 8.0

    def height(self) -> float:
        """The height :meth:`draw` needs now (the tab row alone while folded)."""
        if self.folded and not self.peek and not self.query:
            return self.tab_row_height()
        return self.tab_row_height() + self.band_height()

    def state(self) -> dict:
        """What a host keeps between sessions: ``pinned``, and while pinned the fold and the tab."""
        out: dict = {"pinned": bool(self.pinned)}
        if self.pinned:
            out.update(folded=bool(self.folded), current=str(self.current))
        return out

    def restore(self, state: dict | None) -> None:
        """Adopt a :meth:`state`: an unpinned ribbon starts folded, a pinned one as it was left."""
        state = state if isinstance(state, dict) else {}
        self.pinned = bool(state.get("pinned", True))
        self.peek = False
        if not self.pinned:
            self.folded = True
            return
        self.folded = bool(state.get("folded", self.folded))
        if state.get("current"):
            self.current = str(state["current"])

    def set_pinned(self, pinned: bool) -> None:
        """Pin (the band is shown and stays) or unpin (auto-fold: the band folds away now)."""
        self.pinned = bool(pinned)
        self.peek = False
        self.folded = not self.pinned

    def current_tab(self) -> RibbonTab | None:
        """The selected tab."""
        for tab in self.tabs:
            if tab.title == self.current:
                return tab
        return self.tabs[0] if self.tabs else None

    # -- measuring ------------------------------------------------------------ #
    def _text_w(self, text: str) -> float:
        return get_current_context().draw.calc_text_size(text)[0]

    def _icon_slot(self) -> float:
        """A small button's icon slot and the gap after it (a colour pictogram draws wider than a line)."""
        return self._frame_height() + 4.0

    def _small_width(self, button: RibbonButton) -> float:
        ctx = get_current_context()
        pad = ctx.style.frame_padding[0]
        icon = self._icon_slot() if button.icon else 0.0
        return pad * 2.0 + icon + self._text_w(tr(button.label))

    def _large_width(self, button: RibbonButton) -> float:
        ctx = get_current_context()
        pad = ctx.style.frame_padding[0]
        return max(self._large_icon() + pad * 2.0, self._text_w(tr(button.label)) + pad * 2.0)

    def _large_icon(self) -> float:
        """A large button's icon box (the one size rule of :mod:`emtk.icons`)."""
        return icon_box(get_current_context().p.line_height(), large=True)

    def _draw_icon(self, icon: str, x: float, y: float, size: float, colour, enabled: bool) -> None:
        """*icon* in colour, fitted into the square at ``(x, y)``; as text where it cannot be rasterised."""
        ctx = get_current_context()
        if draw_icon(ctx.draw.p, icon, x, y, size, colour, enabled):
            return
        glyph = _w.icon_text(icon)
        gw, gh = ctx.draw.calc_text_size(glyph)
        ctx.draw.add_text((x + (size - gw) * 0.5, y + (size - gh) * 0.5), colour, glyph)

    def _columns(self, group: RibbonGroup) -> list[tuple[bool, list[RibbonButton], float]]:
        """``(large, buttons, width)`` per column: a large button alone, else up to three small ones."""
        columns: list[tuple[bool, list[RibbonButton], float]] = []
        run: list[RibbonButton] = []

        def flush() -> None:
            for start in range(0, len(run), SMALL_ROWS):
                chunk = run[start:start + SMALL_ROWS]
                columns.append((False, chunk, max(self._small_width(b) for b in chunk)))
            run.clear()

        for button in group.buttons:
            if button.large:
                flush()
                columns.append((True, [button], self._large_width(button)))
            else:
                run.append(button)
        flush()
        return columns

    def _full_width(self, group: RibbonGroup) -> float:
        columns = self._columns(group)
        inner = sum(width for _l, _b, width in columns) + COLUMN_GAP * max(0, len(columns) - 1)
        return max(inner, self._text_w(tr(group.title))) + GROUP_PAD * 2.0

    def _collapsed_width(self, group: RibbonGroup) -> float:
        ctx = get_current_context()
        caption = self._text_w(tr(group.title) + " " + DROP)
        return max(self._frame_height() * 1.8, caption + ctx.style.frame_padding[0] * 2.0) + GROUP_PAD * 2.0

    def _overflow_width(self) -> float:
        return self._frame_height() * 1.4 + GROUP_PAD * 2.0

    def fit(self, groups: Sequence[RibbonGroup], width: float) -> list[str]:
        """How each group is drawn in *width*: ``"full"``, ``"collapsed"`` or ``"overflow"``.

        Groups collapse from the right (each only where collapsing saves width)
        until the rest fits; then the rightmost go behind the overflow button
        until what is left fits.
        """
        full = [self._full_width(g) for g in groups]
        small = [self._collapsed_width(g) for g in groups]
        modes = ["full"] * len(groups)

        def total() -> float:
            used = sum(full[i] if m == "full" else small[i] for i, m in enumerate(modes) if m != "overflow")
            return used + (self._overflow_width() if "overflow" in modes else 0.0)

        for index in range(len(groups) - 1, -1, -1):
            if total() <= width:
                return modes
            if small[index] < full[index]:
                modes[index] = "collapsed"
        for index in range(len(groups) - 1, -1, -1):
            if total() <= width:
                return modes
            modes[index] = "overflow"
        return modes

    # -- drawing -------------------------------------------------------------- #
    def draw(self, box, corner: Callable[[float, float, float], float] | None = None) -> str | None:
        """Draw the ribbon into *box* (canvas coordinates) of the current im window.

        Parameters
        ----------
        box : tuple of float
            ``(x, y, width, height)``; the height should be :meth:`height`.
        corner : callable, optional
            ``corner(right, top, height) -> width`` draws the host's own controls in the tab
            row, right-aligned at *right*, and returns how wide they are.

        Returns
        -------
        str or None
            The key of the button pressed this frame.
        """
        self.item_rects.clear()
        self.menu_open = False
        x, y, width, _height = (float(v) for v in box)
        ctx = get_current_context()
        pressed = None
        row_h = self.tab_row_height()
        ctx.draw.add_rect_filled((x, y), (x + width, y + row_h), _col(Col.MENU_BAR_BG))
        right = x + width - 4.0
        if corner is not None:
            right -= float(corner(right, y + 1.0, row_h - 2.0) or 0.0) + 4.0
        if self.pin:
            right = self._draw_pin_toggle(right, y + 1.0)
        right = self._draw_fold_toggle(right, y + 1.0)
        if self.search:
            right = self._draw_search(right, y + 1.0)
        self._draw_tab_strip(x + 4.0, y + 1.0, right - x - 8.0)
        if self.height() <= row_h:
            return pressed
        band_y = y + row_h
        band_h = self.band_height()
        ctx.draw.add_rect_filled((x, band_y), (x + width, band_y + band_h), _col(Col.WINDOW_BG))
        ctx.draw.add_line((x, band_y + band_h - 1.0), (x + width, band_y + band_h - 1.0),
                          _col(Col.BORDER))
        groups = self._result_groups() if self.query.strip() else (
            self.current_tab().groups if self.current_tab() else [])
        if not groups:
            if self.query.strip():
                ctx.draw.add_text((x + GROUP_PAD, band_y + GROUP_PAD), _col(Col.TEXT_DISABLED),
                                  tr("No tool matches the search."))
            return pressed
        hit = self._draw_band(groups, x, band_y, width, band_h)
        if hit is not None and self.peek:
            self.peek = False
        if hit is not None and not self.pinned:
            self.folded, self.peek = True, False  # auto-fold: the pick is made, the band goes
        return pressed or hit

    def _fire(self, button: RibbonButton) -> str:
        if button.on_press is not None:
            button.on_press()
        return button.key

    def _draw_tab_strip(self, x: float, y: float, room: float) -> None:
        ctx = get_current_context()
        h = self._frame_height()
        pad = ctx.style.frame_padding[0]
        current = self.current_tab()
        for tab in self.tabs:
            caption = tr(tab.title)
            w = self._text_w(caption) + pad * 2.0
            tab_box = (x, y, w, h)
            hovered, _held, clicked = ctx.button_behavior(tab_box, (self.name, "tab", tab.title))
            if clicked:
                if self.folded:
                    self.peek = not (self.peek and tab is current)
                self.current = tab.title
                current = tab
                self.query = ""
            selected = tab is current and (not self.folded or self.peek)
            if selected or hovered:
                colour = _col(Col.TAB_SELECTED) if selected else _col(Col.HEADER_HOVERED)
                ctx.draw.add_rect_filled((x, y), (x + w, y + h), colour, 0.0)
            ctx.draw.add_text((x + pad, y + ctx.style.frame_padding[1]), _col(Col.TEXT), caption)
            self.item_rects[f"{self.name}.tab.{tab.title}"] = tab_box
            x += w + 2.0

    def _draw_fold_toggle(self, right: float, y: float) -> float:
        ctx = get_current_context()
        h = self._frame_height()
        glyph = "▴" if not self.folded else "▾"
        w = h
        box = (right - w, y, w, h)
        hovered, _held, clicked = ctx.button_behavior(box, (self.name, "fold"))
        _w.set_item_tooltip(tr("Fold the ribbon: show only its tabs.") if not self.folded
                            else tr("Unfold the ribbon: show its buttons again."))
        if clicked:
            self.folded = not self.folded
            self.peek = False
        if hovered:
            ctx.draw.add_rect_filled((box[0], box[1]), (box[0] + w, box[1] + h),
                                     _col(Col.BUTTON_HOVERED), ctx.style.frame_rounding)
        gw, gh = ctx.draw.calc_text_size(glyph)
        ctx.draw.add_text((box[0] + (w - gw) * 0.5, box[1] + (h - gh) * 0.5), _col(Col.TEXT), glyph)
        self.item_rects[f"{self.name}.fold"] = box
        return box[0] - 4.0

    def _draw_pin_toggle(self, right: float, y: float) -> float:
        ctx = get_current_context()
        h = self._frame_height()
        w = h * 1.3
        box = (right - w, y, w, h)
        hovered, _held, clicked = ctx.button_behavior(box, (self.name, "pin"))
        _w.set_item_tooltip(tr("Unpin the ribbon: it folds away after each command (auto-fold).")
                            if self.pinned else
                            tr("Pin the ribbon: it stays as you leave it, also at the next start."))
        if clicked:
            self.set_pinned(not self.pinned)
        if self.pinned or hovered:
            colour = _col(Col.BUTTON_ACTIVE) if self.pinned else _col(Col.BUTTON_HOVERED)
            ctx.draw.add_rect_filled((box[0], box[1]), (box[0] + w, box[1] + h), colour,
                                     ctx.style.frame_rounding)
        # A drawn push-pin (no glyph: the atlas keeps only what controls spell): a round head
        # over a needle, upright while pinned, tilted while the ribbon auto-folds.
        colour = _col(Col.TEXT) if self.pinned else _col(Col.TEXT_DISABLED)
        cx, cy = box[0] + w * 0.5, box[1] + h * 0.5
        r = h * 0.18
        tilt = 0.0 if self.pinned else h * 0.18
        head = (cx + tilt, cy - h * 0.16)
        ctx.draw.add_circle_filled(head, r, colour)
        ctx.draw.add_line((head[0] - r * 1.4, head[1] + r), (head[0] + r * 1.4, head[1] + r),
                          colour, 1.5)
        ctx.draw.add_line((head[0], head[1] + r), (cx - tilt, cy + h * 0.32), colour, 1.5)
        self.item_rects[f"{self.name}.pin"] = box
        return box[0] - 4.0

    def _draw_search(self, right: float, y: float) -> float:
        left = right - SEARCH_WIDTH
        _w.set_cursor_screen_pos((left, y))
        _w.set_next_item_width(SEARCH_WIDTH)
        changed, value = _w.input_text_with_hint(f"##{self.name} search", self.query, tr("Search…"))
        if changed:
            self.query = value
        self.item_rects[f"{self.name}.search"] = (left, y, SEARCH_WIDTH, self._frame_height())
        return left - 6.0

    def _result_groups(self) -> list[RibbonGroup]:
        """Every tab's buttons that match :attr:`query`, grouped as ``Tab › Group``."""
        words = self.query.casefold().split()
        groups = []
        for tab in self.tabs:
            for group in tab.groups:
                found = []
                for button in group.buttons:
                    text = " ".join((tr(tab.title), tr(group.title), tr(button.label), tr(button.tooltip),
                                     tab.title, group.title, button.label, button.key)).casefold()
                    if all(word in text for word in words):
                        found.append(RibbonButton(button.key, button.label, button.icon, button.tooltip,
                                                  False, button.enabled, button.on_press))
                if found:
                    title = tab.title if group.title == tab.title else f"{tr(tab.title)} ▸ {tr(group.title)}"
                    groups.append(RibbonGroup(title, found))
        return groups

    def _draw_band(self, groups: Sequence[RibbonGroup], x: float, y: float, width: float,
                   height: float) -> str | None:
        ctx = get_current_context()
        modes = self.fit(groups, width - 8.0)
        tab_title = self.current_tab().title if self.current_tab() and not self.query.strip() else "search"
        self.group_modes = {group.title: mode for group, mode in zip(groups, modes)}
        caption_h = ctx.p.line_height()
        body_h = height - caption_h - 6.0
        cx = x + 4.0
        pressed = None
        overflow: list[RibbonGroup] = []
        for group, mode in zip(groups, modes):
            if mode == "overflow":
                overflow.append(group)
                continue
            if mode == "full":
                gw = self._full_width(group)
                hit = self._draw_group_buttons(group, cx + GROUP_PAD, y + 3.0, body_h)
            else:
                gw = self._collapsed_width(group)
                hit = self._draw_collapsed(group, tab_title, cx + GROUP_PAD, y + 3.0, gw - GROUP_PAD * 2.0,
                                           height - 6.0)
            pressed = pressed or hit
            if mode == "full":  # a collapsed group's button already carries its caption
                caption = tr(group.title)
                tw = self._text_w(caption)
                ctx.draw.add_text((cx + (gw - tw) * 0.5, y + height - caption_h - 3.0),
                                  _col(Col.TEXT_DISABLED), caption)
            sep_x = cx + gw
            ctx.draw.add_line((sep_x, y + 4.0), (sep_x, y + height - 4.0), _col(Col.SEPARATOR))
            cx = sep_x + 1.0
        if overflow:
            hit = self._draw_overflow(overflow, cx + GROUP_PAD, y + 3.0, height - 6.0)
            pressed = pressed or hit
        return pressed

    def _draw_group_buttons(self, group: RibbonGroup, x: float, y: float, body_h: float) -> str | None:
        pressed = None
        row_h = self._frame_height()
        for large, buttons, column_w in self._columns(group):
            if large:
                hit = self._large_button(buttons[0], (x, y, column_w, body_h))
                pressed = pressed or hit
            else:
                for row, button in enumerate(buttons):
                    hit = self._small_button(button, (x, y + row * row_h, column_w, row_h))
                    pressed = pressed or hit
            x += column_w + COLUMN_GAP
        return pressed

    def _button_frame(self, button: RibbonButton, box, item_id) -> tuple[bool, bool, bool]:
        ctx = get_current_context()
        enabled = button.is_enabled()
        if not enabled:
            _w.begin_disabled(True)
        hovered, held, clicked = ctx.button_behavior(box, item_id)
        if not enabled:
            _w.end_disabled()
        _w.set_item_tooltip(tr(button.tooltip) if button.tooltip else tr(button.label))
        if hovered or held:
            ctx.draw.add_rect_filled((box[0], box[1]), (box[0] + box[2], box[1] + box[3]),
                                     _col(Col.BUTTON_ACTIVE if held else Col.BUTTON_HOVERED),
                                     ctx.style.frame_rounding)
        return hovered, held, clicked and enabled

    def _small_button(self, button: RibbonButton, box) -> str | None:
        ctx = get_current_context()
        _h, _held, clicked = self._button_frame(button, box, (self.name, "button", button.key))
        colour = _col(Col.TEXT if button.is_enabled() else Col.TEXT_DISABLED)
        pad_x, pad_y = ctx.style.frame_padding
        tx = box[0] + pad_x
        if button.icon:
            size = icon_box(ctx.p.line_height())
            slot = self._frame_height()
            self._draw_icon(button.icon, tx + (slot - size) * 0.5, box[1] + (box[3] - size) * 0.5,
                            size, colour, button.is_enabled())
            tx += self._icon_slot()
        ctx.draw.add_text((tx, box[1] + pad_y), colour, tr(button.label))
        self.item_rects[f"{self.name}.button.{button.key}"] = tuple(box)
        return self._fire(button) if clicked else None

    def _large_button(self, button: RibbonButton, box) -> str | None:
        ctx = get_current_context()
        _h, _held, clicked = self._button_frame(button, box, (self.name, "button", button.key))
        colour = _col(Col.TEXT if button.is_enabled() else Col.TEXT_DISABLED)
        label = tr(button.label)
        lw, lh = ctx.draw.calc_text_size(label)
        if button.icon:
            size = min(self._large_icon(), max(box[3] - lh - 12.0, 1.0))
            self._draw_icon(button.icon, box[0] + (box[2] - size) * 0.5, box[1] + 4.0, size,
                            colour, button.is_enabled())
        ctx.draw.add_text((box[0] + (box[2] - lw) * 0.5, box[1] + box[3] - lh - 4.0), colour, label)
        self.item_rects[f"{self.name}.button.{button.key}"] = tuple(box)
        return self._fire(button) if clicked else None

    def _popup_name(self, *parts: str) -> str:
        return "##" + ".".join((self.name, *parts))

    def _draw_menu(self, popup: str, groups: Sequence[RibbonGroup], captions: bool) -> str | None:
        """A collapsed group's (or the overflow's) buttons as a menu; returns the key picked."""
        if not _w.begin_popup(popup):
            return None
        self.menu_open = True
        pressed = None
        for group in groups:
            if captions:
                _w.separator_text(group.title)
            for button in group.buttons:
                if _w.menu_item(button.label, enabled=button.is_enabled(), icon=button.icon or None):
                    pressed = self._fire(button)
                _w.set_item_tooltip(tr(button.tooltip) if button.tooltip else "")
        _w.end_popup()
        return pressed

    def _drop_button(self, item_key: str, icon: str, caption: str, box, popup: str, tooltip: str) -> None:
        ctx = get_current_context()
        hovered, held, clicked = ctx.button_behavior(box, (self.name, "drop", item_key))
        _w.set_item_tooltip(tooltip)
        if hovered or held:
            ctx.draw.add_rect_filled((box[0], box[1]), (box[0] + box[2], box[1] + box[3]),
                                     _col(Col.BUTTON_ACTIVE if held else Col.BUTTON_HOVERED),
                                     ctx.style.frame_rounding)
        cw, ch = ctx.draw.calc_text_size(caption)
        if icon:
            size = min(self._large_icon(), max(box[3] - ch - 12.0, 1.0))
            self._draw_icon(icon, box[0] + (box[2] - size) * 0.5, box[1] + 4.0, size,
                            _col(Col.TEXT), True)
        ctx.draw.add_text((box[0] + (box[2] - cw) * 0.5, box[1] + box[3] - ch - 4.0), _col(Col.TEXT), caption)
        self.item_rects[item_key] = tuple(box)
        if clicked:
            ctx.open_context_popup(popup, (box[0], box[1] + box[3]))

    def _draw_collapsed(self, group: RibbonGroup, tab: str, x: float, y: float, w: float,
                        body_h: float) -> str | None:
        popup = self._popup_name("group", tab, group.title)
        caption = tr(group.title) + " " + DROP
        tip = ", ".join(tr(button.label) for button in group.buttons)
        self._drop_button(f"{self.name}.group.{tab}.{group.title}", group.icon, caption,
                          (x, y, w, body_h), popup, tip)
        return self._draw_menu(popup, [group], captions=False)

    def _draw_overflow(self, groups: Sequence[RibbonGroup], x: float, y: float, body_h: float) -> str | None:
        popup = self._popup_name("overflow")
        w = self._overflow_width() - GROUP_PAD * 2.0
        tip = ", ".join(tr(group.title) for group in groups)
        self._drop_button(f"{self.name}.overflow", "", OVERFLOW, (x, y, w, body_h), popup,
                          tr("More") + ": " + tip)
        return self._draw_menu(popup, groups, captions=True)
