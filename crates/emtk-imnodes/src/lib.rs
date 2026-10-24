//! EMTK Immediate-Mode Node Graph Editor (Nelarius/imnodes compatible)
//!
//! Provides an immediate-mode canvas for interactive dataflow graphs, neural networks,
//! signal processing diagrams, and visual programming nodes.

use std::collections::{HashMap, HashSet};
use emtk_core::{
    types::{Color, Rect, Vec2, ALIGN_LEFT, ALIGN_VCENTER},
    painter::Painter,
    context::Context,
};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PinShape {
    Circle,
    CircleFilled,
    Quad,
    QuadFilled,
    Triangle,
    TriangleFilled,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AttributeType {
    None,
    Input,
    Output,
}

#[derive(Debug, Clone)]
pub struct NodeState {
    pub id: i32,
    pub grid_pos: Vec2,
    pub size: Vec2,
    pub selected: bool,
}

#[derive(Debug, Clone)]
pub struct PinRecord {
    pub id: i32,
    pub node_id: i32,
    pub attr_type: AttributeType,
    pub shape: PinShape,
    pub screen_pos: Vec2,
}

#[derive(Debug, Clone)]
pub struct LinkRecord {
    pub id: i32,
    pub start_pin_id: i32,
    pub end_pin_id: i32,
}

#[derive(Debug, Clone)]
pub struct EditorColors {
    pub grid_bg: Color,
    pub grid_line: Color,
    pub node_bg: Color,
    pub node_bg_hovered: Color,
    pub node_bg_selected: Color,
    pub node_title_bar: Color,
    pub node_title_bar_hovered: Color,
    pub node_title_bar_selected: Color,
    pub node_outline: Color,
    pub node_outline_selected: Color,
    pub pin: Color,
    pub pin_hovered: Color,
    pub link: Color,
    pub link_hovered: Color,
    pub link_selected: Color,
    pub title_text: Color,
}

impl Default for EditorColors {
    fn default() -> Self {
        Self {
            grid_bg: Color::rgb(32, 35, 42),
            grid_line: Color::rgb(42, 46, 56),
            node_bg: Color::rgb(45, 49, 60),
            node_bg_hovered: Color::rgb(52, 57, 70),
            node_bg_selected: Color::rgb(58, 64, 78),
            node_title_bar: Color::rgb(60, 72, 94),
            node_title_bar_hovered: Color::rgb(70, 84, 110),
            node_title_bar_selected: Color::rgb(82, 98, 128),
            node_outline: Color::rgb(25, 27, 33),
            node_outline_selected: Color::rgb(90, 160, 255),
            pin: Color::rgb(80, 160, 255),
            pin_hovered: Color::rgb(120, 190, 255),
            link: Color::rgba(80, 160, 255, 210),
            link_hovered: Color::rgba(130, 200, 255, 255),
            link_selected: Color::rgba(255, 180, 50, 255),
            title_text: Color::rgb(230, 235, 245),
        }
    }
}

#[derive(Debug, Clone)]
pub struct EditorStyle {
    pub grid_spacing: f32,
    pub node_corner_rounding: f32,
    pub node_padding: Vec2,
    pub pin_radius: f32,
    pub link_thickness: f32,
    pub colors: EditorColors,
}

impl Default for EditorStyle {
    fn default() -> Self {
        Self {
            grid_spacing: 32.0,
            node_corner_rounding: 4.0,
            node_padding: Vec2::new(8.0, 8.0),
            pin_radius: 4.5,
            link_thickness: 2.5,
            colors: EditorColors::default(),
        }
    }
}

pub struct EditorContext {
    pub pan: Vec2,
    pub zoom: f32,
    pub style: EditorStyle,
    pub node_states: HashMap<i32, NodeState>,
    pub selected_nodes: HashSet<i32>,
    pub selected_links: HashSet<i32>,

    // Transient frame data
    pub current_editor_rect: Rect,
    pub current_node_id: Option<i32>,
    pub current_attr_id: Option<i32>,
    pub current_attr_type: AttributeType,
    pub current_pins: Vec<PinRecord>,
    pub current_links: Vec<LinkRecord>,

    // Interactivity
    pub hovered_node_id: Option<i32>,
    pub hovered_pin_id: Option<i32>,
    pub hovered_link_id: Option<i32>,
    pub active_pin_id: Option<i32>, // link dragging start pin
    pub link_created: Option<(i32, i32)>,
    pub link_destroyed: Option<i32>,

    // Panning & dragging
    pub is_panning: bool,
    pub pan_start_pos: Vec2,
    pub pan_start_offset: Vec2,
    pub is_dragging_nodes: bool,
    pub drag_start_mouse: Vec2,
    pub drag_start_node_positions: HashMap<i32, Vec2>,
}

impl Default for EditorContext {
    fn default() -> Self {
        Self::new()
    }
}

impl EditorContext {
    pub fn new() -> Self {
        Self {
            pan: Vec2::new(0.0, 0.0),
            zoom: 1.0,
            style: EditorStyle::default(),
            node_states: HashMap::new(),
            selected_nodes: HashSet::new(),
            selected_links: HashSet::new(),

            current_editor_rect: Rect::ZERO,
            current_node_id: None,
            current_attr_id: None,
            current_attr_type: AttributeType::None,
            current_pins: Vec::new(),
            current_links: Vec::new(),

            hovered_node_id: None,
            hovered_pin_id: None,
            hovered_link_id: None,
            active_pin_id: None,
            link_created: None,
            link_destroyed: None,

            is_panning: false,
            pan_start_pos: Vec2::ZERO,
            pan_start_offset: Vec2::ZERO,
            is_dragging_nodes: false,
            drag_start_mouse: Vec2::ZERO,
            drag_start_node_positions: HashMap::new(),
        }
    }

    pub fn set_node_grid_space_pos(&mut self, id: i32, pos: Vec2) {
        if let Some(node) = self.node_states.get_mut(&id) {
            node.grid_pos = pos;
        } else {
            self.node_states.insert(id, NodeState {
                id,
                grid_pos: pos,
                size: Vec2::new(140.0, 80.0),
                selected: false,
            });
        }
    }

    pub fn get_node_grid_space_pos(&self, id: i32) -> Vec2 {
        self.node_states.get(&id).map(|n| n.grid_pos).unwrap_or(Vec2::ZERO)
    }

    pub fn is_node_selected(&self, id: i32) -> bool {
        self.selected_nodes.contains(&id)
    }

    pub fn is_link_created(&self) -> Option<(i32, i32)> {
        self.link_created
    }

    pub fn is_link_destroyed(&self) -> Option<i32> {
        self.link_destroyed
    }

    pub fn grid_to_screen(&self, grid: Vec2) -> Vec2 {
        Vec2::new(
            self.current_editor_rect.x + (grid.x + self.pan.x) * self.zoom,
            self.current_editor_rect.y + (grid.y + self.pan.y) * self.zoom,
        )
    }

    pub fn screen_to_grid(&self, screen: Vec2) -> Vec2 {
        Vec2::new(
            (screen.x - self.current_editor_rect.x) / self.zoom - self.pan.x,
            (screen.y - self.current_editor_rect.y) / self.zoom - self.pan.y,
        )
    }
}

// Global active editor context pointer for C ABI ergonomics
static mut G_ACTIVE_EDITOR: Option<*mut EditorContext> = None;

pub fn set_current_editor_context(ctx: &mut EditorContext) {
    unsafe {
        G_ACTIVE_EDITOR = Some(ctx as *mut EditorContext);
    }
}

pub fn get_current_editor_context() -> Option<&'static mut EditorContext> {
    unsafe {
        G_ACTIVE_EDITOR.map(|p| &mut *p)
    }
}

// --- Immediate Mode API ---

pub fn begin_node_editor(editor: &mut EditorContext, rect: Rect) {
    editor.current_editor_rect = rect;
    editor.current_pins.clear();
    editor.current_links.clear();
    editor.link_created = None;
    editor.link_destroyed = None;
}

pub fn begin_node(editor: &mut EditorContext, id: i32) {
    editor.current_node_id = Some(id);
    editor.node_states.entry(id).or_insert_with(|| NodeState {
        id,
        grid_pos: Vec2::new(30.0 + (id as f32 * 40.0) % 200.0, 30.0 + (id as f32 * 30.0) % 150.0),
        size: Vec2::new(140.0, 80.0),
        selected: false,
    });
}

pub fn begin_node_title_bar(_editor: &mut EditorContext) {
    // Marker for layout hierarchy
}

pub fn end_node_title_bar(_editor: &mut EditorContext) {
}

pub fn begin_input_attribute(editor: &mut EditorContext, id: i32, shape: PinShape) {
    editor.current_attr_id = Some(id);
    editor.current_attr_type = AttributeType::Input;

    if let Some(node_id) = editor.current_node_id {
        let node_pos = editor.grid_to_screen(editor.get_node_grid_space_pos(node_id));
        let pin_pos = Vec2::new(node_pos.x, node_pos.y + 35.0 + (editor.current_pins.len() as f32 * 18.0));
        editor.current_pins.push(PinRecord {
            id,
            node_id,
            attr_type: AttributeType::Input,
            shape,
            screen_pos: pin_pos,
        });
    }
}

pub fn end_input_attribute(editor: &mut EditorContext) {
    editor.current_attr_id = None;
    editor.current_attr_type = AttributeType::None;
}

pub fn begin_output_attribute(editor: &mut EditorContext, id: i32, shape: PinShape) {
    editor.current_attr_id = Some(id);
    editor.current_attr_type = AttributeType::Output;

    if let Some(node_id) = editor.current_node_id {
        let node_pos = editor.grid_to_screen(editor.get_node_grid_space_pos(node_id));
        let node_w = editor.node_states.get(&node_id).map(|n| n.size.x).unwrap_or(140.0);
        let pin_pos = Vec2::new(node_pos.x + node_w, node_pos.y + 35.0 + (editor.current_pins.len() as f32 * 18.0));
        editor.current_pins.push(PinRecord {
            id,
            node_id,
            attr_type: AttributeType::Output,
            shape,
            screen_pos: pin_pos,
        });
    }
}

pub fn end_output_attribute(editor: &mut EditorContext) {
    editor.current_attr_id = None;
    editor.current_attr_type = AttributeType::None;
}

pub fn end_node(editor: &mut EditorContext) {
    editor.current_node_id = None;
}

pub fn link(editor: &mut EditorContext, id: i32, start_pin_id: i32, end_pin_id: i32) {
    editor.current_links.push(LinkRecord {
        id,
        start_pin_id,
        end_pin_id,
    });
}

/// Draw cubic bezier curve for a link
fn draw_bezier_link(painter: &mut dyn Painter, p0: Vec2, p3: Vec2, thickness: f32, color: Color) {
    let dx = (p3.x - p0.x).abs().max(40.0) * 0.5;
    let p1 = Vec2::new(p0.x + dx, p0.y);
    let p2 = Vec2::new(p3.x - dx, p3.y);

    let segments = 24;
    let mut prev = p0;

    for i in 1..=segments {
        let t = i as f32 / segments as f32;
        let it = 1.0 - t;
        // B(t) = (1-t)^3 p0 + 3(1-t)^2 t p1 + 3(1-t) t^2 p2 + t^3 p3
        let curr = Vec2::new(
            it * it * it * p0.x + 3.0 * it * it * t * p1.x + 3.0 * it * t * t * p2.x + t * t * t * p3.x,
            it * it * it * p0.y + 3.0 * it * it * t * p1.y + 3.0 * it * t * t * p2.y + t * t * t * p3.y,
        );

        painter.line(prev, curr, thickness, color);
        prev = curr;
    }
}

pub fn end_node_editor(ctx: &mut Context, painter: &mut dyn Painter, editor: &mut EditorContext) {
    let bounds = editor.current_editor_rect;
    painter.push_clip(bounds);

    // 1. Grid background
    painter.fill_rect(bounds, editor.style.colors.grid_bg);

    let grid_step = editor.style.grid_spacing * editor.zoom;
    if grid_step > 4.0 {
        let off_x = (editor.pan.x * editor.zoom) % grid_step;
        let off_y = (editor.pan.y * editor.zoom) % grid_step;

        let mut x = bounds.x + off_x;
        while x < bounds.x + bounds.w {
            painter.line(Vec2::new(x, bounds.y), Vec2::new(x, bounds.y + bounds.h), 1.0, editor.style.colors.grid_line);
            x += grid_step;
        }

        let mut y = bounds.y + off_y;
        while y < bounds.y + bounds.h {
            painter.line(Vec2::new(bounds.x, y), Vec2::new(bounds.x + bounds.w, y), 1.0, editor.style.colors.grid_line);
            y += grid_step;
        }
    }

    // 2. Process Mouse Interaction (Panning & Node Dragging)
    let mouse_pos = ctx.io.mouse_pos;
    let is_inside = bounds.contains(mouse_pos);

    // Middle click or Alt+Left click pans
    if is_inside && ctx.io.mouse_clicked[2] {
        editor.is_panning = true;
        editor.pan_start_pos = mouse_pos;
        editor.pan_start_offset = editor.pan;
    }
    if editor.is_panning {
        if ctx.io.mouse_down[2] {
            let delta = mouse_pos - editor.pan_start_pos;
            editor.pan = editor.pan_start_offset + Vec2::new(delta.x / editor.zoom, delta.y / editor.zoom);
        } else {
            editor.is_panning = false;
        }
    }

    // 3. Render Links
    let pin_map: HashMap<i32, Vec2> = editor.current_pins.iter().map(|p| (p.id, p.screen_pos)).collect();

    for l in &editor.current_links {
        if let (Some(&start_pos), Some(&end_pos)) = (pin_map.get(&l.start_pin_id), pin_map.get(&l.end_pin_id)) {
            let is_sel = editor.selected_links.contains(&l.id);
            let col = if is_sel {
                editor.style.colors.link_selected
            } else {
                editor.style.colors.link
            };
            draw_bezier_link(painter, start_pos, end_pos, editor.style.link_thickness, col);
        }
    }

    // 4. Render Active Drag Link
    if let Some(start_pin) = editor.active_pin_id {
        if let Some(&p_pos) = pin_map.get(&start_pin) {
            draw_bezier_link(painter, p_pos, mouse_pos, editor.style.link_thickness, editor.style.colors.link_hovered);
        }
        if ctx.io.mouse_released[0] {
            // Check if dropped onto a target pin
            if let Some(end_pin) = editor.hovered_pin_id {
                if end_pin != start_pin {
                    editor.link_created = Some((start_pin, end_pin));
                }
            }
            editor.active_pin_id = None;
        }
    }

    // 5. Render Nodes
    editor.hovered_node_id = None;
    let mut clicked_node = None;

    // Snapshot keys to avoid borrow conflicts
    let node_ids: Vec<i32> = editor.node_states.keys().cloned().collect();
    for &id in &node_ids {
        if let Some(node) = editor.node_states.get(&id) {
            let screen_pos = editor.grid_to_screen(node.grid_pos);
            let node_rect = Rect::new(screen_pos.x, screen_pos.y, node.size.x, node.size.y);

            let is_hovered = node_rect.contains(mouse_pos) && is_inside;
            if is_hovered {
                editor.hovered_node_id = Some(id);
                if ctx.io.mouse_clicked[0] && editor.hovered_pin_id.is_none() {
                    clicked_node = Some(id);
                }
            }

            let is_selected = editor.selected_nodes.contains(&id);

            // Node Body
            let body_col = if is_selected {
                editor.style.colors.node_bg_selected
            } else if is_hovered {
                editor.style.colors.node_bg_hovered
            } else {
                editor.style.colors.node_bg
            };

            painter.fill_rect(node_rect, body_col);

            // Node Outline
            let outline_col = if is_selected {
                editor.style.colors.node_outline_selected
            } else {
                editor.style.colors.node_outline
            };
            painter.stroke_rect(node_rect, outline_col, None, if is_selected { 2.0 } else { 1.0 });

            // Title Bar
            let title_h = 24.0;
            let title_rect = Rect::new(node_rect.x, node_rect.y, node_rect.w, title_h);
            let title_col = if is_selected {
                editor.style.colors.node_title_bar_selected
            } else {
                editor.style.colors.node_title_bar
            };
            painter.fill_rect(title_rect, title_col);

            let title_text = format!("Node #{}", id);
            painter.text(
                Rect::new(title_rect.x + 8.0, title_rect.y, title_rect.w - 16.0, title_rect.h),
                ALIGN_LEFT | ALIGN_VCENTER,
                &title_text,
                editor.style.colors.title_text,
                true,
            );
        }
    }

    // Handle node selection & dragging
    if let Some(id) = clicked_node {
        if !ctx.io.key_ctrl && !editor.selected_nodes.contains(&id) {
            editor.selected_nodes.clear();
        }
        editor.selected_nodes.insert(id);

        editor.is_dragging_nodes = true;
        editor.drag_start_mouse = mouse_pos;
        editor.drag_start_node_positions.clear();
        for &sel_id in &editor.selected_nodes {
            if let Some(n) = editor.node_states.get(&sel_id) {
                editor.drag_start_node_positions.insert(sel_id, n.grid_pos);
            }
        }
    }

    if editor.is_dragging_nodes {
        if ctx.io.mouse_down[0] {
            let delta = (mouse_pos - editor.drag_start_mouse) * (1.0 / editor.zoom);
            for (&sel_id, &start_pos) in &editor.drag_start_node_positions {
                if let Some(n) = editor.node_states.get_mut(&sel_id) {
                    n.grid_pos = start_pos + delta;
                }
            }
        } else {
            editor.is_dragging_nodes = false;
        }
    }

    // 6. Render Pins
    editor.hovered_pin_id = None;
    for pin in &editor.current_pins {
        let p_rect = Rect::new(
            pin.screen_pos.x - editor.style.pin_radius * 1.5,
            pin.screen_pos.y - editor.style.pin_radius * 1.5,
            editor.style.pin_radius * 3.0,
            editor.style.pin_radius * 3.0,
        );

        let is_pin_hovered = p_rect.contains(mouse_pos) && is_inside;
        if is_pin_hovered {
            editor.hovered_pin_id = Some(pin.id);
            if ctx.io.mouse_clicked[0] {
                editor.active_pin_id = Some(pin.id);
            }
        }

        let pin_col = if is_pin_hovered || editor.active_pin_id == Some(pin.id) {
            editor.style.colors.pin_hovered
        } else {
            editor.style.colors.pin
        };

        // Render pin shape
        let r = editor.style.pin_radius;
        let center = pin.screen_pos;
        let circle_rect = Rect::new(center.x - r, center.y - r, r * 2.0, r * 2.0);
        painter.fill_rect(circle_rect, pin_col);
        painter.stroke_rect(circle_rect, editor.style.colors.node_outline, None, 1.0);
    }

    // Border around editor
    painter.stroke_rect(bounds, editor.style.colors.node_outline, None, 1.0);
    painter.pop_clip();
}

#[cfg(test)]
mod tests {
    use super::*;
    use emtk_core::software_painter::SoftwarePainter;

    #[test]
    fn test_node_editor_lifecycle() {
        let mut editor = EditorContext::new();
        let mut painter = SoftwarePainter::new(640, 480, Color::rgba(30, 32, 38, 255));
        let mut ctx = Context::new();

        begin_node_editor(&mut editor, Rect::new(10.0, 10.0, 600.0, 400.0));

        begin_node(&mut editor, 1);
        begin_node_title_bar(&mut editor);
        end_node_title_bar(&mut editor);
        begin_output_attribute(&mut editor, 10, PinShape::Circle);
        end_output_attribute(&mut editor);
        end_node(&mut editor);

        begin_node(&mut editor, 2);
        begin_input_attribute(&mut editor, 20, PinShape::Circle);
        end_input_attribute(&mut editor);
        end_node(&mut editor);

        link(&mut editor, 100, 10, 20);

        end_node_editor(&mut ctx, &mut painter, &mut editor);

        assert_eq!(editor.current_pins.len(), 2);
        assert_eq!(editor.current_links.len(), 1);
        assert!(editor.node_states.contains_key(&1));
        assert!(editor.node_states.contains_key(&2));
    }
}
