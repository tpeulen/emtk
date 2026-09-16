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
