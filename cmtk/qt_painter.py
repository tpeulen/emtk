"""The Qt implementation of :class:`~.painter.Painter` -- the reference half.

This is what the chrome has always drawn with, repackaged behind the interface
rather than reimplemented: the same ``QPainter``, the same ``QFont("Menlo")``,
the same alignment flags. That is deliberate. Introducing the interface and
changing the pixels in one step would make the port unreviewable, because
"different" would no longer distinguish a wiring mistake from an intended
change. The images this produces must be **byte-identical** to the ones the
direct ``QPainter`` calls produced, and a test asserts it.

It stays after the GPU painter lands. It is the reference the glyph atlas is
baked from, and the thing a parity test compares against.
"""
from __future__ import annotations

from collections.abc import Sequence

from .painter import (
    ALIGN_HCENTER,
    ALIGN_LEFT,
    ALIGN_RIGHT,
    ALIGN_VCENTER,
    Colour,
)

__all__ = ["QtPainter", "png_decode", "image_bytes"]

#: Point size of the chrome's font. Read from ``InternalGui.FONT_PT`` by the
#: caller; repeated here only as the fallback for a painter built standalone.
DEFAULT_FONT_PT = 9


# --------------------------------------------------------------------------- #
# Decoding, which is Qt's other useful trick
# --------------------------------------------------------------------------- #
def png_decode(data: bytes):
    """``(width, height, rgba bytes)`` from PNG *data*, using Qt's decoder.

    Parameters
    ----------
    data : bytes

    Returns
    -------
    tuple

    Raises
    ------
    ValueError
        If Qt will not read *data*. Raised rather than returning an empty
        image, which a caller would upload as a fully transparent atlas and
        read as a layout bug.

    Notes
    -----
    Here because this is the module that already depends on a toolkit, and
    because the caller is :func:`cmtk.gpu_atlas.png_decode`, which wants
    this when it is available and the pure-Python decoder in :mod:`.testing`
    when it is not. The difference on cmtk's own 640x2795 atlas is about
    **2 seconds**: the fallback unfilters it one byte at a time.
    """
    from qtpy import QtGui

    image = QtGui.QImage()
    if not image.loadFromData(data):
        raise ValueError("Qt could not decode this image")
    return image_bytes(image)


def image_bytes(image):
    """``(width, height, rgba bytes)`` from a ``QImage``, tightly packed.

    Parameters
    ----------
    image : QtGui.QImage

    Returns
    -------
    tuple

    Notes
    -----
    ``constBits`` is a ``memoryview`` on PySide and a ``sip.voidptr`` on
    PyQt, and a scanline may be padded, so neither the type nor the stride
    can be assumed. Both cases are handled below; a host that assumed
    either one works on one binding and returns sheared pixels on the
    other.
    """
    from qtpy import QtGui

    image = image.convertToFormat(QtGui.QImage.Format_RGBA8888)
    width, height = image.width(), image.height()
    stride = image.bytesPerLine()
    bits = image.constBits()
    try:
        raw = bytes(bits)
    except (TypeError, IndexError, ValueError):
        # PyQt hands back a `sip.voidptr` of unknown size, which refuses to
        # be read until it is told how long it is. PySide hands back a
        # `memoryview`, which does not have `setsize` at all.
        bits.setsize(stride * height)
        raw = bytes(bits)
    if stride == width * 4:
        return width, height, raw
    packed = bytearray(width * height * 4)
    for row in range(height):
        start = row * stride
        packed[row * width * 4:(row + 1) * width * 4] = raw[start:start + width * 4]
    return width, height, bytes(packed)


class QtPainter:
    """Draw the chrome with a ``QPainter``.

    Parameters
    ----------
    painter : QtGui.QPainter
        An open painter. Not closed here -- whoever opened it owns it.
    font_pt : float, optional
        Point size for the monospaced chrome font. Fractional, because the
        chrome scale is fractional and rounding it here would draw text of a
        size the layout did not budget for.
    """

    def __init__(self, painter, font_pt: float = DEFAULT_FONT_PT) -> None:
        from qtpy import QtGui

        self._p = painter
        font = QtGui.QFont("Menlo")
        font.setStyleHint(QtGui.QFont.Monospace)
        font.setPointSizeF(float(font_pt))
        painter.setFont(font)
        self._metrics = QtGui.QFontMetrics(font)
        self._clips: list = []

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _colour(value: Colour):
        """Return *value* as a ``QColor``.

        Parameters
        ----------
        value : tuple
            ``(r, g, b)`` or ``(r, g, b, a)``, 0-255.

        Returns
        -------
        QtGui.QColor
        """
        from qtpy import QtGui

        return QtGui.QColor(*value)

    @staticmethod
    def _rect(x: float, y: float, w: float, h: float):
        """Return a ``QRectF``."""
        from qtpy import QtCore

        return QtCore.QRectF(x, y, w, h)

    @staticmethod
    def _flags(align: int) -> int:
        """Translate this module's alignment bits into Qt's.

        Parameters
        ----------
        align : int
            A combination of the ``ALIGN_*`` constants.

        Returns
        -------
        int
            The corresponding ``Qt.Alignment`` value.

        Notes
        -----
        Translated rather than reused. The constants happen to share Qt's
        values today, and relying on that would make the GPU painter's
        behaviour depend on a Qt header.
        """
        from qtpy import QtCore

        flags = 0
        if align & ALIGN_LEFT:
            flags |= QtCore.Qt.AlignLeft
        if align & ALIGN_RIGHT:
            flags |= QtCore.Qt.AlignRight
        if align & ALIGN_HCENTER:
            flags |= QtCore.Qt.AlignHCenter
        if align & ALIGN_VCENTER:
            flags |= QtCore.Qt.AlignVCenter
        return int(flags)

    # -- the interface -----------------------------------------------------

    #: ``id(texture) -> (revision, QImage)``. A live frame is re-uploaded
    #: every frame and a colour map almost never, so the QImage is rebuilt
    #: only when the revision moves. Class-level, because a QtPainter is
    #: constructed per paint event and a per-instance cache would never hit.
    _image_cache: dict = {}

    def image(self, x: float, y: float, w: float, h: float, handle,
              uv0=(0.0, 0.0), uv1=(1.0, 1.0),
              tint: Colour = (255, 255, 255, 255)) -> None:
        """Draw *handle* into the box.

        A :class:`~cmtk.texture.Texture` is wrapped in a ``QImage`` over the
        same bytes -- no graphics API in the application, which is the point.
        Anything else is opaque to cmtk and degrades to a tinted box, the
        same fallback every painter gives.
        """
        from qtpy import QtCore, QtGui

        from .texture import Texture

        if not isinstance(handle, Texture):
            self.fill_rect(x, y, w, h, tint)
            return

        key = id(handle)
        hit = self._image_cache.get(key)
        if hit is None or hit[0] != handle.revision:
            # bytes(), not a view: QImage does not own the buffer it is given,
            # and a bytearray that the application keeps writing would be
            # repainted mid-frame -- or freed under Qt entirely.
            img = QtGui.QImage(bytes(handle.px), handle.width, handle.height,
                               handle.width * 4,
                               QtGui.QImage.Format_RGBA8888)
            self._image_cache[key] = (handle.revision, img)
        else:
            img = hit[1]

        src = QtCore.QRectF(uv0[0] * handle.width, uv0[1] * handle.height,
                            (uv1[0] - uv0[0]) * handle.width,
                            (uv1[1] - uv0[1]) * handle.height)
        painter = self._p
        painter.save()
        try:
            if tuple(tint)[:3] != (255, 255, 255):
                painter.setOpacity((list(tint) + [255])[3] / 255.0)
            # nearest neighbour: a scientific image scaled up should show its
            # pixels rather than a smooth guess between them
            painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, False)
            painter.drawImage(self._rect(x, y, w, h), img, src)
        finally:
            painter.restore()

    def fill_rect(self, x: float, y: float, w: float, h: float, colour: Colour) -> None:
        """Fill a rectangle. No outline."""
        from qtpy import QtCore

        self._p.setPen(QtCore.Qt.NoPen)
        self._p.setBrush(self._colour(colour))
        self._p.drawRect(self._rect(x, y, w, h))

    def stroke_rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        edge: Colour,
        fill: Colour | None = None,
    ) -> None:
        """Draw a one-pixel outline, optionally over a fill."""
        from qtpy import QtCore

        self._p.setBrush(
            self._colour(fill) if fill is not None else QtCore.Qt.NoBrush
        )
        self._p.setPen(self._colour(edge))
        self._p.drawRect(self._rect(x, y, w, h))

    def gradient_rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        stops: Sequence[Colour],
        edge: Colour | None = None,
    ) -> None:
        """Fill a rectangle with a left-to-right gradient through *stops*."""
        from qtpy import QtCore, QtGui

        box = self._rect(x, y, w, h)
        gradient = QtGui.QLinearGradient(box.left(), 0.0, box.right(), 0.0)
        count = max(len(stops) - 1, 1)
        for index, stop in enumerate(stops):
            gradient.setColorAt(index / count, self._colour(stop))
        self._p.setBrush(QtGui.QBrush(gradient))
        self._p.setPen(
            self._colour(edge) if edge is not None else QtCore.Qt.NoPen
        )
        self._p.drawRect(box)

    def text(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        align: int,
        string: str,
        colour: Colour,
        bold: bool = False,
    ) -> None:
        """Draw *string* aligned inside the box."""
        if bold:
            font = self._p.font()
            font.setBold(True)
            self._p.setFont(font)
        self._p.setPen(self._colour(colour))
        self._p.drawText(self._rect(x, y, w, h), self._flags(align), string)
        if bold:
            font.setBold(False)
            self._p.setFont(font)

    def fill_triangle(
        self,
        p0: tuple[float, float],
        p1: tuple[float, float],
        p2: tuple[float, float],
        colour: Colour,
    ) -> None:
        """Fill a triangle with three independent corners. No outline.

        Stroked with a hairline pen in the **same** colour as the fill,
        rather than ``NoPen`` -- two triangles sharing an edge (a quad
        drawn as two `fill_triangle` calls, which is every quad this
        primitive serves: `line`, a marker, a projected 3-D face) are two
        independent antialiased paths, and antialiasing a shared internal
        edge from both sides does not reliably sum to full coverage: the
        gap reads as a stray hairline bisecting what should be one flat
        shape. A same-colour stroke closes it without changing anything a
        caller can see on a triangle's own *outer* boundary, where the
        stroke and the fill are the same colour anyway.
        """
        from qtpy import QtCore, QtGui

        path = QtGui.QPainterPath()
        path.moveTo(QtCore.QPointF(*p0))
        path.lineTo(QtCore.QPointF(*p1))
        path.lineTo(QtCore.QPointF(*p2))
        path.closeSubpath()
        fill = self._colour(colour)
        self._p.setPen(QtGui.QPen(fill, 1.0))
        self._p.setBrush(fill)
        self._p.drawPath(path)

    def push_clip(self, x: float, y: float, w: float, h: float) -> None:
        """Restrict drawing to a rectangle until :meth:`pop_clip`."""
        self._p.save()
        self._clips.append(True)
        self._p.setClipRect(self._rect(x, y, w, h))

    def pop_clip(self) -> None:
        """Undo the most recent :meth:`push_clip`."""
        if self._clips:
            self._clips.pop()
            self._p.restore()

    def text_width(self, string: str) -> float:
        """Advance width of *string*, in pixels."""
        try:
            return float(self._metrics.horizontalAdvance(string))
        except AttributeError:  # Qt 5.10 and older
            return float(self._metrics.width(string))

    def line_height(self) -> float:
        """Height of one line of text, in pixels."""
        return float(self._metrics.height())
