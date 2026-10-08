Widget guide
=============

The families below are the ones |CONTROL_MODULES| enumerates. Each
module is documented in the API reference (generated from its docstrings);
this page gives the shape of each family and a runnable example.

.. contents::

Text
----

``widgets.text`` draws strings in the seven layouts the reference
distinguishes: plain text, coloured, disabled, wrapped, bulleted, labelled
and separated.

.. image:: _screenshots/text.png
   :alt: Plain, coloured, disabled text and a bullet item

::

    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 300, 200)):
        im.begin("Text")
        im.text("plain")
        im.text_colored((255, 200, 50), "coloured")
        im.text_disabled("dimmed")
        im.bullet_text("bulleted")
        im.separator()
        im.end()

    assert "plain" in painter.strings
    assert "coloured" in painter.strings

Basic
------

``widgets.basic`` carries the foundational controls: :class:`Button`,
:class:`Checkbox`, :class:`SliderFloat`, :class:`ProgressBar`,
:class:`TreeNode`, :class:`Separator`, :class:`Toggle`,
:class:`RadioGroup`, :class:`InputInt`, :class:`Combo`,
:class:`ListBox`, :class:`Table`, :class:`Tabs`, :class:`TextInput`,
:class:`Tooltip`, :class:`ColorEdit4`, :class:`PlotLines`,
:class:`Histogram`, :class:`ScrollBar`, and the layout helper
:func:`fit_text`.

These are retained controls: they own their state and draw into a box.
The immediate-mode functions in ``im`` are the other shape.

.. image:: _screenshots/basic.png
   :alt: A checkbox, three kinds of button and a progress bar

::

    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 300, 200)):
        im.begin("Basic")
        im.checkbox("enabled", True)
        im.progress_bar(0.7, (0, 0, -1, 0))
        im.end()

    assert len(painter.fills) > 0

Buttons
-------

``widgets.buttons`` adds :class:`SmallButton` (no vertical frame padding,
sits inside a line of text), :class:`InvisibleButton` (a hit box that
paints nothing), :class:`ArrowButton` (a framed button with a triangular
arrow), :class:`CheckboxFlags` (a checkbox over a bitmask, with the
reference's *mixed* state), and :class:`RadioButton`.

::

    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 300, 200)):
        im.begin("Buttons")
        im.button("Normal")
        im.small_button("Small")
        im.arrow_button("arrow", im.Dir.LEFT)
        im.end()

    assert "Normal" in painter.strings
    assert "Small" in painter.strings

Sliders
--------

``widgets.sliders`` ports the full slider family: horizontal and vertical,
float and integer, linear and logarithmic, single and multi-component, and
:func:`slider_angle` (radians stored, degrees shown). The reference's
``ScaleRatioFromValueT`` / ``ScaleValueFromRatioT`` pair is ported
faithfully, including the awkward half: a logarithmic slider cannot take
``log(0)``, so the bounds are fudged away from zero by an epsilon derived
from the format string's precision.

.. image:: _screenshots/sliders.png
   :alt: Float, integer and angle sliders

::

    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 300, 200)):
        im.begin("Sliders")
        changed, f = im.slider_float("float", 0.5, 0.0, 1.0)
        changed, i = im.slider_int("int", 5, 0, 100)
        im.end()

    assert isinstance(f, float)
    assert isinstance(i, int)

Drag
----

``widgets.drag`` provides scrubbing controls: a number you scrub rather
than a slider you aim. The box is only where the gesture *starts*; from
then on the value moves by the mouse's delta, scaled by ``v_speed``. An
integer drag at a tenth of a unit per pixel would round every single event
to zero and never move at all — the reference fixes this with an
accumulator (``g.DragCurrentAccum``), ported faithfully here.

::

    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 300, 200)):
        im.begin("Drag")
        changed, v = im.drag_float("drag", 1.0, 0.01)
        im.end()

    assert isinstance(v, float)

Inputs
------

``widgets.inputs`` ports the reference's scalar editor: a field you type a
number into, with optional ``-``/``+`` buttons and a printf format that
decides both how the value is shown and how the typed string is read back.
Also carries ``InputTextMultiline`` and ``InputTextWithHint``.

Text editing shortcuts
----------------------

Every emtk text entry -- ``im.input_text`` and view-form fields, a combo
list's filter, DataTable cells and filter, the retained inputs -- edits
through :class:`emtk.widgets.text_field.TextField`, so the shortcuts are the
same everywhere; the code editor follows the same table. Hosts deliver the
*primary* modifier as ``CONTROL_MODIFIER`` (``io.key_ctrl``): Command on a
Mac (the browser's client, read from ``navigator``), Ctrl elsewhere;
``emtk.keys.mac_behaviors()`` says which, ``set_mac_behaviors()`` forces it.

=====================  ======================  ==========================
action                 Mac                     Windows / Linux
=====================  ======================  ==========================
select all             Cmd+A                   Ctrl+A
copy / cut / paste     Cmd+C / X / V           Ctrl+C / X / V
undo                   Cmd+Z                   Ctrl+Z
redo                   Cmd+Shift+Z             Ctrl+Y, Ctrl+Shift+Z
word left / right      Option+Left / Right     Ctrl+Left / Right
line start / end       Cmd+Left / Right,       Home / End
                       Home / End, Ctrl+A / E
delete word            Option+Backspace        Ctrl+Backspace / Delete
delete to line start   Cmd+Backspace           --
=====================  ======================  ==========================

Shift with any movement extends the selection, typing or pasting replaces
it, Backspace and Delete remove it; a click places the caret, a drag
selects, a double click selects a word and a triple click everything. On a
Mac Control-A/E/B/F/D/H/K keep their Emacs meaning, as in a Cocoa field --
so Control-A is line start there, not select all. The command line is a
readline prompt and keeps Ctrl/Cmd+A as line start on every platform.

The clipboard is :mod:`emtk.clipboard` (``copy`` / ``paste``): Qt hosts use
``QClipboard``, the Tk host its root, a glfw window glfw's clipboard, other
native windows ``pbcopy``/``pbpaste``, ``wl-copy``/``xclip`` or ``clip``/
``Get-Clipboard``. In a page ``boot.js`` lets the browser raise its
``copy``/``cut``/``paste`` events for Cmd/Ctrl+C/X/V and forwards them with
their text (``WebPage.copy`` / ``WebPage.paste``), preventing the browser's
default only when the app took the shortcut.

Colour
------

``widgets.color`` ports the reference's colour family: a swatch
(:class:`ColorButton`), a numeric editor (:class:`ColorEdit4` and
:class:`ColorEditRGB`), and a saturation/value picker with a hue bar
(:class:`ColorPicker4`). The hue-state bug is avoided structurally:
:class:`ColorState` holds H, S, V and the byte triple side by side, so a
drag on the hue bar cannot snap to red at the white or black edge.

Selection
----------

``widgets.selection`` ports :class:`Selectable`,
:class:`CollapsingHeader`, and the multi-select model
(:class:`MultiSelectState`) that turns clicks plus modifiers into
selection requests.

.. image:: _screenshots/selection.png
   :alt: Collapsing headers and selectable rows

::

    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 300, 200)):
        im.begin("Selection")
        im.selectable("option A")
        im.selectable("option B")
        im.collapsing_header("Section")
        im.end()

    assert "option A" in painter.strings

List view
----------

``widgets.list_view`` provides virtualised lists: the view asks the model
for the rows it is about to draw and no others, so a list of a hundred
thousand rows costs the same as a list of twenty.

Menus
------

``widgets.menus`` ports :class:`MenuBar`, :class:`Menu`,
:class:`MenuItem`, :class:`Popup`, and :class:`PopupModal`.

.. image:: _screenshots/menus.png
   :alt: A menu bar with the View menu open, its items showing shortcuts

Tabs
----

``widgets.tabs`` ports the reference's full tab bar: measured per-tab
widths, shrinking (the widest tab pays first), scrolling (with the
selected tab kept visible), and reordering by drag.

.. image:: _screenshots/tabs.png
   :alt: A tab bar with three tabs, the first selected

Tables
------

``widgets.tables`` ports the reference's data table: sized, resized,
reordered, multi-sorted, frozen, clipped.

.. image:: _screenshots/table.png
   :alt: A data table with three columns and four rows

::

    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 300, 200)):
        im.begin("Table")
        im.begin_table("t", 3)
        for col in range(3):
            im.table_setup_column(f"Col {col}")
        im.table_headers_row()
        im.table_next_row()
        for col in range(3):
            im.table_next_column()
            im.text(f"{col}")
        im.end_table()
        im.end()

Declared tables
---------------

``widgets.data_table`` draws the tables a ChiSurf ``view.json`` declares --
``{"type": "table"}`` and ``{"type": "custom", "key": "data_table"}`` -- the
way AutoForm's Qt renderer reads them: records or named arrays from a model
``source``, column specs, values sorted as values, selection into
``selected_call``, and a refresh that notices a source growing while a
computation streams. A column with ``"display": "bar"`` and a ``range`` draws
its value as a bar under the text (diverging, coloured by sign, when the range
spans zero). :func:`emtk.widgets.view_spec.table_bindings` and
:class:`emtk.widgets.view_spec.ViewSpecPanel` render them from a retained
panel; :mod:`emtk.view_form` draws them in an immediate-mode form.

``ViewSpecPanel`` hosts an inner ``ImApp`` and uses ``view_form.draw_sections``
for its settings. A spec's ``n_col`` packs fields into rows, and their ``weight``
shares the available width; ``width``, ``min_width`` and ``wrap_before`` follow
the same rules as an immediate-mode form. For example, two fields with weights
1 and 3 receive control widths in a 1:3 ratio when their minimum widths fit.
A ``button_row`` with ``weight: 1`` stretches to fill its row.
When a numeric section omits ``style``, the panel preserves its former integer
stepper or float slider, with default bounds 0–100 or 0–1 respectively. An
explicit ``style`` wins. This normalization uses a copy of the section and does
not change the spec or the defaults of ``view_form.draw_form``.

The panel retains the group selector and setting search above the fields.
Descriptions are hover tooltips. Tables retain filtering, sorting, selection
callbacks and source refresh, with expanding tables sharing the remaining
height. Pointer and keyboard events are applied on the next ``draw``, following
the usual ``ImApp`` contract. Table cell editors and filters preserve the
host-normalized keyboard modifiers: Ctrl+A (Command+A on macOS) selects all,
and typing replaces the selection. Enter commits a cell; Escape cancels it.
``item_rects`` exposes the current named controls
for tours and ``emtk.testing.Driver``. ``visible_rows`` remains accepted by the
constructor; the form now scrolls with its window instead of limiting its rows.

::

    from emtk.widgets.data_table import TableBinding

    class Ranking:
        def rows(self):
            return [{"score": 0.8, "x": "Tau"}, {"score": -0.3, "x": "N"}]

    section = {"type": "custom", "key": "data_table", "options": {
        "source": "rows", "sort": {"key": "score", "descending": True},
        "columns": [{"key": "score", "display": "bar", "range": [-1, 1]},
                    {"key": "x"}]}}
    binding = TableBinding(section, Ranking())
    painter = RecordingPainter()
    binding.control.draw(painter, 0, 0, 300, 120)
    assert "Tau" in painter.strings

Drag and drop
-------------

``widgets.dragdrop`` ports the reference's drag-and-drop: :class:`Payload`,
:class:`DragDropSource`, :class:`DragDropTarget`, and the
:class:`DragDropContext` state machine.

Text editor
------------

``widgets.text_editor`` is the port of ImGuiColorTextEdit: a colourising
text editor with syntax highlighting, bracket matching, undo/redo, and
multiple cursors.

Memory editor
--------------

``widgets.memory_editor`` ports the imgui_club memory editor: a hex viewer
and editor for any buffer the host provides.

Layout
-------

``layout`` carries the layout cursor: the arithmetic that decides where the
next widget goes.

:func:`~emtk.im_widgets.splitter` is the draggable divider between two
resizable panes, and :func:`~emtk.im_widgets.splitter_behavior` is the drag
on its own for a window that draws its own bar. The sizes come back rather
than being written through pointers, as everywhere else in ``im``:

.. doctest::

    >>> import emtk
    >>> from emtk.testing import RecordingPainter
    >>> state = {"left": 150.0, "right": 242.0}
    >>> def two_panes():
    ...     im.begin("panes")
    ...     x, y = im.get_cursor_screen_pos()
    ...     im.begin_child((x, y, state["left"], 200.0))
    ...     im.text("controls")
    ...     im.end_child()
    ...     im.same_line(0.0, 0.0)
    ...     moved, state["left"], state["right"] = im.splitter(
    ...         "##v", im.Axis.X, 12.0, 200.0,
    ...         state["left"], state["right"], 60.0, 80.0)
    ...     im.same_line(0.0, 0.0)
    ...     im.end()
    ...     return moved
    >>> with emtk.frame(RecordingPainter(), (0, 0, 400, 300)):
    ...     moved = two_panes()
    >>> moved, state["left"], state["right"]
    (False, 150.0, 242.0)

``thickness`` is the space the divider takes and the size of the grab
target; ``bar_margin`` insets what is actually drawn, so a bar that is easy
to hit does not have to look like a slab. ``min_size1`` and ``min_size2``
both hold at once, so a drag stops at whichever limit it reaches first
instead of collapsing the other pane.

Splitter
---------

``widgets.splitter`` is the same control retained: it owns the boundary, and
:meth:`~emtk.widgets.splitter.Splitter.split` hands back the three rectangles
a two-pane layout is made of, already clamped.

.. doctest::

    >>> from emtk.widgets.splitter import Splitter
    >>> sp = Splitter(150.0, thickness=12.0, min_size1=60.0, min_size2=80.0)
    >>> pane1, bar, pane2 = sp.split(0.0, 0.0, 400.0, 300.0)
    >>> pane1, bar, pane2
    ((0.0, 0.0, 150.0, 300.0), (150.0, 0.0, 12.0, 300.0), (162.0, 0.0, 238.0, 300.0))

They tile the region exactly. A resize too small for the starting sizes
clamps rather than inverting a pane -- and when the region cannot hold both
minimums at once, the first pane keeps its own and the second is squeezed
below it, which is arbitrary but stable. The alternative is a boundary that
jumps between the two limits as the window resizes:

.. doctest::

    >>> pane1, bar, pane2 = sp.split(0.0, 0.0, 150.0, 300.0)
    >>> sp.size1, sp.size2
    (60.0, 78.0)
    >>> pane1[2] + bar[2] + pane2[2]
    150.0

Control
--------

``control`` defines the :class:`~emtk.control.Control` base class: the
contract every retained control follows.

Axis and markers
-----------------

``widgets.axis`` ports the implot linear axis.
``widgets.markers`` provides scatter-plot marker shapes.

Plot
----

``widgets.plot`` ports the implot ``BeginPlot`` / ``PlotLine`` /
``EndPlot`` pattern as a context manager.

.. image:: _screenshots/plot.png
   :alt: A line plot with two series, gridlines and a legend

::

    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 300, 200)):
        im.begin("Plot")
        im.end()

    assert painter is not None

ImPlot
------

``implot`` is ImPlot's 2-D library, ported whole and spelled the way a C++
port reads (``begin_plot`` / ``setup_axes`` / ``plot_line`` / ``end_plot``,
and every ``ImPlot*_`` constant): line, scatter, bubbles, polygons, stairs,
shaded bands, bars and bar groups (stacked too), error bars, stems, infinite
lines, pie charts, heatmaps, 1-D and 2-D histograms, digital signals, images,
text, annotations, tags and legend-only items; six axes with linear, time,
log10, symlog and custom scales, inversion, formats, custom ticks, links,
constraints and equal aspect; subplots with linked axes and a shared legend;
all sixteen built-in colormaps with the colormap scale, slider and button;
and the interaction -- left drag pans, the wheel zooms about the cursor, right
drag box-selects, a double click fits, an axis drags and zooms alone, a legend
entry click hides its item, right click opens the plot, axis and legend menus
-- plus ``drag_point``/``drag_line_x``/``drag_line_y``/``drag_rect``, which
return ``(modified, value..., clicked, hovered, held)``.
``implot_demo.show_demo_window()`` is the reference demo, section for section.
Beyond ImPlot it takes a dash pattern in ``PlotSpec(dash=(on, off))`` (and the
obsolete ``set_next_line_style(colour, weight, dash=...)``).

.. image:: _screenshots/implot.png
   :alt: An ImPlot plot with bars, a shaded band, a line, error bars and a legend

::

    from emtk import implot

Plot3D
------

``implot3d`` is ImPlot3D, ported whole: a rotatable 3-D box with ticks and
labels on its outer edges, scatter, line, triangle, quad, surface, mesh (the
reference's cube, sphere and duck included), image and text items, legends,
colormaps, and the reference's mouse bindings -- left drag pans, the wheel
zooms, right drag rotates, a double right click snaps to a face or back to the
initial view. Every item is projected into triangles, sorted back to front and
drawn through the painter, so it runs on every host;
``implot3d_demo.show_demo_window()`` is the reference's demo, section for
section.

.. image:: _screenshots/plot3d.png
   :alt: A colormapped surface in ImPlot3D's rotated box

::

    from emtk import implot3d

    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 420, 420)):
        im.begin("Plot3D")
        if implot3d.begin_plot("Line"):
            implot3d.setup_axes("x", "y", "z")
            implot3d.plot_line("helix", [0.0, 0.5, 1.0], [0.0, 1.0, 0.0], [0.0, 0.5, 1.0])
            implot3d.end_plot()
        im.end()

    assert painter.triangles

File dialog
-----------

``file_dialog.FileDialog`` chooses files to open or a file to save, drawn by
emtk inside any window: filters (the chosen one comes back as
``filter_index``), multi-selection, a save-mode name field that appends the
filter's extension, and paging. Dear ImGui has none, a browser host has no
native one, and a test cannot press a native dialog's buttons.

::

    from emtk.file_dialog import FileDialog

    dialog = FileDialog("Load", filters="Sessions (*.mat);;Raw (*.dat)")
    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 400, 400)):
        im.begin("Load")
        result = dialog.draw()
        im.end()

    assert result is None

Circle plot
------------

``widgets.circle`` is a Circos-style circular layout, ported from
pyCirclize.

DrawList
---------

``drawlist`` provides ``ImDrawList`` names over any :class:`Painter`:
``add_line``, ``add_rect_filled``, ``add_circle_filled``.

::

    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 300, 200)):
        im.begin("DrawList")
        dl = im.get_window_draw_list()
        dl.add_rect_filled(10, 10, 80, 40, (80, 80, 80, 255))
        im.end()

    assert painter.fills

View declaration vocabulary
----------------------------

``emtk.view_form.COMMON_KEYS`` and ``SECTION_KEYS`` describe the keys consumed
by the immediate-mode form readers. ``TABLE_KEYS`` is the shared table's
option vocabulary; ``VIEW_KEYS`` describes a form envelope. Client validators
can combine these with their own loader or preprocessing contracts without
copying a second toolkit key list. Type-specific keys stay scoped: a choice
uses ``style`` rather than ``kind``, and an info field does not declare grid
columns. ``tests/test_view_form_schema.py`` guards every literal section read
in both form and view-spec readers so a new read cannot silently outrun the
published dialect.


Translatable form fields
------------------------

``emtk.view_form.TEXT_KEYS`` exports the immutable JSON vocabulary carrying
user-facing form text. Extractors should include labels, descriptions, hints,
placeholders, units, numeric ``special_text`` and displayed choice values when
explicit labels are absent. Binding keys (``attr``, ``source``, ``call`` and
``action``) identify model APIs and should not enter translation catalogues.
The declaration does not change rendering; it gives schema/translation tools
the same text contract as the renderer.
