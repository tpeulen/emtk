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
import sys
from collections.abc import Sequence

from . import im_core as _core

def _in_browser() -> bool:
    """True under Pyodide, where 'load from computer' is the platform picker."""
    return sys.platform == "emscripten" or "pyodide" in sys.modules


def _module_start_local_pick(accept: str | None) -> bool:
    """Module-level seam over ``emtk.web.page.start_local_pick`` for tests."""
    try:
        from emtk.web.page import start_local_pick  # noqa: PLC0415
    except Exception:  # noqa: BLE001 - off a page there is nothing to start
        return False
    return bool(start_local_pick(accept))

from . import im_widgets as _w
from .flags import InputTextFlags as _ITF
from .i18n import mark, tr

__all__ = ["FileDialog", "parse_filters"]

#: The error line's colour, L2D's ``ImColor(1.0f, 0.0f, 0.2f)``.
ERROR_COLOUR = (255, 0, 51, 255)
#: A file dialog's local-files hint: present, but quieter than an error.
HINT_COLOUR = (170, 170, 180, 255)


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
    return sections or [(mark("All files", domain="emtk"), ["*"])]


def _default_start_directory() -> str:
    """Where a dialog with no ``directory`` opens: user files first.

    On a page that is the mount, else the drop folder -- the two places a
    browser can hand the page files -- and only then the process's working
    folder. A dialog that opened in the virtual home showed an empty
    listing and no way forward.
    """
    try:
        from emtk.web.page import user_files_dir  # noqa: PLC0415 - page-only path
        return user_files_dir(os.getcwd())
    except Exception:  # not on a page, or the page module is absent
        return os.getcwd()


def _local_files_hint() -> str | None:
    """One line telling a page user how files get into the dialog."""
    try:
        from emtk.web.page import running_on_page  # noqa: PLC0415 - page-only path
    except Exception:
        return None
    if not running_on_page():
        return None
    return mark(
        "Drop files onto the window (or use the Mount folder button) "
        "and they appear here.", domain="emtk")


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

    def __init__(self, title: str = mark("Open", domain="emtk"), mode: str = "open",
                 filters: Sequence | str = ((mark("All files", domain="emtk"), ("*",)),),
                 directory: str | None = None, filename: str = "",
                 multiselect: bool = False, action: str | None = None,
                 rows: int = 12, auto_pick: bool | None = None) -> None:
        if mode not in ("open", "save", "folder"):
            raise ValueError(f"mode must be 'open', 'save' or 'folder', not {mode!r}")
        self.title = title
        self.mode = mode
        self.filters = (parse_filters(filters) if isinstance(filters, str)
                        else [(str(label), [str(p) for p in patterns])
                              for label, patterns in filters]) or [
                                  (mark("All files", domain="emtk"), ["*"])]
        self.filter_index = 0
        start = os.path.abspath(os.path.expanduser(
            directory if directory is not None else _default_start_directory()))
        self.directory = start if os.path.isdir(start) else os.path.expanduser("~")
        self.filename = filename
        self.multiselect = bool(multiselect) and mode == "open"
        self.action = action or {"save": mark("Save", domain="emtk"),
                                  "folder": mark("Choose", domain="emtk")}.get(
            mode, mark("Open", domain="emtk"))
        self.rows = max(1, int(rows))
        self.selection: list[str] = []
        self.error = ""
        self._pending_overwrite: list[str] | None = None
        self.overwrite_confirmed = False
        self.page = 0
        self.folders: list[str] = []
        self.files: list[str] = []
        self._listed: tuple | None = None
        #: A "Load from computer…" pick in flight (pages only): the browser's
        #: file sheet is up; each frame polls for its result.
        self._pick_pending: bool = False
        #: On a page an open dialog starts the browser's file sheet by itself
        #: (``None``: when its listing has nothing matching; ``True``: always;
        #: ``False``: never). One try per :meth:`open`.
        self.auto_pick = auto_pick
        self._pick_tried: bool = False
        #: The address bar's text, and the folder it was last synced from:
        #: the buffer is the user's while they edit it, and follows the
        #: listing again once the shown folder moves.
        self._path_edit: str = ""
        self._path_last_dir: str | None = None
        #: Frames the "path copied." note still shows.
        self._copied_frames: int = 0

    def open(self) -> None:
        """Show this dialog again: a new open may start a new computer pick."""
        self._pick_tried = False
        self._pick_pending = False
        self.error = ""

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
            self.error = (mark("Enter a file name.", domain="emtk") if self.mode == "save"
                          else mark("Select a file first.", domain="emtk"))
            return None
        if self.mode == "open" and not all(os.path.isfile(p) for p in paths):
            self.error = mark("No such file.", domain="emtk")
            return None
        if self.mode == "folder" and not all(os.path.isdir(p) for p in paths):
            self.error = mark("No such folder.", domain="emtk")
            return None
        self.error = ""
        return paths

    # -- the address bar: a path can be pasted in and jumped to -------------- #

    def _jump_to(self, text: str) -> None:
        """Show the folder *text* names, or select the file it names.

        A relative name resolves against the folder being shown, the way every
        host's dialog resolves it. A path that is neither a folder nor a file
        is said in :attr:`error`; a pasted path in quotes (macOS' "Copy as
        Pathname", Windows' shell) has them taken off first.
        """
        target = text.strip().strip("\"").strip("'").strip()
        if not target:
            return
        path = os.path.expanduser(target)
        if not os.path.isabs(path):
            path = os.path.normpath(os.path.join(self.directory, path))
        if os.path.isdir(path):
            self.directory = path
            self.page = 0
            self.selection = []
            self.refresh()
            self.error = ""
        elif os.path.isfile(path):
            self.directory, name = os.path.split(path)
            self.page = 0
            self.refresh()
            # selected even when the filter hides it: the pasted path is the
            # user's choice, and choose() validates the file itself
            self.selection = [name]
            self.error = ""
        else:
            self.error = tr("No such file or folder:", domain="emtk") + f" {target}"

    def _copy_target(self) -> str:
        """The path "Copy path" puts on the clipboard: what is chosen, else where."""
        if self.mode == "save" and self.filename:
            return os.path.join(self.directory, self.filename)
        if self.selection:
            return os.path.join(self.directory, self.selection[0])
        return self.directory

    def _draw_address_bar(self, _w) -> None:
        """Draw the address bar: the shown folder, editable, with a copy button.

        The field carries the folder while it is not being edited, so a pasted
        or typed path (Return to go there) reads as an address bar; the copy
        button puts the chosen path on the clipboard for the paste elsewhere.
        """
        if self._path_last_dir != self.directory:
            self._path_edit = self.directory
            self._path_last_dir = self.directory
        _w.set_next_item_width(-76.0)
        changed, text = _w.input_text("##file-dialog-path", self._path_edit,
                                      hint=tr("path -- paste or type, then Return",
                                              domain="emtk"),
                                      flags=_ITF.ENTER_RETURNS_TRUE, elide_start=True)
        if changed:
            self._jump_to(text)
        _w.set_item_tooltip(tr("The folder being shown. Paste or type a path and press "
                               "Return: a folder is shown, a file is selected in its "
                               "folder.", domain="emtk"))
        _w.same_line()
        if _w.small_button(tr("Copy path", domain="emtk")):
            _w.set_clipboard_text(self._copy_target())
            self._copied_frames = 90
        _w.set_item_tooltip(tr("Copy the chosen path to the clipboard -- the folder being "
                               "shown when nothing is chosen.", domain="emtk"))
        if self._copied_frames:
            self._copied_frames -= 1
            _w.same_line()
            _w.text_colored(HINT_COLOUR, tr("path copied.", domain="emtk"))

    # -- a page's "Load from computer…" -------------------------------------- #

    def _pick_accept(self) -> str | None:
        """The current filter as the picker's ``accept``, when it can be one.

        The browser's ``accept`` takes single extensions; a compound pattern
        (``*.json.gz``) or a catch-all has no honest equivalent, so it is left
        off and every file is offered.
        """
        patterns = self.filters[self.filter_index][1] if self.filters else []
        extensions = []
        for pattern in patterns:
            if pattern.startswith("*.") and "." not in pattern[2:]:
                extensions.append(pattern[1:])
        return " ".join(dict.fromkeys(extensions)) or None

    def should_auto_pick(self) -> bool:
        """Whether this dialog opens the browser's file sheet on its own.

        On a page the sandbox's folders are empty until the user brings files
        in, so loading from the computer *is* the default path: an open dialog
        with nothing matching in its listing starts the sheet itself. On the
        desktop the same surprise would be wrong -- a native dialog starts on
        the listing, and the explicit ``Load from computer`` button (or
        ``auto_pick=True``) opens the platform picker.
        """
        if self.mode != "open" or self._pick_tried:
            return False
        if self.auto_pick is not None:
            return bool(self.auto_pick)
        if not _in_browser():
            return False
        return not any(self.matches(name) for name in self.files)

    def _maybe_auto_pick(self) -> None:
        """Start the browser's file sheet once, when :meth:`should_auto_pick` says so."""
        if not self.should_auto_pick():
            return
        self._pick_tried = True
        if _module_start_local_pick(self._pick_accept()):
            self._pick_pending = True
            self.error = ""

    def _draw_local_pick_button(self, _w) -> bool:
        """Draw the pick button and drive a pick in flight; True while one runs.

        On a page an open-mode dialog can fetch files the way the user expects:
        the browser's own file sheet. The chosen files land in the page's
        user-files folder, the dialog shows it and preselects them.
        """
        if self.mode != "open":
            return False
        from emtk.web.page import local_pick_result, running_on_page, start_local_pick  # noqa: PLC0415

        if not running_on_page():
            return False
        if self._pick_pending:
            outcome = local_pick_result()
            if outcome == "waiting":
                _w.text_colored(HINT_COLOUR, tr("choose files in the browser's dialog…",
                                                domain="emtk"))
                return True
            self._pick_pending = False
            if isinstance(outcome, tuple):
                directory, names = outcome
                self.directory = directory if os.path.isdir(directory) else self.directory
                self.page = 0
                self.refresh()
                here = set(self.files)
                self.selection = [name for name in names if name in here]
                return True
            if isinstance(outcome, str) and outcome.startswith("error: "):
                self.error = outcome[len("error: "):]
            return False
        _w.same_line()
        if _w.button(tr("Load from computer…", domain="emtk")):
            if start_local_pick(self._pick_accept()):
                self._pick_pending = True
                self.error = ""
            else:
                self.error = mark("This page cannot open the browser's file picker.",
                                  domain="emtk")
        _w.set_item_tooltip(tr("Choose a file on this computer; it is copied into the page "
                               "and selected here.", domain="emtk"))
        return False

    # -- the panel ----------------------------------------------------------- #
    def draw(self) -> list[str] | bool | None:
        """Draw the dialog body into the current window.

        Returns
        -------
        list of str, False or None
            The chosen paths on the frame the action is taken, ``False`` on
            the frame Cancel is pressed, ``None`` while the dialog stays open.
        """
        if self._pending_overwrite is not None:
            _w.text_wrapped(tr("Replace the existing file?", domain="emtk")
                            + f"\n{self._pending_overwrite[0]}")
            if _w.button(tr("Replace existing file", domain="emtk")):
                paths = self._pending_overwrite
                self._pending_overwrite = None
                self.overwrite_confirmed = True
                return paths
            _w.set_item_tooltip(tr("Replace this existing file with the new output.", domain="emtk"))
            if _w.button(tr("Choose another name", domain="emtk")):
                self._pending_overwrite = None
            _w.set_item_tooltip(tr("Return to the file chooser without replacing the file.",
                                   domain="emtk"))
            if _w.button(tr("Cancel", domain="emtk")):
                self._pending_overwrite = None
                return False
            _w.set_item_tooltip(tr("Cancel saving; leave the existing file unchanged.", domain="emtk"))
            return None
        self.refresh()
        self._maybe_auto_pick()
        result: list[str] | bool | None = None

        self._draw_address_bar(_w)
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
            _w.set_item_tooltip((tr("Open this folder.", domain="emtk") if is_folder
                                 else tr("Select this file.", domain="emtk"))
                                + "\n" + os.path.join(self.directory, name))
        for _ in range(self.rows - len(entries[start:start + self.rows])):
            _w.dummy(1.0, _core.get_frame_height())
        if pages > 1:
            if _w.small_button(tr("< prev", domain="emtk")) and self.page > 0:
                self.page -= 1
            _w.set_item_tooltip(tr("Show the previous page of files.", domain="emtk"))
            _w.same_line()
            _w.text_disabled(tr("page {page} / {pages}", domain="emtk").format(
                page=self.page + 1, pages=pages))
            _w.same_line()
            if _w.small_button(tr("next >", domain="emtk")) and self.page < pages - 1:
                self.page += 1
            _w.set_item_tooltip(tr("Show the next page of files.", domain="emtk"))
        _w.separator()

        if self.mode == "save":
            _w.set_next_item_width(-1.0)
            _changed, name = _w.input_text("##file-dialog-name", self.filename,
                                          tr("file name", domain="emtk"))
            self.filename = name.replace("\r", "").replace("\n", "")
            _w.set_item_tooltip(tr("Enter the output file name; the selected format supplies its "
                                   "extension.", domain="emtk"))
        elif self.mode == "folder":
            _w.text_disabled(self.chosen()[0])
        else:
            shown = ", ".join(self.selection) if self.selection else tr("(nothing selected)", domain="emtk")
            _w.text_disabled(shown)

        if self.mode != "folder":
            labels = [tr(label) for label, _patterns in self.filters]
            changed, index = _w.combo("##file-dialog-filter", self.filter_index, labels)
            _w.set_item_tooltip(tr("Choose which file formats to list or save.", domain="emtk"))
            if changed and index != self.filter_index:
                self.filter_index = index
                self.refresh()

        if _w.button(tr(self.action, domain="emtk"), (90.0, 0.0)):
            result = self.choose()
        _w.set_item_tooltip({"save": tr("Save to the chosen output file.", domain="emtk"),
                            "folder": tr("Use the selected folder.", domain="emtk"),
                            "open": tr("Open the selected files.", domain="emtk")}[self.mode])
        _w.same_line()
        if _w.button(tr("Cancel", domain="emtk"), (90.0, 0.0)):
            result = False
        _w.set_item_tooltip(tr("Close the file chooser without selecting a path.", domain="emtk"))
        if self._draw_local_pick_button(_w):
            result = None  # a pick started or resolved: not a choice's frame
        hint = _local_files_hint()
        if hint:
            _w.text_colored(HINT_COLOUR, tr(hint, domain="emtk"))
        if self.error:
            _w.text_colored(ERROR_COLOUR, tr(self.error, domain="emtk"))
        if isinstance(result, list) and self.mode == "save" and os.path.isfile(result[0]):
            self.overwrite_confirmed = False
            self._pending_overwrite = result
            return None
        return result
