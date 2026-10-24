//! Multi-Window Docking and Tabbed DockSpace Engine for EMTK.
//!
//! Provides binary spatial partition tree splitting, tab strips, sticky window snapping,
//! and Dear ImGui DockSpace / DockBuilder compatible APIs.

use std::collections::HashMap;
use crate::types::{Color, Rect, Vec2, ALIGN_CENTER};
use crate::painter::Painter;

#[repr(C)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SplitDir {
    Left = 0,
    Right = 1,
    Up = 2,
    Down = 3,
}

#[repr(C)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SplitSide {
    First = 0,
    Second = 1,
}

#[derive(Debug, Clone)]
pub enum DockNodeData {
    Leaf {
        windows: Vec<String>,
        active_tab_index: usize,
    },
    Split {
        dir: SplitDir,
        ratio: f32,
        child_0: u32,
        child_1: u32,
        collapsible: bool,
        collapsed: Option<SplitSide>,
        uncollapsed_ratio: Option<f32>,
    },
}

#[derive(Debug, Clone)]
pub struct DockNode {
    pub id: u32,
    pub rect: Rect,
    pub data: DockNodeData,
    pub parent_id: Option<u32>,
}

impl DockNode {
    pub fn new_leaf(id: u32, rect: Rect) -> Self {
        Self {
            id,
            rect,
            data: DockNodeData::Leaf {
                windows: Vec::new(),
                active_tab_index: 0,
            },
            parent_id: None,
        }
    }
}

#[derive(Debug, Clone)]
pub struct DockSpace {
    pub id: u32,
    pub rect: Rect,
    pub nodes: HashMap<u32, DockNode>,
    pub window_to_node: HashMap<String, u32>,
    pub next_node_id: u32,
}

impl DockSpace {
    pub fn new(id: u32) -> Self {
        let mut ds = Self {
            id,
            rect: Rect::ZERO,
            nodes: HashMap::new(),
            window_to_node: HashMap::new(),
            next_node_id: id + 1,
        };
        // Create root leaf node
        let root = DockNode::new_leaf(id, Rect::ZERO);
        ds.nodes.insert(id, root);
        ds
    }

    pub fn set_rect(&mut self, rect: Rect) {
        self.rect = rect;
        self.update_node_rects(self.id, rect);
    }

    fn update_node_rects(&mut self, node_id: u32, rect: Rect) {
        if let Some(node) = self.nodes.get_mut(&node_id) {
            node.rect = rect;
            match node.data.clone() {
                DockNodeData::Leaf { .. } => {}
                DockNodeData::Split { dir, ratio, child_0, child_1, collapsed, .. } => {
                    let (r0, r1) = match collapsed {
                        Some(SplitSide::First) => {
                            let r0 = match dir {
                                SplitDir::Left | SplitDir::Right => Rect::new(rect.x, rect.y, 0.0, rect.h),
                                SplitDir::Up | SplitDir::Down => Rect::new(rect.x, rect.y, rect.w, 0.0),
                            };
                            (r0, rect)
                        }
                        Some(SplitSide::Second) => {
                            let r1 = match dir {
                                SplitDir::Left => Rect::new(rect.x + rect.w, rect.y, 0.0, rect.h),
                                SplitDir::Right => Rect::new(rect.x, rect.y, 0.0, rect.h),
                                SplitDir::Up => Rect::new(rect.x, rect.y + rect.h, rect.w, 0.0),
                                SplitDir::Down => Rect::new(rect.x, rect.y, rect.w, 0.0),
                            };
                            (rect, r1)
                        }
                        None => match dir {
                            SplitDir::Left => {
                                let w0 = rect.w * ratio;
                                (
                                    Rect::new(rect.x, rect.y, w0, rect.h),
                                    Rect::new(rect.x + w0, rect.y, rect.w - w0, rect.h),
                                )
                            }
                            SplitDir::Right => {
                                let w1 = rect.w * ratio;
                                (
                                    Rect::new(rect.x, rect.y, rect.w - w1, rect.h),
                                    Rect::new(rect.x + rect.w - w1, rect.y, w1, rect.h),
                                )
                            }
                            SplitDir::Up => {
                                let h0 = rect.h * ratio;
                                (
                                    Rect::new(rect.x, rect.y, rect.w, h0),
                                    Rect::new(rect.x, rect.y + h0, rect.w, rect.h - h0),
                                )
                            }
                            SplitDir::Down => {
                                let h1 = rect.h * ratio;
                                (
                                    Rect::new(rect.x, rect.y, rect.w, rect.h - h1),
                                    Rect::new(rect.x, rect.y + rect.h - h1, rect.w, h1),
                                )
                            }
                        },
                    };
                    self.update_node_rects(child_0, r0);
                    self.update_node_rects(child_1, r1);
                }
            }
        }
    }

    pub fn collapse_node(&mut self, node_id: u32, side: SplitSide) {
        if let Some(node) = self.nodes.get_mut(&node_id) {
            if let DockNodeData::Split { ref mut collapsed, ref mut uncollapsed_ratio, ratio, .. } = node.data {
                if collapsed.is_none() {
                    *uncollapsed_ratio = Some(ratio);
                }
                *collapsed = Some(side);
            }
        }
        let r = self.nodes.get(&node_id).map(|n| n.rect).unwrap_or(Rect::ZERO);
        self.update_node_rects(node_id, r);
    }

    pub fn uncollapse_node(&mut self, node_id: u32) {
        if let Some(node) = self.nodes.get_mut(&node_id) {
            if let DockNodeData::Split { ref mut collapsed, ref mut ratio, uncollapsed_ratio, .. } = node.data {
                *collapsed = None;
                if let Some(ur) = uncollapsed_ratio {
                    *ratio = ur;
                }
            }
        }
        let r = self.nodes.get(&node_id).map(|n| n.rect).unwrap_or(Rect::ZERO);
        self.update_node_rects(node_id, r);
    }

    pub fn toggle_collapse_node(&mut self, node_id: u32, side: SplitSide) {
        if self.is_node_collapsed(node_id).is_some() {
            self.uncollapse_node(node_id);
        } else {
            self.collapse_node(node_id, side);
        }
    }

    pub fn is_node_collapsed(&self, node_id: u32) -> Option<SplitSide> {
        if let Some(node) = self.nodes.get(&node_id) {
            if let DockNodeData::Split { collapsed, .. } = node.data {
                return collapsed;
            }
        }
        None
    }

    pub fn split_node(
        &mut self,
        node_id: u32,
        dir: SplitDir,
        ratio: f32,
        out_id_at_dir: &mut u32,
        out_id_at_opposite: &mut u32,
    ) {
        let node_rect = self.nodes.get(&node_id).map(|n| n.rect).unwrap_or(Rect::ZERO);

        let id_0 = self.next_node_id;
        self.next_node_id += 1;
        let id_1 = self.next_node_id;
        self.next_node_id += 1;

        let mut child_0 = DockNode::new_leaf(id_0, Rect::ZERO);
        child_0.parent_id = Some(node_id);
        let mut child_1 = DockNode::new_leaf(id_1, Rect::ZERO);
        child_1.parent_id = Some(node_id);

        self.nodes.insert(id_0, child_0);
        self.nodes.insert(id_1, child_1);

        if let Some(parent) = self.nodes.get_mut(&node_id) {
            parent.data = DockNodeData::Split {
                dir,
                ratio,
                child_0: id_0,
                child_1: id_1,
                collapsible: true,
                collapsed: None,
                uncollapsed_ratio: Some(ratio),
            };
        }

        match dir {
            SplitDir::Left | SplitDir::Up => {
                *out_id_at_dir = id_0;
                *out_id_at_opposite = id_1;
            }
            SplitDir::Right | SplitDir::Down => {
                *out_id_at_dir = id_1;
                *out_id_at_opposite = id_0;
            }
        }

        self.update_node_rects(node_id, node_rect);
    }

    pub fn dock_window(&mut self, window_name: &str, node_id: u32) {
        self.window_to_node.insert(window_name.to_string(), node_id);
        if let Some(node) = self.nodes.get_mut(&node_id) {
            if let DockNodeData::Leaf { ref mut windows, .. } = node.data {
                if !windows.contains(&window_name.to_string()) {
                    windows.push(window_name.to_string());
                }
            }
        }
    }

    pub fn get_window_rect(&self, window_name: &str) -> Option<Rect> {
        let node_id = self.window_to_node.get(window_name)?;
        let node = self.nodes.get(node_id)?;
        let tab_bar_h = 24.0;
        Some(Rect::new(node.rect.x, node.rect.y + tab_bar_h, node.rect.w, (node.rect.h - tab_bar_h).max(0.0)))
    }

    pub fn is_window_tab_active(&self, window_name: &str) -> bool {
        if let Some(&node_id) = self.window_to_node.get(window_name) {
            if let Some(node) = self.nodes.get(&node_id) {
                if let DockNodeData::Leaf { ref windows, active_tab_index } = node.data {
                    if let Some(active_name) = windows.get(active_tab_index) {
                        return active_name == window_name;
                    }
                }
            }
        }
        true
    }

    pub fn render_tabs(&mut self, painter: &mut dyn Painter, mouse_pos: Vec2, mouse_clicked: bool) {
        let tab_h = 24.0;
        let tab_w = 90.0;

        let leaf_ids: Vec<u32> = self.nodes.iter().filter_map(|(&id, node)| {
            if let DockNodeData::Leaf { .. } = node.data {
                Some(id)
            } else {
                None
            }
        }).collect();

        for id in leaf_ids {
            let mut newly_selected_tab = None;
            if let Some(node) = self.nodes.get(&id) {
                if let DockNodeData::Leaf { ref windows, active_tab_index } = node.data {
                    if windows.is_empty() {
                        continue;
                    }

                    // Render Tab Bar background
                    let bar_rect = Rect::new(node.rect.x, node.rect.y, node.rect.w, tab_h);
                    painter.fill_rect(bar_rect, Color::rgb(35, 38, 46));
                    painter.stroke_rect(bar_rect, Color::rgb(25, 27, 33), None, 1.0);

                    for (idx, name) in windows.iter().enumerate() {
                        let tab_rect = Rect::new(node.rect.x + (idx as f32) * tab_w, node.rect.y, tab_w, tab_h);
                        let is_active = idx == active_tab_index;
                        let is_hovered = tab_rect.contains(mouse_pos);

                        if is_hovered && mouse_clicked {
                            newly_selected_tab = Some(idx);
                        }

                        let bg_col = if is_active {
                            Color::rgb(55, 62, 78)
                        } else if is_hovered {
                            Color::rgb(45, 50, 62)
                        } else {
                            Color::rgb(35, 38, 46)
                        };

                        painter.fill_rect(tab_rect, bg_col);
                        painter.stroke_rect(tab_rect, Color::rgb(25, 27, 33), None, 1.0);
                        painter.text(tab_rect, ALIGN_CENTER, name, Color::rgb(220, 225, 235), is_active);
                    }
                }
            }

            if let Some(new_idx) = newly_selected_tab {
                if let Some(node) = self.nodes.get_mut(&id) {
                    if let DockNodeData::Leaf { ref mut active_tab_index, .. } = node.data {
                        *active_tab_index = new_idx;
                    }
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_dockspace_binary_split() {
        let mut ds = DockSpace::new(100);
        ds.set_rect(Rect::new(0.0, 0.0, 1000.0, 800.0));

        let mut left_id = 0;
        let mut right_id = 0;
        ds.split_node(100, SplitDir::Left, 0.3, &mut left_id, &mut right_id);

        ds.dock_window("PanelLeft", left_id);
        ds.dock_window("PanelRight", right_id);

        let left_rect = ds.get_window_rect("PanelLeft").unwrap();
        let right_rect = ds.get_window_rect("PanelRight").unwrap();

        assert!((left_rect.w - 300.0).abs() < 1.0);
        assert!((right_rect.w - 700.0).abs() < 1.0);
        assert!(ds.is_window_tab_active("PanelLeft"));
        assert!(ds.is_window_tab_active("PanelRight"));
    }

    #[test]
    fn test_dockspace_collapsible_split() {
        let mut ds = DockSpace::new(100);
        ds.set_rect(Rect::new(0.0, 0.0, 1000.0, 800.0));

        let mut left_id = 0;
        let mut right_id = 0;
        ds.split_node(100, SplitDir::Left, 0.3, &mut left_id, &mut right_id);

        ds.dock_window("PanelLeft", left_id);
        ds.dock_window("PanelRight", right_id);

        // Collapse left pane (First side)
        ds.collapse_node(100, SplitSide::First);
        assert_eq!(ds.is_node_collapsed(100), Some(SplitSide::First));

        let left_rect = ds.get_window_rect("PanelLeft").unwrap();
        let right_rect = ds.get_window_rect("PanelRight").unwrap();

        assert_eq!(left_rect.w, 0.0);
        assert!((right_rect.w - 1000.0).abs() < 1.0);

        // Uncollapse
        ds.uncollapse_node(100);
        assert_eq!(ds.is_node_collapsed(100), None);

        let left_rect2 = ds.get_window_rect("PanelLeft").unwrap();
        let right_rect2 = ds.get_window_rect("PanelRight").unwrap();

        assert!((left_rect2.w - 300.0).abs() < 1.0);
        assert!((right_rect2.w - 700.0).abs() < 1.0);
    }
}

