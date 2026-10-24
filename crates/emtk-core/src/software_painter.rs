//! Software CPU rasterizer for EMTK, matching Python's PixelPainter for headless rendering and tests.

use std::fs::File;
use std::io::BufWriter;
use std::path::Path;
use std::sync::OnceLock;

use emtk_font::{default_atlas, BakedAtlas, DecodedImage};
use crate::painter::Painter;
use crate::types::{Color, Rect, Vec2, ALIGN_HCENTER, ALIGN_RIGHT, ALIGN_VCENTER};

static ATLAS_IMAGE: OnceLock<DecodedImage> = OnceLock::new();

fn get_atlas_image() -> &'static DecodedImage {
    ATLAS_IMAGE.get_or_init(BakedAtlas::decode_png)
}

pub struct SoftwarePainter {
    pub width: u32,
    pub height: u32,
    pub pixels: Vec<u8>,
    clips: Vec<Rect>,
    atlas: &'static BakedAtlas,
    pub font_scale: f32,
}

impl SoftwarePainter {
    pub fn new(width: u32, height: u32, background: Color) -> Self {
        let mut pixels = vec![0u8; (width * height * 4) as usize];
        if background != Color::TRANSPARENT {
            for i in (0..pixels.len()).step_by(4) {
                pixels[i] = background.r;
                pixels[i + 1] = background.g;
                pixels[i + 2] = background.b;
                pixels[i + 3] = background.a;
            }
        }

        Self {
            width,
            height,
            pixels,
            clips: vec![Rect::new(0.0, 0.0, width as f32, height as f32)],
            atlas: default_atlas(),
            font_scale: 1.0,
        }
    }

    fn current_clip(&self) -> Rect {
        *self.clips.last().unwrap()
    }

    #[inline]
    fn blend_pixel(&mut self, x: u32, y: u32, r: u8, g: u8, b: u8, a: u8) {
        if x >= self.width || y >= self.height || a == 0 {
            return;
        }
        let idx = ((y * self.width + x) * 4) as usize;
        if a == 255 {
            self.pixels[idx] = r;
            self.pixels[idx + 1] = g;
            self.pixels[idx + 2] = b;
            self.pixels[idx + 3] = 255;
        } else {
            let sa = a as u32;
            let inv_sa = 255 - sa;
            let dr = self.pixels[idx] as u32;
            let dg = self.pixels[idx + 1] as u32;
            let db = self.pixels[idx + 2] as u32;
            let da = self.pixels[idx + 3] as u32;

            self.pixels[idx] = ((r as u32 * sa + dr * inv_sa) / 255) as u8;
            self.pixels[idx + 1] = ((g as u32 * sa + dg * inv_sa) / 255) as u8;
            self.pixels[idx + 2] = ((b as u32 * sa + db * inv_sa) / 255) as u8;
            self.pixels[idx + 3] = (sa + da * inv_sa / 255).min(255) as u8;
        }
    }

    pub fn save_png<P: AsRef<Path>>(&self, path: P) -> Result<(), std::io::Error> {
        let file = File::create(path)?;
        let w = BufWriter::new(file);
        let mut encoder = png::Encoder::new(w, self.width, self.height);
        encoder.set_color(png::ColorType::Rgba);
        encoder.set_depth(png::BitDepth::Eight);
        let mut writer = encoder.write_header().map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e))?;
        writer.write_image_data(&self.pixels).map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e))?;
        Ok(())
    }
}

impl Painter for SoftwarePainter {
    fn fill_rect(&mut self, rect: Rect, color: Color) {
        if color.a == 0 {
            return;
        }
        let clip = self.current_clip();
        let target = rect.intersect(&clip);
        if target.w <= 0.0 || target.h <= 0.0 {
            return;
        }

        let x0 = target.x.floor().max(0.0) as u32;
        let y0 = target.y.floor().max(0.0) as u32;
        let x1 = (target.x + target.w).ceil().min(self.width as f32) as u32;
        let y1 = (target.y + target.h).ceil().min(self.height as f32) as u32;

        if color.a == 255 {
            let row_span = ((x1 - x0) * 4) as usize;
            let mut row = Vec::with_capacity(row_span);
            for _ in 0..(x1 - x0) {
                row.extend_from_slice(&[color.r, color.g, color.b, 255]);
            }
            for y in y0..y1 {
                let base = ((y * self.width + x0) * 4) as usize;
                self.pixels[base..base + row_span].copy_from_slice(&row);
            }
        } else {
            for y in y0..y1 {
                for x in x0..x1 {
                    self.blend_pixel(x, y, color.r, color.g, color.b, color.a);
                }
            }
        }
    }

    fn stroke_rect(&mut self, rect: Rect, edge: Color, fill: Option<Color>, width: f32) {
        if let Some(fill_color) = fill {
            self.fill_rect(rect, fill_color);
        }
        if edge.a == 0 || width <= 0.0 {
            return;
        }
        // Top, bottom, left, right
        self.fill_rect(Rect::new(rect.x, rect.y, rect.w, width), edge);
        self.fill_rect(Rect::new(rect.x, rect.y + rect.h - width, rect.w, width), edge);
        self.fill_rect(Rect::new(rect.x, rect.y + width, width, (rect.h - 2.0 * width).max(0.0)), edge);
        self.fill_rect(Rect::new(rect.x + rect.w - width, rect.y + width, width, (rect.h - 2.0 * width).max(0.0)), edge);
    }

    fn gradient_rect(&mut self, rect: Rect, stops: &[Color]) {
        if stops.is_empty() {
            return;
        }
        if stops.len() == 1 {
            self.fill_rect(rect, stops[0]);
            return;
        }

        let clip = self.current_clip();
        let target = rect.intersect(&clip);
        if target.w <= 0.0 || target.h <= 0.0 {
            return;
        }

        let x0 = target.x.floor().max(0.0) as u32;
        let y0 = target.y.floor().max(0.0) as u32;
        let x1 = (target.x + target.w).ceil().min(self.width as f32) as u32;
        let y1 = (target.y + target.h).ceil().min(self.height as f32) as u32;

        let num_segments = stops.len() - 1;

        for x in x0..x1 {
            let t = ((x as f32 - rect.x) / rect.w).clamp(0.0, 1.0);
            let scaled_t = t * num_segments as f32;
            let idx = (scaled_t.floor() as usize).min(num_segments - 1);
            let local_t = scaled_t - idx as f32;

            let c0 = stops[idx];
            let c1 = stops[idx + 1];

            let r = (c0.r as f32 * (1.0 - local_t) + c1.r as f32 * local_t) as u8;
            let g = (c0.g as f32 * (1.0 - local_t) + c1.g as f32 * local_t) as u8;
            let b = (c0.b as f32 * (1.0 - local_t) + c1.b as f32 * local_t) as u8;
            let a = (c0.a as f32 * (1.0 - local_t) + c1.a as f32 * local_t) as u8;

            for y in y0..y1 {
                self.blend_pixel(x, y, r, g, b, a);
            }
        }
    }

    fn text(&mut self, rect: Rect, align: u32, text: &str, color: Color, bold: bool) {
        if text.is_empty() || color.a == 0 {
            return;
        }
        let atlas = self.atlas;
        let img = get_atlas_image();

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

        let clip = self.current_clip();
        let scale = atlas.render_scale * self.font_scale;

        for c in text.chars() {
            if let Some(cell) = atlas.cell_of(c, bold) {
                let glyph_w = cell.w as f32 * scale;
                let glyph_h = cell.h as f32 * scale;
                let glyph_rect = Rect::new(start_x, start_y, glyph_w, glyph_h);

                let visible = glyph_rect.intersect(&clip);
                if visible.w > 0.0 && visible.h > 0.0 {
                    let vx0 = visible.x.floor() as u32;
                    let vy0 = visible.y.floor() as u32;
                    let vx1 = (visible.x + visible.w).ceil() as u32;
                    let vy1 = (visible.y + visible.h).ceil() as u32;

                    for vy in vy0..vy1 {
                        let ty = ((vy as f32 - glyph_rect.y) / scale) as u32;
                        let src_y = cell.y + ty.min(cell.h - 1);
                        if src_y >= img.height { continue; }

                        for vx in vx0..vx1 {
                            let tx = ((vx as f32 - glyph_rect.x) / scale) as u32;
                            let src_x = cell.x + tx.min(cell.w - 1);
                            if src_x >= img.width { continue; }

                            let src_idx = ((src_y * img.width + src_x) * 4) as usize;
                            let alpha_texel = img.pixels[src_idx + 3];
                            if alpha_texel > 0 {
                                let blended_a = ((alpha_texel as u32 * color.a as u32) / 255) as u8;
                                self.blend_pixel(vx, vy, color.r, color.g, color.b, blended_a);
                            }
                        }
                    }
                }
            }
            start_x += atlas.advance_1x * self.font_scale;
        }
    }

    fn push_clip(&mut self, rect: Rect) {
        let cur = self.current_clip();
        self.clips.push(cur.intersect(&rect));
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
        let min_x = p0.x.min(p1.x).min(p2.x).max(clip.x_min()).floor() as i32;
        let max_x = p0.x.max(p1.x).max(p2.x).min(clip.x_max()).ceil() as i32;
        let min_y = p0.y.min(p1.y).min(p2.y).max(clip.y_min()).floor() as i32;
        let max_y = p0.y.max(p1.y).max(p2.y).min(clip.y_max()).ceil() as i32;

        if max_x <= min_x || max_y <= min_y {
            return;
        }

        fn edge(a: Vec2, b: Vec2, c: Vec2) -> f32 {
            (c.x - a.x) * (b.y - a.y) - (c.y - a.y) * (b.x - a.x)
        }

        let area = edge(p0, p1, p2);
        if area.abs() <= 0.0001 {
            return;
        }
        let inv_area = 1.0 / area;

        for y in min_y..max_y {
            for x in min_x..max_x {
                let p = Vec2::new(x as f32 + 0.5, y as f32 + 0.5);
                let w0 = edge(p1, p2, p) * inv_area;
                let w1 = edge(p2, p0, p) * inv_area;
                let w2 = edge(p0, p1, p) * inv_area;

                if w0 >= 0.0 && w1 >= 0.0 && w2 >= 0.0 {
                    self.blend_pixel(x as u32, y as u32, color.r, color.g, color.b, color.a);
                }
            }
        }
    }

    fn text_width(&self, text: &str) -> f32 {
        self.atlas.advance(text) * self.font_scale
    }

    fn line_height(&self) -> f32 {
        self.atlas.line_height() * self.font_scale
    }
}
