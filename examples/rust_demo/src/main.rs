//! Pure Rust EMTK Application Example

use emtk_core::{
    types::{Color, Rect, Vec2},
    context::Context,
    software_painter::SoftwarePainter,
    quad_painter::QuadPainter,
    docking::{DockSpace, SplitDir},
};
use emtk_implot as implot;
use emtk_imnodes as imnodes;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("=== EMTK Pure Rust Native Showcase ===");
    println!("EMTK Core Version: {}", emtk_core::version());

    let mut ctx = Context::new();

    // 1. Render Immediate-Mode UI & ImPlot Scientific Plot
    {
        let mut painter = SoftwarePainter::new(360, 260, Color::rgba(25, 27, 34, 255));
        let mut show_grid = true;
        let mut gain = 0.72f32;
        let mut click_count = 5;

        ctx.new_frame_with_painter(&mut painter, 1.0 / 60.0, 360.0, 260.0);

        if ctx.begin_window("Experiment Controller", None, 0) {
            ctx.text_unformatted("Native EMTK running in pure Rust!");
            ctx.checkbox_simple("Enable TCSPC Sync", &mut show_grid);
            ctx.slider_float_simple("Detector Gain", &mut gain, 0.0, 1.0, "%.3f");

            if ctx.button_simple("Trigger Laser", Vec2::ZERO) {
                click_count += 1;
            }
            ctx.same_line(0.0, -1.0);
            ctx.text_unformatted(&format!("triggers = {}", click_count));

            ctx.separator_simple();

            // ImPlot 2D Scientific Plotting in Rust
            if implot::begin_plot(&mut ctx, "Decay Profile", Vec2::new(320.0, 130.0), 0) {
                implot::setup_axes("Time (ns)", "Counts");
                let xs = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0];
                let ys = [1200.0, 727.8, 441.4, 267.7, 162.4, 98.5, 59.7, 36.2, 22.0, 13.3];
                implot::plot_line("Decay", &xs, &ys);
                implot::end_plot(&mut ctx);
            }

            ctx.end_window();
        }

        ctx.end_frame();

        let out_png = "rust_frame.png";
        painter.save_png(out_png)?;
        println!("Successfully rendered UI & ImPlot frame to {}", out_png);
    }

    // 2. Render Interactive Node Editor with ImNodes in Rust
    {
        let mut editor = imnodes::EditorContext::new();
        let mut node_painter = SoftwarePainter::new(640, 480, Color::rgba(22, 24, 30, 255));

        imnodes::begin_node_editor(&mut editor, Rect::new(10.0, 10.0, 620.0, 460.0));

        // Node 1: Pulsed Laser Source
        editor.set_node_grid_space_pos(1, Vec2::new(40.0, 60.0));
        imnodes::begin_node(&mut editor, 1);
        imnodes::begin_node_title_bar(&mut editor);
        imnodes::end_node_title_bar(&mut editor);
        imnodes::begin_output_attribute(&mut editor, 10, imnodes::PinShape::Circle);
        imnodes::end_output_attribute(&mut editor);
        imnodes::end_node(&mut editor);

        // Node 2: Hybrid APD Detector
        editor.set_node_grid_space_pos(2, Vec2::new(340.0, 150.0));
        imnodes::begin_node(&mut editor, 2);
        imnodes::begin_node_title_bar(&mut editor);
        imnodes::end_node_title_bar(&mut editor);
        imnodes::begin_input_attribute(&mut editor, 20, imnodes::PinShape::Circle);
        imnodes::end_input_attribute(&mut editor);
        imnodes::end_node(&mut editor);

        // Link output of Node 1 to input of Node 2
        imnodes::link(&mut editor, 101, 10, 20);

        imnodes::end_node_editor(&mut ctx, &mut node_painter, &mut editor);

        let out_node_png = "rust_node_editor.png";
        node_painter.save_png(out_node_png)?;
        println!("Successfully rendered ImNodes dataflow graph to {}", out_node_png);
    }

    // 3. Multi-Window Docking in Rust
    {
        let mut dockspace = DockSpace::new(1);
        dockspace.set_rect(Rect::new(0.0, 0.0, 1280.0, 720.0));

        let mut left_node = 0;
        let mut right_node = 0;
        dockspace.split_node(1, SplitDir::Left, 0.25, &mut left_node, &mut right_node);

        dockspace.dock_window("Instruments", left_node);
        dockspace.dock_window("Data Viewer", right_node);

        assert!(dockspace.is_window_tab_active("Instruments"));
        assert!(dockspace.is_window_tab_active("Data Viewer"));
        println!("DockSpace successfully partitioned: Left ({}), Right ({})", left_node, right_node);
    }

    // 4. Single-Draw-Call GPU Quad Batching in Rust
    {
        let mut quad_painter = QuadPainter::new();
        ctx.new_frame_with_painter(&mut quad_painter, 1.0 / 60.0, 360.0, 260.0);

        if ctx.begin_window("GPU Window", None, 0) {
            ctx.text_unformatted("Emitting WebGPU quads directly in Rust");
            ctx.button_simple("Batch Submit", Vec2::new(120.0, 24.0));
            ctx.end_window();
        }
        ctx.end_frame();

        let count = quad_painter.vertex_count();
        println!("QuadPainter produced {} vertices ({} quads) in 1 draw call buffer.",
                 count, count / 6);
        assert!(count > 0 && count % 6 == 0);
    }

    println!("All Pure Rust EMTK features verified successfully!");
    Ok(())
}
