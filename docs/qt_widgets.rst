Qt widget inventory
===================

emtk replaced Qt in ChiSurf, so the question a port asks first is "what is
``QSomething`` here?". This page answers it for Qt's standard widget set: the
emtk spelling where one exists, what was added to close a gap, and what is
deliberately not provided because immediate mode (or another emtk control)
already covers it. ``im.x`` is :mod:`emtk.im`; the retained controls are the
classes under ``emtk.widgets``.

.. contents::
   :local:

Inputs and values
-----------------

.. list-table::
   :header-rows: 1
   :widths: 22 45 33

   * - Qt
     - emtk
     - notes
   * - ``QPushButton``
     - ``im.button`` (``role=`` primary / danger), ``im.action_button``
     - :class:`~emtk.widgets.basic.Button`
   * - ``QToolButton`` (checkable)
     - ``im.toggle_button``, ``im.small_button``, ``im.arrow_button``, ``im.image_button``
     -
   * - ``QCheckBox``
     - ``im.checkbox``, ``im.checkbox_flags``
     - :class:`~emtk.widgets.basic.Checkbox`
   * - ``QCheckBox`` tristate
     - ``im.checkbox_tristate``
     - **added**; ``None`` is partial
   * - ``QRadioButton``
     - ``im.radio_button``
     - :class:`~emtk.widgets.buttons.RadioButton`
   * - ``QButtonGroup``
     - ``im.radio_button(label, v, value)``
     - the shared ``v`` is the group
   * - ``QSlider``
     - ``im.slider_float`` / ``slider_int``, ``im.v_slider_float``, ``im.slider_angle``
     - :mod:`emtk.widgets.sliders`
   * - ``QScrollBar``
     - child windows scroll themselves; ``im.set_scroll_y``
     - :class:`~emtk.widgets.basic.ScrollBar`
   * - ``QDial``
     - ``im.dial``
     - **added** (:mod:`emtk.widgets.instruments`)
   * - ``QSpinBox``
     - ``im.input_int`` (with ``step``), ``im.drag_int``
     - a form ``value`` with ``style: "spin"``
   * - ``QDoubleSpinBox``
     - ``im.input_float`` / ``input_double``, ``im.drag_float``
     -
   * - ``QLineEdit``
     - ``im.input_text``, ``input_text_with_hint``
     - ``PASSWORD`` flag for echo mode
   * - ``QLineEdit`` + completer
     - ``im.input_text_completer``
     - **added**; ``QCompleter``'s popup
   * - ``QCompleter``
     - ``im.input_text_completer``, :class:`~emtk.widgets.command_line.CommandLine`
     - the command line completes by prefix
   * - ``QTextEdit`` / ``QPlainTextEdit``
     - ``im.input_text_multiline``, :class:`~emtk.widgets.text_editor.TextEditor`
     - undo/redo, folding, find
   * - ``QComboBox``
     - ``im.combo``, ``begin_combo`` / ``end_combo``
     - a filter field for long lists
   * - ``QComboBox`` (editable)
     - :class:`~emtk.widgets.combo.EditableComboBox`, a form ``choice`` with ``editable: true`` ``im.input_text_completer``
     -
   * - ``QFontComboBox``
     - ``im.show_font_selector``
     - :mod:`emtk.fonts`
   * - ``QKeySequenceEdit``
     - ``im.key_sequence_input``
     - **added**; value is an ``im`` chord
   * - ``QDateEdit``
     - ``im.date_input``
     - **added** (:mod:`emtk.widgets.calendar`)
   * - ``QTimeEdit``
     - ``im.time_input``
     - **added**
   * - ``QDateTimeEdit``
     - ``im.datetime_input``
     - **added**
   * - ``QCalendarWidget``
     - ``im.calendar``
     - **added**
   * - ``QColorDialog``
     - ``im.color_picker3`` / ``color_picker4``, ``im.color_edit3``, ``im.color_button``
     - a form ``value`` of ``kind: "color"``

Display
-------

.. list-table::
   :header-rows: 1
   :widths: 22 45 33

   * - Qt
     - emtk
     - notes
   * - ``QLabel``
     - ``im.text`` and its variants, ``im.label_text``, ``im.text_link``
     - rich text: ``im.markdown``
   * - ``QTextBrowser``
     - ``im.markdown``, :mod:`emtk.htmltext`, :class:`~emtk.help_guide.EmTkHelpWindow`
     - links, tables, code blocks
   * - ``QLCDNumber``
     - ``im.lcd_number``
     - **added**; seven segments, not a font
   * - ``QProgressBar``
     - ``im.progress_bar``, :class:`~emtk.widgets.progress.ProgressOverlay`
     - indeterminate in a form ``progress``
   * - ``QToolTip``
     - ``im.set_item_tooltip``, ``im.set_tooltip``
     - :mod:`emtk.tooltip`
   * - ``QWhatsThis``
     - ``?`` help: :mod:`emtk.help_guide`
     - and guided tours
   * - ``QListView`` / ``QListWidget``
     - ``im.list_box``, ``im.selectable``, ``begin_multi_select``
     - :class:`~emtk.widgets.list_view.ListView`
   * - ``QTreeView`` / ``QTreeWidget``
     - ``im.tree_node``, ``im.collapsing_header``
     - :class:`~emtk.widgets.list_view.TreeView`, a data table with ``tree_key``
   * - ``QTableView`` / ``QTableWidget``
     - ``im.begin_table``, :class:`~emtk.widgets.data_table.DataTable`
     - :mod:`emtk.widgets.data_table`
   * - ``QGraphicsView``
     - :mod:`emtk.implot`, :mod:`emtk.nodes`, ``im.image``, the draw list
     - a painter is the canvas
   * - ``QRubberBand``
     - ImPlot's box select, the node editor's marquee
     - a ``DrawList`` rectangle elsewhere

Containers and windows
----------------------

.. list-table::
   :header-rows: 1
   :widths: 22 45 33

   * - Qt
     - emtk
     - notes
   * - ``QGroupBox``
     - ``im.separator_text``, a form ``box`` / ``panel``
     - collapsible with ``collapsible: true``
   * - ``QToolBox``
     - ``im.begin_tool_box`` / ``tool_box_item`` / ``end_tool_box``
     - **added**; one page open at a time
   * - ``QTabWidget`` / ``QTabBar``
     - ``im.begin_tab_bar`` / ``begin_tab_item``
     - :mod:`emtk.widgets.tabs`; form ``tabs``
   * - ``QStackedWidget``
     - not needed: an ``if`` on the page index
     - immediate mode draws only what it is asked
   * - ``QScrollArea``
     - ``im.begin_child``
     - scrolls with wheel and bar
   * - ``QSplitter``
     - ``im.splitter``, :class:`~emtk.widgets.splitter.Splitter`
     - :class:`~emtk.widgets.pane_stack.PaneStack` for more than two panes
   * - ``QFrame``
     - ``im.begin_child`` with a border, ``im.separator``
     - ``im.separator`` for ``HLine``
   * - ``QDockWidget``
     - :mod:`emtk.docking`
     - snap, tabs, saved layouts
   * - ``QMainWindow``
     - :class:`~emtk.app.ImApp` with a dock manager
     - menu bar: ``im.begin_main_menu_bar``
   * - ``QMdiArea``
     - floating windows of :mod:`emtk.docking`
     - a workspace of free windows
   * - ``QMenu`` / ``QMenuBar``
     - ``im.begin_menu`` / ``menu_item``, ``begin_popup_context_item``
     - :mod:`emtk.widgets.menus`
   * - ``QToolBar``
     - :mod:`emtk.ribbon`, a form ``button_row``
     - a row of ``im`` buttons
   * - ``QStatusBar``
     - not a widget: a line of ``im.text`` at the bottom of the window
     - the window's own layout is the bar
   * - ``QDialog``
     - :class:`~emtk.dialog_window.DialogWindow`
     - modal backdrop, close button
   * - ``QMessageBox``
     - :class:`~emtk.message_dialog.MessageDialogs` ``message``, ``confirm``, ``choice``
     -
   * - ``QInputDialog``
     - ``MessageDialogs.text``
     - a number: a small form in a dialog
   * - ``QFileDialog``
     - :class:`~emtk.file_dialog.FileDialog`
     - filters, recent places
   * - ``QFontDialog``
     - ``im.show_font_selector``
     - the font is the interface's, not a document's
   * - ``QWizard``
     - not a widget: a form whose ``visible`` follows a step, with Back / Next buttons
     - AutoForm's ``wizard`` section in ChiSurf
   * - ``QUndoView``
     - not provided: undo lives in the model; the text editor has its own
     - a ``list_box`` of the history if wanted

Why the gaps were filled the way they were
------------------------------------------

The added controls are the ones a scientific desktop tool reaches for and
cannot build from two ``im`` calls: a calendar (measurements are filed and
filtered by acquisition day), date and time fields, a knob and a readout for
instrument panels, the partial state of a "select all" box, a field that
completes from a known list (dye names, sample ids), a shortcut editor for a
preferences page, and a tool box for a tall settings column. Each is spelled the
``im`` way -- the value in, ``(changed, value)`` out -- uses the theme's
colours, sits in the keyboard navigation ring, and takes a
``set_item_tooltip`` after it.

Left out on purpose: ``QStackedWidget`` (an ``if``), ``QStatusBar`` and
``QWizard`` (layouts, not widgets, in immediate mode), ``QUndoView`` (undo is
the model's), and ``QMdiArea`` (the docking workspace already floats windows).
