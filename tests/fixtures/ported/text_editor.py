"""text_editor: auto-ported from TextEditor.h, TextEditor.cpp
(upstream, MIT) by tools/autoport.py.

A mechanical port of Dear ImGui C++ to cmtk. Lines flagged
TODO(autoport) need a hand; everything else is the C++ under the
naming rules in tools/autoport.py.
"""
import math

import cmtk.im as im

inited = False
inited = False
inited = False
inited = False
inited = False
inited = False
inited = False

from enum import IntFlag

class PaletteIndex(IntFlag):
    """PaletteIndex, from TextEditor.h."""
    default = 0
    keyword = 1
    number = 2
    string = 3
    char_literal = 4
    punctuation = 5
    preprocessor = 6
    identifier = 7
    known_identifier = 8
    preproc_identifier = 9
    comment = 10
    multi_line_comment = 11
    background = 12
    cursor = 13
    selection = 14
    error_marker = 15
    breakpoint = 16
    line_number = 17
    current_line_fill = 18
    current_line_fill_inactive = 19
    current_line_edge = 20
    max = 21

class SelectionMode(IntFlag):
    """SelectionMode, from TextEditor.h."""
    normal = 0
    word = 1
    line = 2

class TextEditor:
    """TextEditor, from TextEditor.h."""

    def set_error_markers(self, aMarkers):
        """SetErrorMarkers()."""
        mErrorMarkers = aMarkers

    def set_breakpoints(self, aMarkers):
        """SetBreakpoints()."""
        mBreakpoints = aMarkers

    def get_total_lines(self):
        """GetTotalLines()."""
        return int(mLines.size)()

    def is_overwrite(self):
        """IsOverwrite()."""
        return self.m_overwrite

    def is_read_only(self):
        """IsReadOnly()."""
        return self.m_read_only

    def is_text_changed(self):
        """IsTextChanged()."""
        return self.m_text_changed

    def is_cursor_position_changed(self):
        """IsCursorPositionChanged()."""
        return self.m_cursor_position_changed

    def is_colorizer_enabled(self):
        """IsColorizerEnabled()."""
        return self.m_colorizer_enabled

    def get_cursor_position(self):
        """GetCursorPosition()."""
        return get_actual_cursor_coordinates()

    def set_handle_mouse_inputs(self, aValue):
        """SetHandleMouseInputs()."""
        self.m_handle_mouse_inputs = aValue

    def is_handle_mouse_inputs_enabled(self):
        """IsHandleMouseInputsEnabled()."""
        return self.m_handle_keyboard_inputs

    def set_handle_keyboard_inputs(self, aValue):
        """SetHandleKeyboardInputs()."""
        self.m_handle_keyboard_inputs = aValue

    def is_handle_keyboard_inputs_enabled(self):
        """IsHandleKeyboardInputsEnabled()."""
        return self.m_handle_keyboard_inputs

    def set_im_gui_child_ignored(self, aValue):
        """SetImGuiChildIgnored()."""
        self.m_ignore_im_gui_child = aValue

    def is_im_gui_child_ignored(self):
        """IsImGuiChildIgnored()."""
        return self.m_ignore_im_gui_child

    def set_show_whitespaces(self, aValue):
        """SetShowWhitespaces()."""
        self.m_show_whitespaces = aValue

    def is_showing_whitespaces(self):
        """IsShowingWhitespaces()."""
        return self.m_show_whitespaces

    def get_tab_size(self):
        """GetTabSize()."""
        return self.m_tab_size

    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def __init__(self, count):
    pass
    def set_language_definition(self, aLanguageDef):
        """TextEditor::SetLanguageDefinition()."""
        mLanguageDefinition = aLanguageDef
        mRegexList.clear()
        for r in mLanguageDefinition.m_token_regex_strings:
            mRegexList.push_back(std.make_pair(std.regex(r.first, std.regex_constants.optimize), r.second))
        colorize()

    def set_palette(self, aValue):
        """TextEditor::SetPalette()."""
        mPaletteBase = aValue

    def get_actual_cursor_coordinates(self):
        """TextEditor::GetActualCursorCoordinates()."""
        return sanitize_coordinates(mState.m_cursor_position)

    def sanitize_coordinates(self, aValue):
        """TextEditor::SanitizeCoordinates()."""
        line = aValue.m_line
        column = aValue.m_column
        if line >= int(mLines.size)():
            if mLines.empty():
                line = 0
                column = 0
            else:
                line = int(mLines.size)() - 1
                column = get_line_max_column(line)
            return coordinates(line, column)
        else:
            column = (0 if mLines.empty() else std.min(column, get_line_max_column(line)))
            return coordinates(line, column)

    def advance(self, aCoordinates):
        """TextEditor::Advance()."""
        if aCoordinates.m_line < int(mLines.size)():
            line = mLines[aCoordinates.m_line]
            cindex = get_character_index(aCoordinates)
            if cindex + 1 < int(line.size)():
                delta = utf8_char_length(line[cindex].m_char)
                cindex = std.min(cindex + delta, int(line.size)() - 1)
            else:
                ++aCoordinates.m_line
                cindex = 0
            aCoordinates.m_column = get_character_column(aCoordinates.m_line, cindex)

    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def delete_range(self, aStart, aEnd):
    pass
    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def insert_text_at(self, aWhere, aValue):
    pass
    def add_undo(self, aValue):
        """TextEditor::AddUndo()."""
        assert(not self.m_read_only)
        mUndoBuffer.resize(int(self.m_undo_index + 1))
# TODO(autoport): hand-translate (the rules mangled this line):         mUndoBuffer.back() = aValue
        pass  # TODO(autoport): body of the line above
        mUndoIndex += 1

    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def screen_pos_to_coordinates(self, aPosition):
    pass
    def find_word_start(self, aFrom):
        """TextEditor::FindWordStart()."""
# TODO(autoport): hand-translate (the rules mangled this line):         Coordinates at = aFrom
        pass  # TODO(autoport): body of the line above
        if at.m_line >= int(mLines.size)():
            return at
        line = mLines[at.m_line]
        cindex = get_character_index(at)
        if cindex >= int(line.size)():
            return at
        while cindex > 0  and  isspace(line[cindex].m_char):
            cindex -= 1
        cstart = line[cindex].m_color_index
        while cindex > 0:
            c = line[cindex].m_char
            if (c & 0xC0) != 0x80:
                if c <= 32  and  isspace(c):
                    cindex += 1
                    break
                if cstart != line[size_t(cindex - 1)].m_color_index:
                    break
            cindex -= 1
        return coordinates(at.m_line, get_character_column(at.m_line, cindex))

    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def find_word_end(self, aFrom):
    pass
    def find_next_word(self, aFrom):
        """TextEditor::FindNextWord()."""
# TODO(autoport): hand-translate (the rules mangled this line):         Coordinates at = aFrom
        pass  # TODO(autoport): body of the line above
        if at.m_line >= int(mLines.size)():
            return at
        cindex = get_character_index(aFrom)
        isword = False
        skip = False
        if cindex < int(mLines)[at.m_line].size():
            line = mLines[at.m_line]
            isword = isalnum(line[cindex].m_char) != 0
            skip = isword
        while not isword  or  skip:
            if at.m_line >= mLines.size():
                l = std.max(0, int(mLines.size)() - 1)
                return coordinates(l, get_line_max_column(l))
            line = mLines[at.m_line]
            if cindex < int(line.size)():
                isword = isalnum(line[cindex].m_char) != 0
                if isword  and  not skip:
                    return coordinates(at.m_line, get_character_column(at.m_line, cindex))
                if not isword:
                    skip = False
                cindex += 1
            else:
                cindex = 0
                ++at.m_line
                skip = False
                isword = False
        return at

    def get_character_index(self, aCoordinates):
        """TextEditor::GetCharacterIndex()."""
        # TODO(autoport): for (; i < line.size() && c < aCoordinates.mColumn; )
        if aCoordinates.m_line >= mLines.size():
            return -1
        line = mLines[aCoordinates.m_line]
        c = 0
        i = 0
        for _ in range(0):  # TODO(autoport):
            if line[i].m_char == '\t':
                c = (c / self.m_tab_size) * self.m_tab_size + self.m_tab_size
            else:
                i = i + utf8_char_length(line[i].m_char)
        return i

    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def get_character_column(self, aLine, aIndex):
    pass
    def get_line_character_count(self, aLine):
        """TextEditor::GetLineCharacterCount()."""
        # TODO(autoport): for (i = 0; i < line.size(); c++)
        if aLine >= mLines.size():
            return 0
        line = mLines[aLine]
        c = 0
        for _ in range(0):  # TODO(autoport): for(i = 0; i < line.size(); c++):
            i = i + utf8_char_length(line[i].m_char)
        return c

    def get_line_max_column(self, aLine):
        """TextEditor::GetLineMaxColumn()."""
        # TODO(autoport): for (i = 0; i < line.size(); )
        if aLine >= mLines.size():
            return 0
        line = mLines[aLine]
        col = 0
        for _ in range(0):  # TODO(autoport): for(i = 0; i < line.size(); ):
            c = line[i].m_char
            if c == '\t':
                col = (col / self.m_tab_size) * self.m_tab_size + self.m_tab_size
            else:
                i = i + utf8_char_length(c)
        return col

    def is_on_word_boundary(self, aAt):
        """TextEditor::IsOnWordBoundary()."""
        if aAt.m_line >= int(mLines.size)()  or  aAt.m_column == 0:
            return True
        line = mLines[aAt.m_line]
        cindex = get_character_index(aAt)
        if cindex >= int(line.size)():
            return True
        if self.m_colorizer_enabled:
            return line[cindex].m_color_index != line[size_t(cindex - 1)].m_color_index
        return isspace(line[cindex].m_char) != isspace(line[cindex - 1].m_char)

    def remove_line(self, aIndex):
        """TextEditor::RemoveLine()."""
        assert(not self.m_read_only)
        assert(mLines.size() > 1)
        etmp = None  # TODO(autoport): ErrorMarkers -- construct this state
        for i in mErrorMarkers:
            e = ErrorMarkers.value_type((i.first - 1 if i.first > aIndex else i.first), i.second)
            if e.first - 1 == aIndex:
                continue
            etmp.insert(e)
        mErrorMarkers = std.move(etmp)
        btmp = None  # TODO(autoport): Breakpoints -- construct this state
        for i in mBreakpoints:
            if i == aIndex:
                continue
            btmp.insert((i - 1 if i >= aIndex else i))
        mBreakpoints = std.move(btmp)
        mLines.erase(mLines.begin() + aIndex)
        assert(not mLines.empty())
        self.m_text_changed = True

    def get_word_under_cursor(self):
        """TextEditor::GetWordUnderCursor()."""
        c = get_cursor_position()
        return get_word_at(c)

    def get_word_at(self, aCoords):
        """TextEditor::GetWordAt()."""
        start = find_word_start(aCoords)
        end = find_word_end(aCoords)
        r = ""  # TODO(autoport): std::string -> str: methods differ (substr, append, c_str)
        istart = get_character_index(start)
        iend = get_character_index(end)
        for it in range(int(istart), int(iend)):
            r.push_back(mLines[aCoords.m_line][it].m_char)
        return r

    def get_glyph_color(self, aGlyph):
        """TextEditor::GetGlyphColor()."""
        if not self.m_colorizer_enabled:
            return mPalette[PaletteIndex.default]
        if aGlyph.m_comment:
            return mPalette[PaletteIndex.comment]
        if aGlyph.m_multi_line_comment:
            return mPalette[PaletteIndex.multi_line_comment]
# TODO(autoport): hand-translate (the rules mangled this line):         auto const color = mPalette[int(aGlyph.m_color_index)]
        pass  # TODO(autoport): body of the line above
        if aGlyph.m_preprocessor:
            ppcolor = mPalette[PaletteIndex.preprocessor]
            c0 = ((ppcolor & 0xff) + (color & 0xff)) / 2
            c1 = (((ppcolor >> 8) & 0xff) + ((color >> 8) & 0xff)) / 2
            c2 = (((ppcolor >> 16) & 0xff) + ((color >> 16) & 0xff)) / 2
            c3 = (((ppcolor >> 24) & 0xff) + ((color >> 24) & 0xff)) / 2
            return int(c0 | (c1 << 8) | (c2 << 16) | (c3 << 24))
        return color

    def handle_keyboard_inputs(self):
        """TextEditor::HandleKeyboardInputs()."""
        io = im.get_io()
        shift = io.key_shift
        ctrl = (io.key_super if io.config_mac_osx_behaviors else io.key_ctrl)
        alt = (io.key_ctrl if io.config_mac_osx_behaviors else io.key_alt)
        if im.is_window_focused():
            if im.is_window_hovered():
                im.set_mouse_cursor(im.MouseCursor.TEXT_INPUT)
            io.want_capture_keyboard = True
            io.want_text_input = True
            if not is_read_only()  and  ctrl  and  not shift  and  not alt  and  im.is_key_pressed(im.Key.Z):
                undo()
            elif not is_read_only()  and  not ctrl  and  not shift  and  alt  and  im.is_key_pressed(im.Key.BACKSPACE):
                undo()
            elif not is_read_only()  and  ctrl  and  not shift  and  not alt  and  im.is_key_pressed(im.Key.Y):
                redo()
            elif not ctrl  and  not alt  and  im.is_key_pressed(im.Key.UP_ARROW):
                move_up(1, shift)
            elif not ctrl  and  not alt  and  im.is_key_pressed(im.Key.DOWN_ARROW):
                move_down(1, shift)
            elif not alt  and  im.is_key_pressed(im.Key.LEFT_ARROW):
                move_left(1, shift, ctrl)
            elif not alt  and  im.is_key_pressed(im.Key.RIGHT_ARROW):
                move_right(1, shift, ctrl)
            elif not alt  and  im.is_key_pressed(im.Key.PAGE_UP):
                move_up(get_page_size() - 4, shift)
            elif not alt  and  im.is_key_pressed(im.Key.PAGE_DOWN):
                move_down(get_page_size() - 4, shift)
            elif not alt  and  ctrl  and  im.is_key_pressed(im.Key.HOME):
                move_top(shift)
            elif ctrl  and  not alt  and  im.is_key_pressed(im.Key.END):
                move_bottom(shift)
            elif not ctrl  and  not alt  and  im.is_key_pressed(im.Key.HOME):
                move_home(shift)
            elif not ctrl  and  not alt  and  im.is_key_pressed(im.Key.END):
                move_end(shift)
            elif not is_read_only()  and  not ctrl  and  not shift  and  not alt  and  im.is_key_pressed(im.Key.DELETE):
                delete()
            elif not is_read_only()  and  not ctrl  and  not shift  and  not alt  and  im.is_key_pressed(im.Key.BACKSPACE):
                backspace()
            elif not ctrl  and  not shift  and  not alt  and  im.is_key_pressed(im.Key.INSERT):
                self.m_overwrite = self.m_overwrite ^ True
            elif ctrl  and  not shift  and  not alt  and  im.is_key_pressed(im.Key.INSERT):
                copy()
            elif ctrl  and  not shift  and  not alt  and  im.is_key_pressed(im.Key.C):
                copy()
            elif not is_read_only()  and  not ctrl  and  shift  and  not alt  and  im.is_key_pressed(im.Key.INSERT):
                paste()
            elif not is_read_only()  and  ctrl  and  not shift  and  not alt  and  im.is_key_pressed(im.Key.V):
                paste()
            elif ctrl  and  not shift  and  not alt  and  im.is_key_pressed(im.Key.X):
                cut()
            elif not ctrl  and  shift  and  not alt  and  im.is_key_pressed(im.Key.DELETE):
                cut()
            elif ctrl  and  not shift  and  not alt  and  im.is_key_pressed(im.Key.A):
                select_all()
            elif not is_read_only()  and  not ctrl  and  not shift  and  not alt  and  im.is_key_pressed(im.Key.ENTER):
                enter_character('\n', False)
            elif not is_read_only()  and  not ctrl  and  not alt  and  im.is_key_pressed(im.Key.TAB):
                enter_character('\t', shift)
            if not is_read_only()  and  not io.input_queue_characters.empty():
                for i in range(int(0), int(io.input_queue_characters.size)):
                    c = io.input_queue_characters[i]
                    if c != 0  and  (c == '\n'  or  c >= 32):
                        enter_character(c, shift)
                io.input_queue_characters.resize(0)

    def handle_mouse_inputs(self):
        """TextEditor::HandleMouseInputs()."""
        io = im.get_io()
        shift = io.key_shift
        ctrl = (io.key_super if io.config_mac_osx_behaviors else io.key_ctrl)
        alt = (io.key_ctrl if io.config_mac_osx_behaviors else io.key_alt)
        if im.is_window_hovered():
            if not shift  and  not alt:
                click = im.is_mouse_clicked(0)
                doubleClick = im.is_mouse_double_clicked(0)
                t = im.get_time()
                tripleClick = click  and  not doubleClick  and  (self.m_last_click != -1.0  and  (t - self.m_last_click) < io.mouse_double_click_time)
                if tripleClick:
                    if not ctrl:
                        mState.m_cursor_position = mInteractiveStart = mInteractiveEnd = screen_pos_to_coordinates(im.get_mouse_pos())
                        mSelectionMode = SelectionMode.line
                        set_selection(mInteractiveStart, mInteractiveEnd, mSelectionMode)
                    self.m_last_click = -1.0
                elif doubleClick:
                    if not ctrl:
                        mState.m_cursor_position = mInteractiveStart = mInteractiveEnd = screen_pos_to_coordinates(im.get_mouse_pos())
                        if mSelectionMode == SelectionMode.line:
                            mSelectionMode = SelectionMode.normal
                        else:
                            set_selection(mInteractiveStart, mInteractiveEnd, mSelectionMode)
                    self.m_last_click = im.get_time()
                elif click:
                    mState.m_cursor_position = mInteractiveStart = mInteractiveEnd = screen_pos_to_coordinates(im.get_mouse_pos())
                    if ctrl:
                        mSelectionMode = SelectionMode.word
                    else:
                        set_selection(mInteractiveStart, mInteractiveEnd, mSelectionMode)
                    self.m_last_click = im.get_time()
                elif im.is_mouse_dragging(0)  and  im.is_mouse_down(0):
                    io.want_capture_mouse = True
                    mState.m_cursor_position = mInteractiveEnd = screen_pos_to_coordinates(im.get_mouse_pos())
                    set_selection(mInteractiveStart, mInteractiveEnd, mSelectionMode)

    def render(self, aTitle, aSize, aBorder):
        """TextEditor::Render()."""
        # TODO(autoport): BeginChild: cmtk takes a box anchored at the cursor; the id/border/flags are dropped
        self.m_within_render = True
        self.m_text_changed = False
        self.m_cursor_position_changed = False
        im.push_style_color(im.Col.CHILD_BG, im.color_convert_u32_to_float4(mPalette[PaletteIndex.background]))
        im.push_style_var(im.StyleVar.ITEM_SPACING, (0.0, 0.0))
        if not self.m_ignore_im_gui_child:
            im.begin_child((*im.get_cursor_screen_pos(), aSize[0], aSize[1]))
        if self.m_handle_keyboard_inputs:
            handle_keyboard_inputs()
            im.push_item_flag(im.ItemFlags.NO_TAB_STOP, False)
        if self.m_handle_mouse_inputs:
            handle_mouse_inputs()
        colorize_internal()
        render()
        if self.m_handle_keyboard_inputs:
            im.pop_item_flag()
        if not self.m_ignore_im_gui_child:
            im.end_child()
        im.pop_style_var()
        im.pop_style_color()
        self.m_within_render = False

    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def set_text(self, aText):
    pass
    def set_text_lines(self, aLines):
        """TextEditor::SetTextLines()."""
        mLines.clear()
        if aLines.empty():
            mLines.emplace_back(line())
        else:
            mLines.resize(aLines.size())
            for i in range(int(0), int(aLines.size())):
                aLine = aLines[i]
                mLines[i].reserve(aLine.size())
                for j in range(int(0), int(aLine.size())):
                    mLines[i].emplace_back(glyph(aLine[j], PaletteIndex.default))
        self.m_text_changed = True
        self.m_scroll_to_top = True
        mUndoBuffer.clear()
        self.m_undo_index = 0
        colorize()

    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def enter_character(self, aChar, aShift):
    pass
    def set_read_only(self, aValue):
        """TextEditor::SetReadOnly()."""
        self.m_read_only = aValue

    def set_colorizer_enable(self, aValue):
        """TextEditor::SetColorizerEnable()."""
        self.m_colorizer_enabled = aValue

    def set_cursor_position(self, aPosition):
        """TextEditor::SetCursorPosition()."""
        if mState.m_cursor_position != aPosition:
            mState.m_cursor_position = aPosition
            self.m_cursor_position_changed = True
            ensure_cursor_visible()

    def set_selection_start(self, aPosition):
        """TextEditor::SetSelectionStart()."""
        mState.m_selection_start = sanitize_coordinates(aPosition)
        if mState.m_selection_start > mState.m_selection_end:
            std.swap(mState.m_selection_start, mState.m_selection_end)

    def set_selection_end(self, aPosition):
        """TextEditor::SetSelectionEnd()."""
        mState.m_selection_end = sanitize_coordinates(aPosition)
        if mState.m_selection_start > mState.m_selection_end:
            std.swap(mState.m_selection_start, mState.m_selection_end)

    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def set_selection(self, aStart, aEnd, aMode):
    pass
    def set_tab_size(self, aValue):
        """TextEditor::SetTabSize()."""
        self.m_tab_size = std.max(0, std.min(32, aValue))

    def insert_text(self, aValue):
        """TextEditor::InsertText()."""
        if aValue == None:
            return
        pos = get_actual_cursor_coordinates()
        start = std.min(pos, mState.m_selection_start)
        totalLines = pos.m_line - start.m_line
        totalLines = totalLines + insert_text_at(pos, aValue)
        set_selection(pos, pos)
        set_cursor_position(pos)
        colorize(start.m_line - 1, totalLines + 2)

    def delete_selection(self):
        """TextEditor::DeleteSelection()."""
        assert(mState.m_selection_end >= mState.m_selection_start)
        if mState.m_selection_end == mState.m_selection_start:
            return
        delete_range(mState.m_selection_start, mState.m_selection_end)
        set_selection(mState.m_selection_start, mState.m_selection_start)
        set_cursor_position(mState.m_selection_start)
        colorize(mState.m_selection_start.m_line, 1)

    def move_up(self, aAmount, aSelect):
        """TextEditor::MoveUp()."""
        oldPos = mState.m_cursor_position
        mState.m_cursor_position.m_line = std.max(0, mState.m_cursor_position.m_line - aAmount)
        if oldPos != mState.m_cursor_position:
            if aSelect:
                if oldPos == mInteractiveStart:
                    mInteractiveStart = mState.m_cursor_position
                elif oldPos == mInteractiveEnd:
                    mInteractiveEnd = mState.m_cursor_position
                else:
                    mInteractiveStart = mState.m_cursor_position
                    mInteractiveEnd = oldPos
            else:
                set_selection(mInteractiveStart, mInteractiveEnd)
            ensure_cursor_visible()

    def move_down(self, aAmount, aSelect):
        """TextEditor::MoveDown()."""
        assert(mState.m_cursor_position.m_column >= 0)
        oldPos = mState.m_cursor_position
        mState.m_cursor_position.m_line = std.max(0, std.min(int(mLines.size)() - 1, mState.m_cursor_position.m_line + aAmount))
        if mState.m_cursor_position != oldPos:
            if aSelect:
                if oldPos == mInteractiveEnd:
                    mInteractiveEnd = mState.m_cursor_position
                elif oldPos == mInteractiveStart:
                    mInteractiveStart = mState.m_cursor_position
                else:
                    mInteractiveStart = oldPos
                    mInteractiveEnd = mState.m_cursor_position
            else:
                set_selection(mInteractiveStart, mInteractiveEnd)
            ensure_cursor_visible()

    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def move_left(self, aAmount, aSelect, aWordMode):
    pass
    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def move_right(self, aAmount, aSelect, aWordMode):
    pass
    def move_top(self, aSelect):
        """TextEditor::MoveTop()."""
        oldPos = mState.m_cursor_position
        set_cursor_position(coordinates(0, 0))
        if mState.m_cursor_position != oldPos:
            if aSelect:
                mInteractiveEnd = oldPos
                mInteractiveStart = mState.m_cursor_position
            else:
                set_selection(mInteractiveStart, mInteractiveEnd)

    def move_home(self, aSelect):
        """TextEditor::MoveHome()."""
        oldPos = mState.m_cursor_position
        set_cursor_position(coordinates(mState.m_cursor_position.m_line, 0))
        if mState.m_cursor_position != oldPos:
            if aSelect:
                if oldPos == mInteractiveStart:
                    mInteractiveStart = mState.m_cursor_position
                elif oldPos == mInteractiveEnd:
                    mInteractiveEnd = mState.m_cursor_position
                else:
                    mInteractiveStart = mState.m_cursor_position
                    mInteractiveEnd = oldPos
            else:
                set_selection(mInteractiveStart, mInteractiveEnd)

    def move_end(self, aSelect):
        """TextEditor::MoveEnd()."""
        oldPos = mState.m_cursor_position
        set_cursor_position(coordinates(mState.m_cursor_position.m_line, get_line_max_column(oldPos.m_line)))
        if mState.m_cursor_position != oldPos:
            if aSelect:
                if oldPos == mInteractiveEnd:
                    mInteractiveEnd = mState.m_cursor_position
                elif oldPos == mInteractiveStart:
                    mInteractiveStart = mState.m_cursor_position
                else:
                    mInteractiveStart = oldPos
                    mInteractiveEnd = mState.m_cursor_position
            else:
                set_selection(mInteractiveStart, mInteractiveEnd)

    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def delete(self):
    pass
    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def backspace(self):
    pass
    def select_word_under_cursor(self):
        """TextEditor::SelectWordUnderCursor()."""
        c = get_cursor_position()
        set_selection(find_word_start(c), find_word_end(c))

    def select_all(self):
        """TextEditor::SelectAll()."""
        set_selection(coordinates(0, 0), coordinates(int(mLines.size)(), 0))

    def has_selection(self):
        """TextEditor::HasSelection()."""
        return mState.m_selection_end > mState.m_selection_start

    def copy(self):
        """TextEditor::Copy()."""
        if has_selection():
            im.set_clipboard_text(get_selected_text())
        else:
            if not mLines.empty():
                str = ""  # TODO(autoport): std::string -> str: methods differ (substr, append, c_str)
                line = mLines[get_actual_cursor_coordinates().m_line]
                for g in line:
                    str.push_back(g.m_char)
                im.set_clipboard_text(str)

    def cut(self):
        """TextEditor::Cut()."""
        if is_read_only():
            copy()
        else:
            if has_selection():
                u = None  # TODO(autoport): UndoRecord -- construct this state
                u.m_before = mState
                u.m_removed = get_selected_text()
                u.m_removed_start = mState.m_selection_start
                u.m_removed_end = mState.m_selection_end
                copy()
                delete_selection()
                u.m_after = mState
                add_undo(u)

    def paste(self):
        """TextEditor::Paste()."""
        if is_read_only():
            return
        clipText = im.get_clipboard_text()
        if clipText != None  and  len(clipText) > 0:
            u = None  # TODO(autoport): UndoRecord -- construct this state
            u.m_before = mState
            if has_selection():
                u.m_removed = get_selected_text()
                u.m_removed_start = mState.m_selection_start
                u.m_removed_end = mState.m_selection_end
                delete_selection()
            u.m_added = clipText
            u.m_added_start = get_actual_cursor_coordinates()
            insert_text(clipText)
            u.m_added_end = get_actual_cursor_coordinates()
            u.m_after = mState
            add_undo(u)

    def can_undo(self):
        """TextEditor::CanUndo()."""
        return not self.m_read_only  and  self.m_undo_index > 0

    def can_redo(self):
        """TextEditor::CanRedo()."""
        return not self.m_read_only  and  self.m_undo_index < int(mUndoBuffer.size)()

    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def undo(self, aSteps):
    pass
    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def redo(self, aSteps):
    pass
    def get_text(self):
        """TextEditor::GetText()."""
        return get_text(coordinates(), coordinates(int(mLines.size)(), 0))

    def get_text_lines(self):
        """TextEditor::GetTextLines()."""
        result = None  # TODO(autoport): std::vector -- construct this state
        result.reserve(mLines.size())
        for line in mLines:
            text = ""  # TODO(autoport): std::string -> str: methods differ (substr, append, c_str)
            text.resize(line.size())
            for i in range(int(0), int(line.size())):
                text[i] = line[i].m_char
            result.emplace_back(std.move(text))
        return result

    def get_selected_text(self):
        """TextEditor::GetSelectedText()."""
        return get_text(mState.m_selection_start, mState.m_selection_end)

    def get_current_line_text(self):
        """TextEditor::GetCurrentLineText()."""
        lineLength = get_line_max_column(mState.m_cursor_position.m_line)
        return get_text(coordinates(mState.m_cursor_position.m_line, 0), coordinates(mState.m_cursor_position.m_line, lineLength))

    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def process_inputs(self):
    pass
    def colorize(self, aFromLine, aLines):
        """TextEditor::Colorize()."""
        toLine = (int(mLines.size)() if aLines == -1 else std.min(int(mLines.size)(), aFromLine + aLines))
        mColorRangeMin = std.min(mColorRangeMin, aFromLine)
        mColorRangeMax = std.max(mColorRangeMax, toLine)
        mColorRangeMin = std.max(0, mColorRangeMin)
        mColorRangeMax = std.max(mColorRangeMin, mColorRangeMax)
        self.m_check_comments = True

    def colorize_range(self, aFromLine, aToLine):
        """TextEditor::ColorizeRange()."""
        # TODO(autoport): for (first = bufferBegin; first != last; )
        if mLines.empty()  or  aFromLine >= aToLine:
            return
        buffer = ""  # TODO(autoport): std::string -> str: methods differ (substr, append, c_str)
        results = None  # TODO(autoport): std::cmatch -- construct this state
        id = ""  # TODO(autoport): std::string -> str: methods differ (substr, append, c_str)
        endLine = std.max(0, std.min(int(mLines.size)(), aToLine))
        for i in range(int(aFromLine), int(endLine)):
            line = mLines[i]
            if line.empty():
                continue
            buffer.resize(line.size())
            for j in range(int(0), int(line.size())):
                col = line[j]
                buffer[j] = col.m_char
                col.m_color_index = PaletteIndex.default
# TODO(autoport): hand-translate (the rules mangled this line):             bufferBegin = &buffer.front()
            pass  # TODO(autoport): body of the line above
            bufferEnd = bufferBegin + buffer.size()
            last = bufferEnd
            for _ in range(0):  # TODO(autoport): for(first = bufferBegin; first != last; ):
                token_begin = None
                token_end = None
# TODO(autoport): hand-translate (the rules mangled this line):                 PaletteIndex token_color = PaletteIndex.default
                pass  # TODO(autoport): body of the line above
                hasTokenizeResult = False
                if mLanguageDefinition.m_tokenize != None:
                    if mLanguageDefinition.m_tokenize(first, last, token_begin, token_end, token_color):
                        hasTokenizeResult = True
                if hasTokenizeResult == False:
                    for p in mRegexList:
                        if std.regex_search(first, last, results, p.first, std.regex_constants.match_continuous):
                            hasTokenizeResult = True
# TODO(autoport): hand-translate (the rules mangled this line):                             v = *results.begin()
                            pass  # TODO(autoport): body of the line above
                            token_begin = v.first
                            token_end = v.second
                            token_color = p.second
                            break
                if hasTokenizeResult == False:
                    first += 1
                else:
                    token_length = token_end - token_begin
                    if token_color == PaletteIndex.identifier:
                        id.assign(token_begin, token_end)
                        if not mLanguageDefinition.m_case_sensitive:
                            std.transform(id.begin(), id.end(), id.begin(), toupper)
                        if not line[first - bufferBegin].m_preprocessor:
                            if mLanguageDefinition.m_keywords.count(id) != 0:
                                token_color = PaletteIndex.keyword
                            elif mLanguageDefinition.m_identifiers.count(id) != 0:
                                token_color = PaletteIndex.known_identifier
                            elif mLanguageDefinition.m_preproc_identifiers.count(id) != 0:
                                token_color = PaletteIndex.preproc_identifier
                        else:
                            if mLanguageDefinition.m_preproc_identifiers.count(id) != 0:
                                token_color = PaletteIndex.preproc_identifier
                    for j in range(int(0), int(token_length)):
                        line[(token_begin - bufferBegin) + j].m_color_index = token_color
                    first = token_end

    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def colorize_internal(self):
    pass
    def text_distance_to_line_start(self, aFrom):
        """TextEditor::TextDistanceToLineStart()."""
        # TODO(autoport): for (it = 0u; it < line.size() && it < colIndex; )
        # TODO(autoport): for (; i < 6 && d-- > 0 && it < (int)line.size(); i++, it++)
        line = mLines[aFrom.m_line]
        distance = 0.0
        spaceSize = im.get_font().calc_text_size_a(im.get_font_size(), FLT_MAX, -1.0, " ", None, None)[0]
        colIndex = get_character_index(aFrom)
        for _ in range(0):  # TODO(autoport): for(it = 0u; it < line.size() && it < colIndex; ):
            if line[it].m_char == '\t':
                distance = (1.0 + std.floor((1.0 + distance) / (float(self.m_tab_size) * spaceSize))) * (float(self.m_tab_size) * spaceSize)
                it += 1
            else:
                d = utf8_char_length(line[it].m_char)
                tempCString = [None] * (7)
                i = 0
                for _ in range(0):  # TODO(autoport):
                    tempCString[i] = line[it].m_char
                tempCString[i] = '\0'
                distance = distance + im.get_font().calc_text_size_a(im.get_font_size(), FLT_MAX, -1.0, tempCString, None, None)[0]
        return distance

    def ensure_cursor_visible(self):
        """TextEditor::EnsureCursorVisible()."""
        if not self.m_within_render:
            self.m_scroll_to_cursor = True
            return
        scrollX = im.get_scroll_x()
        scrollY = im.get_scroll_y()
        height = im.get_window_height()
        width = im.get_window_width()
        top = 1 + int(ceil)(scrollY / self.m_char_advance[1])
        bottom = int(ceil)((scrollY + height) / self.m_char_advance[1])
        left = int(ceil)(scrollX / self.m_char_advance[0])
        right = int(ceil)((scrollX + width) / self.m_char_advance[0])
        pos = get_actual_cursor_coordinates()
        len = text_distance_to_line_start(pos)
        if pos.m_line < top:
            im.set_scroll_y(std.max(0.0, (pos.m_line - 1) * self.m_char_advance[1]))
        if pos.m_line > bottom - 4:
            im.set_scroll_y(std.max(0.0, (pos.m_line + 4) * self.m_char_advance[1] - height))
        if len + self.m_text_start < left + 4:
            im.set_scroll_x(std.max(0.0, len + self.m_text_start - 4))
        if len + self.m_text_start > right - 4:
            im.set_scroll_x(std.max(0.0, len + self.m_text_start + 4 - width))

    def get_page_size(self):
        """TextEditor::GetPageSize()."""
        height = im.get_window_height() - 20.0
        return int(floor)(height / self.m_char_advance[1])

class Breakpoint:
    """Breakpoint, from TextEditor.h."""

    def __init__(self):
        """Breakpoint()."""
        self.mLine = None
        self.mEnabled = None
        self.mCondition = None
        self.m_line = -1
        self.m_enabled = False

class Coordinates:
    """Coordinates, from TextEditor.h."""

    def __init__(self):
        """Coordinates()."""
        mLine = 0
        mColumn = 0

    def __init__2(self, aLine, aColumn):
        """Coordinates()."""
        mLine = aLine
        mColumn = aColumn
        assert(aLine >= 0)
        assert(aColumn >= 0)

    def invalid(self):
        """Invalid()."""
        invalid = coordinates(-1, -1)
        return invalid

class Glyph:
    """Glyph, from TextEditor.h."""

    def __init__(self, aChar, aColorIndex):
        """Glyph()."""
        mChar = aChar
        mColorIndex = aColorIndex
        mComment = False
        mMultiLineComment = False
        mPreprocessor = False

class LanguageDefinition:
    """LanguageDefinition, from TextEditor.h."""

    def __init__(self):
        """LanguageDefinition()."""
        self.mName = None
        self.mPreprocChar = None
        self.mAutoIndentation = None
        self.mCaseSensitive = None
        self.m_preproc_char = '#'
        self.m_auto_indentation = True
        mTokenize = None
        self.m_case_sensitive = True

class UndoRecord:
    """UndoRecord, from TextEditor.h."""

    def __init__(self):
        """UndoRecord()."""
        self.mAdded = None
        self.mRemoved = None

def equals(first1, last1, first2, last2, p):
    """equals()."""
    # TODO(autoport): for (; first1 != last1 && first2 != last2; ++first1, ++first2)
    for _ in range(0):  # TODO(autoport):
        if not p(*first1, *first2):
            return False
    return first1 == last1  and  first2 == last2

def utf8_char_length(c):
    """UTF8CharLength()."""
    if (c & 0xFE) == 0xFC:
        return 6
    if (c & 0xFC) == 0xF8:
        return 5
    if (c & 0xF8) == 0xF0:
        return 4
    elif (c & 0xF0) == 0xE0:
        return 3
    elif (c & 0xE0) == 0xC0:
        return 2
    return 1

def im_text_char_to_utf8(buf, buf_size, c):
    """ImTextCharToUtf8()."""
    if c < 0x80:
        buf[0] = c
        return 1
    if c < 0x800:
        if buf_size < 2:
            return 0
        buf[0] = (char)(0xc0 + (c >> 6))
        buf[1] = (char)(0x80 + (c & 0x3f))
        return 2
    if c >= 0xdc00  and  c < 0xe000:
        return 0
    if c >= 0xd800  and  c < 0xdc00:
        if buf_size < 4:
            return 0
        buf[0] = (char)(0xf0 + (c >> 18))
        buf[1] = (char)(0x80 + ((c >> 12) & 0x3f))
        buf[2] = (char)(0x80 + ((c >> 6) & 0x3f))
        buf[3] = (char)(0x80 + ((c) & 0x3f))
        return 4
    if buf_size < 3:
        return 0
    buf[0] = (char)(0xe0 + (c >> 12))
    buf[1] = (char)(0x80 + ((c >> 6) & 0x3f))
    buf[2] = (char)(0x80 + ((c) & 0x3f))
    return 3

def is_utf_sequence(c):
    """IsUTFSequence()."""
    return (c & 0xC0) == 0x80

def move_bottom(aSelect):
    """TextEditor::TextEditor::MoveBottom()."""
    oldPos = get_cursor_position()
    newPos = coordinates(int(mLines.size)() - 1, 0)
    set_cursor_position(newPos)
    if aSelect:
        mInteractiveStart = oldPos
        mInteractiveEnd = newPos
    else:
        set_selection(mInteractiveStart, mInteractiveEnd)

def undo_record(aAdded, aAddedStart, aAddedEnd, aRemoved, aRemovedStart, aRemovedEnd, aBefore, aAfter):
    """TextEditor::UndoRecord::UndoRecord()."""
    mAdded = aAdded
    mAddedStart = aAddedStart
    mAddedEnd = aAddedEnd
    mRemoved = aRemoved
    mRemovedStart = aRemovedStart
    mRemovedEnd = aRemovedEnd
    mBefore = aBefore
    mAfter = aAfter
    assert(mAddedStart <= mAddedEnd)
    assert(mRemovedStart <= mRemovedEnd)

def undo(aEditor):
    """TextEditor::UndoRecord::Undo()."""
    if not mAdded.empty():
        aEditor.delete_range(mAddedStart, mAddedEnd)
        aEditor.colorize(mAddedStart.m_line - 1, mAddedEnd.m_line - mAddedStart.m_line + 2)
    if not mRemoved.empty():
        start = mRemovedStart
        aEditor.insert_text_at(start, mRemoved)
        aEditor.colorize(mRemovedStart.m_line - 1, mRemovedEnd.m_line - mRemovedStart.m_line + 2)
    aEditor.m_state = mBefore
    aEditor.ensure_cursor_visible()

def redo(aEditor):
    """TextEditor::UndoRecord::Redo()."""
    if not mRemoved.empty():
        aEditor.delete_range(mRemovedStart, mRemovedEnd)
        aEditor.colorize(mRemovedStart.m_line - 1, mRemovedEnd.m_line - mRemovedStart.m_line + 1)
    if not mAdded.empty():
        start = mAddedStart
        aEditor.insert_text_at(start, mAdded)
        aEditor.colorize(mAddedStart.m_line - 1, mAddedEnd.m_line - mAddedStart.m_line + 1)
    aEditor.m_state = mAfter
    aEditor.ensure_cursor_visible()

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def tokenize_c_style_string(in_begin, in_end, out_begin, out_end):
pass
# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def tokenize_c_style_character_literal(in_begin, in_end, out_begin, ou
pass
# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def tokenize_c_style_identifier(in_begin, in_end, out_begin, out_end):
pass
# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def tokenize_c_style_number(in_begin, in_end, out_begin, out_end):
pass
# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def tokenize_c_style_punctuation(in_begin, in_end, out_begin, out_end)
pass
# TODO(autoport): destructor ~UndoRecord() dropped: Python has no deterministic destruction