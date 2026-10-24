//! Immediate-Mode Context, Layout Engine, State Machine, and Core Widgets.

use ahash::AHasher;
use std::hash::{Hash, Hasher};

use crate::painter::Painter;
use crate::style::{Style, CHECK_MARK, TEXT};
use crate::types::{Rect, Vec2, ALIGN_CENTER, ALIGN_LEFT, ALIGN_VCENTER};

#[derive(Debug, Clone)]
pub struct IO {
    pub mouse_pos: Vec2,
    pub mouse_down: [bool; 5],
    pub mouse_clicked: [bool; 5],
    pub mouse_released: [bool; 5],
    pub mouse_wheel: f32,
    pub key_ctrl: bool,
    pub key_shift: bool,
    pub key_alt: bool,
    pub display_size: Vec2,
    pub delta_time: f32,
}

impl Default for IO {
    fn default() -> Self {
        Self {
            mouse_pos: Vec2::new(-1.0, -1.0),
            mouse_down: [false; 5],
            mouse_clicked: [false; 5],
            mouse_released: [false; 5],
            mouse_wheel: 0.0,
            key_ctrl: false,
            key_shift: false,
            key_alt: false,
            display_size: Vec2::new(1280.0, 720.0),
            delta_time: 1.0 / 60.0,
        }
    }
}

#[derive(Debug, Clone)]
pub struct Window {
    pub name: String,
    pub id: u32,
    pub rect: Rect,
    pub cursor_pos: Vec2,
    pub cursor_start: Vec2,
    pub line_max_h: f32,
    pub prev_line_h: f32,
    pub last_item_rect: Rect,
    pub collapsed: bool,
}

impl Window {
    pub fn new(name: &str, id: u32, rect: Rect) -> Self {
        let cursor_start = Vec2::new(rect.x + 8.0, rect.y + 24.0);
        Self {
            name: name.to_string(),
            id,
            rect,
            cursor_pos: cursor_start,
            cursor_start,
            line_max_h: 0.0,
            prev_line_h: 0.0,
            last_item_rect: Rect::ZERO,
            collapsed: false,
        }
    }
}

pub struct Context {
    pub io: IO,
    pub style: Style,
    pub windows: Vec<Window>,
    pub current_window_idx: Option<usize>,
    id_stack: Vec<u32>,
    pub active_id: u32,
    pub hovered_id: u32,
    pub frame_count: u64,
    pub active_painter: Option<*mut dyn Painter>,
}

impl Context {
    pub fn new() -> Self {
        Self {
            io: IO::default(),
            style: Style::default(),
            windows: Vec::new(),
            current_window_idx: None,
            id_stack: vec![0],
            active_id: 0,
            hovered_id: 0,
            frame_count: 0,
            active_painter: None,
        }
    }

    pub fn new_frame(&mut self, dt: f32, width: f32, height: f32) {
        self.io.delta_time = dt;
        self.io.display_size = Vec2::new(width, height);
        self.frame_count += 1;
        self.current_window_idx = None;
        self.hovered_id = 0;
        self.id_stack = vec![0];
    }

    pub fn new_frame_with_painter(&mut self, painter: &mut dyn Painter, dt: f32, width: f32, height: f32) {
        self.new_frame(dt, width, height);
        let erased: *mut (dyn Painter + 'static) = unsafe { std::mem::transmute(painter as *mut dyn Painter) };
        self.active_painter = Some(erased);
    }

    pub fn end_frame(&mut self) {
        // Clear one-shot edges
        for i in 0..5 {
            self.io.mouse_clicked[i] = false;
            self.io.mouse_released[i] = false;
        }
        self.io.mouse_wheel = 0.0;
        self.active_painter = None;
    }

    pub fn get_painter(&mut self) -> Option<&mut dyn Painter> {
        self.active_painter.map(|ptr| unsafe { &mut *ptr })
    }

    pub fn get_id(&self, label: &str) -> u32 {
        let mut hasher = AHasher::default();
        let seed = *self.id_stack.last().unwrap_or(&0);
        seed.hash(&mut hasher);
        label.hash(&mut hasher);
        (hasher.finish() & 0xFFFFFFFF) as u32
    }

    pub fn push_id(&mut self, id: u32) {
        self.id_stack.push(id);
    }

    pub fn pop_id(&mut self) {
        if self.id_stack.len() > 1 {
            self.id_stack.pop();
        }
    }

    // --- Windowing ---

    pub fn begin(&mut self, painter: &mut dyn Painter, name: &str, _p_open: Option<&mut bool>, _flags: u32) -> bool {
        let id = self.get_id(name);
        let win_idx = if let Some(idx) = self.windows.iter().position(|w| w.id == id) {
            idx
        } else {
            let default_rect = Rect::new(10.0, 10.0, 320.0, 240.0);
            self.windows.push(Window::new(name, id, default_rect));
            self.windows.len() - 1
        };

        self.current_window_idx = Some(win_idx);
        let win = &mut self.windows[win_idx];
        win.cursor_pos = Vec2::new(win.rect.x + self.style.window_padding.x, win.rect.y + 24.0);
        win.cursor_start = win.cursor_pos;
        win.line_max_h = 0.0;

        // Draw Window background & Title bar
        painter.fill_rect(win.rect, self.style.window_bg);
        painter.stroke_rect(win.rect, self.style.border, None, 1.0);

        let title_rect = Rect::new(win.rect.x, win.rect.y, win.rect.w, 20.0);
        painter.fill_rect(title_rect, self.style.title_bg_active);
        painter.text(Rect::new(title_rect.x + 8.0, title_rect.y, title_rect.w - 16.0, title_rect.h),
                     ALIGN_LEFT | ALIGN_VCENTER, name, TEXT, true);

        // Clip window contents
        let content_rect = Rect::new(win.rect.x, win.rect.y + 20.0, win.rect.w, (win.rect.h - 20.0).max(0.0));
        painter.push_clip(content_rect);

        true
    }

    pub fn end(&mut self, painter: &mut dyn Painter) {
        painter.pop_clip();
        self.current_window_idx = None;
    }

    // --- Layout Cursor ---

    pub fn same_line(&mut self, offset_from_start: f32, spacing: f32) {
        if let Some(idx) = self.current_window_idx {
            let win = &mut self.windows[idx];
            let sp = if spacing >= 0.0 { spacing } else { self.style.item_spacing.x };
            if offset_from_start != 0.0 {
                win.cursor_pos.x = win.rect.x + offset_from_start;
            } else {
                win.cursor_pos.x = win.last_item_rect.x + win.last_item_rect.w + sp;
            }
            win.cursor_pos.y -= win.prev_line_h;
        }
    }

    fn item_size(&mut self, size: Vec2) -> Rect {
        if let Some(idx) = self.current_window_idx {
            let win = &mut self.windows[idx];
            let bb = Rect::new(win.cursor_pos.x, win.cursor_pos.y, size.x, size.y);
            win.last_item_rect = bb;
            win.cursor_pos.x = win.rect.x + self.style.window_padding.x;
            win.cursor_pos.y += size.y + self.style.item_spacing.y;
            win.prev_line_h = size.y + self.style.item_spacing.y;
            bb
        } else {
            Rect::ZERO
        }
    }

    fn button_behavior(&mut self, bb: Rect, id: u32) -> (bool, bool, bool) {
        let is_hovered = bb.contains(self.io.mouse_pos);
        if is_hovered {
            self.hovered_id = id;
        }

        let mut pressed = false;
        let mut held = false;

        if is_hovered && self.io.mouse_clicked[0] {
            self.active_id = id;
        }

        if self.active_id == id {
            held = self.io.mouse_down[0];
            if self.io.mouse_released[0] {
                if is_hovered {
                    pressed = true;
                }
                self.active_id = 0;
            }
        }

        (is_hovered, held, pressed)
    }

    // --- Widgets ---

    pub fn text(&mut self, painter: &mut dyn Painter, string: &str) {
        let w = painter.text_width(string);
        let h = painter.line_height();
        let bb = self.item_size(Vec2::new(w, h));
        painter.text(bb, ALIGN_LEFT | ALIGN_VCENTER, string, self.style.text, false);
    }

    pub fn button(&mut self, painter: &mut dyn Painter, label: &str, size_arg: Vec2) -> bool {
        let id = self.get_id(label);
        let label_w = painter.text_width(label);
        let line_h = painter.line_height();

        let w = if size_arg.x > 0.0 { size_arg.x } else { label_w + self.style.frame_padding.x * 2.0 };
        let h = if size_arg.y > 0.0 { size_arg.y } else { line_h + self.style.frame_padding.y * 2.0 };

        let bb = self.item_size(Vec2::new(w, h));
        let (hovered, held, pressed) = self.button_behavior(bb, id);

        let bg_col = if held {
            self.style.button_active
        } else if hovered {
            self.style.button_hovered
        } else {
            self.style.button
        };

        painter.fill_rect(bb, bg_col);
        painter.stroke_rect(bb, self.style.border, None, 1.0);
        painter.text(bb, ALIGN_CENTER, label, self.style.text, false);

        pressed
    }

    pub fn checkbox(&mut self, painter: &mut dyn Painter, label: &str, v: &mut bool) -> bool {
        let id = self.get_id(label);
        let line_h = painter.line_height();
        let square_sz = line_h;
        let label_w = painter.text_width(label);
        let total_w = square_sz + self.style.item_inner_spacing.x + label_w;

        let bb = self.item_size(Vec2::new(total_w, square_sz));
        let (hovered, _held, pressed) = self.button_behavior(bb, id);

        if pressed {
            *v = !*v;
        }

        let check_bb = Rect::new(bb.x, bb.y, square_sz, square_sz);
        let frame_col = if hovered { self.style.frame_bg_hovered } else { self.style.frame_bg };
        painter.fill_rect(check_bb, frame_col);
        painter.stroke_rect(check_bb, self.style.border, None, 1.0);

        if *v {
            let inset = 3.0;
            let tick = check_bb.inset(inset, inset);
            painter.fill_rect(tick, CHECK_MARK);
        }

        let text_bb = Rect::new(check_bb.x + square_sz + self.style.item_inner_spacing.x, bb.y, label_w, square_sz);
        painter.text(text_bb, ALIGN_LEFT | ALIGN_VCENTER, label, self.style.text, false);

        pressed
    }

    pub fn slider_float(&mut self, painter: &mut dyn Painter, label: &str, v: &mut f32, v_min: f32, v_max: f32, _format: &str) -> bool {
        let id = self.get_id(label);
        let line_h = painter.line_height();
        let total_w = 200.0; // default frame width
        let bb = self.item_size(Vec2::new(total_w, line_h + self.style.frame_padding.y * 2.0));

        let frame_bb = Rect::new(bb.x, bb.y, 120.0, bb.h);
        let (hovered, held, _) = self.button_behavior(frame_bb, id);

        let mut changed = false;
        if held {
            let t = ((self.io.mouse_pos.x - frame_bb.x) / frame_bb.w).clamp(0.0, 1.0);
            let new_val = v_min + t * (v_max - v_min);
            if (new_val - *v).abs() > 0.0001 {
                *v = new_val;
                changed = true;
            }
        }

        // Draw frame background
        let bg_col = if hovered { self.style.frame_bg_hovered } else { self.style.frame_bg };
        painter.fill_rect(frame_bb, bg_col);
        painter.stroke_rect(frame_bb, self.style.border, None, 1.0);

        // Draw grab
        let grab_w = self.style.grab_min_size;
        let t = ((*v - v_min) / (v_max - v_min)).clamp(0.0, 1.0);
        let grab_x = frame_bb.x + t * (frame_bb.w - grab_w);
        let grab_bb = Rect::new(grab_x, frame_bb.y, grab_w, frame_bb.h);
        let grab_col = if held { self.style.slider_grab_active } else { self.style.slider_grab };
        painter.fill_rect(grab_bb, grab_col);

        // Draw value text inside frame
        let val_str = format!("{:.3}", *v);
        painter.text(frame_bb, ALIGN_CENTER, &val_str, self.style.text, false);

        // Draw label beside
        let label_bb = Rect::new(frame_bb.x + frame_bb.w + self.style.item_inner_spacing.x, bb.y, bb.w - frame_bb.w, bb.h);
        painter.text(label_bb, ALIGN_LEFT | ALIGN_VCENTER, label, self.style.text, false);

        changed
    }

    pub fn separator(&mut self, painter: &mut dyn Painter) {
        if let Some(idx) = self.current_window_idx {
            let win = &self.windows[idx];
            let bb = self.item_size(Vec2::new(win.rect.w - self.style.window_padding.x * 2.0, 1.0));
            painter.fill_rect(bb, self.style.border);
        }
    }

    // --- Ambient Painter Methods for C ABI and Rust Ergonomics ---

    pub fn begin_window(&mut self, name: &str, p_open: Option<&mut bool>, flags: u32) -> bool {
        if let Some(ptr) = self.active_painter {
            let painter = unsafe { &mut *ptr };
            self.begin(painter, name, p_open, flags)
        } else {
            false
        }
    }

    pub fn end_window(&mut self) {
        if let Some(ptr) = self.active_painter {
            let painter = unsafe { &mut *ptr };
            self.end(painter);
        }
    }

    pub fn text_unformatted(&mut self, string: &str) {
        if let Some(ptr) = self.active_painter {
            let painter = unsafe { &mut *ptr };
            self.text(painter, string);
        }
    }

    pub fn button_simple(&mut self, label: &str, size_arg: Vec2) -> bool {
        if let Some(ptr) = self.active_painter {
            let painter = unsafe { &mut *ptr };
            self.button(painter, label, size_arg)
        } else {
            false
        }
    }

    pub fn checkbox_simple(&mut self, label: &str, v: &mut bool) -> bool {
        if let Some(ptr) = self.active_painter {
            let painter = unsafe { &mut *ptr };
            self.checkbox(painter, label, v)
        } else {
            false
        }
    }

    pub fn slider_float_simple(&mut self, label: &str, v: &mut f32, v_min: f32, v_max: f32, format: &str) -> bool {
        if let Some(ptr) = self.active_painter {
            let painter = unsafe { &mut *ptr };
            self.slider_float(painter, label, v, v_min, v_max, format)
        } else {
            false
        }
    }

    pub fn separator_simple(&mut self) {
        if let Some(ptr) = self.active_painter {
            let painter = unsafe { &mut *ptr };
            self.separator(painter);
        }
    }
}
