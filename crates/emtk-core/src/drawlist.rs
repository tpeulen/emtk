//! DrawList: Dear ImGui's ImDrawList tessellator over the EMTK Painter contract.

use std::f32::consts::PI;
use crate::painter::Painter;
use crate::types::{Color, Rect, Vec2, ALIGN_LEFT, ALIGN_VCENTER};

pub const DRAW_FLAGS_NONE: u32 = 0;
pub const DRAW_FLAGS_CLOSED: u32 = 1 << 0;
pub const DRAW_FLAGS_ROUND_CORNERS_TOP_LEFT: u32 = 1 << 4;
pub const DRAW_FLAGS_ROUND_CORNERS_TOP_RIGHT: u32 = 1 << 5;
pub const DRAW_FLAGS_ROUND_CORNERS_BOTTOM_LEFT: u32 = 1 << 6;
pub const DRAW_FLAGS_ROUND_CORNERS_BOTTOM_RIGHT: u32 = 1 << 7;
pub const DRAW_FLAGS_ROUND_CORNERS_ALL: u32 = DRAW_FLAGS_ROUND_CORNERS_TOP_LEFT
    | DRAW_FLAGS_ROUND_CORNERS_TOP_RIGHT
    | DRAW_FLAGS_ROUND_CORNERS_BOTTOM_LEFT
    | DRAW_FLAGS_ROUND_CORNERS_BOTTOM_RIGHT;

pub struct DrawList<'a> {
    painter: &'a mut dyn Painter,
}

impl<'a> DrawList<'a> {
    pub fn new(painter: &'a mut dyn Painter) -> Self {
        Self { painter }
    }

    pub fn push_clip_rect(&mut self, clip_rect_min: Vec2, clip_rect_max: Vec2) {
        let rect = Rect::new(
            clip_rect_min.x,
            clip_rect_min.y,
            (clip_rect_max.x - clip_rect_min.x).max(0.0),
            (clip_rect_max.y - clip_rect_min.y).max(0.0),
        );
        self.painter.push_clip(rect);
    }

    pub fn pop_clip_rect(&mut self) {
        self.painter.pop_clip();
    }

    pub fn add_line(&mut self, p1: Vec2, p2: Vec2, col: Color, thickness: f32) {
        self.painter.polyline(&[p1, p2], col, false, thickness);
    }

    pub fn add_rect(&mut self, p_min: Vec2, p_max: Vec2, col: Color, rounding: f32, flags: u32, thickness: f32) {
        let w = (p_max.x - p_min.x).max(0.0);
        let h = (p_max.y - p_min.y).max(0.0);
        if w <= 0.0 || h <= 0.0 || col.a == 0 {
            return;
        }

        if rounding <= 0.0 || flags == 0 {
            self.painter.stroke_rect(Rect::new(p_min.x, p_min.y, w, h), col, None, thickness);
            return;
        }

        // Rounded rect outline
        let points = self.get_rounded_rect_points(p_min, p_max, rounding, flags, 12);
        self.painter.polyline(&points, col, true, thickness);
    }

    pub fn add_rect_filled(&mut self, p_min: Vec2, p_max: Vec2, col: Color, rounding: f32, flags: u32) {
        let w = (p_max.x - p_min.x).max(0.0);
        let h = (p_max.y - p_min.y).max(0.0);
        if w <= 0.0 || h <= 0.0 || col.a == 0 {
            return;
        }

        if rounding <= 0.0 || flags == 0 {
            self.painter.fill_rect(Rect::new(p_min.x, p_min.y, w, h), col);
            return;
        }

        // Rounded rect filled polygon fan
        let points = self.get_rounded_rect_points(p_min, p_max, rounding, flags, 12);
        self.add_convex_poly_filled(&points, col);
    }

    pub fn add_circle(&mut self, center: Vec2, radius: f32, col: Color, segments: u32, thickness: f32) {
        if radius <= 0.0 || col.a == 0 {
            return;
        }
        let segs = segments.max(12);
        let mut points = Vec::with_capacity(segs as usize);
        let step = (2.0 * PI) / segs as f32;
        for i in 0..segs {
            let theta = i as f32 * step;
            points.push(Vec2::new(center.x + theta.cos() * radius, center.y + theta.sin() * radius));
        }
        self.painter.polyline(&points, col, true, thickness);
    }

    pub fn add_circle_filled(&mut self, center: Vec2, radius: f32, col: Color, segments: u32) {
        if radius <= 0.0 || col.a == 0 {
            return;
        }
        let segs = segments.max(12);
        let step = (2.0 * PI) / segs as f32;
        for i in 0..segs {
            let t0 = i as f32 * step;
            let t1 = (i + 1) as f32 * step;
            let p1 = Vec2::new(center.x + t0.cos() * radius, center.y + t0.sin() * radius);
            let p2 = Vec2::new(center.x + t1.cos() * radius, center.y + t1.sin() * radius);
            self.painter.fill_triangle(center, p1, p2, col);
        }
    }

    pub fn add_triangle_filled(&mut self, p1: Vec2, p2: Vec2, p3: Vec2, col: Color) {
        self.painter.fill_triangle(p1, p2, p3, col);
    }

    pub fn add_text(&mut self, pos: Vec2, col: Color, text: &str) {
        let w = self.painter.text_width(text);
        let h = self.painter.line_height();
        self.painter.text(Rect::new(pos.x, pos.y, w, h), ALIGN_LEFT | ALIGN_VCENTER, text, col, false);
    }

    pub fn add_convex_poly_filled(&mut self, points: &[Vec2], col: Color) {
        if points.len() < 3 || col.a == 0 {
            return;
        }
        let p0 = points[0];
        for i in 1..(points.len() - 1) {
            self.painter.fill_triangle(p0, points[i], points[i + 1], col);
        }
    }

    fn get_rounded_rect_points(&self, p_min: Vec2, p_max: Vec2, rounding: f32, _flags: u32, segments: u32) -> Vec<Vec2> {
        let w = p_max.x - p_min.x;
        let h = p_max.y - p_min.y;
        let r = rounding.min(w * 0.5).min(h * 0.5);

        let mut pts = Vec::new();
        let n = segments.max(3);

        let mut add_arc = |cx: f32, cy: f32, a0: f32, a1: f32| {
            for i in 0..=n {
                let a = a0 + (a1 - a0) * (i as f32 / n as f32);
                pts.push(Vec2::new(cx + a.cos() * r, cy + a.sin() * r));
            }
        };

        // Top-left
        add_arc(p_min.x + r, p_min.y + r, PI, 1.5 * PI);
        // Top-right
        add_arc(p_max.x - r, p_min.y + r, 1.5 * PI, 2.0 * PI);
        // Bottom-right
        add_arc(p_max.x - r, p_max.y - r, 0.0, 0.5 * PI);
        // Bottom-left
        add_arc(p_min.x + r, p_max.y - r, 0.5 * PI, PI);

        pts
    }
}
