"""l2d_file_dialog: auto-ported from L2DFileDialog.h
(upstream, MIT) by tools/autoport.py.

A mechanical port of Dear ImGui C++ to emtk. Lines flagged
TODO(autoport) need a hand; everything else is the C++ under the
naming rules in tools/autoport.py.
"""
import math

import emtk.im as im

file_dialog_open = False

from enum import IntFlag

class FileDialogType(IntFlag):
    """FileDialogType, from L2DFileDialog.h."""
    open_file = 0
    select_folder = 1

class FileDialogSortOrder(IntFlag):
    """FileDialogSortOrder, from L2DFileDialog.h."""
    up = 0
    down = 1
    none = 2

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def show_file_dialog(open, buffer, buffer_size, type=FileDialogType.op
pass
def catch(_arg0):
    """catch()."""
    pass

def sort(begin, end, b):
    """sort()."""
    if file_name_sort_order == FileDialogSortOrder.down:
        return a.path().filename().string() > b.path().filename().string()
    else:
        return a.path().filename().string() < b.path().filename().string()

def sort(begin, end, b):
    """sort()."""
    if size_sort_order == FileDialogSortOrder.down:
        return a.file_size() > b.file_size()
    else:
        return a.file_size() < b.file_size()

def sort(begin, end, b):
    """sort()."""
    if type_sort_order == FileDialogSortOrder.down:
        return a.path().extension().string() > b.path().extension().string()
    else:
        return a.path().extension().string() < b.path().extension().string()

def sort(begin, end, b):
    """sort()."""
    if date_sort_order == FileDialogSortOrder.down:
        return a.last_write_time() > b.last_write_time()
    else:
        return a.last_write_time() < b.last_write_time()

def show_file_dialog_s(open, buffer, type=FileDialogType.open_file):
    """ShowFileDialog_s()."""
    show_file_dialog(open, buffer, 500, type)