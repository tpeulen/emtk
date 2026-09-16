"""Dear ImGui's "Hello, world!", in emtk.

Run it::

    python examples/emtk/hello_world.py

Beside each line is the C++ it was transliterated from
(``imgui/examples/example_glfw_opengl3/main.cpp``). The translation is
mechanical: ``ImGui::`` becomes ``emtk.``, ``CamelCase`` becomes ``snake_case``,
and a ``bool*``/``float*`` argument becomes a returned value.
"""
import emtk
from emtk.testing import RecordingPainter


def gui(state, painter):
    with emtk.frame(painter, (0.0, 0.0, 320.0, 200.0), io=state["io"],
                  storage=state["storage"]):
        emtk.begin("Hello, world!")                       # ImGui::Begin(...)
        emtk.text("This is some useful text.")            # ImGui::Text(...)
        _, state["demo"] = emtk.checkbox(                 # ImGui::Checkbox(...)
            "Demo Window", state["demo"])
        _, state["f"] = emtk.slider_float(                # ImGui::SliderFloat(...)
            "float", state["f"], 0.0, 1.0)
        if emtk.button("Button"):                         # if (ImGui::Button(...))
            state["counter"] += 1
        emtk.same_line()                                  # ImGui::SameLine();
        emtk.text("counter = %d" % state["counter"])      # ImGui::Text(...)
        emtk.end()                                        # ImGui::End();


def main() -> None:
    # Any Painter will do -- a real one draws; this one records, which is what
    # makes a widget testable without a window.
    state = {"io": emtk.IO(), "storage": {}, "demo": True, "f": 0.5, "counter": 0}
    painter = RecordingPainter()
    gui(state, painter)
    print(f"{len(painter.calls)} draw calls")
    for line in painter.strings:
        print(f"  {line}")


if __name__ == "__main__":
    main()
