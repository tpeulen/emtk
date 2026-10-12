"""The texture caches are bounded in pixels, not only in entries.

A documentation sweep left ~1900 live textures holding ~9 million texels. The bulk was
the math cache: 256 display equations, each ~900 px wide, which a count bound lets grow
to tens of megabytes. Both caches now also evict least-recently-used entries past a
texel budget.
"""

from emtk import mathtext
from emtk.texture import ImageTextureCache, Texture


def _wide(width=400, height=100):
    return Texture(width, height)


def test_math_cache_evicts_oldest_past_its_texel_budget():
    cache = mathtext.MathTextureCache(maxsize=1000, max_texels=100_000)
    key = lambda i: (f"f{i}", (0, 0, 0, 255), 14.0, 144)
    for i in range(10):
        cache.put(*key(i), _wide())            # 40 000 texels each
    assert cache.texels <= 100_000
    assert len(cache._cache) == 2
    assert cache.get(*key(0)) is None          # the oldest went first
    assert cache.get(*key(9)) is not None      # the newest stays


def test_math_cache_keeps_a_lone_oversized_entry():
    cache = mathtext.MathTextureCache(max_texels=1_000)
    big = _wide()
    cache.put("big", (0, 0, 0, 255), 14.0, 144, big)
    assert cache.get("big", (0, 0, 0, 255), 14.0, 144) is big      # the caller is about to draw it


def test_a_cache_hit_protects_an_entry_from_eviction():
    key = lambda name: (name, (0, 0, 0, 255), 14.0, 144)
    cache = mathtext.MathTextureCache(max_texels=300)               # room for three 100-texel entries
    for name in "abc":
        cache.put(*key(name), Texture(10, 10))
    assert cache.get(*key("a")) is not None                         # a is now the newest
    cache.put(*key("d"), Texture(10, 10))
    assert cache.get(*key("b")) is None                             # b was the oldest
    assert cache.get(*key("a")) is not None


def test_math_cache_texels_follow_clear_and_replacement():
    cache = mathtext.MathTextureCache()
    cache.put("x", (0, 0, 0, 255), 14.0, 144, _wide(10, 10))
    cache.put("x", (0, 0, 0, 255), 14.0, 144, _wide(20, 10))
    assert cache.texels == 200
    cache.clear()
    assert cache.texels == 0


def test_the_default_math_budget_bounds_a_sweep_of_display_equations():
    cache = mathtext.MathTextureCache()
    for i in range(256):
        cache.put(f"f{i}", (0, 0, 0, 255), 14.0, 144, _wide(900, 100))
    assert cache.texels <= mathtext.DEFAULT_MAX_TEXELS
    assert cache.texels < 256 * 900 * 100 / 5


def test_image_cache_evicts_past_its_texel_budget(tmp_path):
    cache = ImageTextureCache(maxsize=100, max_texels=250_000)
    paths = []
    for i in range(6):
        p = tmp_path / f"{i}.png"
        p.write_bytes(b"x")
        paths.append(p)
        cache.put(p, "linear", Texture(300, 300))           # 90 000 texels each
    assert cache.texels <= 250_000
    assert cache.get(paths[0], "linear") is None
    assert cache.get(paths[-1], "linear") is not None
