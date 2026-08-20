"""Drag-and-drop and hover-delayed tooltips, ported to a context the host owns.

What is here
------------
* :class:`Payload` -- the reference implementation's ``ImGuiPayload``: a type
  tag, the data, who it came from, and the two flags that carry the semantics
  (*preview* and *delivery*).
* :class:`DragDropSource` -- where a drag starts, and the only thing that draws
  the preview that follows the cursor.
* :class:`DragDropTarget` -- a box that may take a drop, and the yellow
  highlight the reference draws over one.
* :class:`DragDropContext` -- the drag itself: the live payload, the cursor,
  and the accept/deliver state machine.
* :class:`AcceptFlags` -- the reference's ``ImGuiDragDropFlags_``, the ones
  that still change behaviour here.
* :class:`DelayedTooltip` -- :class:`~.widgets.Tooltip` with the reference's
  hover delay *and* its stationary rule.

Why there is a context object rather than a global
--------------------------------------------------
The reference routes all of this through one per-frame global (``GImGui``):
``g.DragDropActive``, ``g.DragDropPayload``, ``g.DragDropAcceptIdCurr`` and a
dozen more, reset at the top of every frame and read from inside whichever
widget happens to be submitting itself. That works because the reference *has*
a frame; cmtk does not. The chrome is repainted when it changes, controls are
retained objects, and the host delivers presses and motion rather than a
per-frame input snapshot.

So the whole of ``g.DragDropXXX`` is one explicit :class:`DragDropContext` that
the host owns and threads through: ``source.drag(ctx, x, y)``,
``ctx.hover(target)``, ``ctx.drop()``. Nothing here reads module state, so two
drags in two windows are two contexts and cannot see each other -- which the
global version cannot do at all.

What the frame gave the reference, and what replaces it
-------------------------------------------------------
Two things, and only two:

* **The accept pass.** ``NewFrame`` rolls ``DragDropAcceptIdCurr`` into
  ``...Prev`` and clears it, so every target gets one shot per frame at
  accepting and the *smallest* box wins. Here the pass is bounded by
  :meth:`DragDropContext.move` instead -- motion is the tick -- and the
  smallest-box rule is unchanged.
* **The one-frame deferral.** The reference sets ``payload.Preview`` from
  ``was_accepted_previously`` (the target accepted on the *previous* frame),
  because a target is discovered after the source has already drawn, so the
  overlap cannot be resolved in time to draw the highlight in the same frame.
  Nothing here draws before the accept pass finishes, so preview is immediate.
  The rule that deferral existed to guarantee is kept exactly: a delivery only
  ever goes to a target that was previewing when the button came up.

Nothing else was lost. Payload data is a Python object rather than a copied
byte buffer, so the reference's heap/local payload buffers and its
``PayloadNoCrossContext`` / ``PayloadNoCrossProcess`` hints have nothing to
describe.

What the six painter operations cannot express
----------------------------------------------
The reference's target rectangle is a rounded 2-pixel border
(``DragDropTargetRounding``, ``DragDropTargetBorderSize``). There is no
rounding and no stroke width: the border is two nested one-pixel
:meth:`~.painter.Painter.stroke_rect` calls and the corners are square. The
drag tooltip's ``SetNextWindowBgAlpha(PopupBg.w * 0.60)`` is baked into the
colour instead, since there is no per-surface alpha. And the reference clamps a
tooltip inside the viewport; the painter knows no viewport, so the caller
positions the box.
"""
from __future__ import annotations

import math
from collections.abc import Hashable, Sequence
from typing import Any

from ..painter import ALIGN_LEFT, ALIGN_VCENTER, Painter
from ..style import BORDER, DRAG_DROP_TARGET, POPUP_BG, TEXT, fit_text, hit, with_alpha
from .basic import Tooltip

__all__ = [
    "DELAY_NONE",
    "DELAY_SHORT",
    "DELAY_NORMAL",
    "STATIONARY_DELAY",
    "AcceptFlags",
    "Payload",
    "DragDropSource",
    "DragDropTarget",
    "DragDropContext",
    "DelayedTooltip",
]


# --------------------------------------------------------------------------
# Constants, all from the reference's ImGuiStyle / ImGuiIO defaults
# --------------------------------------------------------------------------
#: ``ImGuiHoveredFlags_DelayNone``: show at once.
DELAY_NONE = 0.0
#: ``style.HoverDelayShort``, and what ``ImGuiHoveredFlags_ForTooltip`` uses
#: with a mouse.
DELAY_SHORT = 0.15
#: ``style.HoverDelayNormal``.
DELAY_NORMAL = 0.40
#: ``style.HoverStationaryDelay``: how long the cursor must hold still before a
#: delayed tooltip is allowed to count its delay at all.
STATIONARY_DELAY = 0.15

#: ``io.MouseDragThreshold``: how far the pointer must travel with the button
#: down before a press becomes a drag. Without it every click on a draggable
#: control starts a drag nobody asked for.
_DRAG_THRESHOLD = 6.0

#: The reference's stationary test: a sample within this many pixels of the
#: last one is "not moving". Squared distance, so a diagonal twitch of one
#: pixel each way still counts as still.
_STATIONARY_THRESHOLD = 2.0

#: ``style.DragDropTargetPadding``: how far the highlight is grown past the
#: target's own box, so it reads as *around* the target rather than as part of
#: it.
_TARGET_PADDING = 3.0

#: ``style.DragDropTargetBorderSize``, in whole pixels -- one nested
#: :meth:`~.painter.Painter.stroke_rect` each.
_TARGET_BORDER = 2

#: ``TOOLTIP_DEFAULT_OFFSET_MOUSE``: where a tooltip sits relative to the
#: cursor, so the cursor does not cover its first character.
_CURSOR_OFFSET = (16.0, 10.0)

#: Padding inside the drag preview box.
_PREVIEW_PAD = 6.0


class AcceptFlags:
    """The reference's ``ImGuiDragDropFlags_``, ported where they still bite.

    The values are the reference's own, so a port can be checked against the
    source it came from by reading down the column.

    Attributes
    ----------
    NONE : int
        No flags.
    SOURCE_NO_PREVIEW_TOOLTIP : int
        ``ImGuiDragDropFlags_SourceNoPreviewTooltip``. The source draws nothing
        at the cursor while dragging.
    SOURCE_ALLOW_NULL_ID : int
        ``ImGuiDragDropFlags_SourceAllowNullID``. Let a control with no
        identity be dragged, by manufacturing one from the box it was pressed
        in. The reference makes this explicit because such an id does not
        survive the control moving, and the drag is then silently cancelled --
        the same caveat applies here.
    ACCEPT_BEFORE_DELIVERY : int
        ``ImGuiDragDropFlags_AcceptBeforeDelivery``.
        :meth:`DragDropContext.hover` hands the payload back while the button
        is still down, so a target can inspect what it is about to be given.
        Without it the payload only appears on the drop.
    ACCEPT_NO_DRAW_DEFAULT_RECT : int
        ``ImGuiDragDropFlags_AcceptNoDrawDefaultRect``. Accept, but draw no
        highlight -- for a target that shows its own.
    ACCEPT_NO_PREVIEW_TOOLTIP : int
        ``ImGuiDragDropFlags_AcceptNoPreviewTooltip``. The *target* asks the
        *source* to stop drawing its preview, because the target's own
        highlight already says what will happen.
    ACCEPT_PEEK_ONLY : int
        The reference's combination of the two accept flags above: look at the
        payload without committing and without lighting up.

    Notes
    -----
    Deliberately **not** ported, all for the same reason -- they describe the
    global per-frame context rather than the drag:

    * ``SourceNoDisableHover`` suppresses the reference's own clearing of
      ``IsItemHovered()`` for the dragged item. cmtk's controls are told
      when they are hovered (see :mod:`.buttons`); nothing clears it for them.
    * ``SourceNoHoldToOpenOthers`` turns off opening tree nodes by hovering
      them mid-drag. That is a timer in the frame loop
      (``DragDropHoldJustPressedId``), and there is no frame loop.
    * ``SourceExtern`` marks a drag begun outside the library, which exists so
      the global active-id machinery does not try to read a current item. A
      context that is handed its source explicitly has no such machinery.
    * ``PayloadAutoExpire`` drops the payload when the source stops being
      *submitted* -- submission being a per-frame notion.
    * ``PayloadNoCrossContext`` / ``PayloadNoCrossProcess`` are hints about
      copying a byte buffer elsewhere. The payload here is a live Python
      object; there is nowhere to copy it to.
    * ``AcceptDrawAsHovered`` renders the accepting *control* in its hovered
      colours. The target here does not own the control it sits over -- the
      host does, and it already has the control's ``hover``.
    """

    NONE = 0
    SOURCE_NO_PREVIEW_TOOLTIP = 1 << 0
    SOURCE_ALLOW_NULL_ID = 1 << 3
    ACCEPT_BEFORE_DELIVERY = 1 << 10
    ACCEPT_NO_DRAW_DEFAULT_RECT = 1 << 11
    ACCEPT_NO_PREVIEW_TOOLTIP = 1 << 12
    ACCEPT_PEEK_ONLY = ACCEPT_BEFORE_DELIVERY | ACCEPT_NO_DRAW_DEFAULT_RECT


class Payload:
    """What is being dragged: a type tag, the data, and where it came from.

    The reference's ``ImGuiPayload``. The two booleans are the whole point of
    the type: **preview** is "the pointer is over a target that would take
    this", **delivery** is "the button came up over that target and it is
    yours now". A port that folds them into one bool loses the ability to
    light a target up before anything has been committed, which is most of
    what makes a drag readable.

    Parameters
    ----------
    payload_type : str
        The type tag a target matches against, the reference's ``DataType``.
    data : Any, optional
        The payload itself. Held by reference -- unlike the reference, which
        copies bytes into its own buffer, because a Python object cannot be
        memcpy'd and pretending otherwise would be a lie about ownership.
    source_id : Hashable, optional
        Which control the drag started from, the reference's ``SourceId``.

    Attributes
    ----------
    preview : bool
        ``ImGuiPayload::Preview``. Set while the pointer is over a target that
        accepts this type.
    delivery : bool
        ``ImGuiPayload::Delivery``. Set once, when the button is released over
        such a target.
    """

    def __init__(
        self,
        payload_type: str,
        data: Any = None,
        source_id: Hashable = 0,
    ) -> None:
        self.type = str(payload_type)
        self.data = data
        self.source_id = source_id
        self.preview = False
        self.delivery = False

    def is_data_type(self, payload_type: str) -> bool:
        """Whether this payload carries the named type.

        The reference also requires ``DataFrameCount != -1`` -- that the data
        was actually set -- so a payload whose source began a drag and never
        said what it was matches nothing. The equivalent here is an empty
        type tag, which matches nothing either.

        Parameters
        ----------
        payload_type : str
            The type a target is willing to take.

        Returns
        -------
        bool
            True if the tags match and this payload has one.
        """
        return bool(self.type) and self.type == payload_type

    def is_preview(self) -> bool:
        """Whether the pointer is over a target that accepts this payload.

        Returns
        -------
        bool
            ``ImGuiPayload::IsPreview()``. Nothing has been handed over.
        """
        return self.preview

    def is_delivery(self) -> bool:
        """Whether this payload has been dropped on a target that took it.

        Returns
        -------
        bool
            ``ImGuiPayload::IsDelivery()``. The drop happened; act on it.
        """
        return self.delivery

    def clear(self) -> None:
        """Forget the data and both flags, as ``ImGuiPayload::Clear`` does."""
        self.type = ""
        self.data = None
        self.source_id = 0
        self.preview = False
        self.delivery = False

    def __repr__(self) -> str:
        """Show the type, the source and which of the two flags are up."""
        state = "delivery" if self.delivery else ("preview" if self.preview else "carried")
        return f"<Payload {self.type!r} from {self.source_id!r} ({state})>"


class DragDropSource:
    """A control that a drag can start from.

    The reference's ``BeginDragDropSource`` + ``SetDragDropPayload`` +
    ``EndDragDropSource``, which are three calls only because they bracket the
    caller's own drawing of the preview inside a tooltip window. Here the
    preview is one method, so there is nothing to bracket.

    A source is a *behaviour attached to an existing control*, not a control:
    it draws nothing where the control is, and the host keeps drawing that
    control exactly as before. What it draws is the preview at the cursor,
    which is why its drawing method is :meth:`draw_preview` and not the
    ``draw(p, x, y, w, h)`` every control has -- the box it would be given is
    not where the preview goes.

    Parameters
    ----------
    source_id : Hashable
        Identity of the control the drag comes from. May be falsy only with
        :attr:`AcceptFlags.SOURCE_ALLOW_NULL_ID`.
    payload_type : str
        The type tag the payload carries.
    data : Any, optional
        What the payload carries.
    label : str, optional
        What the preview says. Defaults to the type tag, which is better than
        an empty box but worse than a name.
    flags : int, optional
        :class:`AcceptFlags`, the ``SOURCE_*`` ones.
    """

    def __init__(
        self,
        source_id: Hashable,
        payload_type: str,
        data: Any = None,
        label: str = "",
        flags: int = AcceptFlags.NONE,
    ) -> None:
        self.source_id = source_id
        self.payload_type = str(payload_type)
        self.data = data
        self.label = label or str(payload_type)
        self.flags = int(flags)
        self._armed = False
        self._press: tuple[float, float] = (0.0, 0.0)
        self._box: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)

    # ------------------------------------------------------------------ #
    @property
    def armed(self) -> bool:
        """Whether the control is held but has not yet moved far enough.

        Returns
        -------
        bool
            True between :meth:`press` and either :meth:`drag` passing the
            threshold or :meth:`release`.
        """
        return self._armed

    def effective_id(self) -> Hashable | None:
        """The identity this source will drag under, or ``None`` if it has none.

        The reference refuses a source with no id unless
        ``SourceAllowNullID`` is set, in which case it manufactures one from
        the item's rectangle and warns that the drag dies if the item moves.
        Both halves are ported: the refusal, and the manufactured id.

        Returns
        -------
        Hashable or None
            The id to put in the payload, or ``None`` when the source has no
            id and was not allowed to invent one.
        """
        if self.source_id:
            return self.source_id
        if self.flags & AcceptFlags.SOURCE_ALLOW_NULL_ID:
            return ("##rect", self._box)
        return None

    def press(
        self,
        x: float,
        y: float,
        box_x: float,
        box_y: float,
        box_w: float,
        box_h: float,
    ) -> bool:
        """Take a press in the control's box, arming a possible drag.

        Parameters
        ----------
        x, y : float
            Where the press landed.
        box_x, box_y, box_w, box_h : float
            The control's box.

        Returns
        -------
        bool
            Whether the press was inside. A press is not yet a drag: the
            pointer has to travel :data:`_DRAG_THRESHOLD` first, which is what
            keeps a click on a draggable control a click.
        """
        self._box = (box_x, box_y, box_w, box_h)
        if not hit(x, y, box_x, box_y, box_w, box_h):
            self._armed = False
            return False
        self._armed = True
        self._press = (float(x), float(y))
        return True

    def drag(self, ctx: DragDropContext, x: float, y: float) -> bool:
        """Continue a press into a drag, beginning one in *ctx* if needed.

        Parameters
        ----------
        ctx : DragDropContext
            The drag the host owns. Threaded through rather than held, so one
            source can be dragged into whichever context is current.
        x, y : float
            Where the pointer is now.

        Returns
        -------
        bool
            Whether this source is being dragged in *ctx* after the call.
        """
        if not self._armed:
            return False
        if ctx.payload is None or ctx.payload.source_id != self.effective_id():
            dx = float(x) - self._press[0]
            dy = float(y) - self._press[1]
            if math.hypot(dx, dy) < _DRAG_THRESHOLD:
                return False
            if ctx.begin(self) is None:
                return False
        ctx.move(x, y)
        return True

    def release(self) -> None:
        """Let go of the control.

        Ends the *press*, not the drag: the drag is the context's, and it is
        :meth:`DragDropContext.drop` that decides whether anything was
        delivered. Calling this without calling that would leave a payload
        being carried by nobody.
        """
        self._armed = False

    def make_payload(self) -> Payload | None:
        """Build the payload this source would drag.

        Returns
        -------
        Payload or None
            ``None`` when the source has no usable identity -- the reference's
            assert in ``BeginDragDropSource`` for an id-less item without
            ``SourceAllowNullID``.
        """
        source_id = self.effective_id()
        if source_id is None:
            return None
        return Payload(self.payload_type, self.data, source_id)

    # ------------------------------------------------------------------ #
    def preview_size(self, p: Painter) -> tuple[float, float]:
        """Measured ``(width, height)`` of the preview box.

        Parameters
        ----------
        p : Painter
            Used to measure.

        Returns
        -------
        tuple of float
            Width and height, padding included.
        """
        return (
            p.text_width(self.label) + 2.0 * _PREVIEW_PAD,
            p.line_height() + 2.0 * _PREVIEW_PAD,
        )

    def draw_preview(self, p: Painter, ctx: DragDropContext) -> None:
        """Draw what is being dragged, at the cursor.

        The reference opens a real tooltip window here and lets the caller
        fill it, at ``PopupBg`` faded to 60%. This draws the same box with the
        same colour, faded the same way, offset from the cursor by the
        reference's ``TOOLTIP_DEFAULT_OFFSET_MOUSE`` so the pointer does not
        sit on the first character.

        Draws nothing when this source is not the one being dragged, when it
        carries :attr:`AcceptFlags.SOURCE_NO_PREVIEW_TOOLTIP`, or when the
        target under the cursor asked for the preview to be hidden with
        :attr:`AcceptFlags.ACCEPT_NO_PREVIEW_TOOLTIP` -- the reference's
        ``BeginTooltipHidden`` path.

        Parameters
        ----------
        p : Painter
            Where to draw.
        ctx : DragDropContext
            The drag, for the cursor position and the accepting target.
        """
        payload = ctx.payload
        if payload is None or payload.source_id != self.effective_id():
            return
        if self.flags & AcceptFlags.SOURCE_NO_PREVIEW_TOOLTIP:
            return
        if ctx.preview_suppressed():
            return
        width, height = self.preview_size(p)
        x = ctx.x + _CURSOR_OFFSET[0]
        y = ctx.y + _CURSOR_OFFSET[1]
        faded = with_alpha(POPUP_BG, int(POPUP_BG[3] * 0.60) if len(POPUP_BG) > 3 else 153)
        p.stroke_rect(x, y, width, height, BORDER, faded)
        inner = max(width - 2.0 * _PREVIEW_PAD, 1.0)
        p.push_clip(x, y, width, height)
        p.text(
            x + _PREVIEW_PAD,
            y,
            inner,
            height,
            ALIGN_VCENTER | ALIGN_LEFT,
            fit_text(p, self.label, inner),
            TEXT,
        )
        p.pop_clip()


class DragDropTarget:
    """A box that may take a drop, and the highlight drawn over it.

    The reference's ``BeginDragDropTarget`` + ``AcceptDragDropPayload`` +
    ``EndDragDropTarget``. Whether it *would* take the payload is
    :meth:`accepts`; whether it *does* is :meth:`DragDropContext.hover`, which
    owns the accept pass because overlapping targets have to be resolved
    against each other and no single target can do that.

    Parameters
    ----------
    target_id : Hashable
        Identity of the target. Must differ from a source's id for that source
        to be droppable here: the reference refuses a target whose id is the
        payload's ``SourceId``, which is what stops a control being dropped on
        itself.
    types : str or sequence of str
        The type tags this target takes. A target that lists none takes
        nothing.
    flags : int, optional
        :class:`AcceptFlags`, the ``ACCEPT_*`` ones.
    """

    def __init__(
        self,
        target_id: Hashable,
        types: str | Sequence[str],
        flags: int = AcceptFlags.NONE,
    ) -> None:
        self.target_id = target_id
        self.types = (types,) if isinstance(types, str) else tuple(str(one) for one in types)
        self.flags = int(flags)
        #: Set by :meth:`DragDropContext.hover`: whether the highlight should
        #: be drawn. Not the same as the payload's preview -- a target with
        #: ``ACCEPT_NO_DRAW_DEFAULT_RECT`` previews without lighting up.
        self.previewing = False
        self._box: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)

    # ------------------------------------------------------------------ #
    @property
    def box(self) -> tuple[float, float, float, float]:
        """The box this target occupies, as ``(x, y, w, h)``.

        Returns
        -------
        tuple of float
            Whatever :meth:`place` or the last :meth:`draw` was given.
        """
        return self._box

    @property
    def surface(self) -> float:
        """Area of the box, in square pixels.

        Returns
        -------
        float
            Used by the accept pass: of two overlapping targets that both
            accept, the smaller one wins, so a target nested inside another
            needs no ordering rule to work.
        """
        return self._box[2] * self._box[3]

    def place(self, x: float, y: float, w: float, h: float) -> None:
        """Say where this target is, from the host's layout.

        Parameters
        ----------
        x, y, w, h : float
            The box.
        """
        self._box = (float(x), float(y), float(w), float(h))

    def accepts_type(self, payload: Payload) -> bool:
        """Whether the payload's type is one this target takes.

        Parameters
        ----------
        payload : Payload
            The payload being dragged.

        Returns
        -------
        bool
            True if any listed type matches.
        """
        return any(payload.is_data_type(one) for one in self.types)

    def over(self, ctx: DragDropContext) -> bool:
        """Whether the drag's cursor is inside this target's box.

        Parameters
        ----------
        ctx : DragDropContext
            The drag.

        Returns
        -------
        bool
            False when nothing is being dragged, when the cursor is elsewhere,
            or when the payload came from this very target.
        """
        payload = ctx.payload
        if payload is None:
            return False
        if payload.source_id == self.target_id:
            return False
        return hit(ctx.x, ctx.y, *self._box)

    def accepts(self, ctx: DragDropContext) -> bool:
        """Whether this target is under the cursor *and* takes the type.

        Parameters
        ----------
        ctx : DragDropContext
            The drag.

        Returns
        -------
        bool
            The question a host asks to decide whether to offer the target to
            :meth:`DragDropContext.hover`. It is safe to offer it either way;
            this is here so a host can colour a whole panel by it.
        """
        payload = ctx.payload
        return payload is not None and self.over(ctx) and self.accepts_type(payload)

    # ------------------------------------------------------------------ #
    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Place the target and draw its highlight if it is previewing.

        The reference's ``RenderDragDropTargetRectEx``: a wash of the target
        colour inside a border of it, grown past the target's own box by
        ``style.DragDropTargetPadding``. The border is two nested one-pixel
        rectangles because there is no stroke width, and its corners are
        square because there is no rounding.

        The wash is the border colour at low alpha rather than the reference's
        separate ``DragDropTargetBg``, which the shared palette does not
        carry; deriving it keeps the two in step by construction.

        Parameters
        ----------
        p : Painter
            Where to draw.
        x, y, w, h : float
            The target's box. Recorded, so the hit test and the drawing can
            never disagree about where the target is.
        """
        self.place(x, y, w, h)
        if not self.previewing:
            return
        bx = x - _TARGET_PADDING
        by = y - _TARGET_PADDING
        bw = w + 2.0 * _TARGET_PADDING
        bh = h + 2.0 * _TARGET_PADDING
        p.fill_rect(bx, by, bw, bh, with_alpha(DRAG_DROP_TARGET, 40))
        for ring in range(_TARGET_BORDER):
            p.stroke_rect(bx + ring, by + ring, bw - 2.0 * ring, bh - 2.0 * ring,
                          DRAG_DROP_TARGET, None)


class DragDropContext:
    """The drag itself: the payload, the cursor, and who is accepting.

    Everything the reference keeps in ``g.DragDropXXX``, in an object the host
    owns. The host's loop is:

    1. ``source.press(...)`` when the button goes down on a draggable control;
    2. ``source.drag(ctx, x, y)`` as the pointer moves -- which calls
       :meth:`begin` once and :meth:`move` every time;
    3. ``ctx.hover(target)`` for each target, in any order;
    4. ``target.draw(...)`` and ``source.draw_preview(...)``;
    5. ``ctx.drop()`` when the button comes up, and ``source.release()``.

    Steps 3 and 5 are the two halves the reference collapses into
    ``AcceptDragDropPayload``, which returns the payload on the delivery frame
    because that frame is the release. Split, they say plainly which is which.
    """

    def __init__(self) -> None:
        self.payload: Payload | None = None
        self.source_id: Hashable = 0
        self.x = 0.0
        self.y = 0.0
        self._accepting: DragDropTarget | None = None
        self._accept_surface = float("inf")

    # ------------------------------------------------------------------ #
    @property
    def active(self) -> bool:
        """Whether a drag is in progress.

        Returns
        -------
        bool
            The reference's ``g.DragDropActive``. It is exactly "there is a
            payload": the two cannot drift apart if only one of them exists.
        """
        return self.payload is not None

    @property
    def accepting(self) -> DragDropTarget | None:
        """The target that took the last accept pass, if any.

        Returns
        -------
        DragDropTarget or None
            Whoever :meth:`drop` would deliver to. Reset by :meth:`move`, so
            it always describes the cursor's current position.
        """
        return self._accepting

    def preview_suppressed(self) -> bool:
        """Whether the accepting target asked for the source preview to be hidden.

        Returns
        -------
        bool
            The reference's ``AcceptNoPreviewTooltip`` check in
            ``BeginDragDropSource``, which sends the source's tooltip to
            ``BeginTooltipHidden`` rather than clearing the flag -- the source
            may already be drawing into it.
        """
        target = self._accepting
        return target is not None and bool(target.flags & AcceptFlags.ACCEPT_NO_PREVIEW_TOOLTIP)

    # ------------------------------------------------------------------ #
    def begin(self, source: DragDropSource) -> Payload | None:
        """Start a drag from *source*, setting its payload.

        Parameters
        ----------
        source : DragDropSource
            Where the drag comes from.

        Returns
        -------
        Payload or None
            The live payload. ``None`` when the source has no usable identity,
            or when a *different* source is already dragging -- the reference
            only arms drag-and-drop ``if (!g.DragDropActive)``, so a second
            source cannot steal a drag in flight.

        Notes
        -----
        Calling this again for the source already dragging returns the same
        payload object rather than a new one: the reference's rule is that a
        payload persists for the whole drag, and handing back a fresh object
        would quietly reset its preview state mid-drag.
        """
        candidate = source.effective_id()
        if candidate is None:
            return None
        if self.payload is not None:
            return self.payload if self.payload.source_id == candidate else None
        payload = source.make_payload()
        if payload is None:
            return None
        self.clear()
        self.payload = payload
        self.source_id = payload.source_id
        return payload

    def move(self, x: float, y: float) -> None:
        """Put the cursor somewhere, and open a fresh accept pass.

        Motion is this port's frame boundary. The reference clears
        ``DragDropAcceptIdCurr`` and ``DragDropAcceptIdCurrRectSurface`` at
        the top of every frame so each target gets one shot at accepting and
        the smallest box wins; the same clearing happens here, on the same
        event that could have changed which target is under the cursor.

        Parameters
        ----------
        x, y : float
            Where the pointer is.
        """
        self.x = float(x)
        self.y = float(y)
        if self._accepting is not None:
            self._accepting.previewing = False
        self._accepting = None
        self._accept_surface = float("inf")
        if self.payload is not None:
            self.payload.preview = False

    def hover(self, target: DragDropTarget) -> Payload | None:
        """Offer the drag to a target: the reference's ``AcceptDragDropPayload``.

        Parameters
        ----------
        target : DragDropTarget
            The target to test. Offering targets in any order is safe -- of
            two that both accept, the one with the smaller box wins, which is
            what lets targets nest.

        Returns
        -------
        Payload or None
            The payload, but only for a target carrying
            :attr:`AcceptFlags.ACCEPT_BEFORE_DELIVERY`: without that flag the
            reference returns nothing until the drop, and so does this. The
            payload is marked as previewing either way, so a host can read
            ``ctx.payload.is_preview()`` without being handed the data it has
            not been given yet.
        """
        payload = self.payload
        if payload is None:
            return None
        if not target.over(self) or not target.accepts_type(payload):
            target.previewing = False
            return None
        if target is not self._accepting and target.surface > self._accept_surface:
            target.previewing = False
            return None
        if self._accepting is not None and self._accepting is not target:
            self._accepting.previewing = False
        self._accepting = target
        self._accept_surface = target.surface
        payload.preview = True
        payload.delivery = False
        target.previewing = not (target.flags & AcceptFlags.ACCEPT_NO_DRAW_DEFAULT_RECT)
        if target.flags & AcceptFlags.ACCEPT_BEFORE_DELIVERY:
            return payload
        return None

    def drop(self) -> Payload | None:
        """The button came up: deliver to whoever was previewing, then clear.

        Returns
        -------
        Payload or None
            The delivered payload, with :meth:`Payload.is_delivery` true and
            :meth:`Payload.is_preview` false -- the drag is over, so there is
            nothing left to preview. ``None`` when the release happened away
            from every target.

        Notes
        -----
        The payload is dropped from the context **whether or not it was
        accepted**, which is the reference's rule (``EndDragDropTarget``
        clears on delivery, and the frame loop clears once the button is no
        longer down). Unlike the reference this does not wipe the returned
        object: it has just been handed to the caller, and a payload that
        empties itself the moment it is delivered would be a trap.
        """
        payload = self.payload
        target = self._accepting
        delivered: Payload | None = None
        if payload is not None and target is not None:
            payload.preview = False
            payload.delivery = True
            delivered = payload
        self.clear()
        return delivered

    def clear(self) -> None:
        """Abandon any drag, as ``ClearDragDrop`` does.

        Drops the payload, forgets the source and closes the accept pass. The
        cursor position is left alone: it is where the pointer is, and that
        does not stop being true because a drag ended.
        """
        if self._accepting is not None:
            self._accepting.previewing = False
        self.payload = None
        self.source_id = 0
        self._accepting = None
        self._accept_surface = float("inf")


class DelayedTooltip(Tooltip):
    """A :class:`~.widgets.Tooltip` that waits before it appears.

    The reference's ``ImGuiHoveredFlags_DelayShort`` / ``DelayNormal`` /
    ``Stationary``, which is what ``BeginItemTooltip`` and ``SetItemTooltip``
    use (``style.HoverFlagsForTooltipMouse`` is ``Stationary | DelayShort``)
    and therefore what a tooltip should do unless told otherwise.

    The two conditions are separate and both must hold, which is the part
    worth porting carefully:

    * the **delay** is time spent hovering, and it runs whether or not the
      pointer is moving;
    * the **stationary** rule is that the pointer must have *stopped* --
      held still for :data:`STATIONARY_DELAY` -- at least once while over this
      item. Sweeping the pointer across a row of controls never satisfies it,
      so nothing pops up in the wake of a pointer on its way somewhere else.
      Once satisfied it stays satisfied until the pointer leaves, so the
      tooltip does not vanish because you nudged the mouse.

    The reference reads both timers off its frame clock. There is no frame
    clock here, so :meth:`hover` takes ``now``. Any monotonic seconds source
    will do, and the caller having to supply one is the point: two hosts
    ticking at different rates get identical behaviour.

    Parameters
    ----------
    lines : str or sequence of str
        Contents, as :class:`~.widgets.Tooltip` takes them.
    delay : float, optional
        Seconds of hovering before showing. :data:`DELAY_SHORT` by default,
        matching the reference's mouse tooltips; :data:`DELAY_NONE` disables
        the delay but *not* the stationary rule.
    stationary : bool, optional
        Whether the pointer must hold still once. On by default.

    Notes
    -----
    The reference's *shared* delay -- ``HoverItemDelayClearTimer``, which keeps
    the elapsed timer alive for about a quarter-second as the pointer crosses
    from one item to the next, so the second tooltip in a row appears at once
    -- is **not** ported. It is state shared between items through the global
    context, and a retained per-item tooltip has no one to share it with. Its
    opt-out, ``NoSharedDelay``, is therefore the only behaviour available here
    and needs no flag.
    """

    def __init__(
        self,
        lines: str | Sequence[str],
        delay: float = DELAY_SHORT,
        stationary: bool = True,
    ) -> None:
        super().__init__(lines)
        self.delay = float(delay)
        self.stationary = bool(stationary)
        self._hovering = False
        self._hover_since = 0.0
        self._still_since = 0.0
        self._unlocked = False
        self._at: tuple[float, float] = (0.0, 0.0)
        self._visible = False

    # ------------------------------------------------------------------ #
    @property
    def visible(self) -> bool:
        """Whether the tooltip should currently be drawn.

        Returns
        -------
        bool
            What the last :meth:`hover` returned, so a host can draw in a
            different place from where it feeds the pointer.
        """
        return self._visible

    @property
    def unlocked(self) -> bool:
        """Whether the pointer has held still over this item at least once.

        Returns
        -------
        bool
            The reference's ``HoverItemUnlockedStationaryId`` test, for this
            one item. Once true it stays true until :meth:`leave`.
        """
        return self._unlocked

    @property
    def position(self) -> tuple[float, float]:
        """The last pointer sample, as ``(x, y)``.

        Returns
        -------
        tuple of float
            Where :meth:`draw_at` would put the box, before the cursor offset.
        """
        return self._at

    def hover(self, x: float, y: float, now: float) -> bool:
        """Feed a pointer sample taken over the item, and ask whether to show.

        Parameters
        ----------
        x, y : float
            Where the pointer is. Only the *distance* from the previous sample
            matters -- more than :data:`_STATIONARY_THRESHOLD` pixels is
            movement and restarts the stationary timer.
        now : float
            Monotonic seconds. The reference accumulates ``io.DeltaTime``
            instead; passing the clock in is the same arithmetic with the
            frame loop taken out.

        Returns
        -------
        bool
            Whether the tooltip should be drawn now.
        """
        now = float(now)
        if not self._hovering:
            self._hovering = True
            self._hover_since = now
            self._still_since = now
            self._unlocked = False
            self._at = (float(x), float(y))
        else:
            moved = math.hypot(float(x) - self._at[0], float(y) - self._at[1])
            self._at = (float(x), float(y))
            if moved > _STATIONARY_THRESHOLD:
                self._still_since = now
            elif now - self._still_since >= STATIONARY_DELAY:
                self._unlocked = True
        if self.stationary and not self._unlocked:
            self._visible = False
            return False
        self._visible = (now - self._hover_since) >= self.delay
        return self._visible

    def leave(self) -> None:
        """The pointer left the item: forget both timers and hide.

        The reference does this by simply not naming the item as its hover
        delay id on the next frame, which clears the timers a few frames
        later. Stated as an event it is one line and cannot be forgotten.
        """
        self._hovering = False
        self._unlocked = False
        self._visible = False

    # ------------------------------------------------------------------ #
    def draw_at(self, p: Painter, x: float, y: float) -> None:
        """Draw the box near a point, offset the way the reference offsets it.

        Parameters
        ----------
        p : Painter
            Where to draw.
        x, y : float
            The cursor. The box is placed down and to the right of it by
            ``TOOLTIP_DEFAULT_OFFSET_MOUSE``, so the pointer never covers the
            first character.
        """
        width, height = self.size(p)
        self.draw(p, x + _CURSOR_OFFSET[0], y + _CURSOR_OFFSET[1], width, height)

    def draw_if_visible(self, p: Painter) -> bool:
        """Draw at the last pointer sample, but only if the delay has elapsed.

        The reference's ``SetItemTooltip``: hover test and tooltip in one
        call, so the two cannot get out of step.

        Parameters
        ----------
        p : Painter
            Where to draw.

        Returns
        -------
        bool
            Whether anything was drawn.
        """
        if not self._visible:
            return False
        self.draw_at(p, self._at[0], self._at[1])
        return True
