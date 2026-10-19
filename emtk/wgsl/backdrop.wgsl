// The frosted backdrop behind a modal window: a separable Gaussian over what was drawn
// before it.
//
// `emtk.wgpu_host.WgpuRenderer.render` splits a frame that carries a backdrop
// (`QuadPainter.backdrop`): the interface drawn *before* the modal window is rendered
// into a texture of its own, blurred here in two passes (horizontal, then vertical, at
// half resolution -- the blur hides the lost detail and costs a quarter of the taps), and
// composited back under the modal window and everything drawn after it.
//
// One shader does both jobs: `step` = (0, 0) copies the texture unchanged (the same tap
// read 2N+1 times, weights summing to one), any other step blurs along it. The
// vertex stage makes a triangle covering the target from the vertex index alone, so no
// buffer is bound.

struct Blur {
    // Texel offset between taps, in source texture coordinates (0-1).
    step  : vec2<f32>,
    // Gaussian sigma, in taps.
    sigma : f32,
    pad   : f32,
};

@group(0) @binding(0) var source  : texture_2d<f32>;
@group(0) @binding(1) var linear_sampler : sampler;
@group(0) @binding(2) var<uniform> blur : Blur;

struct BlurOut {
    @builtin(position) clip : vec4<f32>,
    @location(0) uv         : vec2<f32>,
};

@vertex
fn vs_fullscreen(@builtin(vertex_index) index : u32) -> BlurOut {
    // (0,0) (2,0) (0,2): one triangle that covers the viewport.
    let corner = vec2<f32>(f32((index << 1u) & 2u), f32(index & 2u));
    var out : BlurOut;
    out.clip = vec4<f32>(corner * 2.0 - 1.0, 0.0, 1.0);
    out.uv = vec2<f32>(corner.x, 1.0 - corner.y);
    return out;
}

const TAPS : i32 = 12;

@fragment
fn fs_blur(in : BlurOut) -> @location(0) vec4<f32> {
    var sum = vec4<f32>(0.0);
    var weights = 0.0;
    let s = max(blur.sigma, 0.5);
    for (var i : i32 = -TAPS; i <= TAPS; i = i + 1) {
        let x = f32(i);
        let w = exp(-0.5 * x * x / (s * s));
        sum = sum + w * textureSampleLevel(source, linear_sampler, in.uv + blur.step * x, 0.0);
        weights = weights + w;
    }
    return sum / weights;
}
