/*
 * EMTK (Embeddable Immediate-Mode Toolkit) Modern C++ Header
 * MIT Licensed - Copyright (c) Thomas-Otavio Peulen
 */

#pragma once

#include "emtk.h"
#include <string>
#include <string_view>
#include <memory>

namespace emtk {

class Context {
public:
    inline Context() : ctx_(emtk_create_context()) {}
    inline ~Context() {
        if (ctx_) {
            emtk_destroy_context(ctx_);
        }
    }

    inline void SetCurrent() {
        emtk_set_current_context(ctx_);
    }

    inline EmtkContext* raw() const { return ctx_; }

    Context(const Context&) = delete;
    Context& operator=(const Context&) = delete;
    Context(Context&& other) noexcept : ctx_(other.ctx_) { other.ctx_ = nullptr; }
    Context& operator=(Context&& other) noexcept {
        if (this != &other) {
            if (ctx_) emtk_destroy_context(ctx_);
            ctx_ = other.ctx_;
            other.ctx_ = nullptr;
        }
        return *this;
    }

private:
    EmtkContext* ctx_{nullptr};
};

class SoftwarePainter {
public:
    inline SoftwarePainter(uint32_t width, uint32_t height, uint8_t r = 0, uint8_t g = 0, uint8_t b = 0, uint8_t a = 255)
        : painter_(emtk_create_software_painter(width, height, r, g, b, a)) {}

    inline ~SoftwarePainter() {
        if (painter_) {
            emtk_destroy_software_painter(painter_);
        }
    }

    inline bool SavePNG(const std::string& path) {
        return emtk_software_painter_save_png(painter_, path.c_str());
    }

    inline EmtkSoftwarePainter* raw() const { return painter_; }

    SoftwarePainter(const SoftwarePainter&) = delete;
    SoftwarePainter& operator=(const SoftwarePainter&) = delete;
    SoftwarePainter(SoftwarePainter&& other) noexcept : painter_(other.painter_) { other.painter_ = nullptr; }
    SoftwarePainter& operator=(SoftwarePainter&& other) noexcept {
        if (this != &other) {
            if (painter_) emtk_destroy_software_painter(painter_);
            painter_ = other.painter_;
            other.painter_ = nullptr;
        }
        return *this;
    }

private:
    EmtkSoftwarePainter* painter_{nullptr};
};

class QuadPainter {
public:
    inline QuadPainter() : painter_(emtk_create_quad_painter()) {}
    inline ~QuadPainter() {
        if (painter_) {
            emtk_destroy_quad_painter(painter_);
        }
    }

    inline void Clear() { emtk_quad_painter_clear(painter_); }
    inline size_t VertexCount() const { return emtk_quad_painter_vertex_count(painter_); }
    inline const float* VertexData() const { return emtk_quad_painter_vertex_data(painter_); }
    inline EmtkQuadPainter* raw() const { return painter_; }

    QuadPainter(const QuadPainter&) = delete;
    QuadPainter& operator=(const QuadPainter&) = delete;
    QuadPainter(QuadPainter&& other) noexcept : painter_(other.painter_) { other.painter_ = nullptr; }
    QuadPainter& operator=(QuadPainter&& other) noexcept {
        if (this != &other) {
            if (painter_) emtk_destroy_quad_painter(painter_);
            painter_ = other.painter_;
            other.painter_ = nullptr;
        }
        return *this;
    }

private:
    EmtkQuadPainter* painter_{nullptr};
};

class Frame {
public:
    inline Frame(SoftwarePainter& painter, float width, float height, float dt = 1.0f / 60.0f) {
        emtk_new_frame_with_software_painter(painter.raw(), dt, width, height);
    }
    inline Frame(QuadPainter& painter, float width, float height, float dt = 1.0f / 60.0f) {
        emtk_new_frame_with_quad_painter(painter.raw(), dt, width, height);
    }
    inline Frame(float width, float height, float dt = 1.0f / 60.0f) {
        emtk_new_frame(dt, width, height);
    }
    inline ~Frame() {
        emtk_end_frame();
    }

    Frame(const Frame&) = delete;
    Frame& operator=(const Frame&) = delete;
};

// --- Immediate-Mode Operations (Dear ImGui Compatible) ---

inline bool Begin(const char* name, bool* p_open = nullptr, uint32_t flags = 0) {
    return emtk_begin(name, p_open, flags);
}

inline bool Begin(std::string_view name, bool* p_open = nullptr, uint32_t flags = 0) {
    return emtk_begin(name.data(), p_open, flags);
}

inline void End() {
    emtk_end();
}

inline void Text(const char* text) {
    emtk_text(text);
}

inline void Text(std::string_view text) {
    emtk_text(text.data());
}

inline bool Button(const char* label, float width = 0.0f, float height = 0.0f) {
    return emtk_button(label, width, height);
}

inline bool Button(std::string_view label, float width = 0.0f, float height = 0.0f) {
    return emtk_button(label.data(), width, height);
}

inline bool Checkbox(const char* label, bool* v) {
    return emtk_checkbox(label, v);
}

inline bool Checkbox(std::string_view label, bool* v) {
    return emtk_checkbox(label.data(), v);
}

inline bool SliderFloat(const char* label, float* v, float v_min, float v_max, const char* format = "%.3f") {
    return emtk_slider_float(label, v, v_min, v_max, format);
}

inline bool SliderFloat(std::string_view label, float* v, float v_min, float v_max, const char* format = "%.3f") {
    return emtk_slider_float(label.data(), v, v_min, v_max, format);
}

inline void SameLine(float offset_from_start_x = 0.0f, float spacing = -1.0f) {
    emtk_same_line(offset_from_start_x, spacing);
}

inline void Separator() {
    emtk_separator();
}

namespace plot {

inline bool BeginPlot(const char* title, float width = 0.0f, float height = 0.0f, uint32_t flags = 0) {
    return emtk_begin_plot(title, width, height, flags);
}

inline bool BeginPlot(std::string_view title, float width = 0.0f, float height = 0.0f, uint32_t flags = 0) {
    return emtk_begin_plot(title.data(), width, height, flags);
}

inline void EndPlot() {
    emtk_end_plot();
}

inline void SetupAxes(const char* x_label, const char* y_label) {
    emtk_setup_axes(x_label, y_label);
}

inline void SetupAxes(std::string_view x_label, std::string_view y_label) {
    emtk_setup_axes(x_label.data(), y_label.data());
}

inline void SetupAxisLimits(uint32_t axis, double min, double max) {
    emtk_setup_axis_limits(axis, min, max);
}

inline void PlotLine(const char* label, const double* xs, const double* ys, size_t count) {
    emtk_plot_line(label, xs, ys, count);
}

inline void PlotLine(std::string_view label, const double* xs, const double* ys, size_t count) {
    emtk_plot_line(label.data(), xs, ys, count);
}

template <typename Container>
inline void PlotLine(std::string_view label, const Container& xs, const Container& ys) {
    emtk_plot_line(label.data(), xs.data(), ys.data(), std::min(xs.size(), ys.size()));
}

inline void PlotScatter(const char* label, const double* xs, const double* ys, size_t count) {
    emtk_plot_scatter(label, xs, ys, count);
}

inline void PlotScatter(std::string_view label, const double* xs, const double* ys, size_t count) {
    emtk_plot_scatter(label.data(), xs, ys, count);
}

template <typename Container>
inline void PlotScatter(std::string_view label, const Container& xs, const Container& ys) {
    emtk_plot_scatter(label.data(), xs.data(), ys.data(), std::min(xs.size(), ys.size()));
}

inline void PlotBars(const char* label, const double* xs, const double* ys, size_t count, double width = 0.67) {
    emtk_plot_bars(label, xs, ys, count, width);
}

template <typename Container>
inline void PlotBars(std::string_view label, const Container& xs, const Container& ys, double width = 0.67) {
    emtk_plot_bars(label.data(), xs.data(), ys.data(), std::min(xs.size(), ys.size()), width);
}

inline void PlotHeatmap(const char* label, const double* values, size_t rows, size_t cols, double min, double max) {
    emtk_plot_heatmap(label, values, rows, cols, min, max);
}

} // namespace plot

namespace dock {

enum class SplitDir : uint32_t {
    Left = 0,
    Right = 1,
    Up = 2,
    Down = 3,
};

class DockSpace {
public:
    explicit DockSpace(uint32_t id) : m_handle(emtk_create_dockspace(id)) {}
    ~DockSpace() {
        if (m_handle) emtk_destroy_dockspace(m_handle);
    }
    DockSpace(const DockSpace&) = delete;
    DockSpace& operator=(const DockSpace&) = delete;
    DockSpace(DockSpace&& other) noexcept : m_handle(other.m_handle) { other.m_handle = nullptr; }

    void SetRect(float x, float y, float w, float h) {
        emtk_dockspace_set_rect(m_handle, x, y, w, h);
    }

    void SplitNode(uint32_t node_id, SplitDir dir, float ratio, uint32_t* out_dir, uint32_t* out_opp) {
        emtk_dock_builder_split_node(m_handle, node_id, static_cast<uint32_t>(dir), ratio, out_dir, out_opp);
    }

    void DockWindow(std::string_view name, uint32_t node_id) {
        emtk_dock_builder_dock_window(m_handle, name.data(), node_id);
    }

    bool IsWindowActive(std::string_view name) const {
        return emtk_dockspace_is_window_active(m_handle, name.data());
    }

    emtk_dockspace_t* Raw() const { return m_handle; }

private:
    emtk_dockspace_t* m_handle{nullptr};
};

} // namespace dock

namespace nodes {

class EditorContext {
public:
    EditorContext() : m_handle(emtk_imnodes_create_context()) {}
    ~EditorContext() {
        if (m_handle) emtk_imnodes_destroy_context(m_handle);
    }
    EditorContext(const EditorContext&) = delete;
    EditorContext& operator=(const EditorContext&) = delete;
    EditorContext(EditorContext&& other) noexcept : m_handle(other.m_handle) { other.m_handle = nullptr; }

    void SetCurrent() {
        emtk_imnodes_set_current_context(m_handle);
    }

    emtk_imnodes_context_t* Raw() const { return m_handle; }

private:
    emtk_imnodes_context_t* m_handle{nullptr};
};

inline void BeginNodeEditor(float x, float y, float w, float h) {
    emtk_imnodes_begin_node_editor(x, y, w, h);
}

inline void EndNodeEditor() {
    emtk_imnodes_end_node_editor();
}

inline void BeginNode(int32_t id) {
    emtk_imnodes_begin_node(id);
}

inline void EndNode() {
    emtk_imnodes_end_node();
}

inline void BeginNodeTitleBar() {
    emtk_imnodes_begin_node_title_bar();
}

inline void EndNodeTitleBar() {
    emtk_imnodes_end_node_title_bar();
}

inline void BeginInputAttribute(int32_t id, int32_t shape = 0) {
    emtk_imnodes_begin_input_attribute(id, shape);
}

inline void EndInputAttribute() {
    emtk_imnodes_end_input_attribute();
}

inline void BeginOutputAttribute(int32_t id, int32_t shape = 0) {
    emtk_imnodes_begin_output_attribute(id, shape);
}

inline void EndOutputAttribute() {
    emtk_imnodes_end_output_attribute();
}

inline void Link(int32_t id, int32_t start_pin_id, int32_t end_pin_id) {
    emtk_imnodes_link(id, start_pin_id, end_pin_id);
}

inline bool IsLinkCreated(int32_t* out_start_pin, int32_t* out_end_pin) {
    return emtk_imnodes_is_link_created(out_start_pin, out_end_pin);
}

inline void SetNodeGridSpacePos(int32_t id, float x, float y) {
    emtk_imnodes_set_node_grid_pos(id, x, y);
}

inline void GetNodeGridSpacePos(int32_t id, float* out_x, float* out_y) {
    emtk_imnodes_get_node_grid_pos(id, out_x, out_y);
}

} // namespace nodes

} // namespace emtk
