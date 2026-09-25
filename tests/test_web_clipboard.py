"""Copy, cut and paste in a page: boot.js's clipboard block and WebPage's half.

A page cannot read the clipboard synchronously, so ``boot.js`` does not send
Cmd/Ctrl+C/X/V as keys; the browser's default raises ``copy``/``cut``/
``paste``, and the block forwards those with their text. This runs that very
block under node against stand-in events (the pattern of test_web_drop.py),
then drives :class:`emtk.web.page.WebPage` with an immediate-mode app.
"""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess

import pytest

from emtk import keys
from emtk.web import serve

WEB = pathlib.Path(serve.__file__).parent

HARNESS = r"""
%(block)s

const calls = [];
const listeners = {};
const doc = { addEventListener: (name, fn) => { listeners[name] = fn; } };
const page = {
  copy: (cut) => { calls.push(["copy", cut]); return cut ? "cut text" : undefined; },
  paste: (text) => { calls.push(["paste", text]); return true; },
};
let redraws = 0;
const isForm = (el) => Boolean(el && el.tagName === "INPUT");
const divert = forwardClipboard(doc, page, () => { redraws += 1; }, isForm);
Object.defineProperty(globalThis, "navigator", { value: { platform: %(platform)s }, configurable: true });

function clipEvent(target, text) {
  const store = {};
  return {
    target, prevented: false, store,
    clipboardData: { setData: (t, v) => { store[t] = v; }, getData: () => text },
    preventDefault() { this.prevented = true; },
  };
}
const out = {};
out.mac = isMacClient({ platform: "MacIntel" });
out.macUA = isMacClient({ userAgentData: { platform: "macOS" } });
out.linux = isMacClient({ platform: "Linux x86_64" });
const key = (k, o) => Object.assign({ key: k, metaKey: false, ctrlKey: false, altKey: false }, o);
out.cmdV = clipboardShortcut(key("v", { metaKey: true }), true);
out.ctrlVonMac = clipboardShortcut(key("v", { ctrlKey: true }), true);
out.ctrlC = clipboardShortcut(key("C", { ctrlKey: true, shiftKey: true }), false);
out.ctrlA = clipboardShortcut(key("a", { ctrlKey: true }), false);

const copy = clipEvent({ tagName: "CANVAS" });
listeners.copy(copy);
out.copyPrevented = copy.prevented;
const cut = clipEvent({ tagName: "CANVAS" });
listeners.cut(cut);
out.cut = [cut.prevented, cut.store["text/plain"]];
const paste = clipEvent({ tagName: "CANVAS" }, "pasted!");
listeners.paste(paste);
out.pastePrevented = paste.prevented;
const inForm = clipEvent({ tagName: "INPUT" }, "not ours");
listeners.paste(inForm);
out.formPrevented = inForm.prevented;

// A diverted key with no clipboard event after it is delivered plain.
let delivered = 0;
out.diverted = divert(key("v", { metaKey: %(mac)s, ctrlKey: %(pc)s }), () => { delivered += 1; });
out.plain = divert(key("a", { metaKey: true, ctrlKey: true }), () => { delivered += 1; });
setTimeout(() => {
  // ...and one the paste event answered is not delivered twice.
  divert(key("v", { metaKey: %(mac)s, ctrlKey: %(pc)s }), () => { delivered += 10; });
  listeners.paste(clipEvent({ tagName: "CANVAS" }, "x"));
  setTimeout(() => {
    out.delivered = delivered;
    out.calls = calls;
    out.redraws = redraws;
    console.log(JSON.stringify(out));
  }, 5);
}, 5);
"""


def _block() -> str:
    text = (WEB / "boot.js").read_text(encoding="utf-8")
    match = re.search(r"// <clipboard>.*?// </clipboard>", text, re.S)
    assert match, "boot.js lost its clipboard block"
    return match.group(0)


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
@pytest.mark.parametrize("mac", [True, False], ids=["mac", "pc"])
def test_boot_forwards_the_clipboard_events(tmp_path, mac):
    script = tmp_path / "clip.js"
    script.write_text(HARNESS % {
        "block": _block(), "platform": json.dumps("MacIntel" if mac else "Win32"),
        "mac": json.dumps(mac), "pc": json.dumps(not mac)})
    out = json.loads(subprocess.run(["node", str(script)], capture_output=True, text=True,
                                    check=True, timeout=60).stdout)
    assert out["mac"] and out["macUA"] and not out["linux"]
    assert out["cmdV"] == "v" and out["ctrlVonMac"] is None
    assert out["ctrlC"] == "c" and out["ctrlA"] is None
    assert out["copyPrevented"] is False, "nothing copied: the browser's copy stands"
    assert out["cut"] == [True, "cut text"]
    assert out["pastePrevented"] is True
    assert out["formPrevented"] is False, "a paste into a real <input> is left alone"
    assert out["diverted"] is True and out["plain"] is False
    assert out["delivered"] == 1, "unanswered: delivered once; answered: not at all"
    assert ["paste", "pasted!"] in out["calls"]
    assert ["paste", "not ours"] not in out["calls"]


# -- WebPage's half ------------------------------------------------------- #
class _Canvas:
    width, height, clientWidth = 400, 80, 400

    def getContext(self, _kind):          # noqa: N802 - the DOM's spelling
        raise RuntimeError("no GPU in this test")


def _page(value):
    import emtk
    from emtk.app import ControlSurface, ImApp
    from emtk.testing import RecordingPainter
    from emtk.web.page import WebPage

    state = {"value": value, "box": None}

    def gui():
        from emtk.im_core import get_current_context

        emtk.begin("w", (0, 0, 400, 80))
        _c, state["value"] = emtk.input_text("##f", state["value"])
        state["box"] = get_current_context().get_item_rect()
        emtk.end()

    app = ImApp(gui)
    app.io.wall_clock = False

    class Surface(ControlSurface):
        def attach(self, *a):
            pass

        def render(self, _view):
            self.control.draw(RecordingPainter(), 0, 0, 400, 80)

    surface = Surface(app)
    page = WebPage(_Canvas(), surface, device=object(), format="bgra8unorm")
    page.draw = lambda: surface.render(None)
    return page, app, state


@pytest.mark.parametrize("mac", [True, False], ids=["mac", "pc"])
def test_a_page_copies_cuts_and_pastes_through_the_events(mac):
    keys.set_mac_behaviors(mac)
    try:
        page, app, state = _page("hello")
        page.draw()
        x, y, _w, _h = state["box"]
        page.press(x + 300, y + 4, 0)
        page.release(x + 300, y + 4, 0)
        page.draw()
        page.key("a", "a", ctrl=not mac, meta=mac)     # select all, typed nothing
        page.draw()
        assert state["value"] == "hello"
        assert page.copy() == "hello"
        assert page.copy(cut=True) == "hello" and state["value"] == ""
        assert page.paste("from the dom") is True
        assert state["value"] == "from the dom"
        assert page.copy() is None, "nothing selected: nothing copied"
    finally:
        keys.set_mac_behaviors(None)


def test_a_paste_nobody_takes_is_not_kept_for_later():
    from emtk import clipboard

    page, _app, _state = _page("x")        # the field is not focused
    page.draw()
    assert page.paste("stray") is False
    assert not clipboard.holding()
