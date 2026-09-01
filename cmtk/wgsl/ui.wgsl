// cmtk's interface, as quads. One pipeline, one draw call.
//
// This is the toolkit's shader, not any one consumer's. It reads what
// `cmtk.quad_painter.QuadPainter` emits and draws the whole interface --
// panels, menus, text, images -- in a single pass. `cmtk.wgpu_host` is the
// host built on it, and an application embedding cmtk's interface in its own
// render pass loads this same file through `cmtk.wgsl`. That is the point of
// it living here: two copies of one pipeline's shader are two things to keep
// in step, and they do not stay in step.
//
// Why quads rather than a rasterised image
// ----------------------------------------
// The panel, the sequence strip, the menus and the transport used to be
// rasterised on the CPU into an image the size of the window and uploaded every
// time it changed -- `9.6 ms of a 21 ms frame` on a quarter-million beads, which
// is why a timer existed to let the panel go deliberately *stale* rather than
// repaint it when it changed. A frame of chrome is a few hundred rectangles and
// a few thousand glyphs; sending those as vertices costs kilobytes and no CPU
// rasterisation at all.
//
// One pipeline draws all of it. A rectangle samples the atlas's opaque block, so
// there is no "is this text" branch and no second pipeline -- the difference
// between a panel background and a letter is which texels the quad points at.
//
// **Image quads** point at the *image* atlas instead, and say so by carrying a
// negative `u`: an image's u is `-(1 + texel_u / atlas2.w)` in [-2, -1], while
// every glyph/rect u is a texel coordinate >= 0. The fragment tests `u < -0.5`
// and selects, which keeps one draw call (images stay in the chrome's draw
// order -- text after an image lands *on* it), one vertex format, and one
// pipeline. The image atlas is premultiplied RGBA, multiplied by the vertex
// colour (tint), composited like everything else here. See
// `cmtk.gpu_atlas.image_u`, which is the encoder for this decoder.
//
// Clipping travels per-vertex rather than as a scissor rect, because the whole
// chrome is one draw call and a scissor would split it. Menus are the only
// caller, and a menu taller than its box scrolls inside it.
//
// Output is **premultiplied**, matching the blend state the chrome has always
// been composited with. Straight alpha here darkens every antialiased glyph
// edge against a light background -- which is invisible on the dark panel and
// obvious the moment the background is white.
//
// The bindings are **group 1**, and group 0 is deliberately left alone: an
// application that embeds this typically prepends a shared prelude declaring
// group 0 to every shader it loads, and a file that claimed group 0 could not
// be that file too. `cmtk.wgpu_host` binds an empty group 0 -- the cost of one
// shader instead of two.

struct UiOut {
    @builtin(position) clip   : vec4<f32>,
    @location(0) uv           : vec2<f32>,
    @location(1) colour       : vec4<f32>,
    // The clip rectangle, in pixels: (x0, y0, x1, y1).
    @location(2) box          : vec4<f32>,
    // Where this fragment is, in the same pixel space, so the fragment stage
    // can test it against `box` without recovering it from `clip`.
    @location(3) pixel        : vec2<f32>,
};

struct UiUniforms {
    // Viewport size in pixels, and the two atlases' sizes in texels.
    viewport : vec2<f32>,
    atlas    : vec2<f32>,
    atlas2   : vec2<f32>,
};

@group(1) @binding(0) var<uniform> ui : UiUniforms;
@group(1) @binding(1) var uiTex : texture_2d<f32>;
@group(1) @binding(2) var uiSampler : sampler;
@group(1) @binding(3) var uiTex2 : texture_2d<f32>;
@group(1) @binding(4) var uiSampler2 : sampler;

@vertex
fn vs_ui(
    @location(0) position : vec2<f32>,
    @location(1) uv       : vec2<f32>,
    @location(2) colour   : vec4<f32>,
    @location(3) box      : vec4<f32>,
) -> UiOut {
    var out : UiOut;
    // Pixels to clip space. The chrome lays itself out y-down from the top
    // left, as every 2-D layout does; clip space is y-up.
    let ndc = vec2<f32>(
         position.x / ui.viewport.x * 2.0 - 1.0,
         1.0 - position.y / ui.viewport.y * 2.0,
    );
    out.clip = vec4<f32>(ndc, 0.0, 1.0);
    // Raw: glyph uvs normalise in the fragment (they need `ui.atlas`),
    // image uvs decode there instead (they need `ui.atlas2`).
    out.uv = uv;
    out.colour = colour;
    out.box = box;
    out.pixel = position;
    return out;
}

@fragment
fn fs_ui(in : UiOut) -> @location(0) vec4<f32> {
    if (in.pixel.x < in.box.x || in.pixel.x > in.box.z ||
        in.pixel.y < in.box.y || in.pixel.y > in.box.w) {
        discard;
    }
    if (in.uv.x < -0.5) {
        // An image quad: u decodes to a fraction of the image atlas, v is
        // a texel row of it. Premultiplied in, tinted, premultiplied out.
        // `textureSampleLevel` because a varying branch is non-uniform
        // control flow and the implicit-LOD `textureSample` may not enter
        // one; these atlases have no mips, so level 0 is exact.
        let iuv = vec2<f32>(-(in.uv.x) - 1.0, in.uv.y / ui.atlas2.y);
        let texel = textureSampleLevel(uiTex2, uiSampler2, iuv, 0.0);
        return texel * in.colour;
    }
    // The atlas stores coverage in alpha; its colour channels are white where
    // there is ink, so sampling alpha alone is what carries the glyph and lets
    // the vertex colour decide what it looks like.
    let coverage = textureSampleLevel(
        uiTex, uiSampler, in.uv / ui.atlas, 0.0).a;
    let alpha = in.colour.a * coverage;
    return vec4<f32>(in.colour.rgb * alpha, alpha);
}
