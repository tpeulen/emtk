//! EMTK Font Engine: Baked Chrome Atlas + Dynamic TTF Rasterizer.

use std::collections::HashMap;
use std::sync::OnceLock;
use serde::Deserialize;

pub const CHROME_PNG_BYTES: &[u8] = include_bytes!("../../../emtk/atlas/chrome.png");
pub const CHROME_JSON_STR: &str = include_str!("../../../emtk/atlas/chrome.json");

pub const MISSING_GLYPH: char = '\u{00a4}';
pub const DEFAULT_FONT_PT: f32 = 8.0;
pub const PX_PER_PT: f32 = 96.0 / 72.0;

#[derive(Debug, Clone, Deserialize)]
pub struct AtlasMetadata {
    pub scale: u32,
    pub pad: u32,
    pub cell: (u32, u32),
    pub size: (u32, u32),
    pub solid: (u32, u32, u32, u32),
    pub ascent: i32,
    #[serde(default)]
    pub ascent_1x: Option<f32>,
    pub descent: i32,
    #[serde(default)]
    pub font_pt: Option<f32>,
    pub advance: u32,
    #[serde(default)]
    pub advance_1x: Option<f32>,
    #[serde(default)]
    pub line_height: Option<u32>,
    #[serde(default)]
    pub line_height_1x: Option<f32>,
    pub glyphs: GlyphsMap,
}

#[derive(Debug, Clone, Deserialize)]
pub struct GlyphsMap {
    #[serde(default)]
    pub regular: HashMap<String, (u32, u32, u32, u32, u32)>,
    #[serde(default)]
    pub bold: HashMap<String, (u32, u32, u32, u32, u32)>,
}

#[derive(Debug, Clone, Copy)]
pub struct GlyphCell {
    pub x: u32,
    pub y: u32,
    pub w: u32,
    pub h: u32,
    pub advance_texels: u32,
}

pub struct BakedAtlas {
    pub meta: AtlasMetadata,
    pub advance_1x: f32,
    pub line_height_1x: f32,
    pub render_scale: f32,
}

impl BakedAtlas {
    pub fn new() -> Self {
        let meta: AtlasMetadata = serde_json::from_str(CHROME_JSON_STR)
            .expect("Valid embedded chrome.json");

        let scale = meta.scale as f32;
        let advance_1x = meta.advance_1x.unwrap_or(meta.advance as f32 / scale);
        let baked_adv = meta.advance as f32 / scale;
        let render_scale = if baked_adv > 0.0 {
            (advance_1x / baked_adv) / scale
        } else {
            1.0 / scale
        };

        let line_height_1x = meta.line_height_1x.unwrap_or_else(|| {
            meta.line_height.map(|lh| lh as f32 / scale).unwrap_or(13.0)
        });

        Self {
            meta,
            advance_1x,
            line_height_1x,
            render_scale,
        }
    }

    pub fn advance(&self, text: &str) -> f32 {
        let char_count = text.chars().count();
        if char_count == 0 {
            self.advance_1x
        } else {
            self.advance_1x * (char_count as f32)
        }
    }

    pub fn line_height(&self) -> f32 {
        self.line_height_1x
    }

    pub fn cell_of(&self, c: char, bold: bool) -> Option<GlyphCell> {
        let table = if bold {
            &self.meta.glyphs.bold
        } else {
            &self.meta.glyphs.regular
        };

        let mut buf = [0u8; 4];
        let s = c.encode_utf8(&mut buf);

        if let Some(&(x, y, w, h, adv)) = table.get(s) {
            return Some(GlyphCell { x, y, w, h, advance_texels: adv });
        }

        // Try missing glyph placeholder
        let mut missing_buf = [0u8; 4];
        let missing_s = MISSING_GLYPH.encode_utf8(&mut missing_buf);
        table.get(missing_s).map(|&(x, y, w, h, adv)| GlyphCell {
            x, y, w, h, advance_texels: adv,
        })
    }
}

pub struct DecodedImage {
    pub width: u32,
    pub height: u32,
    pub pixels: Vec<u8>, // RGBA
}

impl BakedAtlas {
    pub fn decode_png() -> DecodedImage {
        let decoder = png::Decoder::new(CHROME_PNG_BYTES);
        let mut reader = decoder.read_info().expect("Valid chrome.png header");
        let mut pixels = vec![0; reader.output_buffer_size()];
        let info = reader.next_frame(&mut pixels).expect("Valid chrome.png frame");
        pixels.truncate(info.buffer_size());

        DecodedImage {
            width: info.width,
            height: info.height,
            pixels,
        }
    }
}

static DEFAULT_ATLAS: OnceLock<BakedAtlas> = OnceLock::new();

pub fn default_atlas() -> &'static BakedAtlas {
    DEFAULT_ATLAS.get_or_init(BakedAtlas::new)
}

/// Dynamic TTF font loader and rasterizer
pub struct DynamicFont {
    font: fontdue::Font,
}

impl DynamicFont {
    pub fn from_bytes(data: &[u8]) -> Result<Self, &'static str> {
        let settings = fontdue::FontSettings::default();
        let font = fontdue::Font::from_bytes(data, settings)?;
        Ok(Self { font })
    }

    pub fn rasterize(&self, c: char, size_px: f32) -> (fontdue::Metrics, Vec<u8>) {
        self.font.rasterize(c, size_px)
    }

    pub fn line_height(&self, size_px: f32) -> f32 {
        self.font.horizontal_line_metrics(size_px)
            .map(|m| m.new_line_size)
            .unwrap_or(size_px * 1.2)
    }

    pub fn text_width(&self, text: &str, size_px: f32) -> f32 {
        let mut w = 0.0;
        for c in text.chars() {
            let metrics = self.font.metrics(c, size_px);
            w += metrics.advance_width;
        }
        w
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_baked_atlas_loads() {
        let atlas = default_atlas();
        assert_eq!(atlas.meta.scale, 4);
        assert!(atlas.advance_1x > 0.0);
        assert!(atlas.line_height_1x > 0.0);

        let space_cell = atlas.cell_of(' ', false).expect("Space glyph exists");
        assert!(space_cell.w > 0);
        assert!(space_cell.h > 0);

        let adv = atlas.advance("Hello");
        assert_eq!(adv, atlas.advance_1x * 5.0);
    }

    #[test]
    fn test_decode_atlas_png() {
        let img = BakedAtlas::decode_png();
        assert_eq!(img.width, 2368);
        assert_eq!(img.height, 4257);
        assert_eq!(img.pixels.len(), (2368 * 4257 * 4) as usize);
    }
}
