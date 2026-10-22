"""The browser build: what goes into a page, and what the page is told.

``python -m emtk.web.serve`` is pure Python up to the moment a browser opens
the result, so the whole build is checked here: the archive's contents (the
app, emtk itself with its *data*, extra packages, exclusions, stamped files),
the wheels, and the configuration ``boot.js`` reads.
"""
from __future__ import annotations

import functools
import hashlib
import http.server
import json
import threading
import urllib.request
import pathlib
import re
import zipfile

import pytest

from emtk.web import serve
from emtk.web.serve import Bundle, build, bundle_from_args, pack_zip, parser, resolve_package

WEB = pathlib.Path(serve.__file__).parent


def _app(tmp_path: pathlib.Path, name: str = "demoapp") -> pathlib.Path:
    """A tiny app package on disk: code, data, a desktop-only subpackage."""
    pkg = tmp_path / "src" / name
    (pkg / "qt").mkdir(parents=True)
    (pkg / "__pycache__").mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "main.py").write_text("def make_app():\n    return None\n")
    (pkg / "table.csv").write_text("a,b\n1,2\n")
    (pkg / "big.bin").write_bytes(b"\0" * 10)
    (pkg / "qt" / "__init__.py").write_text("import qtpy\n")
    (pkg / "__pycache__" / "main.cpython-312.pyc").write_bytes(b"x")
    return pkg


def _config(site: pathlib.Path) -> dict:
    text = (site / "index.html").read_text(encoding="utf-8")
    payload = re.search(r'<script id="emtk-config" type="application/json">(.*?)</script>',
                        text, re.S).group(1)
    return json.loads(payload.replace("<\\/", "</"))


def test_the_archive_holds_the_app_and_emtk_with_its_data(tmp_path):
    pkg = _app(tmp_path)
    names = zipfile.ZipFile(pack_zip(Bundle(app="demoapp.main:make_app", packages=[pkg]),
                                     tmp_path / "app.zip")).namelist()
    assert "demoapp/__init__.py" in names and "demoapp/main.py" in names
    assert "demoapp/table.csv" in names, "an app's data ships with it"
    assert "demoapp/big.bin" not in names, "only the listed file types ship"
    assert not [n for n in names if "__pycache__" in n]
    # emtk is the host, and it is not only code: without the atlas a page
    # imports cleanly and then cannot measure a single label; without the
    # shader it cannot draw one.
    for needed in ("emtk/__init__.py", "emtk/app.py", "emtk/web/page.py",
                   "emtk/gpu/browser.py", "emtk/atlas/chrome.json",
                   "emtk/atlas/chrome.png", "emtk/wgsl/ui.wgsl"):
        assert needed in names, f"{needed} is missing"


def test_exclusions_extra_packages_and_stamped_files(tmp_path):
    pkg = _app(tmp_path)
    dep = tmp_path / "vendor" / "helper.py"
    dep.parent.mkdir()
    dep.write_text("X = 1\n")
    bundle = Bundle(app="demoapp.main:make_app", packages=[pkg], extra_packages=[dep],
                    exclude=("demoapp/qt/",),
                    extra_files={"demoapp/_version.py": b"__version__ = '1.2'\n"})
    archive = zipfile.ZipFile(pack_zip(bundle, tmp_path / "app.zip"))
    names = archive.namelist()
    assert not [n for n in names if n.startswith("demoapp/qt/")], "a desktop-only subpackage shipped"
    assert "helper.py" in names, "a single-module dependency lands at the root"
    assert archive.read("demoapp/_version.py") == b"__version__ = '1.2'\n"
    assert len(names) == len(set(names)), "a file was packed twice"


def test_a_package_is_found_by_import_name():
    assert resolve_package("emtk") == pathlib.Path(serve.__file__).resolve().parents[1]
    with pytest.raises(FileNotFoundError):
        resolve_package("no_such_package_for_emtk_tests")


def test_the_app_defaults_to_its_own_top_level_package(tmp_path):
    names = zipfile.ZipFile(pack_zip(Bundle(app="emtk.implot_demo:make_app"),
                                     tmp_path / "a.zip")).namelist()
    assert "emtk/implot_demo.py" in names


def test_an_app_spec_must_name_a_factory():
    with pytest.raises(ValueError):
        Bundle(app="emtk.implot_demo")


def test_the_site_carries_the_config_boot_js_reads(tmp_path):
    pkg = _app(tmp_path)
    wheel = tmp_path / "tttrlib-0.0.0-cp312-cp312-pyodide_2024_0_wasm32.whl"
    wheel.write_bytes(b"PK\x05\x06" + b"\0" * 18)
    args = parser().parse_args([
        "--app", "demoapp.main:make_app", "--package", str(pkg),
        "--pyodide-packages", "numpy,scipy", "--pyodide-packages", "pandas",
        "--wheels", str(tmp_path / "*.whl"), "--title", "Demo </script> app",
    ])
    site = build(bundle_from_args(args), tmp_path / "site")
    config = _config(site)
    assert config["app"] == "demoapp.main:make_app"
    # The defaults stay, in order, and nothing is asked for twice.
    assert config["pyodide_packages"] == ["numpy", "Pillow", "scipy", "pandas"]
    assert config["wheels"] == [f"wheels/{wheel.name}"]
    assert (site / "wheels" / wheel.name).is_file()
    assert (site / config["archive"].split("?")[0]).is_file()
    assert (site / "boot.js").read_text() == (WEB / "boot.js").read_text()
    html = (site / "index.html").read_text()
    assert "<title>Demo &lt;/script&gt; app</title>" in html
    assert '<meta name="emtk-app" content="demoapp.main:make_app">' in html
    assert serve.DEFAULT_PYODIDE_URL in html


def _digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def test_the_archive_and_loader_urls_name_their_bytes(tmp_path):
    """A CDN caches ``app.zip`` and ``boot.js`` for hours while ``index.html``
    is revalidated; without the content in the URL a redeploy runs the new
    page on the old bundle.
    """
    pkg = _app(tmp_path)
    bundle = Bundle(app="demoapp.main:make_app", packages=[pkg])
    site = build(bundle, tmp_path / "site")
    archive = _config(site)["archive"]
    assert archive == f"app.zip?v={_digest(site / 'app.zip')}"
    page = (site / "index.html").read_text()
    assert f'<script src="boot.js?v={_digest(site / "boot.js")}"></script>' in page
    assert "{{" not in page, "a placeholder was left unfilled"

    (pkg / "main.py").write_text("def make_app():\n    return 1\n")
    rebuilt = _config(build(bundle, site))["archive"]
    assert rebuilt != archive, "a changed bundle kept its URL"
    assert rebuilt == f"app.zip?v={_digest(site / 'app.zip')}"


def test_the_dev_server_resolves_a_versioned_url(tmp_path):
    site = build(Bundle(app="demoapp.main:make_app", packages=[_app(tmp_path)]),
                 tmp_path / "site")
    archive = _config(site)["archive"]
    handler = functools.partial(serve.Handler, directory=str(site))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}/"
        with urllib.request.urlopen(base + archive, timeout=5) as response:
            assert response.read() == (site / "app.zip").read_bytes()
        boot = re.search(r'<script src="(boot\.js\?v=[0-9a-f]{12})"',
                         (site / "index.html").read_text()).group(1)
        with urllib.request.urlopen(base + boot, timeout=5) as response:
            assert response.read() == (site / "boot.js").read_bytes()
    finally:
        server.shutdown()
        server.server_close()


def test_a_local_pyodide_replaces_the_cdn(tmp_path):
    local = tmp_path / "pyodide-dist"
    local.mkdir()
    (local / "pyodide.js").write_text("// stub")
    site = build(Bundle(app="emtk.implot_demo:make_app"), tmp_path / "site", pyodide=local)
    html = (site / "index.html").read_text()
    assert 'src="pyodide/pyodide.js"' in html and serve.DEFAULT_PYODIDE_URL not in html
    assert (site / "pyodide" / "pyodide.js").is_file()


def test_a_missing_wheel_fails_the_build(tmp_path):
    args = parser().parse_args(["--app", "emtk.implot_demo:make_app",
                                "--wheels", str(tmp_path / "nothing*.whl")])
    with pytest.raises(FileNotFoundError):
        bundle_from_args(args)


def test_an_app_wrapper_presets_a_bundle(tmp_path):
    """What an app's own ``serve`` module does: a base bundle, CLI on top."""
    base = Bundle(app="emtk.implot_demo:make_app", title="Preset", ready_message="drawn")
    bundle = bundle_from_args(parser().parse_args(["--extra-packages", "json"]), base)
    assert bundle.app == base.app and bundle.title == "Preset"
    assert bundle.extra_packages == ["json"]
    assert base.extra_packages == [], "the preset was mutated"
    site = build(bundle, tmp_path / "s")
    assert _config(site)["ready_message"] == "drawn"


def test_the_loader_draws_nothing():
    """``boot.js`` is a loader and an event forwarder. A renderer in
    JavaScript would be a second implementation of every frame.
    """
    text = (WEB / "boot.js").read_text(encoding="utf-8")
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//"))
    for forbidden in ("createRenderPipeline", "createBuffer", "beginRenderPass"):
        assert forbidden not in code, f"boot.js calls {forbidden}"
    # And it hands the DOM's own values to Python rather than deciding.
    for handler in ("page.press", "page.move", "page.release", "page.wheel",
                    "page.key", "page.open_path", "page.resize", "page.animating"):
        assert handler in text, f"boot.js no longer forwards {handler}"
    assert "mountNativeFS" in text


def test_the_server_sends_no_store_and_isolation_only_when_asked():
    sent = []

    class _Probe(serve.Handler):
        def __init__(self):  # no socket
            pass

        def send_header(self, key, value):
            sent.append((key, value))

    probe = _Probe()
    probe._headers_buffer = []
    probe.request_version = "HTTP/1.1"
    try:
        probe.end_headers()
    except Exception:  # noqa: BLE001 - flushing a socket that is not there
        pass
    assert ("Cache-Control", "no-store") in sent
    assert not [k for k, _ in sent if k.startswith("Cross-Origin")]
    assert serve.Handler.extensions_map[".wasm"] == "application/wasm"


def test_the_server_logs_a_frame_error_report_from_the_page(tmp_path, capsys):
    site = build(Bundle(app="demoapp.main:make_app", packages=[_app(tmp_path)]),
                 tmp_path / "site")
    handler = functools.partial(serve.Handler, directory=str(site))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}/"
        request = urllib.request.Request(
            base + serve.Handler.ERROR_REPORT_PATH, method="POST",
            data="RuntimeError: the panel died too".encode(), )
        with urllib.request.urlopen(request, timeout=5) as response:
            assert response.status == 204
        logged = capsys.readouterr().err
        assert "FRAME-ERROR-REPORT:" in logged
        assert "RuntimeError: the panel died too" in logged
    finally:
        server.shutdown()
        server.server_close()
