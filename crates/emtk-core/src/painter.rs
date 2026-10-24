//! EMTK Painter Contract: The minimal 6-operation drawing surface.

use crate::types::{Color, Rect, Vec2};

pub trait Painter {
    /// Fill an axis-aligned rectangle with a solid color.
    fn fill_rect(&mut self, rect: Rect, color: Color);

    /// Draw a stroked outline of `width` logical pixels, with an optional solid fill.
    fn stroke_rect(&mut self, rect: Rect, edge: Color, fill: Option<Color>, width: f32);

    /// Fill a rectangle with a left-to-right gradient through `stops`.
    fn gradient_rect(&mut self, rect: Rect, stops: &[Color]);

    /// Draw `text` aligned inside `rect`.
    fn text(&mut self, rect: Rect, align: u32, text: &str, color: Color, bold: bool);

    /// Push a rectangular clip boundary.
    fn push_clip(&mut self, rect: Rect);

    /// Restore the previous clip boundary.
    fn pop_clip(&mut self);

    /// Fill an arbitrary triangle with three independent corners.
    fn fill_triangle(&mut self, p0: Vec2, p1: Vec2, p2: Vec2, color: Color);

    /// Returns advance width of `text` in logical pixels.
    fn text_width(&self, text: &str) -> f32;

    /// Returns height of one text line in logical pixels.
    fn line_height(&self) -> f32;

    /// Optional acceleration: Draw polyline
    fn polyline(&mut self, points: &[Vec2], color: Color, closed: bool, width: f32) {
        if points.len() < 2 {
            return;
        }
        let half_w = width * 0.5;
        let count = if closed { points.len() } else { points.len() - 1 };

        for i in 0..count {
            let p0 = points[i];
            let p1 = points[(i + 1) % points.len()];
            let dir = Vec2::new(p1.x - p0.x, p1.y - p0.y);
            let len = (dir.x * dir.x + dir.y * dir.y).sqrt();
            if len <= 0.0001 {
                continue;
            }
            let normal = Vec2::new(-dir.y / len * half_w, dir.x / len * half_w);
            let a = Vec2::new(p0.x + normal.x, p0.y + normal.y);
            let b = Vec2::new(p0.x - normal.x, p0.y - normal.y);
            let c = Vec2::new(p1.x - normal.x, p1.y - normal.y);
            let d = Vec2::new(p1.x + normal.x, p1.y + normal.y);

            self.fill_triangle(a, b, c, color);
            self.fill_triangle(a, c, d, color);
        }
    }

    /// Convenience method to draw a single line segment
    fn line(&mut self, p0: Vec2, p1: Vec2, width: f32, color: Color) {
        self.polyline(&[p0, p1], color, false, width);
    }
}
