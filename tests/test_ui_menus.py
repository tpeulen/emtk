"""Painter-level tests for the menu and popup controls.

No GUI toolkit, no clock and no input context: a menu that quietly grows a
dependency on any of the three fails here first.
"""

from __future__ import annotations

import pytest

from emtk.widgets import menus


class RecordingPainter:
    """Records the six operations instead of performing them."""

    def __init__(self) -> None:
        self.fills: list[tuple] = []
        self.strokes: list[tuple] = []
        self.strings: list[str] = []
        self.clips: list[tuple] = []

    def fill_rect(self, x, y, w, h, colour) -> None:
        self.fills.append((x, y, w, h, colour))

    def stroke_rect(self, x, y, w, h, edge, fill=None) -> None:
        self.strokes.append((x, y, w, h, edge, fill))

    def gradient_rect(self, x, y, w, h, stops, edge=None) -> None:
        self.fills.append((x, y, w, h, stops[0] if stops else None))

    def text(self, x, y, w, h, align, string, colour, bold=False) -> None:
        self.strings.append(string)

    def push_clip(self, x, y, w, h) -> None:
        self.clips.append((x, y, w, h))

    def pop_clip(self) -> None:
        if self.clips:
            self.clips.pop()

    def text_width(self, string) -> float:
        return len(string) * 7.0

    def line_height(self) -> float:
        return 12.0


def _bar() -> menus.MenuBar:
    """Build a bar with two menus, one carrying a nested submenu."""
    inner = menus.Menu("Recent", [menus.MenuItem("one.pdb"), menus.MenuItem("two.pdb")])
    file_menu = menus.Menu(
        "File",
        [
            menus.MenuItem("Open", "Ctrl+O"),
            inner,
            None,
            menus.MenuItem("Quit", "Ctrl+Q"),
        ],
    )
    edit_menu = menus.Menu("Edit", [menus.MenuItem("Undo", "Ctrl+Z", enabled=False)])
    return menus.MenuBar([file_menu, edit_menu])


ALL = [
    lambda: menus.MenuItem("Open", "Ctrl+O", checked=True),
    lambda: menus.Menu("File", [menus.MenuItem("Open"), None, menus.MenuItem("Quit")]),
    lambda: _bar(),
    lambda: menus.Popup([menus.MenuItem("Copy")], title="Selection"),
    lambda: menus.PopupModal([menus.MenuItem("OK")], title="Really?"),
]


@pytest.mark.parametrize("build", ALL, ids=lambda b: type(b()).__name__)
def test_every_control_paints_and_balances_its_clips(build):
    """Every control draws something and leaves the clip stack as it found it."""
    painter = RecordingPainter()
    control = build()
    if isinstance(control, (menus.Menu, menus.MenuBar)):
        opener = control if isinstance(control, menus.Menu) else control.menus[0]
        opener.open = True
    if isinstance(control, menus.Popup):
        control.open_at(40.0, 30.0)
    control.draw(painter, 0.0, 0.0, 400.0, 300.0)
    assert painter.fills or painter.strokes or painter.strings
    assert painter.clips == []


# ---------------------------------------------------------------------- #
# Sizing: the shortcut is a column, and it widens the panel
# ---------------------------------------------------------------------- #
def test_panel_is_at_least_as_wide_as_its_widest_item_and_shortcut_column():
    """Width = widest label + spacing + widest shortcut + spacing + mark + pad."""
    painter = RecordingPainter()
    menu = menus.Menu(
        "File",
        [menus.MenuItem("Open", "Ctrl+O"), menus.MenuItem("Save As", "Ctrl+Shift+S")],
    )
    width, _height = menu.panel_size(painter)

    label_w = painter.text_width("Save As")
    shortcut_w = painter.text_width("Ctrl+Shift+S")
    mark_w = painter.line_height() * menus.MARK_SCALE
    wanted = (
        label_w + menus.SPACING + shortcut_w + menus.SPACING + mark_w + 2.0 * menus.PAD
    )
    assert width == pytest.approx(wanted)
    # And every row really does fit inside it.
    assert width >= label_w + shortcut_w


def test_the_shortcut_column_is_what_widens_the_panel():
    """The same menu without accelerators is narrower by the whole column."""
    painter = RecordingPainter()
    with_shortcuts = menus.Menu("File", [menus.MenuItem("Open", "Ctrl+Shift+O")])
    without = menus.Menu("File", [menus.MenuItem("Open")])
    wide, _ = with_shortcuts.panel_size(painter)
    narrow, _ = without.panel_size(painter)
    assert wide - narrow == pytest.approx(
        painter.text_width("Ctrl+Shift+O") + menus.SPACING
    )


def test_a_long_shortcut_on_one_row_widens_every_row():
    """One row's accelerator sets the column, so no label can run into it."""
    painter = RecordingPainter()
    menu = menus.Menu(
        "Edit",
        [menus.MenuItem("Undo", "Ctrl+Z"), menus.MenuItem("Redo", "Ctrl+Shift+Z")],
    )
    menu.open = True
    menu.viewport = (800.0, 600.0)
    menu.draw(painter, 0.0, 0.0, 60.0, 18.0)
    widest = painter.text_width("Ctrl+Shift+Z")
    for entry in menu.entries:
        assert entry.column_shortcut_width == pytest.approx(widest)


# ---------------------------------------------------------------------- #
# Placement: flipping rather than overflowing
# ---------------------------------------------------------------------- #
def test_a_popup_near_the_bottom_right_flips_instead_of_overflowing():
    """Right and down have no room, so it goes up and left, wholly on screen."""
    painter = RecordingPainter()
    popup = menus.Popup([menus.MenuItem("Alpha"), menus.MenuItem("Beta")])
    popup.open_at(190.0, 95.0)
    popup.draw(painter, 0.0, 0.0, 200.0, 100.0)

    pos_x, pos_y, width, height = popup.panel_rect
    assert pos_x + width <= 200.0
    assert pos_y + height <= 100.0
    assert pos_x >= 0.0 and pos_y >= 0.0
    # It really moved off the anchor rather than merely fitting by luck.
    assert pos_x < 190.0
    assert pos_y < 95.0


def test_a_popup_with_room_stays_exactly_where_it_was_asked_for():
    """The flip is the exception; a popup that fits does not move."""
    painter = RecordingPainter()
    popup = menus.Popup([menus.MenuItem("Alpha")])
    popup.open_at(20.0, 30.0)
    popup.draw(painter, 0.0, 0.0, 400.0, 300.0)
    pos_x, pos_y, _w, _h = popup.panel_rect
    assert (pos_x, pos_y) == pytest.approx((20.0, 30.0))


def test_a_submenu_against_the_right_edge_opens_on_the_other_side():
    """The classic bug: clamped instead of flipped, a submenu covers its parent."""
    painter = RecordingPainter()
    submenu = menus.Menu("Recent", [menus.MenuItem("one.pdb")])
    submenu.viewport = (200.0, 100.0)
    submenu.horizontal = False
    submenu.open = True
    row = (140.0, 10.0, 55.0, 17.0)
    submenu.draw(painter, *row)

    pos_x, _pos_y, width, _height = submenu.panel_rect
    assert pos_x + width <= row[0] + menus.OVERLAP    # entirely left of the parent
    assert pos_x >= 0.0


def test_a_bar_menu_drops_below_the_strip_and_not_beside_it():
    """The bar is what a bar menu avoids, so right and left are ruled out."""
    painter = RecordingPainter()
    bar = _bar()
    bar.set_viewport(400.0, 300.0)
    bar.menus[0].open = True
    bar.draw(painter, 0.0, 0.0, 400.0, 18.0)
    _pos_x, pos_y, _w, _h = bar.menus[0].panel_rect
    assert pos_y == pytest.approx(18.0)


def test_best_popup_pos_falls_back_inside_when_no_side_has_room():
    """A panel bigger than its viewport is pushed in, not left hanging out."""
    x, y, direction = menus.best_popup_pos(
        (90.0, 90.0), (300.0, 300.0), (0.0, 0.0, 100.0, 100.0), (90.0, 90.0, 90.0, 90.0)
    )
    assert direction == "none"
    assert (x, y) == (0.0, 0.0)


# ---------------------------------------------------------------------- #
# Presses
# ---------------------------------------------------------------------- #
def test_a_disabled_menu_item_refuses_its_click():
    """Shown, dimmed, and inert -- but the press is still the menu's."""
    painter = RecordingPainter()
    item = menus.MenuItem("Undo", "Ctrl+Z", enabled=False)
    assert item.press(10.0, 5.0, 0.0, 0.0, 100.0, 18.0) is False

    menu = menus.Menu("Edit", [item])
    menu.viewport = (400.0, 300.0)
    menu.open = True
    menu.draw(painter, 0.0, 0.0, 60.0, 18.0)
    row_x, row_y, row_w, row_h = menu._rows[0][1]
    result = menu.press(row_x + row_w * 0.5, row_y + row_h * 0.5, 0.0, 0.0, 60.0, 18.0)
    assert result.item is None            # nothing fired
    assert result.consumed is True        # but it did not fall through to the scene
    assert menu.open is True              # and the menu stayed up


def test_an_enabled_menu_item_fires_and_closes_its_menu():
    """Activation is what closes a menu, exactly as CloseCurrentPopup does."""
    painter = RecordingPainter()
    item = menus.MenuItem("Open", "Ctrl+O")
    menu = menus.Menu("File", [item])
    menu.viewport = (400.0, 300.0)
    menu.open = True
    menu.draw(painter, 0.0, 0.0, 60.0, 18.0)
    row_x, row_y, row_w, row_h = menu._rows[0][1]
    result = menu.press(row_x + row_w * 0.5, row_y + row_h * 0.5, 0.0, 0.0, 60.0, 18.0)
    assert result.item is item
    assert result.consumed and result.closed
    assert menu.open is False


def test_a_checkable_item_toggles_when_it_fires():
    """The reference's ``bool*`` overload; the plain one does not toggle."""
    toggling = menus.MenuItem("Sticks", checkable=True)
    assert toggling.press(5.0, 5.0, 0.0, 0.0, 50.0, 18.0) is True
    assert toggling.checked is True
    plain = menus.MenuItem("Sticks", checked=True)
    plain.press(5.0, 5.0, 0.0, 0.0, 50.0, 18.0)
    assert plain.checked is True


def test_a_nested_submenu_routes_a_press_to_the_inner_item():
    """A submenu overlaps its parent by design, so a press lands on both rows.

    The press is aimed squarely into that overlap band -- inside the inner
    ``Load`` row *and* inside the outer ``Recent`` row that opened it. Front to
    back, the inner one owns it; tested back to front, a nested menu can be seen
    and never clicked.
    """
    painter = RecordingPainter()
    inner_item = menus.MenuItem("Load")
    outer_item = menus.MenuItem("Load")
    submenu = menus.Menu("Recent", [inner_item])
    menu = menus.Menu("File", [outer_item, submenu])
    menu.set_viewport(400.0, 300.0)
    menu.open = True
    submenu.open = True
    menu.draw(painter, 0.0, 0.0, 60.0, 18.0)

    inner_rect = submenu._rows[0][1]
    outer_rect = menu._rows[1][1]
    at_x = inner_rect[0] + 1.0
    at_y = inner_rect[1] + inner_rect[3] * 0.5
    assert menus.style.hit(at_x, at_y, *inner_rect)
    assert menus.style.hit(at_x, at_y, *outer_rect)   # genuinely ambiguous

    result = menu.press(at_x, at_y, 0.0, 0.0, 60.0, 18.0)
    assert result.item is inner_item
    assert result.item is not outer_item
    assert menu.open is False and submenu.open is False


def test_pressing_a_submenu_row_opens_it_and_closes_its_sibling():
    """Two panels down the same column would sit on top of each other."""
    painter = RecordingPainter()
    first = menus.Menu("Recent", [menus.MenuItem("one.pdb")])
    second = menus.Menu("Export", [menus.MenuItem("png")])
    menu = menus.Menu("File", [first, second])
    menu.set_viewport(400.0, 300.0)
    menu.open = True
    first.open = True
    menu.draw(painter, 0.0, 0.0, 60.0, 18.0)

    row_x, row_y, row_w, row_h = menu._rows[1][1]
    result = menu.press(row_x + row_w * 0.5, row_y + row_h * 0.5, 0.0, 0.0, 60.0, 18.0)
    assert result.consumed and result.item is None
    assert second.open is True
    assert first.open is False


def test_a_press_outside_a_plain_popup_closes_it_and_passes_through():
    """The click that dismisses a popup still reaches what is behind it."""
    painter = RecordingPainter()
    popup = menus.Popup([menus.MenuItem("Copy")])
    popup.open_at(40.0, 40.0)
    popup.draw(painter, 0.0, 0.0, 400.0, 300.0)
    assert popup.contains(45.0, 45.0)

    result = popup.press(300.0, 250.0, 0.0, 0.0, 400.0, 300.0)
    assert result.closed is True
    assert result.consumed is False
    assert popup.open is False


def test_a_press_outside_a_modal_is_swallowed_and_leaves_it_open():
    """What modal means: nothing behind hears the click, and it does not close."""
    painter = RecordingPainter()
    modal = menus.PopupModal([menus.MenuItem("OK")], title="Really?")
    modal.open_at(40.0, 40.0)
    modal.draw(painter, 0.0, 0.0, 400.0, 300.0)

    result = modal.press(300.0, 250.0, 0.0, 0.0, 400.0, 300.0)
    assert result.consumed is True
    assert result.closed is False
    assert modal.open is True


def test_a_modal_lays_its_dim_wash_over_the_whole_viewport():
    """The wash is the only thing that says the rest of the app is not live."""
    painter = RecordingPainter()
    modal = menus.PopupModal([menus.MenuItem("OK")])
    modal.open_at(40.0, 40.0)
    modal.draw(painter, 0.0, 0.0, 400.0, 300.0)
    assert (0.0, 0.0, 400.0, 300.0, menus.style.MODAL_DIM_BG) in painter.fills

    plain = menus.Popup([menus.MenuItem("OK")])
    plain.open_at(40.0, 40.0)
    other = RecordingPainter()
    plain.draw(other, 0.0, 0.0, 400.0, 300.0)
    assert not any(fill[4] == menus.style.MODAL_DIM_BG for fill in other.fills)


def test_an_unopened_popup_draws_nothing_and_ignores_presses():
    """A closed popup is not a transparent one -- it is not there at all."""
    painter = RecordingPainter()
    popup = menus.Popup([menus.MenuItem("Copy")])
    popup.draw(painter, 0.0, 0.0, 400.0, 300.0)
    assert not painter.fills and not painter.strokes and not painter.strings
    assert popup.press(10.0, 10.0, 0.0, 0.0, 400.0, 300.0) == menus.PopupPress(
        None, False, False
    )


# ---------------------------------------------------------------------- #
# The bar
# ---------------------------------------------------------------------- #
def test_the_bar_picks_the_menu_whose_label_extent_contains_the_point():
    """Not an equal share of the strip: "File" and "Edit" are not equally long."""
    painter = RecordingPainter()
    bar = _bar()
    bar.set_viewport(400.0, 300.0)
    bar.draw(painter, 0.0, 0.0, 400.0, 18.0)

    file_menu, edit_menu = bar.menus
    file_rect = bar._titles[0][1]
    edit_rect = bar._titles[1][1]
    assert edit_rect[0] == pytest.approx(file_rect[0] + file_rect[2])

    bar.press(edit_rect[0] + 2.0, 9.0, 0.0, 0.0, 400.0, 18.0)
    assert edit_menu.open is True
    assert file_menu.open is False


def test_the_bar_closes_the_open_menu_when_another_title_is_pressed():
    """Two panels down at once is a bar that has lost track of itself."""
    painter = RecordingPainter()
    bar = _bar()
    bar.set_viewport(400.0, 300.0)
    bar.draw(painter, 0.0, 0.0, 400.0, 18.0)
    file_menu, edit_menu = bar.menus

    bar.press(bar._titles[0][1][0] + 2.0, 9.0, 0.0, 0.0, 400.0, 18.0)
    assert file_menu.open is True
    bar.draw(painter, 0.0, 0.0, 400.0, 18.0)
    bar.press(bar._titles[1][1][0] + 2.0, 9.0, 0.0, 0.0, 400.0, 18.0)
    assert file_menu.open is False and edit_menu.open is True


def test_a_press_in_the_scene_closes_the_bar_without_being_consumed():
    """A click in the viewport dismisses the menu and still rotates the molecule."""
    painter = RecordingPainter()
    bar = _bar()
    bar.set_viewport(400.0, 300.0)
    bar.menus[0].open = True
    bar.draw(painter, 0.0, 0.0, 400.0, 18.0)

    result = bar.press(350.0, 250.0, 0.0, 0.0, 400.0, 18.0)
    assert result.consumed is False
    assert bar.menus[0].open is False


def test_a_bar_press_reaches_an_item_in_an_open_panel_below_the_strip():
    """The panel hangs outside the strip, so the strip cannot gate the press."""
    painter = RecordingPainter()
    bar = _bar()
    bar.set_viewport(400.0, 300.0)
    file_menu = bar.menus[0]
    file_menu.open = True
    bar.draw(painter, 0.0, 0.0, 400.0, 18.0)

    open_item = file_menu.entries[0]
    row_x, row_y, row_w, row_h = file_menu._rows[0][1]
    assert row_y > 18.0
    result = bar.press(row_x + row_w * 0.5, row_y + row_h * 0.5, 0.0, 0.0, 400.0, 18.0)
    assert result.item is open_item
    assert file_menu.open is False


def test_a_disabled_menu_refuses_to_open():
    """Same rule as a disabled item, one level up."""
    menu = menus.Menu("Build", [menus.MenuItem("Fragment")], enabled=False)
    result = menu.press(10.0, 9.0, 0.0, 0.0, 60.0, 18.0)
    assert menu.open is False
    assert result.consumed is True


def test_a_separator_is_a_rule_and_never_takes_a_press():
    """It is a row with geometry, and nothing else."""
    painter = RecordingPainter()
    menu = menus.Menu("File", [menus.MenuItem("Open"), None, menus.MenuItem("Quit")])
    menu.viewport = (400.0, 300.0)
    menu.open = True
    menu.draw(painter, 0.0, 0.0, 60.0, 18.0)

    entries = [entry for entry, _rect in menu._rows]
    assert entries[1] is None
    _row_x, row_y, row_w, row_h = menu._rows[1][1]
    result = menu.press(_row_x + row_w * 0.5, row_y + row_h * 0.5, 0.0, 0.0, 60.0, 18.0)
    assert result.item is None
    assert result.consumed is True         # dead space inside the panel is still the panel's
    assert menu.open is True


def test_the_widest_submenu_label_is_not_cut_short():
    """A panel is sized to its widest label; laying a submenu row out again
    subtracts the same columns back and lands a hair under that width in
    floating point. ``fit_text`` then took the last letter off the widest
    entry -- "Export" in a File menu drew as "Expo." -- so it allows the slack."""
    from emtk.testing import PixelPainter
    from emtk.widgets.menus import Menu, MenuBar, MenuItem

    class _Strings(PixelPainter):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.strings = []

        def text(self, x, y, w, h, align, string, colour, bold=False):
            self.strings.append(string)
            return super().text(x, y, w, h, align, string, colour, bold)

    painter = _Strings(400, 300)
    bar = MenuBar([Menu("File", [MenuItem("Load"), MenuItem("Save"),
                                 Menu("Export", [MenuItem("Traces")]), MenuItem("Exit")])])
    bar.draw(painter, 0, 0, 400, 22)
    bar.press(10, 10, 0, 0, 400, 22)
    bar.draw(painter, 0, 0, 400, 22)
    assert "Export" in painter.strings
