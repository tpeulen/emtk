//! EMTK Style and Colors: Standard Dark Theme and Metrics.

use crate::types::{Color, Vec2};

pub const TEXT: Color = Color::rgb(235, 235, 240);
pub const DIM: Color = Color::rgb(150, 150, 160);
pub const LINKED: Color = Color::rgb(140, 150, 235);
pub const GOLD: Color = Color::rgb(245, 225, 128);
pub const TEXT_DISABLED: Color = Color::rgb(128, 128, 128);

pub const WINDOW_BG: Color = Color::rgba(15, 15, 15, 240);
pub const POPUP_BG: Color = Color::rgba(20, 20, 20, 240);
pub const BORDER: Color = Color::rgba(90, 90, 96, 200);
pub const FRAME_BG: Color = Color::rgba(50, 50, 56, 220);
pub const FRAME_BG_HOVERED: Color = Color::rgba(66, 150, 250, 102);
pub const FRAME_BG_ACTIVE: Color = Color::rgba(66, 150, 250, 171);
pub const TITLE_BG: Color = Color::rgba(10, 10, 10, 255);
pub const TITLE_BG_ACTIVE: Color = Color::rgba(41, 74, 122, 255);
pub const MENU_BAR_BG: Color = Color::rgba(36, 36, 36, 255);

pub const CHECK_MARK: Color = Color::rgba(66, 150, 250, 255);
pub const SLIDER_GRAB: Color = Color::rgba(61, 133, 224, 255);
pub const SLIDER_GRAB_ACTIVE: Color = Color::rgba(66, 150, 250, 255);
pub const BUTTON: Color = Color::rgba(66, 150, 250, 102);
pub const BUTTON_HOVERED: Color = Color::rgba(66, 150, 250, 255);
pub const BUTTON_ACTIVE: Color = Color::rgba(15, 135, 250, 255);
pub const HEADER: Color = Color::rgba(66, 150, 250, 79);
pub const HEADER_HOVERED: Color = Color::rgba(66, 150, 250, 204);
pub const HEADER_ACTIVE: Color = Color::rgba(66, 150, 250, 255);
pub const SEPARATOR: Color = BORDER;

#[derive(Debug, Clone)]
pub struct Style {
    pub window_padding: Vec2,
    pub window_rounding: f32,
    pub frame_padding: Vec2,
    pub frame_rounding: f32,
    pub item_spacing: Vec2,
    pub item_inner_spacing: Vec2,
    pub grab_min_size: f32,
    pub grab_rounding: f32,

    pub text: Color,
    pub window_bg: Color,
    pub border: Color,
    pub frame_bg: Color,
    pub frame_bg_hovered: Color,
    pub frame_bg_active: Color,
    pub button: Color,
    pub button_hovered: Color,
    pub button_active: Color,
    pub check_mark: Color,
    pub slider_grab: Color,
    pub slider_grab_active: Color,
    pub header: Color,
    pub header_hovered: Color,
    pub header_active: Color,
    pub title_bg: Color,
    pub title_bg_active: Color,
}

impl Default for Style {
    fn default() -> Self {
        Self {
            window_padding: Vec2::new(8.0, 8.0),
            window_rounding: 4.0,
            frame_padding: Vec2::new(4.0, 3.0),
            frame_rounding: 3.0,
            item_spacing: Vec2::new(8.0, 4.0),
            item_inner_spacing: Vec2::new(4.0, 4.0),
            grab_min_size: 10.0,
            grab_rounding: 2.0,

            text: TEXT,
            window_bg: WINDOW_BG,
            border: BORDER,
            frame_bg: FRAME_BG,
            frame_bg_hovered: FRAME_BG_HOVERED,
            frame_bg_active: FRAME_BG_ACTIVE,
            button: BUTTON,
            button_hovered: BUTTON_HOVERED,
            button_active: BUTTON_ACTIVE,
            check_mark: CHECK_MARK,
            slider_grab: SLIDER_GRAB,
            slider_grab_active: SLIDER_GRAB_ACTIVE,
            header: HEADER,
            header_hovered: HEADER_HOVERED,
            header_active: HEADER_ACTIVE,
            title_bg: TITLE_BG,
            title_bg_active: TITLE_BG_ACTIVE,
        }
    }
}
