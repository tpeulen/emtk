"""``emtk.file_dialog`` -- choose files to open or a file to save, inside a frame.

Dear ImGui has no file dialog; applications either reach for the host's native
one or draw their own. Three emtk applications had each drawn their own, and a
fourth was about to. The native dialog is not an answer for emtk: a browser
host has none, and a test that has to press *Load* cannot drive one. So this is
the one drawn by emtk itself, with the immediate-mode shape every other widget
has -- it is a panel body, called every frame between ``begin`` and ``end``:

.. code-block:: python

    dialog = FileDialog("Load", filters=[("Raw time series (.dat)", ["*.dat"]),
                                          ("SMD (.json.gz)", ["*.json.gz"])],
                        multiselect=True)
    ...
    im.begin("Load")
    result = dialog.draw()
    im.end()
    if result:          # a list of paths
        load(result, dialog.filter_index)
    elif result is False:
        close()

The interaction model is L2DFileDialog's (Limeoats, Apache-2.0): folders
first with ``..`` to go up, a click selects, a double click enters a folder or
takes a file, a line shows what will be chosen, and Cancel / the action button
sit at the bottom with an error line when the action is pressed with nothing
chosen. Added, because the applications that need a dialog need them: the
filter chooser MATLAB's ``uigetfile`` and Qt's ``getOpenFileName`` both have
(its index comes back as :attr:`FileDialog.filter_index`, which is how a caller
tells a ``.mat`` session from a ``.mat`` dataset), multi-selection, and a
file-name field in save mode that appends the filter's extension, and a
folder mode -- Qt's ``getExistingDirectory`` -- for an application that opens
a folder rather than a file (a burst-analysis folder, a working folder).
"""
from __future__ import annotations

import fnmatch
import os
from collections.abc import Sequence

from . import im_core as _core
from . import im_widgets as _w

__all__ = ["FileDialog", "parse_filters"]

#: The error line's colour, L2D's ``ImColor(1.0f, 0.0f, 0.2f)``.
ERROR_COLOUR = (255, 0, 51, 255)


def parse_filters(spec: str) -> list[tuple[str, list[str]]]:
    """Split a Qt-style filter string into ``(label, patterns)`` pairs.

    Parameters
    ----------
    spec : str
        ``"Sessions (*.mat);;All files (*)"``.

    Returns
    -------
    list of tuple
        ``[("Sessions", ["*.mat"]), ("All files", ["*"])]``. A section with no
        parenthesised patterns is dropped; an empty result is ``All files``.
    """
    sections: list[tuple[str, list[str]]] = []
    for section in str(spec or "").split(";;"):
        if "(" not in section or ")" not in section:
            continue
        label = section[: section.rindex("(")].strip()
        body = section[section.rindex("(") + 1: section.rindex(")")]
        patterns = [part.strip() for part in body.split() if part.strip()]
        if label and patterns:
            sections.append((label, patterns))
    return sections or [("All files", ["*"])]


class FileDialog:
    """A file chooser drawn by emtk.

    Parameters
    ----------
    title : str
        What the dialog is for; also the action button's caption when
        ``action`` is not given.
    mode : {"open", "save", "folder"}
        Choose existing files, name one to write, or choose a folder. In
        folder mode only folders are listed: a click selects one, a double
        click enters it, and the action takes the selected folder -- or the
        folder being shown when none is selected.
    filters : sequence of (str, sequence of str), or str
        ``(label, patterns)`` pairs, or a Qt-style filter string. Patterns are
        shell globs matched case-insensitively against the file *name*, so a
        compound extension (``*.json.gz``) works.
    directory : str, optional
        Where to start. Falls back to the home folder when it does not exist.
    filename : str, optional
        Initial name in save mode.
    multiselect : bool
        In open mode, a click toggles a file in and out of the selection.
    action : str, optional
        Caption of the action button (``"Open"`` / ``"Save"`` by default).
    rows : int
        Entries per page.

    Attributes
    ----------
    directory : str
        The folder being shown.
    filter_index : int
        Which filter is selected -- the third output of ``uigetfile``.
    selection : list of str
        Selected file names in :attr:`directory`.
    filename : str
        The save-mode name field.
    error : str
        Shown in red under the buttons; cleared by the next successful choice.
    """

    def __init__(self, title: str = "Open", mode: str = "open",
                 filters: Sequence | str = (("All files", ("*",)),),
                 directory: str | None = None, filename: str = "",
                 multiselect: bool = False, action: str | None = None,
                 rows: int = 12) -> None:
        if mode not in ("open", "save", "folder"):
            raise ValueError(f"mode must be 'open', 'save' or 'folder', not {mode!r}")
        self.title = title
        self.mode = mode
        self.filters = (parse_filters(filters) if isinstance(filters, str)
                        else [(str(label), [str(p) for p in patterns])
                              for label, patterns in filters]) or [("All files", ["*"])]
        self.filter_index = 0
        start = os.path.abspath(os.path.expanduser(directory or os.getcwd()))
        self.directory = start if os.path.isdir(start) else os.path.expanduser("~")
        self.filename = filename
        self.multiselect = bool(multiselect) and mode == "open"
        self.action = action or {"save": "Save", "folder": "Choose"}.get(mode, "Open")
        self.rows = max(1, int(rows))
        self.selection: list[str] = []
        self.error = ""
        self.page = 0
        self.folders: list[str] = []
        self.files: list[str] = []
        self._listed: tuple | None = None

    # -- the model, usable without drawing ----------------------------------- #
    def refresh(self) -> None:
        """Re-read :attr:`directory` when it or the filter changed.

        Hidden entries (a leading dot) are left out. An unreadable folder
        lists nothing and says why in :attr:`error` rather than raising in the
        middle of a frame.
        """
        key = (self.directory, self.filter_index)
        if self._listed == key:
            return
        folders, files = [], []
        try:
            names = sorted(os.listdir(self.directory), key=str.lower)
        except OSError as exc:
            names = []
            self.error = str(exc)
        for name in names:
            if name.startswith("."):
                continue
            if os.path.isdir(os.path.join(self.directory, name)):
                folders.append(name)
            elif self.mode != "folder" and self.matches(name):
                files.append(name)
        self.folders, self.files = folders, files
        keep = folders if self.mode == "folder" else files
        self.selection = [name for name in self.selection if name in keep]
        if self._listed is None or self._listed[0] != self.directory:
            self.page = 0
        self._listed = key

    def matches(self, name: str) -> bool:
        """Whether *name* passes the selected filter.

        Parameters
        ----------
        name : str
            A file name, without its folder.

        Returns
        -------
        bool
        """
        patterns = self.filters[self.filter_index][1]
        lowered = name.lower()
        return any(fnmatch.fnmatch(lowered, pattern.lower()) for pattern in patterns)

    def enter(self, folder: str) -> None:
        """Show *folder*: a name in :attr:`directory`, or ``".."`` for up.

        Parameters
        ----------
        folder : str
            Folder name or ``".."``.
        """
        target = (os.path.dirname(self.directory) if folder == ".."
                  else os.path.join(self.directory, folder))
        if os.path.isdir(target):
            self.directory = os.path.abspath(target)
            self.selection = []
            self.refresh()

    def select(self, name: str) -> None:
        """Click on the file *name*: select it, or toggle it in multi-select.

        Parameters
        ----------
        name : str
            A file in the current listing.
        """
        if self.multiselect:
            if name in self.selection:
                self.selection.remove(name)
            else:
                self.selection.append(name)
        else:
            self.selection = [name]
        if self.mode == "save":
            self.filename = name

    def chosen(self) -> list[str]:
        """The absolute paths the action button would return.

        In save mode this is the name field, with the selected filter's
        extension appended when the name has none of the filter's patterns --
        the ``uiputfile`` behaviour, and what stops ``session`` being written
        where ``session.mat`` was meant.

        Returns
        -------
        list of str
            Empty when nothing is chosen.
        """
        if self.mode == "save":
            name = self.filename.strip()
            if not name:
                return []
            if not self.matches(name):
                for pattern in self.filters[self.filter_index][1]:
                    if pattern.startswith("*.") and "*" not in pattern[2:]:
                        name += pattern[1:]
                        break
            return [os.path.join(self.directory, name)]
        if self.mode == "folder" and not self.selection:
            return [self.directory]
        return [os.path.join(self.directory, name) for name in self.selection]

    def choose(self) -> list[str] | None:
        """Press the action button.

        Returns
        -------
        list of str or None
            The chosen paths, or ``None`` with :attr:`error` set when nothing
            usable is chosen.
        """
        paths = self.chosen()
        if not paths:
            self.error = ("Enter a file name." if self.mode == "save"
                          else "Select a file first.")
            return None
        if self.mode == "open" and not all(os.path.isfile(p) for p in paths):
            self.error = "No such file."
            return None
        if self.mode == "folder" and not all(os.path.isdir(p) for p in paths):
            self.error = "No such folder."
            return None
        self.error = ""
        return paths

    # -- the panel ----------------------------------------------------------- #
    def draw(self) -> list[str] | bool | None:
        """Draw the dialog body into the current window.

        Returns
        -------
        list of str, False or None
            The chosen paths on the frame the action is taken, ``False`` on
            the frame Cancel is pressed, ``None`` while the dialog stays open.
        """
        self.refresh()
        result: list[str] | bool | None = None

        _w.text_disabled(self.directory)
        _w.separator()

        entries = [("..", True)] + [(n, True) for n in self.folders] + \
                  [(n, False) for n in self.files]
        pages = max(1, (len(entries) + self.rows - 1) // self.rows)
        self.page = min(self.page, pages - 1)
        start = self.page * self.rows
        for name, is_folder in entries[start:start + self.rows]:
            if is_folder and self.mode == "folder" and name != "..":
                picked = _w.selectable(f"[{name}]##folder:{name}", name in self.selection)
                if _w.is_item_hovered() and _w.is_mouse_double_clicked(0):
                    self.enter(name)
                    return None
                if picked:
                    self.selection = [name]
            elif is_folder:
                label = f"[{name}]##folder:{name}"
                if _w.selectable(label, False):
                    self.enter(name)
                    return None
            else:
                picked = _w.selectable(f"{name}##file:{name}", name in self.selection)
                # A double click is seen on the *press*, while a selectable
                # reports its click on the release -- so the two are separate
                # tests, as ImGui's ``AllowDoubleClick`` makes them.
                if _w.is_item_hovered() and _w.is_mouse_double_clicked(0):
                    self.selection = [name]
                    if self.mode == "save":
                        self.filename = name
                    result = self.choose()
                elif picked:
                    self.select(name)
        for _ in range(self.rows - len(entries[start:start + self.rows])):
            _w.dummy(1.0, _core.get_frame_height())
        if pages > 1:
            if _w.small_button("< prev") and self.page > 0:
                self.page -= 1
            _w.same_line()
            _w.text_disabled(f"page {self.page + 1} / {pages}")
            _w.same_line()
            if _w.small_button("next >") and self.page < pages - 1:
                self.page += 1
        _w.separator()

        if self.mode == "save":
            _w.set_next_item_width(-1.0)
            _changed, name = _w.input_text("##file-dialog-name", self.filename, "file name")
            self.filename = name.replace("\r", "").replace("\n", "")
        elif self.mode == "folder":
            _w.text_disabled(self.chosen()[0])
        else:
            shown = ", ".join(self.selection) if self.selection else "(nothing selected)"
            _w.text_disabled(shown)

        if self.mode != "folder":
            labels = [label for label, _patterns in self.filters]
            changed, index = _w.combo("##file-dialog-filter", self.filter_index, labels)
            if changed and index != self.filter_index:
                self.filter_index = index
                self.refresh()

        if _w.button(self.action, (90.0, 0.0)):
            result = self.choose()
        _w.same_line()
        if _w.button("Cancel", (90.0, 0.0)):
            result = False
        if self.error:
            _w.text_colored(ERROR_COLOUR, self.error)
        return result
