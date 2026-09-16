"""imgui_markdown: auto-ported from imgui_markdown.h
(upstream, MIT) by tools/autoport.py.

A mechanical port of Dear ImGui C++ to emtk. Lines flagged
TODO(autoport) need a hand; everything else is the C++ under the
naming rules in tools/autoport.py.
"""
import math

import emtk.im as im

from enum import IntFlag

class MarkdownFormatFlags(IntFlag):
    """ImGuiMarkdownFormatFlags, from imgui_markdown.h."""
    NONE = 0

class MarkdownFormatType(IntFlag):
    """MarkdownFormatType, from imgui_markdown.h."""
    normal_text = 0
    heading = 1
    unordered_list = 2
    link = 3
    emphasis = 4

class LinkState(IntFlag):
    """LinkState, from imgui_markdown.h."""
    no_link = 0
    has_square_bracket_open = 1
    has_square_brackets = 2
    has_square_brackets_round_bracket_open = 3

class EmphasisState(IntFlag):
    """EmphasisState, from imgui_markdown.h."""
    none = 0
    left = 1
    middle = 2
    right = 3

class TextRegion:
    """TextRegion, from imgui_markdown.h."""

    def __init__(self):
        """TextRegion()."""
        indentX = 0.0

    def render_list_text_wrapped(self, text_, text_end_):
        """RenderListTextWrapped()."""
        bullet()
        same_line()
        render_text_wrapped(text_, text_end_, True)

    def reset_indent(self):
        """ResetIndent()."""
        if indentX > 0.0:
            unindent(indentX)
        indentX = 0.0

    def render_link_text(self, text_, text_end_, link_, markdown_, mdConfig_, linkHoverStart_):
        """TextRegion::RenderLinkText()."""
        formatInfo = None  # TODO(autoport): MarkdownFormatInfo -- construct this state
# TODO(autoport): hand-translate (the rules mangled this line):         formatInfo.config = &mdConfig_
        pass  # TODO(autoport): body of the line above
        formatInfo.type = MarkdownFormatType.LINK
        mdConfig_.format_callback(formatInfo, True)
        push_text_wrap_pos(-1.0)
        im.text(text_)
        pop_text_wrap_pos()
        bThisItemHovered = is_item_hovered()
        if bThisItemHovered:
# TODO(autoport): hand-translate (the rules mangled this line):             *linkHoverStart_ = markdown_ + link_.text.start
            pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):         bHovered = bThisItemHovered  or  ( *linkHoverStart_ == ( markdown_ + link_.text.start ) )
        pass  # TODO(autoport): body of the line above
        formatInfo.item_hovered = bHovered
        mdConfig_.format_callback(formatInfo, False)
        if bHovered:
            if is_mouse_released(0)  and  mdConfig_.link_callback:
                mdConfig_.link_callback(( markdown_ + link_.text.start, link_.text.size(), markdown_ + link_.url.start, link_.url.size(), mdConfig_.user_data, False ))
            if mdConfig_.tooltip_callback:
                mdConfig_.tooltip_callback(( ( markdown_ + link_.text.start, link_.text.size(), markdown_ + link_.url.start, link_.url.size(), mdConfig_.user_data, False ), mdConfig_.link_icon ))
        return bThisItemHovered

    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def render_text_wrapped(self, text_, text_end_, bIndentToHere_):
    pass
    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def render_link_text_wrapped(self, text_, text_end_, link_, markdown_,
    pass
class TextBlock:
    """TextBlock, from imgui_markdown.h."""

    def size(self):
        """size()."""
        return self.stop - self.start

def default_markdown_tooltip_callback(data_):
    """defaultMarkdownTooltipCallback()."""
    if data_.link_data.is_image:
        im.set_tooltip("%.*s" % (data_.link_data.link_length, data_.link_data.link))
    else:
        im.set_tooltip("%s Open in browser\n%.*s" % (data_.link_icon, data_.link_data.link_length, data_.link_data.link))

def under_line(col_):
    """UnderLine()."""
    min = get_item_rect_min()
    max = get_item_rect_max()
    min[1] = max[1]
    get_window_draw_list().add_line(min, max, col_, 1.0)

def render_line(markdown_, line_, textRegion_, mdConfig_):
    """RenderLine()."""
    indentStart = 0
    if line_.is_unordered_list_start:
        indentStart = 1
    for j in range(int(indentStart), int(line_.lead_space_count / 2)):
        indent()
    formatInfo = None  # TODO(autoport): MarkdownFormatInfo -- construct this state
# TODO(autoport): hand-translate (the rules mangled this line):     formatInfo.config = &mdConfig_
    pass  # TODO(autoport): body of the line above
    textStart = line_.last_render_position + 1
    textSize = line_.line_end - textStart
    if line_.is_unordered_list_start:
        formatInfo.type = MarkdownFormatType.UNORDERED_LIST
        mdConfig_.format_callback(formatInfo, True)
        text = markdown_ + textStart + 1
        textRegion_.render_list_text_wrapped(text, text + textSize - 1)
    elif line_.is_heading:
        formatInfo.level = line_.heading_count
        formatInfo.type = MarkdownFormatType.HEADING
        text = markdown_ + textStart + 1
        formatInfo.text = text
        formatInfo.text_length = textSize - 1
        mdConfig_.format_callback(formatInfo, True)
        textRegion_.render_text_wrapped(text, text + textSize - 1)
    elif line_.is_emphasis:
        formatInfo.level = line_.emphasis_count
        formatInfo.type = MarkdownFormatType.EMPHASIS
        mdConfig_.format_callback(formatInfo, True)
        text = markdown_ + textStart
        textRegion_.render_text_wrapped(text, text + textSize)
    else:
        formatInfo.type = MarkdownFormatType.NORMAL_TEXT
        mdConfig_.format_callback(formatInfo, True)
        text = markdown_ + textStart
        textRegion_.render_text_wrapped(text, text + textSize)
    mdConfig_.format_callback(formatInfo, False)
    for j in range(int(indentStart), int(line_.lead_space_count / 2)):
        unindent()

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def markdown(markdown_, markdownLength_, mdConfig_):
pass
def is_char_inside_word(c_):
    """IsCharInsideWord()."""
    return c_ != ' '  and  c_ != '.'  and  c_ != ','  and  c_ != ';'  and  c_ != '!'  and  c_ != '?'  and  c_ != '\"'

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def default_markdown_format_callback(markdownFormatInfo_, start_):
pass
# TODO(autoport): destructor ~TextRegion() dropped: Python has no deterministic destruction