"""imspinner: auto-ported from imspinner.h
(upstream, MIT) by tools/autoport.py.

A mechanical port of Dear ImGui C++ to cmtk. Lines flagged
TODO(autoport) need a hand; everything else is the C++ under the
naming rules in tools/autoport.py.
"""
import math

import cmtk.im as im

IM_PI = math.pi

white = (1., 1., 1., 1.)
half_white = (1., 1., 1., 0.5)
red = (1., 0., 0., 1.)
PI_DIV_4 = IM_PI / 4.
PI_DIV_2 = IM_PI / 2.
PI_2 = IM_PI * 2.

from enum import IntFlag

class SpinnerTypeT(IntFlag):
    """SpinnerTypeT, from imspinner.h."""
    e_st_rainbow = 0
    e_st_angle = 1
    e_st_dots = 2
    e_st_ang = 3
    e_st_vdots = 4
    e_st_bounce_ball = 5
    e_st_eclipse = 6
    e_st_ingyang = 7
    e_st_barchartsine = 8
    e_st_count = 9

class ease_mode(IntFlag):
    """ease_mode, from imspinner.h."""
    e_ease_none = 0
    e_ease_inoutquad = 1
    e_ease_inoutexpo = 2
    e_ease_spring = 3
    e_ease_gravity = 4
    e_ease_infinity = 5
    e_ease_elastic = 6
    e_ease_sine = 7
    e_ease_damping = 8

class ImRect:
    """ImRect: axis-aligned rectangle, as the ImGuizmo family
    expects it. Corners are ``(x, y)`` tuples; min is inclusive,
    max exclusive -- the same convention as a clip rect."""
    def __init__(self, a=(0.0, 0.0), b=(0.0, 0.0)):
        self.min = a
        self.max = b

    def contains(self, p):
        return (self.min[0] <= p[0] < self.max[0]
                and self.min[1] <= p[1] < self.max[1])

    def get_center(self):
        return ((self.min[0] + self.max[0]) * 0.5,
                (self.min[1] + self.max[1]) * 0.5)

    def expand(self, amount):
        return ImRect((self.min[0] - amount, self.min[1] - amount),
                      (self.max[0] + amount, self.max[1] + amount))

def im_clamp(v, mn, mx):
    """ImClamp."""
    return max(mn, min(mx, v))

class SpinnerConfig:
    """SpinnerConfig, from imspinner.h."""

    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def __init__(self):
    pass
    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def set(self):
    pass
    def __init__2(self, args):
        """SpinnerConfig()."""
# TODO(autoport): hand-translate (the rules mangled this line):         self.template set(args...)
        pass  # TODO(autoport): body of the line above

def pi_div(d):
    """PI_DIV()."""
    return IM_PI / float(d)

def pi_2_div(d):
    """PI_2_DIV()."""
    return PI_2 / float(d)

def declprop(SpinnerType, SpinnerTypeT, Radius, _arg3, Speed, _arg5, Thickness, _arg7, Color, _arg9, BgColor, _arg11, AltColor, _arg13, Angle, _arg15, AngleMin, _arg17, AngleMax, _arg19, FloatPtr, float_ptr, Dots, _arg23, MiddleDots, _arg25, MinThickness, _arg27, Reverse, _arg29, Delta, _arg31, Mode, _arg33, label, radius, pos, size, centre, value):
    """DECLPROP()."""
    pass  # TODO(autoport): internal window state: ImGuiWindow *window = ImGui::GetCurrentWindow()
    if window.skip_items:
        return False, value
# TODO(autoport): hand-translate (the rules mangled this line):     ImGuiContext &g = *GImGui
    pass  # TODO(autoport): body of the line above
    style = g.style
    id = window.get_id(label)
    pass  # TODO(autoport): internal window state: pos = window->DC.CursorPos
    size = ((radius) * 2, (radius + style.frame_padding[1]) * 2)
    bb = ImRect(pos, (pos[0] + size[0], pos[1] + size[1]))
    im.item_size(bb, style.frame_padding[1])
    value = window.draw_list._CalcCircleAutoSegmentCount(radius)
    centre = bb.get_center()
    if not im.item_add(bb, id):
        return False, value
    return True, value

def path_stroke(draw_list, col, thickness, flags):
    """PathStroke()."""
    draw_list.path_stroke(col, thickness, flags)

def add_polyline(draw_list, points, num_points, col, thickness, flags):
    """AddPolyline()."""
    draw_list.add_polyline(points, num_points, col, thickness, flags)

def color_alpha(c, alpha):
    """color_alpha()."""
    c.value[3] = c.value[3] * alpha * im.get_style().alpha
    return c

def damped_spring(mass, stiffness, damping, time, a=PI_DIV_2, b=PI_DIV_2):
    """damped_spring()."""
    omega = math.sqrt(stiffness / mass)
    alpha = damping / (2 * mass)
    exponent = std.exp(-alpha * time)
    cosTerm = math.cos(omega * math.sqrt(1 - alpha * alpha) * time)
    result = exponent * cosTerm
# TODO(autoport): hand-translate (the rules mangled this line):     return ((result *= a) + b)
    pass  # TODO(autoport): body of the line above

def damped_gravity(limtime):
    """damped_gravity()."""
    time = 0.0
    initialHeight = 10.
    height = initialHeight
    velocity = 0.
    prtime = 0.0
    while height >= 0.0:
        if prtime >= limtime:
            return height / 10.
        time = time + 0.01
        prtime = prtime + 0.01
        height = initialHeight - 0.5 * 9.81 * time * time
        if height < 0.0:
            initialHeight = 0.0
            time = 0.0
    return 0.

def damped_trifolium(limtime, a=0., b=1.):
    """damped_trifolium()."""
    return a * math.sin(limtime) - b * math.sin(3 * limtime)

def damped_inoutelastic(t, amplitude, period):
    """damped_inoutelastic()."""
    if t == 0:
        return 0
    t = t * 2
    if t == 2:
        return 1
    s = None  # TODO(autoport): uninitialized float
    if amplitude < 1:
        amplitude = 1
        s = period / 4
    else:
        s = period / (2 * IM_PI) * std.asin(1 / amplitude)
    if t < 1:
        return -0.5 * ( amplitude * math.pow(2.0, 10.*(t-1.)) * math.sin((t-1.-s)*(2.*IM_PI)/period))
    return amplitude * math.pow(2.0, -10*(t-1)) * math.sin((t-1.-s)*(2.*IM_PI)/period) * 0.5 + 1.

def damped_infinity(t, a):
    """damped_infinity()."""
    return std.make_pair((a * math.cos(t)) / (1 + (math.pow(math.sin(t), 2.0))), (a * math.sin(t) * math.cos(t)) / (1 + (math.pow(math.sin(t), 2.0))))

def ease_inquad(time):
    """ease_inquad()."""
    return time * time

def ease_outquad(time):
    """ease_outquad()."""
    return time * (2. - time)

def ease_inoutquad(t):
    """ease_inoutquad()."""
    if t < 0.5:
        return 2 * t * t
    else:
        return -1 + (4 - 2 * t) * t

def ease_inoutquad(p):
    """ease_inoutquad()."""
    tr = max(math.sin(p[0]) - 0.5, 0.) * (p[1] * 0.5)
    return ease_inoutquad(tr)

def ease_outcubic(t):
    """ease_outcubic()."""
    ft = t - 1
    return ft * ft * ft + 1

def ease_inexpo(t):
    """ease_inexpo()."""
    return (0. if t == 0. else float(math.pow(2, 10 * (t - 1))))

def ease_inoutexpo(t):
    """ease_inoutexpo()."""
    if t == 0:
        return 0
    if t == 1:
        return 1
    if t < 0.5:
        return 0.5 * math.pow(2, (20 * t) - 10)
    return 0.5 * (2 - math.pow(2, -20 * t + 10))

def ease_inoutexpo(p):
    """ease_inoutexpo()."""
    tr = max(math.sin(p[0]) - 0.5, 0.) * (p[1] * 0.4)
    return ease_inoutexpo(tr) * (p[1] * 0.3)

def ease_spring(p):
    """ease_spring()."""
    return damped_spring(1, 10., 1.0, math.sin(math.fmod(p[0], p[1])), p[2], p[3])

def ease_gravity(p):
    """ease_gravity()."""
    return damped_gravity(p[0])

def ease_infinity(p):
    """ease_infinity()."""
    return damped_infinity(p[0], p[1]).second

def ease_inoutelastic(p):
    """ease_inoutelastic()."""
    return damped_inoutelastic(p[1], p[2], p[3])

def ease_sine(p):
    """ease_sine()."""
    return 0.5 * (1.0 - math.cos(p[0] * IM_PI))

def ease_damping(p):
    """ease_damping()."""
    A = 3.14 * 2
    ma = 5.0
    k = 2.1
    b = 0.09
    theta = 0.0
    w = math.sqrt(k / ma)
    t = math.fmod(*p, 25)
    x = A * std.exp(-b * t) * std.cos(w * t - theta)
    return x

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def ease(mode, args):
pass
# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_rainbow(label, radius, thickness, color, speed, ang_min=0.
pass
def circle(seg):
    """circle()."""
    a = a_min + (float(seg) / float(num_segments)) * (a_max - a_min)
    rspeed = a + t * speed
    return (math.cos(rspeed) * rb, math.sin(rspeed) * rb)

def spinner_rainbow_mix(label, radius, thickness, color, speed, ang_min=0., ang_max=PI_2, arcs=1, mode=0):
    """SpinnerRainbowMix()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    out_h = 0.0
    out_s = 0.0
    out_v = 0.0
    im.color_convert_rg_bto_hsv(color.value[0], color.value[1], color.value[2], out_h, out_s, out_v)
    for i in range(int(0), int(arcs)):
        rb = (radius / arcs) * (i + 1)
        start = abs(math.sin(im.get_time()) * (num_segments - 5))
        a_min = max(ang_min, PI_2 * (float(start)) / float(num_segments) + (IM_PI / arcs) * i)
        a_max = min(ang_max, PI_2 * (float(num_segments) + 3 * (i + 1)) / float(num_segments))
        koeff = ((1.1 - 1. / (i+1)) if mode else 1.)
        c = ImColor.HSV(out_h + i * (1. / arcs), out_s, out_v)
# TODO(autoport): hand-translate (the rules mangled this line):         circle([&] (int i)
        pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):         a = a_min + (float(i) / float(num_segments)) * (a_max - a_min); const float rspeed = a + im.get_time() * speed * koeff; return (math.cos(rspeed) * rb, math.sin(rspeed) * rb);
        pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):         , color_alpha(c, 1.), thickness)
        pass  # TODO(autoport): body of the line above

def circle(i):
    """circle()."""
    a = a_min + (float(i) / float(num_segments)) * (a_max - a_min)
    rspeed = a + im.get_time() * speed * koeff
    return (math.cos(rspeed) * rb, math.sin(rspeed) * rb)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_rotating_heart(label, radius, thickness, color, speed, ang
pass
def circle(i):
    """circle()."""
    a = PI_2 * i / num_segments
    x = (scale(16) * math.pow(math.sin(a), 3))
    y = -1. * (scale(13) * math.cos(a) - scale(5) * math.cos(2 * a) - scale(2) * math.cos(3 * a) - math.cos(4 * a))
    return rotate((x, y), ang_min)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_ang(label, radius, thickness, color=white, bg=white, speed
pass
def circle(i):
    """circle()."""
    a = start + (i * (PI_2 / (num_segments - 1)))
    return (math.cos(a) * radiusmode(a), math.sin(a) * radiusmode(a))

def circle(i):
    """circle()."""
    a = start - b + (i * angle / num_segments)
    return (math.cos(a) * radiusmode(a), math.sin(a) * radiusmode(a))

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_ang8(label, radius, thickness, color=white, bg=white, spee
pass
def circle(i):
    """circle()."""
    a = start - b + (i * angle / num_segments)
    return (math.cos(a) * radiusmode(a, rkoef), math.sin(a) * radiusmode(a, rkoef))

def circle(i):
    """circle()."""
    a = start - b + (i * angle / num_segments)
    return (math.cos(-a) * radiusmode(a, 1. - rkoef), math.sin(-a) * radiusmode(a, 1. - rkoef))

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_ang_mix(label, radius, thickness, color=white, speed=2.8, 
pass
def circle(i):
    """circle()."""
    a = start - b + (i * angle / num_segments)
    return (math.cos(a) * rb, math.sin(a) * rb)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_loading_ring(label, radius, thickness, color=white, bg=hal
pass
def circle(i):
    """circle()."""
    return (math.cos(i * bg_angle_offset) * radius, math.sin(i * bg_angle_offset) * radius)

def spinner_clock(label, radius, thickness, color=white, bg=half_white, speed=2.8):
    """SpinnerClock()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = im.get_time() * speed
    bg_angle_offset = PI_2 / (num_segments - 1)
# TODO(autoport): hand-translate (the rules mangled this line):     circle([&] (int i)
    pass  # TODO(autoport): body of the line above
    return (math.cos(i * bg_angle_offset) * radius, math.sin(i * bg_angle_offset) * radius);
# TODO(autoport): hand-translate (the rules mangled this line):     , color_alpha(bg, 1.), thickness)
    pass  # TODO(autoport): body of the line above
    window.draw_list.add_line(centre, (centre[0] + math.cos(start) * radius, centre[1] + math.sin(start) * radius), color_alpha(color, 1.), thickness * 2)
    window.draw_list.add_line(centre, (centre[0] + math.cos(start * 0.5) * radius / 2., centre[1] + math.sin(start * 0.5) * radius / 2.), color_alpha(color, 1.), thickness * 2)

def circle(i):
    """circle()."""
    return (math.cos(i * bg_angle_offset) * radius, math.sin(i * bg_angle_offset) * radius)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_pulsar(label, radius, thickness, bg=half_white, speed=2.8,
pass
def circle(i):
    """circle()."""
    return (math.cos(i * bg_angle_offset) * radius1, math.sin(i * bg_angle_offset) * radius1)

def circle(i):
    """circle()."""
    return (math.cos(i * bg_angle_offset) * radius_tb, math.sin(i * bg_angle_offset) * radius_tb)

def spinner_double_fade_pulsar(label, radius, _arg2, bg=half_white, speed=2.8):
    """SpinnerDoubleFadePulsar()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    pass  # TODO(autoport): internal window state: ImGuiStorage* storage = window->DC.StateStorage
    radiusbId = window.get_id("##radiusb")
    radius_b = storage.get_float(radiusbId, 0.8)
    start = im.get_time() * speed
    bg_angle_offset = pi_2_div(num_segments)
    start_r = math.fmod(start, PI_DIV_2)
    radius_k = math.sin(start_r)
    window.draw_list.add_circle_filled(centre, radius_k * radius, color_alpha(bg, min(0.1, radius_k)), num_segments)
    radius_b = (1. - radius_k)
    storage.set_float(radiusbId, radius_b)
    window.draw_list.add_circle_filled(centre, radius_b * radius, color_alpha(bg, min(0.3, radius_b)), num_segments)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_twin_pulsar(label, radius, thickness, color=white, speed=2
pass
def circle(i):
    """circle()."""
    a = start + (i * bg_angle_offset)
    return (math.cos(a) * radius1, math.sin(a) * radius1)

def spinner_fade_pulsar(label, radius, color=white, speed=2.8, rings=2, mode=0):
    """SpinnerFadePulsar()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    bg_angle_offset = pi_2_div(num_segments)
    koeff = pi_div(2 * rings)
    start = im.get_time() * speed
    for num_ring in range(int(0), int(rings)):
        radius_k = math.sin(math.fmod(start + (num_ring * koeff), PI_DIV_2))
        c = color_alpha(color, ((2. - (radius_k * 2.)) if (radius_k > 0.5) else color.value[3]))
        c.value[3] = c.value[3] - ease(mode, start, c.value[3])
        window.draw_list.add_circle_filled(centre, radius_k * radius, c, num_segments)

def spinner_fade_pulsar_square(label, radius, color=white, speed=2.8, rings=2, mode=0):
    """SpinnerFadePulsarSquare()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    bg_angle_offset = pi_2_div(num_segments)
    koeff = pi_div(2 * rings)
    start = im.get_time() * speed
    for num_ring in range(int(0), int(rings)):
        start_r = math.fmod(start, PI_DIV_2)
        radius_k = math.sin(start_r * (1. - (1. / rings) * num_ring))
        radius_k = radius_k + ease(mode, bg_angle_offset, speed)
        radius_k = std.clamp(radius_k, 0., 1.)
        c = color_alpha(color, ((2. - (radius_k * 2.)) if (radius_k > 0.5) else color.value[3]))
        c.value[3] = 0.8 / (1 + rings)
        px = radius_k * radius
        window.draw_list.add_rect_filled((centre[0] - px, centre[1] - px), (centre[0] + px, centre[1] + px), c, 2.)
        px = radius * (1. - radius_k)
        window.draw_list.add_rect_filled((centre[0] - px, centre[1] - px), (centre[0] + px, centre[1] + px), c, 2.)

def spinner_circular_lines(label, radius, color=white, speed=1.8, lines=8, mode=0):
    """SpinnerCircularLines()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
# TODO(autoport): hand-translate (the rules mangled this line):     ghalf_pi = [] (float f) . float ( return min(f, PI_DIV_2); )
    pass  # TODO(autoport): body of the line above
    start = math.fmod(im.get_time() * speed, IM_PI)
    bg_angle_offset = pi_2_div(lines)
    for j in range(int(0), int(3)):
        start_offset = j * pi_div(7.)
        rmax = max(math.sin(ghalf_pi(start - start_offset)), 0.3) * radius
        rmin = max(math.sin(ghalf_pi(start - PI_DIV_4 - start_offset)), 0.3) * radius
        c = color_alpha(color, 1. - j * 0.3)
        for i in range(int(0), int(lines) + 1):
            a = (i * bg_angle_offset)
            a = a + ease(mode, start_offset, radius)
            window.draw_list.add_line((centre[0] + math.cos(a) * rmin, centre[1] + math.sin(a) * rmin), (centre[0] + math.cos(a) * rmax, centre[1] + math.sin(a) * rmax), color_alpha(c, 1.), 1.)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_dots(label, nextdot, radius, thickness, color=white, speed
pass
# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_v_dots(label, radius, thickness, color=white, bgcolor=whit
pass
def spinner4_caleidospcope(label, radius, thickness, color=0xffffffff, speed=2.8, lt=8):
    """Spinner4Caleidospcope()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = math.fmod(im.get_time() * speed, PI_2)
    nextItemKoeff = 2.5
    offset = size[0] / 4.
    ab = start
    msize = 2
    out_h = 0.0
    out_s = 0.0
    out_v = 0.0
    im.color_convert_rg_bto_hsv(color.value[0], color.value[1], color.value[2], out_h, out_s, out_v)
    for i in range(int(0), int(msize)):
        a = ab - i * IM_PI
        c = color_alpha(ImColor.HSV(out_h + (0.1 * i), out_s, out_v, 0.7), 1.)
        window.draw_list.add_circle_filled((centre[0] - offset + math.sin(a) * offset, centre[1] + math.cos(a) * offset), thickness, c, lt)
    for i in range(int(0), int(msize)):
        a = ab + i * IM_PI + PI_DIV_2
        c = color_alpha(ImColor.HSV(out_h + 0.2 + (0.1 * i), out_s, out_v, 0.7), 1.)
        window.draw_list.add_circle_filled((centre[0] + math.sin(a) * offset, centre[1] - offset + math.cos(a) * offset), thickness, c, lt)
    ba = start
    msize = 2
    for i in range(int(0), int(msize)):
        a = -ba + i * IM_PI + PI_DIV_2
        c = color_alpha(ImColor.HSV(out_h + 0.4 + (0.1 * i), out_s, out_v, 0.7), 1.)
        window.draw_list.add_circle_filled((centre[0] + offset + math.sin(a) * offset, centre[1] + math.cos(a) * offset), thickness, c, lt)
    for i in range(int(0), int(msize)):
        a = ab - i * IM_PI + PI_DIV_4
        c = color_alpha(ImColor.HSV(out_h + 0.6 + (0.1 * i), out_s, out_v, 0.7), 1.)
        window.draw_list.add_circle_filled((centre[0] + math.sin(a) * offset, centre[1] + offset + math.cos(a) * offset), thickness, c, lt)

def spinner_thick_to_sin(label, radius, thickness, color=white, speed=2.8, nt=1, lt=8, mode=0):
    """SpinnerThickToSin()."""
    # TODO(autoport): for (; i < (lt * 2); i++)
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = math.fmod(im.get_time() * speed, PI_2)
    length = math.fmod(start, IM_PI)
    dangle = math.sin(length) * IM_PI * 0.5
    angle_offset = IM_PI / (lt * 2)
# TODO(autoport): hand-translate (the rules mangled this line):     draw_spring = [&] (float k, float r)
    pass  # TODO(autoport): body of the line above
    arc = 0.
    i = 0
    for _ in range(0):  # TODO(autoport):
        a = start + (i * angle_offset)
        a = a + ease(mode, a, dangle)
        if math.sin(a) < 0.:
            a = a * -1
        arc = arc + angle_offset
        if arc > dangle:
            break
        th = thickness * (2 * abs(math.cos(start)))
        th = max(th, 1.)
        window.draw_list.add_circle_filled((centre[0] + math.cos(a) * r, centre[1] + k * math.sin(a) * r), th, color_alpha(color, 1.), 8)
    for num_ring in range(int(0), int(nt)):
        draw_spring(-1 - num_ring * 0.1, radius * (1 - 0.1 * num_ring))

def spinner_square_spins(label, radius, thickness, color=white, speed=2.8):
    """SpinnerSquareSpins()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    nextItemKoeff = 2.5
    heightSpeed = 0.8
    dots = (size[0] / (thickness * nextItemKoeff))
    start = im.get_time() * speed
    for i in range(int(0), int(dots)):
        a = math.fmod(start + i * ((PI_DIV_2 * 0.7) / dots), PI_DIV_2)
        th = thickness * (math.cos(a * heightSpeed) * 2.)
        pmin = (centre[0] - (size[0] / 2.) + i * thickness * nextItemKoeff - thickness, centre[1] - thickness)
        pmax = (centre[0] - (size[0] / 2.) + i * thickness * nextItemKoeff + thickness, centre[1] + thickness)
        window.draw_list.add_rect(pmin, pmax, color_alpha(color, 1.), 0.)
        lmin = (centre[0] - (size[0] / 2.) + i * thickness * nextItemKoeff - thickness, centre[1] - th + thickness)
        lmax = (centre[0] - (size[0] / 2.) + i * thickness * nextItemKoeff + thickness - 1, centre[1] - th + thickness)
        window.draw_list.add_line(lmin, lmax, color_alpha(color, 1.), 1.)

def spinner_twin_ang(label, radius1, radius2, thickness, color1=white, color2=red, speed=2.8, angle=IM_PI, mode=0):
    """SpinnerTwinAng()."""
    radius = max(radius1, radius2)
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = math.fmod(im.get_time() * speed, PI_2)
    aoffset = math.fmod(im.get_time(), 1.5 * IM_PI)
    bofsset = (angle if (aoffset > angle) else aoffset)
    angle_offset = angle * 2. / num_segments
    window.draw_list.path_clear()
    for i in range(int(0), int(2 * num_segments) + 1):
        b = ease(mode, start + i * pi_div(2) / num_segments, IM_PI, 1.0, 0.0)
        a = start + b + (i * angle_offset)
        if i * angle_offset > 2 * bofsset:
            break
        window.draw_list.path_line_to((centre[0] + math.cos(a) * radius1, centre[1] + math.sin(a) * radius1))
    path_stroke(window.draw_list, color_alpha(color1, 1.), thickness, False)
    window.draw_list.path_clear()
    for i in range(int(0), int(num_segments / 2)):
        b = ease(mode, start + i * pi_div(2) / num_segments, IM_PI, 1.0, 0.0)
        a = start - b + (i * angle_offset)
        if i * angle_offset > bofsset:
            break
        window.draw_list.path_line_to((centre[0] + math.cos(a) * radius2, centre[1] + math.sin(a) * radius2))
    path_stroke(window.draw_list, color_alpha(color2, 1.), thickness, False)

def spinner_filling(label, radius, thickness, color1=white, color2=red, speed=2.8):
    """SpinnerFilling()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = math.fmod(im.get_time() * speed, PI_2)
    angle_offset = pi_2_div(num_segments - 1)
# TODO(autoport): hand-translate (the rules mangled this line):     circle([&] (int i)
    pass  # TODO(autoport): body of the line above
    a = (i * angle_offset); return (math.cos(a) * radius, math.sin(a) * radius);
# TODO(autoport): hand-translate (the rules mangled this line):     , color_alpha(color1, 1.), thickness)
    pass  # TODO(autoport): body of the line above
    window.draw_list.path_clear()
    for i in range(int(0), int(2 * num_segments / 2)):
        a = (i * angle_offset)
        if a > start:
            break
        window.draw_list.path_line_to((centre[0] + math.cos(a) * radius, centre[1] + math.sin(a) * radius))
    path_stroke(window.draw_list, color_alpha(color2, 1.), thickness, False)

def circle(i):
    """circle()."""
    a = (i * angle_offset)
    return (math.cos(a) * radius, math.sin(a) * radius)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_filling_mem(label, radius, thickness, color, colorbg, spee
pass
def circle(i):
    """circle()."""
    a = (i * angle_offset)
    return (math.cos(a) * radius, math.sin(a) * radius)

def spinner_topup(label, radius1, radius2, color=red, fg=white, bg=white, speed=2.8):
    """SpinnerTopup()."""
    radius = max(radius1, radius2)
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = math.fmod(im.get_time() * speed, IM_PI)
    window.draw_list.add_circle_filled(centre, radius1, color_alpha(bg, 1.), num_segments)
    abegin = (PI_DIV_2) - start
    aend = (PI_DIV_2) + start
    angle_offset = (aend - abegin) / num_segments
    window.draw_list.path_clear()
    window.draw_list.path_arc_to(centre, radius1, abegin, aend, num_segments * 2)
# TODO(autoport): hand-translate (the rules mangled this line):     ImDrawListFlags save = window.draw_list.flags
    pass  # TODO(autoport): body of the line above
    window.draw_list.flags &= ~ImDrawListFlags_AntiAliasedFill
    window.draw_list.path_fill_convex(color_alpha(color, 1.))
    window.draw_list.add_circle_filled(centre, radius2, color_alpha(fg, 1.), num_segments)
    window.draw_list.flags = save

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_twin_ang180(label, radius1, radius2, thickness, color1=whi
pass
def spinner_twin_ang360(label, radius1, radius2, thickness, color1=white, color2=red, speed1=2.8, speed2=2.5, mode=0):
    """SpinnerTwinAng360()."""
    radius = max(radius1, radius2)
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    num_segments = num_segments * 4
    start1 = math.fmod(im.get_time() * speed1, PI_2)
    start2 = math.fmod(im.get_time() * speed2, PI_2)
    aoffset = math.fmod(im.get_time(), 2. * IM_PI)
    bofsset = (IM_PI if (aoffset > IM_PI) else aoffset)
    angle_offset = PI_2 / num_segments
    ared_min = 0
    ared = 0
    if aoffset > IM_PI:
        ared_min = aoffset - IM_PI
    window.draw_list.path_clear()
    for i in range(int(0), int(num_segments + 1) + 1):
        ared = ((damped_spring(1, 10., 1.0, math.sin(math.fmod(start1 + 0 * pi_div(2), PI_2))) if mode else start1)) + (i * angle_offset)
        if i * angle_offset < ared_min * 2:
            continue
        if i * angle_offset > bofsset * 2.:
            break
        window.draw_list.path_line_to((centre[0] + math.cos(ared) * radius2, centre[1] + math.sin(ared) * radius2))
    path_stroke(window.draw_list, color_alpha(color2, 1.), thickness, False)
    window.draw_list.path_clear()
    for i in range(int(0), int(num_segments + 1) + 1):
        ared = ((damped_spring(1, 10., 1.0, math.sin(math.fmod(start2 + 1 * pi_div(2), PI_2))) if mode else start2)) + (i * angle_offset)
        if i * angle_offset < ared_min * 2:
            continue
        if i * angle_offset > bofsset * 2.:
            break
        window.draw_list.path_line_to((centre[0] + math.cos(-ared) * radius1, centre[1] + math.sin(-ared) * radius1))
    path_stroke(window.draw_list, color_alpha(color1, 1.), thickness, False)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_fade_tris(label, radius, color=white, speed=2.8, dim=2, sc
pass
def spinner_ang_twin(label, radius1, radius2, thickness, color=white, bg=half_white, speed=2.8, angle=IM_PI, arcs=1, mode=0):
    """SpinnerAngTwin()."""
    radius = max(radius1, radius2)
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = im.get_time()* speed
    bg_angle_offset = PI_2 / num_segments
    window.draw_list.path_clear()
    for i in range(int(0), int(num_segments) + 1):
        a = start + (i * bg_angle_offset)
        window.draw_list.path_line_to((centre[0] + math.cos(a) * radius1, centre[1] + math.sin(a) * radius1))
    path_stroke(window.draw_list, color_alpha(bg, 1.), thickness, False)
    angle_offset = angle / num_segments
    for arc_num in range(int(0), int(arcs)):
        window.draw_list.path_clear()
        arc_start = 2 * IM_PI / arcs
        b = ease(mode, start + arc_num * pi_div(2) / arcs, IM_PI, 1.0, 0.0)
        for i in range(int(0), int(num_segments)):
            a = start + b + arc_start * arc_num + (i * angle_offset)
            window.draw_list.path_line_to((centre[0] + math.cos(a) * radius2, centre[1] + math.sin(a) * radius2))
        path_stroke(window.draw_list, color_alpha(color, 1.), thickness, False)

def spinner_arc_rotation(label, radius, thickness, color=white, speed=2.8, arcs=4, mode=0):
    """SpinnerArcRotation()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = im.get_time()* speed
    arc_angle = PI_2 / float(arcs)
    angle_offset = arc_angle / num_segments
    for arc_num in range(int(0), int(arcs)):
        window.draw_list.path_clear()
        c = color_alpha(color, max(0.1, arc_num / float(arcs)))
        b = ease(mode, start + arc_num * pi_div(2) / arcs, IM_PI, 1.0, 0.0)
        for i in range(int(0), int(num_segments) + 1):
            a = start + b + arc_angle * arc_num + (i * angle_offset)
            window.draw_list.path_line_to((centre[0] + math.cos(a) * radius, centre[1] + math.sin(a) * radius))
        path_stroke(window.draw_list, c, thickness, False)

def spinner_arc_fade(label, radius, thickness, color=white, speed=2.8, arcs=4, mode=0):
    """SpinnerArcFade()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = math.fmod(im.get_time()* speed, IM_PI * 4.)
    arc_angle = PI_2 / float(arcs)
    angle_offset = arc_angle / num_segments
    for arc_num in range(int(0), int(arcs)):
        window.draw_list.path_clear()
        for i in range(int(0), int(num_segments + 1) + 1):
            a = arc_angle * arc_num + (i * angle_offset) - PI_DIV_2 - PI_DIV_4
            window.draw_list.path_line_to((centre[0] + math.cos(a) * radius, centre[1] + math.sin(a) * radius))
        a = arc_angle * arc_num
        c = color
        if start < PI_2:
            c.value[3] = 0.
            if start > a  and  start < (a + arc_angle):
                c.value[3] = 1. - (start - a) / float(arc_angle)
            elif start < a:
                c.value[3] = 1.
            woff = ease(mode, start - a, 4.)
            c.value[3] = max(0.05, 1. - c.value[3] - woff)
        else:
            startk = start - PI_2
            c.value[3] = 0.
            if startk > a  and  startk < (a + arc_angle):
                c.value[3] = 1. - (startk - a) / float(arc_angle)
            elif startk < a:
                c.value[3] = 1.
            woff = ease(mode, start - a, 4.)
            c.value[3] = max(0.05, c.value[3] + woff)
        path_stroke(window.draw_list, color_alpha(c, 1.), thickness, False)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_simple_arc_fade(label, radius, thickness, color=white, spe
pass
def spinner_square_stroke_fade(label, radius, thickness, color=white, speed=2.8):
    """SpinnerSquareStrokeFade()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = math.fmod(im.get_time() * speed, IM_PI * 4.)
    arc_angle = PI_DIV_2
    ht = thickness / 2.
    for arc_num in range(int(0), int(4)):
        a = arc_angle * arc_num
        c = color_alpha(color, 1.)
        if start < PI_2:
            c.value[3] = (1. - (start - a) / float(arc_angle) if (start > a  and  start < (a + arc_angle)) else ((1. if start < a else 0.)))
            c.value[3] = max(0.05, 1. - c.value[3])
        else:
            startk = start - PI_2
            c.value[3] = (1. - (startk - a) / float(arc_angle) if (startk > a  and  startk < (a + arc_angle)) else ((1. if startk < a else 0.)))
            c.value[3] = max(0.05, c.value[3])
        a = a - PI_DIV_4
        r = radius * 1.4
        right = math.sin(a) > 0
        top = math.cos(a) < 0
        p1 = (centre[0] + math.cos(a) * r, centre[1] + math.sin(a) * r)
        p2 = (centre[0] + math.cos(a - PI_DIV_2) * r, centre[1] + math.sin(a - PI_DIV_2) * r)
        if arc_num == 0:
            p2[0] = p2[0] - ht
        elif arc_num == 1:
            p2[1] = p2[1] - ht
        elif arc_num == 2:
            p2[0] = p2[0] + ht
        elif arc_num == 3:
            p2[1] = p2[1] + ht
        window.draw_list.add_line(p1, p2, color_alpha(c, 1.), thickness)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_ascii_symbol_points(label, text, radius, thickness, color=
pass
# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_seven_segments(label, text, radius, thickness, color=white
pass
def spinner_square_stroke_fill(label, radius, thickness, color=white, speed=2.8):
    """SpinnerSquareStrokeFill()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    overt = 3.
    start = math.fmod(im.get_time() * speed, PI_2 + overt)
    arc_angle = 2. * PI_DIV_4
    ht = thickness / 2.
    r = radius * 1.4
    pp = (centre[0] + math.cos(-IM_PI * 0.75) * r, centre[1] + math.sin(-IM_PI * 0.75) * r)
    if start > PI_2:
        c = color
        delta = (start - PI_2) / overt
        if delta < 0.5:
            c.value[3] = 1. - delta * 2.
            window.draw_list.add_line((pp[0] - ht, pp[1]), (pp[0] + ht, pp[1]), color_alpha(c, 1.), thickness)
        else:
            c.value[3] = (delta - 0.5) * 2.
            window.draw_list.add_line((pp[0] - ht, pp[1]), (pp[0] + ht, pp[1]), color_alpha(color, 1.), thickness)
    else:
        window.draw_list.add_line((pp[0] - ht, pp[1]), (pp[0] + ht, pp[1]), color_alpha(color, 1.), thickness)
    if start < PI_2:
        for arc_num in range(int(0), int(4)):
            a = arc_angle * arc_num
            segment_progress = (1. - (start - a) / float(arc_angle) if (start > a  and  start < (a + arc_angle)) else ((1. if start < a else 0.)))
            a = a - PI_DIV_4
            segment_progress = 1. - segment_progress
            p1 = (centre[0] + math.cos(a - PI_DIV_2) * r, centre[1] + math.sin(a - PI_DIV_2) * r)
            p2 = (centre[0] + math.cos(a) * r, centre[1] + math.sin(a) * r)
            if arc_num == 0:
                p2[0] = p2[0] - ht
                p2 = (p1[0] + (p2[0] - p1[0]) * segment_progress, p2[1])
            elif arc_num == 1:
                p2[1] = p2[1] - ht
                p2 = (p2[0], p1[1] + (p2[1] - p1[1]) * segment_progress)
            elif arc_num == 2:
                p2[0] = p2[0] + ht
                p2 = (p1[0] + (p2[0] - p1[0]) * segment_progress, p2[1])
            elif arc_num == 3:
                p2[1] = p2[1] - ht
                p2 = (p2[0], p1[1] + (p2[1] - p1[1]) * segment_progress)
            window.draw_list.add_line(p1, p2, color_alpha(color, 1.), thickness)

def spinner_square_stroke_loading(label, radius, thickness, color=white, speed=2.8):
    """SpinnerSquareStrokeLoading()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = math.fmod(im.get_time() * speed, PI_2)
    arc_angle = 2. * PI_DIV_4
    ht = thickness / 2.
    best_radius = radius * 1.4
    delta = (start - PI_2) / 2.
    for arc_num in range(int(0), int(4)):
        a = arc_angle * arc_num
        a = a - PI_DIV_4
        pp = (centre[0] + math.cos(a) * best_radius, centre[1] + math.sin(a) * best_radius)
        window.draw_list.add_line((pp[0] - ht, pp[1]), (pp[0] + ht, pp[1]), color_alpha(color, 1.), thickness)
    grow = start < IM_PI
    segment_progress = ((start / IM_PI) if grow else (1. - (start - IM_PI) / IM_PI))
    for arc_num in range(int(0), int(4)):
        a = arc_angle * arc_num
        a = a - PI_DIV_4
        right = math.sin(a) > 0
        top = math.cos(a) < 0
        p1 = (centre[0] + math.cos(a - PI_DIV_2) * best_radius, centre[1] + math.sin(a - PI_DIV_2) * best_radius)
        p2 = (centre[0] + math.cos(a) * best_radius, centre[1] + math.sin(a) * best_radius)
        if arc_num == 0:
            p2[0] = p2[0] + ht
            p1 = ((p1[0] if grow else p1[0] + (p2[0] - p1[0]) * (1. - segment_progress)), p1[1])
            p2 = ((p1[0] + (p2[0] - p1[0]) * segment_progress if grow else p2[0]), p2[1])
        elif arc_num == 1:
            p2[1] = p2[1] + ht
            p1 = (p1[0], (p1[1] if grow else p1[1] + (p2[1] - p1[1]) * (1. - segment_progress)))
            p2 = (p2[0], (p1[1] + (p2[1] - p1[1]) * segment_progress if grow else p2[1]))
        elif arc_num == 2:
            p2[0] = p2[0] - ht
            p1 = ((p1[0] if grow else (p1[0] if grow else p1[0] + (p2[0] - p1[0]) * (1. - segment_progress))), p1[1])
            p2 = ((p1[0] + (p2[0] - p1[0]) * segment_progress if grow else p2[0]), p2[1])
        elif arc_num == 3:
            p2[1] = p2[1] - ht
            p1 = (p1[0], (p1[1] if grow else p1[1] + (p2[1] - p1[1]) * (1. - segment_progress)))
            p2 = (p2[0], (p1[1] + (p2[1] - p1[1]) * segment_progress if grow else p2[1]))
        window.draw_list.add_line(p1, p2, color_alpha(color, 1.), thickness)

def spinner_square_loading(label, radius, thickness, color=white, speed=2.8):
    """SpinnerSquareLoading()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = math.fmod(im.get_time() * speed, PI_2 + PI_DIV_2)
    arc_angle = PI_DIV_2
    ht = thickness / 2.
    best_radius = radius * 1.4
    a = arc_angle * 3 - PI_DIV_4 + ((start * 2. if start > PI_2 else 0))
    last_pos = (centre[0] + math.cos(a) * best_radius, centre[1] + math.sin(a) * best_radius)
    ppMin = 0
    ppMax = 0
    for arc_num in range(int(0), int(4)):
        a = arc_angle * arc_num - PI_DIV_4 + ((start * 2. if start > PI_2 else 0))
        pp = (centre[0] + math.cos(a) * best_radius, centre[1] + math.sin(a) * best_radius)
        window.draw_list.add_line(last_pos, pp, color_alpha(color, 1.), thickness)
        last_pos = pp
        if start < PI_2:
            if arc_num == 2:
                ppMin = (centre[0] + math.cos(a) * best_radius * 0.8, centre[1] + math.sin(a) * best_radius * 0.8)
            elif arc_num == 0:
                ppMax = (centre[0] + math.cos(a) * best_radius * 0.8, centre[1] + math.sin(a) * best_radius * 0.8)
    if start < PI_2:
        ppMax[1] = ppMin[1] + (start / PI_2) * (ppMax[1] - ppMin[1])
        window.draw_list.add_rect_filled(ppMin, ppMax, color_alpha(color, 1.), 0.)

def spinner_filled_arc_fade(label, radius, color=white, speed=2.8, arcs=4, mode=0):
    """SpinnerFilledArcFade()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = math.fmod(im.get_time()* speed, IM_PI * 4.)
    arc_angle = PI_2 / float(arcs)
    angle_offset = arc_angle / num_segments
    for arc_num in range(int(0), int(arcs)):
        b = arc_angle * arc_num - PI_DIV_2 - PI_DIV_4
        e = arc_angle * arc_num + arc_angle - PI_DIV_2 - PI_DIV_4
        a = arc_angle * arc_num
        c = color
        vradius = radius
        if start < PI_2:
            c.value[3] = 0.
            if start > a  and  start < (a + arc_angle):
                c.value[3] = 1. - (start - a) / float(arc_angle)
            elif start < a:
                c.value[3] = 1.
            c.value[3] = max(0., 1. - c.value[3])
            if mode == 1:
                vradius = radius * c.value[3]
        else:
            startk = start - PI_2
            c.value[3] = 0.
            if startk > a  and  startk < (a + arc_angle):
                c.value[3] = 1. - (startk - a) / float(arc_angle)
            elif startk < a:
                c.value[3] = 1.
            if mode == 1:
                vradius = radius * c.value[3]
        window.draw_list.path_clear()
        window.draw_list.path_line_to(centre)
        for i in range(int(0), int(num_segments + 1) + 1):
            ar = arc_angle * arc_num + (i * angle_offset) - PI_DIV_2 - PI_DIV_4
            window.draw_list.path_line_to((centre[0] + math.cos(ar) * vradius, centre[1] + math.sin(ar) * vradius))
        window.draw_list.path_fill_convex(color_alpha(c, 1.))

def spinner_points_roller(label, radius, thickness, color=white, speed=2.8, points=8, circles=2, rspeed=1.):
    """SpinnerPointsRoller()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = math.fmod(im.get_time() * speed, IM_PI / (points / 2))
    arc_angle = PI_2 / float(points)
    angle_offset = arc_angle / num_segments
    dspeed = rspeed
    angleStep = IM_PI * 2.0 / points
    for c_num in range(int(0), int(circles)):
        vradius = radius * (1. - (1. / (circles + 2.) * c_num))
        adv_angle = ((IM_PI * 2) / circles) * c_num
        for arc_num in range(int(0), int(points)):
            b = arc_angle * arc_num - PI_DIV_2 - PI_DIV_4
            e = arc_angle * arc_num + arc_angle - PI_DIV_2 - PI_DIV_4
            a = arc_angle * arc_num
            angle = angleStep * arc_num + start * speed
            alpha = 1.0 - (angle / (IM_PI * 2.0))
            dotColor = im.get_color_u32(((color >> IM_COL32_R_SHIFT) / 255.0, (color >> IM_COL32_G_SHIFT) / 255.0, (color >> IM_COL32_B_SHIFT) / 255.0, alpha))
            ar = start + adv_angle + arc_angle * arc_num - PI_DIV_2 - PI_DIV_4
            window.draw_list.add_circle_filled((centre[0] + math.cos(ar) * vradius, centre[1] + math.sin(ar) * vradius), thickness, color_alpha(dotColor, 1.), 8)
        dspeed = dspeed + rspeed

def spinner_points_arc_bounce(label, radius, thickness, color=white, speed=2.8, points=4, circles=2, rspeed=0.):
    """SpinnerPointsArcBounce()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = math.fmod(im.get_time()* speed, IM_PI * 4.)
    arc_angle = PI_2 / float(points)
    angle_offset = arc_angle / num_segments
    dspeed = rspeed
    for c_num in range(int(0), int(circles)):
        mr = radius * (1. - (1. / (circles + 2.) * c_num))
        adv_angle = IM_PI * c_num
        for arc_num in range(int(0), int(points)):
            b = arc_angle * arc_num - PI_DIV_2 - PI_DIV_4
            e = arc_angle * arc_num + arc_angle - PI_DIV_2 - PI_DIV_4
            a = arc_angle * arc_num
            c = color
            vradius = mr
            if start < PI_2:
                c.value[3] = 0.
                if start > a  and  start < (a + arc_angle):
                    c.value[3] = 1. - (start - a) / float(arc_angle)
                elif start < a:
                    c.value[3] = 1.
                c.value[3] = max(0., 1. - c.value[3])
                vradius = mr * c.value[3]
            else:
                startk = start - PI_2
                c.value[3] = 0.
                if startk > a  and  startk < (a + arc_angle):
                    c.value[3] = 1. - (startk - a) / float(arc_angle)
                elif startk < a:
                    c.value[3] = 1.
                vradius = mr * c.value[3]
            ar = start * dspeed + adv_angle + arc_angle * arc_num - PI_DIV_2 - PI_DIV_4
            window.draw_list.add_circle_filled((centre[0] + math.cos(ar) * vradius, centre[1] + math.sin(ar) * vradius), thickness, color_alpha(c, 1.), 8)
        dspeed = dspeed + rspeed

def spinner_filled_arc_color(label, radius, color=red, bg=white, speed=2.8, arcs=4):
    """SpinnerFilledArcColor()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = math.fmod(im.get_time()* speed, PI_2)
    arc_angle = PI_2 / float(arcs)
    angle_offset = arc_angle / num_segments
    window.draw_list.add_circle_filled(centre, radius, color_alpha(bg, 1.), num_segments * 2)
    for arc_num in range(int(0), int(arcs)):
        b = arc_angle * arc_num - PI_DIV_2
        e = arc_angle * arc_num + arc_angle - PI_DIV_2
        a = arc_angle * arc_num
        c = color
        c.value[3] = 0.
        if start > a  and  start < (a + arc_angle):
            c.value[3] = 1. - (start - a) / float(arc_angle)
        elif start < a:
            c.value[3] = 1.
        c.value[3] = max(0., 1. - c.value[3])
        window.draw_list.path_clear()
        window.draw_list.path_line_to(centre)
        for i in range(int(0), int(num_segments + 1)):
            ar = arc_angle * arc_num + (i * angle_offset) - PI_DIV_2
            window.draw_list.path_line_to((centre[0] + math.cos(ar) * radius, centre[1] + math.sin(ar) * radius))
        window.draw_list.path_fill_convex(color_alpha(c, 1.))

def spinner_filled_arc_ring(label, radius, thickness, color=red, bg=white, speed=2.8, arcs=4):
    """SpinnerFilledArcRing()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    pi_div_2 = PI_DIV_2
    pi_div_4 = PI_DIV_4
    pi_mul_2 = PI_2
    start = math.fmod(im.get_time() * speed, pi_mul_2 + pi_div_4)
    arc_angle = pi_mul_2 / float(arcs)
    angle_offset = arc_angle / num_segments
    window.draw_list.path_clear()
    for i in range(int(0), int(num_segments + 1)):
        ar_b = (i * (pi_mul_2 / num_segments))
        window.draw_list.path_line_to((centre[0] + math.cos(ar_b) * radius, centre[1] + math.sin(ar_b) * radius))
    path_stroke(window.draw_list, color_alpha(bg, 1.), thickness, False)
    for arc_num in range(int(0), int(arcs)):
        b = arc_angle * arc_num - pi_div_2
        e = arc_angle * arc_num + arc_angle - pi_div_2
        a = arc_angle * arc_num
        alpha = 0.
        if start > pi_mul_2:
            alpha = (start - pi_mul_2) / pi_div_4
        elif start > a  and  start < (a + arc_angle):
            alpha = 1. - (start - a) / float(arc_angle)
        elif start < a:
            alpha = 1.
        window.draw_list.path_clear()
        for i in range(int(0), int(num_segments + 1)):
            ar_b = arc_angle * arc_num + (i * angle_offset) - pi_div_2
            window.draw_list.path_line_to((centre[0] + math.cos(ar_b) * radius, centre[1] + math.sin(ar_b) * radius))
        path_stroke(window.draw_list, color_alpha(color, max(0., 1. - alpha)), thickness, False)

def spinner_arc_wedges(label, radius, color=red, speed=2.8, arcs=4, mode=0):
    """SpinnerArcWedges()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = im.get_time() * speed
    arc_angle = PI_2 / float(arcs)
    angle_offset = arc_angle / num_segments
    out_h = 0.0
    out_s = 0.0
    out_v = 0.0
    im.color_convert_rg_bto_hsv(color.value[0], color.value[1], color.value[2], out_h, out_s, out_v)
    for arc_num in range(int(0), int(arcs)):
        b = arc_angle * arc_num - PI_DIV_2
        e = arc_angle * arc_num + arc_angle - PI_DIV_2
        a = arc_angle * arc_num
        window.draw_list.path_clear()
        window.draw_list.path_line_to(centre)
        ab = ease(mode, start + arc_num * pi_div(2) / arcs, IM_PI, 1.0, 0.0)
        for i in range(int(0), int(num_segments + 1)):
            start_a = math.fmod(start * (1.05 * (arc_num + 1)), PI_2)
            ar = start_a + ab + arc_angle * arc_num + (i * angle_offset) - PI_DIV_2
            window.draw_list.path_line_to((centre[0] + math.cos(ar) * radius, centre[1] + math.sin(ar) * radius))
        window.draw_list.path_fill_convex(color_alpha(ImColor.HSV(out_h + (1. / arcs) * arc_num, out_s, out_v, 0.7), 1.))

def spinner_twin_ball(label, radius1, radius2, thickness, b_thickness, ball=white, bg=half_white, speed=2.8, balls=2, mode=0):
    """SpinnerTwinBall()."""
    radius = max(radius1, radius2)
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = im.get_time()* speed
    bg_angle_offset = PI_2 / num_segments
    window.draw_list.path_clear()
    for i in range(int(0), int(num_segments) + 1):
        a = start + (i * bg_angle_offset)
        window.draw_list.path_line_to((centre[0] + math.cos(a) * radius1, centre[1] + math.sin(a) * radius1))
    path_stroke(window.draw_list, color_alpha(bg, 1.), thickness, False)
    for b_num in range(int(0), int(balls)):
        b_start = PI_2 / balls
        ab = ease(mode, start + b_num * pi_div(2) / balls, IM_PI, 1.0, 0.0)
        a = b_start * b_num + start + ab
        window.draw_list.add_circle_filled((centre[0] + math.cos(a) * radius2, centre[1] + math.sin(a) * radius2), b_thickness, color_alpha(ball, 1.))

def spinner_solar_balls(label, radius, thickness, ball=white, bg=half_white, speed=2.8, balls=4):
    """SpinnerSolarBalls()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = im.get_time() * speed
    bg_angle_offset = PI_2 / num_segments
    for i in range(int(0), int(balls)):
        rb = (radius / balls) * 1.3 * (i + 1)
        window.draw_list.add_circle(centre, rb, color_alpha(bg, 1.), num_segments, thickness * 0.3)
    for i in range(int(0), int(balls)):
        rb = (radius / balls) * 1.3 * (i + 1)
        a = start * (1.0 + 0.1 * i)
        window.draw_list.add_circle_filled((centre[0] + math.cos(a) * rb, centre[1] + math.sin(a) * rb), thickness, color_alpha(ball, 1.))

def spinner_solar_scale_balls(label, radius, thickness, ball=white, speed=2.8, balls=4):
    """SpinnerSolarScaleBalls()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = math.fmod(im.get_time() * speed, IM_PI * 16.)
    bg_angle_offset = PI_2 / num_segments
    for i in range(int(0), int(balls)):
        rb = (radius / balls) * 1.3 * (i + 1)
        a = start * (1.0 + 0.1 * i)
        window.draw_list.add_circle_filled((centre[0] + math.cos(a) * rb, centre[1] + math.sin(a) * rb), ((thickness * 2.) / balls) * i, color_alpha(ball, 1.))

def spinner_solar_arcs(label, radius, thickness, ball=white, bg=half_white, speed=2.8, balls=4):
    """SpinnerSolarArcs()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = im.get_time()* speed
    half_segments = num_segments / 2
    for i in range(int(0), int(balls)):
        rb = (radius / balls) * 1.3 * (i + 1)
        bg_angle_offset = IM_PI / half_segments
        mul = (-1 if i % 2 else 1)
        window.draw_list.path_clear()
        for ii in range(int(0), int(half_segments) + 1):
            a = (ii * bg_angle_offset)
            window.draw_list.path_line_to((centre[0] + math.cos(a) * rb, centre[1] + math.sin(a) * rb * mul))
        path_stroke(window.draw_list, color_alpha(bg, 1.), thickness * 0.8, False)
    for i in range(int(0), int(balls)):
        rb = (radius / balls) * 1.3 * (i + 1)
        a = math.fmod(start * (1.0 + 0.1 * i), PI_2)
        mul = (-1 if i % 2 else 1)
        y = math.sin(a) * rb
        if (y > 0  and  mul < 0)  or  (y < 0  and  mul > 0):
            y = -y
        window.draw_list.add_circle_filled((centre[0] + math.cos(a) * rb, centre[1] + y), thickness, color_alpha(ball, 1.))

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_moving_arcs(label, radius, thickness, color=white, speed=2
pass
def circle(i):
    """circle()."""
    b = a + (i * angle / num_segments)
    return (math.cos(b) * rb, math.sin(b) * rb)

def spinner_rainbow_circle(label, radius, thickness, color=white, speed=2.8, arcs=4, mode=1):
    """SpinnerRainbowCircle()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = im.get_time() * speed
    num_segments = num_segments * 2
    bg_angle_offset = IM_PI / num_segments
    out_h = 0.0
    out_s = 0.0
    out_v = 0.0
    im.color_convert_rg_bto_hsv(color.value[0], color.value[1], color.value[2], out_h, out_s, out_v)
    for i in range(int(0), int(arcs)):
        max_angle = IM_PI - math.fmod(start, IM_PI + PI_DIV_2 + pi_div(8))
        max_angle = min(IM_PI, max_angle + (PI_DIV_2 / arcs) * i)
        rb = (radius / arcs) * 1.1 * (i + 1)
        c = ImColor.HSV(out_h + i * (0.8 / arcs), out_s, out_v)
        draw_segments = max(0, int(max_angle / bg_angle_offset))
        for j in range(int(0), int(2)):
            mul = (-1 if j % 2 else 1)
            py = ((-0.5 if j % 2 else 0.5)) * thickness
            alpha_start = ((0 if j % 2 else IM_PI)) * mode
            window.draw_list.path_clear()
            for ii in range(int(0), int(draw_segments + 1) + 1):
                a = (ii * bg_angle_offset)
                window.draw_list.path_line_to((centre[0] + math.cos(IM_PI - alpha_start - a) * rb, centre[1] + math.sin(a) * rb * mul + py))
            path_stroke(window.draw_list, color_alpha(c, 1.), thickness * 0.8, False)

def spinner_bounce_ball(label, radius, thickness, color=white, speed=2.8, dots=1, shadow=False):
    """SpinnerBounceBall()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    pass  # TODO(autoport): internal window state: ImGuiStorage* storage = window->DC.StateStorage
    vtimeId = window.get_id("##vtime")
    hmaxId = window.get_id("##hmax")
    vtime = storage.get_float(vtimeId, 0.)
    hmax = storage.get_float(hmaxId, 1.)
    vtime = vtime + 0.05
    hmax = hmax + 0.01
    storage.set_float(vtimeId, vtime)
    storage.set_float(hmaxId, hmax)
    rkoeff = [0.1, 0.15, 0.17, 0.25, 0.31, 0.19, 0.08, 0.24, 0.9]
    iterations = (4 if shadow else 1)
    for j in range(int(0), int(iterations)):
        c = color_alpha(color, 1. - 0.15 * j)
        for i in range(int(0), int(dots)):
            start = math.fmod(im.get_time() * speed * (1 + rkoeff[i % 9]) - (IM_PI / 12.) * j, IM_PI)
            sign = ((1. if (i % 2 == 0) else -1.))
            offset = (0. if (i == 0) else (math.floor((i+1) / 2. + 0.1) * sign * 2. * thickness))
            maxht = damped_gravity(math.sin(math.fmod(hmax, IM_PI))) * radius
            window.draw_list.add_circle_filled((centre[0] + offset, centre[1] + radius - math.sin(start) * 2. * maxht), thickness, c, 8)

def spinner_pulsar_ball(label, radius, thickness, color=white, speed=2.8, shadow=False, mode=0):
    """SpinnerPulsarBall()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    pass  # TODO(autoport): internal window state: ImGuiStorage* storage = window->DC.StateStorage
    iterations = (4 if shadow else 1)
    for j in range(int(0), int(iterations)):
        c = color_alpha(color, 1. - 0.15 * j)
        start = math.fmod(im.get_time() * speed - (IM_PI / 12.) * j, IM_PI)
        maxht = damped_gravity(math.sin(math.fmod(start, IM_PI))) * (radius * 0.6)
        window.draw_list.add_circle_filled((centre[0], centre[1]), maxht, c, num_segments)
    angle_offset = PI_DIV_2 / num_segments
    arcs = 2
    for arc_num in range(int(0), int(arcs)):
        window.draw_list.path_clear()
        arc_start = 2 * IM_PI / arcs
        start = math.fmod(im.get_time() * speed - (IM_PI * arc_num), IM_PI)
        b = (start + damped_spring(1, 10., 1.0, math.sin(math.fmod(start + arc_num * pi_div(2) / arcs, IM_PI)), 1, 0) if mode else start)
        maxht = (damped_gravity(math.sin(math.fmod(start, IM_PI))) * 0.3 + 0.7) * radius
        for i in range(int(0), int(num_segments)):
            a = b + arc_start * arc_num + (i * angle_offset)
            window.draw_list.path_line_to((centre[0] + math.cos(a) * maxht, centre[1] + math.sin(a) * maxht))
        path_stroke(window.draw_list, color_alpha(color, 1.), thickness, False)

def spinner_ang_triple(label, radius1, radius2, radius3, thickness, c1=white, c2=half_white, c3=white, speed=2.8, angle=IM_PI):
    """SpinnerAngTriple()."""
    radius = max(max(radius1, radius2), radius3)
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start1 = im.get_time() * speed
    angle_offset = angle / num_segments
    window.draw_list.path_clear()
    for i in range(int(0), int(num_segments)):
        a = start1 + (i * angle_offset)
        window.draw_list.path_line_to((centre[0] + math.cos(a) * radius1, centre[1] + math.sin(a) * radius1))
    path_stroke(window.draw_list, color_alpha(c1, 1.), thickness, False)
    start2 = im.get_time() * 1.2 * speed
    window.draw_list.path_clear()
    for i in range(int(0), int(num_segments)):
        a = start2 + (i * angle_offset)
        window.draw_list.path_line_to((centre[0] + math.cos(-a) * radius2, centre[1] + math.sin(-a) * radius2))
    path_stroke(window.draw_list, color_alpha(c2, 1.), thickness, False)
    start3 = im.get_time() * 0.9 * speed
    window.draw_list.path_clear()
    for i in range(int(0), int(num_segments)):
        a = start3 + (i * angle_offset)
        window.draw_list.path_line_to((centre[0] + math.cos(a) * radius3, centre[1] + math.sin(a) * radius3))
    path_stroke(window.draw_list, color_alpha(c3, 1.), thickness, False)

def spinner_ang_eclipse(label, radius, thickness, color=white, speed=2.8, angle=IM_PI):
    """SpinnerAngEclipse()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = im.get_time()* speed
    angle_offset = angle / num_segments
    th = thickness / num_segments
    for i in range(int(0), int(num_segments)):
        a = start + (i * angle_offset)
        a1 = start + ((i+1) * angle_offset)
        window.draw_list.add_line((centre[0] + math.cos(a) * radius, centre[1] + math.sin(a) * radius), (centre[0] + math.cos(a1) * radius, centre[1] + math.sin(a1) * radius), color_alpha(color, 1.), th * i)

def spinner_ing_yang(label, radius, thickness, reverse, yang_detlta_r, colorI=white, colorY=white, speed=2.8, angle=IM_PI * 0.7, mode=0):
    """SpinnerIngYang()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    startI = im.get_time() * speed
    startY = im.get_time() * (speed + ((im_clamp(yang_detlta_r * 0.5, 0.5, 2.) if yang_detlta_r > 0. else 0.)))
    angle_offset = angle / num_segments
    th = thickness / num_segments
    for i in range(int(0), int(num_segments)):
        ab = ease(mode, startI + i * pi_div(2) / num_segments, IM_PI, 1.0, 0.0)
        a = startI + ab + (i * angle_offset)
        a1 = startI + ab + ((i + 1) * angle_offset)
        window.draw_list.add_line((centre[0] + math.cos(a) * radius, centre[1] + math.sin(a) * radius), (centre[0] + math.cos(a1) * radius, centre[1] + math.sin(a1) * radius), color_alpha(colorI, 1.), th * i)
    ab = ease(mode, startI + pi_div(2), IM_PI, 1.0, 0.0)
    ai_end = startI + ab + (num_segments * angle_offset)
    circle_i_center = (centre[0] + math.cos(ai_end) * radius, centre[1] + math.sin(ai_end) * radius)
    window.draw_list.add_circle_filled(circle_i_center, thickness / 2., color_alpha(colorI, 1.), num_segments)
    rv = (-1. if reverse else 1.)
    yang_radius = (radius - yang_detlta_r)
    for i in range(int(0), int(num_segments)):
        ae = ease(mode, startI + i * pi_div(2) / num_segments, IM_PI, 1.0, 0.0)
        a = startY - ae + IM_PI + (i * angle_offset)
        a1 = startY - ae + IM_PI + ((i+1) * angle_offset)
        window.draw_list.add_line((centre[0] + math.cos(a * rv) * yang_radius, centre[1] + math.sin(a * rv) * yang_radius), (centre[0] + math.cos(a1 * rv) * yang_radius, centre[1] + math.sin(a1 * rv) * yang_radius), color_alpha(colorY, 1.), th * i)
    ae = ease(mode, startI + pi_div(2), IM_PI, 1.0, 0.0)
    ay_end = startY - ae + IM_PI + (num_segments * angle_offset)
    circle_y_center = (centre[0] + math.cos(ay_end * rv) * yang_radius, centre[1] + math.sin(ay_end * rv) * yang_radius)
    window.draw_list.add_circle_filled(circle_y_center, thickness / 2., color_alpha(colorY, 1.), num_segments)

def spinner_gooey_balls(label, radius, color, speed, mode=0):
    """SpinnerGooeyBalls()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = math.fmod(im.get_time() * speed, IM_PI)
    start = (damped_spring(1, 10., 1.0, math.sin(start), 1, 0) if mode else start)
    radius1 = (0.4 + 0.3 * math.sin(start)) * radius
    radius2 = radius - radius1
    window.draw_list.add_circle_filled((centre[0] - radius + radius1, centre[1]), radius1, color_alpha(color, 1.), num_segments)
    window.draw_list.add_circle_filled((centre[0] - radius + radius1 * 1.2 + radius2, centre[1]), radius2, color_alpha(color, 1.), num_segments)

def spinner_rotate_gooey_balls(label, radius, thickness, color, speed, balls, mode=0):
    """SpinnerRotateGooeyBalls()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = math.fmod(im.get_time(), IM_PI)
    rstart = math.fmod(im.get_time() * speed, PI_2)
    radius1 = (0.2 + 0.3 * math.sin(start)) * radius
    angle_offset = PI_2 / balls
    roff = ease(mode, start, radius)
    for i in range(int(0), int(balls) + 1):
        a = rstart + (i * angle_offset)
        window.draw_list.add_circle_filled((centre[0] + math.cos(a) * (radius1 + roff), centre[1] + math.sin(a) * (radius1 + roff)), thickness, color_alpha(color, 1.), num_segments)

def spinner_herbert_balls(label, radius, thickness, color, speed, balls):
    """SpinnerHerbertBalls()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = math.fmod(im.get_time(), IM_PI)
    rstart = math.fmod(im.get_time() * speed, PI_2)
    radius1 = 0.3 * radius
    radius2 = 0.8 * radius
    angle_offset = PI_2 / balls
    for i in range(int(0), int(balls)):
        a = rstart + (i * angle_offset)
        window.draw_list.add_circle_filled((centre[0] + math.cos(a) * radius1, centre[1] + math.sin(a) * radius1), thickness, color_alpha(color, 1.), num_segments)
    for i in range(int(0), int(balls * 2)):
        a = -rstart + (i * angle_offset / 2.)
        window.draw_list.add_circle_filled((centre[0] + math.cos(a) * radius2, centre[1] + math.sin(a) * radius2), thickness, color_alpha(color, 1.), num_segments)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_herbert_balls3_d(label, radius, thickness, color, speed):
pass
def spinner_rotate_triangles(label, radius, thickness, color, speed, tris, mode=0):
    """SpinnerRotateTriangles()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = math.fmod(im.get_time(), IM_PI)
    rstart = math.fmod(im.get_time() * speed, PI_2)
    radius1 = radius / 2.5 + thickness
    angle_offset = PI_2 / tris
    for i in range(int(0), int(tris) + 1):
        ab = ease(mode, start + i * pi_div(2) / tris, IM_PI, 1.0, 0.0)
        a = rstart + ab + (i * angle_offset)
        tri_centre = (centre[0] + math.cos(a) * radius1, centre[1] + math.sin(a) * radius1)
        p1 = (tri_centre[0] + math.cos(-a) * radius1, tri_centre[1] + math.sin(-a) * radius1)
        p2 = (tri_centre[0] + math.cos(-a + PI_2 / 3.) * radius1, tri_centre[1] + math.sin(-a + PI_2 / 3.) * radius1)
        p3 = (tri_centre[0] + math.cos(-a - PI_2 / 3.) * radius1, tri_centre[1] + math.sin(-a - PI_2 / 3.) * radius1)
        points = [p1, p2, p3]
        window.draw_list.add_convex_poly_filled(points, 3, color_alpha(color, 1.))

def spinner_rotate_shapes(label, radius, thickness, color, speed, shapes, pnt):
    """SpinnerRotateShapes()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = math.fmod(im.get_time(), IM_PI)
    rstart = math.fmod(im.get_time() * speed, PI_2)
    radius1 = radius / 2.5 + thickness
    angle_offset = PI_2 / shapes
    points = std.vector(pnt)
    begin_a = -IM_PI / ((pnt if (pnt % 2 == 0) else (pnt - 1)))
    for i in range(int(0), int(shapes) + 1):
        a = rstart + (i * angle_offset)
        tri_centre = (centre[0] + math.cos(a) * radius1, centre[1] + math.sin(a) * radius1)
        for pi in range(int(0), int(pnt)):
            points[pi] = (tri_centre[0] + math.cos(begin_a + pi * PI_2 / pnt) * radius1, tri_centre[1] + math.sin(begin_a + pi * PI_2 / pnt) * radius1)
        window.draw_list.add_convex_poly_filled(points.data(), pnt, color_alpha(color, 1.))

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_sin_squares(label, radius, thickness, color, speed, mode=0
pass
# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_moon_line(label, radius, thickness, color=white, bg=red, s
pass
def draw_gradient(i):
    """draw_gradient()."""
    return (num_segments + i) * angle_offset

def draw_gradient(i):
    """draw_gradient()."""
    return (i) * angle_offset

def draw_gradient(i):
    """draw_gradient()."""
    return (num_segments + i) * angle_offset

def draw_gradient(i):
    """draw_gradient()."""
    return num_segments * angle_offset * 2. + (i * b_angle_offset)

def spinner_circle_drop(label, radius, thickness, thickness_drop, color=white, bg=half_white, speed=2.8, angle=IM_PI):
    """SpinnerCircleDrop()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = im.get_time() * speed
    bg_angle_offset = PI_2 / num_segments
    angle_offset = angle / num_segments
    th = thickness_drop / num_segments
    drop_radius_th = thickness_drop / num_segments
    for i in range(int(0), int(num_segments)):
        a = start + (i * angle_offset)
        a1 = start + ((i + 1) * angle_offset)
        s_drop_radius = radius - thickness / 2. - (drop_radius_th * i)
        window.draw_list.add_line((centre[0] + math.cos(a) * s_drop_radius, centre[1] + math.sin(a) * s_drop_radius), (centre[0] + math.cos(a1) * s_drop_radius, centre[1] + math.sin(a1) * s_drop_radius), color_alpha(color, 1.), th * 2. * i)
    ai_end = start + (num_segments * angle_offset)
    f_drop_radius = radius - thickness / 2. - thickness_drop
    circle_i_center = (centre[0] + math.cos(ai_end) * f_drop_radius, centre[1] + math.sin(ai_end) * f_drop_radius)
    window.draw_list.add_circle_filled(circle_i_center, thickness_drop, color_alpha(color, 1.), num_segments)
    window.draw_list.path_clear()
    for i in range(int(0), int(num_segments) + 1):
        a = (i * bg_angle_offset)
        window.draw_list.path_line_to((centre[0] + math.cos(a) * radius, centre[1] + math.sin(a) * radius))
    path_stroke(window.draw_list, color_alpha(bg, 1.), thickness, False)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_surrounded_indicator(label, radius, thickness, color=white
pass
def spinner_wifi_indicator(label, radius, thickness, color=red, bg=half_white, speed=2.8, cangle=0., dots=3):
    """SpinnerWifiIndicator()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    lerp_koeff = (math.sin(im.get_time() * speed) + 1.) * 0.5
    start_ang = -cangle - PI_DIV_4 - PI_DIV_2
    pc = (centre[0] + math.sin(cangle) * radius, centre[1] + math.cos(cangle) * radius)
    window.draw_list.add_circle_filled(pc, thickness, bg, num_segments)
    window.draw_list.add_circle_filled(pc, thickness, color_alpha(color, max(0.1, min(lerp_koeff, 1.))), num_segments)
# TODO(autoport): hand-translate (the rules mangled this line):     PathArc = [&] (float as, const ImColor& c, float th, float r)
    pass  # TODO(autoport): body of the line above
    window.draw_list.path_clear()
    bg_angle_offset = pi_div(2) / num_segments
    for i in range(int(0), int(num_segments) + 1):
# TODO(autoport): hand-translate (the rules mangled this line):         window.draw_list.path_line_to((pc[0] + math.cos(as + i * bg_angle_offset) * r, pc[1] + math.sin(as + i * bg_angle_offset) * r))
        pass  # TODO(autoport): body of the line above
    path_stroke(window.draw_list, color_alpha(c, 1.), th, False)
    interval = (size[0] * 0.7) / dots
    for i in range(int(0), int(dots)):
        r = 1.5 * (i + 1) * interval
        lerp_koeff = (math.sin(im.get_time() * speed - (i+1) * (IM_PI / dots)) + 1.) * 0.5
        path_arc(start_ang, bg, thickness, r)
        path_arc(start_ang, color_alpha(color, max(0.1, min(lerp_koeff, 1.))), thickness, r)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_triangles_selector(label, radius, thickness, color=white, 
pass
def draw_sectors(_arg0, _arg1):
    """draw_sectors()."""
    return color_alpha(bg, 0.1)

def draw_sectors(start, i):
    """draw_sectors()."""
    return color_alpha(bg, (i / float(bars)) - 0.5)

def spinner_camera(label, radius, thickness, leaf_color, speed=2.8, bars=8, mode=0):
    """SpinnerCamera()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = im.get_time() * speed
    if mode == 1:
        thickness = thickness + ease_inoutquad(math.sin(math.fmod(start, IM_PI))) * (thickness * 0.5)
    angle_offset = PI_2 / bars
    angle_offset_t = angle_offset * 0.3
    bars = min(bars, 32)
    rmin = radius - thickness - 1
# TODO(autoport): hand-translate (the rules mangled this line):     get_points = [&] (float left, float right) . std.array<ImVec2, 4>
    pass  # TODO(autoport): body of the line above
    return ( (centre[0] + math.cos(left - 0.1) * radius, centre[1] + math.sin(left - 0.1) * radius), (centre[0] + math.cos(right + 0.15) * radius, centre[1] + math.sin(right + 0.15) * radius), (centre[0] + math.cos(right - 0.91) * rmin, centre[1] + math.sin(right - 0.91) * rmin) )
# TODO(autoport): hand-translate (the rules mangled this line):     draw_sectors = [&] (float s, const std.function<int(int)>& color_func)
    pass  # TODO(autoport): body of the line above
    for i in range(int(0), int(bars) + 1):
        left = s + (i * angle_offset) - angle_offset_t
        right = s + (i * angle_offset) + angle_offset_t
        points = get_points(left, right)
        window.draw_list.add_convex_poly_filled(points.data(), 3, color_alpha(color_func(int(i)), 1.))
    draw_sectors(start, leaf_color)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_flowing_gradient(label, radius, thickness, color=white, bg
pass
def draw_gradient(i):
    """draw_gradient()."""
    return (i) * angle_offset

def draw_gradient(i):
    """draw_gradient()."""
    return (num_segments + i) * angle_offset

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_rotate_segments(label, radius, thickness, color=white, spe
pass
def spinner_lemniscate(label, radius, thickness, color=white, speed=2.8, angle=IM_PI / 2.0):
    """SpinnerLemniscate()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = im.get_time() * speed
    a = radius
    t = start
    step = angle / num_segments
    th = thickness / num_segments
    for i in range(int(0), int(num_segments)):
        xy0 = damped_infinity(start + (i * step), a)
        xy1 = damped_infinity(start + ((i + 1) * step), a)
        window.draw_list.add_line((centre[0] + xy0.first, centre[1] + xy0.second), (centre[0] + xy1.first, centre[1] + xy1.second), color_alpha(color, 1.), th * i)

def spinner_rotate_gear(label, radius, thickness, color=white, speed=2.8, pins=12):
    """SpinnerRotateGear()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = im.get_time()* speed
    bg_angle_offset = PI_2 / num_segments
    bg_radius = radius - thickness
    window.draw_list.path_clear()
    for i in range(int(0), int(num_segments) + 1):
        a = (i * bg_angle_offset)
        window.draw_list.path_line_to((centre[0] + math.cos(a) * bg_radius, centre[1] + math.sin(a) * bg_radius))
    path_stroke(window.draw_list, color_alpha(color, 1.), bg_radius / 2, False)
    rmin = bg_radius
    rmax = radius
    pin_angle_offset = PI_2 / pins
    for i in range(int(0), int(pins) + 1):
        a = start + (i * pin_angle_offset)
        window.draw_list.add_line((centre[0] + math.cos(a) * rmin, centre[1] + math.sin(a) * rmin), (centre[0] + math.cos(a) * rmax, centre[1] + math.sin(a) * rmax), color_alpha(color, 1.), thickness)

def spinner_rotate_wheel(label, radius, thickness, bg_color=white, color=white, speed=2.8, pins=12):
    """SpinnerRotateWheel()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = im.get_time() * speed
    bg_radius = radius - thickness
    line_th = max(radius / 8., 3.)
# TODO(autoport): hand-translate (the rules mangled this line):     draw_circle = [window, num_segments, centre] (float r, const ImColor &c, float th)
    pass  # TODO(autoport): body of the line above
    bg_angle_offset = PI_2 / num_segments
    window.draw_list.path_clear()
    for i in range(int(0), int(num_segments) + 1):
        a = (i * bg_angle_offset)
        window.draw_list.path_line_to((centre[0] + math.cos(a) * r, centre[1] + math.sin(a) * r))
    path_stroke(window.draw_list, color_alpha(c, 1.), th, False)
# TODO(autoport): hand-translate (the rules mangled this line):     draw_pins = [window, centre, pins, start] (float rmin, float rmax, const ImColor &c, float th)
    pass  # TODO(autoport): body of the line above
    pin_angle_offset = PI_2 / pins
    for i in range(int(0), int(pins) + 1):
        a = start + (i * pin_angle_offset)
        window.draw_list.add_line((centre[0] + math.cos(a) * rmin, centre[1] + math.sin(a) * rmin), (centre[0] + math.cos(a) * rmax, centre[1] + math.sin(a) * rmax), color_alpha(c, 1.), th)
    draw_circle(bg_radius, bg_color, line_th)
    draw_pins(bg_radius, radius, bg_color, line_th)
    draw_circle(radius, color, line_th)

def spinner_atom(label, radius, thickness, color=white, speed=2.8, elipses=3):
    """SpinnerAtom()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = im.get_time()* speed
    elipses = std.min(elipses, 3)
# TODO(autoport): hand-translate (the rules mangled this line):     draw_rotated_ellipse = [&] (float alpha, float start)
    pass  # TODO(autoport): body of the line above
    alpha = math.fmod(alpha, IM_PI)
    a = radius
    b = radius / 2.
    window.draw_list.path_clear()
    for i in range(int(0), int(num_segments)):
        anga = (i * (PI_2 / (num_segments - 1)))
        xx = a * math.cos(anga) * math.cos(alpha) + b * math.sin(anga) * math.sin(alpha) + centre[0]
        yy = b * math.sin(anga) * math.cos(alpha) - a * math.cos(anga) * math.sin(alpha) + centre[1]
        window.draw_list.path_line_to((xx, yy))
    path_stroke(window.draw_list, color_alpha(color, 1.), thickness, False)
    anga = math.fmod(start, PI_2)
    x = a * math.cos(anga) * math.cos(alpha) + b * math.sin(anga) * math.sin(alpha) + centre[0]
    y = b * math.sin(anga) * math.cos(alpha) - a * math.cos(anga) * math.sin(alpha) + centre[1]
    return ImVec2(x, y)
    ppos = [None] * (3)
    for i in range(int(0), int(elipses)):
        ppos[i % 3] = draw_rotated_ellipse((IM_PI * float(i)/ elipses), start * (1. + 0.1 * i))
    pcolors = [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255)]
    for i in range(int(0), int(elipses)):
        window.draw_list.add_circle_filled(ppos[i], thickness * 2, color_alpha(pcolors[i], 1.), int(num_segments / 3.))

def spinner_pattern_rings(label, radius, thickness, color=white, speed=2.8, elipses=3):
    """SpinnerPatternRings()."""
    # TODO(autoport): for ((int i = 0)
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = im.get_time()* speed
    elipses = std.max(elipses, 1)
# TODO(autoport): hand-translate (the rules mangled this line):     draw_rotated_ellipse = [&] (float alpha, float tr, float y)
    pass  # TODO(autoport): body of the line above
    alpha = math.fmod(alpha, IM_PI)
    a = radius
    b = radius / 2.
    bg_angle_offset = PI_2 / (num_segments - 1)
    c = color_alpha(color, tr)
    window.draw_list.path_clear()
    for i in range(int(0), int(num_segments)):
        anga = (i * bg_angle_offset)
        xx = a * math.cos(anga) * math.cos(alpha) + b * math.sin(anga) * math.sin(alpha) + centre[0]
        yy = b * math.sin(anga) * math.cos(alpha) - a * math.cos(anga) * math.sin(alpha) + centre[1] + y
        window.draw_list.path_line_to((xx, yy))
    path_stroke(window.draw_list, c, thickness, False)
    for _ in range(0):  # TODO(autoport):
        i < elipses
# TODO(autoport): hand-translate (the rules mangled this line):     ++i)
    pass  # TODO(autoport): body of the line above
    h = (0.5 * math.sin(start + (IM_PI / elipses) * i))
    draw_rotated_ellipse(0., 0.1 + (0.9 / elipses) * i, radius * h)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_pattern_eclipse(label, radius, thickness, color=white, spe
# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: pass
pass
# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_pattern_sphere(label, radius, thickness, color=white, spee
pass
def spinner_ring_synchronous(label, radius, thickness, color=white, speed=2.8, elipses=3):
    """SpinnerRingSynchronous()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = math.fmod(im.get_time() * speed, PI_2)
    num_segments = num_segments * 4
    aoffset = math.fmod(im.get_time(), PI_2)
    bofsset = (IM_PI if (aoffset > IM_PI) else aoffset)
    angle_offset = PI_2 / num_segments
    ared_min = 0
    ared = 0
    if aoffset > IM_PI:
        ared_min = aoffset - IM_PI
# TODO(autoport): hand-translate (the rules mangled this line):     draw_ellipse = [&] (float alpha, float y, float r)
    pass  # TODO(autoport): body of the line above
    window.draw_list.path_clear()
    for i in range(int(0), int(num_segments + 1) + 1):
        ared = start + (i * angle_offset)
        if i * angle_offset < ared_min * 2:
            continue
        if i * angle_offset > bofsset * 2.:
            break
        a = r
        b = r * 0.25
        xx = a * math.cos(ared) * math.cos(alpha) + b * math.sin(ared) * math.sin(alpha) + centre[0]
        yy = b * math.sin(ared) * math.cos(alpha) - a * math.cos(ared) * math.sin(alpha) + pos[1] + y
        window.draw_list.path_line_to((xx, yy))
    path_stroke(window.draw_list, color_alpha(color, 1.), thickness, False)
    for i in range(int(0), int(elipses)):
        y = i * (float(size[1] * 0.7) / float(elipses)) + (size[1] * 0.15)
        draw_ellipse(0, y, radius * math.sin((i + 1) * (IM_PI / (elipses + 1))))

def spinner_ring_watermarks(label, radius, thickness, color=white, speed=2.8, elipses=3):
    """SpinnerRingWatermarks()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = im.get_time() * speed
    num_segments = num_segments * 4
    angle_offset = PI_2 / num_segments
# TODO(autoport): hand-translate (the rules mangled this line):     draw_ellipse = [&] (float s, float alpha, float x, float y, float r)
    pass  # TODO(autoport): body of the line above
    aoffset = math.fmod(float(s), PI_2)
    bofsset = (IM_PI if (aoffset > IM_PI) else aoffset)
    ared_min = 0
    ared = 0
    if aoffset > IM_PI:
        ared_min = aoffset - IM_PI
    window.draw_list.path_clear()
    for i in range(int(0), int(num_segments + 1) + 1):
        ared = s + (i * angle_offset)
        if i * angle_offset < ared_min * 2:
            continue
        if i * angle_offset > bofsset * 2.:
            break
        a = r
        b = r * 0.25
        xx = a * math.cos(ared) * math.cos(alpha) + b * math.sin(ared) * math.sin(alpha) + centre[0] + x
        yy = b * math.sin(ared) * math.cos(alpha) - a * math.cos(ared) * math.sin(alpha) + pos[1] + y
        window.draw_list.path_line_to((xx, yy))
    path_stroke(window.draw_list, color_alpha(color, 1.), thickness, False)
    for i in range(int(0), int(elipses)):
        y = i * (float(size[1] * 0.7) / float(elipses)) + (size[1] * 0.15)
        x = -i * (radius / elipses)
        draw_ellipse(start + (i * IM_PI / (elipses * 2)), -PI_DIV_4, x, y, radius)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_rotated_atom(label, radius, thickness, color=white, speed=
pass
# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_rainbow_balls(label, radius, thickness, color, speed, ball
pass
# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_rainbow_shot(label, radius, thickness, color, speed, balls
pass
def spinner_spiral(label, radius, thickness, color=white, speed=2.8, arcs=4):
    """SpinnerSpiral()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = math.fmod(im.get_time() * speed, PI_2)
    a = radius / num_segments
    b = a
    last = centre
    for arc_num in range(int(0), int((num_segments * arcs))):
        angle = (PI_2 / num_segments) * arc_num
        x = centre[0] + (a + b * angle) * math.cos(start + angle)
        y = centre[1] + (a + b * angle) * math.sin(start + angle)
        window.draw_list.add_line(last, (x, y), color_alpha(color, 1.), thickness)
        last = (x, y)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_spiral_eye(label, radius, thickness, color=white, speed=2.
pass
def spinner_blocks(label, radius, thickness, bg, color, speed):
    """SpinnerBlocks()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    lt = (centre[0] - radius, centre[1] - radius)
    offset_block = radius * 2. / 3.
    start = int(ImFmod)(im.get_time() * speed, 8.)
# TODO(autoport): hand-translate (the rules mangled this line):     const ImVec2ih poses[] = {(0, 0), (1, 0), (2, 0), (2, 1), (2, 2), (1, 2), (0, 2), (0, 1)}
    pass  # TODO(autoport): body of the line above
    ti = 0
    for rpos in poses:
        c = (color if (ti == start) else bg)
        window.draw_list.add_rect_filled((lt[0] + rpos[0] * (offset_block), lt[1] + rpos[1] * offset_block), (lt[0] + rpos[0] * (offset_block) + thickness, lt[1] + rpos[1] * offset_block + thickness), color_alpha(c, 1.))
        ti += 1

def spinner_twin_blocks(label, radius, thickness, bg, color, speed):
    """SpinnerTwinBlocks()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    offset_block = radius * 2. / 3.
    lt = (centre[0] - radius - offset_block / 2., centre[1] - radius - offset_block / 2.)
    start = int(ImFmod)(im.get_time() * speed, 8.)
# TODO(autoport): hand-translate (the rules mangled this line):     const ImVec2ih poses[] = {(0, 0), (1, 0), (2, 0), (2, 1), (2, 2), (1, 2), (0, 2), (0, 1)}
    pass  # TODO(autoport): body of the line above
    ti = 0
    for rpos in poses:
        c = (color if (ti == start) else bg)
        window.draw_list.add_rect_filled((lt[0] + rpos[0] * (offset_block), lt[1] + rpos[1] * offset_block), (lt[0] + rpos[0] * (offset_block) + thickness, lt[1] + rpos[1] * offset_block + thickness), color_alpha(c, 1.))
        ti += 1
    lt = ImVec2(centre[0] - radius + offset_block / 2., centre[1] - radius + offset_block / 2.)
    ti = std.size(poses) - 1
    start = int(ImFmod)(im.get_time() * speed * 1.1, 8.)
    for rpos in poses:
        c = (color if (ti == start) else bg)
        window.draw_list.add_rect_filled((lt[0] + rpos[0] * (offset_block), lt[1] + rpos[1] * offset_block), (lt[0] + rpos[0] * (offset_block) + thickness, lt[1] + rpos[1] * offset_block + thickness), color_alpha(c, 1.))
        ti -= 1

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_scale_blocks(label, radius, thickness, color, speed, mode=
pass
def spinner_scale_squares(label, radius, thikness, color, speed):
    """SpinnerScaleSquares()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    lt = (centre[0] - radius, centre[1] - radius)
    offset_block = radius * 2. / 3.
    hside = (thikness / 2.)
# TODO(autoport): hand-translate (the rules mangled this line):     const ImVec2ih poses[] = {(0, 0), (1, 0), (0, 1), (2, 0), (1, 1), (0, 2), (2, 1), (1, 2), (2, 2)}
    pass  # TODO(autoport): body of the line above
    offsets = [0.,    0.8,   0.8,   1.6,   1.6,   1.6,   2.4,   2.4,   3.2]
    ti = 0
    out_h = 0.0
    out_s = 0.0
    out_v = 0.0
    im.color_convert_rg_bto_hsv(color.value[0], color.value[1], color.value[2], out_h, out_s, out_v)
    for rpos in poses:
        c = ImColor.HSV(out_h + offsets[ti], out_s, out_v)
        strict = (0.5 + 0.5 * math.sin((float)-im.get_time() * speed + offsets[ti % 9]))
        side = im_clamp(strict + 0.1, 0.1, 1.) * hside
        window.draw_list.add_rect_filled((lt[0] + hside + (rpos[0] * offset_block) - side, lt[1] + hside + (rpos[1] * offset_block) - side), (lt[0] + hside + (rpos[0] * offset_block) + side, lt[1] + hside + (rpos[1] * offset_block) + side), color_alpha(c, 1.))
        ti += 1

def spinner_squish_square(label, radius, color, speed):
    """SpinnerSquishSquare()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = math.fmod(im.get_time() * speed, PI_2)
    side = math.sin((float)-start) * radius
    type = (1 if (start > IM_PI) else 0)
    if type:
        if start > IM_PI  and  start < IM_PI + PI_DIV_2:
            window.draw_list.add_rect_filled((centre[0] - side, centre[1] - radius), (centre[0] + side, centre[1] + radius), color_alpha(color, 1.))
        else:
            window.draw_list.add_rect_filled((centre[0] - radius, centre[1] - side), (centre[0] + radius, centre[1] + side), color_alpha(color, 1.))
    else:
        if start < PI_DIV_2:
            window.draw_list.add_rect_filled((centre[0] - radius, centre[1] - side), (centre[0] + radius, centre[1] + side), color_alpha(color, 1.))
        else:
            window.draw_list.add_rect_filled((centre[0] - side, centre[1] - radius), (centre[0] + side, centre[1] + radius), color_alpha(color, 1.))

def spinner_arc_polar_fade(label, radius, color=white, speed=2.8, arcs=4, mode=0):
    """SpinnerArcPolarFade()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    arc_angle = PI_2 / float(arcs)
    angle_offset = arc_angle / num_segments
# TODO(autoport): hand-translate (the rules mangled this line):     constexpr float rkoeff[6][3] = {(0.15, 0.1, 0.1), (0.033, 0.15, 0.8), (0.017, 0.25, 0.6), (0.037, 0.1, 0.4), (0.25, 0.1, 0.3), (0.11, 0.1, 0.2)}
    pass  # TODO(autoport): body of the line above
    for arc_num in range(int(0), int(arcs)):
        b = arc_angle * arc_num - PI_DIV_2 - PI_DIV_4
        e = arc_angle * arc_num + arc_angle - PI_DIV_2 - PI_DIV_4
        a = arc_angle * arc_num
        h = (0.6 + 0.3 * math.sin(im.get_time() * (speed * rkoeff[arc_num % 6][2] * 2.) + (2 * rkoeff[arc_num % 6][0])))
        c = color_alpha(color, h)
        c.value[3] = c.value[3] + ease(mode, h, arc_angle)
        window.draw_list.path_clear()
        window.draw_list.path_line_to(centre)
        for i in range(int(0), int(num_segments + 1) + 1):
            ar = arc_angle * arc_num + (i * angle_offset) - PI_DIV_2 - PI_DIV_4
            window.draw_list.path_line_to((centre[0] + math.cos(ar) * radius, centre[1] + math.sin(ar) * radius))
        window.draw_list.path_fill_convex(c)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_arc_polar_radius(label, radius, color=white, speed=2.8, ar
pass
# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_caleidoscope(label, radius, thickness, color=white, speed=
# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: pass
pass
def draw_sectors(start, i):
    """draw_sectors()."""
    return ImColor.HSV(out_h + i * 0.31, out_s, out_v)

def spinner_sine_arcs(label, radius, thickness, color=white, speed=2.8):
    """SpinnerSineArcs()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = math.fmod(im.get_time() * speed, PI_2)
    length = math.fmod(start, IM_PI)
    dangle = math.sin(length) * IM_PI * 0.35
    angle_offset = IM_PI / num_segments
# TODO(autoport): hand-translate (the rules mangled this line):     draw_spring = [&] (float k)
    pass  # TODO(autoport): body of the line above
    arc = 0.
    window.draw_list.path_clear()
    for i in range(int(0), int(num_segments)):
        a = start + (i * angle_offset)
        if math.sin(a) < 0.:
            a = a * -1
        window.draw_list.path_line_to((centre[0] + math.cos(a) * radius, centre[1] + k * math.sin(a) * radius))
        arc = arc + angle_offset
        if arc > dangle:
            break
    path_stroke(window.draw_list, color_alpha(color, 1.), thickness, False)
    draw_spring(1)
    draw_spring(-1)

def spinner_triangles_shift(label, radius, thickness, color=white, bg=half_white, speed=2.8, bars=8):
    """SpinnerTrianglesShift()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    c = color
    lerp_koeff = (math.sin(im.get_time() * speed) + 1.) * 0.5
    c.value[3] = max(0.1, min(lerp_koeff, 1.))
    angle_offset = PI_2 / bars
    start = im.get_time() * speed
    astart = math.fmod(start, angle_offset)
    save_start = start
    start = start - astart
    angle_offset_t = angle_offset * 0.3
    bars = min(bars, 32)
    rmin = radius - thickness
# TODO(autoport): hand-translate (the rules mangled this line):     get_points = [&] (float left, float right, float r1, float r2) . std.array<ImVec2, 4>
    pass  # TODO(autoport): body of the line above
    return ( (centre[0] + math.cos(left) * r1, centre[1] + math.sin(left) * r1), (centre[0] + math.cos(left) * r2, centre[1] + math.sin(left) * r2), (centre[0] + math.cos(right) * r2, centre[1] + math.sin(right) * r2), (centre[0] + math.cos(right) * r1, centre[1] + math.sin(right) * r1) )
    rc = bg
    for i in range(int(0), int(bars)):
        left = start + (i * angle_offset) - angle_offset_t
        right = start + (i * angle_offset) + angle_offset_t
        centera = start - PI_DIV_2 + (i * angle_offset)
        rmul = 1. - im_clamp(abs(centera - save_start), 0., PI_DIV_2) / PI_DIV_2
        rc.value[3] = max(rmul, 0.1)
        rmul = rmul * 1.5
        rmul = max(0.5, rmul)
        r1 = max(rmin * rmul, rmin)
        r2 = max(radius * rmul, radius)
        points = get_points(left, right, r1, r2)
        window.draw_list.add_convex_poly_filled(points.data(), 4, color_alpha(rc, 1.))

def spinner_points_shift(label, radius, thickness, color=white, bg=half_white, speed=2.8, bars=8):
    """SpinnerPointsShift()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    c = color
    lerp_koeff = (math.sin(im.get_time() * speed) + 1.) * 0.5
    c.value[3] = max(0.1, min(lerp_koeff, 1.))
    angle_offset = PI_2 / bars
    start = im.get_time() * speed
    astart = math.fmod(start, angle_offset)
    save_start = start
    start = start - astart
    angle_offset_t = angle_offset * 0.3
    bars = min(bars, 32)
    rmin = radius - thickness
    rc = bg
    for i in range(int(0), int(bars)):
        left = start + (i * angle_offset) - angle_offset_t
        centera = start - PI_DIV_2 + (i * angle_offset)
        rmul = 1. - im_clamp(abs(centera - save_start), 0., PI_DIV_2) / PI_DIV_2
        rc.value[3] = max(rmul, 0.1)
        rmul = rmul * 1. + math.sin(rmul * IM_PI)
        r = max(radius * rmul, radius)
        window.draw_list.add_circle_filled((centre[0] + math.cos(left) * r, centre[1] + math.sin(left) * r), thickness, color_alpha(rc, 1.), num_segments)

def spinner_circular_points(label, radius, thickness, color=white, speed=1.8, lines=8):
    """SpinnerCircularPoints()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = math.fmod(im.get_time() * speed, radius)
    bg_angle_offset = (PI_2) / lines
    for j in range(int(0), int(3)):
        start_offset = j * radius / 3.
        rmax = math.fmod((start + start_offset), radius)
        c = color_alpha(color, math.sin((radius - rmax) / radius * IM_PI))
        for i in range(int(0), int(lines)):
            a = (i * bg_angle_offset)
            window.draw_list.add_circle_filled((centre[0] + math.cos(a) * rmax, centre[1] + math.sin(a) * rmax), thickness, c, num_segments)

def spinner_curved_circle(label, radius, thickness, color=white, speed=2.8, circles=1):
    """SpinnerCurvedCircle()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = math.fmod(im.get_time() * speed, PI_2)
    bg_angle_offset = PI_2 / num_segments
    out_h = 0.0
    out_s = 0.0
    out_v = 0.0
    im.color_convert_rg_bto_hsv(color.value[0], color.value[1], color.value[2], out_h, out_s, out_v)
    for j in range(int(0), int(circles)):
        window.draw_list.path_clear()
        rr = radius - ((radius * 0.5) / circles) * j
        start_a = start * (1.1 * (j+1))
        for i in range(int(0), int(num_segments) + 1):
            a = start_a + (i * bg_angle_offset)
            r = rr - (0.2 * (i % 2)) * rr
            window.draw_list.path_line_to((centre[0] + math.cos(a) * r, centre[1] + math.sin(a) * r))
        path_stroke(window.draw_list, color_alpha(ImColor.HSV(out_h + (j * 1. / circles), out_s, out_v), 1.), thickness, False)

def spinner_mod_circle(label, radius, thickness, color=white, ang_min=1., ang_max=1., speed=2.8):
    """SpinnerModCircle()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    start = math.fmod(im.get_time() * speed, PI_2)
    window.draw_list.path_clear()
    for i in range(int(0), int(90) + 1):
        ax = ((i / 90.) * PI_2 * ang_min)
        ay = ((i / 90.) * PI_2 * ang_max)
        window.draw_list.path_line_to((centre[0] + math.cos(ax) * radius, centre[1] + math.sin(ay) * radius))
    path_stroke(window.draw_list, color_alpha(color, 1.), thickness, False)
    start = ((start * 2.) if (start < IM_PI) else (PI_2 - start) * 2.)
    window.draw_list.add_circle_filled((centre[0] + math.cos(start * ang_min) * radius, centre[1] + math.sin(start * ang_max) * radius), thickness * 4., color_alpha(color, 1.), num_segments)

def spinner_rotate_segments_pulsar(label, radius, thickness, color=white, speed=2.8, arcs=4, layers=1):
    """SpinnerRotateSegmentsPulsar()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    arc_angle = PI_2 / float(arcs)
    angle_offset = arc_angle / num_segments
    r = radius
    reverse = 1.
    bg_angle_offset = pi_2_div(num_segments)
    koeff = pi_div(2 * layers)
    start = im.get_time() * speed
    for num_ring in range(int(0), int(layers)):
        radius_k = math.sin(math.fmod(start + (num_ring * koeff), PI_DIV_2))
        c = color_alpha(color, ((2. - (radius_k * 2.)) if (radius_k > 0.5) else color.value[3]))
        for arc_num in range(int(0), int(arcs)):
            window.draw_list.path_clear()
            for i in range(int(2), int(num_segments - 2) + 1):
                a = start * (1. + 0.1 * num_ring) + arc_angle * arc_num + (i * angle_offset)
                window.draw_list.path_line_to((centre[0] + math.cos(a * reverse) * (r * radius_k), centre[1] + math.sin(a * reverse) * (r * radius_k)))
            path_stroke(window.draw_list, c, thickness, False)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_spline_ang(label, radius, thickness, color=white, bg=white
pass
def circle(i):
    """circle()."""
    a = start - b + (i * angle / num_segments)
    return (math.sin(a) * radius, math.cos(a) * radius)

def spinner_conic_grid(label, radius, thickness, color=white, speed=1., mode=0):
    """SpinnerConicGrid()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    thickness
    W = radius * 2.
    H = W
    g = 0.06 * W
    dot_r = 0.12 * W
    c = color_alpha(color, 1.)
    time = im.get_time() * speed
    ang = math.fmod(time, 1.) * IM_PI
    if mode == 1:
        ang = ang * 2.
    if mode == 2:
        ang = -ang
# TODO(autoport): hand-translate (the rules mangled this line):     ca = math.cos(ang), sa = math.sin(ang)
    pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):     rot = [&](float x, float y) . ImVec2 ( const float dx = x - centre[0], dy = y - centre[1]; return (centre[0] + dx * ca - dy * sa, centre[1] + dx * sa + dy * ca); )
    pass  # TODO(autoport): body of the line above
    l = centre[0] - radius
    t = centre[1] - radius
    r = l + W
    b = t + H
    cx = centre[0]
    cy = centre[1]
# TODO(autoport): hand-translate (the rules mangled this line):     const ImVec2 tiles[4][4] = { { (l, t),       (cx - g, t),    (cx - g, cy - g), (l, cy - g) }, { (cx + g, t),  (r, t),         (r, cy - g),      (cx + g, cy - g) }, { (cx + g, cy + g), (r, cy + g), (r, b),          (cx + g, b) }, { (l, cy + g),  (cx - g, cy + g), (cx - g, b),    (l, b) }, }
    pass  # TODO(autoport): body of the line above
    for i in range(int(0), int(4)):
        window.draw_list.add_quad_filled(rot(tiles[i][0][0], tiles[i][0][1]), rot(tiles[i][1][0], tiles[i][1][1]), rot(tiles[i][2][0], tiles[i][2][1]), rot(tiles[i][3][0], tiles[i][3][1]), c)
    dots = [( cx,            t + dot_r ), ( cx,            b - dot_r ), ( r - dot_r,     cy ), ( l + dot_r,     cy ), ( cx,            cy ),]
    for i in range(int(0), int(5)):
        p = rot(dots[i][0], dots[i][1])
        window.draw_list.add_circle_filled(p, dot_r, c, num_segments)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_arc_arrow(label, radius, thickness, color=white, speed=1.,
pass
# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_orbit_moon(label, radius, thickness, color=white, speed=1.
pass
# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def spinner_conic_wheels(label, radius, thickness, color=white, speed=
pass
def spinner_dot_ring(label, radius, thickness, color=white, speed=1., mode=0):
    """SpinnerDotRing()."""
    pass  # TODO(autoport): macro SPINNER_HEADER(...) invocation dropped -- expand by hand
    color
    g1 = color_alpha((81, 75, 130, 255), 1.)
    g2 = color_alpha((238, 238, 238, 255), 1.)
    N = 12
    ring = radius - thickness
    time = im.get_time() * speed
    spin = math.fmod(time, 2.) / 2. * (2. * IM_PI)
    spin = (spin if (mode == 2) else -spin)
    for k in range(int(0), int(N)):
        a = -IM_PI * 0.5 + spin + k * (2. * IM_PI / N)
        p = (centre[0] + math.cos(a) * ring, centre[1] + math.sin(a) * ring)
        window.draw_list.add_circle_filled(p, thickness, (g1 if (k % 2 == 0) else g2), num_segments)