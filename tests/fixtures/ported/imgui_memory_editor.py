"""imgui_memory_editor: auto-ported from imgui_memory_editor.h
(upstream, MIT) by tools/autoport.py.

A mechanical port of Dear ImGui C++ to emtk. Lines flagged
TODO(autoport) need a hand; everything else is the C++ under the
naming rules in tools/autoport.py.
"""
import math

import emtk.im as im

_PRISizeT = "I"

class MemoryEditor:
    """MemoryEditor, from imgui_memory_editor.h."""

    def __init__(self):
        """MemoryEditor()."""
        self.Open = None
        self.ReadOnly = None
        self.Cols = None
        self.OptShowOptions = None
        self.OptShowDataPreview = None
        self.OptShowHexII = None
        self.OptShowAscii = None
        self.OptGreyOutZeroes = None
        self.OptUpperCaseHex = None
        self.OptMidColsCount = None
        self.OptAddrDigitsCount = None
        self.OptFooterExtraHeight = None
        self.HighlightColor = None
        self.MouseHovered = None
        self.MouseHoveredAddr = None
        self.ContentsWidthChanged = None
        self.DataPreviewAddr = None
        self.DataEditingAddr = None
        self.DataEditingTakeFocus = None
        self.GotoAddr = None
        self.PreviewEndianness = None
        self.PreviewDataType = None
        self.open = True
        self.read_only = False
        self.cols = 16
        self.opt_show_options = True
        self.opt_show_data_preview = False
        self.opt_show_hex_ii = False
        self.opt_show_ascii = True
        self.opt_grey_out_zeroes = True
        self.opt_upper_case_hex = True
        self.opt_mid_cols_count = 8
        self.opt_addr_digits_count = 0
        self.opt_footer_extra_height = 0.0
        self.highlight_color = im.col32(255, 255, 255, 50)
        ReadFn = None
        WriteFn = None
        HighlightFn = None
        BgColorFn = None
        UserData = None
        self.contents_width_changed = False
        self.data_preview_addr = self.data_editing_addr = (size_t)-1
        self.data_editing_take_focus = False
        memset(DataInputBuf, 0, sizeof(DataInputBuf))
        memset(AddrInputBuf, 0, sizeof(AddrInputBuf))
        self.goto_addr = (size_t)-1
        self.mouse_hovered = False
        self.mouse_hovered_addr = 0
        HighlightMin = HighlightMax = (size_t)-1
        self.preview_endianness = 0
        self.preview_data_type = im.DataType.S32

    def goto_addr_and_highlight(self, addr_min, addr_max):
        """GotoAddrAndHighlight()."""
        self.goto_addr = addr_min
        HighlightMin = addr_min
        HighlightMax = addr_max

    def calc_sizes(self, s, mem_size, base_display_addr):
        """CalcSizes()."""
        style = im.get_style()
        s.addr_digits_count = self.opt_addr_digits_count
        if s.addr_digits_count == 0:
            for _ in range(0):  # TODO(autoport): for(n = base_display_addr + mem_size - 1; n > 0; n >>= 4):
# TODO(autoport): hand-translate (the rules mangled this line):                 s.addr_digits_count++
                pass  # TODO(autoport): body of the line above
        s.line_height = im.get_text_line_height()
        s.glyph_width = im.calc_text_size("F")[0] + 1
        s.hex_cell_width = floatint(s.glyph_width * 2.5)
        s.spacing_between_mid_cols = floatint(s.hex_cell_width * 0.25)
        s.offset_hex_min_x = (s.addr_digits_count + 2) * s.glyph_width
        s.offset_hex_max_x = s.offset_hex_min_x + (s.hex_cell_width * self.cols)
        s.offset_ascii_min_x = s.offset_ascii_max_x = s.offset_hex_max_x
        if self.opt_show_ascii:
            s.offset_ascii_min_x = s.offset_hex_max_x + s.glyph_width * 1
            if self.opt_mid_cols_count > 0:
                s.offset_ascii_min_x = s.offset_ascii_min_x + float((self.cols + self.opt_mid_cols_count - 1) / self.opt_mid_cols_count) * s.spacing_between_mid_cols
            s.offset_ascii_max_x = s.offset_ascii_min_x + self.cols * s.glyph_width
        s.window_width = s.offset_ascii_max_x + style.scrollbar_size + style.window_padding[0] * 2 + s.glyph_width

    def draw_window(self, title, mem_data, mem_size, base_display_addr=0x0000):
        """DrawWindow()."""
        s = None  # TODO(autoport): Sizes -- construct this state
        calc_sizes(s, mem_size, base_display_addr)
        im.set_next_window_size((s.window_width, s.window_width * 0.60), im.Cond.FIRST_USE_EVER)
        im.set_next_window_size_constraints((0.0, 0.0), (s.window_width, FLT_MAX))
        self.open = True
        if im.begin(title, self.open, im.WindowFlags.NO_SCROLLBAR):
            draw_contents(mem_data, mem_size, base_display_addr)
            if self.contents_width_changed:
                calc_sizes(s, mem_size, base_display_addr)
                im.set_window_size((s.window_width, im.get_window_size()[1]))
        im.end()

    def draw_contents(self, mem_data_void, mem_size, base_display_addr=0x0000):
        """DrawContents()."""
        if self.cols < 1:
            self.cols = 1
# TODO(autoport): hand-translate (the rules mangled this line):         ImU8* mem_data = (ImU8*)mem_data_void
        pass  # TODO(autoport): body of the line above
        s = None  # TODO(autoport): Sizes -- construct this state
        calc_sizes(s, mem_size, base_display_addr)
        style = im.get_style()
        contents_pos_start = im.get_cursor_screen_pos()
        height_separator = style.item_spacing[1]
        footer_height = self.opt_footer_extra_height
        if self.opt_show_options:
            footer_height = footer_height + height_separator + im.get_frame_height_with_spacing() * 1
        if self.opt_show_data_preview:
            footer_height = footer_height + height_separator + im.get_frame_height_with_spacing() * 1 + im.get_text_line_height_with_spacing() * 3
        im.begin_child("##scrolling", (-FLT_MIN, -footer_height), im.ChildFlags.NONE, im.WindowFlags.NO_MOVE | im.WindowFlags.NO_NAV)
        draw_list = im.get_window_draw_list()
        im.push_style_var(im.StyleVar.FRAME_PADDING, (0, 0))
        im.push_style_var(im.StyleVar.ITEM_SPACING, (0, 0))
        avail_size = im.get_content_region_avail()
        line_total_count = int((mem_size + self.cols - 1) / self.cols)
        clipper = None  # TODO(autoport): ImGuiListClipper -- construct this state
        clipper.begin(line_total_count, s.line_height)
        data_next = False
        if self.data_editing_addr >= mem_size:
            self.data_editing_addr = (size_t)-1
        if self.data_preview_addr >= mem_size:
            self.data_preview_addr = (size_t)-1
        preview_data_type_size = (data_type_get_size(self.preview_data_type) if self.opt_show_data_preview else 0)
        data_editing_addr_next = (size_t)-1
        if self.data_editing_addr != (size_t)-1:
# TODO(autoport): hand-translate (the rules mangled this line):             if im.is_key_pressed(im.Key.UP_ARROW)  and  (ptrdiff_t)self.data_editing_addr >= (ptrdiff_t)self.cols:
            pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 data_editing_addr_next = self.data_editing_addr - self.cols
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            elif im.is_key_pressed(im.Key.DOWN_ARROW)  and  (ptrdiff_t)self.data_editing_addr < (ptrdiff_t)mem_size - self.cols:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                data_editing_addr_next = self.data_editing_addr + self.cols
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            elif im.is_key_pressed(im.Key.LEFT_ARROW)  and  (ptrdiff_t)self.data_editing_addr > (ptrdiff_t)0:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                data_editing_addr_next = self.data_editing_addr - 1
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            elif im.is_key_pressed(im.Key.RIGHT_ARROW)  and  (ptrdiff_t)self.data_editing_addr < (ptrdiff_t)mem_size - 1:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                data_editing_addr_next = self.data_editing_addr + 1
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        window_pos = im.get_window_pos()
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        if self.opt_show_ascii:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            draw_list.add_line((window_pos[0] + s.offset_ascii_min_x - s.glyph_width, window_pos[1]), (window_pos[0] + s.offset_ascii_min_x - s.glyph_width, window_pos[1] + 9999), im.get_color_u32(im.Col.BORDER))
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        color_text = im.get_color_u32(im.Col.TEXT)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        color_disabled = (im.get_color_u32(im.Col.TEXT_DISABLED) if self.opt_grey_out_zeroes else color_text)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        format_address = ("%0*" + _PRISizeT + "X: " if self.opt_upper_case_hex else "%0*" + _PRISizeT + "x: ")
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        format_data = ("%0*" + _PRISizeT + "X" if self.opt_upper_case_hex else "%0*" + _PRISizeT + "x")
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        format_byte = ("%02X" if self.opt_upper_case_hex else "%02x")
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        format_byte_space = ("%02X " if self.opt_upper_case_hex else "%02x ")
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        self.mouse_hovered = False
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        self.mouse_hovered_addr = 0
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        while clipper.step():
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            for line_i in range(int(clipper.display_start), int(clipper.display_end)):
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        addr = (size_t)line_i * self.cols
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        im.text(format_address, s.addr_digits_count, base_display_addr + addr)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        for _ in range(0):  # TODO(autoport): for(n = 0; n < Cols && addr < mem_size; n++, addr++):
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            byte_pos_x = s.offset_hex_min_x + s.hex_cell_width * n
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            if self.opt_mid_cols_count > 0:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                byte_pos_x = byte_pos_x + float(n / self.opt_mid_cols_count) * s.spacing_between_mid_cols
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            im.same_line(byte_pos_x)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            is_highlight_from_user_range = (addr >= HighlightMin  and  addr < HighlightMax)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            is_highlight_from_user_func = (HighlightFn  and  highlight_fn(mem_data, addr, UserData))
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            is_highlight_from_preview = (addr >= self.data_preview_addr  and  addr < self.data_preview_addr + preview_data_type_size)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            bg_color = 0
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            is_next_byte_highlighted = False
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            if is_highlight_from_user_range  or  is_highlight_from_user_func  or  is_highlight_from_preview:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                is_next_byte_highlighted = (addr + 1 < mem_size)  and  ((HighlightMax != (size_t)-1  and  addr + 1 < HighlightMax)  or  (HighlightFn  and  highlight_fn(mem_data, addr + 1, UserData))  or  (addr + 1 < self.data_preview_addr + preview_data_type_size))
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                bg_color = self.highlight_color
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            elif BgColorFn != None:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                is_next_byte_highlighted = (addr + 1 < mem_size)  and  ((bg_color_fn(mem_data, addr + 1, UserData) & IM_COL32_A_MASK) != 0)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                bg_color = bg_color_fn(mem_data, addr, UserData)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            if bg_color != 0:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                bg_width = s.glyph_width * 2
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                if is_next_byte_highlighted  or  (n + 1 == self.cols):
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                    bg_width = s.hex_cell_width
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                    if self.opt_mid_cols_count > 0  and  n > 0  and  (n + 1) < self.cols  and  ((n + 1) % self.opt_mid_cols_count) == 0:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                        bg_width = bg_width + s.spacing_between_mid_cols
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                pos = im.get_cursor_screen_pos()
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                draw_list.add_rect_filled(pos, (pos[0] + bg_width, pos[1] + s.line_height), bg_color)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            if self.data_editing_addr == addr:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                data_write = False
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                im.push_id((void*)addr)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                if self.data_editing_take_focus:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                    im.set_keyboard_focus_here(0)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                    im_snprintf(AddrInputBuf, 32, format_data, s.addr_digits_count, base_display_addr + addr)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                    im_snprintf(DataInputBuf, 32, format_byte, (read_fn(mem_data, addr, UserData) if ReadFn else mem_data[addr]))
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                struct InputTextUserData { static int callback(ImGuiInputTextCallbackData* data) { InputTextUserData* user_data = (InputTextUserData*)data.user_data; if (not data.has_selection()) user_data.cursor_pos = data.cursor_pos; if (data.flags & im.InputTextFlags.READ_ONLY) return 0; if (data.selection_start == 0  and  data.selection_end == data.buf_text_len) ( data.delete_chars(0, data.buf_text_len); data.insert_chars(0, user_data.current_buf_overwrite); data.selection_start = 0; data.selection_end = 2; data.cursor_pos = 0; ) return 0; } char   CurrentBufOverwrite[3]; int    CursorPos; }
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                input_text_user_data = None  # TODO(autoport): InputTextUserData -- construct this state
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                input_text_user_data.cursor_pos = -1
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                im_snprintf(input_text_user_data.current_buf_overwrite, 3, format_byte, (read_fn(mem_data, addr, UserData) if ReadFn else mem_data[addr]))
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                flags = im.InputTextFlags.CHARS_HEXADECIMAL | im.InputTextFlags.ENTER_RETURNS_TRUE | im.InputTextFlags.AUTO_SELECT_ALL | im.InputTextFlags.NO_HORIZONTAL_SCROLL | im.InputTextFlags.CALLBACK_ALWAYS
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                if self.read_only:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                    flags = flags | im.InputTextFlags.READ_ONLY
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                flags = flags | im.InputTextFlags.ALWAYS_OVERWRITE
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                im.set_next_item_width(s.glyph_width * 2)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                if _changed, DataInputBuf = im.input_text("##data", DataInputBuf, len(DataInputBuf), flags, InputTextUserData.callback, input_text_user_data):
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                    data_write = data_next = True
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                elif not self.data_editing_take_focus  and  not im.is_item_active():
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                    self.data_editing_addr = data_editing_addr_next = (size_t)-1
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                self.data_editing_take_focus = False
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                if input_text_user_data.cursor_pos >= 2:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                    data_write = data_next = True
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                if data_editing_addr_next != (size_t)-1:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                    data_write = data_next = False
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                data_input_value = 0
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                if not self.read_only  and  data_write  and  sscanf(DataInputBuf, "%X", data_input_value) == 1:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                    if WriteFn:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                        write_fn(mem_data, addr, (ImU8)data_input_value, UserData)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                    else:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                if im.is_item_hovered():
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                    self.mouse_hovered = True
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                    self.mouse_hovered_addr = addr
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                im.pop_id()
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            else:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                (read_fn(mem_data, addr, UserData) if ImU8 b = ReadFn else mem_data[addr])
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                if self.opt_show_hex_ii:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                    if (b >= 32  and  b < 128):
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                        im.text(".%c " % b)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                    elif b == 0xFF  and  self.opt_grey_out_zeroes:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                        im.text_disabled("## ")
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                    elif b == 0x00:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                        im.text("   ")
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                    else:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                else:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                    if b == 0  and  self.opt_grey_out_zeroes:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                        im.text_disabled("00 ")
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                    else:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                if im.is_item_hovered():
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                    self.mouse_hovered = True
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                    self.mouse_hovered_addr = addr
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                    if im.is_mouse_clicked(0):
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                        self.data_editing_take_focus = True
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                        data_editing_addr_next = addr
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        if self.opt_show_ascii:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            im.same_line(s.offset_ascii_min_x)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            pos = im.get_cursor_screen_pos()
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            addr = (size_t)line_i * self.cols
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            mouse_off_x = im.get_io().mouse_pos[0] - pos[0]
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            mouse_addr = (addr + (size_t)(mouse_off_x / s.glyph_width) if (mouse_off_x >= 0.0  and  mouse_off_x < s.offset_ascii_max_x - s.offset_ascii_min_x) else (size_t)-1)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            im.push_id(line_i)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            if im.invisible_button("ascii", (s.offset_ascii_max_x - s.offset_ascii_min_x, s.line_height)):
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                self.data_editing_addr = self.data_preview_addr = mouse_addr
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                self.data_editing_take_focus = True
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            if im.is_item_hovered():
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                self.mouse_hovered = True
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                self.mouse_hovered_addr = mouse_addr
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            im.pop_id()
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            for _ in range(0):  # TODO(autoport): for(n = 0; n < Cols && addr < mem_size; n++, addr++):
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                if addr == self.data_editing_addr:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                    draw_list.add_rect_filled(pos, (pos[0] + s.glyph_width, pos[1] + s.line_height), im.get_color_u32(im.Col.FRAME_BG))
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                    draw_list.add_rect_filled(pos, (pos[0] + s.glyph_width, pos[1] + s.line_height), im.get_color_u32(im.Col.TEXT_SELECTED_BG))
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                elif BgColorFn:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                    draw_list.add_rect_filled(pos, (pos[0] + s.glyph_width, pos[1] + s.line_height), bg_color_fn(mem_data, addr, UserData))
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                c = (read_fn(mem_data, addr, UserData) if ReadFn else mem_data[addr])
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                display_c = ('.' if (c < 32  or  c >= 128) else c)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                draw_list.add_text(pos, (color_text if (display_c == c) else color_disabled), display_c, display_c + 1)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                pos[0] = pos[0] + s.glyph_width
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        im.pop_style_var(2)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        child_width = im.get_window_size()[0]
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        im.end_child()
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        backup_pos = im.get_cursor_screen_pos()
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        im.set_cursor_pos_x(s.window_width)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        im.dummy((0.0, 0.0))
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        im.set_cursor_screen_pos(backup_pos)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        if data_next  and  self.data_editing_addr + 1 < mem_size:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            self.data_editing_addr = self.data_preview_addr = self.data_editing_addr + 1
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            self.data_editing_take_focus = True
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        elif data_editing_addr_next != (size_t)-1:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            self.data_editing_addr = self.data_preview_addr = data_editing_addr_next
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            self.data_editing_take_focus = True
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        lock_show_data_preview = self.opt_show_data_preview
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        if self.opt_show_options:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            im.separator()
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            draw_options_line(s, mem_data, mem_size, base_display_addr)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        if lock_show_data_preview:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            im.separator()
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            draw_preview_line(s, mem_data, mem_size, base_display_addr)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        if self.goto_addr != (size_t)-1:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            if self.goto_addr < mem_size:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                im.begin_child("##scrolling")
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                im.set_scroll_y((self.goto_addr / self.cols) * im.get_text_line_height() - avail_size[1] * 0.5)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                im.end_child()
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                self.data_editing_addr = self.data_preview_addr = self.goto_addr
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                self.data_editing_take_focus = True
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            self.goto_addr = (size_t)-1
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        const ImVec2 contents_pos_end(contents_pos_start[0] + child_width, im.get_cursor_screen_pos()[1])
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        if self.opt_show_options:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            if im.is_mouse_hovering_rect(contents_pos_start, contents_pos_end):
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                if im.is_window_hovered(im.HoveredFlags.CHILD_WINDOWS)  and  im.is_mouse_released(im.MouseButton.RIGHT):
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                    im.open_popup("OptionsPopup")
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        if im.begin_popup("OptionsPopup"):
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            im.set_next_item_width(s.glyph_width * 7 + style.frame_padding[0] * 2.0)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            if im.drag_int("##cols", self.cols, 0.2, 4, 32, "%d cols"):
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                self.contents_width_changed = True
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                if self.cols < 1:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                    self.cols = 1
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            im.checkbox("Show Data Preview", self.opt_show_data_preview)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            im.checkbox("Show HexII", self.opt_show_hex_ii)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            if im.checkbox("Show Ascii", self.opt_show_ascii):
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                self.contents_width_changed = True
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            im.checkbox("Grey out zeroes", self.opt_grey_out_zeroes)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            im.checkbox("Uppercase Hex", self.opt_upper_case_hex)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            im.end_popup()
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above    def draw_options_line(self, s, mem_data, mem_size, base_display_addr):
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        """DrawOptionsLine()."""
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        im_unused(mem_data)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        style = im.get_style()
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        format_range = ("Range %0*" + _PRISizeT + "X..%0*" + _PRISizeT + "X" if self.opt_upper_case_hex else "Range %0*" + _PRISizeT + "x..%0*" + _PRISizeT + "x")
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        if im.button("Options"):
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            im.open_popup("OptionsPopup")
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        im.same_line()
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        im.text(format_range, s.addr_digits_count, base_display_addr, s.addr_digits_count, base_display_addr + mem_size - 1)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        im.same_line()
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        im.set_next_item_width((s.addr_digits_count + 1) * s.glyph_width + style.frame_padding[0] * 2.0)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        if _changed, AddrInputBuf = im.input_text("##addr", AddrInputBuf, len(AddrInputBuf), im.InputTextFlags.CHARS_HEXADECIMAL | im.InputTextFlags.ENTER_RETURNS_TRUE):
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            goto_addr = None  # TODO(autoport): uninitialized size_t
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            if sscanf(AddrInputBuf, "%" + _PRISizeT + "X", goto_addr) == 1:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                self.goto_addr = goto_addr - base_display_addr
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                HighlightMin = HighlightMax = (size_t)-1
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above    def draw_preview_line(self, s, mem_data_void, mem_size, base_display_addr):
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        """DrawPreviewLine()."""
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        im_unused(base_display_addr)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        ImU8* mem_data = (ImU8*)mem_data_void
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        style = im.get_style()
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        im.align_text_to_frame_padding()
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        im.text("Preview as:")
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        im.same_line()
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        im.set_next_item_width((s.glyph_width * 10.0) + style.frame_padding[0] * 2.0 + style.item_inner_spacing[0])
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        supported_data_types = [im.DataType.S8, im.DataType.U8, im.DataType.S16, im.DataType.U16, im.DataType.S32, im.DataType.U32, im.DataType.S64, im.DataType.U64, im.DataType.FLOAT, im.DataType.DOUBLE]
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        if im.begin_combo("##combo_type", data_type_get_desc(self.preview_data_type), im.ComboFlags.HEIGHT_LARGEST):
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            for n in range(int(0), int(len(supported_data_types))):
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                data_type = supported_data_types[n]
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                if im.selectable(data_type_get_desc(data_type), self.preview_data_type == data_type):
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                    self.preview_data_type = data_type
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            im.end_combo()
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        im.same_line()
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        im.set_next_item_width((s.glyph_width * 6.0) + style.frame_padding[0] * 2.0 + style.item_inner_spacing[0])
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        im.combo("##combo_endianness", self.preview_endianness, "LE\0BE\0\0")
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        buf = ""
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        x = s.glyph_width * 6.0
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        has_value = self.data_preview_addr != (size_t)-1
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        if has_value:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            draw_preview_data(self.data_preview_addr, mem_data, mem_size, self.preview_data_type, DataFormat_Dec, buf, (size_t)len(buf))
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        im.text("Dec")
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        im.same_line(x)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        im.text((buf if has_value else "N/A"))
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        if has_value:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            draw_preview_data(self.data_preview_addr, mem_data, mem_size, self.preview_data_type, DataFormat_Hex, buf, (size_t)len(buf))
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        im.text("Hex")
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        im.same_line(x)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        im.text((buf if has_value else "N/A"))
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        if has_value:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            draw_preview_data(self.data_preview_addr, mem_data, mem_size, self.preview_data_type, DataFormat_Bin, buf, (size_t)len(buf))
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        buf[len(buf) - 1] = 0
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        im.text("Bin")
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        im.same_line(x)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        im.text((buf if has_value else "N/A"))
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above    def data_type_get_size(self, data_type):
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        """DataTypeGetSize()."""
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        sizes = [1, 1, 2, 2, 4, 4, 8, 8, sizeof(float), sizeof(double)]
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        im_assert(data_type >= 0  and  data_type < len(sizes))
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        return sizes[data_type]
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above    def is_big_endian(self):
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        """IsBigEndian()."""
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        ImU16 x = 1
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        c = [None] * (2)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        memcpy(c, x, 2)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        return c[0] != 0
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above    def endianness_copy_big_endian(self, _dst, _src, s, is_little_endian):
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        """EndiannessCopyBigEndian()."""
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        if is_little_endian:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            ImU8* dst = (ImU8*)_dst
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            ImU8* src = (ImU8*)_src + s - 1
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            for i in range(int(0, n = int(s)), int(n)):
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                memcpy(dst++, src--, 1)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            return _dst
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        else:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            return memcpy(_dst, _src, s)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above    def endianness_copy_little_endian(self, _dst, _src, s, is_little_endian):
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        """EndiannessCopyLittleEndian()."""
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        if is_little_endian:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            return memcpy(_dst, _src, s)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        else:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            ImU8* dst = (ImU8*)_dst
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            ImU8* src = (ImU8*)_src + s - 1
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            for i in range(int(0, n = int(s)), int(n)):
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                memcpy(dst++, src--, 1)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            return _dst
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above    def endianness_copy(self, dst, src, size):
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        """EndiannessCopy()."""
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        static void* (*fp)(void*, void*, size_t, int) = None
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        if fp == None:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            fp = (EndiannessCopyBigEndian if is_big_endian() else EndiannessCopyLittleEndian)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        return fp(dst, src, size, self.preview_endianness)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above    def draw_preview_data(self, addr, mem_data, mem_size, data_type, data_format, out_buf, out_buf_size):
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        """DrawPreviewData()."""
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        ImU8 buf[8]
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        elem_size = data_type_get_size(data_type)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        size = (mem_size - addr if addr + elem_size > mem_size else elem_size)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        if ReadFn:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            for i in range(int(0, n = int(size)), int(n)):
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                buf[i] = read_fn(mem_data, addr + i, UserData)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        else:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            if data_format == DataFormat_Bin:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                ImU8 binbuf[8]
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                endianness_copy(binbuf, buf, size)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                im_snprintf(out_buf, out_buf_size, "%s", format_binary(binbuf, int(size) * 8))
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                return
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        out_buf[0] = 0
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        if data_type == im.DataType.S8:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            ImS8 data = 0
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            endianness_copy(data, buf, size)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            if data_format == DataFormat_Dec:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                im_snprintf(out_buf, out_buf_size, "%hhd", data)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                return
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            if data_format == DataFormat_Hex:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                im_snprintf(out_buf, out_buf_size, "0x%02x", data & 0xFF)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                return
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        elif data_type == im.DataType.U8:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            ImU8 data = 0
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            endianness_copy(data, buf, size)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            if data_format == DataFormat_Dec:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                im_snprintf(out_buf, out_buf_size, "%hhu", data)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                return
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            if data_format == DataFormat_Hex:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                im_snprintf(out_buf, out_buf_size, "0x%02x", data & 0XFF)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                return
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        elif data_type == im.DataType.S16:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            ImS16 data = 0
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            endianness_copy(data, buf, size)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            if data_format == DataFormat_Dec:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                im_snprintf(out_buf, out_buf_size, "%hd", data)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                return
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            if data_format == DataFormat_Hex:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                im_snprintf(out_buf, out_buf_size, "0x%04x", data & 0xFFFF)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                return
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        elif data_type == im.DataType.U16:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            ImU16 data = 0
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            endianness_copy(data, buf, size)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            if data_format == DataFormat_Dec:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                im_snprintf(out_buf, out_buf_size, "%hu", data)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                return
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            if data_format == DataFormat_Hex:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                im_snprintf(out_buf, out_buf_size, "0x%04x", data & 0xFFFF)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                return
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        elif data_type == im.DataType.S32:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            data = 0
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            endianness_copy(data, buf, size)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            if data_format == DataFormat_Dec:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                im_snprintf(out_buf, out_buf_size, "%d", data)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                return
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            if data_format == DataFormat_Hex:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                im_snprintf(out_buf, out_buf_size, "0x%08x", data)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                return
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        elif data_type == im.DataType.U32:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            data = 0
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            endianness_copy(data, buf, size)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            if data_format == DataFormat_Dec:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                im_snprintf(out_buf, out_buf_size, "%u", data)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                return
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            if data_format == DataFormat_Hex:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                im_snprintf(out_buf, out_buf_size, "0x%08x", data)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                return
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        elif data_type == im.DataType.S64:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            data = 0
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            endianness_copy(data, buf, size)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            if data_format == DataFormat_Dec:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                im_snprintf(out_buf, out_buf_size, "%lld", (long long)data)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                return
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            if data_format == DataFormat_Hex:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                im_snprintf(out_buf, out_buf_size, "0x%016llx", (long long)data)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                return
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        elif data_type == im.DataType.U64:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            data = 0
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            endianness_copy(data, buf, size)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            if data_format == DataFormat_Dec:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                im_snprintf(out_buf, out_buf_size, "%llu", (long long)data)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                return
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            if data_format == DataFormat_Hex:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                im_snprintf(out_buf, out_buf_size, "0x%016llx", (long long)data)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                return
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        elif data_type == im.DataType.FLOAT:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            data = 0.0
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            endianness_copy(data, buf, size)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            if data_format == DataFormat_Dec:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                im_snprintf(out_buf, out_buf_size, "%f", data)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                return
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            if data_format == DataFormat_Hex:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                im_snprintf(out_buf, out_buf_size, "%a", data)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                return
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        elif data_type == im.DataType.DOUBLE:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            data = 0.0
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            endianness_copy(data, buf, size)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            if data_format == DataFormat_Dec:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                im_snprintf(out_buf, out_buf_size, "%f", data)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                return
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            if data_format == DataFormat_Hex:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                im_snprintf(out_buf, out_buf_size, "%a", data)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above                return
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        break = None  # TODO(autoport): default: -- construct this state
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        im_assert(0)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line aboveclass Sizes:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above    """Sizes, from imgui_memory_editor.h."""
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above    def __init__(self):
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        """Sizes()."""
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        self.AddrDigitsCount = None
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        self.LineHeight = None
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        self.GlyphWidth = None
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        self.HexCellWidth = None
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        self.SpacingBetweenMidCols = None
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        self.OffsetHexMinX = None
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        self.OffsetHexMaxX = None
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        self.OffsetAsciiMinX = None
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        self.OffsetAsciiMaxX = None
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        self.WindowWidth = None
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        memset(this, 0, sizeof(*this))
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line aboveclass InputTextUserData:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above    """InputTextUserData, from imgui_memory_editor.h."""
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above    def callback(self, data):
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        """Callback()."""
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        InputTextUserData* user_data = (InputTextUserData*)data.user_data
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        if not data.has_selection():
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            user_data.self.cursor_pos = data.self.cursor_pos
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        if data.flags & im.InputTextFlags.READ_ONLY:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            return 0
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        if data.selection_start == 0  and  data.selection_end == data.buf_text_len:
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            data.delete_chars(0, data.buf_text_len)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            data.insert_chars(0, user_data.current_buf_overwrite)
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            data.selection_start = 0
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            data.selection_end = 2
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above            data.self.cursor_pos = 0
# TODO(autoport): hand-translate (the rules mangled this line):                 pass  # TODO(autoport): body of the line above        return 0                pass  # TODO(autoport): body of the line above