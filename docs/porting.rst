Porting from Dear ImGui
========================

The translation is mechanical. Three rules and no thought:

- ``ImGui::Button("Save")`` → ``im.button("Save")`` — ``::`` becomes ``.``
- ``ImGui::SliderFloat`` → ``im.slider_float`` — ``CamelCase`` becomes ``snake_case``
- ``ImGui::Checkbox("x", &b)`` → ``changed, b = im.checkbox("x", b)``

The third is the only place Python forces a difference: C++ writes results
through ``bool*`` and ``float*``, and Python has no pointers, so the value
comes back beside the changed flag. That is what pyimgui and imgui-bundle
do, so a port from C++ *or* from either binding lands unchanged.

Enums follow the same rule: ``ImGuiCol_Button`` → ``im.Col.BUTTON``,
``ImGuiDir_Left`` → ``im.Dir.LEFT``,
``ImGuiItemFlags_ButtonRepeat`` → ``im.ItemFlags.BUTTON_REPEAT``.

All 362 published ``ImGui::`` names and all 60 ``ImDrawList::`` methods
translate, and all 187 sections of ``imgui_demo.cpp`` are ported and
driven as tests — including docking, keyboard navigation, table sizing
and ``ImGuiListClipper``. ``tests/test_imgui_api_coverage.py`` and
``tests/test_imgui_demo_remaining.py`` prove both, and neither figure may
fall.

That is not decoration. Porting the reference's own demo is how the
toolkit was found to be wrong twenty-two times — a label claiming a
full-width item so the buttons beside it were dead,
``IsItemDeactivated`` firing for widgets nobody had touched,
``TableNextColumn`` one column out of step, ``ImVec2(120, 0)`` taken
literally so a button was zero pixels tall. A port that runs is the only
evidence that a re-implementation matches.

Mechanical auto-porting
-----------------------

``tools/autoport`` ports Dear ImGui C++ to emtk mechanically — the same
rules a person applies, written down so they apply the same way every
time. See ``README.md`` for the full account.

AutoForm tab pages
------------------

A ``tabs`` section renders its child ``tab`` sections as native emtk headers.
Only the selected page's ordinary AutoForm controls are drawn. Mouse clicks and
keyboard focus followed by Enter or Space select a page; no host adapter is
needed. ``FormState`` remembers the selected page when a host reopens the form.

Give the bar and each page a stable ``key``. The header's guided-tour and test
rectangle is ``<bar key>.<page key>`` (for example ``simulator.preview``); a
missing key falls back to the section's title. Page ``description`` strings
become header tooltips. Titles and descriptions are translated for display,
while keys and model attributes stay unchanged. Field widget identities are
scoped to their bar and page, and inactive pages retire their control targets.
Leaving a page commits pending declared value fields through the normal parser,
runtime bounds and callbacks before its replacement page is drawn. Custom
sections own any nested form state and its pending edits themselves.
