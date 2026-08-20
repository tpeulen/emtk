"""Dear ImGui's "Hello, world!", in cmtk.

Run it::

    python examples/cmtk/hello_world.py

Beside each line is the C++ it was transliterated from
(``imgui/examples/example_glfw_opengl3/main.cpp``). The translation is
mechanical: ``ImGui::`` becomes ``cmtk.``, ``CamelCase`` becomes ``snake_case``,
and a ``bool*``/``float*`` argument becomes a returned value.
"""
import cmtk
from cmtk.testing import RecordingPainter


def gui(state, painter):
    with cmtk.frame(painter, (0.0, 0.0, 320.0, 200.0), io=state["io"],
                  storage=state["storage"]):
        cmtk.begin("Hello, world!")                       # ImGui::Begin(...)
        cmtk.text("This is some useful text.")            # ImGui::Text(...)
        _, state["demo"] = cmtk.checkbox(                 # ImGui::Checkbox(...)
            "Demo Window", state["demo"])
        _, state["f"] = cmtk.slider_float(                # ImGui::SliderFloat(...)
            "float", state["f"], 0.0, 1.0)
        if cmtk.button("Button"):                         # if (ImGui::Button(...))
            state["counter"] += 1
        cmtk.same_line()                                  # ImGui::SameLine();
        cmtk.text("counter = %d" % state["counter"])      # ImGui::Text(...)
        cmtk.end()                                        # ImGui::End();


def main() -> None:
    # Any Painter will do -- a real one draws; this one records, which is what
    # makes a widget testable without a window.
    state = {"io": cmtk.IO(), "storage": {}, "demo": True, "f": 0.5, "counter": 0}
    painter = RecordingPainter()
    gui(state, painter)
    print(f"{len(painter.calls)} draw calls")
    for line in painter.strings:
        print(f"  {line}")


if __name__ == "__main__":
    main()
