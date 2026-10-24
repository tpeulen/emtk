use std::cell::RefCell;
use std::ffi::CStr;
use std::os::raw::c_char;
use std::ptr;

use emtk_core::{Color, Context, QuadPainter, SoftwarePainter, Vec2};

thread_local! {
    static CURRENT_CONTEXT: RefCell<*mut Context> = RefCell::new(ptr::null_mut());
}

#[no_mangle]
pub extern "C" fn emtk_version() -> *const c_char {
    c"0.1.22".as_ptr()
}

#[no_mangle]
pub extern "C" fn emtk_create_context() -> *mut Context {
    let ctx = Box::new(Context::new());
    let ptr = Box::into_raw(ctx);
    CURRENT_CONTEXT.with(|c| {
        if c.borrow().is_null() {
            *c.borrow_mut() = ptr;
        }
    });
    ptr
}

#[no_mangle]
pub extern "C" fn emtk_destroy_context(ctx: *mut Context) {
    if !ctx.is_null() {
        CURRENT_CONTEXT.with(|c| {
            if *c.borrow() == ctx {
                *c.borrow_mut() = ptr::null_mut();
            }
        });
        unsafe { drop(Box::from_raw(ctx)) };
    }
}

#[no_mangle]
pub extern "C" fn emtk_set_current_context(ctx: *mut Context) {
    CURRENT_CONTEXT.with(|c| {
        *c.borrow_mut() = ctx;
    });
}

#[no_mangle]
pub extern "C" fn emtk_get_current_context() -> *mut Context {
    CURRENT_CONTEXT.with(|c| *c.borrow())
}

#[no_mangle]
pub extern "C" fn emtk_create_software_painter(
    width: u32,
    height: u32,
    r: u8,
    g: u8,
    b: u8,
    a: u8,
) -> *mut SoftwarePainter {
    let painter = Box::new(SoftwarePainter::new(width, height, Color::rgba(r, g, b, a)));
    Box::into_raw(painter)
}

#[no_mangle]
pub extern "C" fn emtk_destroy_software_painter(painter: *mut SoftwarePainter) {
    if !painter.is_null() {
        unsafe { drop(Box::from_raw(painter)) };
    }
}

#[no_mangle]
pub extern "C" fn emtk_software_painter_save_png(
    painter: *mut SoftwarePainter,
    path: *const c_char,
) -> bool {
    if painter.is_null() || path.is_null() {
        return false;
    }
    let c_str = unsafe { CStr::from_ptr(path) };
    if let Ok(path_str) = c_str.to_str() {
        let p = unsafe { &*painter };
        p.save_png(path_str).is_ok()
    } else {
        false
    }
}

#[no_mangle]
pub extern "C" fn emtk_create_quad_painter() -> *mut QuadPainter {
    let painter = Box::new(QuadPainter::new());
    Box::into_raw(painter)
}

#[no_mangle]
pub extern "C" fn emtk_destroy_quad_painter(painter: *mut QuadPainter) {
    if !painter.is_null() {
        unsafe { drop(Box::from_raw(painter)) };
    }
}

#[no_mangle]
pub extern "C" fn emtk_quad_painter_clear(painter: *mut QuadPainter) {
    if !painter.is_null() {
        let p = unsafe { &mut *painter };
        p.clear();
    }
}

#[no_mangle]
pub extern "C" fn emtk_quad_painter_vertex_count(painter: *mut QuadPainter) -> usize {
    if !painter.is_null() {
        let p = unsafe { &*painter };
        p.vertex_count()
    } else {
        0
    }
}

#[no_mangle]
pub extern "C" fn emtk_quad_painter_vertex_data(painter: *mut QuadPainter) -> *const f32 {
    if !painter.is_null() {
        let p = unsafe { &*painter };
        p.vertex_bytes().as_ptr() as *const f32
    } else {
        ptr::null()
    }
}

#[no_mangle]
pub extern "C" fn emtk_new_frame_with_quad_painter(
    painter: *mut QuadPainter,
    dt: f32,
    width: f32,
    height: f32,
) {
    let ctx_ptr = emtk_get_current_context();
    if !ctx_ptr.is_null() && !painter.is_null() {
        let ctx = unsafe { &mut *ctx_ptr };
        let p = unsafe { &mut *painter };
        ctx.new_frame_with_painter(p, dt, width, height);
    }
}

#[no_mangle]
pub extern "C" fn emtk_new_frame(dt: f32, width: f32, height: f32) {
    let ctx_ptr = emtk_get_current_context();
    if !ctx_ptr.is_null() {
        let ctx = unsafe { &mut *ctx_ptr };
        ctx.new_frame(dt, width, height);
    }
}

#[no_mangle]
pub extern "C" fn emtk_new_frame_with_software_painter(
    painter: *mut SoftwarePainter,
    dt: f32,
    width: f32,
    height: f32,
) {
    let ctx_ptr = emtk_get_current_context();
    if !ctx_ptr.is_null() && !painter.is_null() {
        let ctx = unsafe { &mut *ctx_ptr };
        let p = unsafe { &mut *painter };
        ctx.new_frame_with_painter(p, dt, width, height);
    }
}

#[no_mangle]
pub extern "C" fn emtk_end_frame() {
    let ctx_ptr = emtk_get_current_context();
    if !ctx_ptr.is_null() {
        let ctx = unsafe { &mut *ctx_ptr };
        ctx.end_frame();
    }
}

#[no_mangle]
pub extern "C" fn emtk_begin(name: *const c_char, p_open: *mut bool, flags: u32) -> bool {
    let ctx_ptr = emtk_get_current_context();
    if ctx_ptr.is_null() || name.is_null() {
        return false;
    }
    let c_str = unsafe { CStr::from_ptr(name) };
    let name_str = match c_str.to_str() {
        Ok(s) => s,
        Err(_) => return false,
    };
    let ctx = unsafe { &mut *ctx_ptr };
    let open_ref = if p_open.is_null() { None } else { Some(unsafe { &mut *p_open }) };
    ctx.begin_window(name_str, open_ref, flags)
}

#[no_mangle]
pub extern "C" fn emtk_end() {
    let ctx_ptr = emtk_get_current_context();
    if !ctx_ptr.is_null() {
        let ctx = unsafe { &mut *ctx_ptr };
        ctx.end_window();
    }
}

#[no_mangle]
pub extern "C" fn emtk_text(text: *const c_char) {
    let ctx_ptr = emtk_get_current_context();
    if ctx_ptr.is_null() || text.is_null() {
        return;
    }
    let c_str = unsafe { CStr::from_ptr(text) };
    if let Ok(s) = c_str.to_str() {
        let ctx = unsafe { &mut *ctx_ptr };
        ctx.text_unformatted(s);
    }
}

#[no_mangle]
pub extern "C" fn emtk_button(label: *const c_char, width: f32, height: f32) -> bool {
    let ctx_ptr = emtk_get_current_context();
    if ctx_ptr.is_null() || label.is_null() {
        return false;
    }
    let c_str = unsafe { CStr::from_ptr(label) };
    if let Ok(s) = c_str.to_str() {
        let ctx = unsafe { &mut *ctx_ptr };
        ctx.button_simple(s, Vec2::new(width, height))
    } else {
        false
    }
}

#[no_mangle]
pub extern "C" fn emtk_checkbox(label: *const c_char, v: *mut bool) -> bool {
    let ctx_ptr = emtk_get_current_context();
    if ctx_ptr.is_null() || label.is_null() || v.is_null() {
        return false;
    }
    let c_str = unsafe { CStr::from_ptr(label) };
    if let Ok(s) = c_str.to_str() {
        let ctx = unsafe { &mut *ctx_ptr };
        let val_ref = unsafe { &mut *v };
        ctx.checkbox_simple(s, val_ref)
    } else {
        false
    }
}

#[no_mangle]
pub extern "C" fn emtk_slider_float(
    label: *const c_char,
    v: *mut f32,
    v_min: f32,
    v_max: f32,
    format: *const c_char,
) -> bool {
    let ctx_ptr = emtk_get_current_context();
    if ctx_ptr.is_null() || label.is_null() || v.is_null() {
        return false;
    }
    let c_str = unsafe { CStr::from_ptr(label) };
    let fmt_str = if format.is_null() {
        "%.3f"
    } else {
        unsafe { CStr::from_ptr(format) }.to_str().unwrap_or("%.3f")
    };
    if let Ok(s) = c_str.to_str() {
        let ctx = unsafe { &mut *ctx_ptr };
        let val_ref = unsafe { &mut *v };
        ctx.slider_float_simple(s, val_ref, v_min, v_max, fmt_str)
    } else {
        false
    }
}

#[no_mangle]
pub extern "C" fn emtk_same_line(offset_from_start_x: f32, spacing: f32) {
    let ctx_ptr = emtk_get_current_context();
    if !ctx_ptr.is_null() {
        let ctx = unsafe { &mut *ctx_ptr };
        ctx.same_line(offset_from_start_x, spacing);
    }
}

#[no_mangle]
pub extern "C" fn emtk_separator() {
    let ctx_ptr = emtk_get_current_context();
    if !ctx_ptr.is_null() {
        let ctx = unsafe { &mut *ctx_ptr };
        ctx.separator_simple();
    }
}

// --- ImPlot Scientific Plotting C ABI ---

#[no_mangle]
pub extern "C" fn emtk_begin_plot(title: *const c_char, width: f32, height: f32, flags: u32) -> bool {
    let ctx_ptr = emtk_get_current_context();
    if ctx_ptr.is_null() || title.is_null() {
        return false;
    }
    let c_str = unsafe { CStr::from_ptr(title) };
    if let Ok(t) = c_str.to_str() {
        let ctx = unsafe { &mut *ctx_ptr };
        emtk_implot::begin_plot(ctx, t, Vec2::new(width, height), flags)
    } else {
        false
    }
}

#[no_mangle]
pub extern "C" fn emtk_end_plot() {
    let ctx_ptr = emtk_get_current_context();
    if !ctx_ptr.is_null() {
        let ctx = unsafe { &mut *ctx_ptr };
        emtk_implot::end_plot(ctx);
    }
}

#[no_mangle]
pub extern "C" fn emtk_setup_axes(x_label: *const c_char, y_label: *const c_char) {
    let x_str = if x_label.is_null() { "" } else { unsafe { CStr::from_ptr(x_label) }.to_str().unwrap_or("") };
    let y_str = if y_label.is_null() { "" } else { unsafe { CStr::from_ptr(y_label) }.to_str().unwrap_or("") };
    emtk_implot::setup_axes(x_str, y_str);
}

#[no_mangle]
pub extern "C" fn emtk_setup_axis_limits(axis: u32, min: f64, max: f64) {
    emtk_implot::setup_axis_limits(axis, min, max);
}

#[no_mangle]
pub extern "C" fn emtk_plot_line(label: *const c_char, xs: *const f64, ys: *const f64, count: usize) {
    if label.is_null() || xs.is_null() || ys.is_null() || count == 0 {
        return;
    }
    let c_str = unsafe { CStr::from_ptr(label) };
    if let Ok(lbl) = c_str.to_str() {
        let x_slice = unsafe { std::slice::from_raw_parts(xs, count) };
        let y_slice = unsafe { std::slice::from_raw_parts(ys, count) };
        emtk_implot::plot_line(lbl, x_slice, y_slice);
    }
}

#[no_mangle]
pub extern "C" fn emtk_plot_scatter(label: *const c_char, xs: *const f64, ys: *const f64, count: usize) {
    if label.is_null() || xs.is_null() || ys.is_null() || count == 0 {
        return;
    }
    let c_str = unsafe { CStr::from_ptr(label) };
    if let Ok(lbl) = c_str.to_str() {
        let x_slice = unsafe { std::slice::from_raw_parts(xs, count) };
        let y_slice = unsafe { std::slice::from_raw_parts(ys, count) };
        emtk_implot::plot_scatter(lbl, x_slice, y_slice);
    }
}

#[no_mangle]
pub extern "C" fn emtk_plot_bars(label: *const c_char, xs: *const f64, ys: *const f64, count: usize, width: f64) {
    if label.is_null() || xs.is_null() || ys.is_null() || count == 0 {
        return;
    }
    let c_str = unsafe { CStr::from_ptr(label) };
    if let Ok(lbl) = c_str.to_str() {
        let x_slice = unsafe { std::slice::from_raw_parts(xs, count) };
        let y_slice = unsafe { std::slice::from_raw_parts(ys, count) };
        emtk_implot::plot_bars(lbl, x_slice, y_slice, width);
    }
}

#[no_mangle]
pub extern "C" fn emtk_plot_heatmap(label: *const c_char, values: *const f64, rows: usize, cols: usize, min: f64, max: f64) {
    if label.is_null() || values.is_null() || rows == 0 || cols == 0 {
        return;
    }
    let c_str = unsafe { CStr::from_ptr(label) };
    if let Ok(lbl) = c_str.to_str() {
        let val_slice = unsafe { std::slice::from_raw_parts(values, rows * cols) };
        emtk_implot::plot_heatmap(lbl, val_slice, rows, cols, min, max);
    }
}

// --- Docking / DockBuilder C ABI ---

use emtk_core::docking::{DockSpace, SplitDir};

#[no_mangle]
pub extern "C" fn emtk_create_dockspace(id: u32) -> *mut DockSpace {
    Box::into_raw(Box::new(DockSpace::new(id)))
}

#[no_mangle]
pub extern "C" fn emtk_destroy_dockspace(ds: *mut DockSpace) {
    if !ds.is_null() {
        unsafe { drop(Box::from_raw(ds)) };
    }
}

#[no_mangle]
pub extern "C" fn emtk_dockspace_set_rect(ds: *mut DockSpace, x: f32, y: f32, w: f32, h: f32) {
    if !ds.is_null() {
        let d = unsafe { &mut *ds };
        d.set_rect(emtk_core::types::Rect::new(x, y, w, h));
    }
}

#[no_mangle]
pub extern "C" fn emtk_dock_builder_split_node(
    ds: *mut DockSpace,
    node_id: u32,
    dir: u32,
    ratio: f32,
    out_id_at_dir: *mut u32,
    out_id_at_opposite: *mut u32,
) {
    if ds.is_null() || out_id_at_dir.is_null() || out_id_at_opposite.is_null() {
        return;
    }
    let split_dir = match dir {
        0 => SplitDir::Left,
        1 => SplitDir::Right,
        2 => SplitDir::Up,
        _ => SplitDir::Down,
    };
    let d = unsafe { &mut *ds };
    let mut d_out = 0;
    let mut opp_out = 0;
    d.split_node(node_id, split_dir, ratio, &mut d_out, &mut opp_out);
    unsafe {
        *out_id_at_dir = d_out;
        *out_id_at_opposite = opp_out;
    }
}

#[no_mangle]
pub extern "C" fn emtk_dock_builder_dock_window(ds: *mut DockSpace, window_name: *const c_char, node_id: u32) {
    if ds.is_null() || window_name.is_null() {
        return;
    }
    let c_str = unsafe { CStr::from_ptr(window_name) };
    if let Ok(name) = c_str.to_str() {
        let d = unsafe { &mut *ds };
        d.dock_window(name, node_id);
    }
}

#[no_mangle]
pub extern "C" fn emtk_dockspace_is_window_active(ds: *mut DockSpace, window_name: *const c_char) -> bool {
    if ds.is_null() || window_name.is_null() {
        return true;
    }
    let c_str = unsafe { CStr::from_ptr(window_name) };
    if let Ok(name) = c_str.to_str() {
        let d = unsafe { &*ds };
        d.is_window_tab_active(name)
    } else {
        true
    }
}

// --- ImNodes C ABI ---

use emtk_imnodes::{EditorContext, PinShape};

thread_local! {
    static CURRENT_IMNODES_EDITOR: RefCell<*mut EditorContext> = RefCell::new(ptr::null_mut());
}

#[no_mangle]
pub extern "C" fn emtk_imnodes_create_context() -> *mut EditorContext {
    let editor = Box::new(EditorContext::new());
    let ptr = Box::into_raw(editor);
    CURRENT_IMNODES_EDITOR.with(|c| {
        if c.borrow().is_null() {
            *c.borrow_mut() = ptr;
        }
    });
    ptr
}

#[no_mangle]
pub extern "C" fn emtk_imnodes_destroy_context(editor: *mut EditorContext) {
    if !editor.is_null() {
        CURRENT_IMNODES_EDITOR.with(|c| {
            if *c.borrow() == editor {
                *c.borrow_mut() = ptr::null_mut();
            }
        });
        unsafe { drop(Box::from_raw(editor)) };
    }
}

#[no_mangle]
pub extern "C" fn emtk_imnodes_set_current_context(editor: *mut EditorContext) {
    CURRENT_IMNODES_EDITOR.with(|c| {
        *c.borrow_mut() = editor;
    });
}

#[no_mangle]
pub extern "C" fn emtk_imnodes_begin_node_editor(x: f32, y: f32, w: f32, h: f32) {
    CURRENT_IMNODES_EDITOR.with(|c| {
        let ptr = *c.borrow();
        if !ptr.is_null() {
            let editor = unsafe { &mut *ptr };
            emtk_imnodes::begin_node_editor(editor, emtk_core::types::Rect::new(x, y, w, h));
        }
    });
}

#[no_mangle]
pub extern "C" fn emtk_imnodes_end_node_editor() {
    let ctx_ptr = emtk_get_current_context();
    let editor_ptr = CURRENT_IMNODES_EDITOR.with(|c| *c.borrow());

    if !ctx_ptr.is_null() && !editor_ptr.is_null() {
        let ctx = unsafe { &mut *ctx_ptr };
        let editor = unsafe { &mut *editor_ptr };
        if let Some(painter_ptr) = ctx.active_painter {
            let painter = unsafe { &mut *painter_ptr };
            emtk_imnodes::end_node_editor(ctx, painter, editor);
        }
    }
}

#[no_mangle]
pub extern "C" fn emtk_imnodes_begin_node(id: i32) {
    CURRENT_IMNODES_EDITOR.with(|c| {
        let ptr = *c.borrow();
        if !ptr.is_null() {
            let editor = unsafe { &mut *ptr };
            emtk_imnodes::begin_node(editor, id);
        }
    });
}

#[no_mangle]
pub extern "C" fn emtk_imnodes_end_node() {
    CURRENT_IMNODES_EDITOR.with(|c| {
        let ptr = *c.borrow();
        if !ptr.is_null() {
            let editor = unsafe { &mut *ptr };
            emtk_imnodes::end_node(editor);
        }
    });
}

#[no_mangle]
pub extern "C" fn emtk_imnodes_begin_node_title_bar() {
    CURRENT_IMNODES_EDITOR.with(|c| {
        let ptr = *c.borrow();
        if !ptr.is_null() {
            let editor = unsafe { &mut *ptr };
            emtk_imnodes::begin_node_title_bar(editor);
        }
    });
}

#[no_mangle]
pub extern "C" fn emtk_imnodes_end_node_title_bar() {
    CURRENT_IMNODES_EDITOR.with(|c| {
        let ptr = *c.borrow();
        if !ptr.is_null() {
            let editor = unsafe { &mut *ptr };
            emtk_imnodes::end_node_title_bar(editor);
        }
    });
}

#[no_mangle]
pub extern "C" fn emtk_imnodes_begin_input_attribute(id: i32, _shape: i32) {
    CURRENT_IMNODES_EDITOR.with(|c| {
        let ptr = *c.borrow();
        if !ptr.is_null() {
            let editor = unsafe { &mut *ptr };
            emtk_imnodes::begin_input_attribute(editor, id, PinShape::Circle);
        }
    });
}

#[no_mangle]
pub extern "C" fn emtk_imnodes_end_input_attribute() {
    CURRENT_IMNODES_EDITOR.with(|c| {
        let ptr = *c.borrow();
        if !ptr.is_null() {
            let editor = unsafe { &mut *ptr };
            emtk_imnodes::end_input_attribute(editor);
        }
    });
}

#[no_mangle]
pub extern "C" fn emtk_imnodes_begin_output_attribute(id: i32, _shape: i32) {
    CURRENT_IMNODES_EDITOR.with(|c| {
        let ptr = *c.borrow();
        if !ptr.is_null() {
            let editor = unsafe { &mut *ptr };
            emtk_imnodes::begin_output_attribute(editor, id, PinShape::Circle);
        }
    });
}

#[no_mangle]
pub extern "C" fn emtk_imnodes_end_output_attribute() {
    CURRENT_IMNODES_EDITOR.with(|c| {
        let ptr = *c.borrow();
        if !ptr.is_null() {
            let editor = unsafe { &mut *ptr };
            emtk_imnodes::end_output_attribute(editor);
        }
    });
}

#[no_mangle]
pub extern "C" fn emtk_imnodes_link(id: i32, start_pin_id: i32, end_pin_id: i32) {
    CURRENT_IMNODES_EDITOR.with(|c| {
        let ptr = *c.borrow();
        if !ptr.is_null() {
            let editor = unsafe { &mut *ptr };
            emtk_imnodes::link(editor, id, start_pin_id, end_pin_id);
        }
    });
}

#[no_mangle]
pub extern "C" fn emtk_imnodes_is_link_created(out_start_pin: *mut i32, out_end_pin: *mut i32) -> bool {
    let mut created = false;
    CURRENT_IMNODES_EDITOR.with(|c| {
        let ptr = *c.borrow();
        if !ptr.is_null() {
            let editor = unsafe { &*ptr };
            if let Some((start, end)) = editor.is_link_created() {
                if !out_start_pin.is_null() { unsafe { *out_start_pin = start; } }
                if !out_end_pin.is_null() { unsafe { *out_end_pin = end; } }
                created = true;
            }
        }
    });
    created
}

#[no_mangle]
pub extern "C" fn emtk_imnodes_set_node_grid_pos(id: i32, x: f32, y: f32) {
    CURRENT_IMNODES_EDITOR.with(|c| {
        let ptr = *c.borrow();
        if !ptr.is_null() {
            let editor = unsafe { &mut *ptr };
            editor.set_node_grid_space_pos(id, Vec2::new(x, y));
        }
    });
}

#[no_mangle]
pub extern "C" fn emtk_imnodes_get_node_grid_pos(id: i32, out_x: *mut f32, out_y: *mut f32) {
    CURRENT_IMNODES_EDITOR.with(|c| {
        let ptr = *c.borrow();
        if !ptr.is_null() {
            let editor = unsafe { &*ptr };
            let pos = editor.get_node_grid_space_pos(id);
            if !out_x.is_null() { unsafe { *out_x = pos.x; } }
            if !out_y.is_null() { unsafe { *out_y = pos.y; } }
        }
    });
}
