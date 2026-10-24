//! 2D Scientific Plot Container and Item Renderers.

use emtk_core::{Color, Painter, Rect, Style, Vec2, ALIGN_CENTER, ALIGN_LEFT, ALIGN_RIGHT};
use crate::types::{sample_colormap, Colormap, PlotPoint, PlotRange, PLOT_FLAGS_NO_TITLE};

#[derive(Debug, Clone)]
pub enum PlotItem {
    Line {
        label: String,
        points: Vec<PlotPoint>,
        color: Color,
        thickness: f32,
    },
    Scatter {
        label: String,
        points: Vec<PlotPoint>,
        color: Color,
        radius: f32,
    },
    Bars {
        label: String,
        points: Vec<PlotPoint>,
        bar_width: f64,
        color: Color,
    },
    Heatmap {
        label: String,
        values: Vec<f64>,
        rows: usize,
        cols: usize,
        range: PlotRange,
        colormap: Colormap,
    },
}

#[derive(Debug, Clone)]
pub struct Plot {
    pub title: String,
    pub flags: u32,
    pub frame_rect: Rect,
    pub canvas_rect: Rect,
    pub x_label: String,
    pub y_label: String,
    pub x_range: PlotRange,
    pub y_range: PlotRange,
    pub items: Vec<PlotItem>,
    pub auto_fit: bool,
}

impl Plot {
    pub fn new(title: &str, rect: Rect, flags: u32) -> Self {
        // Pad for axes labels and title
        let pad_left = 50.0;
        let pad_bottom = 25.0;
        let pad_top = if (flags & PLOT_FLAGS_NO_TITLE) != 0 { 10.0 } else { 25.0 };
        let pad_right = 15.0;

        let canvas_rect = Rect::new(
            rect.x + pad_left,
            rect.y + pad_top,
            (rect.w - pad_left - pad_right).max(10.0),
            (rect.h - pad_top - pad_bottom).max(10.0),
        );

        Self {
            title: title.to_string(),
            flags,
            frame_rect: rect,
            canvas_rect,
            x_label: String::new(),
            y_label: String::new(),
            x_range: PlotRange::new(0.0, 1.0),
            y_range: PlotRange::new(0.0, 1.0),
            items: Vec::new(),
            auto_fit: true,
        }
    }

    pub fn transform(&self, pt: PlotPoint) -> Vec2 {
        let x_size = self.x_range.size().max(1e-9);
        let y_size = self.y_range.size().max(1e-9);

        let tx = ((pt.x - self.x_range.min) / x_size) as f32;
        let ty = ((pt.y - self.y_range.min) / y_size) as f32;

        let px = self.canvas_rect.x + tx * self.canvas_rect.w;
        let py = self.canvas_rect.y + (1.0 - ty) * self.canvas_rect.h; // Y-up
        Vec2::new(px, py)
    }

    pub fn fit(&mut self) {
        if !self.auto_fit || self.items.is_empty() {
            return;
        }

        let mut x_min = f64::MAX;
        let mut x_max = f64::MIN;
        let mut y_min = f64::MAX;
        let mut y_max = f64::MIN;

        for item in &self.items {
            match item {
                PlotItem::Line { points, .. } | PlotItem::Scatter { points, .. } | PlotItem::Bars { points, .. } => {
                    for p in points {
                        if p.x < x_min { x_min = p.x; }
                        if p.x > x_max { x_max = p.x; }
                        if p.y < y_min { y_min = p.y; }
                        if p.y > y_max { y_max = p.y; }
                    }
                }
                PlotItem::Heatmap { cols, rows, .. } => {
                    x_min = 0.0;
                    x_max = *cols as f64;
                    y_min = 0.0;
                    y_max = *rows as f64;
                }
            }
        }

        if x_max > x_min {
            let pad_x = (x_max - x_min) * 0.05;
            self.x_range = PlotRange::new(x_min - pad_x, x_max + pad_x);
        }
        if y_max > y_min {
            let pad_y = (y_max - y_min) * 0.05;
            self.y_range = PlotRange::new(y_min - pad_y, y_max + pad_y);
        }
    }

    pub fn render(&self, painter: &mut dyn Painter, style: &Style) {
        // Plot canvas background & border
        let plot_bg = Color::rgba(20, 20, 22, 255);
        let grid_col = Color::rgba(50, 50, 56, 180);
        let border_col = style.border;

        painter.fill_rect(self.canvas_rect, plot_bg);
        painter.stroke_rect(self.canvas_rect, border_col, None, 1.0);

        // Grid lines (5 ticks on each axis)
        for i in 1..5 {
            let t = i as f32 / 5.0;
            // Vertical grid
            let gx = self.canvas_rect.x + t * self.canvas_rect.w;
            painter.polyline(&[Vec2::new(gx, self.canvas_rect.y), Vec2::new(gx, self.canvas_rect.y + self.canvas_rect.h)],
                             grid_col, false, 1.0);
            // Horizontal grid
            let gy = self.canvas_rect.y + t * self.canvas_rect.h;
            painter.polyline(&[Vec2::new(self.canvas_rect.x, gy), Vec2::new(self.canvas_rect.x + self.canvas_rect.w, gy)],
                             grid_col, false, 1.0);
        }

        // Clip items to canvas
        painter.push_clip(self.canvas_rect);

        for item in &self.items {
            match item {
                PlotItem::Line { points, color, thickness, .. } => {
                    let screen_pts: Vec<Vec2> = points.iter().map(|&p| self.transform(p)).collect();
                    painter.polyline(&screen_pts, *color, false, *thickness);
                }
                PlotItem::Scatter { points, color, radius, .. } => {
                    for &p in points {
                        let center = self.transform(p);
                        painter.fill_rect(Rect::new(center.x - radius, center.y - radius, radius * 2.0, radius * 2.0), *color);
                    }
                }
                PlotItem::Bars { points, bar_width, color, .. } => {
                    let half_w = (*bar_width * 0.5) as f64;
                    for &p in points {
                        let p0 = self.transform(PlotPoint::new(p.x - half_w, p.y));
                        let p1 = self.transform(PlotPoint::new(p.x + half_w, 0.0));
                        let rx = p0.x.min(p1.x);
                        let ry = p0.y.min(p1.y);
                        let rw = (p0.x - p1.x).abs().max(1.0);
                        let rh = (p0.y - p1.y).abs().max(1.0);
                        painter.fill_rect(Rect::new(rx, ry, rw, rh), *color);
                    }
                }
                PlotItem::Heatmap { values, rows, cols, range, colormap, .. } => {
                    let cell_w = self.canvas_rect.w / *cols as f32;
                    let cell_h = self.canvas_rect.h / *rows as f32;
                    let val_span = range.size().max(1e-9);

                    for r in 0..*rows {
                        for c in 0..*cols {
                            let val = values[r * cols + c];
                            let t = (val - range.min) / val_span;
                            let color = sample_colormap(t, *colormap);

                            let px = self.canvas_rect.x + c as f32 * cell_w;
                            let py = self.canvas_rect.y + (*rows - 1 - r) as f32 * cell_h;
                            painter.fill_rect(Rect::new(px, py, cell_w + 0.5, cell_h + 0.5), color);
                        }
                    }
                }
            }
        }

        painter.pop_clip();

        // Title
        if (self.flags & PLOT_FLAGS_NO_TITLE) == 0 && !self.title.is_empty() {
            let title_rect = Rect::new(self.frame_rect.x, self.frame_rect.y, self.frame_rect.w, 20.0);
            painter.text(title_rect, ALIGN_CENTER, &self.title, style.text, true);
        }

        // Axis Tick Labels
        let x_min_str = format!("{:.1}", self.x_range.min);
        let x_max_str = format!("{:.1}", self.x_range.max);
        let y_min_str = format!("{:.1}", self.y_range.min);
        let y_max_str = format!("{:.1}", self.y_range.max);

        // X Axis labels
        let x_lbl_y = self.canvas_rect.y + self.canvas_rect.h + 4.0;
        painter.text(Rect::new(self.canvas_rect.x, x_lbl_y, 60.0, 15.0), ALIGN_LEFT, &x_min_str, Color::rgb(160, 160, 160), false);
        painter.text(Rect::new(self.canvas_rect.x + self.canvas_rect.w - 60.0, x_lbl_y, 60.0, 15.0), ALIGN_RIGHT, &x_max_str, Color::rgb(160, 160, 160), false);

        // Y Axis labels
        let y_lbl_x = self.canvas_rect.x - 45.0;
        painter.text(Rect::new(y_lbl_x, self.canvas_rect.y + self.canvas_rect.h - 15.0, 40.0, 15.0), ALIGN_RIGHT, &y_min_str, Color::rgb(160, 160, 160), false);
        painter.text(Rect::new(y_lbl_x, self.canvas_rect.y, 40.0, 15.0), ALIGN_RIGHT, &y_max_str, Color::rgb(160, 160, 160), false);
    }
}
