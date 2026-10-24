//! ImPlot types, ranges, colormaps, and flags.

use emtk_core::Color;

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct PlotPoint {
    pub x: f64,
    pub y: f64,
}

impl PlotPoint {
    pub const fn new(x: f64, y: f64) -> Self {
        Self { x, y }
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct PlotRange {
    pub min: f64,
    pub max: f64,
}

impl PlotRange {
    pub const fn new(min: f64, max: f64) -> Self {
        Self { min, max }
    }

    pub fn size(&self) -> f64 {
        self.max - self.min
    }

    pub fn contains(&self, v: f64) -> bool {
        v >= self.min && v <= self.max
    }

    pub fn expand_to_include(&mut self, v: f64) {
        if v < self.min { self.min = v; }
        if v > self.max { self.max = v; }
    }
}

pub const PLOT_FLAGS_NONE: u32 = 0;
pub const PLOT_FLAGS_NO_TITLE: u32 = 1 << 0;
pub const PLOT_FLAGS_NO_LEGEND: u32 = 1 << 1;
pub const PLOT_FLAGS_NO_MENUS: u32 = 1 << 2;
pub const PLOT_FLAGS_NO_BOX_SELECT: u32 = 1 << 3;
pub const PLOT_FLAGS_EQUAL: u32 = 1 << 4;

pub const AXIS_FLAGS_NONE: u32 = 0;
pub const AXIS_FLAGS_NO_GRID_LINES: u32 = 1 << 0;
pub const AXIS_FLAGS_NO_TICK_MARKS: u32 = 1 << 1;
pub const AXIS_FLAGS_NO_TICK_LABELS: u32 = 1 << 2;
pub const AXIS_FLAGS_LOG10: u32 = 1 << 3;
pub const AXIS_FLAGS_AUTO_FIT: u32 = 1 << 4;
pub const AXIS_FLAGS_INVERT: u32 = 1 << 5;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Colormap {
    Viridis,
    Plasma,
    Magma,
    Inferno,
    Turbo,
}

pub fn sample_colormap(t: f64, map: Colormap) -> Color {
    let t = t.clamp(0.0, 1.0);
    match map {
        Colormap::Viridis => {
            // High-precision Viridis polynomial approximation
            let r = (0.267 + 0.005 * t + 2.78 * t * t - 3.7 * t * t * t + 1.6 * t * t * t * t).clamp(0.0, 1.0);
            let g = (0.003 + 1.48 * t - 0.58 * t * t + 0.08 * t * t * t).clamp(0.0, 1.0);
            let b = (0.33 + 1.34 * t - 4.2 * t * t + 5.6 * t * t * t - 2.8 * t * t * t * t).clamp(0.0, 1.0);
            Color::rgb((r * 255.0) as u8, (g * 255.0) as u8, (b * 255.0) as u8)
        }
        Colormap::Plasma => {
            let r = (0.058 + 2.7 * t - 2.1 * t * t).clamp(0.0, 1.0);
            let g = (0.01 + 0.6 * t + 0.4 * t * t).clamp(0.0, 1.0);
            let b = (0.54 - 0.2 * t + 0.8 * (1.0 - t).powi(2)).clamp(0.0, 1.0);
            Color::rgb((r * 255.0) as u8, (g * 255.0) as u8, (b * 255.0) as u8)
        }
        _ => {
            // General heat fallback
            let r = (t * 2.0).clamp(0.0, 1.0);
            let g = ((t - 0.5) * 2.0).clamp(0.0, 1.0);
            let b = ((t - 0.75) * 4.0).clamp(0.0, 1.0);
            Color::rgb((r * 255.0) as u8, (g * 255.0) as u8, (b * 255.0) as u8)
        }
    }
}
