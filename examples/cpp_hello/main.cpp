#include "emtk.hpp"
#include <iostream>

int main() {
    std::cout << "EMTK C++ Library Version: " << emtk_version() << std::endl;

    emtk::Context ctx;
    ctx.SetCurrent();

    emtk::SoftwarePainter painter(320, 240, 30, 32, 38, 255);

    bool show_demo = true;
    float alpha = 0.35f;
    int counter = 0;

    {
        emtk::Frame frame(painter, 320.0f, 240.0f);

        if (emtk::Begin("Hello, C++ world!")) {
            emtk::Text("This is EMTK running natively in C++!");
            emtk::Checkbox("Show Demo", &show_demo);
            emtk::SliderFloat("alpha", &alpha, 0.0f, 1.0f);

            if (emtk::Button("Click Me")) {
                counter++;
            }
            emtk::SameLine();
            emtk::Text((std::string("counter = ") + std::to_string(counter)).c_str());

            emtk::Separator();

            // ImPlot C++ native scientific plotting
            if (emtk::plot::BeginPlot("Decay Curve", 280.0f, 120.0f)) {
                emtk::plot::SetupAxes("Time (ns)", "Photons");
                double xs[] = {0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0};
                double ys[] = {1000.0, 606.5, 367.8, 223.1, 135.3, 82.0, 49.7, 30.1, 18.3, 11.1};
                emtk::plot::PlotLine("Fluorescence", xs, ys, 10);
                emtk::plot::EndPlot();
            }

            emtk::End();
        }
    }

    std::string out_png = "cpp_frame.png";
    if (painter.SavePNG(out_png)) {
        std::cout << "Successfully rendered C++ frame to " << out_png << std::endl;
    } else {
        std::cerr << "Failed to write PNG output" << std::endl;
        return 1;
    }

    // Verify Docking & DockBuilder in C++
    {
        emtk::dock::DockSpace ds(100);
        ds.SetRect(0.0f, 0.0f, 800.0f, 600.0f);
        uint32_t left_id = 0, right_id = 0;
        ds.SplitNode(100, emtk::dock::SplitDir::Left, 0.25f, &left_id, &right_id);
        ds.DockWindow("Hierarchy", left_id);
        ds.DockWindow("Viewport", right_id);
        std::cout << "C++ DockSpace split into Left (" << left_id << ") and Right (" << right_id << ") successfully." << std::endl;
        if (!ds.IsWindowActive("Hierarchy") || !ds.IsWindowActive("Viewport")) {
            std::cerr << "Failed DockSpace active window query" << std::endl;
            return 1;
        }
    }

    // Verify ImNodes Immediate-Mode Node Editor in C++
    {
        emtk::nodes::EditorContext editor;
        editor.SetCurrent();

        emtk::SoftwarePainter node_painter(640, 480, 24, 27, 34, 255);
        {
            emtk::Frame frame(node_painter, 640.0f, 480.0f);
            emtk::nodes::BeginNodeEditor(10.0f, 10.0f, 620.0f, 460.0f);

            // Node 1: Photon Source
            emtk::nodes::SetNodeGridSpacePos(1, 40.0f, 60.0f);
            emtk::nodes::BeginNode(1);
            emtk::nodes::BeginNodeTitleBar();
            emtk::Text("Laser Source");
            emtk::nodes::EndNodeTitleBar();
            emtk::nodes::BeginOutputAttribute(10);
            emtk::Text("Photons Out");
            emtk::nodes::EndOutputAttribute();
            emtk::nodes::EndNode();

            // Node 2: TCSPC Detector
            emtk::nodes::SetNodeGridSpacePos(2, 320.0f, 140.0f);
            emtk::nodes::BeginNode(2);
            emtk::nodes::BeginNodeTitleBar();
            emtk::Text("TCSPC Detector");
            emtk::nodes::EndNodeTitleBar();
            emtk::nodes::BeginInputAttribute(20);
            emtk::Text("Photons In");
            emtk::nodes::EndInputAttribute();
            emtk::nodes::EndNode();

            // Link node 1 output to node 2 input
            emtk::nodes::Link(101, 10, 20);

            emtk::nodes::EndNodeEditor();
        }

        std::string node_png = "cpp_node_editor.png";
        if (node_painter.SavePNG(node_png)) {
            std::cout << "Successfully rendered C++ node editor to " << node_png << std::endl;
        } else {
            std::cerr << "Failed to write C++ node editor PNG output" << std::endl;
            return 1;
        }
    }

    // Also verify GPU QuadPainter vertex emission in C++
    {
        emtk::QuadPainter quad_painter;
        emtk::Frame frame(quad_painter, 320.0f, 240.0f);

        if (emtk::Begin("Quad Window")) {
            emtk::Text("GPU quad vertices in C++");
            emtk::Button("GPU Button");
            emtk::End();
        }

        std::cout << "C++ QuadPainter emitted " << quad_painter.VertexCount() << " vertices ("
                  << (quad_painter.VertexCount() / 6) << " quads) for 1-draw-call presentation." << std::endl;
        if (quad_painter.VertexCount() == 0 || (quad_painter.VertexCount() % 6) != 0) {
            std::cerr << "Invalid vertex count emitted by QuadPainter" << std::endl;
            return 1;
        }
    }

    std::cout << "C++ EMTK verified successfully!" << std::endl;
    return 0;
}
