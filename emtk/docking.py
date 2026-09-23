"""``emtk.docking`` -- sticky windows and dock regions.

An emtk window (:func:`emtk.begin`) is a box to lay out in, placed by the
caller. An application with panels wants more: windows the user can move,
resize, fold and close, that snap flush to the edges and to each other, and
that can be *docked* -- dropped into a region of the application where they
stick and fill it, several in one region becoming tabs. This module is that
window manager, in two layers.

The geometry of stickiness
--------------------------
Pure functions and one small state machine, no drawing, usable by any
application that paints its own windows (a 3-D viewer's in-viewport chrome):

* :func:`snap` -- a frame dragged near (or flung past) an edge of the bounds
  lands flush on it and is *anchored* there; :func:`anchored_position` keeps
  an anchored window on its edge when the bounds resize.
* :func:`snap_to_frames` -- a frame dragged near another window's edge lands
  flush against it, and aligns the perpendicular edge when nearly level.
* :func:`frames_touch` / :func:`stuck_group` -- two windows sitting flush are
  *stuck*. Stuck is read off the geometry, not kept as links: pulling one
  window flush against another is all it takes to join them.
* :class:`WindowDrag` -- a title-bar drag of one window and the group stuck
  to it: the group travels at its offsets from the lead (a shift-drag takes
  the window alone), the lead snaps to windows and to the bounds.
* :func:`load_states` / :func:`save_states` and :class:`LayoutStore` -- the
  layout as JSON, in a file on the desktop and in ``localStorage`` in a page.

The window manager
------------------
:class:`DockManager` draws the windows through :mod:`emtk.im`. The
application declares its **regions** -- a tree of :class:`Split` and
:class:`Region` -- and its **windows**, each with a ``draw(box)`` callback
for its content, then calls :meth:`DockManager.draw` once per frame::

    from emtk.docking import DockManager, Region, Split

    docks = DockManager(Split("h", 0.3, Region("left"),
                              Split("v", 0.7, Region("center"), Region("bottom"))))
    docks.add_window("form", "Form", draw_form, dock="left")
    docks.add_window("table", "Table", draw_table, dock="left")    # a tab beside Form
    docks.add_window("plot", "Plot", draw_plot, dock="center")
    docks.add_window("notes", "Notes", draw_notes, box=(500, 80, 280, 200))  # floating

    # every frame, inside emtk.frame(...)
    docks.draw((0.0, 0.0, width, height))

What the user can do:

* drag a floating window by its title bar; it snaps to the edges of the
  box and to other floating windows, and windows stuck to it travel with it
  (shift-drag to take it alone). A band along a glued edge and an accent
  border on the partner windows show the snap while the drag lasts;
* resize it by its bottom-right grip, fold it with the arrow or a double
  click on the title, close it with ``×``;
* while a window is dragged, every region shows a drop target -- a pad in
  its middle, and its tab strip. Over one, the whole region lights up where
  the window will go, and releasing docks it there: it sticks to the region
  and fills it. Elsewhere the window stays floating;
* windows docked in one region are its tabs; a tab is dragged along the
  strip to reorder it and dragged off the strip to undock it, which carries
  on as a floating drag -- straight into another region if wanted;
* drag the bar between two regions to resize them. A region with nothing
  visible in it gives its space to its neighbour.

:meth:`DockManager.state` / :meth:`DockManager.restore` are the whole layout
-- floating boxes, what is docked where, tab order, the selected tabs, split
ratios, visibility -- as a JSON-able dict, and a :class:`LayoutStore` passed
as ``store`` loads it at start and saves it after every change.

Everything is in logical pixels, the space :func:`emtk.frame` lays out in;
the device pixel ratio is the host's business and is applied once, there.
"""
from __future__ import annotations

import json
import logging
import pathlib
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from . import im_core as _core
from . import style as _style
from .flags import WindowFlags

__all__ = [
    "SNAP_DISTANCE",
    "STICK_DISTANCE",
    "TOUCH_SLACK",
    "snap",
    "anchored_position",
    "frames_touch",
    "stuck_group",
    "snap_to_frames",
    "DragStep",
    "WindowDrag",
    "load_states",
    "save_states",
    "LayoutStore",
    "Region",
    "Split",
    "DockWindow",
    "DockManager",
]

logger = logging.getLogger(__name__)

Rect = Tuple[float, float, float, float]

#: How near an edge of the bounds (logical pixels) a dragged window snaps flush to it.
SNAP_DISTANCE = 14.0
#: How near another window's edge a dragged window snaps flush against it.
STICK_DISTANCE = 8.0
#: How flush two frames must be to count as stuck together.
TOUCH_SLACK = 2.0


# --------------------------------------------------------------------------- #
# The geometry of stickiness
# --------------------------------------------------------------------------- #
def snap(x: float, y: float, w: float, h: float,
         width: float, height: float, top: float = 0.0,
         distance: float = SNAP_DISTANCE, left: float = 0.0
         ) -> Tuple[float, float, Optional[str]]:
    """Snap a window rectangle to the edges of the bounds.

    Parameters
    ----------
    x, y, w, h : float
        The window frame being dragged.
    width, height : float
        The right and bottom edge of the bounds (the viewport's size when it
        starts at the origin).
    top : float
        The top edge: the height of fixed chrome (menu and tool bars) that the
        snapped position should sit below.
    distance : float
        How near an edge the frame must be to snap.
    left : float
        The left edge.

    Returns
    -------
    tuple
        ``(x, y, anchor)`` -- the snapped position, and where the window is
        now glued: a corner (``"top-right"``, ...), a side (``"right"``,
        ``"top"``, ...), or ``None`` in the open. An anchored window follows
        its edge when the bounds resize (:func:`anchored_position`).

    Notes
    -----
    An edge counts as reached when the frame is within ``distance`` of it
    **or pushed past it** -- which is how an edge is actually hit: the cursor
    is flung at it and overshoots, the frame ends far beyond the line, and a
    symmetric ``abs()`` test concludes the window is nowhere near the edge it
    has just been slammed into. That miss is what makes sides feel unsticky.
    """
    at_left = x <= left + distance
    at_right = (x + w) >= width - distance
    high = y <= top + distance
    low = (y + h) >= height - distance

    if at_left:
        x = float(left)
    elif at_right:
        x = width - w
    if high:
        y = float(top)
    elif low:
        y = height - h

    vertical = "top" if high else ("bottom" if low else "")
    horizontal = "left" if at_left else ("right" if at_right else "")
    anchor = "-".join(part for part in (vertical, horizontal) if part) or None
    return x, y, anchor


def anchored_position(anchor: str, x: float, y: float, w: float, h: float,
                      width: float, height: float, top: float = 0.0,
                      left: float = 0.0) -> Tuple[float, float]:
    """Return the frame position an anchored window takes in these bounds.

    A corner anchor pins both coordinates; a side anchor pins one and keeps
    the window's own position on the other, so a window parked on the right
    side stays on the right side -- at its own height -- through resizes.
    *width*/*height* are the right and bottom edges, as for :func:`snap`.
    """
    parts = set(str(anchor).split("-"))
    if "left" in parts:
        x = float(left)
    elif "right" in parts:
        x = max(width - w, float(left))
    if "top" in parts:
        y = float(top)
    elif "bottom" in parts:
        y = max(height - h, float(top))
    return x, y


def frames_touch(a: Sequence[float], b: Sequence[float],
                 slack: float = TOUCH_SLACK) -> bool:
    """Whether two frames ``(x, y, w, h)`` share an edge.

    Flush within *slack*, with the spans along that edge overlapping -- the
    geometric definition of *stuck*.
    """
    ax, ay, aw, ah = a[:4]
    bx, by, bw, bh = b[:4]
    h_overlap = min(ax + aw, bx + bw) - max(ax, bx)
    v_overlap = min(ay + ah, by + bh) - max(ay, by)
    beside = abs((ax + aw) - bx) <= slack or abs((bx + bw) - ax) <= slack
    stacked = abs((ay + ah) - by) <= slack or abs((by + bh) - ay) <= slack
    return (beside and v_overlap > 0) or (stacked and h_overlap > 0)


def stuck_group(frames: Dict[Any, Sequence[float]], key: Any,
                slack: float = TOUCH_SLACK) -> List[Any]:
    """The keys of the windows transitively touching *key*, *key* first.

    *frames* maps each candidate window (visible, movable) to its frame.
    Stuck is read off the geometry rather than kept as links: two windows
    that sit flush are a group, and pulling one flush against another is all
    it takes to join them.
    """
    if key not in frames:
        return [key]
    group = {key}
    ordered = [key]
    grew = True
    while grew:
        grew = False
        for other, frame in frames.items():
            if other in group:
                continue
            if any(frames_touch(frames[member], frame, slack) for member in ordered):
                group.add(other)
                ordered.append(other)
                grew = True
    return ordered


def snap_to_frames(key: Any, x: float, y: float, w: float, h: float,
                   frames: Dict[Any, Sequence[float]], skip: Iterable[Any] = (),
                   stick: float = STICK_DISTANCE) -> Tuple[float, float, set]:
    """Snap a dragged frame flush against other windows' edges.

    Parameters
    ----------
    key : hashable
        The dragged window, never snapped against itself.
    x, y, w, h : float
        Where the drag would put its frame.
    frames : dict
        ``{key: (x, y, w, h)}`` of the windows it may land against.
    skip : iterable
        Keys to leave out -- the followers of the drag: a group must not
        snap against itself.
    stick : float
        How near an edge must be.

    Returns
    -------
    tuple
        The adjusted ``(x, y)`` and the set of keys it landed against, for
        the visual hint.
    """
    skip = set(skip)
    hit_keys: set = set()
    for other, frame in frames.items():
        if other == key or other in skip:
            continue
        ox, oy, ow, oh = frame[:4]
        v_overlap = min(y + h, oy + oh) - max(y, oy)
        h_overlap = min(x + w, ox + ow) - max(x, ox)
        snapped = False
        if v_overlap > 0:
            if abs((x + w) - ox) <= stick:
                x = ox - w
                snapped = True
            elif abs((ox + ow) - x) <= stick:
                x = ox + ow
                snapped = True
        if h_overlap > 0:
            if abs((y + h) - oy) <= stick:
                y = oy - h
                snapped = True
            elif abs((oy + oh) - y) <= stick:
                y = oy + oh
                snapped = True
        if snapped:
            # Align the perpendicular edge too when it is nearly level -- a
            # stuck pair with a two-pixel step reads as a mistake.
            if abs(y - oy) <= stick:
                y = oy
            if abs(x - ox) <= stick:
                x = ox
            hit_keys.add(other)
    return x, y, hit_keys


@dataclass
class DragStep:
    """Where one step of a :class:`WindowDrag` puts the windows.

    Attributes
    ----------
    x, y : float
        The lead window's new position.
    anchor : str or None
        The edge or corner of the bounds it is glued to now.
    edges : tuple of str
        The glued edges (``("top", "right")``), for the hint bands.
    stuck : set
        The windows it landed flush against, for the hint borders.
    followers : dict
        ``{key: (x, y)}`` -- the new position of every window travelling
        with it.
    """

    x: float
    y: float
    anchor: Optional[str] = None
    edges: Tuple[str, ...] = ()
    stuck: set = field(default_factory=set)
    followers: Dict[Any, Tuple[float, float]] = field(default_factory=dict)


class WindowDrag:
    """A title-bar drag of one window, and of the group stuck to it.

    Parameters
    ----------
    key : hashable
        The window grabbed (the lead).
    grab : (float, float)
        The pointer's offset from the lead's top-left corner.
    followers : list of (key, dx, dy)
        The windows travelling with it, at their offsets from the lead.

    Use :meth:`start` to make one from the frames on screen, then
    :meth:`move` for each pointer position.
    """

    def __init__(self, key: Any, grab: Tuple[float, float],
                 followers: Sequence[Tuple[Any, float, float]] = ()) -> None:
        self.key = key
        self.grab = (float(grab[0]), float(grab[1]))
        self.followers = [(k, float(dx), float(dy)) for k, dx, dy in followers]

    @classmethod
    def start(cls, key: Any, px: float, py: float,
              frames: Dict[Any, Sequence[float]], alone: bool = False,
              slack: float = TOUCH_SLACK) -> "WindowDrag":
        """Grab *key* at ``(px, py)``.

        Windows that touch it move with it -- stuck is geometric, read off
        *frames* at the moment the drag starts, so nothing has to be linked or
        unlinked explicitly. *alone* (a shift-drag) takes the window by
        itself, which is how a stuck pair is pulled apart.
        """
        x, y = float(frames[key][0]), float(frames[key][1])
        followers = [] if alone else [
            (other, float(frames[other][0]) - x, float(frames[other][1]) - y)
            for other in stuck_group(frames, key, slack) if other != key
        ]
        return cls(key, (px - x, py - y), followers)

    @property
    def follower_keys(self) -> set:
        return {k for k, _dx, _dy in self.followers}

    def move(self, px: float, py: float, size: Tuple[float, float],
             frames: Dict[Any, Sequence[float]], bounds: Optional[Rect] = None,
             snapping: bool = True, stick: float = STICK_DISTANCE,
             distance: float = SNAP_DISTANCE) -> DragStep:
        """The windows' positions with the pointer at ``(px, py)``.

        Parameters
        ----------
        size : (float, float)
            The lead's frame size (its title bar alone while folded).
        frames : dict
            ``{key: (x, y, w, h)}`` of the windows the lead may snap against.
        bounds : (x, y, w, h), optional
            The area the windows live in, whose edges it snaps to.
        snapping : bool
            Off: the window goes exactly where it is dropped, owns its
            position and follows no edge. Stuck windows still travel with it
            -- stickiness and snapping are different promises.
        """
        w, h = float(size[0]), float(size[1])
        x, y = px - self.grab[0], py - self.grab[1]
        anchor = None
        stuck: set = set()
        if snapping:
            skip = {self.key} | self.follower_keys
            x, y, stuck = snap_to_frames(self.key, x, y, w, h, frames, skip, stick)
            if bounds is not None:
                bx, by, bw, bh = bounds
                x, y, anchor = snap(x, y, w, h, bx + bw, by + bh, top=by,
                                    distance=distance, left=bx)
        edges = tuple(anchor.split("-")) if anchor else ()
        followers = {k: (x + dx, y + dy) for k, dx, dy in self.followers}
        return DragStep(x, y, anchor, edges, stuck, followers)


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
def load_states(path, fields: Optional[Sequence[str]] = None) -> dict:
    """Read a layout written by :func:`save_states`; ``{}`` when none or bad.

    With *fields*, the file is ``{key: {field: value}}`` and only those
    fields of each entry are kept -- what a caller that restores a few known
    attributes per window wants.
    """
    if path is None:
        return {}
    try:
        raw = json.loads(pathlib.Path(path).read_text())
    except FileNotFoundError:
        return {}
    except Exception:  # noqa: BLE001 - a bad file is a fresh start, not a crash
        logger.debug("emtk.docking: unreadable layout %s; starting fresh", path,
                     exc_info=True)
        return {}
    if not isinstance(raw, dict):
        return {}
    if fields is None:
        return raw
    states: dict = {}
    for key, entry in raw.items():
        if isinstance(entry, dict):
            states[str(key)] = {name: entry[name] for name in fields if name in entry}
    return states


def save_states(states: dict, path) -> bool:
    """Write *states* as JSON to *path*; ``False`` when there is nowhere to write."""
    if path is None:
        return False
    try:
        path = pathlib.Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(states, indent=2, sort_keys=True))
        return True
    except Exception:  # noqa: BLE001
        logger.debug("emtk.docking: could not save the layout to %s", path, exc_info=True)
        return False


class LayoutStore:
    """Where a layout lives between runs: a file, or the page's ``localStorage``.

    Parameters
    ----------
    name : str
        The layout's name; the ``localStorage`` key is ``emtk.layout.<name>``.
    path : str or pathlib.Path, optional
        The JSON file on the desktop. ``None`` keeps nothing on the desktop.
    storage : object, optional
        Anything with ``getItem``/``setItem``/``removeItem`` -- the DOM's
        ``localStorage``, which is what is used in a page (Pyodide's file
        system is gone when the tab closes). A test passes a stand-in.
    """

    def __init__(self, name: str, path=None, storage=None) -> None:
        self.name = str(name)
        self.path = None if path is None else pathlib.Path(path)
        self.storage = storage if storage is not None else self._page_storage()

    @staticmethod
    def _page_storage():
        if sys.platform != "emscripten":
            return None
        try:
            import js  # noqa: PLC0415 - only exists inside Pyodide

            return js.localStorage
        except Exception:  # noqa: BLE001
            return None

    @property
    def key(self) -> str:
        return f"emtk.layout.{self.name}"

    def load(self) -> dict:
        """The saved layout, ``{}`` when there is none."""
        if self.storage is not None:
            try:
                text = self.storage.getItem(self.key)
                data = json.loads(text) if text else {}
                return data if isinstance(data, dict) else {}
            except Exception:  # noqa: BLE001
                logger.debug("emtk.docking: unreadable stored layout", exc_info=True)
                return {}
        return load_states(self.path)

    def save(self, data: dict) -> bool:
        if self.storage is not None:
            try:
                self.storage.setItem(self.key, json.dumps(data, sort_keys=True))
                return True
            except Exception:  # noqa: BLE001
                logger.debug("emtk.docking: could not store the layout", exc_info=True)
                return False
        return save_states(data, self.path)

    def clear(self) -> None:
        """Forget the saved layout."""
        if self.storage is not None:
            try:
                self.storage.removeItem(self.key)
            except Exception:  # noqa: BLE001
                pass
            return
        try:
            if self.path is not None and self.path.is_file():
                self.path.unlink()
        except OSError:
            logger.debug("emtk.docking: could not remove %s", self.path, exc_info=True)


# --------------------------------------------------------------------------- #
# Regions and windows
# --------------------------------------------------------------------------- #
@dataclass
class Region:
    """A named place windows dock into.

    Attributes
    ----------
    name : str
    keep : bool
        Keep the region's space (drawn empty) when nothing is docked in it.
        Off by default: an empty region gives its space to its neighbour.
    """

    name: str
    keep: bool = False


@dataclass
class Split:
    """Two nodes side by side (``axis="h"``) or one over the other (``"v"``).

    Attributes
    ----------
    axis : str
        ``"h"``: *first* on the left; ``"v"``: *first* on top.
    ratio : float
        The share of the space *first* takes; the bar between them drags it.
    first, second : Region or Split
    name : str
        Identity in a saved layout; derived from the position in the tree
        (``"root"``, ``"root.1"``, ...) when left empty.
    min_size : float
        Neither side is dragged below this (logical pixels).
    """

    axis: str
    ratio: float
    first: "Node"
    second: "Node"
    name: str = ""
    min_size: float = 80.0


Node = Union[Region, Split]


@dataclass
class DockWindow:
    """One window of a :class:`DockManager`.

    Attributes
    ----------
    key : str
        Identity (in the saved layout too).
    title : str
        Shown in its title bar or tab.
    draw : callable or None
        ``draw(box)`` -- the content, called inside an :func:`emtk.begin_child`
        of the content box, so it lays out with :mod:`emtk.im` as anywhere.
    box : (x, y, w, h) or None
        The floating frame: where the window is, or goes when it is undocked.
        ``h`` is the unfolded height. ``None`` until it first floats.
    visible, collapsed : bool
    closable, resizable, movable, dockable : bool
        What the user may do to it. ``movable`` covers undocking.
    anchor : str or None
        The edge or corner of the dock box a floating window is glued to.
    min_size : (float, float)
    padding : float
        Space between the frame and the content box.
    frame, content : (x, y, w, h) or None
        Where it was drawn last frame (``None`` when not drawn).
    """

    key: str
    title: str = ""
    draw: Optional[Callable[[Rect], Any]] = None
    box: Optional[Rect] = None
    visible: bool = True
    collapsed: bool = False
    closable: bool = True
    resizable: bool = True
    movable: bool = True
    dockable: bool = True
    anchor: Optional[str] = None
    min_size: Tuple[float, float] = (120.0, 60.0)
    padding: float = 6.0
    frame: Optional[Rect] = None
    content: Optional[Rect] = None


#: The bar between two regions, logical pixels.
SPLITTER = 4.0
#: A drop pad's side: this share of the region's shorter side, within bounds.
PAD_FRACTION = 0.34
PAD_MIN = 44.0
PAD_MAX = 110.0
#: How far off its tab strip a tab must be dragged to come undocked.
UNDOCK_DISTANCE = 14.0
#: The resize grip's side.
GRIP = 14.0
#: The band drawn along an edge a dragged window is glued to.
HINT_BAND = 3.0


def _hit(px: float, py: float, rect: Optional[Rect]) -> bool:
    if rect is None:
        return False
    x, y, w, h = rect
    return x <= px < x + w and y <= py < y + h


class DockManager:
    """Sticky floating windows and dock regions, drawn with :mod:`emtk.im`.

    Parameters
    ----------
    layout : Region or Split, optional
        The regions windows dock into; one ``Region("center")`` by default.
    store : LayoutStore, optional
        Loaded by :meth:`load` and written after every change the user makes.
    on_change : callable, optional
        ``on_change(manager)`` once a frame in which the layout changed -- by
        the user (a drop, a close, a resize or a split let go, a tab chosen)
        or by the application (:meth:`show`, :meth:`hide`, :meth:`focus`,
        :meth:`dock`, ...). The store is written at the same moment.
    snapping : bool
        Whether dragged windows snap to the edges and to each other.
    name : str
        Prefix of the :mod:`emtk.im` windows it submits, so two managers in
        one frame do not collide.

    See the module docstring for the whole picture.
    """

    def __init__(self, layout: Optional[Node] = None, store: Optional[LayoutStore] = None,
                 on_change: Optional[Callable[["DockManager"], Any]] = None,
                 snapping: bool = True, name: str = "dock") -> None:
        self.layout: Node = layout if layout is not None else Region("center")
        self.name = str(name)
        self.store = store
        self.on_change = on_change
        self.snapping = bool(snapping)
        self.regions: Dict[str, Region] = {}
        self.splits: Dict[str, Split] = {}
        self._index(self.layout, "root")
        self._default_ratios = {name: s.ratio for name, s in self.splits.items()}
        #: Region name -> window keys docked there, in tab order.
        self.tabs: Dict[str, List[str]] = {name: [] for name in self.regions}
        #: Region name -> the key of its tab on top.
        self.selected: Dict[str, Optional[str]] = {name: None for name in self.regions}
        self.windows: Dict[str, DockWindow] = {}
        #: Floating windows, back to front.
        self.z: List[str] = []
        self.box: Rect = (0.0, 0.0, 0.0, 0.0)
        #: Last frame's region boxes and splitter bars.
        self.region_boxes: Dict[str, Rect] = {}
        self.splitters: List[Tuple[Split, Rect, Rect]] = []
        self._tab_rects: Dict[str, List[Tuple[str, Rect]]] = {}
        self._defaults: Dict[str, dict] = {}
        self._saved: dict = {}
        self._drag: Optional[dict] = None
        #: While a window is dragged: the region under the pointer.
        self.drop_target: Optional[str] = None
        self._hint_edges: Tuple[str, ...] = ()
        self._hint_keys: set = set()
        self._title_h = 20.0
        #: The layout changed since it was last written; flushed by :meth:`draw`.
        self._dirty = False

    # ------------------------------------------------------------ the tree
    def _index(self, node: Node, path: str) -> None:
        if isinstance(node, Region):
            if node.name in self.regions:
                raise ValueError(f"two regions are called {node.name!r}")
            self.regions[node.name] = node
            return
        if node.axis not in ("h", "v"):
            raise ValueError(f"a split's axis is 'h' or 'v', not {node.axis!r}")
        if not node.name:
            node.name = path
        self.splits[node.name] = node
        self._index(node.first, f"{path}.0")
        self._index(node.second, f"{path}.1")

    # --------------------------------------------------------- the windows
    def add_window(self, key: str, title: str = "", draw: Optional[Callable] = None,
                   dock: Optional[str] = None, box: Optional[Rect] = None,
                   **options) -> DockWindow:
        """Add (or replace) a window; returns it.

        Parameters
        ----------
        key : str
        title : str
            Defaults to *key*.
        draw : callable
            ``draw(box)``, the content.
        dock : str, optional
            The region it starts docked in (a tab after those already there).
        box : (x, y, w, h), optional
            Its floating frame -- where it starts when *dock* is not given.
        **options
            Any other :class:`DockWindow` attribute (``closable``,
            ``min_size``, ``visible``, ...).

        A layout loaded earlier (:meth:`restore`, :meth:`load`) that knows
        this window is applied to it here, so windows may be added after the
        layout is read.
        """
        if dock is not None and dock not in self.regions:
            raise KeyError(f"no region {dock!r}; the regions are {sorted(self.regions)}")
        if key in self.windows:
            self._forget(key)
        win = DockWindow(key=key, title=title or key, draw=draw,
                         box=None if box is None else tuple(float(v) for v in box),
                         **options)
        self.windows[key] = win
        self._defaults[key] = {"dock": dock, "box": win.box, "visible": win.visible,
                               "collapsed": win.collapsed}
        if dock is not None:
            self._put(key, dock)
        else:
            if win.box is None:
                win.box = (40.0, 40.0, 320.0, 240.0)
            self.z.append(key)
        entry = (self._saved.get("windows") or {}).get(key)
        if isinstance(entry, dict):
            self._apply_entry(win, entry)
            self._order_tabs()
        return win

    def remove_window(self, key: str) -> bool:
        """Drop a window. Returns whether there was one."""
        if key not in self.windows:
            return False
        self._forget(key)
        self.windows.pop(key, None)
        self._defaults.pop(key, None)
        return True

    def window(self, key: str) -> Optional[DockWindow]:
        return self.windows.get(key)

    def region_of(self, key: str) -> Optional[str]:
        """The region *key* is docked in, or ``None`` when it floats."""
        for name, keys in self.tabs.items():
            if key in keys:
                return name
        return None

    def docked(self, region: str) -> List[str]:
        """The windows docked in *region*, in tab order."""
        return list(self.tabs[region])

    def floating(self) -> List[str]:
        """The floating windows, back to front."""
        return list(self.z)

    def active_tab(self, region: str) -> Optional[str]:
        """The visible tab on top of *region*, or ``None`` when it shows nothing."""
        shown = [k for k in self.tabs[region] if self.windows[k].visible]
        if not shown:
            return None
        chosen = self.selected.get(region)
        return chosen if chosen in shown else shown[0]

    def is_shown(self, key: str) -> bool:
        """Whether *key* is drawn: visible, and on top of its region if docked."""
        win = self.windows.get(key)
        if win is None or not win.visible:
            return False
        region = self.region_of(key)
        return region is None or self.active_tab(region) == key

    def _forget(self, key: str) -> None:
        for name, keys in self.tabs.items():
            if key in keys:
                keys.remove(key)
                if self.selected.get(name) == key:
                    self.selected[name] = keys[0] if keys else None
        if key in self.z:
            self.z.remove(key)

    def _put(self, key: str, region: str, index: Optional[int] = None) -> None:
        self._forget(key)
        keys = self.tabs[region]
        if index is None or index >= len(keys):
            keys.append(key)
        else:
            keys.insert(max(int(index), 0), key)
        if self.selected.get(region) is None:
            self.selected[region] = key

    # ------------------------------------------------------------- actions
    def dock(self, key: str, region: str, index: Optional[int] = None,
             select: bool = True) -> None:
        """Dock *key* in *region* (at tab *index*), shown on top unless *select* is off."""
        if region not in self.regions:
            raise KeyError(f"no region {region!r}")
        win = self.windows[key]
        self._put(key, region, index)
        win.anchor = None
        if select:
            self.selected[region] = key
        self._dirty = True

    def undock(self, key: str, box: Optional[Rect] = None) -> None:
        """Float *key*, at *box* or where it last floated."""
        win = self.windows[key]
        region = self.region_of(key)
        if box is not None:
            win.box = tuple(float(v) for v in box)
        elif win.box is None:
            win.box = self._undocked_box(region)
        self._forget(key)
        self.z.append(key)
        self._dirty = True

    def _undocked_box(self, region: Optional[str]) -> Rect:
        bx, by, bw, bh = self.box if self.box[2] > 0 else (0.0, 0.0, 800.0, 600.0)
        rect = self.region_boxes.get(region) if region else None
        w = min(rect[2] if rect else 360.0, max(bw * 0.45, 200.0))
        h = min(rect[3] if rect else 260.0, max(bh * 0.6, 150.0))
        x = rect[0] + 24.0 if rect else bx + 40.0
        y = rect[1] + 24.0 if rect else by + 40.0
        return (x, y, w, h)

    def show(self, key: str) -> None:
        self.windows[key].visible = True
        self._dirty = True

    def hide(self, key: str) -> None:
        self.windows[key].visible = False
        self._dirty = True

    def toggle(self, key: str) -> bool:
        """Show a hidden window (on top) or hide a shown one; returns visibility.

        A docked window that is visible but under another tab is brought to
        the top rather than hidden -- the View menu's toggle is "let me see
        it" as often as "put it away".
        """
        win = self.windows[key]
        if win.visible and self.is_shown(key):
            win.visible = False
            self._dirty = True
        else:
            self.focus(key)
        return win.visible

    def is_visible(self, key: str) -> bool:
        win = self.windows.get(key)
        return bool(win is not None and win.visible)

    def focus(self, key: str) -> None:
        """Show *key* and bring it to the front: its tab on top, or raised."""
        win = self.windows[key]
        win.visible = True
        win.collapsed = False
        region = self.region_of(key)
        if region is not None:
            self.selected[region] = key
        else:
            self.raise_window(key)
        self._dirty = True

    def raise_window(self, key: str) -> None:
        if key in self.z and self.z[-1] != key:
            self.z.remove(key)
            self.z.append(key)

    def set_ratio(self, split: str, ratio: float) -> None:
        self.splits[split].ratio = min(max(float(ratio), 0.02), 0.98)
        self._dirty = True

    # --------------------------------------------------------------- state
    def state(self) -> dict:
        """The whole layout as a JSON-able dict (see :meth:`restore`)."""
        windows: Dict[str, dict] = {}
        for key, entry in (self._saved.get("windows") or {}).items():
            if key not in self.windows and isinstance(entry, dict):
                windows[key] = dict(entry)   # a window not added this run keeps its place
        for key, win in self.windows.items():
            windows[key] = {
                "dock": self.region_of(key),
                "box": None if win.box is None else [round(float(v), 2) for v in win.box],
                "visible": bool(win.visible),
                "collapsed": bool(win.collapsed),
                "anchor": win.anchor,
            }
        regions = {}
        for name in self.regions:
            tabs = list(self.tabs[name])
            for key, entry in windows.items():
                if key not in self.windows and entry.get("dock") == name:
                    saved = ((self._saved.get("regions") or {}).get(name) or {}).get("tabs") or []
                    at = saved.index(key) if key in saved else len(tabs)
                    tabs.insert(min(at, len(tabs)), key)
            regions[name] = {"tabs": tabs, "selected": self.selected.get(name)}
        return {
            "version": 1,
            "splits": {name: round(float(s.ratio), 4) for name, s in self.splits.items()},
            "regions": regions,
            "windows": windows,
            "z": [k for k in self.z],
        }

    def to_json(self) -> str:
        return json.dumps(self.state(), indent=2, sort_keys=True)

    def restore(self, state: Optional[dict]) -> None:
        """Put the layout of :meth:`state` back.

        Windows it names that are not added yet get their place when they
        are (:meth:`add_window`); windows it does not name keep theirs;
        regions and splits it names that no longer exist are ignored.
        """
        if not isinstance(state, dict):
            return
        self._saved = state
        for name, ratio in (state.get("splits") or {}).items():
            if name in self.splits:
                try:
                    self.set_ratio(name, float(ratio))
                except (TypeError, ValueError):
                    pass
        for key, entry in (state.get("windows") or {}).items():
            win = self.windows.get(key)
            if win is not None and isinstance(entry, dict):
                self._apply_entry(win, entry)
        self._order_tabs()
        for name, entry in (state.get("regions") or {}).items():
            if name in self.regions and isinstance(entry, dict):
                chosen = entry.get("selected")
                if chosen in self.tabs[name]:
                    self.selected[name] = chosen
        z = [k for k in (state.get("z") or []) if k in self.z]
        self.z = z + [k for k in self.z if k not in z]
        self._dirty = False

    @classmethod
    def from_json(cls, text: str, layout: Optional[Node] = None, **kwargs) -> "DockManager":
        """A manager over *layout* with the state *text* (windows re-added later)."""
        manager = cls(layout, **kwargs)
        manager.restore(json.loads(text))
        return manager

    def _apply_entry(self, win: DockWindow, entry: dict) -> None:
        dirty = self._dirty
        try:
            self._apply(win, entry)
        finally:
            self._dirty = dirty

    def _apply(self, win: DockWindow, entry: dict) -> None:
        box = entry.get("box")
        if isinstance(box, (list, tuple)) and len(box) == 4:
            try:
                win.box = tuple(float(v) for v in box)
            except (TypeError, ValueError):
                pass
        if "visible" in entry:
            win.visible = bool(entry["visible"])
        if "collapsed" in entry:
            win.collapsed = bool(entry["collapsed"])
        if "anchor" in entry:
            win.anchor = str(entry["anchor"]) if entry["anchor"] else None
        if "dock" in entry:
            region = entry.get("dock")
            if region in self.regions:
                if self.region_of(win.key) != region:
                    self._put(win.key, region)
            elif region is None and self.region_of(win.key) is not None:
                self.undock(win.key)

    def _order_tabs(self) -> None:
        """Tabs in the order the saved layout lists them."""
        for name, entry in (self._saved.get("regions") or {}).items():
            if name not in self.tabs or not isinstance(entry, dict):
                continue
            order = [k for k in (entry.get("tabs") or []) if isinstance(k, str)]
            rank = {k: i for i, k in enumerate(order)}
            self.tabs[name].sort(key=lambda k: rank.get(k, len(rank)))
            chosen = entry.get("selected")
            if chosen in self.tabs[name]:
                self.selected[name] = chosen

    def load(self) -> bool:
        """Restore the layout from :attr:`store`; whether there was one."""
        if self.store is None:
            return False
        data = self.store.load()
        if not data:
            return False
        self.restore(data)
        return True

    def save(self) -> bool:
        """Write the layout to :attr:`store`."""
        return self.store.save(self.state()) if self.store is not None else False

    def reset(self) -> None:
        """Put every window and split back as the application declared them.

        The escape hatch for a layout that has gone wrong, and it forgets the
        stored layout too: restoring this session without clearing the store
        would bring the bad layout back on the next run.
        """
        self._saved = {}
        for name, ratio in self._default_ratios.items():
            self.splits[name].ratio = ratio
        for name in self.tabs:
            self.tabs[name] = []
            self.selected[name] = None
        self.z = []
        for key, win in self.windows.items():
            default = self._defaults.get(key) or {}
            win.visible = bool(default.get("visible", True))
            win.collapsed = bool(default.get("collapsed", False))
            win.anchor = None
            win.box = default.get("box")
            if default.get("dock"):
                self._put(key, default["dock"])
            else:
                if win.box is None:
                    win.box = (40.0, 40.0, 320.0, 240.0)
                self.z.append(key)
        if self.store is not None:
            self.store.clear()
        self._dirty = False

    def _changed(self) -> None:
        """The layout changed: written (and announced) at the end of the frame."""
        self._dirty = True

    def flush(self) -> bool:
        """Write a changed layout to the store and tell ``on_change``, now.

        :meth:`draw` calls it at the end of every frame, so a change is saved
        once however many steps made it. Returns whether there was one.
        """
        if not self._dirty:
            return False
        self._dirty = False
        if self.store is not None:
            self.save()
        if self.on_change is not None:
            try:
                self.on_change(self)
            except Exception:  # noqa: BLE001 - a listener must not break the frame
                logger.exception("emtk.docking: on_change failed")
        return True

    # -------------------------------------------------------------- layout
    def _present(self, node: Node, force: Optional[str] = None) -> bool:
        if isinstance(node, Region):
            return (node.keep or node.name == force
                    or any(self.windows[k].visible for k in self.tabs[node.name]))
        return self._present(node.first, force) or self._present(node.second, force)

    def compute_layout(self, box: Rect, force: Optional[str] = None
                       ) -> Tuple[Dict[str, Rect], List[Tuple[Split, Rect, Rect]]]:
        """Region boxes and splitter bars for *box*.

        Returns ``({region: rect}, [(split, split_rect, bar_rect)])`` for the
        regions with something to show (and *force*, laid out as if it had).
        """
        boxes: Dict[str, Rect] = {}
        bars: List[Tuple[Split, Rect, Rect]] = []

        def walk(node: Node, rect: Rect) -> None:
            if isinstance(node, Region):
                boxes[node.name] = rect
                return
            a = self._present(node.first, force)
            b = self._present(node.second, force)
            if a and b:
                x, y, w, h = rect
                span = (w if node.axis == "h" else h) - SPLITTER
                low = min(node.min_size, span / 2.0)
                cut = round(min(max(span * node.ratio, low), span - low))
                if node.axis == "h":
                    one, two = (x, y, cut, h), (x + cut + SPLITTER, y, span - cut, h)
                    bar = (x + cut, y, SPLITTER, h)
                else:
                    one, two = (x, y, w, cut), (x, y + cut + SPLITTER, w, span - cut)
                    bar = (x, y + cut, w, SPLITTER)
                bars.append((node, rect, bar))
                walk(node.first, one)
                walk(node.second, two)
            elif a:
                walk(node.first, rect)
            elif b:
                walk(node.second, rect)

        if self._present(self.layout, force):
            walk(self.layout, tuple(float(v) for v in box))
        return boxes, bars

    def drop_targets(self) -> Dict[str, Tuple[Rect, Rect, Rect]]:
        """``{region: (preview, pad, strip)}`` for a window dragged now.

        *preview* is the box the window would fill -- the region's box, or,
        for an empty region, the box it would get once something is in it.
        *pad* is the target in its middle and *strip* its tab strip.
        """
        targets = {}
        for name in self.regions:
            rect = self.region_boxes.get(name)
            if rect is None:
                rect = self.compute_layout(self.box, force=name)[0].get(name)
            if rect is None:
                continue
            x, y, w, h = rect
            side = min(max(min(w, h) * PAD_FRACTION, PAD_MIN), PAD_MAX, min(w, h))
            pad = (x + (w - side) / 2.0, y + (h - side) / 2.0, side, side)
            strip = (x, y, w, self._title_h)
            targets[name] = (rect, pad, strip)
        return targets

    def target_at(self, px: float, py: float) -> Optional[str]:
        """The region whose drop target is under ``(px, py)``, or ``None``."""
        best, best_d = None, None
        for name, (_rect, pad, strip) in self.drop_targets().items():
            if _hit(px, py, pad) or _hit(px, py, strip):
                cx, cy = pad[0] + pad[2] / 2.0, pad[1] + pad[3] / 2.0
                d = (px - cx) ** 2 + (py - cy) ** 2
                if best is None or d < best_d:
                    best, best_d = name, d
        return best

    def _floating_frame(self, win: DockWindow) -> Rect:
        """The frame a floating window is drawn at: its box, kept inside the dock box."""
        bx, by, bw, bh = self.box
        x, y, w, h = win.box if win.box is not None else (bx + 40.0, by + 40.0, 320.0, 240.0)
        mw, mh = win.min_size
        w = min(max(w, mw), max(bw, mw))
        h = min(max(h, mh, self._title_h), max(bh, self._title_h))
        fh = self._title_h if win.collapsed else h
        x = min(max(x, bx), max(bx + bw - w, bx))
        y = min(max(y, by), max(by + bh - fh, by))
        return (x, y, w, fh)

    def _follow_box(self, box: Rect) -> None:
        """Anchored windows follow their edge; every floating window stays reachable."""
        old = self.box
        self.box = tuple(float(v) for v in box)
        bx, by, bw, bh = self.box
        moved = old != self.box
        for key in self.z:
            win = self.windows[key]
            if win.box is None:
                continue
            x, y, w, h = win.box
            if moved and win.anchor:
                fw, fh = self._floating_frame(win)[2:]
                x, y = anchored_position(win.anchor, x, y, fw, fh, bx + bw, by + bh,
                                         top=by, left=bx)
                win.box = (x, y, w, h)
            fx, fy = self._floating_frame(win)[:2]
            win.box = (fx, fy, w, h)

    def _frames(self, keys: Iterable[str]) -> Dict[str, Rect]:
        return {k: self._floating_frame(self.windows[k]) for k in keys
                if self.windows[k].visible}

    # --------------------------------------------------------------- drags
    def _begin_move(self, ctx, key: str, px: float, py: float, item_id, alone: bool) -> None:
        movable = [k for k in self.z if self.windows[k].movable]
        frames = self._frames(movable)
        frames.setdefault(key, self._floating_frame(self.windows[key]))
        self._drag = {"kind": "move", "key": key, "id": item_id,
                      "drag": WindowDrag.start(key, px, py, frames, alone=alone),
                      "moved": False}
        ctx.set_active_id(item_id)

    def _update_drag(self, ctx) -> None:
        drag = self._drag
        if drag is None:
            return
        io = ctx.io
        px, py = io.mouse_pos
        if not io.mouse_down[0]:
            self._finish_drag(ctx, px, py)
            return
        kind = drag["kind"]
        if kind == "tab":
            self._drag_tab(ctx, drag, px, py)
            drag = self._drag
            kind = drag["kind"]
        if kind == "move":
            self._drag_move(drag, px, py)
        elif kind == "resize":
            win = self.windows.get(drag["key"])
            if win is not None and win.box is not None:
                ox, oy, ow, oh = drag["origin"]
                x, y, _w, _h = win.box
                win.box = (x, y, max(ow + px - ox, win.min_size[0]),
                           max(oh + py - oy, win.min_size[1], self._title_h))
        elif kind == "split":
            split, rect = drag["split"], drag["rect"]
            x, y, w, h = rect
            span = (w if split.axis == "h" else h) - SPLITTER
            if span > 0:
                at = (px - x if split.axis == "h" else py - y) - drag["grab"]
                low = min(split.min_size, span / 2.0)
                split.ratio = min(max(at, low), span - low) / span

    def _drag_move(self, drag: dict, px: float, py: float) -> None:
        key = drag["key"]
        win = self.windows.get(key)
        if win is None or key not in self.z:
            self._drag = None
            return
        drag["moved"] = True
        mover: WindowDrag = drag["drag"]
        target = self.target_at(px, py) if win.dockable else None
        self.drop_target = target
        frame = self._floating_frame(win)
        others = [k for k in self.z if k != key]
        step = mover.move(px, py, (frame[2], frame[3]), self._frames(others),
                          bounds=self.box, snapping=self.snapping and target is None)
        _x, _y, w, h = win.box
        win.box = (step.x, step.y, w, h)
        win.anchor = step.anchor
        self._hint_edges = step.edges
        self._hint_keys = set(step.stuck)
        for other, (ox, oy) in step.followers.items():
            follower = self.windows.get(other)
            if follower is None or follower.box is None:
                continue
            follower.box = (ox, oy, follower.box[2], follower.box[3])
            follower.anchor = None
        for other in [key, *step.followers]:
            follower = self.windows.get(other)
            if follower is not None and follower.box is not None:
                fx, fy = self._floating_frame(follower)[:2]
                follower.box = (fx, fy, follower.box[2], follower.box[3])

    def _drag_tab(self, ctx, drag: dict, px: float, py: float) -> None:
        region, key = drag["region"], drag["key"]
        rect = self.region_boxes.get(region)
        win = self.windows.get(key)
        if rect is None or win is None or key not in self.tabs.get(region, []):
            self._drag = None
            return
        x, y, w, _h = rect
        sx, sy = drag["start"]
        off_strip = (py < y - UNDOCK_DISTANCE or py > y + self._title_h + UNDOCK_DISTANCE
                     or px < x - UNDOCK_DISTANCE or px > x + w + UNDOCK_DISTANCE)
        if off_strip and win.movable:
            # Off the strip: the tab comes away as a floating window under
            # the pointer, and the same press goes on as a floating drag.
            if win.box is None:
                win.box = self._undocked_box(region)
            bw, bh = win.box[2], win.box[3]
            grab_x = min(max(drag["grab_x"], 24.0), max(bw - 48.0, 24.0))
            grab_y = self._title_h / 2.0
            win.box = (px - grab_x, py - grab_y, bw, bh)
            win.collapsed = False
            self._forget(key)
            self.z.append(key)
            self._drag = {"kind": "move", "key": key, "id": drag["id"],
                          "drag": WindowDrag(key, (grab_x, grab_y)), "moved": True}
            return
        if abs(px - sx) < 4.0:
            return
        # Along the strip: reorder.
        keys = self.tabs[region]
        rects = self._tab_rects.get(region) or []
        slot = len(rects)
        for i, (_k, tab) in enumerate(rects):
            if px < tab[0] + tab[2] / 2.0:
                slot = i
                break
        current = keys.index(key)
        if slot > current:
            slot -= 1
        if slot != current:
            keys.remove(key)
            keys.insert(min(slot, len(keys)), key)

    def _finish_drag(self, ctx, px: float, py: float) -> None:
        drag, self._drag = self._drag, None
        if ctx.active_id == drag.get("id"):
            ctx.clear_active_id()
        target, self.drop_target = self.drop_target, None
        self._hint_edges, self._hint_keys = (), set()
        kind = drag["kind"]
        if kind == "move" and drag.get("moved"):
            key = drag["key"]
            if target is not None and key in self.windows and self.windows[key].dockable:
                index = None
                strip = self.drop_targets().get(target, (None, None, None))[2]
                if _hit(px, py, strip):
                    rects = self._tab_rects.get(target) or []
                    index = next((i for i, (_k, tab) in enumerate(rects)
                                  if px < tab[0] + tab[2] / 2.0), None)
                self.dock(key, target, index)
            self._changed()
        elif kind in ("resize", "split", "tab"):
            self._changed()

    # ------------------------------------------------------------- drawing
    def _id(self, *parts) -> tuple:
        return ("##emtk.docking", self.name, *parts)

    def draw(self, box: Rect) -> None:
        """Draw every window and region into *box*, and handle their input.

        Call once per frame inside :func:`emtk.frame` (inside another window
        is fine). The windows' ``draw`` callbacks run from here.
        """
        ctx = _core.get_current_context()
        io = ctx.io
        # The windows submitted before this call -- the application's own,
        # under the docks -- and so the ones the docks must hit-test in front of.
        before = {id(w) for w in ctx.windows if w.active}
        self._title_h = float(ctx.p.line_height() + ctx.style.frame_padding[1] * 2.0)
        self._follow_box(box)
        self._update_drag(ctx)
        # A press on a floating window brings it to the front.
        if (io.mouse_clicked[0] or io.mouse_clicked[1]) and ctx.hovered_window is not None:
            name = ctx.hovered_window.name
            prefix = f"##{self.name}.win."
            if name.startswith(prefix) and name[len(prefix):] in self.z:
                self.raise_window(name[len(prefix):])
        self.region_boxes, self.splitters = self.compute_layout(self.box)
        submitted: List[str] = []

        area = f"##{self.name}.area"
        ctx.begin(area, self.box, WindowFlags.NO_BACKGROUND)
        submitted.append(area)
        self._draw_splitters(ctx)
        ctx.end()

        for region, rect in self.region_boxes.items():
            name = f"##{self.name}.region.{region}"
            ctx.begin(name, rect)
            submitted.append(name)
            self._draw_region(ctx, region, rect)
            ctx.end()

        front = self.z[-1] if self.z else None
        for key in list(self.z):
            win = self.windows[key]
            if not win.visible:
                win.frame = win.content = None
                continue
            name = f"##{self.name}.win.{key}"
            frame = self._floating_frame(win)
            ctx.begin(name, frame)
            submitted.append(name)
            self._draw_floating(ctx, win, frame, key == front)
            ctx.end()

        overlay = f"##{self.name}.overlay"
        ctx.begin(overlay, self.box, WindowFlags.NO_BACKGROUND, no_mouse_inputs=True)
        submitted.append(overlay)
        self._draw_overlay(ctx)
        ctx.end()
        self._sync_order(ctx, submitted, before)
        if self._drag is None:
            self.flush()

    def _sync_order(self, ctx, names: List[str], before: set) -> None:
        """Put this manager's windows in :mod:`emtk.im`'s display list in drawing order.

        The list is what hit-testing walks, so it must say what the screen
        says: a raised window is drawn last *and* hit first. The manager's
        windows go right after those submitted before it (*before*, ids) and
        ahead of everything else -- a dialog the application draws after the
        docks is in front of them however early it was first opened.
        """
        wanted = set(names)
        by_name = {w.name: w for w in ctx.windows if w.name in wanted}
        mine = [by_name[n] for n in names if n in by_name]
        earlier = [w for w in ctx.windows if w.name not in wanted and id(w) in before]
        later = [w for w in ctx.windows if w.name not in wanted and id(w) not in before]
        ctx.windows[:] = earlier + mine + later

    def _draw_splitters(self, ctx) -> None:
        io = ctx.io
        draw = ctx.draw
        for split, rect, bar in self.splitters:
            item = self._id("split", split.name)
            hovered = ctx.item_add(bar, item)
            if hovered and io.mouse_clicked[0] and self._drag is None:
                x, y = rect[0], rect[1]
                grab = (io.mouse_pos[0] - bar[0]) if split.axis == "h" else (io.mouse_pos[1] - bar[1])
                self._drag = {"kind": "split", "split": split, "rect": rect,
                              "grab": grab, "id": item}
                ctx.set_active_id(item)
            active = self._drag is not None and self._drag.get("id") == item
            if hovered or active:
                colour = ctx.style.color(_core.Col.SEPARATOR_ACTIVE if active
                                         else _core.Col.SEPARATOR_HOVERED)
                x, y, w, h = bar
                draw.add_rect_filled((x, y), (x + w, y + h), colour)

    def _draw_region(self, ctx, region: str, rect: Rect) -> None:
        io = ctx.io
        draw = ctx.draw
        style = ctx.style
        x, y, w, h = rect
        th = self._title_h
        pad_x = style.frame_padding[0]
        draw.add_rect_filled((x, y), (x + w, y + th), style.color(_core.Col.TITLE_BG))
        shown = [k for k in self.tabs[region] if self.windows[k].visible]
        top = self.active_tab(region)
        top_win = self.windows.get(top) if top else None

        # The close box first: the first item to claim the pointer keeps it.
        close_rect = None
        if top_win is not None and top_win.closable:
            close_rect = (x + w - th, y, th, th)
            if self._button(ctx, close_rect, self._id("close", region), "×"):
                top_win.visible = False
                self._changed()
        right = (close_rect[0] if close_rect else x + w) - 2.0

        rects: List[Tuple[str, Rect]] = []
        cursor = x + 1.0
        ctx.p.push_clip(x, y, max(right - x, 0.0), th)
        for key in shown:
            win = self.windows[key]
            tw = ctx.p.text_width(win.title) + pad_x * 2.0 + 6.0
            tab = (cursor, y + 1.0, tw, th - 1.0)
            rects.append((key, tab))
            item = self._id("tab", key)
            hovered = ctx.item_add(tab, item)
            if hovered and io.mouse_clicked[0] and self._drag is None:
                if self.selected.get(region) != key:
                    self.selected[region] = key
                self._drag = {"kind": "tab", "region": region, "key": key, "id": item,
                              "start": tuple(io.mouse_pos),
                              "grab_x": io.mouse_pos[0] - tab[0] + 4.0}
                ctx.set_active_id(item)
            active = key == top
            colour = (_core.Col.TAB_SELECTED if active
                      else (_core.Col.HEADER_HOVERED if hovered else _core.Col.TAB))
            draw.add_rect_filled((tab[0], tab[1]), (tab[0] + tab[2], tab[1] + tab[3]),
                                 style.color(colour))
            text_h = ctx.p.line_height()
            draw.add_text((tab[0] + pad_x + 3.0, tab[1] + (tab[3] - text_h) / 2.0),
                          style.color(_core.Col.TEXT), win.title)
            cursor += tw + 2.0
        ctx.p.pop_clip()
        self._tab_rects[region] = rects
        # The rest of the strip drags the tab on top, as its title bar would.
        rest = (cursor, y, max(right - cursor, 0.0), th)
        if top is not None and rest[2] > 0:
            item = self._id("strip", region)
            if ctx.item_add(rest, item) and io.mouse_clicked[0] and self._drag is None:
                self._drag = {"kind": "tab", "region": region, "key": top, "id": item,
                              "start": tuple(io.mouse_pos), "grab_x": 40.0}
                ctx.set_active_id(item)
        draw.add_line((x, y + th), (x + w, y + th), style.color(_core.Col.TAB_SELECTED))

        for key in self.tabs[region]:
            if key != top:
                self.windows[key].frame = self.windows[key].content = None
        if top_win is None:
            return
        top_win.frame = rect
        self._draw_content(ctx, top_win, (x, y + th, w, h - th))

    def _draw_floating(self, ctx, win: DockWindow, frame: Rect, front: bool) -> None:
        io = ctx.io
        draw = ctx.draw
        style = ctx.style
        x, y, w, fh = frame
        th = self._title_h
        win.frame = frame
        draw.add_rect_filled((x, y), (x + w, y + th),
                             style.color(_core.Col.TITLE_BG_ACTIVE if front
                                         else _core.Col.TITLE_BG))
        # The buttons first: the first item to claim the pointer keeps it.
        fold = (x, y, th, th)
        if self._button(ctx, fold, self._id("fold", win.key), None):
            win.collapsed = not win.collapsed
            self._changed()
        self._fold_arrow(draw, fold, win.collapsed, style.color(_core.Col.TEXT))
        right = x + w
        if win.closable:
            close_rect = (x + w - th, y, th, th)
            right = close_rect[0]
            if self._button(ctx, close_rect, self._id("close", win.key), "×"):
                win.visible = False
                self._changed()
        title_rect = (x + th, y, max(right - x - th, 0.0), th)
        item = self._id("title", win.key)
        if ctx.item_add(title_rect, item) and io.mouse_clicked[0] and self._drag is None:
            if io.mouse_double_clicked[0]:
                win.collapsed = not win.collapsed
                self._changed()
            elif win.movable:
                self._begin_move(ctx, win.key, io.mouse_pos[0], io.mouse_pos[1], item,
                                 alone=bool(io.key_shift))
        ctx.p.push_clip(*title_rect)
        text_h = ctx.p.line_height()
        draw.add_text((title_rect[0] + 2.0, y + (th - text_h) / 2.0),
                      style.color(_core.Col.TEXT), win.title)
        ctx.p.pop_clip()
        if win.collapsed:
            win.content = None
            return
        grip = None
        grip_hot = False
        if win.resizable:
            grip = (x + w - GRIP, y + fh - GRIP, GRIP, GRIP)
            item = self._id("grip", win.key)
            grip_hot = ctx.item_add(grip, item)
            if grip_hot and io.mouse_clicked[0] and self._drag is None:
                self._drag = {"kind": "resize", "key": win.key, "id": item,
                              "origin": (io.mouse_pos[0], io.mouse_pos[1],
                                         w, win.box[3] if win.box else fh)}
                ctx.set_active_id(item)
            grip_hot = grip_hot or (self._drag is not None and self._drag.get("id") == item)
        self._draw_content(ctx, win, (x, y + th, w, fh - th))
        if grip is not None:
            gx, gy, gw, gh = grip
            colour = style.color(_core.Col.BUTTON_HOVERED if grip_hot else _core.Col.HEADER)
            draw.add_triangle_filled((gx + gw, gy), (gx + gw, gy + gh), (gx, gy + gh), colour)

    def _draw_content(self, ctx, win: DockWindow, body: Rect) -> None:
        x, y, w, h = body
        p = win.padding
        content = (x + p, y + p, max(w - 2.0 * p, 1.0), max(h - 2.0 * p, 1.0))
        win.content = content
        ctx.begin_child(content)
        ctx.push_id(("dockwin", win.key))
        try:
            if win.draw is not None:
                win.draw(content)
        except Exception:  # noqa: BLE001 - one window must not take the frame down
            logger.exception("emtk.docking: window %r failed to draw", win.key)
        finally:
            ctx.pop_id()
            ctx.end_child()

    def _button(self, ctx, rect: Rect, item, label: Optional[str]) -> bool:
        """A title-bar button: highlighted under the pointer, pressed on release."""
        hovered, held, pressed = ctx.button_behavior(rect, item)
        if hovered or held:
            x, y, w, h = rect
            ctx.draw.add_rect_filled((x + 2.0, y + 2.0), (x + w - 2.0, y + h - 2.0),
                                     ctx.style.color(_core.Col.BUTTON_ACTIVE if held
                                                     else _core.Col.BUTTON_HOVERED))
        if label:
            x, y, w, h = rect
            tw = ctx.p.text_width(label)
            th = ctx.p.line_height()
            ctx.draw.add_text((x + (w - tw) / 2.0, y + (h - th) / 2.0),
                              ctx.style.color(_core.Col.TEXT), label)
        return bool(pressed)

    @staticmethod
    def _fold_arrow(draw, rect: Rect, collapsed: bool, colour) -> None:
        x, y, w, h = rect
        cx, cy = x + w / 2.0, y + h / 2.0
        r = min(w, h) * 0.22
        if collapsed:        # pointing right
            draw.add_triangle_filled((cx - r * 0.7, cy - r), (cx + r, cy), (cx - r * 0.7, cy + r),
                                     colour)
        else:                # pointing down
            draw.add_triangle_filled((cx - r, cy - r * 0.7), (cx + r, cy - r * 0.7),
                                     (cx, cy + r), colour)

    def _draw_overlay(self, ctx) -> None:
        draw = ctx.draw
        accent = _style.NAV_CURSOR
        drag = self._drag
        if drag is None or drag.get("kind") != "move" or not drag.get("moved"):
            return
        win = self.windows.get(drag["key"])
        # Drop targets: a pad in every region, the whole region lit under the pointer.
        if win is not None and win.dockable:
            for name, (rect, pad, _strip) in self.drop_targets().items():
                if name == self.drop_target:
                    x, y, w, h = rect
                    draw.add_rect_filled((x, y), (x + w, y + h), _style.HEADER)
                    draw.add_rect((x, y), (x + w, y + h), accent, thickness=2.0)
                px, py, pw, ph = pad
                lit = name == self.drop_target
                draw.add_rect_filled((px, py), (px + pw, py + ph),
                                     _style.BUTTON_HOVERED if lit else _style.BUTTON, 4.0)
                draw.add_rect((px, py), (px + pw, py + ph), accent, 4.0)
                inset = pw * 0.22
                draw.add_rect((px + inset, py + inset), (px + pw - inset, py + ph - inset),
                              _style.TEXT + (200,), 2.0)
        if self.drop_target is not None:
            return
        # The snap hint: the glued window and its partners outlined, bands on glued edges.
        for key in {drag["key"], *self._hint_keys}:
            other = self.windows.get(key)
            if other is None or other.frame is None:
                continue
            if key == drag["key"] and not (self._hint_edges or self._hint_keys):
                continue
            x, y, w, h = other.frame
            draw.add_rect((x, y), (x + w, y + h), accent, thickness=2.0)
        bx, by, bw, bh = self.box
        band = HINT_BAND
        for edge in self._hint_edges:
            if edge == "left":
                draw.add_rect_filled((bx, by), (bx + band, by + bh), accent)
            elif edge == "right":
                draw.add_rect_filled((bx + bw - band, by), (bx + bw, by + bh), accent)
            elif edge == "top":
                draw.add_rect_filled((bx, by), (bx + bw, by + band), accent)
            elif edge == "bottom":
                draw.add_rect_filled((bx, by + bh - band), (bx + bw, by + bh), accent)
