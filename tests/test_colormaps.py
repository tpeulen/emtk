"""emtk.colormaps: the tables, the matplotlib lookup semantics, colour parsing."""

from __future__ import annotations

import pathlib

import pytest

from emtk import colormaps

np = pytest.importorskip("numpy")


def test_the_tables_ship_and_carry_their_licences():
    root = pathlib.Path(colormaps.__file__).resolve().parent
    assert (root / "colormaps.json").is_file()
    assert (root.parent / "licenses" / "colormaps.txt").is_file()
    for name in ("viridis", "magma", "inferno", "plasma", "cividis", "turbo", "gray",
                 "CET-L4", "CET-L9", "CET-L19", "hot", "RdBu", "coolwarm", "tab10"):
        assert colormaps.has(name), name
        assert colormaps.has(name + "_r"), name


def test_unknown_names_raise_keyerror():
    assert not colormaps.has("no-such-map")
    with pytest.raises(KeyError):
        colormaps.get("no-such-map")


@pytest.mark.parametrize(
    "name", ["viridis", "magma", "inferno", "gray", "grey", "hot", "RdBu_r", "coolwarm",
             "jet", "turbo", "tab10", "spring", "pink"])
def test_lookup_matches_matplotlib(name):
    mpl = pytest.importorskip("matplotlib")
    rng = np.random.default_rng(7)
    x = np.concatenate([rng.uniform(-0.2, 1.2, 500), [0.0, 0.5, 1.0, np.nan]])
    ours = colormaps.get(name)(x)
    theirs = mpl.colormaps[name](x)
    # The tables are stored at 8 bits, so one quantisation step is the tolerance.
    assert np.max(np.abs(ours - theirs)) <= 1.0 / 255.0 + 1e-9
    assert ours.shape == (x.size, 4)


def test_cividis_is_pyqtgraphs_table():
    """cividis exists in two published versions; emtk ships pyqtgraph's.

    matplotlib's table differs from it by up to 0.09 in a channel. ndXplorer
    has always shown pyqtgraph's, so that is the one kept -- a picture drawn
    with matplotlib's cividis is *expected* to differ slightly.
    """
    assert colormaps.lookup_table("cividis", 256)[0] == (0, 32, 77, 255)


def test_integers_index_the_table_and_nan_is_transparent():
    cmap = colormaps.get("viridis")
    assert cmap(0) == cmap(0.0)
    assert cmap(255) == cmap(1.0)
    assert cmap(np.int64(3)) == cmap(3)
    assert cmap(float("nan")) == (0.0, 0.0, 0.0, 0.0)
    assert np.array_equal(cmap(np.array([0, 255])), np.array([cmap(0), cmap(255)]))


def test_reversed_alpha_and_bytes():
    cmap = colormaps.get("magma")
    assert cmap.reversed()(0.0) == cmap(1.0)
    assert cmap.reversed().reversed() == cmap
    assert cmap(0.3, alpha=0.25)[3] == 0.25
    assert cmap(np.array([0.3]), bytes=True).dtype == np.uint8


def test_lookup_table_is_bytes_and_honours_n():
    lut = colormaps.lookup_table("viridis", 16)
    assert len(lut) == 16 and lut[0] == (68, 1, 84, 255)
    assert len(colormaps.lookup_table("tab10", 256)) == 10


def test_works_without_numpy(monkeypatch):
    monkeypatch.setattr(colormaps, "_numpy", lambda: None)
    cmap = colormaps.Colormap("inferno")
    rows = cmap([0.0, 0.5, float("nan")])
    assert rows[0] == cmap(0.0) and rows[2] == (0.0, 0.0, 0.0, 0.0)


@pytest.mark.parametrize(
    "colour", ["steelblue", "k", "r", "C0", "C7", "tab:orange", "#abc", "#1f77b4",
               "#1f77b480", "0.5", "none", (0.1, 0.2, 0.3), (0.1, 0.2, 0.3, 0.4)])
def test_to_rgba_matches_matplotlib(colour):
    mcolors = pytest.importorskip("matplotlib.colors")
    assert np.allclose(colormaps.to_rgba(colour), mcolors.to_rgba(colour), atol=1 / 255)


def test_to_rgba_extensions_and_errors():
    assert colormaps.to_rgba((255, 0, 0)) == (1.0, 0.0, 0.0, 1.0)
    assert colormaps.to_rgba("red", alpha=0.5) == (1.0, 0.0, 0.0, 0.5)
    assert colormaps.to_hex("C0") == "#1f77b4"
    assert colormaps.to_hex((1.0, 0.0, 0.0, 0.5), keep_alpha=True) == "#ff000080"
    assert colormaps.to_rgba_bytes("white") == (255, 255, 255, 255)
    for bad in ("notacolour", (1, 2), "1.5", (2.0, 0.0, 0.0)):
        with pytest.raises(ValueError):
            colormaps.to_rgba(bad)
