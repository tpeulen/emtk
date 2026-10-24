//! EMTK ImPlot: High-Performance 2D Scientific Plotting Engine in Rust.

pub mod types;
pub mod plot;

use std::cell::RefCell;
pub use types::*;
pub use plot::{Plot, PlotItem};
use emtk_core::{Color, Context, Rect, Vec2};

thread_local! {
    static ACTIVE_PLOT: RefCell<Option<Plot>> = RefCell::new(None);
}

pub fn begin_plot(ctx: &mut Context, title: &str, size_arg: Vec2, flags: u32) -> bool {
    let w = if size_arg.x > 0.0 { size_arg.x } else { 300.0 };
    let h = if size_arg.y > 0.0 { size_arg.y } else { 200.0 };

    let win_rect = if let Some(idx) = ctx.current_window_idx {
        let win = &ctx.windows[idx];
        Rect::new(win.cursor_pos.x, win.cursor_pos.y, w, h)
    } else {
        Rect::new(10.0, 10.0, w, h)
    };

    let plot = Plot::new(title, win_rect, flags);
    ACTIVE_PLOT.with(|p| {
        *p.borrow_mut() = Some(plot);
    });
    true
}

pub fn end_plot(ctx: &mut Context) {
    let plot_opt = ACTIVE_PLOT.with(|p| p.borrow_mut().take());
    if let Some(mut plot) = plot_opt {
        plot.fit();
        let style = ctx.style.clone();
        if let Some(painter) = ctx.get_painter() {
            plot.render(painter, &style);
        }
    }
}

pub fn setup_axes(x_label: &str, y_label: &str) {
    ACTIVE_PLOT.with(|p| {
        if let Some(plot) = p.borrow_mut().as_mut() {
            plot.x_label = x_label.to_string();
            plot.y_label = y_label.to_string();
        }
    });
}

pub fn setup_axis_limits(axis: u32, min: f64, max: f64) {
    ACTIVE_PLOT.with(|p| {
        if let Some(plot) = p.borrow_mut().as_mut() {
            plot.auto_fit = false;
            if axis == 0 {
                plot.x_range = PlotRange::new(min, max);
            } else {
                plot.y_range = PlotRange::new(min, max);
            }
        }
    });
}

pub fn plot_line(label: &str, xs: &[f64], ys: &[f64]) {
    ACTIVE_PLOT.with(|p| {
        if let Some(plot) = p.borrow_mut().as_mut() {
            let n = xs.len().min(ys.len());
            let points: Vec<PlotPoint> = (0..n).map(|i| PlotPoint::new(xs[i], ys[i])).collect();
            let color = Color::rgb(66, 150, 250); // Default blue
            plot.items.push(PlotItem::Line {
                label: label.to_string(),
                points,
                color,
                thickness: 1.5,
            });
        }
    });
}

pub fn plot_scatter(label: &str, xs: &[f64], ys: &[f64]) {
    ACTIVE_PLOT.with(|p| {
        if let Some(plot) = p.borrow_mut().as_mut() {
            let n = xs.len().min(ys.len());
            let points: Vec<PlotPoint> = (0..n).map(|i| PlotPoint::new(xs[i], ys[i])).collect();
            let color = Color::rgb(245, 225, 128); // Gold
            plot.items.push(PlotItem::Scatter {
                label: label.to_string(),
                points,
                color,
                radius: 2.5,
            });
        }
    });
}

pub fn plot_bars(label: &str, xs: &[f64], ys: &[f64], width: f64) {
    ACTIVE_PLOT.with(|p| {
        if let Some(plot) = p.borrow_mut().as_mut() {
            let n = xs.len().min(ys.len());
            let points: Vec<PlotPoint> = (0..n).map(|i| PlotPoint::new(xs[i], ys[i])).collect();
            let color = Color::rgb(46, 204, 113); // Emerald
            plot.items.push(PlotItem::Bars {
                label: label.to_string(),
                points,
                bar_width: width,
                color,
            });
        }
    });
}

pub fn plot_heatmap(label: &str, values: &[f64], rows: usize, cols: usize, min: f64, max: f64) {
    ACTIVE_PLOT.with(|p| {
        if let Some(plot) = p.borrow_mut().as_mut() {
            plot.items.push(PlotItem::Heatmap {
                label: label.to_string(),
                values: values.to_vec(),
                rows,
                cols,
                range: PlotRange::new(min, max),
                colormap: Colormap::Viridis,
            });
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    use emtk_core::SoftwarePainter;

    #[test]
    fn test_implot_render_cycle() {
        let mut ctx = Context::new();
        let mut painter = SoftwarePainter::new(400, 300, Color::rgb(30, 32, 38));

        ctx.new_frame_with_painter(&mut painter, 1.0 / 60.0, 400.0, 300.0);
        if ctx.begin_window("Plot Window", None, 0) {
            if begin_plot(&mut ctx, "Test Curve", Vec2::new(350.0, 200.0), 0) {
                setup_axes("Time (s)", "Voltage (V)");
                let xs = [0.0, 1.0, 2.0, 3.0, 4.0];
                let ys = [0.0, 2.5, 1.2, 3.8, 5.0];
                plot_line("Signal", &xs, &ys);
                end_plot(&mut ctx);
            }
            ctx.end_window();
        }
        ctx.end_frame();

        // Verify pixels rendered in plot
        let center_idx = ((150 * 400 + 200) * 4) as usize;
        assert_eq!(painter.pixels[center_idx + 3], 255); // Alpha fully opaque
    }
}
