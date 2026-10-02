"""The menu bar, driven the way a pointer drives it.

A menu's worth of clicks, in order: open, close by title, reopen, pick an
item, reopen, switch to the next menu on the same click that closes the
first, and a press that dismisses a menu landing on the control underneath.
The reopen cases are the reason this file exists: the dismissal state a menu
kept after closing made every later open close itself again on the frame it
opened, so a menu worked once and every click after that "did not land".
"""

from emtk import im
from emtk.im_core import IO
from emtk.testing import RecordingPainter


class _App:
    """One frame, a menu bar with two menus, and a button below the bar."""

    def __init__(self) -> None:
        self.storage: dict = {}
        self.io = IO()
        self.actions: list[str] = []
        self._painter = RecordingPainter()

    def gui(self) -> None:
        if im.begin_main_menu_bar():
            if im.begin_menu("File"):
                if im.menu_item("Save"):
                    self.actions.append("save")
                im.end_menu()
            if im.begin_menu("Run"):
                if im.menu_item("Go"):
                    self.actions.append("go")
                im.end_menu()
            im.end_main_menu_bar()
        if im.button("New"):
            self.actions.append("new")
        # Beyond the width a File menu's panel reaches: a control a
        # dismissing click can land on without hitting the popup itself.
        im.dummy(300.0, 0.0)
        im.same_line()
        if im.button("Far"):
            self.actions.append("far")

    def draw(self, box=(0, 0, 500, 300)) -> RecordingPainter:
        painter = RecordingPainter()
        with im.frame(painter, box, io=self.io, storage=self.storage):
            self.gui()
        return painter

    def press(self, x: float, y: float, box=(0, 0, 500, 300)) -> None:
        self.io.mouse_pos = (x, y)
        self.io.mouse_down[0] = True
        self.io.mouse_clicked[0] = True
        self.draw(box)
        self.io.mouse_clicked[0] = False
        self.io.mouse_down[0] = False
        self.io.mouse_released[0] = True
        self.draw(box)

    def settle(self) -> None:
        self.io.mouse_released[0] = False
        self.draw()

    def visible(self, label: str, box=(0, 0, 500, 300)) -> bool:
        self.settle()
        return label in self.draw(box).strings

    def title(self, label: str, box=(0, 0, 500, 300)) -> tuple[float, float]:
        for text in self.draw(box).texts:
            if text[5] == label:
                return (text[0] + 4.0, text[1] + 6.0)
        raise AssertionError(f"{label!r} is not on screen")

    def popup(self, label: str):
        state = self.storage.get(("__state__", ("context_popup", "##menu_items_" + label)), {})
        return state.get("popup")


def test_a_menu_reopens_after_its_own_title_closed_it():
    app = _App()
    file_at = app.title("File")
    app.press(*file_at)
    assert app.visible("Save")
    app.press(*file_at)
    assert not app.visible("Save")
    app.press(*file_at)
    assert app.visible("Save"), "a closed menu must open again"


def test_a_menu_reopens_after_an_item_was_picked():
    app = _App()
    file_at = app.title("File")
    app.press(*file_at)
    save_at = app.title("Save")
    app.press(*save_at)
    assert app.actions == ["save"]
    if app.visible("Save"):
        app.press(*file_at)
    app.press(*file_at)
    assert app.visible("Save"), "a picked menu must open again"


def test_one_click_moves_an_open_menu_to_another_title():
    app = _App()
    file_at = app.title("File")
    run_at = app.title("Run")
    app.press(*file_at)
    app.press(*run_at)
    assert "go" not in app.actions
    assert app.visible("Go"), "the click that closes one menu opens the next"
    assert not app.visible("Save")


def test_a_dismissing_press_reaches_the_control_under_it():
    app = _App()
    file_at = app.title("File")
    far_at = app.title("Far")
    app.press(*file_at)
    app.press(*far_at)
    assert app.actions == ["far"], "the control under the dismissed menu fires"
    assert not app.visible("Save")


def test_picking_then_switching_still_lands():
    """A pick, a switch and a dismissal in sequence, nothing sticking."""
    app = _App()
    file_at = app.title("File")
    run_at = app.title("Run")
    app.press(*file_at)
    save_at = app.title("Save")
    app.press(*save_at)
    app.press(*file_at)
    assert app.visible("Save")
    app.press(*run_at)
    assert app.visible("Go")
    go_at = app.title("Go")
    app.press(*go_at)
    assert app.actions == ["save", "go"]
    app.press(*run_at)
    assert app.visible("Go"), "the second pick must not wedge the menu"


def test_a_reopened_menu_anchors_where_its_title_is_now():
    """The reused panel opens under the title's *current* position.

    The panel object survives a close; an anchor kept from its last open
    made a menu that had been opened once open again where the title used
    to be -- visible the moment the window or its docks move between the
    two opens.
    """
    app = _App()
    file_at = app.title("File")
    app.press(*file_at)
    assert app.visible("Save")
    app.press(*file_at)
    assert not app.visible("Save")

    shifted = (60, 0, 500, 300)  # the frame grew a left-hand dock
    moved_at = app.title("File", box=shifted)
    app.press(*moved_at, box=shifted)
    popup = app.popup("File")
    assert popup is not None and popup.open
    stored = app.storage.get(
        ("__state__", ("context_popup", "##menu_items_File")), {}
    ).get("position")
    assert popup.anchor == stored, "the reopened menu kept its previous anchor"
    assert popup.anchor[0] > 0, "the anchor did not follow the moved title"
    assert app.visible("Save", box=shifted)


def test_a_pick_survives_the_menus_items_changing():
    """The pick dispatches the row it named, not its old position.

    Run's first row flips between "Run Script" and "Stop" the moment a
    script starts. The pick was remembered as an index, so starting a
    script from the menu dispatched "Stop" on the next frame -- the script
    started and stopped in one click.
    """
    app = _App()
    running = []

    def gui() -> None:
        if im.begin_main_menu_bar():
            if im.begin_menu("Run"):
                if running:
                    if im.menu_item("Stop"):
                        running.clear()
                else:
                    if im.menu_item("Run Script"):
                        running.append(True)
                im.end_menu()
            im.end_main_menu_bar()

    original = _App.gui

    def draw(self, box=(0, 0, 500, 300)):
        painter = RecordingPainter()
        with im.frame(painter, box, io=self.io, storage=self.storage):
            gui()
        return painter

    _App.gui = gui
    _App.draw = draw
    try:
        run_at = app.title("Run")
        app.press(*run_at)
        item_at = app.title("Run Script")
        app.press(*item_at)
        app.settle()
        assert running == [True], "the pick did not start the script"
        app.press(*run_at)
        app.settle()
        assert app.visible("Stop"), "the menu now offers Stop"
        stop_at = app.title("Stop")
        app.press(*stop_at)
        app.settle()
        assert running == [], "the pick did not stop the script"
    finally:
        _App.gui = original
