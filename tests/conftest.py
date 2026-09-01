"""Shared fixtures.

The one thing this file exists for: **cmtk's tests run without Qt.**

cmtk has no dependencies -- that is its claim and most of its point -- and a
suite that cannot be run without a toolkit installed quietly makes the claim
untrue. Two separate things used to break it:

* ``pytest-qt``, if it happens to be installed in the environment without a
  Qt binding, refuses to let pytest *start at all*. cmtk does not use
  pytest-qt, so it is switched off in ``pyproject.toml``'s ``addopts``, and
  the fixture it provided is replaced by :func:`qt_app` below.
* the Qt painter test asked for pytest-qt's ``qapp`` fixture, which without
  the plugin is not a skip but a collection **error**.

An optional backend is allowed to be untested on a machine that cannot run
it. It is not allowed to stop everything else from being tested.
"""
from __future__ import annotations

import pytest


@pytest.fixture(scope="session")
def qt_app():
    """A Qt application for the tests that exercise the Qt painter.

    Skips -- not errors -- when no Qt binding is installed, which is the
    normal state for a cmtk checkout. Replaces pytest-qt's ``qapp`` so that
    testing the optional Qt backend needs Qt, and nothing else does.
    """
    qtwidgets = pytest.importorskip(
        "qtpy.QtWidgets", exc_type=ImportError,
        reason="the Qt painter needs a Qt binding (pip install qtpy PySide6)")
    app = qtwidgets.QApplication.instance()
    if app is None:
        # never destroyed: Qt does not support a second QApplication in one
        # process, so the session shares this one
        app = qtwidgets.QApplication([])
    return app
