//! EMTK Core Immediate-Mode GUI Engine

pub mod types;
pub mod painter;
pub mod software_painter;
pub mod quad_painter;
pub mod drawlist;
pub mod style;
pub mod context;
pub mod docking;

pub use types::*;
pub use painter::Painter;
pub use software_painter::SoftwarePainter;
pub use quad_painter::{QuadPainter, UiVertex, FLOATS_PER_VERTEX, VERTICES_PER_QUAD};
pub use drawlist::DrawList;
pub use style::Style;
pub use context::{Context, IO, Window};
pub use docking::*;

pub fn version() -> &'static str {
    "0.1.22"
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_immediate_mode_frame_lifecycle() {
        let mut ctx = Context::new();
        let mut painter = SoftwarePainter::new(320, 240, Color::rgb(30, 32, 38));

        let mut show_demo = true;
        let mut alpha = 0.35f32;
        let mut counter = 0;

        ctx.new_frame(1.0 / 60.0, 320.0, 240.0);

        if ctx.begin(&mut painter, "Hello, world!", None, 0) {
            ctx.text(&mut painter, "This is some useful text.");
            ctx.checkbox(&mut painter, "Show demo", &mut show_demo);
            ctx.slider_float(&mut painter, "alpha", &mut alpha, 0.0, 1.0, "%.3f");

            if ctx.button(&mut painter, "Button", Vec2::ZERO) {
                counter += 1;
            }
            ctx.same_line(0.0, -1.0);
            ctx.text(&mut painter, &format!("counter = {}", counter));

            ctx.end(&mut painter);
        }

        ctx.end_frame();

        assert_eq!(counter, 0);
        assert!(show_demo);
        assert!((alpha - 0.35).abs() < 0.001);

        // Verify window rendered
        assert_eq!(ctx.windows.len(), 1);
        assert_eq!(ctx.windows[0].name, "Hello, world!");
    }

    #[test]
    fn test_button_click_interaction() {
        let mut ctx = Context::new();
        let mut painter = SoftwarePainter::new(320, 240, Color::rgb(30, 32, 38));

        let mut counter = 0;

        // Frame 1: Mouse hovering over where the button will be and clicked
        ctx.io.mouse_pos = Vec2::new(20.0, 40.0);
        ctx.io.mouse_down[0] = true;
        ctx.io.mouse_clicked[0] = true;

        ctx.new_frame(1.0 / 60.0, 320.0, 240.0);
        if ctx.begin(&mut painter, "Window", None, 0) {
            if ctx.button(&mut painter, "ClickMe", Vec2::new(100.0, 25.0)) {
                counter += 1;
            }
            ctx.end(&mut painter);
        }
        ctx.end_frame();
        // Button not clicked until release
        assert_eq!(counter, 0);

        // Frame 2: Mouse released over the button
        ctx.io.mouse_down[0] = false;
        ctx.io.mouse_released[0] = true;

        ctx.new_frame(1.0 / 60.0, 320.0, 240.0);
        if ctx.begin(&mut painter, "Window", None, 0) {
            if ctx.button(&mut painter, "ClickMe", Vec2::new(100.0, 25.0)) {
                counter += 1;
            }
            ctx.end(&mut painter);
        }
        ctx.end_frame();

        // Button successfully clicked on release!
        assert_eq!(counter, 1);
    }

    #[test]
    fn test_quad_painter_vertex_emission() {
        let mut ctx = Context::new();
        let mut painter = QuadPainter::new();

        ctx.new_frame_with_painter(&mut painter, 1.0 / 60.0, 320.0, 240.0);
        if ctx.begin_window("Quad Window", None, 0) {
            ctx.text_unformatted("Testing WebGPU Quad emission");
            ctx.button_simple("QuadButton", Vec2::new(80.0, 20.0));
            ctx.end_window();
        }
        ctx.end_frame();

        // Must have emitted non-zero vertices (6 per quad)
        assert!(painter.vertex_count() > 0);
        assert_eq!(painter.vertex_count() % 6, 0);

        // Verify vertex bytes layout
        let bytes = painter.vertex_bytes();
        assert_eq!(bytes.len(), painter.vertex_count() * std::mem::size_of::<UiVertex>());
    }
}
