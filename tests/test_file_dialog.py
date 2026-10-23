"""``emtk.file_dialog`` -- choosing files, with no host dialog and no window.

A native dialog cannot be driven by a test and does not exist in a browser, so
these drive the emtk one the way a user does: by clicking the names it draws.
"""
from __future__ import annotations

import os

import pytest

import emtk
from emtk.file_dialog import FileDialog, parse_filters
from emtk.testing import RecordingPainter


@pytest.fixture
def folder(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / ".hidden.dat").write_text("x")
    for name in ("a.dat", "b.DAT", "c.json.gz", "d.mat", "notes.txt"):
        (tmp_path / name).write_text("x")
    return tmp_path


class _Driver:
    """Draws a dialog frame by frame and clicks on the text it drew."""

    def __init__(self, dialog):
        self.dialog = dialog
        self.io, self.storage = emtk.IO(), {}
        self.painter = None
        self.result = None

    def frame(self):
        self.painter = RecordingPainter()
        with emtk.frame(self.painter, (0.0, 0.0, 600.0, 520.0), io=self.io,
                        storage=self.storage):
            emtk.begin("dialog", (0.0, 0.0, 600.0, 520.0))
            self.result = self.dialog.draw()
            emtk.end()
        return self.result

    def where(self, string):
        for x, y, w, h, _align, text, *_rest in self.painter.texts:
            if text == string:
                return (x + 3.0, y + h / 2.0)
        raise AssertionError(f"{string!r} was not drawn: {self.painter.strings}")

    def click(self, string, double=False):
        self.frame()
        pos = self.where(string)
        io = self.io
        io.mouse_pos = io.mouse_clicked_pos[0] = pos
        io.mouse_down[0] = io.mouse_clicked[0] = True
        io.mouse_double_clicked[0] = double
        self.frame()
        io.mouse_down[0] = False
        io.mouse_released[0] = True
        return self.frame()


def test_a_filter_string_splits_like_qts():
    assert parse_filters("Sessions (*.mat);;SMD (*.json *.json.gz)") == [
        ("Sessions", ["*.mat"]), ("SMD", ["*.json", "*.json.gz"])]


def test_save_existing_file_requires_explicit_replacement(folder):
    dialog = FileDialog(mode="save", directory=str(folder), filename="a.dat")
    driver = _Driver(dialog)
    assert driver.click("Save") is None
    assert dialog._pending_overwrite == [str(folder / "a.dat")]
    assert driver.click("Choose another name") is None
    assert dialog._pending_overwrite is None
    assert (folder / "a.dat").read_text() == "x"
    assert driver.click("Save") is None
    assert driver.click("Replace existing file") == [str(folder / "a.dat")]
    assert dialog.overwrite_confirmed
    assert parse_filters("") == [("All files", ["*"])]


def test_the_listing_is_filtered_case_insensitively_and_hides_dotfiles(folder):
    dialog = FileDialog(filters=[("Raw (.dat)", ["*.dat"]), ("SMD (.json.gz)", ["*.json.gz"])],
                        directory=str(folder))
    dialog.refresh()
    assert dialog.folders == ["sub"]
    assert dialog.files == ["a.dat", "b.DAT"]
    dialog.filter_index = 1
    dialog.refresh()
    assert dialog.files == ["c.json.gz"], "a compound extension must match as a glob"


def test_clicking_a_file_and_open_returns_its_path(folder):
    dialog = FileDialog(filters=[("Raw (.dat)", ["*.dat"])], directory=str(folder))
    drive = _Driver(dialog)
    drive.click("a.dat")
    assert dialog.selection == ["a.dat"]
    assert drive.click("Open") == [os.path.join(str(folder), "a.dat")]


def test_multiselect_toggles_and_returns_every_selected_path(folder):
    dialog = FileDialog(filters=[("Raw (.dat)", ["*.dat"])], directory=str(folder),
                        multiselect=True)
    drive = _Driver(dialog)
    drive.click("a.dat")
    drive.click("b.DAT")
    drive.click("a.dat")
    drive.click("a.dat")
    assert sorted(drive.click("Open")) == sorted(
        [os.path.join(str(folder), "a.dat"), os.path.join(str(folder), "b.DAT")])


def test_open_with_nothing_selected_says_so_instead_of_returning(folder):
    dialog = FileDialog(directory=str(folder))
    drive = _Driver(dialog)
    assert drive.click("Open") is None
    assert dialog.error


def test_cancel_returns_false(folder):
    drive = _Driver(FileDialog(directory=str(folder)))
    assert drive.click("Cancel") is False


def test_folders_are_entered_and_left(folder):
    dialog = FileDialog(directory=str(folder))
    drive = _Driver(dialog)
    drive.click("[sub]")
    assert dialog.directory == str(folder / "sub")
    drive.click("[..]")
    assert dialog.directory == str(folder)


def test_save_appends_the_filters_extension(folder):
    dialog = FileDialog("Save", mode="save", filters=[("Session (.mat)", ["*.mat"])],
                        directory=str(folder), filename="session")
    assert dialog.chosen() == [os.path.join(str(folder), "session.mat")]
    dialog.filename = "other.mat"
    assert dialog.chosen() == [os.path.join(str(folder), "other.mat")]
    drive = _Driver(dialog)
    assert drive.click("Save") == [os.path.join(str(folder), "other.mat")]


def test_a_double_click_takes_the_file(folder):
    dialog = FileDialog(filters=[("Session (.mat)", ["*.mat"])], directory=str(folder))
    drive = _Driver(dialog)
    drive.frame()
    pos = drive.where("d.mat")
    drive.io.mouse_pos = drive.io.mouse_clicked_pos[0] = pos
    drive.io.mouse_down[0] = drive.io.mouse_clicked[0] = True
    drive.io.mouse_double_clicked[0] = True
    assert drive.frame() == [os.path.join(str(folder), "d.mat")]


def test_long_listings_page(tmp_path):
    for i in range(30):
        (tmp_path / f"f{i:02d}.dat").write_text("x")
    dialog = FileDialog(directory=str(tmp_path), rows=10)
    drive = _Driver(dialog)
    drive.frame()
    assert "f00.dat" in drive.painter.strings and "f20.dat" not in drive.painter.strings
    drive.click("next >")
    drive.click("next >")
    drive.frame()      # the button fires on release, after that frame's listing
    assert "f20.dat" in drive.painter.strings


def test_folder_mode_lists_folders_and_takes_the_one_selected(folder):
    (folder / "sub" / "inner").mkdir()
    dialog = FileDialog("Burst analysis folder", mode="folder", directory=str(folder))
    driver = _Driver(dialog)
    driver.frame()
    assert "a.dat" not in driver.painter.strings
    assert "[sub]" in driver.painter.strings and "Choose" in driver.painter.strings
    driver.click("[sub]")
    assert dialog.selection == ["sub"]
    assert driver.click("Choose") == [str(folder / "sub")]


def test_folder_mode_takes_the_folder_shown_when_none_is_selected(folder):
    dialog = FileDialog("Working path", mode="folder", directory=str(folder))
    driver = _Driver(dialog)
    driver.click("[sub]", double=True)                  # a double click enters
    assert dialog.directory == str(folder / "sub")
    assert driver.click("Choose") == [str(folder / "sub")]


def test_folder_mode_refuses_a_folder_that_went_away(folder):
    dialog = FileDialog("x", mode="folder", directory=str(folder))
    dialog.selection = ["gone"]
    assert dialog.choose() is None and dialog.error == "No such folder."


def test_a_click_that_navigates_away_does_not_hold_the_pointer(folder):
    """The entered folder's entry is gone on the release; the next click works."""
    dialog = FileDialog("Open", directory=str(folder))
    driver = _Driver(dialog)
    driver.click("[sub]")
    assert dialog.directory == str(folder / "sub")
    driver.click("[..]")
    assert dialog.directory == str(folder)


def test_the_save_name_field_is_drawn_across_the_dialog(folder):
    """``set_next_item_width(-1)`` is "to the right edge": the name field used
    to get a negative width and was not drawn at all."""
    dialog = FileDialog("Save", mode="save", filters=[("PNG", ["*.png"])],
                        directory=str(folder), filename="shot.png")
    driver = _Driver(dialog)
    driver.frame()
    calls = driver.painter.calls
    at = next(i for i, call in enumerate(calls) if "shot.png" in call)
    clip = next(call for call in reversed(calls[:at]) if call[0] == "push_clip")
    assert clip[3] > 400.0, clip


def test_a_negative_row_width_is_measured_from_the_right_edge():
    from emtk.layout import Layout

    layout = Layout(RecordingPainter(), 10.0, 0.0, 200.0, 100.0)
    x, _y, w, _h = layout.row(width=-1.0)
    assert x == 10.0 and w == 199.0


def test_a_dialog_on_a_page_opens_where_the_files_are(tmp_path, monkeypatch):
    """No ``directory`` given: the page's user-files folder wins over cwd.

    A dialog that opened in the virtual home listed an empty filesystem and
    gave a user who had just dropped a file nowhere to click.
    """
    from emtk import file_dialog

    mount = tmp_path / "local" / "my-data"
    mount.mkdir(parents=True)
    monkeypatch.setattr(file_dialog, "_default_start_directory", lambda: str(mount))
    dialog = file_dialog.FileDialog()
    assert dialog.directory == str(mount)


def test_a_dialog_on_a_page_says_how_files_arrive(folder, monkeypatch):
    """On a page the dialog tells the user how files get into it.

    The hint must be drawn, not just exist: a user staring at an empty
    virtual filesystem needs the way forward inside the dialog itself.
    """
    from emtk import file_dialog
    from emtk.web import page as web_page

    monkeypatch.setattr(web_page, "ON_PAGE", True)
    hint = file_dialog._local_files_hint()
    assert hint and hint.lower().startswith("drop files")

    dialog = FileDialog(directory=str(folder))
    drive = _Driver(dialog)
    drive.frame()
    assert any(hint in text for x, y, w, h, _a, text, *_r in drive.painter.texts), (
        f"the hint was not drawn: {drive.painter.strings}")


def test_a_dialog_on_a_desktop_stays_quiet(monkeypatch):
    """Not on a page: no hint, no surprise text in the dialog."""
    from emtk import file_dialog
    from emtk.web import page as web_page

    monkeypatch.setattr(web_page, "ON_PAGE", False)
    assert file_dialog._local_files_hint() is None


def test_on_a_page_an_open_dialog_offers_the_computer(folder, monkeypatch):
    """A dialog that can reach the browser's file picker says so on its face.

    The page's files were reachable only by dropping or mounting; the dialog
    itself offered no way to a file on the user's computer. On a page it does.
    """
    from emtk import file_dialog
    from emtk.web import page as web_page

    dialog = file_dialog.FileDialog(directory=str(folder))
    driver = _Driver(dialog)
    monkeypatch.setattr(web_page, "ON_PAGE", False)
    driver.frame()
    assert "Load from computer…" not in driver.painter.strings
    monkeypatch.setattr(web_page, "ON_PAGE", True)
    driver.frame()
    assert "Load from computer…" in driver.painter.strings
    # a save dialog keeps its name field instead -- picking is for reading
    save = file_dialog.FileDialog(mode="save", directory=str(folder))
    save_driver = _Driver(save)
    save_driver.frame()
    assert "Load from computer…" not in save_driver.painter.strings


def test_a_pick_from_the_computer_lands_selected(folder, monkeypatch):
    """Choose in the browser's sheet: the dialog shows the file, chosen.

    The pick's files land in the page's user-files folder; the dialog switches
    there, preselects what was picked, and Open returns its path -- the user
    never has to know a virtual filesystem exists.
    """
    from emtk import file_dialog
    from emtk.web import page as web_page

    picked = folder / "picked.csv"
    picked.write_text("x,y\n")
    results = iter(["waiting", (str(folder), ["picked.csv"]), (str(folder), ["picked.csv"])])

    monkeypatch.setattr(web_page, "ON_PAGE", True)
    monkeypatch.setattr(web_page, "start_local_pick", lambda accept=None: True)
    monkeypatch.setattr(web_page, "local_pick_result", lambda: next(results))

    dialog = file_dialog.FileDialog(directory=str(folder))
    driver = _Driver(dialog)
    driver.click("Load from computer…")
    assert dialog._pick_pending and dialog.selection == []
    driver.frame()  # waiting: the sheet is up, the dialog keeps drawing
    assert dialog._pick_pending
    driver.frame()  # done: the file is here and chosen
    assert not dialog._pick_pending
    assert dialog.directory == str(folder)
    assert dialog.selection == ["picked.csv"]
    assert driver.click("Open") == [str(picked)]


def test_a_cancelled_pick_keeps_the_dialog_as_it_was(folder, monkeypatch):
    """Closing the browser's sheet without a choice changes nothing."""
    from emtk import file_dialog
    from emtk.web import page as web_page

    monkeypatch.setattr(web_page, "ON_PAGE", True)
    monkeypatch.setattr(web_page, "start_local_pick", lambda accept=None: True)
    monkeypatch.setattr(web_page, "local_pick_result", lambda: "cancel")

    dialog = file_dialog.FileDialog(directory=str(folder))
    driver = _Driver(dialog)
    driver.click("Load from computer…")
    result = driver.frame()
    assert not dialog._pick_pending
    assert dialog.selection == []
    assert result is None  # the dialog stays open, unharmed


def test_the_address_bar_jumps_to_a_pasted_path(folder, monkeypatch):
    """Return in the address bar goes where the pasted path says.

    The dialog drew its folder as text a user could neither copy from nor
    paste into; a path from anywhere else -- a shell, a mail, a note -- had to
    be clicked together folder by folder. The field takes it, and Return
    shows the folder or selects the file.
    """
    from emtk import file_dialog

    target = folder / "bursts" / "set.csv"
    target.parent.mkdir()
    target.write_text("x\n")

    dialog = file_dialog.FileDialog(directory=str(folder))
    driver = _Driver(dialog)

    # a file path: Return selects the file in its folder
    monkeypatch.setattr(file_dialog._w, "input_text",
                        lambda *a, **k: (True, str(target)))
    driver.frame()
    assert dialog.directory == str(target.parent)
    assert dialog.selection == ["set.csv"]
    assert dialog.error == ""

    # a relative name resolves against the folder being shown
    monkeypatch.setattr(file_dialog._w, "input_text", lambda *a, **k: (True, "bursts"))
    driver.frame()
    assert dialog.directory == str(folder / "bursts")

    # a path that is nothing is said, not silently ignored
    monkeypatch.setattr(file_dialog._w, "input_text",
                        lambda *a, **k: (True, str(folder / "nope.csv")))
    driver.frame()
    assert "nope.csv" in dialog.error
    assert dialog.directory == str(folder / "bursts")  # untouched


def test_the_address_bar_shows_the_folder_and_the_field_keeps_the_edit(folder):
    """The field carries the shown folder, and an edit is not stamped over.

    The user types half a path; the frame redraws for a blink elsewhere. The
    buffer is theirs until the shown folder actually moves.
    """
    from emtk import file_dialog

    sub = folder / "sub"
    sub.mkdir(exist_ok=True)
    dialog = file_dialog.FileDialog(directory=str(folder))
    driver = _Driver(dialog)
    driver.frame()
    assert dialog._path_edit == str(folder)
    dialog._path_edit = "/a/path/half-typed"
    driver.frame()  # a redraw with the folder unchanged
    assert dialog._path_edit == "/a/path/half-typed"
    dialog._jump_to(str(sub))
    driver.frame()  # the folder moved: the field follows it again
    assert dialog._path_edit == str(sub)


def test_copy_path_puts_the_chosen_path_on_the_clipboard(folder, monkeypatch):
    """The button copies what is chosen -- the folder when nothing is."""
    from emtk import file_dialog

    (folder / "a.dat").write_text("x")
    dialog = file_dialog.FileDialog(directory=str(folder))
    driver = _Driver(dialog)
    captured = []
    monkeypatch.setattr(file_dialog._w, "set_clipboard_text", captured.append)
    driver.frame()
    driver.click("Copy path")
    assert captured == [str(folder)]
    driver.click("a.dat")
    driver.click("Copy path")
    assert captured[-1] == str(folder / "a.dat")
    dialog.mode = "save"
    dialog.filename = "out"
    monkeypatch.setattr(file_dialog._w, "input_text", lambda *a, **k: (False, "out"))
    driver.frame()
    driver.click("Copy path")
    assert captured[-1] == str(folder / "out")
    # the note that it copied is drawn, not only felt
    dialog._copied_frames = 2
    driver.frame()
    assert "path copied." in driver.painter.strings


def _in_browser(monkeypatch, on: bool = True):
    """Pretend we run (or don't run) under Pyodide for the rest of the test."""
    import emtk.file_dialog as fd

    monkeypatch.setattr(fd, "_in_browser", lambda: on)


class TestAutoPick:
    """On a page, a dialog with nothing to offer opens the browser's file sheet."""

    @pytest.fixture
    def pick_calls(self, monkeypatch):
        calls = []
        import emtk.web.page as page

        monkeypatch.setattr(page, "start_local_pick",
                            lambda accept=None: calls.append(accept) or True)
        return calls

    def test_an_empty_listing_starts_the_pick(self, monkeypatch, tmp_path, pick_calls):
        _in_browser(monkeypatch)
        dialog = FileDialog(directory=str(tmp_path), filters=[("Data", ["*.dat"])])
        assert dialog.should_auto_pick() is True
        dialog._maybe_auto_pick()
        assert pick_calls == [".dat"] and dialog._pick_pending  # the filter's accept

    def test_a_listing_with_matches_does_not(self, monkeypatch, tmp_path, pick_calls):
        _in_browser(monkeypatch)
        (tmp_path / "x.dat").write_text("x")
        dialog = FileDialog(directory=str(tmp_path), filters=[("Data", ["*.dat"])])
        dialog.refresh()
        assert dialog.should_auto_pick() is False
        dialog._maybe_auto_pick()
        assert pick_calls == []

    def test_the_pick_starts_once_per_open(self, monkeypatch, tmp_path, pick_calls):
        _in_browser(monkeypatch)
        dialog = FileDialog(directory=str(tmp_path))
        dialog._maybe_auto_pick()
        dialog._maybe_auto_pick()
        assert len(pick_calls) == 1
        dialog.open()  # a host showing it again gets a fresh pick
        dialog._maybe_auto_pick()
        assert len(pick_calls) == 2

    def test_auto_pick_true_starts_even_with_matches(self, monkeypatch, tmp_path, pick_calls):
        _in_browser(monkeypatch)
        (tmp_path / "x.dat").write_text("x")
        dialog = FileDialog(directory=str(tmp_path), auto_pick=True)
        dialog.refresh()
        assert dialog.should_auto_pick() is True

    def test_auto_pick_false_never_starts(self, tmp_path, pick_calls):
        dialog = FileDialog(directory=str(tmp_path), auto_pick=False)
        assert dialog.should_auto_pick() is False
        dialog._maybe_auto_pick()
        assert pick_calls == []

    def test_save_and_folder_dialogs_never_pick(self, tmp_path, pick_calls):
        for mode in ("save", "folder"):
            dialog = FileDialog(mode=mode, directory=str(tmp_path))
            assert dialog.should_auto_pick() is False


def test_on_the_desktop_no_dialog_opens_a_picker_on_its_own(monkeypatch, tmp_path):
    """Native: the listing is where browsing starts; the picker is a click."""
    _in_browser(monkeypatch, on=False)
    import emtk.file_dialog as fd

    calls = []
    monkeypatch.setattr(fd, "_module_start_local_pick",
                        lambda accept=None: calls.append(accept) or True)
    d = fd.FileDialog("Open", mode="open", directory=str(tmp_path), filters=[("Data", ["*.dat"])])
    d.open()
    assert d.should_auto_pick() is False and calls == []
    # on a page the same dialog would have started the sheet
    _in_browser(monkeypatch)
    assert d._pick_tried is False  # nothing tried yet on the desktop
