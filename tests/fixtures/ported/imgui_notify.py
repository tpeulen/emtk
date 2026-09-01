"""imgui_notify: auto-ported from imgui_notify.h
(upstream, MIT) by tools/autoport.py.

A mechanical port of Dear ImGui C++ to cmtk. Lines flagged
TODO(autoport) need a hand; everything else is the C++ under the
naming rules in tools/autoport.py.
"""
import math

import cmtk.im as im

# hand-pass: the notify example supplies this from its icon
# font range; with no icon atlas there is no icon to draw.
ICON_MIN_FA = 0
ICON_MAX_FA = 0

NOTIFY_MAX_MSG_LENGTH = 4096
NOTIFY_PADDING_X = 20.
NOTIFY_PADDING_Y = 20.
NOTIFY_PADDING_MESSAGE_Y = 10.
NOTIFY_FADE_IN_OUT_TIME = 150
NOTIFY_DEFAULT_DISMISS = 3000
NOTIFY_OPACITY = 1.0
NOTIFY_TOAST_FLAGS = im.WindowFlags.ALWAYS_AUTO_RESIZE | im.WindowFlags.NO_DECORATION | im.WindowFlags.NO_INPUTS | im.WindowFlags.NO_NAV | im.WindowFlags.NO_BRING_TO_FRONT_ON_FOCUS | im.WindowFlags.NO_FOCUS_ON_APPEARING

from enum import IntFlag

class ToastType(IntFlag):
    """ImGuiToastType, from imgui_notify.h."""
    NONE = 0
    SUCCESS = 1
    WARNING = 2
    ERROR = 4
    INFO = 8
    COUNT = 16

class ToastPhase(IntFlag):
    """ImGuiToastPhase, from imgui_notify.h."""
    NONE = 0
    FADE_IN = 1
    WAIT = 2
    FADE_OUT = 4
    EXPIRED = 8
    COUNT = 16

class ToastPos(IntFlag):
    """ImGuiToastPos, from imgui_notify.h."""
    NONE = 0
    TOP_LEFT = 1
    TOP_CENTER = 2
    TOP_RIGHT = 4
    BOTTOM_LEFT = 8
    BOTTOM_CENTER = 16
    BOTTOM_RIGHT = 32
    CENTER = 64
    COUNT = 128

class ImGuiToast:
    """ImGuiToast, from imgui_notify.h."""

    def set_title(self, format, args):
        """set_title()."""
        vsnprintf(self.title, sizeof(self.title), format, args)

    def set_content(self, format, args):
        """set_content()."""
        vsnprintf(self.content, sizeof(self.content), format, args)

    def get_elapsed_time(self):
        """get_elapsed_time()."""
        return get_tick_count() - self.creation_time

    def __init__(self, type, dismiss_time=NOTIFY_DEFAULT_DISMISS):
        """ImGuiToast()."""
        self.dismiss_time = NOTIFY_DEFAULT_DISMISS
        im_assert(type < ToastType.COUNT)
        self.type = type
        self.dismiss_time = self.dismiss_time
        self.creation_time = get_tick_count()
        memset(self.title, 0, sizeof(self.title))
        memset(self.content, 0, sizeof(self.content))

    def __init__2(self, type, format, _arg2):
        """ImGuiToast()."""
        self.dismiss_time = NOTIFY_DEFAULT_DISMISS
        ImGuiToast = type
        notify_format(self.set_content, format)

    def __init__3(self, type, dismiss_time, format, _arg3):
        """ImGuiToast()."""
        self.dismiss_time = NOTIFY_DEFAULT_DISMISS
        ImGuiToast = type, self.dismiss_time
        notify_format(self.set_content, format)

def insert_notification(toast):
    """InsertNotification()."""
    notifications.push_back(toast)

def remove_notification(index):
    """RemoveNotification()."""
    notifications.erase(notifications.begin() + index)

def render_notifications():
    """RenderNotifications()."""
    vp_size = get_main_viewport().size
    height = 0.
    for i in range(int(0), int(notifications.size())):
# TODO(autoport): hand-translate (the rules mangled this line):         auto* current_toast = notifications[i]
        pass  # TODO(autoport): body of the line above
        if current_toast.get_phase() == ToastPhase.EXPIRED:
            remove_notification(i)
            continue
        icon = current_toast.get_icon()
        title = current_toast.get_title()
        content = current_toast.get_content()
        default_title = current_toast.get_default_title()
        opacity = current_toast.get_fade_percent()
        text_color = current_toast.get_color()
        text_color[3] = opacity
        window_name = [None] * (50)
        (window_name := "##TOAST%d" % (i))
        set_next_window_bg_alpha(opacity)
        set_next_window_pos((vp_size[0] - NOTIFY_PADDING_X, vp_size[1] - NOTIFY_PADDING_Y - height), im.Cond.ALWAYS, (1.0, 1.0))
        begin(window_name, None, NOTIFY_TOAST_FLAGS)
        push_text_wrap_pos(vp_size[0] / 3.)
        was_title_rendered = False
        if not notify_null_or_empty(icon):
            text_colored(text_color, icon)
            was_title_rendered = True
        if not notify_null_or_empty(title):
            if not notify_null_or_empty(icon):
                same_line()
            text(title)
            was_title_rendered = True
        elif not notify_null_or_empty(default_title):
            if not notify_null_or_empty(icon):
                same_line()
            text(default_title)
            was_title_rendered = True
        if was_title_rendered  and  not notify_null_or_empty(content):
            set_cursor_pos_y(get_cursor_pos_y() + 5.)
        if not notify_null_or_empty(content):
            if was_title_rendered:
                separator()
            text(content)
        pop_text_wrap_pos()
        height = height + get_window_height() + NOTIFY_PADDING_MESSAGE_Y
        end()

def merge_icons_with_latest_font(font_size, FontDataOwnedByAtlas=False):
    """MergeIconsWithLatestFont()."""
    icons_ranges = [ICON_MIN_FA, ICON_MAX_FA, 0]
    icons_config = None  # TODO(autoport): ImFontConfig -- construct this state
    icons_config.merge_mode = True
    icons_config.pixel_snap_h = True
    icons_config.font_data_owned_by_atlas = FontDataOwnedByAtlas
# TODO(autoport): hand-translate (the rules mangled this line):     get_io().fonts.add_font_from_memory_ttf((void*)fa_solid_900, sizeof(fa_solid_900), font_size, icons_config, icons_ranges)
    pass  # TODO(autoport): body of the line above