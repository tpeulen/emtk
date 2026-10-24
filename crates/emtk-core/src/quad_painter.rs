//! QuadPainter: Compiles Painter commands into interleaved vertex arrays for WebGPU (ui.wgsl).
//!
//! Vertex format (12 floats per vertex):
//!   position: x, y           (pixels, y-down)
//!   uv:       u, v           (atlas texels)
//!   colour:   r, g, b, a     (0.0 - 1.0)
//!   box_clip: x0, y0, x1, y1 (clip rectangle in pixels)

use bytemuck::{Pod, Zeroable};
use emtk_font::{default_atlas, BakedAtlas};

use crate::painter::Painter;
use crate::types::{Color, Rect, Vec2, ALIGN_HCENTER, ALIGN_RIGHT, ALIGN_VCENTER};

pub const FLOATS_PER_VERTEX: usize = 12;
pub const VERTICES_PER_QUAD: usize = 6;
pub const NO_CLIP: [f32; 4] = [-1.0e6, -1.0e6, 1.0e6, 1.0e6];

#[repr(C)]
#[derive(Debug, Clone, Copy, PartialEq, Pod, Zeroable)]
pub struct UiVertex {
    pub position: [f32; 2],
    pub uv: [f32; 2],
    pub colour: [f32; 4],
    pub box_clip: [f32; 4],
}

impl UiVertex {
    pub const fn new(pos: [f32; 2], uv: [f32; 2], color: [f32; 4], clip: [f32; 4]) -> Self {
        Self {
            position: pos,
            uv,
            colour: color,
            box_clip: clip,
        }
    }
}

pub struct QuadPainter {
    pub vertices: Vec<UiVertex>,
    clips: Vec<[f32; 4]>,
    atlas: &'static BakedAtlas,
    solid_uv: [f32; 2],
    pub font_scale: f32,
}

impl QuadPainter {
    pub fn new() -> Self {
        let atlas = default_atlas();
        // The solid block in chrome.json
        let (sx, sy, sw, sh) = atlas.meta.solid;
        let solid_uv = [sx as f32 + sw as f32 * 0.5, sy as f32 + sh as f32 * 0.5];

        Self {
            vertices: Vec::with_capacity(1024),
            clips: vec![NO_CLIP],
            atlas,
            solid_uv,
            font_scale: 1.0,
        }
    }

    pub fn clear(&mut self) {
        self.vertices.clear();
        self.clips.clear();
        self.clips.push(NO_CLIP);
    }

    pub fn vertex_count(&self) -> usize {
        self.vertices.len()
    }

    pub fn vertex_bytes(&self) -> &[u8] {
        bytemuck::cast_slice(&self.vertices)
    }

    fn current_clip(&self) -> [f32; 4] {
        *self.clips.last().unwrap()
    }

    fn to_float_color(c: Color) -> [f32; 4] {
        [
            c.r as f32 / 255.0,
            c.g as f32 / 255.0,
            c.b as f32 / 255.0,
            c.a as f32 / 255.0,
        ]
    }

    pub fn emit_quad(
        &mut self,
        p0: [f32; 2], // top-left
        p1: [f32; 2], // top-right
        p2: [f32; 2], // bottom-right
        p3: [f32; 2], // bottom-left
        uv0: [f32; 2],
        uv1: [f32; 2],
        uv2: [f32; 2],
        uv3: [f32; 2],
        c0: [f32; 4],
        c1: [f32; 4],
        c2: [f32; 4],
        c3: [f32; 4],
    ) {
        let clip = self.current_clip();
        let v0 = UiVertex::new(p0, uv0, c0, clip);
        let v1 = UiVertex::new(p1, uv1, c1, clip);
        let v2 = UiVertex::new(p2, uv2, c2, clip);
        let v3 = UiVertex::new(p3, uv3, c3, clip);

        // Two triangles: (0, 1, 2) and (0, 2, 3)
        self.vertices.extend_from_slice(&[v0, v1, v2, v0, v2, v3]);
    }
}

impl Painter for QuadPainter {
    fn fill_rect(&mut self, rect: Rect, color: Color) {
        if color.a == 0 || rect.w <= 0.0 || rect.h <= 0.0 {
            return;
        }
        let col = Self::to_float_color(color);
        let uv = self.solid_uv;

        let p0 = [rect.x, rect.y];
        let p1 = [rect.x + rect.w, rect.y];
        let p2 = [rect.x + rect.w, rect.y + rect.h];
        let p3 = [rect.x, rect.y + rect.h];

        self.emit_quad(p0, p1, p2, p3, uv, uv, uv, uv, col, col, col, col);
    }

    fn stroke_rect(&mut self, rect: Rect, edge: Color, fill: Option<Color>, width: f32) {
        if let Some(fill_color) = fill {
            self.fill_rect(rect, fill_color);
        }
        if edge.a == 0 || width <= 0.0 {
            return;
        }
        // Top, bottom, left, right edge quads
        self.fill_rect(Rect::new(rect.x, rect.y, rect.w, width), edge);
        self.fill_rect(Rect::new(rect.x, rect.y + rect.h - width, rect.w, width), edge);
        self.fill_rect(Rect::new(rect.x, rect.y + width, width, (rect.h - 2.0 * width).max(0.0)), edge);
        self.fill_rect(Rect::new(rect.x + rect.w - width, rect.y + width, width, (rect.h - 2.0 * width).max(0.0)), edge);
    }

    fn gradient_rect(&mut self, rect: Rect, stops: &[Color]) {
        if stops.is_empty() || rect.w <= 0.0 || rect.h <= 0.0 {
            return;
        }
        if stops.len() == 1 {
            self.fill_rect(rect, stops[0]);
            return;
        }

        let uv = self.solid_uv;
        let num_segments = stops.len() - 1;
        let seg_w = rect.w / num_segments as f32;

        for i in 0..num_segments {
            let x0 = rect.x + i as f32 * seg_w;
            let x1 = x0 + seg_w;
            let c0 = Self::to_float_color(stops[i]);
            let c1 = Self::to_float_color(stops[i + 1]);

            let p0 = [x0, rect.y];
            let p1 = [x1, rect.y];
            let p2 = [x1, rect.y + rect.h];
            let p3 = [x0, rect.y + rect.h];

            self.emit_quad(p0, p1, p2, p3, uv, uv, uv, uv, c0, c1, c1, c0);
        }
    }

    fn text(&mut self, rect: Rect, align: u32, text: &str, color: Color, bold: bool) {
        if text.is_empty() || color.a == 0 {
            return;
        }
        let atlas = self.atlas;
        let advance = atlas.advance_1x * self.font_scale;
        let shrink = atlas.render_scale * self.font_scale;
        let ascent = atlas.meta.ascent as f32;
        let half_cell_h = (atlas.meta.cell.1 as f32) * 0.5;
        let pad = atlas.meta.pad as f32;

        let span = advance * (text.chars().count() as f32);
        let pen_x = if (align & ALIGN_RIGHT) != 0 {
            rect.x + rect.w - span
        } else if (align & ALIGN_HCENTER) != 0 {
            rect.x + (rect.w - span) * 0.5
        } else {
            rect.x
        };

        let baseline = if (align & ALIGN_VCENTER) != 0 {
            rect.y + rect.h * 0.5 + (ascent - half_cell_h) * shrink
        } else {
            rect.y + ascent * shrink
        };
        let start_y = baseline - (ascent + pad) * shrink;
        let mut start_x = pen_x - pad * shrink;

        let scale = atlas.render_scale * self.font_scale;
        let col = Self::to_float_color(color);

        for c in text.chars() {
            if let Some(cell) = atlas.cell_of(c, bold) {
                let glyph_w = cell.w as f32 * scale;
                let glyph_h = cell.h as f32 * scale;

                let p0 = [start_x, start_y];
                let p1 = [start_x + glyph_w, start_y];
                let p2 = [start_x + glyph_w, start_y + glyph_h];
                let p3 = [start_x, start_y + glyph_h];

                let u0 = cell.x as f32;
                let v0 = cell.y as f32;
                let u1 = (cell.x + cell.w) as f32;
                let v1 = (cell.y + cell.h) as f32;

                let uv0 = [u0, v0];
                let uv1 = [u1, v0];
                let uv2 = [u1, v1];
                let uv3 = [u0, v1];

                self.emit_quad(p0, p1, p2, p3, uv0, uv1, uv2, uv3, col, col, col, col);
            }
            start_x += atlas.advance_1x * self.font_scale;
        }
    }

    fn push_clip(&mut self, rect: Rect) {
        let cur = self.current_clip();
        let x0 = rect.x.max(cur[0]);
        let y0 = rect.y.max(cur[1]);
        let x1 = (rect.x + rect.w).min(cur[2]);
        let y1 = (rect.y + rect.h).min(cur[3]);
        self.clips.push([x0, y0, x1.max(x0), y1.max(y0)]);
    }

    fn pop_clip(&mut self) {
        if self.clips.len() > 1 {
            self.clips.pop();
        }
    }

    fn fill_triangle(&mut self, p0: Vec2, p1: Vec2, p2: Vec2, color: Color) {
        if color.a == 0 {
            return;
        }
        let clip = self.current_clip();
        let col = Self::to_float_color(color);
        let uv = self.solid_uv;

        let v0 = UiVertex::new([p0.x, p0.y], uv, col, clip);
        let v1 = UiVertex::new([p1.x, p1.y], uv, col, clip);
        let v2 = UiVertex::new([p2.x, p2.y], uv, col, clip);

        self.vertices.extend_from_slice(&[v0, v1, v2]);
    }

    fn text_width(&self, text: &str) -> f32 {
        self.atlas.advance(text) * self.font_scale
    }

    fn line_height(&self) -> f32 {
        self.atlas.line_height() * self.font_scale
    }
}
