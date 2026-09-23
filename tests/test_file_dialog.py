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
