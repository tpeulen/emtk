/*
 * EMTK (Embeddable Immediate-Mode Toolkit) C99 Interface
 * MIT Licensed - Copyright (c) Thomas-Otavio Peulen
 */

#ifndef EMTK_H
#define EMTK_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct EmtkContext EmtkContext;
typedef struct EmtkSoftwarePainter EmtkSoftwarePainter;
typedef struct EmtkQuadPainter EmtkQuadPainter;

/* Version */
const char* emtk_version(void);

/* Context Management */
EmtkContext* emtk_create_context(void);
void emtk_destroy_context(EmtkContext* ctx);
void emtk_set_current_context(EmtkContext* ctx);
EmtkContext* emtk_get_current_context(void);

/* Headless Software Painter (CPU Rasterizer) */
EmtkSoftwarePainter* emtk_create_software_painter(uint32_t width, uint32_t height, uint8_t r, uint8_t g, uint8_t b, uint8_t a);
void emtk_destroy_software_painter(EmtkSoftwarePainter* painter);
bool emtk_software_painter_save_png(EmtkSoftwarePainter* painter, const char* path);

/* Quad Painter (GPU Quad Emitter for WebGPU / ui.wgsl) */
EmtkQuadPainter* emtk_create_quad_painter(void);
void emtk_destroy_quad_painter(EmtkQuadPainter* painter);
void emtk_quad_painter_clear(EmtkQuadPainter* painter);
size_t emtk_quad_painter_vertex_count(EmtkQuadPainter* painter);
const float* emtk_quad_painter_vertex_data(EmtkQuadPainter* painter);
void emtk_new_frame_with_quad_painter(EmtkQuadPainter* painter, float dt, float width, float height);

/* Frame Lifecycle */
void emtk_new_frame(float dt, float width, float height);
void emtk_new_frame_with_software_painter(EmtkSoftwarePainter* painter, float dt, float width, float height);
void emtk_end_frame(void);

/* Windowing */
bool emtk_begin(const char* name, bool* p_open, uint32_t flags);
void emtk_end(void);

/* Core Widgets */
void emtk_text(const char* text);
bool emtk_button(const char* label, float width, float height);
bool emtk_checkbox(const char* label, bool* v);
bool emtk_slider_float(const char* label, float* v, float v_min, float v_max, const char* format);
void emtk_same_line(float offset_from_start_x, float spacing);
void emtk_separator(void);

/* ImPlot 2D Scientific Plotting */
bool emtk_begin_plot(const char* title, float width, float height, uint32_t flags);
void emtk_end_plot(void);
void emtk_setup_axes(const char* x_label, const char* y_label);
void emtk_setup_axis_limits(uint32_t axis, double min, double max);
void emtk_plot_line(const char* label, const double* xs, const double* ys, size_t count);
void emtk_plot_scatter(const char* label, const double* xs, const double* ys, size_t count);
void emtk_plot_bars(const char* label, const double* xs, const double* ys, size_t count, double width);
void emtk_plot_heatmap(const char* label, const double* values, size_t rows, size_t cols, double min, double max);

/* Docking / DockBuilder */
typedef struct emtk_dockspace emtk_dockspace_t;

emtk_dockspace_t* emtk_create_dockspace(uint32_t id);
void emtk_destroy_dockspace(emtk_dockspace_t* ds);
void emtk_dockspace_set_rect(emtk_dockspace_t* ds, float x, float y, float w, float h);
void emtk_dock_builder_split_node(emtk_dockspace_t* ds, uint32_t node_id, uint32_t dir, float ratio, uint32_t* out_id_at_dir, uint32_t* out_id_at_opposite);
void emtk_dock_builder_dock_window(emtk_dockspace_t* ds, const char* window_name, uint32_t node_id);
bool emtk_dockspace_is_window_active(emtk_dockspace_t* ds, const char* window_name);

/* ImNodes Immediate-Mode Node Graph Editor */
typedef struct emtk_imnodes_context emtk_imnodes_context_t;

emtk_imnodes_context_t* emtk_imnodes_create_context(void);
void emtk_imnodes_destroy_context(emtk_imnodes_context_t* editor);
void emtk_imnodes_set_current_context(emtk_imnodes_context_t* editor);
void emtk_imnodes_begin_node_editor(float x, float y, float w, float h);
void emtk_imnodes_end_node_editor(void);
void emtk_imnodes_begin_node(int32_t id);
void emtk_imnodes_end_node(void);
void emtk_imnodes_begin_node_title_bar(void);
void emtk_imnodes_end_node_title_bar(void);
void emtk_imnodes_begin_input_attribute(int32_t id, int32_t shape);
void emtk_imnodes_end_input_attribute(void);
void emtk_imnodes_begin_output_attribute(int32_t id, int32_t shape);
void emtk_imnodes_end_output_attribute(void);
void emtk_imnodes_link(int32_t id, int32_t start_pin_id, int32_t end_pin_id);
bool emtk_imnodes_is_link_created(int32_t* out_start_pin, int32_t* out_end_pin);
void emtk_imnodes_set_node_grid_pos(int32_t id, float x, float y);
void emtk_imnodes_get_node_grid_pos(int32_t id, float* out_x, float* out_y);

#ifdef __cplusplus
}
#endif

#endif /* EMTK_H */
