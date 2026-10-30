bl_info = {
    "name": "Parametric Stairs from Planes",
    "author": "Oliver Kogi + Claude",
    "version": (7, 4, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar (N) > Stairs",
    "description": "Generates parametric stairs (plane-driven or fully parametric straight/L/U/multi-flight/curved/helical/spiral, "
                   "floating, cantilever, suspended, steel, monolithic, zigzag and sawtooth types, layered tread thickness, underlay, finishes, 11 nosing profiles, "
                   "anti-slip strips, metal nosings, LED channels, "
                   "stringers, landings, 33 railing styles, connected rails around corners/turns, newels, "
                   "LED lighting, looks, presets and stats) that follow the planes you model. "
                   "Sloped faces become flights, flat faces become landings.",
    "category": "Add Mesh",
}

import bisect
import json
import math
import os
import struct
import tempfile
import time
import traceback
import uuid
import zlib

import bmesh
import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper
from mathutils import Vector
from mathutils.bvhtree import BVHTree


Z = Vector((0.0, 0.0, 1.0))

# =============================================================================
#  Materials / parts
# =============================================================================

PART_MATS = {
    "Treads": ["PS_Tread"],
    "Risers": ["PS_Riser"],
    "SolidSteps": ["PS_Concrete"],
    "Stringers": ["PS_Stringer"],
    "Landings": ["PS_Landing"],
    "Finish": ["PS_FinishTread", "PS_FinishRiser", "PS_FinishLanding"],
    "Railings": ["PS_Post", "PS_Handrail", "PS_Infill", "PS_Glass"],
    "Lights": ["PS_LED"],
    "Underlay": ["PS_Underlay"],
    "Inlay": ["PS_Inlay"],
    "Strips": ["PS_Strip"],
}

MAT_DEF = {
    "PS_Tread": ((0.50, 0.34, 0.20), 1.0),
    "PS_Riser": ((0.58, 0.42, 0.26), 1.0),
    "PS_Concrete": ((0.62, 0.62, 0.60), 1.0),
    "PS_Stringer": ((0.22, 0.22, 0.25), 1.0),
    "PS_Landing": ((0.60, 0.60, 0.58), 1.0),
    "PS_FinishTread": ((0.78, 0.74, 0.66), 1.0),
    "PS_FinishRiser": ((0.84, 0.82, 0.76), 1.0),
    "PS_FinishLanding": ((0.78, 0.74, 0.66), 1.0),
    "PS_Post": ((0.10, 0.10, 0.12), 1.0),
    "PS_Handrail": ((0.42, 0.28, 0.16), 1.0),
    "PS_Infill": ((0.14, 0.14, 0.16), 1.0),
    "PS_Glass": ((0.62, 0.82, 0.90), 0.30),
    "PS_LED": ((1.0, 0.82, 0.55), 1.0),
    "PS_Underlay": ((0.55, 0.55, 0.52), 1.0),
    "PS_Inlay": ((0.83, 0.60, 0.24), 1.0),
    "PS_Strip": ((0.05, 0.05, 0.055), 1.0),
}

# (colour, metallic, roughness)
_STONE_DARK = ((0.07, 0.07, 0.08), 0.0, 0.25)
_MARBLE = ((0.88, 0.86, 0.82), 0.0, 0.12)
_OAK = ((0.60, 0.43, 0.26), 0.0, 0.45)
_WALNUT = ((0.14, 0.08, 0.05), 0.0, 0.40)
_BRASS = ((0.83, 0.60, 0.24), 1.0, 0.22)
_BLACK_METAL = ((0.02, 0.02, 0.025), 1.0, 0.35)
_CHROME = ((0.85, 0.86, 0.88), 1.0, 0.08)
_WHITE = ((0.90, 0.90, 0.90), 0.0, 0.50)
_CONCRETE = ((0.46, 0.46, 0.45), 0.0, 0.80)
_STEEL = ((0.55, 0.57, 0.60), 1.0, 0.40)
_DARK = ((0.10, 0.10, 0.11), 0.0, 0.50)

LOOKS = {
    "MODERN_BLACK": {"PS_FinishTread": _STONE_DARK, "PS_FinishRiser": _STONE_DARK, "PS_FinishLanding": _STONE_DARK,
                     "PS_Tread": _DARK, "PS_Riser": _DARK, "PS_Concrete": _CONCRETE, "PS_Landing": _CONCRETE,
                     "PS_Stringer": _BLACK_METAL, "PS_Post": _BLACK_METAL, "PS_Handrail": _BLACK_METAL,
                     "PS_Infill": _BLACK_METAL},
    "LUXURY_BRASS": {"PS_FinishTread": _MARBLE, "PS_FinishRiser": _MARBLE, "PS_FinishLanding": _MARBLE,
                     "PS_Tread": _WHITE, "PS_Riser": _WHITE, "PS_Concrete": _WHITE, "PS_Landing": _WHITE,
                     "PS_Stringer": _BLACK_METAL, "PS_Post": _BRASS, "PS_Handrail": _BRASS, "PS_Infill": _BRASS},
    "MARBLE_WALNUT": {"PS_FinishTread": _MARBLE, "PS_FinishRiser": _MARBLE, "PS_FinishLanding": _MARBLE,
                      "PS_Tread": _WALNUT, "PS_Riser": _WALNUT, "PS_Concrete": _WHITE, "PS_Landing": _WHITE,
                      "PS_Stringer": _BLACK_METAL, "PS_Post": _CHROME, "PS_Handrail": _WALNUT, "PS_Infill": _CHROME},
    "SCANDI_OAK": {"PS_FinishTread": _OAK, "PS_FinishRiser": _WHITE, "PS_FinishLanding": _OAK,
                   "PS_Tread": _OAK, "PS_Riser": _WHITE, "PS_Concrete": _WHITE, "PS_Landing": _WHITE,
                   "PS_Stringer": _WHITE, "PS_Post": _WHITE, "PS_Handrail": _OAK, "PS_Infill": _WHITE},
    "INDUSTRIAL": {"PS_FinishTread": _CONCRETE, "PS_FinishRiser": _CONCRETE, "PS_FinishLanding": _CONCRETE,
                   "PS_Tread": _STEEL, "PS_Riser": _STEEL, "PS_Concrete": _CONCRETE, "PS_Landing": _CONCRETE,
                   "PS_Stringer": _STEEL, "PS_Post": _STEEL, "PS_Handrail": _STEEL, "PS_Infill": _STEEL},
}


_BRONZE = ((0.45, 0.30, 0.16), 1.0, 0.30)
_GOLD = ((0.95, 0.75, 0.30), 1.0, 0.15)
_NOIR = ((0.03, 0.03, 0.035), 0.0, 0.10)
_CARRARA = ((0.93, 0.93, 0.92), 0.0, 0.10)
_SMOKED = ((0.28, 0.20, 0.14), 0.0, 0.40)
_TRAVERTINE = ((0.76, 0.70, 0.58), 0.0, 0.55)

LOOKS.update({
    "NOIR_GOLD": {"PS_FinishTread": _NOIR, "PS_FinishRiser": _NOIR, "PS_FinishLanding": _NOIR,
                  "PS_Tread": _DARK, "PS_Riser": _DARK, "PS_Concrete": _DARK, "PS_Landing": _DARK,
                  "PS_Stringer": _BLACK_METAL, "PS_Post": _GOLD, "PS_Handrail": _GOLD, "PS_Infill": _GOLD},
    "CARRARA_BRONZE": {"PS_FinishTread": _CARRARA, "PS_FinishRiser": _CARRARA, "PS_FinishLanding": _CARRARA,
                       "PS_Tread": _WHITE, "PS_Riser": _WHITE, "PS_Concrete": _WHITE, "PS_Landing": _WHITE,
                       "PS_Stringer": _BRONZE, "PS_Post": _BRONZE, "PS_Handrail": _BRONZE, "PS_Infill": _BRONZE},
    "SMOKED_OAK_BLACK": {"PS_FinishTread": _SMOKED, "PS_FinishRiser": _SMOKED, "PS_FinishLanding": _SMOKED,
                         "PS_Tread": _SMOKED, "PS_Riser": _SMOKED, "PS_Concrete": _CONCRETE, "PS_Landing": _CONCRETE,
                         "PS_Stringer": _BLACK_METAL, "PS_Post": _BLACK_METAL, "PS_Handrail": _SMOKED,
                         "PS_Infill": _BLACK_METAL},
    "TRAVERTINE_CHROME": {"PS_FinishTread": _TRAVERTINE, "PS_FinishRiser": _TRAVERTINE, "PS_FinishLanding": _TRAVERTINE,
                          "PS_Tread": _WHITE, "PS_Riser": _WHITE, "PS_Concrete": _WHITE, "PS_Landing": _WHITE,
                          "PS_Stringer": _CHROME, "PS_Post": _CHROME, "PS_Handrail": _CHROME, "PS_Infill": _CHROME},
})
for _k, _v in LOOKS.items():
    _v.setdefault("PS_Underlay", _CONCRETE)
    _v.setdefault("PS_Inlay", _STEEL if _k == "INDUSTRIAL" else _BRASS)
    _v.setdefault("PS_Strip", ((0.04, 0.04, 0.045), 0.0, 0.85))

LOOK_ITEMS = [
    ("MODERN_BLACK", "Modern Black", "Dark stone, black metal"),
    ("LUXURY_BRASS", "Luxury Brass", "Marble with brass rails"),
    ("MARBLE_WALNUT", "Marble & Walnut", "Marble treads, walnut handrail, chrome"),
    ("SCANDI_OAK", "Scandinavian Oak", "Oak and white paint"),
    ("INDUSTRIAL", "Industrial", "Raw concrete and steel"),
    ("NOIR_GOLD", "Noir & Gold", "Polished black stone, gold metal"),
    ("CARRARA_BRONZE", "Carrara & Bronze", "White marble, bronze metal"),
    ("SMOKED_OAK_BLACK", "Smoked Oak & Black", "Dark oak with black steel"),
    ("TRAVERTINE_CHROME", "Travertine & Chrome", "Warm stone with chrome"),
]


def _set_principled(m, col, metallic, rough):
    m.diffuse_color = (col[0], col[1], col[2], m.diffuse_color[3])
    try:
        m.use_nodes = True
        b = m.node_tree.nodes.get("Principled BSDF")
        if b:
            b.inputs["Base Color"].default_value = (col[0], col[1], col[2], 1.0)
            b.inputs["Metallic"].default_value = metallic
            b.inputs["Roughness"].default_value = rough
    except Exception:
        pass


def apply_look(name):
    for mn, (col, met, rough) in LOOKS.get(name, {}).items():
        _set_principled(get_mat(mn), col, met, rough)


def get_mat(name):
    m = bpy.data.materials.get(name)
    if m:
        return m
    col, alpha = MAT_DEF.get(name, ((0.8, 0.8, 0.8), 1.0))
    m = bpy.data.materials.new(name)
    m.diffuse_color = (col[0], col[1], col[2], alpha)
    try:
        m.use_nodes = True
        b = m.node_tree.nodes.get("Principled BSDF")
        if b:
            b.inputs["Base Color"].default_value = (col[0], col[1], col[2], 1.0)
            if name == "PS_LED":
                for key in ("Emission Color", "Emission"):
                    if key in b.inputs:
                        b.inputs[key].default_value = (1.0, 0.82, 0.55, 1.0)
                if "Emission Strength" in b.inputs:
                    b.inputs["Emission Strength"].default_value = 8.0
            if name == "PS_Inlay":
                b.inputs["Metallic"].default_value = 1.0
                b.inputs["Roughness"].default_value = 0.22
            if alpha < 1.0:
                for key in ("Transmission Weight", "Transmission"):
                    if key in b.inputs:
                        b.inputs[key].default_value = 0.9
                if "Roughness" in b.inputs:
                    b.inputs["Roughness"].default_value = 0.05
                if "Alpha" in b.inputs:
                    b.inputs["Alpha"].default_value = 0.5
    except Exception:
        pass
    return m


# =============================================================================
#  Pure-python mesh builder (no bmesh needed for geometry creation)
# =============================================================================

_UV_ON = [True]
_UV_TILES = {"timber": 0.6, "finish": 0.6, "concrete": 1.0, "other": 1.0}
_MAT_CLASS = {"PS_Tread": "timber", "PS_Riser": "timber", "PS_Handrail": "timber",
              "PS_FinishTread": "finish", "PS_FinishRiser": "finish", "PS_FinishLanding": "finish",
              "PS_Concrete": "concrete", "PS_Landing": "concrete", "PS_Underlay": "concrete"}


def _perim(pts):
    out = [0.0]
    n = len(pts)
    for j in range(n):
        out.append(out[-1] + math.dist(pts[j], pts[(j + 1) % n]))
    return out


def _ring_tables(mb, idx):
    """U = distance travelled from the first ring (per vertex), V = unrolled outline length of each ring."""
    P = [[mb.v[i] for i in ring] for ring in idx]
    V = [_perim(r) for r in P]
    U = [[0.0] * len(P[0])]
    for t in range(1, len(P)):
        U.append([U[-1][j] + math.dist(P[t][j], P[t - 1][j]) for j in range(len(P[0]))])
    return U, V


def _quad_uv(U, V, i, j, k):
    jj = (j + 1) % k
    return [(U[i][j], V[i][j]), (U[i][jj], V[i][j + 1]), (U[i + 1][jj], V[i + 1][j + 1]), (U[i + 1][j], V[i + 1][j])]


def _cap_uv(mb, ids):
    """Planar projection for flat faces: horizontal faces follow their longest edge, vertical faces use (horizontal, up)."""
    pts = [Vector(mb.v[i]) for i in ids]
    nv = newell(pts)
    if nv.length < 1e-12:
        return [(0.0, 0.0)] * len(pts)
    nn = nv.normalized()
    if abs(nn.z) > 0.7:
        ub, best = None, -1.0
        for j in range(len(pts)):
            e = pts[(j + 1) % len(pts)] - pts[j]
            e.z = 0.0
            if e.length > best:
                best, ub = e.length, e
        ub = ub.normalized() if best > 1e-9 else Vector((1.0, 0.0, 0.0))
    else:
        ub = nn.cross(Z)
        ub = ub.normalized() if ub.length > 1e-9 else Vector((1.0, 0.0, 0.0))
    vb = nn.cross(ub)
    if abs(nn.z) <= 0.7 and vb.z < 0:
        vb = -vb
    p0 = pts[0]
    return [((p - p0).dot(ub), (p - p0).dot(vb)) for p in pts]


class MB:
    def __init__(self, mats):
        self.mats = list(mats)
        self.v = []
        self.f = []
        self.fm = []
        self.uvh = {}

    def _v(self, p):
        self.v.append((p[0], p[1], p[2]))
        return len(self.v) - 1

    def put(self, face, mat, uv=None):
        if uv is not None:
            self.uvh[len(self.f)] = uv
        self.f.append(tuple(face))
        self.fm.append(mat)

    def prism(self, ring_a, ring_b, mat=0):
        a = [self._v(p) for p in ring_a]
        b = [self._v(p) for p in ring_b]
        n = len(a)
        U, V = _ring_tables(self, [a, b])
        ca = tuple(reversed(a))
        self.put(ca, mat, _cap_uv(self, ca))
        cb = tuple(b)
        self.put(cb, mat, _cap_uv(self, cb))
        for i in range(n):
            j = (i + 1) % n
            self.put((a[i], a[j], b[j], b[i]), mat, _quad_uv(U, V, 0, i, n))


def circle_profile(r, seg=10):
    return [(r * math.cos(2 * math.pi * i / seg), r * math.sin(2 * math.pi * i / seg)) for i in range(seg)]


def rect_profile(w, h):
    return [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]


def sweep(mb, pts, prof, mat=0, closed=False, yoff=0.0):
    """Sweep a 2D profile along a polyline with mitered corners."""
    clean = []
    for p in pts:
        if not clean or (p - clean[-1]).length > 1e-5:
            clean.append(p)
    if closed and len(clean) > 2 and (clean[0] - clean[-1]).length < 1e-5:
        clean.pop()
    pts = clean
    n = len(pts)
    if n < 2:
        return
    if closed and n < 3:
        closed = False
    cnt = n if closed else n - 1
    dirs = []
    for i in range(cnt):
        d = pts[(i + 1) % n] - pts[i]
        dirs.append(d.normalized())
    rings = []
    for i in range(n):
        if closed:
            tp, tn = dirs[i - 1], dirs[i]
        else:
            tp = dirs[i - 1] if i > 0 else dirs[0]
            tn = dirs[i] if i < n - 1 else dirs[-1]
        t = tp + tn
        if t.length < 1e-6:
            t = tn.copy()
        t.normalize()
        side = t.cross(Z)
        if side.length < 1e-6:
            side = Vector((1.0, 0.0, 0.0))
        side.normalize()
        up = side.cross(t)
        up.normalize()
        bend = tn - tp
        sdir = None
        m = 1.0
        if bend.length > 1e-6:
            sdir = bend.normalized()
            m = 1.0 / max(0.35, t.dot(tn))
        ring = []
        for (x, y) in prof:
            q = side * x + up * (y + yoff)
            if sdir is not None:
                q = q + sdir * (q.dot(sdir) * (m - 1.0))
            ring.append(pts[i] + q)
        rings.append(ring)
    idx = [[mb._v(p) for p in ring] for ring in rings]
    k = len(prof)
    m_ = len(idx)
    segs = m_ if closed else m_ - 1
    U, V = _ring_tables(mb, idx + [idx[0]] if closed else idx)
    for i in range(segs):
        a = idx[i]
        b = idx[(i + 1) % m_]
        for j in range(k):
            jj = (j + 1) % k
            mb.put((a[j], a[jj], b[jj], b[j]), mat, _quad_uv(U, V, i, j, k))
    if not closed:
        c0 = tuple(reversed(idx[0]))
        mb.put(c0, mat, _cap_uv(mb, c0))
        c1 = tuple(idx[-1])
        mb.put(c1, mat, _cap_uv(mb, c1))


def vbar(mb, p, z0, z1, wt, wn, t, mat=0):
    if z1 - z0 < 1e-4:
        return
    sd = Z.cross(t)
    if sd.length < 1e-6:
        sd = Vector((0.0, 1.0, 0.0))
    sd.normalize()
    a = t * (wt / 2)
    b = sd * (wn / 2)
    c = [(-a - b), (a - b), (a + b), (-a + b)]
    mb.prism([Vector((p.x, p.y, z0)) + q for q in c], [Vector((p.x, p.y, z1)) + q for q in c], mat)


def vtube(mb, p, z0, z1, r, seg=10, mat=0):
    if z1 - z0 < 1e-4:
        return
    r0 = [Vector((p.x + r * math.cos(2 * math.pi * i / seg), p.y + r * math.sin(2 * math.pi * i / seg), z0)) for i in range(seg)]
    r1 = [Vector((q.x, q.y, z1)) for q in r0]
    mb.prism(r0, r1, mat)


def bar(mb, a, b, w, h, mat=0):
    d = b - a
    if d.length < 1e-6:
        return
    d = d.normalized()
    side = d.cross(Z)
    if side.length < 1e-6:
        side = Vector((1.0, 0.0, 0.0))
    side.normalize()
    up = side.cross(d)
    up.normalize()
    c = [(-side * w / 2 - up * h / 2), (side * w / 2 - up * h / 2), (side * w / 2 + up * h / 2), (-side * w / 2 + up * h / 2)]
    mb.prism([a + q for q in c], [b + q for q in c], mat)


# ---- extra solids: lofts, lathes, balls, cylinders, twisted bars ----------------

def loft(mb, rings, mat=0, caps=True):
    """Connect consecutive rings (same vertex count) with quads, optionally cap both ends."""
    idx = [[mb._v(p) for p in ring] for ring in rings]
    k = len(idx[0])
    U, V = _ring_tables(mb, idx)
    for i in range(len(idx) - 1):
        a, b = idx[i], idx[i + 1]
        for j in range(k):
            jj = (j + 1) % k
            mb.put((a[j], a[jj], b[jj], b[j]), mat, _quad_uv(U, V, i, j, k))
    if caps:
        c0 = tuple(reversed(idx[0]))
        mb.put(c0, mat, _cap_uv(mb, c0))
        c1 = tuple(idx[-1])
        mb.put(c1, mat, _cap_uv(mb, c1))


def poly_ring(cx, cy, z, R, n, ang):
    return [Vector((cx + R * math.cos(ang + 2 * math.pi * i / n),
                    cy + R * math.sin(ang + 2 * math.pi * i / n), z)) for i in range(n)]


def lathe(mb, cx, cy, zr, mat=0, seg=10):
    """zr = [(z, radius), ...] bottom to top."""
    loft(mb, [poly_ring(cx, cy, z, max(r, 1e-4), seg, 0.0) for z, r in zr], mat)


def ball(mb, c, r, mat=0, seg=10, rings=6, dome=False):
    lo = 0.0 if dome else -80.0
    zr = []
    for k in range(rings + 1):
        a = math.radians(lo + (80.0 - lo) * k / rings)
        zr.append((c.z + r * math.sin(a), r * math.cos(a)))
    lathe(mb, c.x, c.y, zr, mat, seg)


def cyl(mb, a, b, r, mat=0, seg=10):
    """Cylinder between two points."""
    d = b - a
    if d.length < 1e-6:
        return
    d = d.normalized()
    u = d.cross(Z)
    if u.length < 1e-6:
        u = Vector((1.0, 0.0, 0.0))
    u.normalize()
    v = d.cross(u)
    ring = [u * (r * math.cos(2 * math.pi * i / seg)) + v * (r * math.sin(2 * math.pi * i / seg)) for i in range(seg)]
    mb.prism([a + q for q in ring], [b + q for q in ring], mat)


def twist_bar(mb, p, z0, z1, w, t, mat=0, turns=1.5, n=10):
    if z1 - z0 < 1e-3:
        return
    ang = math.atan2(t.y, t.x) + math.pi / 4
    R = w / math.sqrt(2)
    loft(mb, [poly_ring(p.x, p.y, z0 + (z1 - z0) * k / n, R, 4, ang + 2 * math.pi * turns * k / n)
              for k in range(n + 1)], mat)


def shape_ring(p, z, size, shape, t, k=1.0):
    ang = math.atan2(t.y, t.x)
    if shape in ("SQUARE", "TAPERED"):
        return poly_ring(p.x, p.y, z, size * k / math.sqrt(2), 4, ang + math.pi / 4)
    if shape == "OCTAGON":
        return poly_ring(p.x, p.y, z, size * k / 2 / math.cos(math.pi / 8), 8, ang + math.pi / 8)
    return poly_ring(p.x, p.y, z, size * k / 2, 14, 0.0)


def build_newel(mb, p, zf, zr, t, P, mat=0):
    """Newel post from the floor (zf) to the handrail top (zr) with optional base and cap."""
    sz = P.newel_size
    shape = P.newel_shape
    top = zr + P.newel_extra
    z = zf
    bsh = "ROUND" if shape == "ROUND" else ("OCTAGON" if shape == "OCTAGON" else "SQUARE")
    if P.newel_base == "PLATE":
        loft(mb, [shape_ring(p, z, sz * 1.7, bsh, t), shape_ring(p, z + 0.012, sz * 1.7, bsh, t)], mat)
        z += 0.012
    elif P.newel_base == "COLLAR":
        h = 0.08
        loft(mb, [shape_ring(p, z, sz * 1.35, bsh, t), shape_ring(p, z + h * 0.7, sz * 1.35, bsh, t),
                  shape_ring(p, z + h, sz, bsh, t)], mat)
        z += h
    k1 = 0.72 if shape == "TAPERED" else 1.0
    loft(mb, [shape_ring(p, z, sz, shape, t), shape_ring(p, top, sz, shape, t, k1)], mat)
    cs = sz * k1
    cap = P.newel_cap
    if cap == "FLAT":
        loft(mb, [shape_ring(p, top, cs * 1.25, bsh, t), shape_ring(p, top + 0.025, cs * 1.25, bsh, t)], mat)
    elif cap == "PYRAMID":
        loft(mb, [shape_ring(p, top, cs * 1.1, bsh, t), shape_ring(p, top + cs * 0.9, cs * 1.1, bsh, t, 0.04)], mat)
    elif cap == "CHAMFER":
        loft(mb, [shape_ring(p, top, cs * 1.15, bsh, t), shape_ring(p, top + 0.02, cs * 1.15, bsh, t),
                  shape_ring(p, top + 0.05, cs * 0.7, bsh, t)], mat)
    elif cap == "BALL":
        ball(mb, Vector((p.x, p.y, top + cs * 0.5)), cs * 0.62, mat, 12, 8)
    elif cap == "DOME":
        ball(mb, Vector((p.x, p.y, top)), cs * 0.75, mat, 14, 6, dome=True)
    elif cap == "FINIAL":
        lathe(mb, p.x, p.y, [(top, cs * 0.6), (top + 0.02, cs * 0.62), (top + 0.035, cs * 0.17), (top + 0.075, cs * 0.17)], mat, 12)
        cz = top + 0.075 + cs * 0.36
        ball(mb, Vector((p.x, p.y, cz)), cs * 0.4, mat, 12, 8)
        lathe(mb, p.x, p.y, [(cz + cs * 0.3, cs * 0.14), (cz + cs * 0.3 + 0.06, 0.003)], mat, 8)



# =============================================================================
#  Railing style catalogue
# =============================================================================

STYLES = [
    dict(id="BAL_SQ", name="Square Balusters", kind="bal", rnd=False, post="sq", hand="rect"),
    dict(id="BAL_RD", name="Round Balusters", kind="bal", rnd=True, post="sq", hand="round"),
    dict(id="HORIZ", name="Horizontal Bars", kind="horiz", rnd=False, post="sq", hand="rect"),
    dict(id="GLASS", name="Glass + Posts", kind="glass", post="rd", hand="round"),
    dict(id="GLASS_CH", name="Glass Channel", kind="glass_ch", post=None, hand="flat"),
    dict(id="CABLE", name="Cable Rail", kind="cable", post="rd", hand="round"),
    dict(id="FLAT", name="Flat Bar Verticals", kind="flat", post="sq", hand="flat"),
    dict(id="DIAG", name="Diagonal Slats", kind="diag", post="sq", hand="rect"),
    dict(id="ZIGZAG", name="Zig-Zag Bar", kind="zig", post="sq", hand="rect"),
    dict(id="WALL", name="Masonry Parapet", kind="wall", post=None, hand="coping", off="flush"),
    dict(id="PANEL", name="Solid Panel", kind="panel", post="sq", hand="flat"),
    dict(id="SLATS", name="Privacy Slats", kind="slats", post="sq", hand="rect"),
    dict(id="PIPE", name="Pipe Rail", kind="pipe", post="rd", hand="round"),
    dict(id="GRID", name="Wire Grid Mesh", kind="grid", post="sq", hand="rect"),
    dict(id="BRACKET", name="Wall Handrail", kind="bracket", post=None, hand="round", off="bracket"),
    # ---- v2 styles ----
    dict(id="TURNED", name="Turned Balusters", kind="turned", post="sq", hand="oval"),
    dict(id="TWIST", name="Twisted Balusters", kind="twist", post="sq", hand="rect"),
    dict(id="STONE_BAL", name="Stone Balustrade", kind="turned", big=True, post="sq", hand="rect"),
    dict(id="GLASS_BTN", name="Glass + Standoffs", kind="glass", post=None, btn=True, clear=0.07, hand="round"),
    dict(id="GLASS_FRL", name="Frameless Glass", kind="glass", post=None, clear=0.03, hand="flat"),
    dict(id="GLASS_MID", name="Glass + Mid Rail", kind="glass", post="rd", mid=True, hand="round"),
    dict(id="GLASS_FRAME", name="Framed Glass", kind="glass", post="sq", frame=True, hand="rect"),
    dict(id="VCABLE", name="Vertical Cable", kind="bal", rnd=True, bs=0.006, sp=0.07, post="rd", hand="round"),
    dict(id="HORIZ_FLAT", name="Flat Slats", kind="horiz", slat=(0.012, 0.055), post="sq", hand="flat"),
    dict(id="HORIZ_ROD", name="Horizontal Rods", kind="horiz", rod=0.008, post="rd", hand="round"),
    dict(id="PICKET", name="Shaker Pickets", kind="flat", fw=0.04, fd=0.018, fsp=0.10, post="sq", hand="rect"),
    dict(id="FINS", name="Wide Fins", kind="flat", fw=0.012, fd=0.09, fsp=0.12, post="sq", hand="flat"),
    dict(id="TUBE_V", name="Vertical Tubes", kind="bal", rnd=True, bs=0.026, sp=0.14, post="rd", hand="round"),
    dict(id="DIAMOND", name="Diamond Lattice", kind="lattice", post="sq", hand="rect"),
    dict(id="RINGS", name="Circle Rings", kind="rings", post="rd", hand="round"),
    dict(id="WAVE", name="Wave Bars", kind="wave", post="sq", hand="round"),
    dict(id="XCROSS", name="Cross Bracing", kind="xcross", post="sq", hand="rect"),
    dict(id="LOUVER", name="Louvered Slats", kind="louver", post="sq", hand="flat"),
]
STYLE_BY_ID = {s["id"]: s for s in STYLES}


def hand_info(st, P):
    k = st["hand"]
    hs = P.hand_size
    if k != "coping" and P.hand_shape != "AUTO":
        k = {"ROUND": "round", "RECT": "rect", "SLIM": "flat", "OVAL": "oval", "CHAMFER": "cham"}.get(P.hand_shape, k)
    if k == "round":
        return hs, hs, circle_profile(hs / 2, 12)
    if k == "oval":
        w, h = hs * 1.35, hs * 0.75
        return w, h, [(w / 2 * math.cos(2 * math.pi * i / 14), h / 2 * math.sin(2 * math.pi * i / 14)) for i in range(14)]
    if k == "cham":
        w, h = hs, hs * 0.8
        c = hs * 0.25
        return w, h, [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2 - c), (w / 2 - c, h / 2),
                      (-w / 2 + c, h / 2), (-w / 2, h / 2 - c)]
    if k == "flat":
        w, h = hs * 1.3, hs * 0.4
    elif k == "coping":
        w, h = P.wall_thk + 0.05, 0.05
    else:
        w, h = hs, hs * 0.8
    return w, h, rect_profile(w, h)


def rail_offset(st, P):
    o = st.get("off", "std")
    if o == "flush":
        return P.wall_thk / 2.0
    if o == "bracket":
        return P.wall_gap
    return P.rail_offset



class Run:
    """A railing run: handrail centre-line polyline + posts + floor lookup."""

    def __init__(self, pts, floor_fn, stair, seg_in, hh, base_off, drop, closed=False):
        self.pts = pts
        self.floor_fn = floor_fn
        self.stair = stair
        self.seg_in = seg_in
        self.hh = hh
        self.base_off = base_off
        self.drop = drop
        self.closed = closed
        self.cum = [0.0]
        for i in range(1, len(pts)):
            a, b = pts[i - 1], pts[i]
            self.cum.append(self.cum[-1] + math.hypot(b.x - a.x, b.y - a.y))
        self.length = self.cum[-1]
        self.posts = []
        self.nopost = set()
        self.free0 = True
        self.free1 = True
        self.conn0 = False
        self.conn1 = False
        self.kind = "landing"
        self.st = None

    def _seg(self, d):
        i = bisect.bisect_right(self.cum, d) - 1
        return max(0, min(i, len(self.pts) - 2))

    def at(self, d):
        i = self._seg(d)
        L = self.cum[i + 1] - self.cum[i]
        t = 0.0 if L < 1e-9 else (d - self.cum[i]) / L
        t = max(0.0, min(1.0, t))
        return self.pts[i] + (self.pts[i + 1] - self.pts[i]) * t

    def tan(self, d):
        i = self._seg(d)
        a, b = self.pts[i], self.pts[i + 1]
        v = Vector((b.x - a.x, b.y - a.y, 0.0))
        return v.normalized() if v.length > 1e-9 else Vector((1.0, 0.0, 0.0))

    def inward(self, d):
        return self.seg_in[min(self._seg(d), len(self.seg_in) - 1)]

    def floor(self, p):
        return self.floor_fn(p)

    def spans(self):
        return list(zip(self.posts[:-1], self.posts[1:]))

    def newel_ds(self, mode, ang):
        """Distances along the run where a newel belongs (ends and/or turns)."""
        out = set()
        m = len(self.pts) - 1
        if m < 1:
            return out
        if not self.closed and mode in ("ENDS", "ALL"):
            out.add(0.0)
            out.add(round(self.length, 6))
        if mode in ("CORNERS", "ALL"):
            dirs = []
            for i in range(m):
                v = Vector((self.pts[i + 1].x - self.pts[i].x, self.pts[i + 1].y - self.pts[i].y, 0.0))
                dirs.append(v.normalized() if v.length > 1e-9 else None)
            rng = range(m) if self.closed else range(1, m)
            for k in rng:
                a, b = dirs[(k - 1) % m], dirs[k]
                if a is None or b is None:
                    continue
                if math.degrees(math.acos(max(-1.0, min(1.0, a.dot(b))))) > ang:
                    out.add(round(self.cum[k], 6))
        return out


def build_rail_style(run, st, P, mb, lmb=None):
    kind = st["kind"]
    hh = run.hh
    base = run.base_off
    ps = P.post_size
    _, _, prof = hand_info(st, P)
    pts = run.pts[:-1] if run.closed else run.pts

    def shifted(dz):
        return [Vector((q.x, q.y, q.z + dz)) for q in pts]

    def sweep_at(dz, profile, mat, yoff=0.0):
        sweep(mb, shifted(dz), profile, mat, run.closed, yoff)

    # ---- handrail, with optional return curls / ball ends on free ends
    hp = shifted(0.0)
    hs_ = P.hand_size
    if not run.closed and len(hp) >= 2 and P.rail_end in ("RETURN", "BALL"):
        ends = []
        if run.free1:
            ends.append((1, hp[-1], hp[-1] - hp[-2]))
        if run.free0:
            ends.append((0, hp[0], hp[0] - hp[1]))
        for w, pe, dv in ends:
            if dv.length < 1e-6:
                continue
            dv = dv.normalized()
            if P.rail_end == "RETURN":
                R = 0.07
                cur = [pe + dv * (R * math.sin(a)) - Z * (R * (1 - math.cos(a)))
                       for a in [math.pi / 2 * k / 6 for k in range(1, 7)]]
                hp = hp + cur if w == 1 else list(reversed(cur)) + hp
            else:
                ball(mb, pe + dv * hs_ * 0.2, hs_ * 0.72, 1, 10, 6)
    sweep(mb, hp, prof, 1, run.closed, 0.0)
    if lmb is not None and P.led_rail:
        sweep(lmb, shifted(0.0), rect_profile(0.016, 0.006), 0, run.closed, -(hh / 2 + 0.004))

    # ---- posts and newels
    shape = st["post"]
    ndx = set()
    if P.newel_mode != "NONE" and kind not in ("wall", "bracket"):
        ndx = run.newel_ds(P.newel_mode, P.corner_angle)
    for d in run.posts:
        if (run.closed and d >= run.length - 1e-6) or round(d, 6) in run.nopost:
            continue
        p = run.at(d)
        zf = run.floor(p)
        if round(d, 6) in ndx:
            build_newel(mb, p, zf, p.z + hh / 2, run.tan(d), P, 0)
        elif shape:
            zt = p.z - hh / 2
            if shape == "sq":
                vbar(mb, p, zf, zt, ps, ps, run.tan(d), 0)
                if P.post_plate:
                    vbar(mb, p, zf, zf + 0.008, ps * 2.2, ps * 2.2, run.tan(d), 0)
            else:
                vtube(mb, p, zf, zt, ps / 2, 12, 0)
                if P.post_plate:
                    vtube(mb, p, zf, zf + 0.008, ps * 1.1, 14, 0)

    spans = run.spans()
    low_off = max(0.2, base - 0.10)
    bs = st.get("bs", P.baluster_size)
    sp = max(0.03, st.get("sp", P.baluster_spacing))

    def span_positions(d0, d1, spacing):
        L = d1 - d0
        cnt = max(1, int(round(L / spacing)))
        return [d0 + L * k / cnt for k in range(1, cnt)]

    if kind == "bal":
        for d0, d1 in spans:
            for d in span_positions(d0, d1, sp):
                p = run.at(d)
                zf = run.floor(p)
                zt = p.z - hh / 2
                if st["rnd"]:
                    vtube(mb, p, zf, zt, bs / 2, 8, 2)
                else:
                    vbar(mb, p, zf, zt, bs, bs, run.tan(d), 2)

    elif kind == "turned":
        big = st.get("big", False)
        rmax = 0.032 if big else 0.018
        prof_t = [(0, 0.55), (0.04, 0.55), (0.07, 1.0), (0.12, 0.62), (0.20, 0.5), (0.30, 0.8), (0.42, 0.5),
                  (0.55, 0.5), (0.68, 0.8), (0.78, 0.5), (0.88, 0.62), (0.93, 1.0), (0.96, 0.55), (1.0, 0.55)]
        for d0, d1 in spans:
            for d in span_positions(d0, d1, 0.15 if big else max(sp, 0.09)):
                p = run.at(d)
                zf = run.floor(p)
                zt = p.z - hh / 2
                if zt - zf < 0.05:
                    continue
                lathe(mb, p.x, p.y, [(zf + (zt - zf) * t, rmax * f) for t, f in prof_t], 0 if big else 2, 10)

    elif kind == "twist":
        for d0, d1 in spans:
            for d in span_positions(d0, d1, sp):
                p = run.at(d)
                twist_bar(mb, p, run.floor(p), p.z - hh / 2, bs * 1.15, run.tan(d), 2, 1.5, 10)

    elif kind in ("horiz", "pipe"):
        N = max(1, P.bar_count) if kind == "horiz" else 2
        for k in range(1, N + 1):
            dz = -low_off * k / N
            if kind == "pipe":
                sweep_at(dz, circle_profile(0.016, 10), 0)
            elif st.get("rod"):
                sweep_at(dz, circle_profile(st["rod"], 8), 2)
            elif st.get("slat"):
                sweep_at(dz, rect_profile(st["slat"][0], st["slat"][1]), 2)
            else:
                sweep_at(dz, rect_profile(0.03, 0.025), 2)

    elif kind == "cable":
        N = max(2, int(low_off / P.cable_gap + 1e-6))
        for k in range(1, N + 1):
            sweep_at(-low_off * k / N, circle_profile(P.cable_dia / 2, 6), 2)

    elif kind in ("glass", "glass_ch", "panel"):
        if kind == "panel":
            thick, mat, clear, gap = 0.02, 2, 0.06, 0.0
        elif kind == "glass":
            thick, mat, clear, gap = P.glass_thk, 3, 0.05, 0.01
        else:
            thick, mat, clear, gap = P.glass_thk, 3, 0.07, 0.012
        clear = st.get("clear", clear)
        inset = ps / 2 if st["post"] else 0.0
        for d0, d1 in spans:
            a = d0 + inset + gap
            b = d1 - inset - gap
            if b - a < 0.05:
                continue
            A, B = run.at(a), run.at(b)
            v = Vector((B.x - A.x, B.y - A.y, 0.0))
            if v.length < 1e-6:
                continue
            nrm = Z.cross(v.normalized())
            sd = nrm * (thick / 2)
            za = Vector((A.x, A.y, A.z - base + clear))
            zb = Vector((B.x, B.y, B.z - base + clear))
            ta = Vector((A.x, A.y, A.z - hh / 2))
            tb = Vector((B.x, B.y, B.z - hh / 2))
            mb.prism([za - sd, zb - sd, tb - sd, ta - sd], [za + sd, zb + sd, tb + sd, ta + sd], mat)
            if st.get("btn"):
                for fr in (0.10, 0.90):
                    for zl in (0.09, None):
                        Q = A + (B - A) * fr
                        qz = Q.z - base + clear + 0.09 if zl else Q.z - hh / 2 - 0.09
                        c0 = Vector((Q.x, Q.y, qz))
                        cyl(mb, c0 - nrm * (thick / 2 + 0.012), c0 + nrm * (thick / 2 + 0.022), 0.014, 0, 10)
            if st.get("frame"):
                for p0, p1 in ((za, zb), (ta, tb), (za, ta), (zb, tb)):
                    bar(mb, p0, p1, 0.02, 0.02, 0)
            if st.get("mid"):
                bar(mb, (za + ta) / 2, (zb + tb) / 2, 0.016, 0.016, 0)
        if kind == "glass_ch":
            sweep_at(-base + 0.03, rect_profile(0.06, 0.07), 0)

    elif kind == "flat":
        fw, fd = st.get("fw", 0.012), st.get("fd", 0.04)
        for d0, d1 in spans:
            for d in span_positions(d0, d1, st.get("fsp", max(0.08, sp * 0.9))):
                p = run.at(d)
                vbar(mb, p, run.floor(p), p.z - hh / 2, fw, fd, run.tan(d), 2)

    elif kind == "slats":
        for d0, d1 in spans:
            for d in span_positions(d0, d1, 0.075):
                p = run.at(d)
                vbar(mb, p, run.floor(p), p.z - hh / 2, 0.045, 0.03, run.tan(d), 2)

    elif kind in ("diag", "lattice"):
        for d0, d1 in spans:
            L = d1 - d0
            lean = min(0.30, L * 0.6)
            da = d0 + 0.04
            step = max(0.08, sp * (1.4 if kind == "diag" else 1.7))
            while da + lean < d1 - 0.03:
                a = run.at(da)
                b = run.at(da + lean)
                bar(mb, Vector((a.x, a.y, a.z - base + 0.08)), Vector((b.x, b.y, b.z - hh / 2)), 0.02, 0.02, 2)
                if kind == "lattice":
                    bar(mb, Vector((a.x, a.y, a.z - hh / 2)), Vector((b.x, b.y, b.z - base + 0.08)), 0.02, 0.02, 2)
                da += step

    elif kind == "zig":
        for d0, d1 in spans:
            L = d1 - d0
            if L < 0.15:
                continue
            cnt = max(2, int(round(L / 0.20)))
            zp = []
            for k in range(cnt + 1):
                d = d0 + L * k / cnt
                q = run.at(d)
                z = q.z - hh / 2 - 0.06 if k % 2 == 0 else q.z - base + 0.08
                zp.append(Vector((q.x, q.y, z)))
            sweep(mb, zp, rect_profile(0.014, 0.014), 2, False)

    elif kind == "rings":
        avail = max(0.2, base - 0.10)
        rows = max(1, int(round(avail / 0.22)))
        D = avail / rows * 0.92
        for d0, d1 in spans:
            L = d1 - d0
            cnt = max(1, int(L / (D * 1.08)))
            for k in range(cnt):
                dc = d0 + L * (k + 0.5) / cnt
                c = run.at(dc)
                t = run.tan(dc)
                for j in range(rows):
                    zc = c.z - hh / 2 - (j + 0.5) * avail / rows
                    ring = [Vector((c.x + t.x * D / 2 * math.cos(2 * math.pi * q / 16),
                                    c.y + t.y * D / 2 * math.cos(2 * math.pi * q / 16),
                                    zc + D / 2 * math.sin(2 * math.pi * q / 16))) for q in range(17)]
                    sweep(mb, ring, circle_profile(0.006, 6), 2, True)

    elif kind == "wave":
        amp = max(0.05, low_off * 0.30)
        for d0, d1 in spans:
            L = d1 - d0
            if L < 0.2:
                continue
            cyc = max(1, int(round(L / 0.5)))
            n = max(16, int(L / 0.03))
            for ph in (0.0, math.pi):
                pp = []
                for k in range(n + 1):
                    q = run.at(d0 + L * k / n)
                    z = q.z - low_off * 0.5 + amp * math.sin(ph + 2 * math.pi * cyc * k / n)
                    pp.append(Vector((q.x, q.y, z)))
                sweep(mb, pp, circle_profile(0.008, 6), 2, False)

    elif kind == "xcross":
        ins = ps / 2 + 0.01 if st["post"] else 0.02
        for d0, d1 in spans:
            L = d1 - d0 - 2 * ins
            if L < 0.15:
                continue
            cnt = max(1, int(round(L / max(0.3, low_off * 0.9))))
            for k in range(cnt):
                a = run.at(d0 + ins + L * k / cnt)
                b = run.at(d0 + ins + L * (k + 1) / cnt)
                alo, ahi = a.z - base + 0.05, a.z - hh / 2 - 0.02
                blo, bhi = b.z - base + 0.05, b.z - hh / 2 - 0.02
                bar(mb, Vector((a.x, a.y, alo)), Vector((b.x, b.y, bhi)), 0.02, 0.02, 2)
                bar(mb, Vector((a.x, a.y, ahi)), Vector((b.x, b.y, blo)), 0.02, 0.02, 2)

    elif kind == "louver":
        N = max(4, int(low_off / 0.07))
        ca, sa_ = math.cos(math.radians(35)), math.sin(math.radians(35))
        lp = [(x * ca - y * sa_, x * sa_ + y * ca) for (x, y) in rect_profile(0.06, 0.008)]
        for k in range(N):
            sweep_at(-low_off * (k + 0.5) / N, lp, 2)

    elif kind == "wall":
        Hb = base - hh / 2 + run.drop
        sweep(mb, shifted(-hh / 2), rect_profile(P.wall_thk, Hb), 2, run.closed, -Hb / 2)

    elif kind == "grid":
        N = max(2, int((low_off - 0.04) / 0.12))
        for k in range(1, N + 1):
            sweep_at(-(0.04 + (low_off - 0.04) * k / N) + 0.04, rect_profile(0.008, 0.008), 2)
        for d0, d1 in spans:
            for d in span_positions(d0, d1, 0.12):
                p = run.at(d)
                vbar(mb, p, p.z - base + 0.05, p.z - hh / 2, 0.008, 0.008, run.tan(d), 2)

    elif kind == "bracket":
        n = max(2, int(math.ceil(run.length / P.bracket_spacing - 1e-6)) + 1)
        for i in range(n):
            d = 0.1 + max(0.0, run.length - 0.2) * i / (n - 1)
            p = run.at(d)
            t = run.tan(d)
            out = -run.inward(d)
            e = p + out * P.wall_gap
            bar(mb, p, e, 0.014, 0.014, 0)
            vbar(mb, e, e.z - 0.03, e.z + 0.03, 0.06, 0.008, t, 0)


def _collect_posts(runs):
    n = 0
    for r in runs:
        _RS.append(dict(kind=r.kind, length=r.length,
                        posts=len([d_ for d_ in r.posts if round(d_, 6) not in r.nopost])))
        for d_ in r.posts:
            if round(d_, 6) in r.nopost:
                continue
            p = r.at(d_)
            n += 1
            _ATT.append(("POST_BASE", "Post %03d base" % n, Vector((p.x, p.y, r.floor_fn(p)))))


def finalize_rails(runs, P, mb, lmb):
    """Join flight rails to landing rails / neighbouring flights, then build everything."""
    flights = [r for r in runs if r.kind == "flight"]
    lands = [r for r in runs if r.kind == "landing"]
    tol, dz_max = 0.6, 0.65
    bridges = []
    done = set()
    for r in flights:
        for w in (0, 1):
            if not (r.conn0 if w == 0 else r.conn1):
                continue
            pa = r.pts[0] if w == 0 else r.pts[-1]
            best, bd = None, tol
            for lr in lands:
                m = len(lr.pts) - (1 if lr.closed else 0)
                for i in range(m):
                    q = lr.pts[i]
                    dd = math.hypot(q.x - pa.x, q.y - pa.y)
                    if dd < bd and abs(q.z - pa.z) < dz_max:
                        best, bd = ("L", lr, i, q), dd
            for r2 in flights:
                if r2 is r:
                    continue
                for w2 in (0, 1):
                    if not (r2.conn0 if w2 == 0 else r2.conn1):
                        continue
                    q = r2.pts[0] if w2 == 0 else r2.pts[-1]
                    dd = math.hypot(q.x - pa.x, q.y - pa.y)
                    if dd < bd and abs(q.z - pa.z) < dz_max:
                        best, bd = ("F", r2, w2, q), dd
            if best is None:
                # no rail to hook into: the flight keeps its own end post and a free end
                (r.nopost.discard(0.0) if w == 0 else r.nopost.discard(round(r.length, 6)))
                continue
            kind, tr, idx, q = best
            if w == 0:
                r.free0 = False
            else:
                r.free1 = False
            if kind == "L":
                m = len(tr.pts) - (1 if tr.closed else 0)
                if not tr.closed and idx == 0:
                    tr.free0 = False
                elif not tr.closed and idx == m - 1:
                    tr.free1 = False
            else:
                if idx == 0:
                    tr.free0 = False
                else:
                    tr.free1 = False
                key = frozenset(((id(r), w), (id(tr), idx)))
                if key in done:
                    continue
                done.add(key)
            if (q - pa).length > 1e-3:
                bridges.append((pa.copy(), q.copy(), r.st))
    _collect_posts(runs)
    for r in runs:
        build_rail_style(r, r.st, P, mb, lmb)
    for pa, pb, st in bridges:
        hw, hh, prof = hand_info(st, P)
        sweep(mb, [pa, pb], prof, 1, False)
        if abs(hw - hh) < 1e-9:
            ball(mb, pa, hw * 0.52, 1, 10, 6)
            ball(mb, pb, hw * 0.52, 1, 10, 6)




# =============================================================================
#  Reading the source mesh
# =============================================================================

def newell(pts):
    n = Vector((0.0, 0.0, 0.0))
    c = len(pts)
    for i in range(c):
        a, b = pts[i], pts[(i + 1) % c]
        n.x += (a.y - b.y) * (a.z + b.z)
        n.y += (a.z - b.z) * (a.x + b.x)
        n.z += (a.x - b.x) * (a.y + b.y)
    return n


def read_mesh(obj):
    me = obj.data
    if obj.mode == "EDIT":
        bm = bmesh.from_edit_mesh(me)
        own = False
    else:
        bm = bmesh.new()
        bm.from_mesh(me)
        own = True
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    bm.verts.index_update()
    bm.faces.index_update()
    mw = obj.matrix_world
    verts = [mw @ v.co for v in bm.verts]
    faces = []
    for f in bm.faces:
        vi = [v.index for v in f.verts]
        n = newell([verts[i] for i in vi])
        area = n.length / 2.0
        nn = n.normalized()
        if nn.z < 0:
            nn = -nn
        faces.append(dict(vi=vi, nn=nn, area=area))
    edges = {}
    mark_layer = bm.edges.layers.int.get("ps_rail_edge")
    solo_layer = bm.edges.layers.int.get("ps_standalone_edge")
    for e in bm.edges:
        a, b = e.verts[0].index, e.verts[1].index
        key = (a, b) if a < b else (b, a)
        edges[key] = dict(count=len(e.link_faces), seam=e.seam, faces=[f.index for f in e.link_faces], railmark=int(e[mark_layer]) if mark_layer else 0, standalone=int(e[solo_layer]) if solo_layer else 0, selected=bool(e.select))
    if own:
        bm.free()
    return verts, faces, edges


# =============================================================================
#  Generation
# =============================================================================

def _style(P, landing=False):
    key = P.landing_style if (landing and P.landing_style != "SAME") else P.railing_style
    return STYLE_BY_ID.get(key, STYLES[0])


def _side_style(P, left, st):
    key = P.rail_style_left if left else P.rail_style_right
    if key == "SAME":
        return st
    return STYLE_BY_ID.get(key, st)


def _off_vec(n_prev, n_next, off):
    if n_prev is None:
        return n_next * off
    if n_next is None:
        return n_prev * off
    den = 1.0 + n_prev.dot(n_next)
    if den < 0.25:
        return n_next * off
    return (n_prev + n_next) / den * off


def _chain_floor(nodes):
    def f(p):
        best, bz = 1e18, nodes[0].z
        for i in range(len(nodes) - 1):
            a, b = nodes[i], nodes[i + 1]
            abx, aby = b.x - a.x, b.y - a.y
            L2 = abx * abx + aby * aby
            t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((p.x - a.x) * abx + (p.y - a.y) * aby) / L2))
            dd = (p.x - (a.x + abx * t)) ** 2 + (p.y - (a.y + aby * t)) ** 2
            if dd < best:
                best, bz = dd, a.z + (b.z - a.z) * t
        return bz
    return f


_STATS = []
_STATS_BY_OBJ = {}


def layer_info(P):
    """Single place that defines every layer of a step: board -> underlay -> finish."""
    ft = P.finish_thk if P.use_finish else 0.0
    rf = P.riser_finish_thk if P.use_finish else 0.0
    ut = P.underlay_thk if P.use_finish else 0.0
    if P.thk_mode == "TOTAL":
        tt = max(0.005, P.tread_thk - ft - ut)
        lt = max(0.02, P.landing_thk - ft - ut)
    else:
        tt, lt = P.tread_thk, P.landing_thk
    return dict(ft=ft, rf=rf, ut=ut, tt=tt, lt=lt, tot=tt + ut + ft, ltot=lt + ut + ft)


def _cut(pts, i, r, segs):
    """Replace corner i of a 2D polygon by a chamfer (segs=1) or a rounded arc."""
    n = len(pts)
    V = Vector((pts[i][0], pts[i][1], 0.0))
    A = Vector((pts[i - 1][0], pts[i - 1][1], 0.0))
    B = Vector((pts[(i + 1) % n][0], pts[(i + 1) % n][1], 0.0))
    r = min(r, (A - V).length * 0.9, (B - V).length * 0.9)
    if r < 1e-5:
        return
    P1 = V + (A - V).normalized() * r
    P2 = V + (B - V).normalized() * r
    if segs <= 1:
        new = [(P1.x, P1.y), (P2.x, P2.y)]
    else:
        new = []
        for k in range(segs + 1):
            t = k / segs
            q = P1 * ((1 - t) ** 2) + V * (2 * (1 - t) * t) + P2 * (t * t)
            new.append((q.x, q.y))
    pts[i:i + 1] = new


def nose_poly(P, sf, sb, zb, zt, drop=0.0):
    """Side profile (s, z) of the outermost tread layer. Returns (points, inset of layers below)."""
    st = P.nosing_style
    thk = max(zt - zb, 1e-4)
    size = max(P.nosing_size, 0.002)
    if st in ("DROP", "DROP_ROUND"):
        lw = min(min(max(0.012, thk * 0.6), 0.04), max(sb - sf - 0.01, 0.005))
        dp = P.lip_depth
        pts = [(sf + lw, zb), (sb, zb), (sb, zt), (sf, zt), (sf, zb - dp), (sf + lw, zb - dp)]
        if st == "DROP_ROUND":
            _cut(pts, 4, min(lw * 0.9, size * 0.5), 3)
            _cut(pts, 3, min(size, thk * 0.98), 5)
        return pts, lw
    if st == "WATERFALL":
        nz = max(P.nosing, 0.0)
        rfw = max(P.riser_finish_thk if P.use_finish else 0.0, 0.012 - nz if nz < 0.012 else 0.0)
        sx = sf - rfw
        lw = nz + rfw
        dp = drop if drop > 1e-4 else P.lip_depth
        return [(sf + nz, zb), (sb, zb), (sb, zt), (sx, zt), (sx, zb - dp), (sf + nz, zb - dp)], nz
    if st == "OVERHANG":
        rl = min(max(P.nosing, 0.0), max(sb - sf - 0.01, 0.0))
        if rl >= 0.004:
            et = min(max(size, 0.008), thk * 0.8)
            return [(sf, zt - et), (sf + rl, zt - et), (sf + rl, zb), (sb, zb), (sb, zt), (sf, zt)], rl
    if st == "BEVEL":
        bw = min(size * 2.0, max(sb - sf - 0.01, 0.004))
        bv = min(size, thk * 0.95)
        return [(sf, zb), (sb, zb), (sb, zt), (sf + bw, zt), (sf, zt - bv)], 0.0
    if st == "UNDERCUT":
        u = min(size * 1.5, max(sb - sf - 0.02, 0.005))
        return [(sf + u, zb), (sb, zb), (sb, zt), (sf, zt), (sf, zb + thk * 0.4)], u
    pts = [(sf, zb), (sb, zb), (sb, zt), (sf, zt)]
    inset = 0.0
    if st == "EASED":
        _cut(pts, 3, min(0.008, thk * 0.5), 2)
    elif st == "ROUNDED":
        _cut(pts, 3, min(size, thk * 0.95), 6)
    elif st == "BULLNOSE":
        r = min(size, thk * 0.49)
        _cut(pts, 3, r, 6)
        _cut(pts, 0, r, 6)
        inset = r
    elif st == "CHAMFER":
        _cut(pts, 3, min(size, thk * 0.95), 1)
    return pts, inset


_WALL_BVHS = []

def _wall_trees(source, P, context):
    if not P.detect_walls:
        return []
    if P.wall_collection:
        candidates = list(P.wall_collection.all_objects)
    else:
        candidates = [o for o in context.scene.objects if "wall" in o.name.lower()]
    trees = []
    dg = context.evaluated_depsgraph_get()
    for ob in candidates:
        if ob == source or ob.type != "MESH" or ob.get("ps_part") is not None or ob.get("ps_rail_source"):
            continue
        ev = ob.evaluated_get(dg)
        mesh = None
        try:
            mesh = ev.to_mesh()
            if not mesh or not mesh.polygons:
                continue
            points = [ev.matrix_world @ v.co for v in mesh.vertices]
            polys = [tuple(f.vertices) for f in mesh.polygons]
            trees.append(BVHTree.FromPolygons(points, polys, all_triangles=False))
        finally:
            if mesh is not None:
                ev.to_mesh_clear()
    return trees

def _edge_allowed(info, a, b, inward, P):
    mark = info.get("railmark", 0)
    if mark == 1:
        return True
    if mark == 2 or info.get("seam", False) or P.rail_edge_mode == "ASSIGNED":
        return False
    if not P.detect_walls or not _WALL_BVHS:
        return True
    outward = -inward.normalized()
    hits = 0
    for t in (0.15, 0.5, 0.85):
        origin = a.lerp(b, t) + Z * P.wall_probe_height + outward * 0.001
        for tree in _WALL_BVHS:
            hit = tree.ray_cast(origin, outward, P.wall_detect_distance + 0.001)
            if hit[0] is not None:
                hits += 1
                break
    return hits < 2

def generate(verts, faces, edges, P):
    parts = {}
    runs = []
    del _STATS[:]
    del _ATT[:]
    del _FL[:]
    del _RS[:]

    def part(name):
        if name not in parts:
            parts[name] = MB(PART_MATS[name])
        return parts[name]

    cos_flat = math.cos(math.radians(P.flat_tol))
    cos_max = math.cos(math.radians(P.max_angle))
    flat, slope = [], []
    for fi, f in enumerate(faces):
        nz = f["nn"].z
        if nz >= cos_flat:
            flat.append(fi)
        elif nz >= cos_max:
            slope.append(fi)

    # group coplanar sloped faces into flights
    parent = {fi: fi for fi in slope}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for key, info in edges.items():
        fs = [x for x in info["faces"] if x in parent]
        if len(fs) == 2 and faces[fs[0]]["nn"].dot(faces[fs[1]]["nn"]) > 0.9995:
            parent[find(fs[0])] = find(fs[1])
    groups = {}
    for fi in slope:
        groups.setdefault(find(fi), []).append(fi)

    Ly = layer_info(P)
    ft, ut, lt = Ly["ft"], Ly["ut"], Ly["lt"]

    for fids in groups.values():
        _flight(verts, faces, edges, fids, P, part, runs)

    # landings: base slab -> underlay -> finish
    for fi in flat:
        pts = [verts[v] for v in faces[fi]["vi"]]
        top = [p - Z * ft for p in pts]
        ubot = [p - Z * (ft + ut) for p in pts]
        bot = [p - Z * (ft + ut + lt) for p in pts]
        part("Landings").prism(bot, ubot, 0)
        if ut > 0:
            part("Underlay").prism(ubot, top, 0)
        if ft > 0:
            part("Finish").prism(top, pts, 2)

    if P.use_rails and P.rail_landing and flat:
        _landing_rails(verts, faces, edges, flat, P, part, runs)

    if runs:
        finalize_rails(runs, P, part("Railings"), part("Lights") if P.led_rail else None)

    return parts




def _flight(verts, faces, edges, fids, P, part, runs):
    Po = P
    kind = P.stair_kind
    P = _kind_view(P)
    zig = kind == "ZIGZAG"
    mono = kind == "MONOLITHIC"
    fset = set(fids)
    nsum = Vector((0.0, 0.0, 0.0))
    for fi in fids:
        nsum += faces[fi]["nn"] * faces[fi]["area"]
    nn = nsum.normalized()
    nz = nn.z
    grad = Z - nn * nz
    d = Vector((grad.x, grad.y, 0.0))
    if d.length < 1e-9:
        return
    d.normalize()
    wv = Vector((-d.y, d.x, 0.0))
    vids = sorted({v for fi in fids for v in faces[fi]["vi"]})
    o = Vector((0.0, 0.0, 0.0))
    for v in vids:
        o += verts[v]
    o /= len(vids)

    S = {}
    for v in vids:
        q = verts[v] - o
        S[v] = (q.x * d.x + q.y * d.y, q.x * wv.x + q.y * wv.y)
    s_min = min(s for s, w in S.values())
    s_max = max(s for s, w in S.values())
    w_cen = (min(w for s, w in S.values()) + max(w for s, w in S.values())) / 2.0
    z0 = min(verts[v].z for v in vids)
    z1 = max(verts[v].z for v in vids)
    H = z1 - z0
    Ls = s_max - s_min
    if H < 1e-4 or Ls < 1e-4:
        return

    # region boundary edges: (a, b, open, connected)
    bedges = []
    for fi in fids:
        vi = faces[fi]["vi"]
        for k in range(len(vi)):
            a, b = vi[k], vi[(k + 1) % len(vi)]
            key = (a, b) if a < b else (b, a)
            info = edges[key]
            others = [x for x in info["faces"] if x != fi]
            if any(x in fset for x in others):
                continue
            edgevec = verts[b] - verts[a]
            inward = Vector((-edgevec.y, edgevec.x, 0.0))
            mid = (verts[a] + verts[b]) * 0.5
            if inward.length > 1e-9 and (o - mid).dot(inward) < 0:
                inward = -inward
            allowed = inward.length > 1e-9 and _edge_allowed(info, verts[a], verts[b], inward, P)
            bedges.append((a, b, info["count"] == 1 and allowed, info["count"] > 1))

    def wr(s):
        s = min(max(s, s_min + 1e-5), s_max - 1e-5)
        lo, hi = 1e18, -1e18
        for a, b, _o, _c in bedges:
            sa, wa = S[a]
            sb, wb = S[b]
            if abs(sb - sa) < 1e-7:
                if abs(s - sa) < 1e-4:
                    lo, hi = min(lo, wa, wb), max(hi, wa, wb)
                continue
            if min(sa, sb) - 1e-7 <= s <= max(sa, sb) + 1e-7:
                w = wa + (wb - wa) * (s - sa) / (sb - sa)
                lo, hi = min(lo, w), max(hi, w)
        if lo > hi:
            ws = [w for _s, w in S.values()]
            return min(ws), max(ws)
        return lo, hi

    def X(s, w, z):
        return Vector((o.x + d.x * s + wv.x * w, o.y + d.y * s + wv.y * w, z))

    def box_s(mb, sf, sb, zbf, zbb, ztf, ztb, mat, ow=0.0):
        lf, hf = wr(sf)
        lb, hb = wr(sb)
        lf -= ow
        hf += ow
        lb -= ow
        hb += ow
        bot = [X(sf, lf, zbf), X(sb, lb, zbb), X(sb, hb, zbb), X(sf, hf, zbf)]
        top = [X(sf, lf, ztf), X(sb, lb, ztb), X(sb, hb, ztb), X(sf, hf, ztf)]
        mb.prism(bot, top, mat)

    def poly_s(mb, pts, mat, ow=0.0):
        """Extrude a side profile (s, z) across the width of the flight."""
        cache = {}
        a, b = [], []
        for (s, z) in pts:
            k = round(s, 5)
            if k not in cache:
                cache[k] = wr(s)
            lo, hi = cache[k]
            a.append(X(s, lo - ow, z))
            b.append(X(s, hi + ow, z))
        mb.prism(a, b, mat)

    # ---- step count
    if P.riser_mode == "HEIGHT":
        n = max(1, int(round(H / max(P.riser_height, 0.02))))
    else:
        n = max(1, P.step_count)
    r = H / n
    g = Ls / n
    slope_e = r / g
    nos = P.nosing
    Ly = layer_info(P)
    ft, rf, ut, tt = Ly["ft"], Ly["rf"], Ly["ut"], Ly["tt"]
    rt = P.riser_thk if P.use_risers else 0.0
    solid = P.structure == "SOLID"
    ow = P.side_overhang
    _STATS.append((n, r, g, H, Ls))
    _lo_, _hi_ = wr((s_min + s_max) / 2.0)
    _FL.append(dict(width=_hi_ - _lo_, n=n, r=r, g=g, z0=z0))
    rounders = ("EASED", "ROUNDED", "BULLNOSE", "CHAMFER", "DROP_ROUND")

    for i in range(1, n + 1):
        Li = z0 + i * r          # finished top of this step
        Ti = Li - ft             # under the finish
        Tb = Ti - ut             # top of the structural board / solid mass
        Lp = z0 + (i - 1) * r
        si = s_min + (i - 1) * g
        sn = si + g
        inset = 0.0
        if ft > 0:
            poly, inset = nose_poly(P, si - nos, sn, Ti, Li, r - ft)
            fex = []
            if _detail_on(P):
                poly, fex = tread_detail(P, poly, Ti, Li)
            poly_s(part("Finish"), poly, 0, ow)
            for pn_, ep_, si_ in fex:
                poly_s(part(pn_), ep_, 0, ow - si_)
        sf = si - nos + inset
        if solid:
            if P.solid_fill:
                zbf = zbb = z0
            else:
                zbf, zbb = Tb - P.waist - r, Tb - P.waist
            if not mono:
                box_s(part("SolidSteps"), si, sn, zbf, zbb, Tb, Tb, 0)
            if ut > 0:
                box_s(part("Underlay"), sf, sn, Tb, Tb, Ti, Ti, 0, ow)
        else:
            back = sn + rt if i < n else sn
            if ft > 0:
                if zig:
                    pass
                elif P.led_channel:
                    bp_, lx_ = led_channel(P, [(sf, Tb - tt), (back, Tb - tt), (back, Tb), (sf, Tb)], Tb - tt, Tb)
                    poly_s(part("Treads"), bp_, 0, ow)
                    for pn_, ep_, si_ in lx_:
                        poly_s(part(pn_), ep_, 0, ow - si_)
                else:
                    box_s(part("Treads"), sf, back, Tb - tt, Tb - tt, Tb, Tb, 0, ow)
                if ut > 0:
                    box_s(part("Underlay"), sf, sn, Tb, Tb, Ti, Ti, 0, ow)
            elif not zig:
                poly, _ins = nose_poly(P, si - nos, back, Tb - tt, Tb)
                bex = []
                if _detail_on(P):
                    poly, bex = tread_detail(P, poly, Tb - tt, Tb)
                if P.led_channel:
                    poly, lx_ = led_channel(P, poly, Tb - tt, Tb)
                    bex = bex + lx_
                poly_s(part("Treads"), poly, 0, ow)
                for pn_, ep_, si_ in bex:
                    poly_s(part(pn_), ep_, 0, ow - si_)
            if P.use_risers:
                zb = z0 if i == 1 else Lp - ft
                box_s(part("Risers"), si, si + rt, zb, zb, Tb - tt, Tb - tt, 0)
        if rf > 0 and (solid or zig or P.use_risers) and P.nosing_style != "WATERFALL":
            ztp = Tb if (solid or zig) else Tb - tt
            box_s(part("Finish"), si - rf, si, Lp, Lp, ztp, ztp, 1)
        if P.nosing_inlay:
            s0 = si - nos + (2 * P.nosing_size if P.nosing_style == "BEVEL" else
                             (P.nosing_size if P.nosing_style in rounders else 0.004)) + 0.003
            box_s(part("Inlay"), s0, s0 + P.inlay_w, Li - 0.002, Li - 0.002, Li + 0.0015, Li + 0.0015, 0,
                  ow - P.inlay_inset)
        if P.led_steps:
            zlow = Tb if solid else Tb - tt
            s1 = si - rf - 0.001
            box_s(part("Lights"), s1 - 0.012, s1, zlow - 0.012, zlow - 0.012, zlow, zlow, 0, ow - 0.03)

    # ---- v3 stair types (floating, cantilever, suspended, steel, monolithic, zigzag, sawtooth)
    if kind != "STANDARD":
        ksides = {"LEFT": [1.0], "RIGHT": [-1.0], "BOTH": [1.0, -1.0]}[Po.support_side]
        kdep, ksw = Po.stringer_depth, Po.stringer_w

        def Tbi(i):
            return z0 + i * r - ft - ut

        def tbot(i):
            return Tbi(i) - tt

        def pitch(s):
            return tbot(1) + slope_e * (s - (s_min + g))

        def s_clip(low):
            sc = s_min + g + (z0 + low - tbot(1)) / slope_e
            return min(max(s_min + 0.02, sc), s_max - 0.1)

        def band_s(mb, pts, o0, o1, side):
            a_, b_ = [], []
            for (s, z) in pts:
                lo, hi = wr(s)
                if side > 0:
                    w0, w1 = hi - o1, hi - o0
                elif side < 0:
                    w0, w1 = lo + o0, lo + o1
                else:
                    mid = (lo + hi) / 2.0
                    w0, w1 = mid - (o1 - o0) / 2.0, mid + (o1 - o0) / 2.0
                a_.append(X(s, w0, z))
                b_.append(X(s, w1, z))
            mb.prism(a_, b_, 0)

        def dedup(pts):
            out = []
            for p_ in pts:
                if not out or abs(p_[0] - out[-1][0]) > 1e-7 or abs(p_[1] - out[-1][1]) > 1e-7:
                    out.append(p_)
            if len(out) > 1 and abs(out[0][0] - out[-1][0]) < 1e-7 and abs(out[0][1] - out[-1][1]) < 1e-7:
                out.pop()
            return out

        def att(k_, label, p_):
            _ATT.append((k_, label, Vector(p_)))

        def bearing():
            lo, hi = wr(s_min)
            att("BEARING_FOOT", "Bearing foot", X(s_min, (lo + hi) / 2, z0))
            lo, hi = wr(s_max)
            att("BEARING_HEAD", "Bearing head", X(s_max, (lo + hi) / 2, z1))

        def sblock(sa_, sb_, wa_, wb_, za_, zb_):
            lo_ = [X(sa_, wa_, za_), X(sb_, wa_, za_), X(sb_, wb_, za_), X(sa_, wb_, za_)]
            hi_ = [X(sa_, wa_, zb_), X(sb_, wa_, zb_), X(sb_, wb_, zb_), X(sa_, wb_, zb_)]
            part("Stringers").prism(lo_, hi_, 0)

        if kind == "MONOLITHIC":
            if Po.solid_fill:
                bot = [(s_min, z0), (s_max, z0)]
            else:
                bot = [(s_min, Tbi(0) - Po.waist), (s_max, Tbi(n) - Po.waist)]
            pts = list(bot) + [(s_max, Tbi(n))]
            for i in range(n, 0, -1):
                si_ = s_min + (i - 1) * g
                pts.append((si_, Tbi(i)))
                if i > 1:
                    pts.append((si_, Tbi(i - 1)))
            poly_s(part("SolidSteps"), dedup(pts), 0, 0.0)
            bearing()

        elif kind == "ZIGZAG":
            t_ = min(Po.fold_t, 0.9 * min(g, r))
            pts = [(s_min, Tbi(0))]
            for i in range(1, n + 1):
                si_ = s_min + (i - 1) * g
                pts += [(si_, Tbi(i)), (si_ + g, Tbi(i))]
            pts.append((s_max, Tbi(n) - t_))
            for i in range(n, 0, -1):
                si_ = s_min + (i - 1) * g
                pts += [(min(si_ + g + t_, s_max), Tbi(i) - t_), (si_ + t_, Tbi(i) - t_)]
            pts.append((s_min + t_, Tbi(0)))
            poly_s(part("SolidSteps"), dedup(pts), 0, 0.0)
            bearing()

        elif kind == "SAWTOOTH":
            def line(s):
                return pitch(s) - kdep
            sc_ = s_min + g + (z0 + kdep - tbot(1)) / slope_e
            if line(s_min) >= z0:
                bot = [(s_min, line(s_min)), (s_max, line(s_max))]
            elif sc_ < s_max - 0.02:
                bot = [(s_min, z0), (sc_, z0), (s_max, line(s_max))]
            else:
                bot = [(s_min, z0), (s_max, z0)]
            pts = list(bot)
            for i in range(n, 0, -1):
                si_ = s_min + (i - 1) * g
                pts += [(si_ + g, tbot(i)), (si_, tbot(i))]
            pts = dedup(pts)
            so = Po.stringer_offset
            if Po.stringer == "CENTER":
                band_s(part("Stringers"), pts, 0.0, ksw, 0)
            else:
                band_s(part("Stringers"), pts, so, so + ksw, 1)
                band_s(part("Stringers"), pts, so, so + ksw, -1)
            for q, sd in enumerate((1, -1) if Po.stringer != "CENTER" else (0,), 1):
                lo, hi = wr(s_min)
                lo2, hi2 = wr(s_max)
                wf_ = (lo + hi) / 2 if sd == 0 else (hi - so - ksw / 2 if sd > 0 else lo + so + ksw / 2)
                wh_ = (lo2 + hi2) / 2 if sd == 0 else (hi2 - so - ksw / 2 if sd > 0 else lo2 + so + ksw / 2)
                att("STRINGER_FOOT", "Stringer %d foot" % q, X(s_min, wf_, bot[0][1]))
                att("STRINGER_HEAD", "Stringer %d head" % q, X(s_max, wh_, bot[-1][1]))

        elif kind == "FLOATING":
            for i in range(1, n + 1):
                si_ = s_min + (i - 1) * g
                za_, zb_ = tbot(i) + tt * 0.3, tbot(i) + tt * 0.7
                lo, hi = wr(si_ + g * 0.5)
                for sd in ksides:
                    tag = "L" if sd > 0 else "R"
                    att("WALL_ANCHOR", "Anchor %02d %s" % (i, tag), X(si_ + g * 0.5, hi if sd > 0 else lo, (za_ + zb_) / 2))
                    if Po.wall_anchor:
                        wa_, wb_ = (hi - Po.embed * 0.5, hi + Po.embed) if sd > 0 else (lo - Po.embed, lo + Po.embed * 0.5)
                        sblock(si_ + 0.2 * g, si_ + 0.8 * g, wa_, wb_, za_, zb_)

        elif kind == "CANTILEVER":
            sa = s_clip(kdep * (1.0 - Po.beam_top))
            lo_a, hi_a = wr(sa)
            lo_b, hi_b = wr(s_max)
            bt = Po.beam_top
            for sd in ksides:
                tag = "L" if sd > 0 else "R"
                wa_ = hi_a + ksw / 2 if sd > 0 else lo_a - ksw / 2
                wb_ = hi_b + ksw / 2 if sd > 0 else lo_b - ksw / 2
                sweep(part("Stringers"), [X(sa, wa_, pitch(sa) + kdep * bt - kdep / 2),
                                          X(s_max, wb_, pitch(s_max) + kdep * bt - kdep / 2)],
                      rect_profile(ksw, kdep), 0)
                att("BEAM_FOOT", "Beam %s foot" % tag, X(sa, wa_, pitch(sa) + kdep * bt - kdep))
                att("BEAM_HEAD", "Beam %s head" % tag, X(s_max, wb_, pitch(s_max) + kdep * bt - kdep))
                for i in range(1, n + 1):
                    sc = s_min + (i - 1) * g + Po.stub_pos * g
                    zlow, zhi = pitch(sc) + kdep * bt, tbot(i)
                    if sc < sa or zhi - zlow < 0.005:
                        continue
                    lo, hi = wr(sc)
                    if sd > 0:
                        sblock(sc, sc + Po.stub_t, hi - Po.embed, hi, zlow, zhi)
                    else:
                        sblock(sc, sc + Po.stub_t, lo, lo + Po.embed, zlow, zhi)
                    att("TREAD_BRACKET", "Bracket %02d %s" % (i, tag), X(sc, hi if sd > 0 else lo, (zlow + zhi) / 2))

        elif kind == "SUSPENDED":
            zc = z1 + Po.susp_top
            for i in range(1, n + 1):
                sc = s_min + (i - 1) * g + g * Po.rod_pos
                lo, hi = wr(sc)
                if Po.rod_layout == "CENTER":
                    rods = [((lo + hi) / 2, "C")]
                else:
                    rods = [((hi - Po.rod_inset) if sd > 0 else (lo + Po.rod_inset), "L" if sd > 0 else "R")
                            for sd in ksides]
                for w_, tag in rods:
                    p0 = X(sc, w_, tbot(i) - 0.012)
                    cyl(part("Stringers"), p0, X(sc, w_, zc), Po.rod_d / 2, 0, 8)
                    cyl(part("Stringers"), p0, p0 + Z * 0.012, Po.rod_d * 1.5, 0, 10)
                    att("ROD_TOP", "Rod %02d %s top" % (i, tag), X(sc, w_, zc))

        elif kind == "STEEL":
            prof = _steel_profile(Po.steel_sec, ksw, kdep, Po.steel_t)
            sa, sb = s_clip(kdep), s_max
            lo_a, hi_a = wr(sa)
            lo_b, hi_b = wr(sb)
            so = Po.stringer_offset + ksw / 2
            if Po.stringer == "CENTER":
                lat = [((lo_a + hi_a) / 2, (lo_b + hi_b) / 2)]
            else:
                lat = [(lo_a + so, lo_b + so), (hi_a - so, hi_b - so)]
            for q, (wa_, wb_) in enumerate(lat, 1):
                sweep(part("Stringers"), [X(sa, wa_, pitch(sa) - kdep / 2), X(sb, wb_, pitch(sb) - kdep / 2)], prof, 0)
                att("STRINGER_FOOT", "Stringer %d foot" % q, X(sa, wa_, pitch(sa) - kdep))
                att("STRINGER_HEAD", "Stringer %d head" % q, X(sb, wb_, pitch(sb) - kdep))
            for i in range(1, n + 1):
                sc = s_min + (i - 1) * g + Po.stub_pos * g
                zlow, zhi = pitch(sc), tbot(i)
                if sc < sa or zhi - zlow < 0.005:
                    continue
                fr = (sc - sa) / max(sb - sa, 1e-6)
                for wa_, wb_ in lat:
                    wc = wa_ + (wb_ - wa_) * fr
                    sblock(sc, sc + Po.stub_t, wc - ksw / 2, wc + ksw / 2, zlow, zhi)

    # ---- stringers
    if not solid and P.stringer != "NONE":
        sw_, dep = P.stringer_w, P.stringer_depth
        layer = ft + ut + tt

        def ztop(s):
            return (z0 + r - layer) + slope_e * (s - (s_min + g + rt))

        s_start = s_min + rt + layer / slope_e
        s_start = min(max(s_start, s_min), s_max - 0.05)
        la, ha = wr(s_start)
        lb, hb = wr(s_max)
        zta, ztb = ztop(s_start), ztop(s_max)
        bands = []
        if P.stringer == "SIDE":
            so = P.stringer_offset
            bands.append(((la + so, la + so + sw_), (lb + so, lb + so + sw_)))
            bands.append(((ha - so - sw_, ha - so), (hb - so - sw_, hb - so)))
        else:
            ca, cb = (la + ha) / 2, (lb + hb) / 2
            bands.append(((ca - sw_, ca + sw_), (cb - sw_, cb + sw_)))
        for (wa0, wa1), (wb0, wb1) in bands:
            bot = [X(s_start, wa0, zta - dep), X(s_max, wb0, ztb - dep), X(s_max, wb1, ztb - dep), X(s_start, wa1, zta - dep)]
            top = [X(s_start, wa0, zta), X(s_max, wb0, ztb), X(s_max, wb1, ztb), X(s_start, wa1, zta)]
            part("Stringers").prism(bot, top, 0)
            _q = bands.index(((wa0, wa1), (wb0, wb1))) + 1
            _ATT.append(("STRINGER_FOOT", "Stringer %d foot" % _q, X(s_start, (wa0 + wa1) / 2, zta - dep)))
            _ATT.append(("STRINGER_HEAD", "Stringer %d head" % _q, X(s_max, (wb0 + wb1) / 2, ztb - dep)))


    # ---- railings
    if not P.use_rails or P.rail_sides == "NONE":
        return

    top_conn = bot_conn = False
    s_mid = (s_min + s_max) / 2
    for a, b, op, conn in bedges:
        e = verts[b] - verts[a]
        e.z = 0.0
        if e.length < 1e-6 or not conn:
            continue
        e.normalize()
        if abs(e.dot(d)) < 0.5:
            if (S[a][0] + S[b][0]) / 2 > s_mid:
                top_conn = True
            else:
                bot_conn = True

    st = _style(P, False)
    hw, hh, _prof = hand_info(st, P)
    off = rail_offset(st, P)
    h = P.rail_height
    base_off = h - hh / 2.0
    L1 = z0 + r
    Ln = z0 + n * r

    def sfloor(p):
        s = (p.x - o.x) * d.x + (p.y - o.y) * d.y
        k = int(math.floor((s - (s_min - nos)) / g)) + 1
        return z0 + max(1, min(n, k)) * r

    def zp(s):
        return min(L1 + slope_e * (s - s_min + nos), Ln)

    s_brk = s_min + (n - 1) * g - nos
    mb = part("Railings")

    for a, b, op, conn in bedges:
        if not op:
            continue
        e = verts[b] - verts[a]
        e.z = 0.0
        if e.length < 1e-6:
            continue
        e.normalize()
        if abs(e.dot(d)) < 0.5:
            continue
        left = (S[a][1] + S[b][1]) / 2 > w_cen
        forced = edges[tuple(sorted((a, b)))].get("railmark", 0) == 1
        if not forced and P.rail_sides == "LEFT" and not left:
            continue
        if not forced and P.rail_sides == "RIGHT" and left:
            continue
        if S[a][0] <= S[b][0]:
            va, vb = verts[a], verts[b]
            sa, sb = S[a][0], S[b][0]
        else:
            va, vb = verts[b], verts[a]
            sa, sb = S[b][0], S[a][0]
        if sb - sa < 1e-4:
            continue
        nrm = Vector((-e.y, e.x, 0.0))
        mid = (va + vb) / 2
        if (o - mid).dot(nrm) < 0:
            nrm = -nrm

        stx = _side_style(P, left, st)
        hh_ = hand_info(stx, P)[1]
        off_ = rail_offset(stx, P)
        bo_ = h - hh_ / 2.0

        def plan(s, va=va, vb=vb, sa=sa, sb=sb, nrm=nrm, off_=off_):
            t = (s - sa) / (sb - sa)
            return va + (vb - va) * t + nrm * off_

        ns = [sa]
        if sa + 1e-3 < s_brk < sb - 1e-3:
            ns.append(s_brk)
        ns.append(sb)
        pts = []
        for s in ns:
            q = plan(s)
            pts.append(Vector((q.x, q.y, zp(s) + h - hh_ / 2.0)))
        run = Run(pts, sfloor, True, [nrm] * (len(pts) - 1), hh_, bo_, r + 0.10, False)
        plen = run.length
        gp = plen / (sb - sa) * g

        def dd(s, sa=sa, sb=sb, plen=plen):
            return (s - sa) / (sb - sa) * plen

        brk = []
        if sa + 1e-3 < s_brk < sb - 1e-3:
            brk.append(dd(s_brk))
        k = max(1, int(round(P.post_spacing / g)))
        opt = []
        for i in range(1, n + 1, k):
            sc = s_min + (i - 1) * g + g / 2
            if sa + 0.3 * g < sc < sb - 0.3 * g:
                opt.append(dd(sc))
        opt = [x for x in opt if all(abs(x - m) > 0.45 * gp for m in brk + [0.0, plen])]
        run.posts = sorted(set(round(x, 6) for x in [0.0, plen] + brk + opt))
        # where the flight joins a landing, the landing railing already carries a post
        if bot_conn:
            run.nopost.add(0.0)
        if top_conn:
            run.nopost.add(round(plen, 6))
        run.kind = "flight"
        run.st = stx
        run.conn0, run.conn1 = bot_conn, top_conn
        runs.append(run)


def _landing_rails(verts, faces, edges, flat, P, part, runs):
    E = []
    adj = {}
    for fi in flat:
        vi = faces[fi]["vi"]
        cen = Vector((0.0, 0.0, 0.0))
        for v in vi:
            cen += verts[v]
        cen /= len(vi)
        for k in range(len(vi)):
            a, b = vi[k], vi[(k + 1) % len(vi)]
            key = (a, b) if a < b else (b, a)
            info = edges[key]
            if info["count"] != 1:
                continue
            e = verts[b] - verts[a]
            e.z = 0.0
            if e.length < 1e-6:
                continue
            e.normalize()
            nrm = Vector((-e.y, e.x, 0.0))
            mid = (verts[a] + verts[b]) / 2
            if (cen - mid).dot(nrm) < 0:
                nrm = -nrm
            if not _edge_allowed(info, verts[a], verts[b], nrm, P):
                continue
            E.append(dict(a=a, b=b, n=nrm))
            adj.setdefault(a, []).append(len(E) - 1)
            adj.setdefault(b, []).append(len(E) - 1)

    st = _style(P, True)
    _, hh, _prof = hand_info(st, P)
    off = rail_offset(st, P)
    h = P.rail_height
    mb = part("Railings")
    used = set()
    for start in range(len(E)):
        if start in used:
            continue
        used.add(start)
        path = [E[start]["a"], E[start]["b"]]
        el = [start]
        while path[-1] != path[0]:
            cur = path[-1]
            nx = [x for x in adj[cur] if x not in used]
            if not nx:
                break
            x = nx[0]
            used.add(x)
            e = E[x]
            other = e["b"] if e["a"] == cur else e["a"]
            path.append(other)
            el.append(x)
        closed = path[-1] == path[0] and len(el) > 2
        if not closed:
            while True:
                cur = path[0]
                nx = [x for x in adj[cur] if x not in used]
                if not nx:
                    break
                x = nx[0]
                used.add(x)
                e = E[x]
                other = e["b"] if e["a"] == cur else e["a"]
                path.insert(0, other)
                el.insert(0, x)
                if path[0] == path[-1] and len(el) > 2:
                    closed = True
                    break
        m = len(el)
        pts = []
        nodes3 = []
        count = m if closed else m + 1
        for k in range(count):
            if closed:
                n_prev, n_next = E[el[(k - 1) % m]]["n"], E[el[k % m]]["n"]
            else:
                n_prev = E[el[k - 1]]["n"] if k > 0 else None
                n_next = E[el[k]]["n"] if k < m else None
            v = verts[path[k]]
            q = v + _off_vec(n_prev, n_next, off)
            pts.append(Vector((q.x, q.y, v.z + h - hh / 2.0)))
            nodes3.append(Vector((q.x, q.y, v.z)))
        if closed:
            pts.append(pts[0].copy())
            nodes3.append(nodes3[0].copy())
        seg_in = [E[x]["n"] for x in el]
        run = Run(pts, _chain_floor(nodes3), False, seg_in, hh, h - hh / 2.0, 0.0, closed)
        posts = []
        for i in range(len(pts) - 1):
            L = run.cum[i + 1] - run.cum[i]
            if L < 1e-6:
                continue
            c = max(1, int(math.ceil(L / max(0.2, P.post_spacing) - 1e-6)))
            for q in range(c):
                posts.append(run.cum[i] + L * q / c)
        posts.append(run.length)
        run.posts = sorted(set(round(x, 6) for x in posts))
        run.kind = "landing"
        run.st = st
        runs.append(run)


# =============================================================================
#  v3 - shared helpers: property views, tread detailing
# =============================================================================

class _PView(object):
    """Read-only view of a property group with a few values overridden."""

    def __init__(self, base, over):
        object.__setattr__(self, "_b", base)
        object.__setattr__(self, "_o", over)

    def __getattr__(self, k):
        o = object.__getattribute__(self, "_o")
        if k in o:
            return o[k]
        return getattr(object.__getattribute__(self, "_b"), k)


_KIND_OVR = {
    "FLOATING": dict(stringer="NONE", use_risers=False, structure="CLOSED"),
    "CANTILEVER": dict(stringer="NONE", use_risers=False, structure="CLOSED"),
    "SUSPENDED": dict(stringer="NONE", use_risers=False, structure="CLOSED"),
    "STEEL": dict(stringer="NONE", structure="CLOSED"),
    "SAWTOOTH": dict(stringer="NONE", structure="CLOSED"),
    "ZIGZAG": dict(stringer="NONE", structure="CLOSED", use_risers=False),
    "MONOLITHIC": dict(stringer="NONE", structure="SOLID"),
}


def _kind_view(P):
    o = _KIND_OVR.get(P.stair_kind)
    return _PView(P, o) if o else P


_META = {}
_ERR = {}
_SIG = {}
_ATT = []
_FL = []
_RS = []
_FL_BY_OBJ = {}
_RAIL_BY_OBJ = {}
_ATT_BY_OBJ = {}
_CHK = {}


def _detail_on(P):
    return P.strip_mode != "NONE" or P.metal_nosing != "NONE"


def _top_edge(poly, z):
    """Index of the longest horizontal edge of a closed (s, z) polygon lying at height z."""
    best, bi = 0.0, None
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        if abs(a[1] - z) < 1e-7 and abs(b[1] - z) < 1e-7:
            L = abs(a[0] - b[0])
            if L > best + 1e-9:
                best, bi = L, i
    return bi


def _insert_notches(poly, z_edge, spans, dz):
    """Cut rectangular notches (signed depth dz) into the long horizontal edge at z_edge."""
    i = _top_edge(poly, z_edge)
    if i is None or not spans:
        return poly
    n = len(poly)
    a, b = poly[i], poly[(i + 1) % n]
    lo, hi = min(a[0], b[0]) + 1e-5, max(a[0], b[0]) - 1e-5
    sp = sorted((s0, s1) for s0, s1 in spans if s0 >= lo and s1 <= hi and s1 - s0 > 1e-5)
    if not sp:
        return poly
    ins = []
    if a[0] > b[0]:
        for s0, s1 in reversed(sp):
            ins += [(s1, z_edge), (s1, z_edge + dz), (s0, z_edge + dz), (s0, z_edge)]
    else:
        for s0, s1 in sp:
            ins += [(s0, z_edge), (s0, z_edge + dz), (s1, z_edge + dz), (s1, z_edge)]
    return poly[:i + 1] + ins + poly[i + 1:]


def _metal_angle(poly, zt, w, h, t):
    """Metal angle that caps the front of a tread: flange of width w on top, face of height h in front."""
    poly = list(poly)
    i = _top_edge(poly, zt)
    if i is None or t < 1e-4:
        return None
    n = len(poly)
    A, B = poly[i], poly[(i + 1) % n]
    if A[0] < B[0]:
        poly = poly[::-1]
        i = _top_edge(poly, zt)
        A, B = poly[i], poly[(i + 1) % n]
    zb = min(p[1] for p in poly)
    h = min(h, 0.85 * (zt - zb)) if zt - zb > 1e-4 else h
    wf = min(w, A[0] - B[0])
    pl = [(B[0] + wf, zt), B]
    zcut = zt - h
    prev = B
    k = (i + 2) % n
    for _ in range(n):
        q = poly[k]
        if q[1] <= zcut + 1e-9:
            if prev[1] - q[1] > 1e-9 and prev[1] > zcut + 1e-9:
                u = (prev[1] - zcut) / (prev[1] - q[1])
                pl.append((prev[0] + (q[0] - prev[0]) * u, zcut))
            break
        pl.append(q)
        prev = q
        k = (k + 1) % n
    m = len(pl)
    if m < 3:
        return None
    nr = []
    for j in range(m - 1):
        dx, dy = pl[j + 1][0] - pl[j][0], pl[j + 1][1] - pl[j][1]
        L = math.hypot(dx, dy)
        nr.append((dy / L, -dx / L) if L > 1e-9 else (0.0, 1.0))
    out = []
    for j in range(m):
        n0 = nr[j - 1] if j > 0 else nr[0]
        n1 = nr[j] if j < m - 1 else nr[-1]
        nx, ny = n0[0] + n1[0], n0[1] + n1[1]
        nl = math.hypot(nx, ny)
        if nl < 1e-6:
            nx, ny, nl = n1[0], n1[1], 1.0
        nx, ny = nx / nl, ny / nl
        c = max(0.3, nx * n1[0] + ny * n1[1])
        out.append((pl[j][0] + nx * t / c, pl[j][1] + ny * t / c))
    return pl + out[::-1]


def tread_detail(P, poly, zb, zt):
    """Anti-slip strips and metal nosing inserts for one tread/finish side profile (s, z).
    Returns (profile with grooves, [(part, polygon, side_inset), ...])."""
    extras = []
    i = _top_edge(poly, zt)
    if i is None:
        return poly, extras
    n = len(poly)
    a, b = poly[i], poly[(i + 1) % n]
    s_back, s_front = max(a[0], b[0]), min(a[0], b[0])
    thk = max(zt - zb, 1e-4)
    cursor = s_front
    cuts = []
    mode = P.metal_nosing
    if mode == "ANGLE":
        m = _metal_angle(poly, zt, P.mn_w, P.mn_h, P.mn_t)
        if m:
            extras.append(("Inlay", m, 0.0))
            cursor = s_front + P.mn_w
    elif mode == "INSERT":
        d = min(max(P.mn_t, 0.004), thk * 0.8)
        s0 = s_front + 0.004
        s1 = s0 + P.mn_w
        if s1 < s_back - 0.01:
            cuts.append(((s0, s1), d, 0.0, "Inlay", P.inlay_inset))
            cursor = s1
    if P.strip_mode != "NONE":
        d = min(P.strip_depth, thk * 0.8)
        rc = 0.0 if P.strip_mode == "FLUSH" else min(P.strip_recess, d * 0.6)
        for k in range(P.strip_n):
            s0 = cursor + P.strip_off + k * (P.strip_w + P.strip_gap)
            s1 = s0 + P.strip_w
            if s1 > s_back - 0.01 or d < 0.002:
                break
            cuts.append(((s0, s1), d, rc, "Strips", P.strip_inset))
    groups = {}
    for (s0, s1), d, rc, pn, ins in cuts:
        groups.setdefault(round(d, 6), []).append((s0, s1))
        extras.append((pn, [(s0, zt - d), (s1, zt - d), (s1, zt - rc), (s0, zt - rc)], ins))
    for d, spans in groups.items():
        poly = _insert_notches(poly, zt, spans, -d)
    return poly, extras


def led_channel(P, poly, zbot, ztop):
    """Groove along the underside of a tread near its front, plus the LED strip that sits in it."""
    i = _top_edge(poly, zbot)
    if i is None:
        return poly, []
    n = len(poly)
    a, b = poly[i], poly[(i + 1) % n]
    lo, hi = min(a[0], b[0]), max(a[0], b[0])
    d = min(P.led_d, (ztop - zbot) * 0.6)
    s0 = lo + 0.015
    s1 = s0 + P.led_w
    if s1 > hi - 0.01 or d < 0.003:
        return poly, []
    poly = _insert_notches(poly, zbot, [(s0, s1)], d)
    led = [(s0 + 0.002, zbot + d - 0.004), (s1 - 0.002, zbot + d - 0.004),
           (s1 - 0.002, zbot + d - 0.0005), (s0 + 0.002, zbot + d - 0.0005)]
    return poly, [("Lights", led, 0.03)]


def _steel_profile(sec, w, h, t):
    if sec == "PLATE":
        return rect_profile(t, h)
    if sec == "CHANNEL":
        x, y = w / 2, h / 2
        t = min(t, w * 0.4, h * 0.4)
        return [(-x, -y), (x, -y), (x, -y + t), (-x + t, -y + t), (-x + t, y - t), (x, y - t), (x, y), (-x, y)]
    return rect_profile(w, h)


def loft_w(mb, rings, mat=0, caps=True, tol=1e-6):
    """Loft rings into one welded solid (shared vertices, degenerate faces dropped)."""
    key = {}

    def vid(p):
        k = (int(round(p[0] / tol)), int(round(p[1] / tol)), int(round(p[2] / tol)))
        i = key.get(k)
        if i is None:
            i = mb._v(p)
            key[k] = i
        return i

    idx = [[vid(p) for p in ring] for ring in rings]
    k = len(idx[0])

    def add(f, uvq=None):
        ff = []
        for i in f:
            if not ff or ff[-1] != i:
                ff.append(i)
        if len(ff) > 1 and ff[0] == ff[-1]:
            ff.pop()
        if len(ff) < 3 or len(set(ff)) != len(ff):
            return
        if newell([Vector(mb.v[i]) for i in ff]).length < 1e-9:
            return
        uv = None
        if uvq is not None:
            m_ = {}
            for vid, q in zip(f, uvq):
                m_.setdefault(vid, q)
            uv = [m_[i] for i in ff]
        mb.put(ff, mat, uv)

    U, V = _ring_tables(mb, idx)
    for i in range(len(idx) - 1):
        a, b = idx[i], idx[i + 1]
        for j in range(k):
            jj = (j + 1) % k
            add((a[j], a[jj], b[jj], b[j]), _quad_uv(U, V, i, j, k))
    if caps:
        add(list(reversed(idx[0])))
        add(idx[-1])


# =============================================================================
#  v3 - parametric engine (floor height, going, riser, width and landings drive the geometry)
# =============================================================================

def _solve(P, H, nfl):
    """Number of risers N and exact riser height r so that N * r == H (reaches the upper floor)."""
    if P.riser_mode == "HEIGHT":
        N = int(round(H / max(P.riser_height, 0.02)))
    else:
        N = max(1, P.step_count) * nfl
    N = max(N, nfl, 1)
    return N, H / N


def _split(N, nfl, frac):
    if nfl <= 1:
        return [N]
    if nfl == 2:
        a = min(N - 1, max(1, int(round(N * frac))))
        return [a, N - a]
    base, rem = divmod(N, nfl)
    return [base + (1 if i < rem else 0) for i in range(nfl)]


class _VM:
    """Welded vertex/face registry used to build the virtual source plane."""

    def __init__(self):
        self.v, self.k, self.f = [], {}, []

    def vid(self, p):
        key = (round(p.x, 5) + 0.0, round(p.y, 5) + 0.0, round(p.z, 5) + 0.0)
        i = self.k.get(key)
        if i is None:
            i = len(self.v)
            self.k[key] = i
            self.v.append(Vector((p.x, p.y, p.z)))
        return i

    def face(self, pts):
        ids = []
        for p in pts:
            i = self.vid(p)
            if not ids or ids[-1] != i:
                ids.append(i)
        if len(ids) > 1 and ids[0] == ids[-1]:
            ids.pop()
        if len(ids) >= 3:
            self.f.append(ids)

    def finish(self):
        faces, edges = [], {}
        for fi, vi in enumerate(self.f):
            nv = newell([self.v[i] for i in vi])
            nn = nv.normalized() if nv.length > 1e-12 else Z.copy()
            if nn.z < 0:
                nn = -nn
            faces.append(dict(vi=vi, nn=nn, area=nv.length / 2.0))
            for k in range(len(vi)):
                a, b = vi[k], vi[(k + 1) % len(vi)]
                key = (a, b) if a < b else (b, a)
                e = edges.setdefault(key, dict(count=0, seam=False, faces=[]))
                e["count"] += 1
                e["faces"].append(fi)
        return self.v, faces, edges


def _ref_z(ob):
    if ob.type in {"MESH", "CURVE", "SURFACE", "FONT"} and ob.bound_box:
        mw = ob.matrix_world
        zs = [(mw @ Vector(c)).z for c in ob.bound_box]
        return sum(zs) / len(zs)
    return ob.matrix_world.translation.z


def _levels(obj, P):
    """Lower floor level and floor-to-floor height, from reference planes when they are set."""
    z0 = obj.matrix_world.translation.z
    H = P.floor_height
    lo, up = P.lower_ref, P.upper_ref
    if lo is not None:
        z0 = _ref_z(lo) + P.lower_level_offset
    if up is not None:
        H = _ref_z(up) + P.upper_level_offset - z0
    return z0, H


def build_virtual(P, mw, z0, H):
    """Virtual source plane (flights = sloped faces, landings = flat faces) for straight / L / U / multi stairs."""
    rz = mw.to_euler("XYZ").z
    d = Vector((-math.sin(rz), math.cos(rz), 0.0))
    ww = Vector((-d.y, d.x, 0.0))
    loc = Vector((mw.translation.x, mw.translation.y, 0.0))
    W, g = P.st_width, P.going
    lay = P.layout
    if lay == "L_SHAPED":
        nfl, turn = 2, "QUARTER"
    elif lay == "U_SHAPED":
        nfl, turn = 2, "SWITCHBACK"
    elif lay == "MULTI":
        nfl, turn = P.flight_count, P.multi_turn
    else:
        nfl, turn = 1, "STRAIGHT"
    N, r = _solve(P, H, nfl)
    nfl = min(nfl, N)
    counts = _split(N, nfl, P.split)
    sgn = 1.0 if P.turn_dir == "LEFT" else -1.0
    lw = max(W, P.land_w)
    Dl = P.land_d if P.land_d > 0.05 else W
    E = P.end_land_d
    vm = _VM()

    def at(base, dd, a, ww_, b, z):
        return Vector((base.x + dd.x * a + ww_.x * b, base.y + dd.y * a + ww_.y * b, z))

    pos, dd, wl, z = loc.copy(), d.copy(), ww.copy(), z0
    if P.lower_land:
        vm.face([at(pos, dd, -E, wl, -lw / 2, z), at(pos, dd, -E, wl, lw / 2, z), at(pos, dd, 0, wl, lw / 2, z),
                 at(pos, dd, 0, wl, W / 2, z), at(pos, dd, 0, wl, -W / 2, z), at(pos, dd, 0, wl, -lw / 2, z)])
    for fi, n in enumerate(counts):
        L, Hf = n * g, n * r
        Pe = pos + dd * L
        vm.face([at(pos, dd, 0, wl, -W / 2, z), at(pos, dd, 0, wl, W / 2, z),
                 at(Pe, dd, 0, wl, W / 2, z + Hf), at(Pe, dd, 0, wl, -W / 2, z + Hf)])
        z += Hf
        if fi == nfl - 1:
            if P.upper_land:
                vm.face([at(Pe, dd, 0, wl, -lw / 2, z), at(Pe, dd, 0, wl, -W / 2, z), at(Pe, dd, 0, wl, W / 2, z),
                         at(Pe, dd, 0, wl, lw / 2, z), at(Pe, dd, E, wl, lw / 2, z), at(Pe, dd, E, wl, -lw / 2, z)])
            break
        ts = wl * sgn
        if turn == "STRAIGHT":
            vm.face([at(Pe, dd, 0, wl, -lw / 2, z), at(Pe, dd, 0, wl, -W / 2, z), at(Pe, dd, 0, wl, W / 2, z),
                     at(Pe, dd, 0, wl, lw / 2, z), at(Pe, dd, Dl, wl, lw / 2, z), at(Pe, dd, Dl, wl, -lw / 2, z)])
            pos = Pe + dd * Dl
        elif turn == "QUARTER":
            D2 = max(Dl, W)
            side = []
            if sgn > 0:
                side = [at(Pe, dd, D2 - W, wl, lw / 2, z)]
                poly = [at(Pe, dd, 0, wl, -lw / 2, z), at(Pe, dd, 0, wl, -W / 2, z), at(Pe, dd, 0, wl, W / 2, z),
                        at(Pe, dd, 0, wl, lw / 2, z)] + side + [at(Pe, dd, D2, wl, lw / 2, z),
                                                                  at(Pe, dd, D2, wl, -lw / 2, z)]
            else:
                poly = [at(Pe, dd, 0, wl, -lw / 2, z), at(Pe, dd, 0, wl, -W / 2, z), at(Pe, dd, 0, wl, W / 2, z),
                        at(Pe, dd, 0, wl, lw / 2, z), at(Pe, dd, D2, wl, lw / 2, z),
                        at(Pe, dd, D2, wl, -lw / 2, z), at(Pe, dd, D2 - W, wl, -lw / 2, z)]
            vm.face(poly)
            npos = at(Pe, dd, D2 - W / 2, wl, sgn * lw / 2, z)
            ndd = ts.copy()
            pos, dd = Vector((npos.x, npos.y, 0.0)), ndd
            wl = Vector((-dd.y, dd.x, 0.0))
        else:  # SWITCHBACK
            gap = P.well_gap
            D2 = max(Dl, 0.6)
            offs = [-W / 2, W / 2, W / 2 + gap, 1.5 * W + gap]
            near = [at(Pe, dd, 0, ts, o, z) for o in offs]
            far = [at(Pe, dd, D2, ts, o, z) for o in (offs[3], offs[0])]
            vm.face(near + far)
            npos = at(Pe, dd, 0, ts, W + gap, z)
            pos = Vector((npos.x, npos.y, 0.0))
            dd = -dd
            wl = Vector((-dd.y, dd.x, 0.0))
    verts, faces, edges = vm.finish()
    meta = dict(N=N, r=r, g=g, counts=counts, H=H, rise=N * r, W=W, flights=len(counts),
                landing=Dl if nfl > 1 else E)
    return verts, faces, edges, meta


def _generate_param(obj, name):
    P = obj.pstairs
    z0, H = _levels(obj, P)
    if H < 0.05:
        raise ValueError("floor-to-floor height must be above 5 cm")
    if P.layout in ("CURVED", "HELICAL", "SPIRAL"):
        return generate_curved(obj.matrix_world, P, z0, H, name)
    verts, faces, edges, meta = build_virtual(P, obj.matrix_world, z0, H)
    PV = _PView(P, dict(riser_mode="HEIGHT", riser_height=meta["r"]))
    parts = generate(verts, faces, edges, PV)
    _META[name] = meta
    return parts


# =============================================================================
#  v3 - curved, helical and spiral stairs
# =============================================================================

def _polar(c, rho, th, z):
    return Vector((c.x + rho * math.cos(th), c.y + rho * math.sin(th), z))


def _cnt_edges(poly, rho, maxang=math.radians(5.0)):
    cnt = []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        if abs(a[1] - b[1]) < 1e-9:
            cnt.append(max(1, int(math.ceil(abs(b[0] - a[0]) / rho / maxang - 1e-9))))
        else:
            cnt.append(1)
    return cnt


def _refine(poly, cnt):
    out = []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        out.append(a)
        for k in range(1, cnt[i]):
            t = k / cnt[i]
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out


def generate_curved(mw, P, z0, H, name):
    del _STATS[:]
    del _ATT[:]
    del _FL[:]
    del _RS[:]
    parts = {}
    runs = []

    def part(nm):
        if nm not in parts:
            parts[nm] = MB(PART_MATS[nm])
        return parts[nm]

    lay = P.layout
    c = Vector((mw.translation.x, mw.translation.y, 0.0))
    th0 = mw.to_euler("XYZ").z
    sgn = 1.0 if P.turn_dir == "LEFT" else -1.0
    if lay == "SPIRAL":
        Ri = max(P.pole_r, 0.02)
        Ro = max(P.spiral_r, Ri + 0.25)
    else:
        Ri = max(P.curve_radius, 0.02)
        Ro = Ri + P.st_width
    if P.riser_mode == "HEIGHT":
        N = max(1, int(round(H / max(P.riser_height, 0.02))))
    else:
        N = max(1, P.step_count)
    r = H / N
    dA = math.radians(P.step_ang) if lay == "SPIRAL" else math.radians(P.sweep) / N
    dA = min(dA, math.radians(120.0))
    rm = (Ri + Ro) / 2.0
    gw = dA * rm
    kc = P.stair_kind if P.stair_kind in ("FLOATING", "CANTILEVER", "SUSPENDED", "STEEL", "MONOLITHIC") else "STANDARD"
    V = _PView(P, _KIND_OVR[kc]) if kc != "STANDARD" else P
    Ly = layer_info(V)
    ft, rf, ut, tt = Ly["ft"], Ly["rf"], Ly["ut"], Ly["tt"]
    rt = V.riser_thk if V.use_risers else 0.0
    nos, ow = V.nosing, V.side_overhang
    solid = V.structure == "SOLID"
    rin, rout = max(Ri - ow, 0.01), Ro + ow
    rounders = ("EASED", "ROUNDED", "BULLNOSE", "CHAMFER", "DROP_ROUND")
    _STATS.append((N, r, gw, H, N * gw))

    def rpts(poly, rho, af):
        return [_polar(c, rho, af + sgn * s / rho, z) for s, z in poly]

    def lloft(pn, fn, af, r_in, r_out, mat=0):
        rmid = (r_in + r_out) / 2.0
        cnt = _cnt_edges(fn(rmid), rmid)
        rings = [rpts(_refine(fn(rho), cnt), rho, af) for rho in (r_in, r_out)]
        loft(part(pn), rings, mat, True)

    def rect(s0, s1, zb, zt):
        return [(s0, zb), (s1, zb), (s1, zt), (s0, zt)]

    def zl(i):          # finished level of step i
        return z0 + i * r

    for i in range(1, N + 1):
        Li = zl(i)
        Ti = Li - ft
        Tb = Ti - ut
        Lp = zl(i - 1)
        af = th0 + sgn * (i - 1) * dA
        inset = 0.0
        if ft > 0:
            def fx(rho, Ti=Ti, Li=Li):
                poly, ins = nose_poly(V, -nos, dA * rho, Ti, Li, r - ft)
                ex = []
                if _detail_on(V):
                    poly, ex = tread_detail(V, poly, Ti, Li)
                return poly, ins, ex
            p_in, inset, ex_in = fx(rin)
            lloft("Finish", lambda rho: fx(rho)[0], af, rin, rout, 0)
            for j, (pn, _pp, si_) in enumerate(ex_in):
                lloft(pn, lambda rho, j=j: fx(rho)[2][j][1], af, rin + si_, rout - si_, 0)
        sf = -nos + inset
        sn = lambda rho: dA * rho
        if not solid:
            back = (lambda rho: dA * rho + rt) if i < N else sn
            if ft > 0:
                def bp(rho, Tb=Tb, back=back, sf=sf):
                    poly = rect(sf, back(rho), Tb - tt, Tb)
                    ex = []
                    if V.led_channel:
                        poly, ex = led_channel(V, poly, Tb - tt, Tb)
                    return poly, ex
                lloft("Treads", lambda rho: bp(rho)[0], af, rin, rout, 0)
                for j, (pn, _pp, si_) in enumerate(bp(rin)[1]):
                    lloft(pn, lambda rho, j=j: bp(rho)[1][j][1], af, rin + si_, rout - si_, 0)
                if ut > 0:
                    lloft("Underlay", lambda rho: rect(sf, sn(rho), Ti, Tb), af, rin, rout, 0)
            else:
                def bq(rho, Tb=Tb, back=back):
                    poly, _i = nose_poly(V, -nos, back(rho), Tb - tt, Tb)
                    ex = []
                    if _detail_on(V):
                        poly, ex = tread_detail(V, poly, Tb - tt, Tb)
                    if V.led_channel:
                        poly, lx = led_channel(V, poly, Tb - tt, Tb)
                        ex = ex + lx
                    return poly, ex
                lloft("Treads", lambda rho: bq(rho)[0], af, rin, rout, 0)
                for j, (pn, _pp, si_) in enumerate(bq(rin)[1]):
                    lloft(pn, lambda rho, j=j: bq(rho)[1][j][1], af, rin + si_, rout - si_, 0)
            if V.use_risers:
                zb = z0 if i == 1 else Lp - ft
                lloft("Risers", lambda rho, zb=zb, Tb=Tb: rect(0.0, rt, zb, Tb - tt), af, Ri, Ro, 0)
        elif ut > 0:
            lloft("Underlay", lambda rho: rect(sf, sn(rho), Ti, Tb), af, rin, rout, 0)
        if rf > 0 and (solid or V.use_risers) and V.nosing_style != "WATERFALL":
            ztp = Tb if solid else Tb - tt
            lloft("Finish", lambda rho, ztp=ztp, Lp=Lp: rect(-rf, 0.0, Lp, ztp), af, Ri, Ro, 1)
        if V.nosing_inlay:
            s0 = -nos + (2 * V.nosing_size if V.nosing_style == "BEVEL" else
                         (V.nosing_size if V.nosing_style in rounders else 0.004)) + 0.003
            lloft("Inlay", lambda rho, Li=Li, s0=s0: rect(s0, s0 + V.inlay_w, Li - 0.002, Li + 0.0015), af,
                  rin + V.inlay_inset, rout - V.inlay_inset, 0)
        if V.led_steps:
            zlow = Tb if solid else Tb - tt
            s1 = -rf - 0.001
            lloft("Lights", lambda rho, zlow=zlow, s1=s1: rect(s1 - 0.012, s1, zlow - 0.012, zlow), af,
                  rin + 0.03, rout - 0.03, 0)

    # ---- monolithic / solid mass: one welded slab following the whole curve
    if solid:
        fill = V.solid_fill and abs(dA * N) < math.radians(200.0)
        segs = max(2, int(math.ceil(dA / math.radians(6.0))))
        rings = []
        for i in range(1, N + 1):
            Tbi = zl(i) - ft - ut
            for k in range(segs + 1):
                u = k / segs
                th = th0 + sgn * ((i - 1) + u) * dA
                zbot = z0 if fill else Tbi - V.waist - r + r * u
                rings.append([_polar(c, Ri, th, zbot), _polar(c, Ro, th, zbot),
                              _polar(c, Ro, th, Tbi), _polar(c, Ri, th, Tbi)])
        loft_w(part("SolidSteps"), rings, 0, True)

    # ---- supports for the different stair types
    layer = ft + ut + tt
    dep, sw_ = P.stringer_depth, P.stringer_w
    _FL.append(dict(width=Ro - Ri, n=N, r=r, g=gw, z0=z0))

    def top_line(t):    # underside of the treads at their back edge, t in step units
        return z0 + r - layer + r * (t - 1.0)

    def hpts(rho, t0, t1, zfn, per=3):
        k = max(2, int(math.ceil((t1 - t0) * per)))
        return [_polar(c, rho, th0 + sgn * (t0 + (t1 - t0) * j / k) * dA, zfn(t0 + (t1 - t0) * j / k))
                for j in range(k + 1)]

    sides = {"LEFT": [1.0], "RIGHT": [-1.0], "BOTH": [1.0, -1.0]}[P.support_side]

    def edge_rho(sd):
        return Ri if (sd > 0) == (sgn > 0) else Ro

    def outward(sd):
        return -1.0 if (sd > 0) == (sgn > 0) else 1.0

    def att(k_, label, p_):
        _ATT.append((k_, label, Vector(p_)))

    if kc == "STANDARD" and not solid and P.stringer != "NONE":
        so = P.stringer_offset
        rr = [Ri + so + sw_ / 2, Ro - so - sw_ / 2] if P.stringer == "SIDE" else [rm]
        for q, rho in enumerate(rr, 1):
            pp = hpts(rho, 1.0, float(N), lambda t: top_line(t) - dep / 2)
            sweep(part("Stringers"), pp, rect_profile(sw_, dep), 0)
            att("STRINGER_FOOT", "Stringer %d foot" % q, pp[0] - Z * (dep / 2))
            att("STRINGER_HEAD", "Stringer %d head" % q, pp[-1] - Z * (dep / 2))
    elif kc == "FLOATING":
        for i in range(1, N + 1):
            af = th0 + sgn * (i - 1) * dA
            za, zb_ = zl(i) - ft - ut - tt * 0.7, zl(i) - ft - ut - tt * 0.3
            for sd in sides:
                e, o = edge_rho(sd), outward(sd)
                tag = "L" if sd > 0 else "R"
                att("WALL_ANCHOR", "Anchor %02d %s" % (i, tag),
                    _polar(c, e, af + sgn * 0.5 * dA, (za + zb_) / 2))
                if not P.wall_anchor:
                    continue
                a_, b_ = (e - P.embed * 0.5 * o, e + P.embed * o) if o > 0 else (e + P.embed * o, e - P.embed * 0.5 * o)
                lloft("Stringers", lambda rho, za=za, zb_=zb_: rect(0.2 * dA * rho, 0.8 * dA * rho, za, zb_), af,
                      min(a_, b_), max(a_, b_), 0)
    elif kc == "CANTILEVER":
        for sd in sides:
            e, o = edge_rho(sd), outward(sd)
            rb = e + o * sw_ / 2
            bt = P.beam_top
            pp = hpts(rb, 1.0, float(N), lambda t: top_line(t) + dep * bt - dep / 2)
            sweep(part("Stringers"), pp, rect_profile(sw_, dep), 0)
            tag = "L" if sd > 0 else "R"
            att("BEAM_FOOT", "Beam %s foot" % tag, pp[0] - Z * (dep / 2))
            att("BEAM_HEAD", "Beam %s head" % tag, pp[-1] - Z * (dep / 2))
            for i in range(1, N + 1):
                tc = (i - 1) + P.stub_pos
                zlow, zhi = top_line(tc) + dep * bt, zl(i) - ft - ut - tt
                if zhi - zlow < 0.005:
                    continue
                af = th0 + sgn * (i - 1) * dA
                a_, b_ = sorted((e, e - o * P.embed))
                sp_ = P.stub_pos
                lloft("Stringers", lambda rho, zlow=zlow, zhi=zhi: rect(sp_ * dA * rho, sp_ * dA * rho + P.stub_t, zlow, zhi),
                      af, a_, b_, 0)
                att("TREAD_BRACKET", "Bracket %02d %s" % (i, tag), _polar(c, e, af + sgn * sp_ * dA, (zlow + zhi) / 2))
    elif kc == "SUSPENDED":
        zc = z0 + H + P.susp_top
        for i in range(1, N + 1):
            th = th0 + sgn * ((i - 1) + P.rod_pos) * dA
            rods = [(rm, "C")] if P.rod_layout == "CENTER" else [
                (edge_rho(sd) - outward(sd) * P.rod_inset, "L" if sd > 0 else "R") for sd in sides]
            for rho, tag in rods:
                p0 = _polar(c, rho, th, zl(i) - ft - ut - tt - 0.012)
                p1 = _polar(c, rho, th, zc)
                cyl(part("Stringers"), p0, p1, P.rod_d / 2, 0, 8)
                cyl(part("Stringers"), p0, p0 + Z * 0.012, P.rod_d * 1.5, 0, 10)
                att("ROD_TOP", "Rod %02d %s top" % (i, tag), p1)
    elif kc == "STEEL":
        prof = _steel_profile(P.steel_sec, sw_, dep, P.steel_t)
        so = P.stringer_offset + sw_ / 2
        rr = [Ri + so, Ro - so] if P.stringer != "CENTER" else [rm]
        for q, rho in enumerate(rr, 1):
            pp = hpts(rho, 1.0, float(N), lambda t: top_line(t) - dep / 2)
            sweep(part("Stringers"), pp, prof, 0)
            att("STRINGER_FOOT", "Stringer %d foot" % q, pp[0] - Z * (dep / 2))
            att("STRINGER_HEAD", "Stringer %d head" % q, pp[-1] - Z * (dep / 2))
            for i in range(1, N + 1):
                tc = (i - 1) + P.stub_pos
                zlow, zhi = top_line(tc), zl(i) - ft - ut - tt
                if zhi - zlow < 0.005:
                    continue
                af = th0 + sgn * (i - 1) * dA
                sp_ = P.stub_pos
                lloft("Stringers", lambda rr_, zlow=zlow, zhi=zhi: rect(sp_ * dA * rr_, sp_ * dA * rr_ + P.stub_t, zlow, zhi),
                      af, rho - sw_ / 2, rho + sw_ / 2, 0)

    if lay == "SPIRAL":
        p0 = Vector((c.x, c.y, z0))
        ptop = z0 + H + max(P.rail_height, 0.9)
        vtube(part("Stringers"), p0, z0, ptop, Ri, 16, 0)
        att("POLE_BASE", "Pole base", p0)
        att("POLE_TOP", "Pole top", Vector((c.x, c.y, ptop)))

    # ---- landings (flat circular sectors at both ends)
    aL = min(P.end_land_d / rm, math.radians(150.0))

    def sector(ta, tb, z):
        k = max(2, int(math.ceil(abs(tb - ta) / math.radians(6.0))))
        ths = [ta + (tb - ta) * j / k for j in range(k + 1)]
        return [_polar(c, Ro, th, z) for th in ths] + [_polar(c, Ri, th, z) for th in reversed(ths)]
    lt = Ly["lt"]
    ends = []
    if P.lower_land:
        ends.append(sector(th0 - sgn * aL, th0, z0))
    if P.upper_land:
        ends.append(sector(th0 + sgn * N * dA, th0 + sgn * (N * dA + aL), z0 + N * r))
    for pts in ends:
        top = [p - Z * ft for p in pts]
        ubot = [p - Z * (ft + ut) for p in pts]
        bot = [p - Z * (ft + ut + lt) for p in pts]
        part("Landings").prism(bot, ubot, 0)
        if ut > 0:
            part("Underlay").prism(ubot, top, 0)
        if ft > 0:
            part("Finish").prism(top, pts, 2)

    # ---- railings: flight rails + rails along the landing sectors, joined by finalize_rails
    if P.use_rails and P.rail_sides != "NONE":
        st0 = _style(P, False)
        lst0 = _style(P, True)
        h = P.rail_height
        ns = 4
        for sd in (1.0, -1.0):
            if P.rail_sides == "LEFT" and sd < 0:
                continue
            if P.rail_sides == "RIGHT" and sd > 0:
                continue
            e, o = edge_rho(sd), outward(sd)
            if lay == "SPIRAL" and o < 0:
                continue
            stx = _side_style(P, sd > 0, st0)
            hh = hand_info(stx, P)[1]
            off = rail_offset(stx, P)
            base_off = h - hh / 2.0
            rho = e + o * off
            pts, seg_in = [], []
            for j in range(N * ns + 1):
                t = j / ns
                th = th0 + sgn * t * dA
                pts.append(_polar(c, rho, th, z0 + r * (1.0 + min(t, N - 1.0)) + base_off))
                if j < N * ns:
                    tm = th + sgn * dA / ns / 2
                    seg_in.append(Vector((-o * math.cos(tm), -o * math.sin(tm), 0.0)))

            def sfloor(p, base_off=base_off):
                k = math.floor((p.z - base_off - z0) / r + 1e-6)
                return z0 + max(1, min(N, k)) * r

            run = Run(pts, sfloor, True, seg_in, hh, base_off, r + 0.10, False)
            plen = run.length
            k = max(1, int(round(P.post_spacing / max(gw, 0.05))))
            posts = [0.0, plen]
            for i in range(0, N, k):
                x = plen * (i + 0.5) / N
                if all(abs(x - m_) > 0.45 * gw for m_ in (0.0, plen)):
                    posts.append(x)
            run.posts = sorted(set(round(x, 6) for x in posts))
            run.kind = "flight"
            run.st = stx
            run.conn0 = bool(P.lower_land and P.rail_landing)
            run.conn1 = bool(P.upper_land and P.rail_landing)
            if run.conn0:
                run.nopost.add(0.0)
            if run.conn1:
                run.nopost.add(round(plen, 6))
            runs.append(run)
            if not P.rail_landing:
                continue
            lstx = _side_style(P, sd > 0, lst0)
            lhh = hand_info(lstx, P)[1]
            lrho = e + o * rail_offset(lstx, P)
            lbase = h - lhh / 2.0
            for ta, tb_, zlev, on in ((th0 - sgn * aL, th0, z0, P.lower_land),
                                      (th0 + sgn * N * dA, th0 + sgn * (N * dA + aL), z0 + N * r, P.upper_land)):
                if not on:
                    continue
                kk = max(2, int(math.ceil(abs(tb_ - ta) / math.radians(6.0))))
                ths = [ta + (tb_ - ta) * j / kk for j in range(kk + 1)]
                lp = [_polar(c, lrho, th, zlev + lbase) for th in ths]
                lin = [Vector((-o * math.cos((ths[j] + ths[j + 1]) / 2), -o * math.sin((ths[j] + ths[j + 1]) / 2), 0.0))
                       for j in range(kk)]
                lr = Run(lp, lambda p, zf=zlev: zf, False, lin, lhh, lbase, 0.0, False)
                ll = lr.length
                nsp = max(1, int(math.ceil(ll / max(0.2, P.post_spacing) - 1e-6)))
                lr.posts = sorted(set(round(ll * q / nsp, 6) for q in range(nsp + 1)))
                lr.kind = "landing"
                lr.st = lstx
                runs.append(lr)
    if runs:
        finalize_rails(runs, P, part("Railings"), part("Lights") if P.led_rail else None)
    _META[name] = dict(N=N, r=r, g=gw, counts=[N], H=H, rise=N * r, W=Ro - Ri, flights=1, landing=P.end_land_d)
    return parts


# =============================================================================
#  Preview icons (drawn procedurally, no external files needed)
# =============================================================================

class Canvas:
    def __init__(self, w, h, bg):
        self.w, self.h = w, h
        self.b = bytearray(bytes((bg[0], bg[1], bg[2], 255)) * (w * h))

    def put(self, x, y, col, a=1.0):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = ((self.h - 1 - y) * self.w + x) * 4
            if a >= 1.0:
                self.b[i], self.b[i + 1], self.b[i + 2] = col[0], col[1], col[2]
            else:
                for k in range(3):
                    self.b[i + k] = int(self.b[i + k] * (1 - a) + col[k] * a)

    def rect(self, x0, y0, x1, y1, col, a=1.0):
        for y in range(int(y0), int(y1)):
            for x in range(int(x0), int(x1)):
                self.put(x, y, col, a)

    def disc(self, cx, cy, r, col):
        for y in range(int(cy - r), int(cy + r) + 1):
            for x in range(int(cx - r), int(cx + r) + 1):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                    self.put(x, y, col)

    def line(self, x0, y0, x1, y1, w, col):
        n = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
        for k in range(n + 1):
            t = k / n
            self.disc(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, w / 2.0, col)

    def fill_between(self, x0, x1, ylo, yhi, col, a=1.0):
        for x in range(int(x0), int(x1)):
            for y in range(int(ylo(x)), int(yhi(x))):
                self.put(x, y, col, a)

    def downsample(self):
        w2, h2 = self.w // 2, self.h // 2
        out = bytearray(w2 * h2 * 4)
        for y in range(h2):
            for x in range(w2):
                for k in range(3):
                    s = 0
                    for dy in (0, 1):
                        for dx in (0, 1):
                            s += self.b[((2 * y + dy) * self.w + (2 * x + dx)) * 4 + k]
                    out[(y * w2 + x) * 4 + k] = s // 4
                out[(y * w2 + x) * 4 + 3] = 255
        return w2, h2, out


def write_png(path, w, h, rgba):
    raw = b"".join(b"\x00" + bytes(rgba[y * w * 4:(y + 1) * w * 4]) for y in range(h))

    def chunk(t, dat):
        c = struct.pack(">I", len(dat)) + t + dat
        return c + struct.pack(">I", zlib.crc32(t + dat) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    with open(path, "wb") as fh:
        fh.write(png)


def render_preview(st):
    BG = (38, 42, 50)
    STAIR, STAIR_TOP = (96, 102, 114), (150, 156, 168)
    HAND, RAIL, WOOD = (245, 245, 245), (235, 150, 60), (215, 160, 100)
    GLASS, WALLC, DARK = (130, 205, 235), (196, 176, 150), (70, 78, 92)
    c = Canvas(256, 256, BG)
    X0, SW, RISE, N = 22, 38, 20, 6

    def FL(i):
        return 44 + RISE * i

    def Fx(x):
        return FL(max(0, min(N - 1, int((x - X0) // SW))))

    def Pt(x):
        return 44 + (x - X0) * RISE / SW

    HR = 64

    def H(x):
        return Pt(x) + HR

    for i in range(N):
        x0 = X0 + SW * i
        c.rect(x0, 0, x0 + SW, FL(i), STAIR)
        c.rect(x0, FL(i) - 4, x0 + SW, FL(i), STAIR_TOP)
    xs = [34, 134, 226]
    k = st["kind"]
    spans = list(zip(xs[:-1], xs[1:]))

    if k == "bal":
        bsz = st.get("bs", 0.02)
        stp = 8 if bsz < 0.01 else 14
        bw = 2 if bsz < 0.01 else (7 if bsz > 0.022 else (4 if st["rnd"] else 3))
        x = xs[0] + stp
        while x < xs[-1]:
            if all(abs(x - p) > 9 for p in xs):
                c.line(x, Fx(x), x, H(x), bw, WOOD)
            x += stp
    elif k == "horiz":
        for q in range(1, 5):
            off = (HR - 12) * q / 4
            c.line(xs[0], H(xs[0]) - off, xs[-1], H(xs[-1]) - off, 6 if st.get("slat") else (2 if st.get("rod") else 3), RAIL)
    elif k == "pipe":
        for q in (1, 2):
            off = (HR - 12) * q / 2
            c.line(xs[0], H(xs[0]) - off, xs[-1], H(xs[-1]) - off, 5, RAIL)
    elif k == "glass":
        for a, b in spans:
            c.fill_between(a + 7, b - 7, lambda x: Pt(x) + 8, lambda x: H(x) - 4, GLASS, 0.5)
            if st.get("mid"):
                ym = lambda x: (Pt(x) + 8 + H(x) - 4) / 2
                c.line(a + 7, ym(a + 7), b - 7, ym(b - 7), 3, (222, 180, 90))
            if st.get("frame"):
                for (x0, y0, x1, y1) in ((a + 7, Pt(a + 7) + 8, b - 7, Pt(b - 7) + 8), (a + 7, H(a + 7) - 4, b - 7, H(b - 7) - 4),
                                         (a + 7, Pt(a + 7) + 8, a + 7, H(a + 7) - 4), (b - 7, Pt(b - 7) + 8, b - 7, H(b - 7) - 4)):
                    c.line(x0, y0, x1, y1, 2, RAIL)
            if st.get("btn"):
                for fx in (a + 14, b - 14):
                    for yy in (Pt(fx) + 18, H(fx) - 14):
                        c.disc(fx, yy, 4, (200, 205, 215))
    elif k == "glass_ch":
        for a, b in spans:
            c.fill_between(a - 2, b - 2, lambda x: Pt(x) + 10, lambda x: H(x) - 4, GLASS, 0.5)
        c.line(xs[0] - 4, Pt(xs[0] - 4) + 6, xs[-1] + 4, Pt(xs[-1] + 4) + 6, 8, DARK)
    elif k == "cable":
        for q in range(1, 7):
            off = (HR - 12) * q / 6
            c.line(xs[0], H(xs[0]) - off, xs[-1], H(xs[-1]) - off, 2, (200, 205, 215))
    elif k == "flat":
        stp = 14 if "fw" in st else 18
        fwid = (8 if st.get("fw", 0.012) > 0.03 else 3) if "fw" in st else 6
        x = xs[0] + stp
        while x < xs[-1]:
            if all(abs(x - p) > 10 for p in xs):
                c.line(x, Fx(x), x, H(x), fwid, WOOD)
            x += stp
    elif k == "diag":
        x = xs[0] + 8
        while x + 26 < xs[-1]:
            c.line(x, Pt(x) + 8, x + 26, H(x + 26) - 6, 3, WOOD)
            x += 13
    elif k == "zig":
        for a, b in spans:
            n = 9
            pp = []
            for q in range(n + 1):
                x = a + (b - a) * q / n
                y = H(x) - 10 if q % 2 == 0 else Pt(x) + 10
                pp.append((x, y))
            for (x0, y0), (x1, y1) in zip(pp[:-1], pp[1:]):
                c.line(x0, y0, x1, y1, 3, RAIL)
    elif k == "wall":
        c.fill_between(xs[0] - 8, xs[-1] + 8, lambda x: Pt(x) - 24, lambda x: H(x) - 6, WALLC, 1.0)
        c.line(xs[0] - 8, H(xs[0] - 8) - 3, xs[-1] + 8, H(xs[-1] + 8) - 3, 9, (225, 210, 185))
    elif k == "panel":
        for a, b in spans:
            c.fill_between(a + 6, b - 6, lambda x: Pt(x) + 8, lambda x: H(x) - 4, (170, 100, 50), 1.0)
    elif k == "slats":
        x = xs[0] + 8
        while x < xs[-1]:
            c.line(x, Fx(x), x, H(x), 5, (190, 130, 80))
            x += 9
    elif k == "grid":
        x = xs[0] + 12
        while x < xs[-1]:
            c.line(x, Pt(x) + 8, x, H(x) - 4, 2, (200, 205, 215))
            x += 12
        for q in range(1, 5):
            off = (HR - 14) * q / 4
            c.line(xs[0], H(xs[0]) - off, xs[-1], H(xs[-1]) - off, 2, (200, 205, 215))
    elif k == "bracket":
        for x in (58, 134, 210):
            c.line(x, H(x), x, H(x) - 22, 3, (200, 205, 215))
            c.rect(x - 7, H(x) - 30, x + 7, H(x) - 22, (200, 205, 215))
    elif k == "turned":
        x = xs[0] + 14
        while x < xs[-1]:
            if all(abs(x - p) > 9 for p in xs):
                c.line(x, Fx(x), x, H(x), 3, WOOD)
                for q in (0.22, 0.5, 0.78):
                    c.disc(x, Fx(x) + (H(x) - Fx(x)) * q, 4, WOOD)
            x += 14
    elif k == "twist":
        x = xs[0] + 12
        while x < xs[-1]:
            if all(abs(x - p) > 9 for p in xs):
                c.line(x, Fx(x), x, H(x), 4, WOOD)
                for q in range(6):
                    yy = Fx(x) + (H(x) - Fx(x)) * q / 6
                    c.line(x - 3, yy, x + 3, yy + 5, 2, RAIL)
            x += 12
    elif k == "lattice":
        x = xs[0] + 8
        while x + 26 < xs[-1]:
            c.line(x, Pt(x) + 8, x + 26, H(x + 26) - 6, 2, WOOD)
            c.line(x, H(x) - 6, x + 26, Pt(x + 26) + 8, 2, WOOD)
            x += 20
    elif k == "rings":
        for a, b in spans:
            for q in range(4):
                cx = a + (b - a) * (q + 0.5) / 4
                for row in (0, 1):
                    cy = Pt(cx) + 16 + row * 22
                    pp = [(cx + 9 * math.cos(2 * math.pi * m / 14), cy + 9 * math.sin(2 * math.pi * m / 14)) for m in range(15)]
                    for (x0, y0), (x1, y1) in zip(pp[:-1], pp[1:]):
                        c.line(x0, y0, x1, y1, 2, WOOD)
    elif k == "wave":
        for a, b in spans:
            for ph in (0.0, math.pi):
                pp = []
                for m in range(41):
                    x = a + (b - a) * m / 40
                    pp.append((x, Pt(x) + 30 + 14 * math.sin(ph + 2 * math.pi * 4 * m / 40)))
                for (x0, y0), (x1, y1) in zip(pp[:-1], pp[1:]):
                    c.line(x0, y0, x1, y1, 3, WOOD)
    elif k == "xcross":
        for a, b in spans:
            c.line(a + 8, Pt(a + 8) + 8, b - 8, H(b - 8) - 6, 3, RAIL)
            c.line(a + 8, H(a + 8) - 6, b - 8, Pt(b - 8) + 8, 3, RAIL)
    elif k == "louver":
        for q in range(1, 7):
            off = (HR - 10) * q / 7
            c.line(xs[0], H(xs[0]) - off, xs[-1], H(xs[-1]) - off, 5, WOOD)

    shape = st["post"]
    if shape:
        for x in xs:
            if shape == "sq":
                c.rect(x - 5, Fx(x), x + 5, H(x), RAIL)
            else:
                c.line(x, Fx(x), x, H(x), 9, (200, 205, 215))
    hw = {"round": 8, "flat": 6, "coping": 4, "rect": 7, "oval": 8}[st["hand"]]
    if k != "wall":
        c.line(xs[0] - 4, H(xs[0] - 4), xs[-1] + 4, H(xs[-1] + 4), hw, HAND)
    return c.downsample()


def preview_dir():
    try:
        return bpy.utils.user_resource("CONFIG", path="pstairs_previews", create=True)
    except Exception:
        d = os.path.join(tempfile.gettempdir(), "pstairs_previews")
        os.makedirs(d, exist_ok=True)
        return d


_pcoll = None
_RAIL_ITEMS = [("BAL_SQ", "Square Balusters", "", 0, 0)]
_LAND_ITEMS = [("SAME", "Same as flights", "", "DUPLICATE", 0)]


def load_previews():
    global _pcoll, _RAIL_ITEMS, _LAND_ITEMS
    import bpy.utils.previews
    _pcoll = bpy.utils.previews.new()
    folder = preview_dir()
    rail, land = [], [("SAME", "Same as flights", "Use the flight railing style on landings", "DUPLICATE", 0)]
    for i, st in enumerate(STYLES):
        icon = 0
        path = os.path.join(folder, "%s_v2.png" % st["id"])
        try:
            if not os.path.exists(path):
                w, h, px = render_preview(st)
                write_png(path, w, h, px)
            icon = _pcoll.load(st["id"], path, "IMAGE").icon_id
        except Exception:
            traceback.print_exc()
        rail.append((st["id"], st["name"], st["name"], icon, i))
        land.append((st["id"], st["name"], st["name"], icon, i + 1))
    _RAIL_ITEMS, _LAND_ITEMS = rail, land


def _rail_items(self, context):
    return _RAIL_ITEMS


def _land_items(self, context):
    return _LAND_ITEMS


# =============================================================================
#  Writing results into the scene
# =============================================================================

def fill_mesh(me, mb):
    bm = bmesh.new()
    vs = [bm.verts.new(v) for v in mb.v]
    made = []
    for fi, (idx, m) in enumerate(zip(mb.f, mb.fm)):
        try:
            f = bm.faces.new([vs[i] for i in idx])
            f.material_index = m
            made.append((fi, f))
        except ValueError:
            pass
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    if _UV_ON[0] and made:
        bm.verts.index_update()
        layer = bm.loops.layers.uv.verify()
        for fi, f in made:
            nm = mb.mats[mb.fm[fi]] if mb.fm[fi] < len(mb.mats) else ""
            tile = max(_UV_TILES.get(_MAT_CLASS.get(nm, "other"), 1.0), 1e-3)
            hint = mb.uvh.get(fi)
            if hint is None:
                hint = _cap_uv(mb, mb.f[fi])
            mp = {}
            for vid, q in zip(mb.f[fi], hint):
                mp.setdefault(vid, q)
            for lp in f.loops:
                q = mp.get(lp.vert.index, (0.0, 0.0))
                lp[layer].uv = (q[0] / tile, q[1] / tile)
    bm.to_mesh(me)
    bm.free()
    me.update()


# =============================================================================
#  v5 - quantity take-off (BOQ)
# =============================================================================

_BOQ = {}
_FIT_MSG = {}
_STEEL_KINDS = ("STEEL", "CANTILEVER", "SUSPENDED", "FLOATING", "SAWTOOTH")


def _mat_volumes(ob):
    """Return per-material volumes only when each material forms a closed oriented shell.

    Face groups that are open or inconsistently wound cannot define a reliable
    material volume and are omitted. Touching/overlapping shells still require review.
    """
    me = ob.data
    me.calc_loop_triangles()
    edge_counts = {}
    for face in me.polygons:
        group = edge_counts.setdefault(face.material_index, {})
        ids = list(face.vertices)
        for a, b in zip(ids, ids[1:] + ids[:1]):
            key = (a, b) if a < b else (b, a)
            count, direction = group.get(key, (0, 0))
            group[key] = (count + 1, direction + (1 if a < b else -1))
    valid = {mat for mat, edges in edge_counts.items() if edges and
             all(count == 2 and direction == 0 for count, direction in edges.values())}
    volume = {}
    for tri in me.loop_triangles:
        mat = me.polygons[tri.polygon_index].material_index
        if mat not in valid:
            continue
        a, b, c = [me.vertices[i].co for i in tri.vertices]
        volume[mat] = volume.get(mat, 0.0) + a.dot(b.cross(c)) / 6.0
    determinant = abs(ob.matrix_world.to_3x3().determinant())
    return {k: abs(v) * determinant for k, v in volume.items()}


def _top_area(ob, mat=None):
    me = ob.data
    me.calc_loop_triangles()
    area = 0.0
    for tri in me.loop_triangles:
        face = me.polygons[tri.polygon_index]
        if mat is not None and face.material_index != mat:
            continue
        a, b, c = [ob.matrix_world @ me.vertices[i].co for i in tri.vertices]
        cross = (b-a).cross(c-a)
        if cross.length > 1e-12 and cross.normalized().z > 0.95:
            area += cross.length * 0.5
    return area


def compute_boq(obj):
    """Quantities for one generated stair. Returns [(section, item, unit, qty, note, waste_applies)]."""
    P = obj.pstairs
    found, _d = _find_parts(obj, obj.get("ps_uid") or "")
    Ly = layer_info(P)
    rows = []

    def add(sec, item, unit, qty, note="", waste=True):
        if qty is None or (isinstance(qty, float) and qty < 1e-9):
            return
        rows.append((sec, item, unit, qty, note, waste))

    data = _STATS_BY_OBJ.get(obj.name, [])
    fl = _FL_BY_OBJ.get(obj.name, [])
    steps = sum(d[0] for d in data)
    for k, (n, r, g, H, Ls) in enumerate(data, 1):
        w = fl[k - 1]["width"] if k <= len(fl) else 0.0
        add("Geometry", "Flight %d" % k, "nr", n, "riser %.0f mm, going %.0f mm, width %.0f mm" % (r * 1000, g * 1000, w * 1000), False)
    add("Geometry", "Total steps", "nr", steps, "total rise %.3f m" % sum(d[3] for d in data), False)
    wmean = sum(f["width"] * f["n"] for f in fl) / max(steps, 1) if fl else 0.0

    def vol(pn):
        ob = found.get(pn)
        return _mat_volumes(ob) if ob else {}

    t = vol("Treads")
    if t:
        add("Structure", "Treads (boards)", "nr", steps, "", False)
        add("Structure", "Tread timber/board volume", "m3", sum(t.values()))
    rv = vol("Risers")
    if rv:
        add("Structure", "Risers (boards)", "nr", steps, "", False)
        add("Structure", "Riser board volume", "m3", sum(rv.values()))
    sv = vol("SolidSteps")
    if sv:
        add("Structure", "Concrete - solid / monolithic steps", "m3", sum(sv.values()))
    lv = vol("Landings")
    if lv:
        add("Structure", "Concrete - landing slabs", "m3", sum(lv.values()))
        add("Structure", "Landing slab plan area", "m2", _top_area(found["Landings"]))
    stv = vol("Stringers")
    if stv:
        V = sum(stv.values())
        add("Supports", "Stringers / beams / rods / anchors (volume)", "m3", V)
        if P.stair_kind in _STEEL_KINDS:
            fac, note = 1.0, "solid as modelled"
            w_, h_, t_ = P.stringer_w, P.stringer_depth, P.steel_t
            if (P.stair_kind == "STEEL" and P.steel_sec == "BOX") or P.stair_kind == "CANTILEVER":
                fac = min(1.0, max(0.02, (2 * (w_ + h_) * t_ - 4 * t_ * t_) / (w_ * h_)))
                note = "box sections taken as hollow, wall %.0f mm" % (t_ * 1000)
            add("Supports", "Steel mass estimate (7850 kg/m3)", "kg", V * fac * 7850.0, note + "; check against your steel schedule")
    kinds = {}
    for k_, lab, p in _ATT_BY_OBJ.get(obj.name, []):
        if k_ != "POST_BASE":
            kinds[k_] = kinds.get(k_, 0) + 1
    for k_, n_ in sorted(kinds.items()):
        add("Supports", k_.replace("_", " ").title() + " points", "nr", n_, "", False)
    ub = vol("Underlay")
    if ub:
        add("Finishes", "Underlay / screed volume", "m3", sum(ub.values()))
        if Ly["ut"] > 0:
            add("Finishes", "Underlay area", "m2", sum(ub.values()) / Ly["ut"])
    fv = vol("Finish")
    if "Finish" in found:
        fo = found["Finish"]
        add("Finishes", "Tread finish area (top faces)", "m2", _top_area(fo, 0))
        if Ly["rf"] > 0 and 1 in fv:
            add("Finishes", "Riser finish area", "m2", fv[1] / Ly["rf"])
        add("Finishes", "Landing finish area (top faces)", "m2", _top_area(fo, 2))
        add("Finishes", "Finish material volume", "m3", sum(fv.values()))
    iv = vol("Inlay")
    if iv:
        add("Accessories", "Metal inlay / nosing volume", "m3", sum(iv.values()))
        add("Accessories", "Metal nosing run (approx.)", "m", steps * wmean, "one run per step")
    if "Strips" in found:
        add("Accessories", "Anti-slip strips", "nr", steps * P.strip_n, "per tread: %d" % P.strip_n, False)
        add("Accessories", "Anti-slip strip run (approx.)", "m", steps * P.strip_n * max(wmean - 2 * P.strip_inset, 0))
    if "Lights" in found:
        add("Accessories", "LED strip run (approx.)", "m", steps * wmean, "step lighting and channels")
    rs = _RAIL_BY_OBJ.get(obj.name, [])
    if rs:
        add("Railings", "Handrail run", "m", sum(r_["length"] for r_ in rs), "%d run(s), both sides and landings" % len(rs))
        add("Railings", "Posts / newels", "nr", sum(r_["posts"] for r_ in rs), "", False)
    rv2 = vol("Railings")
    names = ["Post", "Handrail", "Infill", "Glass"]
    for m_, v_ in sorted(rv2.items()):
        nm = names[m_] if m_ < len(names) else "Mat %d" % m_
        add("Railings", nm + " volume", "m3", v_)
    if 3 in rv2 and getattr(P, "glass_thk", 0) > 0:
        add("Railings", "Glass area (volume / thickness)", "m2", rv2[3] / P.glass_thk)
    return rows


def _boq_header(obj):
    P = obj.pstairs
    return [("Stair", obj.name), ("Source", P.engine), ("Layout", P.layout if P.engine == "PARAM" else "from planes"),
            ("Type", P.stair_kind), ("Looks", P.look)]


class PSTAIRS_OT_boq_calc(bpy.types.Operator):
    bl_idname = "pstairs.boq_calc"
    bl_label = "Calculate Quantities"
    bl_description = "Measure the generated stair and list quantities"

    def execute(self, context):
        ob = context.object
        if ob is None or ob.type != "MESH" or not ob.pstairs.generated:
            self.report({"ERROR"}, "Select a generated stair")
            return {"CANCELLED"}
        _BOQ[ob.name] = (_SIG.get(ob.name), compute_boq(ob))
        return {"FINISHED"}


class PSTAIRS_OT_boq_export(bpy.types.Operator, ExportHelper):
    bl_idname = "pstairs.boq_export"
    bl_label = "Export BOQ (CSV)"
    bl_description = "Write the quantity take-off to a CSV file (opens in Excel)"
    filename_ext = ".csv"
    filter_glob: StringProperty(default="*.csv", options={"HIDDEN"})

    def invoke(self, context, event):
        ob = context.object
        self.filepath = bpy.path.clean_name(ob.name if ob else "stair") + "_BOQ.csv"
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        import csv
        ob = context.object
        if ob is None or ob.type != "MESH" or not ob.pstairs.generated:
            self.report({"ERROR"}, "Select a generated stair")
            return {"CANCELLED"}
        rows = compute_boq(ob)
        _BOQ[ob.name] = (_SIG.get(ob.name), rows)
        w = 1.0 + ob.pstairs.boq_waste / 100.0
        with open(self.filepath, "w", newline="", encoding="utf-8-sig") as f:
            cw = csv.writer(f)
            for k, v in _boq_header(ob):
                cw.writerow([k, v])
            cw.writerow(["Wastage allowance", "%.0f %%" % ob.pstairs.boq_waste])
            cw.writerow(["Measurement note", "Model-derived estimates; open or inconsistently oriented material shells omitted. Verify material subdivisions, openings, overlaps and quantities manually."])
            cw.writerow(["Measurement basis", "Volumes: signed triangle sums by material; horizontal areas: upward-facing polygons; steel mass: model volume and assumed density."])
            cw.writerow([])
            cw.writerow(["Section", "Item", "Unit", "Quantity", "Qty incl. wastage", "Notes"])
            for sec, item, unit, q, note, wa in rows:
                cw.writerow([sec, item, unit, round(q, 4), round(q * w if wa else q, 4), note])
        self.report({"INFO"}, "Wrote %d lines to %s" % (len(rows), self.filepath))
        return {"FINISHED"}


# =============================================================================
#  v5 - stairwell fit
# =============================================================================

def _footprint(P, H, layout, N, r, g, W, turn):
    """Plan bounding box (x0, x1, y0, y1) of a stair, flight 1 starting at the origin and running along +Y.
    End landings are left out - they belong to the floors, not to the void."""
    from mathutils import Matrix
    PV = _PView(P, dict(layout=layout, st_width=W, going=g, riser_mode="HEIGHT", riser_height=r,
                        lower_land=False, upper_land=False, turn_dir=turn, split=0.5))
    verts, _f, _e, meta = build_virtual(PV, Matrix.Identity(4), 0.0, H)
    xs = [v.x for v in verts]
    ys = [v.y for v in verts]
    return min(xs), max(xs), min(ys), max(ys)


def fit_stair(P, H, A, B, start, candidates_out=None):
    """Search layout / risers / going / width for the best stair that fits an A x B void."""
    rz = {"BOTTOM": 0.0, "TOP": math.pi, "LEFT": -math.pi / 2, "RIGHT": math.pi / 2}[start]
    c, s = math.cos(rz), math.sin(rz)
    best, fail = None, None
    layout_best = {}
    widths, w = [], P.st_width
    while w >= P.fit_min_width - 1e-9:
        widths.append(round(w, 3))
        w -= 0.05
    if not widths:
        widths = [P.st_width]
    n_lo = max(1, int(math.ceil(H / 0.19 - 1e-9)))
    n_hi = max(n_lo, int(math.floor(H / 0.15 + 1e-9)))
    for li, (layout, turns) in enumerate((("STRAIGHT", ("LEFT",)), ("L_SHAPED", ("LEFT", "RIGHT")), ("U_SHAPED", ("LEFT", "RIGHT")))):
        for N in range(n_lo, n_hi + 1):
            if layout != "STRAIGHT" and N < 2:
                continue
            r = H / N
            gp = min(max(0.63 - 2 * r, 0.25), 0.32)
            for g in sorted({round(gp, 4), 0.25}):
                for W in widths:
                    for turn in turns:
                        x0, x1, y0, y1 = _footprint(P, H, layout, N, r, g, W, turn)
                        pts = [(x * c - y * s, x * s + y * c) for x in (x0, x1) for y in (y0, y1)]
                        rx0, rx1 = min(p[0] for p in pts), max(p[0] for p in pts)
                        ry0, ry1 = min(p[1] for p in pts), max(p[1] for p in pts)
                        dx, dy = rx1 - rx0, ry1 - ry0
                        over = max(0.0, dx - A) + max(0.0, dy - B)
                        score = 10 * abs(r - 0.175) + 5 * abs(g - 0.28) + 2 * (P.st_width - W) + 0.03 * li
                        cand = dict(layout=layout, turn=turn, N=N, r=r, g=g, W=W, rz=rz, dx=dx, dy=dy, score=score,
                                    box=(rx0, rx1, ry0, ry1), over=over)
                        if over <= 1e-6:
                            if best is None or score < best["score"]:
                                best = cand
                            if layout not in layout_best or score < layout_best[layout]["score"]:
                                layout_best[layout] = cand
                        elif fail is None or over < fail["over"]:
                            fail = cand
    if candidates_out is not None:
        candidates_out.extend(sorted(layout_best.values(), key=lambda c: c["score"]))
    return best, fail


class PSTAIRS_OT_fit_well(bpy.types.Operator):
    bl_idname = "pstairs.fit_well"
    bl_label = "Fit Stair to Void"
    bl_description = "Choose layout, riser count, going and width that fit the stairwell, then place the stair in it"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        ob = context.object
        if ob is None or ob.type != "MESH" or ob.pstairs.engine != "PARAM" or ob.pstairs.layout in ("CURVED", "HELICAL", "SPIRAL"):
            self.report({"ERROR"}, "Select a parametric stair with a straight, L, U or multi-flight layout")
            return {"CANCELLED"}
        P = ob.pstairs
        z0, H = _levels(ob, P)
        wo = P.well_obj
        if wo is not None:
            mw = wo.matrix_world
            cs = [Vector(cc) for cc in wo.bound_box]
            x0, x1 = min(c.x for c in cs), max(c.x for c in cs)
            y0, y1 = min(c.y for c in cs), max(c.y for c in cs)
            A = (x1 - x0) * Vector(mw.col[0][:3]).length
            B = (y1 - y0) * Vector(mw.col[1][:3]).length
            origin = mw @ Vector((x0, y0, 0.0))
            rzv = mw.to_euler("XYZ").z
        else:
            A, B = P.well_w, P.well_l
            origin = Vector(context.scene.cursor.location)
            rzv = 0.0
        choices = []
        best, fail = fit_stair(P, H, A, B, P.well_start, choices)
        if P.fit_choice != "BEST":
            best = next((candidate for candidate in choices if candidate["layout"] == P.fit_choice), None)
            if best is None and choices:
                self.report({"WARNING"}, "The chosen layout does not fit; use Compare Fit Options")
                return {"CANCELLED"}
        if best is None:
            f = fail
            msg = "No layout fits a %.2f x %.2f m void. Closest (%s) needs %.2f x %.2f m." % (
                A, B, f["layout"].replace("_SHAPED", "").title(), f["dx"], f["dy"])
            _FIT_MSG[ob.name] = msg
            self.report({"WARNING"}, msg)
            return {"CANCELLED"}
        rx0, rx1, ry0, ry1 = best["box"]
        if P.well_start in ("BOTTOM", "TOP"):
            sx = (A - (rx1 - rx0)) / 2 - rx0
            sy = -ry0 if P.well_start == "BOTTOM" else B - ry1
        else:
            sy = (B - (ry1 - ry0)) / 2 - ry0
            sx = -rx0 if P.well_start == "LEFT" else A - rx1
        cz, sz = math.cos(rzv), math.sin(rzv)
        wx = origin.x + sx * cz - sy * sz
        wy = origin.y + sx * sz + sy * cz
        apply_dict(P, dict(layout=best["layout"], riser_mode="HEIGHT", riser_height=best["r"], going=best["g"],
                           st_width=best["W"], turn_dir=best["turn"], split=0.5))
        ob.location.x, ob.location.y = wx, wy
        ob.rotation_euler.z = rzv + best["rz"]
        context.view_layer.update()
        rebuild(ob)
        if P.fit_cut and P.slab_obj is not None:
            try:
                cut_opening(context, ob, P.slab_obj, P.opening_margin, False)
            except Exception as e:
                self.report({"WARNING"}, "Opening not cut: %s" % e)
        msg = "%s: %d risers of %.0f mm, going %.0f mm, width %.0f mm - footprint %.2f x %.2f m in %.2f x %.2f m void" % (
            best["layout"].replace("_SHAPED", "-shaped").replace("STRAIGHT", "Straight"), best["N"], best["r"] * 1000,
            best["g"] * 1000, best["W"] * 1000, best["dx"], best["dy"], A, B)
        _FIT_MSG[ob.name] = msg
        self.report({"INFO"}, msg)
        return {"FINISHED"}


# =============================================================================
#  v6 - textures on the UV maps, slab opening cutter
# =============================================================================

_TEX_GROUPS = {"timber": ("PS_Tread", "PS_Riser", "PS_Handrail"),
               "finish": ("PS_FinishTread", "PS_FinishRiser", "PS_FinishLanding"),
               "concrete": ("PS_Concrete", "PS_Landing", "PS_Underlay")}


def _strip_tex(mat):
    if not mat.use_nodes:
        return
    nt = mat.node_tree
    for n in [n for n in nt.nodes if n.name.startswith("PS_TEX")]:
        nt.nodes.remove(n)


def _apply_tex(mat, kind, img=None):
    """Hook a texture onto Base Color. UVs are in tile units, so no scale node is needed."""
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    _strip_tex(mat)
    if bsdf is None or kind == "NONE":
        return
    base = tuple(bsdf.inputs["Base Color"].default_value)[:3]
    lk = nt.links.new

    def node(t, name):
        n = nt.nodes.new(t)
        n.name = "PS_TEX_" + name
        return n

    def shade(f):
        return (min(1.0, base[0] * f), min(1.0, base[1] * f), min(1.0, base[2] * f), 1.0)

    def ramp(lo, hi):
        r = node("ShaderNodeValToRGB", "ramp")
        r.color_ramp.elements[0].color = shade(lo)
        r.color_ramp.elements[1].color = shade(hi)
        return r

    uv = node("ShaderNodeTexCoord", "uv")
    if kind in ("IMAGE", "GRID"):
        if img is None:
            return
        t = node("ShaderNodeTexImage", "img")
        t.image = img
        lk(uv.outputs["UV"], t.inputs["Vector"])
        lk(t.outputs["Color"], bsdf.inputs["Base Color"])
    elif kind == "TIMBER":
        mp = node("ShaderNodeMapping", "map")
        mp.inputs["Scale"].default_value = (0.25, 1.0, 1.0)
        wv = node("ShaderNodeTexWave", "wave")
        wv.wave_type = "BANDS"
        wv.bands_direction = "Y"
        for k_, v_ in (("Scale", 14.0), ("Distortion", 2.5), ("Detail", 3.0), ("Detail Scale", 1.5), ("Detail Roughness", 0.5)):
            wv.inputs[k_].default_value = v_
        rp = ramp(0.55, 1.15)
        lk(uv.outputs["UV"], mp.inputs["Vector"])
        lk(mp.outputs["Vector"], wv.inputs["Vector"])
        lk(wv.outputs["Fac"], rp.inputs["Fac"])
        lk(rp.outputs["Color"], bsdf.inputs["Base Color"])
    else:
        nz = node("ShaderNodeTexNoise", "noise")
        stone = kind == "STONE"
        for k_, v_ in (("Scale", 3.5 if stone else 30.0), ("Detail", 12.0 if stone else 14.0),
                       ("Roughness", 0.55), ("Distortion", 0.3 if stone else 0.0)):
            nz.inputs[k_].default_value = v_
        rp = ramp(0.68, 1.12) if stone else ramp(0.72, 1.05)
        lk(uv.outputs["UV"], nz.inputs["Vector"])
        lk(nz.outputs["Fac"], rp.inputs["Fac"])
        lk(rp.outputs["Color"], bsdf.inputs["Base Color"])
        if not stone:
            bp = node("ShaderNodeBump", "bump")
            bp.inputs["Strength"].default_value = 0.4
            bp.inputs["Distance"].default_value = 0.02
            lk(nz.outputs["Fac"], bp.inputs["Height"])
            lk(bp.outputs["Normal"], bsdf.inputs["Normal"])


class PSTAIRS_OT_textures(bpy.types.Operator):
    bl_idname = "pstairs.textures"
    bl_label = "Apply Textures"
    bl_description = "Put procedural or image textures on the stair materials (they follow the generated UV maps)"
    bl_options = {"REGISTER", "UNDO"}
    mode: EnumProperty(name="Mode", default="PROCEDURAL", items=[
        ("PROCEDURAL", "Procedural", "Wood, stone and concrete from shader nodes"),
        ("IMAGES", "Images", "Your image files from the Materials panel"),
        ("UV_GRID", "UV Test Grid", "Blender's UV grid, to check orientation and scale"),
        ("CLEAR", "Remove", "Back to flat colours")])

    def execute(self, context):
        ob = context.object
        if ob is None or ob.type != "MESH":
            self.report({"ERROR"}, "Select a stair object")
            return {"CANCELLED"}
        missing = apply_textures(ob.pstairs, self.mode)
        if missing:
            self.report({"WARNING"}, "Could not load: " + ", ".join(sorted(set(missing))))
        return {"FINISHED"}


# =============================================================================
#  v7 - personal preset library (named, stored in Blender's user config folder)
# =============================================================================

_PROJECT_KEYS = {
    "live", "hide_source_render", "flat_tol", "max_angle", "riser_mode", "riser_height", "step_count",
    "engine", "layout", "floor_height", "st_width", "going", "land_d", "land_w", "lower_land", "upper_land",
    "end_land_d", "flight_count", "split", "multi_turn", "turn_dir", "well_gap", "curve_radius", "sweep",
    "pole_r", "spiral_r", "step_ang", "opening_margin", "fit_cut", "boq_waste", "well_w", "well_l",
    "well_start", "fit_min_width", "show_attach", "attach_posts"}
_LIB_DIR = [None]
_LIB_CACHE = [None]
_TEX_PATHS = ("tex_img_timber", "tex_img_finish", "tex_img_concrete")


def lib_dir():
    if _LIB_DIR[0]:
        os.makedirs(_LIB_DIR[0], exist_ok=True)
        return _LIB_DIR[0]
    return bpy.utils.user_resource("CONFIG", path="parametric_stairs_presets", create=True)


def lib_file(name):
    slug = bpy.path.clean_name(name.strip()) or "preset"
    return os.path.join(lib_dir(), slug + ".json")


def _lib_read(path):
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    if not isinstance(doc, dict):
        raise ValueError("not a preset file")
    if "props" not in doc:                      # older flat "Save Settings" file
        doc = {"format": 0, "name": os.path.splitext(os.path.basename(path))[0], "description": "",
               "scope": "FULL", "props": doc}
    if not isinstance(doc["props"], dict):
        raise ValueError("preset has no settings")
    return doc


def lib_items(force=False):
    if _LIB_CACHE[0] is None or force:
        out = []
        try:
            for fn in sorted(os.listdir(lib_dir())):
                if not fn.lower().endswith(".json"):
                    continue
                try:
                    doc = _lib_read(os.path.join(lib_dir(), fn))
                except Exception:
                    continue
                out.append(dict(name=str(doc.get("name") or os.path.splitext(fn)[0]), file=fn,
                                desc=str(doc.get("description", "")), scope=doc.get("scope", "FULL"),
                                n=len(doc["props"]), tex=doc["props"].get("tex_mode", "NONE"),
                                kind=doc["props"].get("stair_kind", "")))
        except OSError:
            pass
        out.sort(key=lambda x: x["name"].lower())
        _LIB_CACHE[0] = out
    return _LIB_CACHE[0]


def lib_doc(name):
    for it in lib_items():
        if it["name"] == name:
            return _lib_read(os.path.join(lib_dir(), it["file"]))
    raise KeyError(name)


def lib_make_doc(P, name, desc, scope):
    d = props_to_dict(P)
    d.pop("live", None)
    for k in _TEX_PATHS:
        if d.get(k):
            d[k] = os.path.normpath(os.path.abspath(bpy.path.abspath(d[k])))
    if scope == "STYLE":
        d = {k: v for k, v in d.items() if k not in _PROJECT_KEYS}
    return {"format": 1, "name": name, "description": desc, "scope": scope,
            "saved": time.strftime("%Y-%m-%d %H:%M"), "props": d}


def lib_apply(context, doc, targets):
    d = doc["props"]
    for o in targets:
        apply_dict(o.pstairs, d)
    if d.get("look"):
        apply_look(d["look"])
    tm = d.get("tex_mode")
    if tm and targets:
        apply_textures(targets[0].pstairs, "CLEAR" if tm == "NONE" else tm)


def _lib_targets(context):
    t = _targets(context)
    if not t and context.object is not None and context.object.type == "MESH" and not context.object.get("ps_src"):
        t = [context.object]
    return t


class PSTAIRS_OT_lib_save(bpy.types.Operator):
    bl_idname = "pstairs.lib_save"
    bl_label = "Save to Preset Library"
    bl_description = "Save this stair's setup as a named preset you can load in any project"
    bl_options = {"REGISTER"}
    name: StringProperty(name="Name", default="My Stair")
    description: StringProperty(name="Note", default="")
    scope: EnumProperty(name="Saves", default="STYLE", items=[
        ("STYLE", "Style only", "Type, nosing, rails, finishes and textures. Loading it keeps the dimensions, layout and void of the stair you load it on"),
        ("FULL", "Full setup", "Everything, including floor height, layout, width and going")])

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        ob = context.object
        if ob is None or ob.type != "MESH":
            self.report({"ERROR"}, "Select a stair object")
            return {"CANCELLED"}
        nm = self.name.strip()
        if not nm:
            self.report({"ERROR"}, "Give the preset a name")
            return {"CANCELLED"}
        path = lib_file(nm)
        existed = os.path.exists(path)
        doc = lib_make_doc(ob.pstairs, nm, self.description, self.scope)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=1)
        lib_items(True)
        self.report({"INFO"}, "%s preset '%s' (%d settings)" % ("Updated" if existed else "Saved", nm, len(doc["props"])))
        return {"FINISHED"}


class PSTAIRS_OT_lib_load(bpy.types.Operator):
    bl_idname = "pstairs.lib_load"
    bl_label = "Load Preset"
    bl_options = {"REGISTER", "UNDO"}
    name: StringProperty(name="Name")

    @classmethod
    def description(cls, context, props):
        for it in lib_items():
            if it["name"] == props.name:
                return "%s - %s. %s" % (("Style" if it["scope"] == "STYLE" else "Full setup"), it["kind"].title() or "stair",
                                        it["desc"] or "Load onto the selected stair(s)")
        return "Load onto the selected stair(s)"

    def execute(self, context):
        targets = _lib_targets(context)
        if not targets:
            self.report({"ERROR"}, "Select a stair object")
            return {"CANCELLED"}
        try:
            doc = lib_doc(self.name)
        except Exception as e:
            self.report({"ERROR"}, "Could not read preset: %s" % e)
            return {"CANCELLED"}
        lib_apply(context, doc, targets)
        self.report({"INFO"}, "Loaded '%s' on %d stair(s)" % (self.name, len(targets)))
        return {"FINISHED"}


class PSTAIRS_OT_lib_delete(bpy.types.Operator):
    bl_idname = "pstairs.lib_delete"
    bl_label = "Delete Preset"
    bl_description = "Remove this preset from the library"
    name: StringProperty(name="Name")

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        for it in lib_items():
            if it["name"] == self.name:
                try:
                    os.remove(os.path.join(lib_dir(), it["file"]))
                except OSError as e:
                    self.report({"ERROR"}, str(e))
                    return {"CANCELLED"}
        lib_items(True)
        return {"FINISHED"}


class PSTAIRS_OT_lib_import(bpy.types.Operator, ImportHelper):
    bl_idname = "pstairs.lib_import"
    bl_label = "Import Preset File"
    bl_description = "Add a preset .json (from a colleague, another machine, or the old Save Settings button) to the library"
    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    def execute(self, context):
        try:
            doc = _lib_read(self.filepath)
        except Exception as e:
            self.report({"ERROR"}, "Not a stair preset: %s" % e)
            return {"CANCELLED"}
        with open(lib_file(str(doc["name"])), "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=1)
        lib_items(True)
        self.report({"INFO"}, "Imported '%s'" % doc["name"])
        return {"FINISHED"}


class PSTAIRS_OT_lib_export(bpy.types.Operator, ExportHelper):
    bl_idname = "pstairs.lib_export"
    bl_label = "Export Preset File"
    bl_description = "Write this preset to a .json file you can share or back up"
    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})
    name: StringProperty(name="Name", options={"HIDDEN"})

    def invoke(self, context, event):
        self.filepath = bpy.path.clean_name(self.name) + ".json"
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        try:
            doc = lib_doc(self.name)
        except Exception as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        with open(self.filepath, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=1)
        return {"FINISHED"}


class PSTAIRS_OT_lib_refresh(bpy.types.Operator):
    bl_idname = "pstairs.lib_refresh"
    bl_label = "Refresh"
    bl_description = "Re-read the preset folder"

    def execute(self, context):
        lib_items(True)
        return {"FINISHED"}


class PSTAIRS_OT_lib_open(bpy.types.Operator):
    bl_idname = "pstairs.lib_open"
    bl_label = "Open Folder"
    bl_description = "Open the preset folder in your file manager (copy files here to share presets between machines)"

    def execute(self, context):
        try:
            bpy.ops.wm.path_open(filepath=lib_dir())
        except Exception as e:
            self.report({"INFO"}, lib_dir())
        return {"FINISHED"}


def apply_textures(P, mode):
    """Put (or remove) textures on the shared stair materials and remember the mode on every stair."""
    grid = None
    if mode == "UV_GRID":
        grid = bpy.data.images.get("PS_UVGrid")
        if grid is None:
            grid = bpy.data.images.new("PS_UVGrid", 1024, 1024)
            grid.generated_type = "UV_GRID"
    paths = {"timber": P.tex_img_timber, "finish": P.tex_img_finish, "concrete": P.tex_img_concrete}
    missing = []
    for cls, names in _TEX_GROUPS.items():
        for nm in names:
            mat = get_mat(nm)
            if mode == "CLEAR":
                _strip_tex(mat)
            elif mode == "UV_GRID":
                _apply_tex(mat, "GRID", grid)
            elif mode == "IMAGES":
                path = bpy.path.abspath(paths[cls]) if paths[cls] else ""
                img = None
                if path:
                    try:
                        img = bpy.data.images.load(path, check_existing=True)
                    except Exception:
                        missing.append(paths[cls])
                _apply_tex(mat, "IMAGE" if img else "NONE", img)
            else:
                kind = {"timber": "TIMBER", "concrete": "CONCRETE"}.get(cls, P.tex_finish)
                _apply_tex(mat, kind)
    tag = "NONE" if mode == "CLEAR" else mode
    for o in bpy.data.objects:
        if o.type == "MESH" and not o.get("ps_part"):
            o.pstairs.tex_mode = tag
    return missing


def _void_frame(P, context):
    """(A, B, origin, rotation, well object) of the stairwell void."""
    wo = P.well_obj
    if wo is not None:
        mw = wo.matrix_world
        cs = [Vector(cc) for cc in wo.bound_box]
        x0, x1 = min(c.x for c in cs), max(c.x for c in cs)
        y0, y1 = min(c.y for c in cs), max(c.y for c in cs)
        A = (x1 - x0) * Vector(mw.col[0][:3]).length
        B = (y1 - y0) * Vector(mw.col[1][:3]).length
        return A, B, mw @ Vector((x0, y0, 0.0)), mw.to_euler("XYZ").z, wo
    return P.well_w, P.well_l, Vector(context.scene.cursor.location), 0.0, None


def cut_opening(context, ob, slab, margin, apply):
    """Boolean-cut the stairwell void through a floor slab. The cutter follows the void object when there is one."""
    from mathutils import Matrix
    P = ob.pstairs
    if slab is None or slab.type != "MESH":
        raise ValueError("pick a mesh slab object")
    A, B, origin, rzv, wo = _void_frame(P, context)
    mw = slab.matrix_world
    zs = [(mw @ Vector(c)).z for c in slab.bound_box]
    zmin, zmax = min(zs), max(zs)
    if zmax - zmin < 0.01:
        raise ValueError("the slab has no thickness (needs a solid slab to cut)")
    pad = 0.1
    uid = _ensure_uid(ob)
    cutter = next((o for o in bpy.data.objects if o.get("ps_opening_for") == uid), None)
    if wo is not None:
        inv = wo.matrix_world.inverted()
        cs = [Vector(cc) for cc in wo.bound_box]
        sx = max(Vector(wo.matrix_world.col[0][:3]).length, 1e-6)
        sy = max(Vector(wo.matrix_world.col[1][:3]).length, 1e-6)
        lz = [(inv @ Vector((wo.matrix_world.translation.x, wo.matrix_world.translation.y, z))).z
              for z in (zmin - pad, zmax + pad)]
        x0, x1 = min(c.x for c in cs) - margin / sx, max(c.x for c in cs) + margin / sx
        y0, y1 = min(c.y for c in cs) - margin / sy, max(c.y for c in cs) + margin / sy
        z0_, z1_ = min(lz), max(lz)
        loc, rot = Vector((0, 0, 0)), 0.0
    else:
        hx, hy = A / 2 + margin, B / 2 + margin
        x0, x1, y0, y1 = -hx, hx, -hy, hy
        z0_, z1_ = -(zmax - zmin) / 2 - pad, (zmax - zmin) / 2 + pad
        c, s = math.cos(rzv), math.sin(rzv)
        ctr = origin + Vector((A / 2 * c - B / 2 * s, A / 2 * s + B / 2 * c, 0.0))
        loc, rot = Vector((ctr.x, ctr.y, (zmin + zmax) / 2)), rzv
    verts = [(x0, y0, z0_), (x1, y0, z0_), (x1, y1, z0_), (x0, y1, z0_),
             (x0, y0, z1_), (x1, y0, z1_), (x1, y1, z1_), (x0, y1, z1_)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    if cutter is None:
        me = bpy.data.meshes.new(ob.name + "_Opening")
        cutter = bpy.data.objects.new(ob.name + "_Opening", me)
        context.scene.collection.objects.link(cutter)
        cutter["ps_opening_for"] = uid
        cutter.display_type = "WIRE"
        cutter.hide_render = True
    me = cutter.data
    me.clear_geometry()
    me.from_pydata(verts, [], faces)
    me.update()
    cutter.parent = wo
    cutter.matrix_parent_inverse = Matrix.Identity(4)
    cutter.location = loc
    cutter.rotation_euler = (0.0, 0.0, rot)
    cutter.scale = (1.0, 1.0, 1.0)
    mname = "Stair Opening " + ob.name
    mod = slab.modifiers.get(mname) or slab.modifiers.new(mname, "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = cutter
    try:
        mod.solver = "EXACT"
    except Exception:
        pass
    if apply:
        if slab.data.users > 1:
            slab.data = slab.data.copy()
        with context.temp_override(object=slab, active_object=slab, selected_objects=[slab]):
            bpy.ops.object.modifier_apply(modifier=mname)
        cm = cutter.data
        bpy.data.objects.remove(cutter, do_unlink=True)
        if cm.users == 0:
            bpy.data.meshes.remove(cm)
    return cutter


class PSTAIRS_OT_cut_opening(bpy.types.Operator):
    bl_idname = "pstairs.cut_opening"
    bl_label = "Cut Opening in Slab"
    bl_description = "Cut the stairwell void through the floor slab with a live Boolean (or make it permanent)"
    bl_options = {"REGISTER", "UNDO"}
    apply: BoolProperty(name="Make Permanent", default=False)

    def execute(self, context):
        ob = context.object
        if ob is None or ob.type != "MESH":
            self.report({"ERROR"}, "Select the stair control object")
            return {"CANCELLED"}
        P = ob.pstairs
        try:
            cut_opening(context, ob, P.slab_obj, P.opening_margin, self.apply)
        except Exception as e:
            self.report({"ERROR"}, "Opening not cut: %s" % e)
            return {"CANCELLED"}
        self.report({"INFO"}, "Opening %s" % ("cut permanently" if self.apply else "cut (live Boolean)"))
        return {"FINISHED"}


def _ensure_uid(obj):
    """Stable identity of a source object, so parts survive renames and copies never share parts."""
    uid = obj.get("ps_uid")
    if uid:
        others = [o for o in bpy.data.objects if o is not obj and o.get("ps_uid") == uid]
        if any(o.get("ps_part") is None for o in others) and not any(
                o.get("ps_part") is not None and o.get("ps_src") == obj.name for o in others):
            uid = None
    if not uid:
        uid = uuid.uuid4().hex[:12]
        obj["ps_uid"] = uid
    return uid


def _find_parts(obj, uid):
    """All generated part objects that belong to this source (any collection). Returns (by part name, duplicates)."""
    found, dupes = {}, []
    for ob in bpy.data.objects:
        pn = ob.get("ps_part")
        if pn is None:
            continue
        ou = ob.get("ps_uid")
        if ou:
            src = ob.get("ps_src")
            mine = ou == uid and (src == obj.name or src is None or src not in bpy.data.objects)
        else:
            mine = ob.get("ps_src") == obj.name
        if not mine:
            continue
        if pn in found:
            dupes.append(ob)
        else:
            found[pn] = ob
    return found, dupes


def _drop(ob):
    me = ob.data
    bpy.data.objects.remove(ob, do_unlink=True)
    if me and me.users == 0:
        bpy.data.meshes.remove(me)


def write_parts(obj, parts):
    scene = bpy.context.scene
    uid = _ensure_uid(obj)
    existing, dupes = _find_parts(obj, uid)
    for ob in dupes:
        _drop(ob)
    cname = "Stairs_" + obj.name
    coll = None
    for ob in existing.values():
        if ob.users_collection:
            coll = ob.users_collection[0]
            break
    if coll is None:
        coll = bpy.data.collections.get(cname)
        if coll is None:
            coll = bpy.data.collections.new(cname)
    elif coll.name != cname and coll.name.startswith("Stairs_") and bpy.data.collections.get(cname) is None:
        coll.name = cname
    if coll.users == 0:
        scene.collection.children.link(coll)
    Pu = obj.pstairs
    _UV_ON[0] = bool(Pu.gen_uvs)
    _UV_TILES.update(timber=Pu.uv_timber, finish=Pu.uv_finish, concrete=Pu.uv_concrete, other=Pu.uv_other)
    for pname, mb in parts.items():
        if not mb.f:
            continue
        ob = existing.pop(pname, None)
        if ob is None:
            me = bpy.data.meshes.new("%s_%s" % (obj.name, pname))
            ob = bpy.data.objects.new("%s_%s" % (obj.name, pname), me)
            ob["ps_part"] = pname
            coll.objects.link(ob)
        ob["ps_src"] = obj.name
        ob["ps_uid"] = uid
        want = "%s_%s" % (obj.name, pname)
        if ob.name != want and bpy.data.objects.get(want) is None:
            ob.name = want
            if ob.data.users == 1 and bpy.data.meshes.get(want) is None:
                ob.data.name = want
        me = ob.data
        if len(me.materials) == 0:
            for mn in mb.mats:
                me.materials.append(get_mat(mn))
        fill_mesh(me, mb)
    for ob in existing.values():
        _drop(ob)


def _run_checks(obj):
    """Geometry checks for the supports and railings of the stair that was just generated."""
    P = obj.pstairs
    out = []

    def add(lv, t):
        out.append((lv, t))

    fl = list(_FL)
    W = min([f["width"] for f in fl]) if fl else 0.0
    kind = P.stair_kind
    mm = lambda v: "%.0f mm" % (v * 1000.0)
    side_st = (kind in ("STEEL", "SAWTOOTH") and P.stringer != "CENTER") or (
        kind == "STANDARD" and P.structure != "SOLID" and P.stringer == "SIDE")
    if side_st and W > 0 and 2 * (P.stringer_offset + P.stringer_w) > 0.9 * W:
        add("WARN", "Side stringers (2 x %s) fill a %s wide stair" % (mm(P.stringer_w), mm(W)))
    if kind in ("FLOATING", "CANTILEVER") and W > 0:
        if P.support_side != "BOTH" and W / max(P.tread_thk, 0.01) > 15:
            add("WARN", "%s treads span %s from one side - confirm with your engineer" % (mm(P.tread_thk), mm(W)))
        if kind == "FLOATING" and P.embed < 0.09:
            add("WARN", "Wall embed of %s: structural review required" % mm(P.embed))
        if kind == "CANTILEVER" and P.embed > W / 2:
            add("WARN", "Bracket length %s is more than half the stair width" % mm(P.embed))
    if kind == "SUSPENDED":
        if P.susp_top < 0.3:
            add("WARN", "Rods end only %s above the upper floor - confirm the fixing level" % mm(P.susp_top))
        if P.rod_d < 0.012:
            add("WARN", "Rod diameter %s is slim for hanging treads" % mm(P.rod_d))
        if P.engine == "PARAM" and P.layout in ("HELICAL", "CURVED") and P.sweep > 360:
            add("WARN", "Rods pass through the turn above (sweep over 360 degrees)")
    if fl:
        floor0 = min(f["z0"] for f in fl)
        Ly = layer_info(P)
        slab = Ly["lt"] + Ly["ft"] + Ly["ut"]
        for k_, lab, p in _ATT:
            if k_ in ("STRINGER_FOOT", "BEAM_FOOT") and floor0 - p.z > slab + 0.005:
                add("WARN", "%s drops %s below the lower floor (landing slab %s)" % (lab, mm(floor0 - p.z), mm(slab)))
    # ---- railings
    if P.use_rails and P.rail_sides != "NONE":
        base = _style(P, False)
        used = [base] + [STYLE_BY_ID[k] for k in (P.rail_style_left, P.rail_style_right) if k in STYLE_BY_ID]
        if P.rail_height < 0.9:
            add("WARN", "Rail height %s is under 900 mm" % mm(P.rail_height))
        if not 0.03 <= P.hand_size <= 0.06:
            add("INFO", "Handrail size %s is outside the 30-60 mm grip range" % mm(P.hand_size))
        seen = set()
        for st in used:
            k = st["kind"]
            if k in seen:
                continue
            seen.add(k)
            if k in ("bal", "turned", "twist", "flat", "lattice"):
                clear = P.baluster_spacing - P.baluster_size
                if st.get("sp"):
                    clear = st["sp"] - st.get("bs", P.baluster_size)
                if clear > 0.1:
                    add("WARN", "Baluster gaps of %s exceed the 100 mm preset; verify applicable rules" % mm(clear))
            if k == "cable" and P.cable_gap - P.cable_dia > 0.1:
                add("WARN", "Cable gaps of %s exceed the 100 mm preset; verify applicable rules" % mm(P.cable_gap - P.cable_dia))
            if k == "bracket" and P.wall_gap < 0.04:
                add("WARN", "Handrail to wall clearance %s is under 40 mm" % mm(P.wall_gap))
    if P.engine == "PARAM" and P.layout in ("L_SHAPED", "U_SHAPED", "MULTI") and 0 < P.land_d < P.st_width:
        add("INFO", "Turn landings are widened to the stair width (%s)" % mm(P.st_width))
    counts = {}
    for k_, lab, p in _ATT:
        if k_ != "POST_BASE":
            counts[k_] = counts.get(k_, 0) + 1
    if counts:
        add("INFO", "%d support attachment points (%s)" % (
            sum(counts.values()), ", ".join("%d %s" % (v, k.lower().replace("_", " ")) for k, v in sorted(counts.items()))))
    order = {"WARN": 0, "INFO": 1, "OK": 2}
    out.sort(key=lambda x: order[x[0]])
    if not any(lv == "WARN" for lv, _t in out):
        out.insert(0, ("INFO", "No warnings from limited checks; not a compliance or structural review"))
    return out


def _attach_coll(obj, create):
    uid = obj.get("ps_uid")
    for c in bpy.data.collections:
        if uid and c.get("ps_attach_uid") == uid:
            return c
    if not create:
        return None
    c = bpy.data.collections.new("Attach_" + obj.name)
    c["ps_attach_uid"] = uid
    bpy.context.scene.collection.children.link(c)
    return c


def _drop_attach(obj):
    c = _attach_coll(obj, False)
    if c is None:
        return
    for o in list(c.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.data.collections.remove(c)


def _sync_attach(obj):
    """Keep one empty per support attachment point (named, typed, placed in world space)."""
    P = obj.pstairs
    if not P.show_attach:
        _drop_attach(obj)
        return
    coll = _attach_coll(obj, True)
    want = "Attach_" + obj.name
    if coll.name != want and bpy.data.collections.get(want) is None:
        coll.name = want
    have = {o.get("ps_att"): o for o in coll.objects}
    used, labels = set(), {}
    for k_, lab, p in _ATT_BY_OBJ.get(obj.name, []):
        if k_ == "POST_BASE" and not P.attach_posts:
            continue
        n = labels.get(lab, 0)
        labels[lab] = n + 1
        key = lab if n == 0 else "%s #%d" % (lab, n + 1)
        o = have.get(key)
        if o is None:
            o = bpy.data.objects.new("%s %s" % (obj.name, key), None)
            o.empty_display_type = "SPHERE"
            o.empty_display_size = 0.04 if k_ != "POST_BASE" else 0.02
            o["ps_att"] = key
            coll.objects.link(o)
        o["ps_att_kind"] = k_
        o.location = p
        used.add(key)
    for key, o in have.items():
        if key not in used:
            bpy.data.objects.remove(o, do_unlink=True)



_busy = False


def _props_sig(obj):
    P = obj.pstairs
    mw = tuple(round(x, 6) for row in obj.matrix_world for x in row)
    return (mw, repr(sorted(props_to_dict(P).items())))


def rebuild(obj, force=True):
    global _busy, _WALL_BVHS
    if _busy:
        return
    _busy = True
    try:
        P = obj.pstairs
        _WALL_BVHS = _wall_trees(obj, P, bpy.context) if P.engine != "PARAM" else []
        if P.engine == "PARAM":
            z0, H = _levels(obj, P)
            sig = (_props_sig(obj), round(z0, 6), round(H, 6))
            if not force and _SIG.get(obj.name) == sig:
                return
            parts = _generate_param(obj, obj.name)
        else:
            verts, faces, edges = read_mesh(obj)
            sig = (_props_sig(obj), tuple(round(c, 6) for v in verts for c in v),
                   tuple(tuple(f["vi"]) for f in faces), tuple(sorted((k, e["seam"], e.get("railmark", 0)) for k, e in edges.items())))
            if not force and _SIG.get(obj.name) == sig:
                return
            _META.pop(obj.name, None)
            parts = generate(verts, faces, edges, P)
        _HEADROOM.pop(obj.name, None)
        _CLASH.pop(obj.name, None)
        _STATS_BY_OBJ[obj.name] = list(_STATS)
        write_parts(obj, parts)
        _ATT_BY_OBJ[obj.name] = list(_ATT)
        _FL_BY_OBJ[obj.name] = list(_FL)
        _RAIL_BY_OBJ[obj.name] = list(_RS)
        _CHK[obj.name] = _run_checks(obj)
        _sync_attach(obj)
        _SIG[obj.name] = sig
        _ERR.pop(obj.name, None)
    except Exception as e:
        traceback.print_exc()
        _ERR[obj.name] = "%s: %s" % (type(e).__name__, e)
    finally:
        _WALL_BVHS = []
        _busy = False


def clear_generated(obj):
    uid = obj.get("ps_uid") or ""
    found, dupes = _find_parts(obj, uid)
    colls = set()
    for ob in list(found.values()) + dupes:
        colls.update(ob.users_collection)
        _drop(ob)
    c0 = bpy.data.collections.get("Stairs_" + obj.name)
    if c0:
        colls.add(c0)
    for coll in colls:
        if coll.name.startswith("Stairs_") and not coll.objects:
            bpy.data.collections.remove(coll)
    _SIG.pop(obj.name, None)
    _drop_attach(obj)


# =============================================================================
#  Properties
# =============================================================================

def _upd(self, context):
    if self.generated and self.live:
        rebuild(self.id_data)


def _L(name, default, mn, mx, desc=""):
    return FloatProperty(name=name, default=default, min=mn, max=mx, unit="LENGTH",
                         precision=3, description=desc, update=_upd)


class PSProps(bpy.types.PropertyGroup):
    generated: BoolProperty(default=False)
    lower_level_offset: FloatProperty(name="Lower Finished Floor Offset", default=0.0, min=-2, max=2, unit="LENGTH", update=_upd,
        description="Offset from lower reference object centre to finished floor")
    upper_level_offset: FloatProperty(name="Upper Finished Floor Offset", default=0.0, min=-2, max=2, unit="LENGTH", update=_upd,
        description="Offset from upper reference object centre to finished floor")
    target_riser_max: FloatProperty(name="Maximum Riser Target", default=0.19, min=0.05, max=0.4, unit="LENGTH")
    target_going_min: FloatProperty(name="Minimum Going Target", default=0.25, min=0.05, max=1.0, unit="LENGTH")
    target_headroom: FloatProperty(name="Headroom Target", default=2.0, min=0.5, max=5.0, unit="LENGTH")
    headroom_range: FloatProperty(name="Probe Range", default=5.0, min=1, max=20, unit="LENGTH")
    section_offset: FloatProperty(name="Section X Offset", default=0.0, min=-100, max=100, unit="LENGTH",
        description="Cut plane offset along the source object's local X axis")
    clash_collection: PointerProperty(name="Clash Objects", type=bpy.types.Collection,
        description="Objects to check for surface intersections with generated stair parts")
    headroom_collection: PointerProperty(name="Overhead Objects", type=bpy.types.Collection,
        description="Collection of slabs, beams and ceilings to sample for headroom")
    live: BoolProperty(name="Live Update", default=True, update=_upd,
                       description="Rebuild the stairs automatically when the plane or any setting changes")
    hide_source_render: BoolProperty(name="Hide Source in Render", default=True,
                                     description="Hide the source plane from renders once stairs exist")
    flat_tol: FloatProperty(name="Flat Tolerance", default=3.0, min=0.0, max=20.0, update=_upd,
                            description="Faces tilted less than this (degrees) count as landings")
    max_angle: FloatProperty(name="Max Slope", default=65.0, min=10.0, max=85.0, update=_upd,
                             description="Faces steeper than this (degrees) are ignored")

    riser_mode: EnumProperty(name="Steps", update=_upd, items=[
        ("HEIGHT", "By Riser Height", "Number of steps follows the target riser height"),
        ("COUNT", "By Step Count", "Fixed number of steps per flight")])
    riser_height: _L("Riser Height", 0.175, 0.05, 0.30, "Target riser height")
    step_count: IntProperty(name="Steps per Flight", default=10, min=1, max=100, update=_upd)

    structure: EnumProperty(name="Structure", update=_upd, items=[
        ("CLOSED", "Tread + Riser Boards", "Separate treads, risers and stringers"),
        ("SOLID", "Solid (Concrete)", "Stepped solid mass")])
    tread_thk: _L("Tread Thickness", 0.04, 0.005, 0.2)
    nosing: _L("Nosing", 0.03, 0.0, 0.1, "Tread overhang past the riser")
    side_overhang: _L("Side Overhang", 0.0, 0.0, 0.1)
    use_risers: BoolProperty(name="Risers", default=True, update=_upd, description="Off = open risers")
    riser_thk: _L("Riser Thickness", 0.02, 0.005, 0.1)
    solid_fill: BoolProperty(name="Fill to Ground", default=True, update=_upd,
                             description="Solid steps go down to the low level (off = waist slab)")
    waist: _L("Waist Thickness", 0.15, 0.05, 0.5)

    stringer: EnumProperty(name="Stringer", default="SIDE", update=_upd, items=[
        ("NONE", "None", ""), ("SIDE", "Side", "Beams along both sides"), ("CENTER", "Center", "Single central spine")])
    stringer_w: _L("Stringer Width", 0.05, 0.02, 0.3)
    stringer_depth: _L("Stringer Depth", 0.22, 0.05, 0.6)
    stringer_offset: _L("Stringer Inset", 0.0, 0.0, 0.5)

    use_finish: BoolProperty(name="Finishes", default=True, update=_upd, description="Add tread/riser/landing finish layers")
    finish_thk: _L("Tread Finish", 0.02, 0.002, 0.08)
    riser_finish_thk: _L("Riser Finish", 0.012, 0.002, 0.05)
    landing_thk: _L("Landing Thickness", 0.15, 0.03, 0.6)

    rail_edge_mode: EnumProperty(name="Edge Mode", default="AUTO", update=_upd, items=[
        ("AUTO", "Automatic + assigned", "Use open edges except exclusions; assigned edges override walls"),
        ("ASSIGNED", "Assigned only", "Only use edges explicitly assigned")])
    detect_walls: BoolProperty(name="Detect Walls", default=False, update=_upd)
    wall_collection: PointerProperty(name="Wall Collection", type=bpy.types.Collection, update=_upd,
        description="Choose wall meshes; if empty, mesh objects with wall in their name are used")
    wall_detect_distance: _L("Detection Distance", 0.15, 0.005, 2.0)
    wall_probe_height: _L("Probe Height", 0.4, 0.02, 3.0)
    use_rails: BoolProperty(name="Railings", default=True, update=_upd)
    rail_sides: EnumProperty(name="Flight Sides", default="BOTH", update=_upd, items=[
        ("BOTH", "Both", ""), ("LEFT", "Left", "Left side when walking up"), ("RIGHT", "Right", "Right side when walking up"),
        ("NONE", "None", "")])
    rail_landing: BoolProperty(name="Landing Railings", default=True, update=_upd,
                               description="Railings on open landing edges (mark edges as Seam to skip them)")
    railing_style: EnumProperty(name="Railing Style", items=_rail_items, update=_upd)
    standalone_style: EnumProperty(name="Standalone Style", items=_rail_items,
        description="Railing design for standalone edge railings, independent of stairs")
    standalone_rail_height: FloatProperty(name='Rail Height', default=0.95, min=0.5, max=1.5, unit="LENGTH", precision=3)
    standalone_post_size: FloatProperty(name='Post Size', default=0.05, min=0.015, max=0.3, unit="LENGTH", precision=3)
    standalone_post_spacing: FloatProperty(name='Post Spacing', default=1.2, min=0.3, max=3, unit="LENGTH", precision=3)
    standalone_baluster_size: FloatProperty(name='Baluster Size', default=0.02, min=0.006, max=0.08, unit="LENGTH", precision=3)
    standalone_baluster_spacing: FloatProperty(name='Baluster Spacing', default=0.11, min=0.04, max=0.3, unit="LENGTH", precision=3)
    standalone_hand_size: FloatProperty(name='Handrail Size', default=0.05, min=0.02, max=0.15, unit="LENGTH", precision=3)
    standalone_rail_offset: FloatProperty(name='Rail Offset', default=0.04, min=0, max=0.3, unit="LENGTH", precision=3)
    standalone_glass_thk: FloatProperty(name='Glass Thickness', default=0.012, min=0.004, max=0.04, unit="LENGTH", precision=3)
    standalone_wall_thk: FloatProperty(name='Parapet Thickness', default=0.15, min=0.05, max=0.4, unit="LENGTH", precision=3)
    standalone_cable_dia: FloatProperty(name='Cable Diameter', default=0.008, min=0.003, max=0.02, unit="LENGTH", precision=3)
    standalone_cable_gap: FloatProperty(name='Cable Pitch', default=0.1, min=0.04, max=0.3, unit="LENGTH", precision=3)
    standalone_wall_gap: FloatProperty(name='Wall Clearance', default=0.07, min=0.03, max=0.2, unit="LENGTH", precision=3)
    standalone_bracket_spacing: FloatProperty(name='Bracket Spacing', default=0.9, min=0.4, max=2, unit="LENGTH", precision=3)
    standalone_bar_count: IntProperty(name="Bars", default=4, min=1, max=10)

    landing_style: EnumProperty(name="Landing Style", items=_land_items, update=_upd)
    rail_height: _L("Rail Height", 0.95, 0.5, 1.5)
    post_size: _L("Post Size", 0.05, 0.015, 0.3)
    post_spacing: _L("Post Spacing", 1.2, 0.3, 3.0)
    baluster_size: _L("Baluster Size", 0.02, 0.006, 0.08)
    baluster_spacing: _L("Baluster Spacing", 0.11, 0.04, 0.3)
    hand_size: _L("Handrail Size", 0.05, 0.02, 0.15)
    rail_offset: _L("Rail Offset", 0.04, 0.0, 0.3, "Distance of the railing centre-line from the plane edge")
    glass_thk: _L("Glass Thickness", 0.012, 0.004, 0.04)
    wall_thk: _L("Parapet Thickness", 0.15, 0.05, 0.4)
    bar_count: IntProperty(name="Bars", default=4, min=1, max=10, update=_upd)

    # ---- v2: layered thickness, nosing, inlay
    thk_mode: EnumProperty(name="Thickness Mode", default="ADD", update=_upd, items=[
        ("ADD", "Board + Layers", "Tread Thickness is the structural board only; underlay and finish are added on top"),
        ("TOTAL", "Total Thickness", "Tread Thickness is the TOTAL step thickness (board + underlay + finish)")])
    underlay_thk: _L("Underlay / Bed", 0.0, 0.0, 0.08, "Mortar / adhesive bed between the board and the finish (needs Finishes on)")
    nosing_style: EnumProperty(name="Nosing Profile", default="ROUNDED", update=_upd, items=[
        ("SQUARE", "Square", "Plain square edge"),
        ("EASED", "Eased", "Slightly softened top edge"),
        ("ROUNDED", "Rounded", "Rounded top edge"),
        ("BULLNOSE", "Bullnose", "Fully rounded front edge"),
        ("CHAMFER", "Chamfer", "Bevelled top edge"),
        ("UNDERCUT", "Undercut", "Angled underside that creates a shadow line"),
        ("DROP", "Drop Lip", "Thin lip that hangs down over the riser"),
        ("DROP_ROUND", "Rounded Drop Lip", "Drop lip with rounded edges"),
        ("BEVEL", "Bevel", "Shallow angled top edge (wider than a chamfer)"),
        ("OVERHANG", "Thin Overhang", "Slab edge that projects past the riser and thins to a knife edge"),
        ("WATERFALL", "Waterfall Edge", "Finish slab wraps down over the riser to the tread below")])
    nosing_size: _L("Profile Size", 0.015, 0.002, 0.06, "Radius / chamfer size of the nosing profile")
    lip_depth: _L("Lip Depth", 0.04, 0.01, 0.15, "How far the drop lip hangs below the finish")
    nosing_inlay: BoolProperty(name="Nosing Inlay Strip", default=False, update=_upd,
                               description="Metal strip set into the front of every tread")
    inlay_w: _L("Inlay Width", 0.012, 0.004, 0.05)
    inlay_inset: _L("Inlay Side Inset", 0.0, 0.0, 0.2, "Shorten the strip from each side")

    # ---- v2: railing luxury
    hand_shape: EnumProperty(name="Handrail Shape", default="AUTO", update=_upd, items=[
        ("AUTO", "Style Default", ""), ("ROUND", "Round", ""), ("RECT", "Rectangular", ""),
        ("SLIM", "Slim Flat", ""), ("OVAL", "Oval", ""), ("CHAMFER", "Chamfered", "")])
    rail_end: EnumProperty(name="Free Rail Ends", default="RETURN", update=_upd, items=[
        ("NONE", "Cut Flat", ""), ("RETURN", "Return Curl", "Handrail curls down at free ends"),
        ("BALL", "Ball End", "Spherical end cap")])
    newel_mode: EnumProperty(name="Newels", default="ALL", update=_upd, items=[
        ("NONE", "None", "Only normal posts"),
        ("ENDS", "Rail Ends", "Heavy newel at the start/end of each rail run"),
        ("CORNERS", "Corners / Turns", "Heavy newel at every turn"),
        ("ALL", "Ends + Corners", "Newels at ends and turns")])
    corner_angle: FloatProperty(name="Turn Angle", default=20.0, min=1.0, max=90.0, update=_upd,
                                description="Rail direction changes above this angle (degrees) count as a corner")
    newel_shape: EnumProperty(name="Newel Shape", default="SQUARE", update=_upd, items=[
        ("SQUARE", "Square", ""), ("ROUND", "Round", ""), ("OCTAGON", "Octagonal", ""),
        ("TAPERED", "Tapered", "Narrower towards the top")])
    newel_size: _L("Newel Size", 0.08, 0.03, 0.3)
    newel_extra: _L("Newel Rise", 0.05, 0.0, 0.3, "How far the newel rises above the handrail")
    newel_cap: EnumProperty(name="Newel Cap", default="CHAMFER", update=_upd, items=[
        ("NONE", "None", ""), ("FLAT", "Flat Slab", ""), ("CHAMFER", "Chamfered", ""), ("PYRAMID", "Pyramid", ""),
        ("BALL", "Ball", ""), ("DOME", "Dome", ""), ("FINIAL", "Finial", "")])
    newel_base: EnumProperty(name="Newel Base", default="NONE", update=_upd, items=[
        ("NONE", "None", ""), ("PLATE", "Base Plate", ""), ("COLLAR", "Collar", "")])
    post_plate: BoolProperty(name="Post Base Plates", default=False, update=_upd,
                             description="Small plate at the foot of every normal post")
    led_rail: BoolProperty(name="LED Under Handrail", default=False, update=_upd)
    led_steps: BoolProperty(name="LED Under Nosing", default=False, update=_upd)
    look: EnumProperty(name="Look", items=LOOK_ITEMS)

    # ---- v3: source / engine
    engine: EnumProperty(name="Source", default="PLANE", update=_upd, items=[
        ("PLANE", "From Planes", "Flights and landings follow the planes you model"),
        ("PARAM", "Parametric", "Geometry is driven by floor height, tread depth, riser, width and landing settings; "
                                "the object's position and Z rotation place the stair")])
    layout: EnumProperty(name="Layout", default="STRAIGHT", update=_upd, items=[
        ("STRAIGHT", "Straight", "Single flight with optional end landings"),
        ("L_SHAPED", "L-Shaped", "Two flights with a quarter-turn landing"),
        ("U_SHAPED", "U-Shaped", "Two flights with a half-turn landing"),
        ("MULTI", "Multi-Flight", "Several flights separated by landings"),
        ("CURVED", "Curved", "Single flight following an arc"),
        ("HELICAL", "Helical", "Continuous flight winding around an open well"),
        ("SPIRAL", "Spiral", "Wedge treads around a central pole")])
    floor_height: _L("Floor to Floor", 3.0, 0.3, 12.0, "Finished lower floor to finished upper floor")
    lower_ref: PointerProperty(type=bpy.types.Object, name="Lower Floor", update=_upd,
                               description="Optional plane/empty that defines the lower floor level")
    upper_ref: PointerProperty(type=bpy.types.Object, name="Upper Floor", update=_upd,
                               description="Optional plane/empty that defines the upper floor level (overrides Floor to Floor)")
    st_width: _L("Stair Width", 1.1, 0.3, 4.0)
    going: _L("Tread Depth", 0.28, 0.15, 0.6, "Going of each step")
    land_d: _L("Landing Depth", 0.0, 0.0, 4.0, "Intermediate landing depth (0 = stair width)")
    land_w: _L("Landing Width", 0.0, 0.0, 6.0, "Landing width (0 = stair width)")
    lower_land: BoolProperty(name="Lower Landing", default=True, update=_upd)
    upper_land: BoolProperty(name="Upper Landing", default=True, update=_upd)
    end_land_d: _L("End Landing Depth", 1.0, 0.2, 5.0)
    flight_count: IntProperty(name="Flights", default=3, min=2, max=8, update=_upd)
    split: FloatProperty(name="First Flight Share", default=0.5, min=0.1, max=0.9, update=_upd,
                         description="Share of the steps in the first flight of L / U stairs")
    multi_turn: EnumProperty(name="Turns", default="SWITCHBACK", update=_upd, items=[
        ("STRAIGHT", "Straight Through", "Landings in line with the flights"),
        ("QUARTER", "Quarter Turns", "90 degree turn at every landing"),
        ("SWITCHBACK", "Switchback", "180 degree turn at every landing")])
    turn_dir: EnumProperty(name="Turn Direction", default="LEFT", update=_upd, items=[
        ("LEFT", "Left", "Turns left (anti-clockwise) when climbing"), ("RIGHT", "Right", "Turns right (clockwise)")])
    well_gap: _L("Well Gap", 0.1, 0.0, 1.5, "Gap between the two flights of a U / switchback stair")
    curve_radius: _L("Inner Radius", 1.0, 0.05, 6.0)
    sweep: FloatProperty(name="Sweep Angle", default=180.0, min=15.0, max=1440.0, update=_upd,
                         description="Total turning angle of curved / helical stairs (degrees)")
    pole_r: _L("Pole Radius", 0.06, 0.02, 0.3)
    spiral_r: _L("Outer Radius", 0.9, 0.4, 3.0)
    step_ang: FloatProperty(name="Angle per Step", default=24.0, min=8.0, max=60.0, update=_upd)

    # ---- v3: stair types
    stair_kind: EnumProperty(name="Stair Type", default="STANDARD", update=_upd, items=[
        ("STANDARD", "Standard", "Boards, risers, stringers or solid steps as set in Treads, Risers, Structure"),
        ("FLOATING", "Floating", "Open slabs fixed into a wall, no visible stringer"),
        ("CANTILEVER", "Cantilever", "Treads project from a single side box beam"),
        ("SUSPENDED", "Suspended", "Treads hang from rods fixed to the ceiling"),
        ("STEEL", "Steel Stringer", "Plate, box or channel steel stringers with tread brackets"),
        ("MONOLITHIC", "Monolithic Concrete", "One continuous cast mass with a sloping soffit"),
        ("ZIGZAG", "Zigzag (Folded Plate)", "Single folded plate forming treads and risers (straight flights)"),
        ("SAWTOOTH", "Sawtooth Stringer", "Notched saw-tooth stringers carrying the treads (straight flights)")])
    support_side: EnumProperty(name="Support Side", default="RIGHT", update=_upd, items=[
        ("LEFT", "Left", "Left when climbing"), ("RIGHT", "Right", "Right when climbing"), ("BOTH", "Both", "")])
    wall_anchor: BoolProperty(name="Wall Anchors", default=True, update=_upd,
                              description="Show the steel anchors that carry floating treads into the wall")
    embed: _L("Anchor / Bracket Length", 0.12, 0.02, 0.5)
    rod_d: _L("Rod Diameter", 0.016, 0.006, 0.06)
    susp_top: _L("Suspension Height", 2.4, 0.3, 8.0, "Rods run this far above the upper floor level")
    steel_sec: EnumProperty(name="Steel Section", default="PLATE", update=_upd, items=[
        ("PLATE", "Flat Plate", ""), ("BOX", "Box Section", ""), ("CHANNEL", "Channel", "")])
    steel_t: _L("Steel Thickness", 0.008, 0.003, 0.05)
    fold_t: _L("Fold Thickness", 0.06, 0.01, 0.3)

    # ---- v4: railings and structural coordination
    rail_style_left: EnumProperty(name="Left Side Style", items=_land_items, update=_upd,
                                  description="Railing style for the left side when climbing (e.g. wall handrail on the wall side)")
    rail_style_right: EnumProperty(name="Right Side Style", items=_land_items, update=_upd,
                                   description="Railing style for the right side when climbing")
    cable_dia: _L("Cable Diameter", 0.008, 0.003, 0.02)
    cable_gap: _L("Cable Pitch", 0.10, 0.04, 0.3, "Vertical distance between cable centres")
    wall_gap: _L("Wall Clearance", 0.07, 0.03, 0.2, "Wall handrail: centre of the rail to the wall face")
    bracket_spacing: _L("Bracket Spacing", 0.9, 0.4, 2.0)
    beam_top: FloatProperty(name="Beam Height", default=0.4, min=-0.5, max=1.0, update=_upd,
                            description="Cantilever beam: how far the beam top rises above the tread underside line, as a share of the beam depth")
    stub_pos: FloatProperty(name="Bracket Position", default=0.3, min=0.05, max=0.9, update=_upd,
                            description="Tread bracket position along each tread (0 = nosing, 1 = back)")
    stub_t: _L("Bracket Thickness", 0.03, 0.01, 0.1)
    rod_inset: _L("Rod Edge Inset", 0.03, 0.0, 0.3, "Distance of the suspension rods from the tread edge")
    rod_pos: FloatProperty(name="Rod Position", default=0.5, min=0.1, max=0.9, update=_upd,
                           description="Rod position along each tread (0 = nosing, 1 = back)")
    rod_layout: EnumProperty(name="Rod Layout", default="SIDES", update=_upd, items=[
        ("SIDES", "At Support Sides", "One rod per support side at the tread edge"),
        ("CENTER", "Centre Rod", "A single rod through the middle of each tread")])
    show_attach: BoolProperty(name="Attachment Points", default=False, update=_upd,
                              description="Create named empties at every support fixing (wall anchors, rod tops, beam ends, stringer feet and heads, pole)")
    tex_mode: EnumProperty(name="Texture Mode", default="NONE", items=[
        ("NONE", "Flat colours", ""), ("PROCEDURAL", "Procedural", ""), ("IMAGES", "Images", ""), ("UV_GRID", "UV grid", "")])
    gen_uvs: BoolProperty(name="Generate UVs", default=True, update=_upd,
                          description="Write a UV map on every generated part (u across the tread, v around the profile)")
    uv_timber: _L("Timber Tile", 0.6, 0.05, 5.0, "Size in metres that one texture tile covers on timber treads, risers and handrails")
    uv_finish: _L("Finish Tile", 0.6, 0.05, 5.0, "Tile size on tread, riser and landing finishes (stone, tile, veneer)")
    uv_concrete: _L("Concrete Tile", 1.0, 0.05, 5.0, "Tile size on concrete, landing slabs and underlay")
    uv_other: _L("Other Tile", 1.0, 0.05, 5.0, "Tile size on everything else")
    tex_finish: EnumProperty(name="Finish Texture", default="STONE", items=[
        ("STONE", "Stone", "Mottled stone"), ("TIMBER", "Timber", "Wood grain on the finish layer")])
    tex_img_timber: StringProperty(name="Timber Image", subtype="FILE_PATH")
    tex_img_finish: StringProperty(name="Finish Image", subtype="FILE_PATH")
    tex_img_concrete: StringProperty(name="Concrete Image", subtype="FILE_PATH")
    slab_obj: PointerProperty(type=bpy.types.Object, name="Floor Slab",
                              description="Slab object that gets the stairwell opening cut into it")
    opening_margin: _L("Opening Clearance", 0.0, 0.0, 0.5, "Extra gap around the void on every side")
    fit_cut: BoolProperty(name="Cut Opening When Fitting", default=False,
                          description="Cut / update the slab opening whenever Fit Stair to Void runs")
    boq_waste: FloatProperty(name="Wastage %", default=5.0, min=0.0, max=30.0)
    well_obj: PointerProperty(type=bpy.types.Object, name="Void Object",
                              description="Plane or box that marks the stairwell opening (its bounding box in its own axes)")
    well_w: _L("Void Width", 2.4, 0.6, 12.0, "Void size along X (used when no void object is set)")
    well_l: _L("Void Length", 4.0, 0.6, 20.0, "Void size along Y (used when no void object is set)")
    well_start: EnumProperty(name="Stair Starts At", default="BOTTOM", items=[
        ("BOTTOM", "-Y Edge", "Bottom step at the void's -Y edge, climbing towards +Y"),
        ("TOP", "+Y Edge", "Bottom step at the void's +Y edge, climbing towards -Y"),
        ("LEFT", "-X Edge", "Bottom step at the void's -X edge, climbing towards +X"),
        ("RIGHT", "+X Edge", "Bottom step at the void's +X edge, climbing towards -X")])
    fit_min_width: _L("Min Stair Width", 0.9, 0.6, 2.0, "The fit narrows the stair down to this width if needed")
    fit_choice: EnumProperty(name="Fit Layout", default="BEST", items=[
        ("BEST", "Best Score", "Select the closest fit according to the built-in heuristic"),
        ("STRAIGHT", "Straight", "Choose the best straight option"),
        ("L_SHAPED", "L-shaped", "Choose the best L-shaped option"),
        ("U_SHAPED", "U-shaped", "Choose the best U-shaped option")])
    attach_posts: BoolProperty(name="Include Rail Posts", default=False, update=_upd,
                               description="Also create an empty at the base of every railing post")

    # ---- v3: tread detailing
    strip_mode: EnumProperty(name="Anti-slip Strips", default="NONE", update=_upd, items=[
        ("NONE", "None", ""), ("FLUSH", "Flush", "Strip set level with the tread surface"),
        ("RECESSED", "Recessed", "Strip sits below the tread surface")])
    strip_w: _L("Strip Width", 0.02, 0.005, 0.08)
    strip_n: IntProperty(name="Strips per Tread", default=2, min=1, max=6, update=_upd)
    strip_gap: _L("Strip Spacing", 0.015, 0.0, 0.1)
    strip_off: _L("Strip Offset", 0.02, 0.0, 0.2, "Distance from the nosing (or metal nosing)")
    strip_inset: _L("Strip Side Inset", 0.05, 0.0, 0.5)
    strip_depth: _L("Groove Depth", 0.006, 0.002, 0.03)
    strip_recess: _L("Recess", 0.002, 0.0005, 0.01, "How far a recessed strip sits below the surface")
    metal_nosing: EnumProperty(name="Metal Nosing", default="NONE", update=_upd, items=[
        ("NONE", "None", ""), ("INSERT", "Flush Insert", "Metal strip set into the tread front"),
        ("ANGLE", "Angle Cap", "Metal angle wrapping the tread edge")])
    mn_w: _L("Nosing Width", 0.035, 0.01, 0.1, "Top flange / insert width")
    mn_h: _L("Nosing Face Height", 0.03, 0.01, 0.1)
    mn_t: _L("Nosing Thickness", 0.003, 0.001, 0.01)
    led_channel: BoolProperty(name="LED Channel", default=False, update=_upd,
                              description="Groove with an LED strip along the tread underside near the front")
    led_w: _L("Channel Width", 0.02, 0.008, 0.06)
    led_d: _L("Channel Depth", 0.015, 0.006, 0.05)


def copy_props(src, dst):
    for k in src.bl_rna.properties.keys():
        if k in ("rna_type", "name", "generated"):
            continue
        try:
            setattr(dst, k, getattr(src, k))
        except Exception:
            pass


# =============================================================================
#  Operators
# =============================================================================


class PSTAIRS_OT_mark_edges(bpy.types.Operator):
    bl_idname = "pstairs.mark_rail_edges"
    bl_label = "Set Railing Edge"
    bl_options = {"REGISTER", "UNDO"}
    action: EnumProperty(items=[("ASSIGN", "Assign", ""), ("EXCLUDE", "Exclude", ""), ("RESET", "Reset", ""), ("SELECT", "Select Assigned", "")])

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == "MESH" and context.object.mode == "EDIT"

    def execute(self, context):
        obj = context.object
        bm = bmesh.from_edit_mesh(obj.data)
        layer = bm.edges.layers.int.get("ps_rail_edge") or bm.edges.layers.int.new("ps_rail_edge")
        if self.action == "SELECT":
            for edge in bm.edges:
                edge.select_set(edge[layer] == 1)
            bm.select_flush_mode()
        else:
            selected = [e for e in bm.edges if e.select]
            if not selected:
                self.report({"WARNING"}, "Select edges in Edit Mode first")
                return {"CANCELLED"}
            previous = bm.edges.layers.int.get("ps_rail_previous")
            if previous is None:
                previous = bm.edges.layers.int.new("ps_rail_previous")
            for edge in selected:
                if self.action == "EXCLUDE":
                    if edge[layer] != 2:
                        edge[previous] = edge[layer]
                    edge[layer] = 2
                elif self.action == "RESET":
                    edge[layer] = edge[previous] if edge[layer] == 2 else 0
                    edge[previous] = 0
                else:
                    edge[layer] = 1
                    edge[previous] = 0
        bmesh.update_edit_mesh(obj.data)
        if self.action != "SELECT" and obj.pstairs.generated and obj.pstairs.engine != "PARAM":
            rebuild(obj, force=True)
            if obj.name in _ERR:
                self.report({"WARNING"}, "Edge saved, but stair update failed: " + _ERR[obj.name])
                return {"FINISHED"}
        self.report({"INFO"}, "Railing edge settings updated")
        return {"FINISHED"}

def _edge_chains(chosen):
    """Order each non-branching connected edge component into a path or cycle."""
    adjacency = {}
    for edge, _info in chosen:
        a, b = edge
        if a == b:
            raise ValueError("Zero-length topological edge")
        adjacency.setdefault(a, []).append(b)
        adjacency.setdefault(b, []).append(a)
    if any(len(neighbors) > 2 for neighbors in adjacency.values()):
        raise ValueError("Railing selection branches. Select unbranched paths or separate source meshes.")
    unused = {tuple(sorted(edge)) for edge, _info in chosen}
    chains = []
    while unused:
        endpoints = sorted(v for v, ns in adjacency.items()
                           if sum(tuple(sorted((v, n))) in unused for n in ns) == 1)
        start = endpoints[0] if endpoints else min(min(edge) for edge in unused)
        chain = [start]
        while True:
            here = chain[-1]
            neighbors = sorted(n for n in adjacency[here] if tuple(sorted((here, n))) in unused)
            if not neighbors:
                break
            nxt = neighbors[0]
            unused.remove(tuple(sorted((here, nxt))))
            chain.append(nxt)
            if nxt == start:
                break
        chains.append(chain)
    return chains


def _standalone_runs(verts, faces, chosen, P, style):
    edge_info = {tuple(sorted(k)): info for k, info in chosen}
    hh = hand_info(style, P)[1]
    offset = rail_offset(style, P)
    runs = []
    for chain in _edge_chains(chosen):
        closed = len(chain) > 3 and chain[0] == chain[-1]
        normals = []
        for a, b in zip(chain[:-1], chain[1:]):
            va, vb = verts[a], verts[b]
            d = vb - va
            n = Vector((-d.y, d.x, 0.0))
            if n.length < 1e-7:
                raise ValueError("Railing edges need a horizontal component")
            n.normalize()
            info = edge_info[tuple(sorted((a, b)))]
            if info["faces"]:
                face = faces[info["faces"][0]]
                center = sum((verts[i] for i in face["vi"]), Vector()) / len(face["vi"])
                if (center - (va + vb) * 0.5).dot(n) < 0:
                    n = -n
            normals.append(n)
        # For loose edges, keep the offset consistently on the same side
        # following the ordered path. Face edges use their face interior.
        m = len(normals)
        nodes, points = [], []
        count = m if closed else m + 1
        for i in range(count):
            before = normals[(i-1) % m] if closed or i > 0 else None
            after = normals[i % m] if closed or i < m else None
            v = verts[chain[i]]
            q = v + _off_vec(before, after, offset)
            nodes.append(q)
            points.append(q + Z * (P.rail_height - hh / 2))
        if closed:
            nodes.append(nodes[0].copy())
            points.append(points[0].copy())
        run = Run(points, _chain_floor(nodes), False, normals, hh, P.rail_height - hh / 2, 0.0, closed)
        posts = []
        for i in range(m):
            length = run.cum[i+1] - run.cum[i]
            count = max(1, int(math.ceil(length / max(0.2, P.post_spacing))))
            posts.extend(run.cum[i] + length*j/count for j in range(count))
        posts.append(run.length)
        run.posts = sorted(set(round(d, 6) for d in posts))
        run.st = style
        runs.append(run)
    return runs


class PSTAIRS_OT_standalone_rails(bpy.types.Operator):
    bl_idname = "pstairs.standalone_rails"
    bl_label = "Build / Update Edge Railings"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        global _WALL_BVHS
        obj = context.object
        if not obj or obj.type != "MESH" or obj.mode not in {"OBJECT", "EDIT"}:
            self.report({"ERROR"}, "Select a source mesh in Edit or Object Mode")
            return {"CANCELLED"}
        try:
            base = obj.pstairs
            standalone_keys = ['rail_height', 'post_size', 'post_spacing', 'baluster_size', 'baluster_spacing', 'hand_size', 'rail_offset', 'glass_thk', 'wall_thk', 'cable_dia', 'cable_gap', 'wall_gap', 'bracket_spacing', 'bar_count']
            P = _PView(base, {key: getattr(base, "standalone_" + key) for key in standalone_keys})
            verts, faces, edges = read_mesh(obj)
            # Edit Mode uses the current selection directly; Object Mode updates
            # the independent standalone selection saved by the previous build.
            if obj.mode == "EDIT":
                chosen = [(k, info) for k, info in edges.items() if info.get("selected")]
            else:
                chosen = [(k, info) for k, info in edges.items() if info.get("standalone")]
                # Compatibility with standalone railings created by version 7.1.
                if not chosen:
                    chosen = [(k, info) for k, info in edges.items() if info.get("railmark") == 1]
            if not chosen:
                self.report({"ERROR"}, "In Edit Mode select the edges for your railing")
                return {"CANCELLED"}
            st = STYLE_BY_ID.get(P.standalone_style, STYLES[0])
            hh = hand_info(st, P)[1]
            off = rail_offset(st, P)
            mb = MB(PART_MATS["Railings"])
            runs = _standalone_runs(verts, faces, chosen, P, st)
            if not runs:
                self.report({"ERROR"}, "Select suitable connected edges")
                return {"CANCELLED"}
            # Build standalone geometry without altering stair statistics or attachment caches.
            for run in runs:
                build_rail_style(run, st, P, mb, None)
            uid = _ensure_uid(obj)
            old = next((o for o in bpy.data.objects if o.get("ps_rail_source") == uid), None)
            mesh = bpy.data.meshes.new(obj.name + "_EdgeRailingsMesh")
            for name in mb.mats:
                mesh.materials.append(get_mat(name))
            try:
                fill_mesh(mesh, mb)
            except Exception:
                bpy.data.meshes.remove(mesh)
                raise
            if old is None:
                old = bpy.data.objects.new(obj.name + "_EdgeRailings", mesh)
                context.scene.collection.objects.link(old)
                old["ps_rail_source"] = uid
            else:
                previous = old.data
                old.data = mesh
                if previous and previous.users == 0:
                    bpy.data.meshes.remove(previous)
            if obj.mode == "EDIT":
                bm = bmesh.from_edit_mesh(obj.data)
                solo = bm.edges.layers.int.get("ps_standalone_edge")
                if solo is None:
                    solo = bm.edges.layers.int.new("ps_standalone_edge")
                for edge in bm.edges:
                    edge[solo] = int(edge.select)
                bmesh.update_edit_mesh(obj.data)
            self.report({"INFO"}, "Built %d connected railing run(s)" % len(runs))
            return {"FINISHED"}
        except Exception as e:
            traceback.print_exc()
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        finally:
            _WALL_BVHS = []

class PSTAIRS_OT_remove_edge_rails(bpy.types.Operator):
    bl_idname = "pstairs.remove_edge_rails"
    bl_label = "Remove Edge Railings"
    bl_options = {"REGISTER", "UNDO"}
    def execute(self, context):
        obj = context.object
        uid = obj.get("ps_uid") if obj else None
        found = [o for o in bpy.data.objects if uid and o.get("ps_rail_source") == uid]
        for o in found:
            _drop(o)
        self.report({"INFO"}, "Removed %d edge railing object(s)" % len(found))
        return {"FINISHED"}

class PSTAIRS_OT_generate(bpy.types.Operator):
    bl_idname = "pstairs.generate"
    bl_label = "Generate Stairs"
    bl_description = "Build stairs from the selected plane(s): sloped faces become flights, flat faces become landings"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        objs = [o for o in context.selected_objects if o.type == "MESH" and not o.get("ps_src")]
        if not objs:
            self.report({"ERROR"}, "Select one or more plane/mesh objects")
            return {"CANCELLED"}
        act = context.active_object
        for o in objs:
            if act in objs and o is not act and not o.pstairs.generated:
                copy_props(act.pstairs, o.pstairs)
            o.pstairs.generated = True
            if o.pstairs.hide_source_render:
                o.hide_render = True
            rebuild(o)
        self.report({"INFO"}, "Stairs generated for %d object(s)" % len(objs))
        return {"FINISHED"}


class PSTAIRS_OT_update(bpy.types.Operator):
    bl_idname = "pstairs.update"
    bl_label = "Update Now"
    bl_description = "Rebuild the stairs of the selected object(s)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        for o in context.selected_objects:
            if o.type == "MESH" and o.pstairs.generated:
                rebuild(o)
        return {"FINISHED"}


class PSTAIRS_OT_clear(bpy.types.Operator):
    bl_idname = "pstairs.clear"
    bl_label = "Remove Stairs"
    bl_description = "Delete the generated stairs of the selected object(s)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        for o in context.selected_objects:
            if o.type == "MESH" and o.pstairs.generated:
                clear_generated(o)
                o.pstairs.generated = False
                o.hide_render = False
        return {"FINISHED"}


class PSTAIRS_OT_freeze(bpy.types.Operator):
    bl_idname = "pstairs.freeze"
    bl_label = "Freeze (Detach)"
    bl_description = "Keep the generated meshes but stop them following the source plane"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        for o in context.selected_objects:
            if o.type == "MESH" and o.pstairs.generated:
                o.pstairs.generated = False
        return {"FINISHED"}


class PSTAIRS_OT_sample(bpy.types.Operator):
    bl_idname = "pstairs.sample"
    bl_label = "Add Sample Stair Plane"
    bl_description = "Add a landing + slope + landing plane to try the addon on"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        v = [(-0.6, -1.2, 0), (0.6, -1.2, 0), (0.6, 0, 0), (-0.6, 0, 0), (0.6, 2.8, 1.8), (-0.6, 2.8, 1.8),
             (0.6, 4.0, 1.8), (-0.6, 4.0, 1.8)]
        f = [(0, 1, 2, 3), (3, 2, 4, 5), (5, 4, 6, 7)]
        me = bpy.data.meshes.new("Stair Plane")
        me.from_pydata(v, [], f)
        me.update()
        ob = bpy.data.objects.new("Stair Plane", me)
        ob.location = context.scene.cursor.location
        context.collection.objects.link(ob)
        for o in context.selected_objects:
            o.select_set(False)
        ob.select_set(True)
        context.view_layer.objects.active = ob
        return {"FINISHED"}


# =============================================================================
#  UI
# =============================================================================

# ---- presets, looks, save/load -----------------------------------------------

PRESETS = {
    "MODERN_LUX": ("Modern Luxury", "MODERN_BLACK", dict(
        structure="CLOSED", thk_mode="TOTAL", tread_thk=0.06, use_finish=True, finish_thk=0.025, underlay_thk=0.01,
        riser_finish_thk=0.012, nosing=0.025, nosing_style="UNDERCUT", nosing_size=0.02, nosing_inlay=True,
        stringer="CENTER", stringer_w=0.07, railing_style="GLASS_FRL", hand_shape="SLIM", newel_mode="CORNERS",
        newel_shape="SQUARE", newel_cap="FLAT", led_rail=True, led_steps=True, rail_end="RETURN", rail_height=1.0)),
    "GRAND_CLASSIC": ("Grand Classic", "LUXURY_BRASS", dict(
        structure="CLOSED", thk_mode="ADD", tread_thk=0.04, use_finish=True, finish_thk=0.03, underlay_thk=0.015,
        nosing=0.04, nosing_style="BULLNOSE", nosing_size=0.025, nosing_inlay=True, stringer="SIDE",
        railing_style="TURNED", hand_shape="OVAL", newel_mode="ALL", newel_shape="SQUARE", newel_cap="BALL",
        newel_base="COLLAR", post_plate=True, led_rail=False, led_steps=False, rail_end="RETURN")),
    "MARBLE_WALNUT": ("Marble & Walnut", "MARBLE_WALNUT", dict(
        structure="CLOSED", thk_mode="ADD", tread_thk=0.04, use_finish=True, finish_thk=0.02, underlay_thk=0.01,
        nosing=0.03, nosing_style="ROUNDED", nosing_inlay=False, stringer="SIDE", railing_style="BAL_RD",
        hand_shape="ROUND", newel_mode="ALL", newel_shape="ROUND", newel_cap="DOME", newel_base="PLATE",
        led_rail=False, led_steps=False, rail_end="RETURN")),
    "SCANDI": ("Scandinavian", "SCANDI_OAK", dict(
        structure="CLOSED", thk_mode="TOTAL", tread_thk=0.04, use_finish=False, nosing=0.025, nosing_style="EASED",
        nosing_inlay=False, stringer="SIDE", stringer_w=0.04, railing_style="PICKET", hand_shape="RECT",
        newel_mode="ENDS", newel_shape="SQUARE", newel_cap="FLAT", led_rail=False, led_steps=False, rail_end="NONE")),
    "INDUSTRIAL": ("Industrial Loft", "INDUSTRIAL", dict(
        structure="CLOSED", thk_mode="TOTAL", tread_thk=0.05, use_finish=False, use_risers=False, nosing=0.0,
        nosing_style="SQUARE", nosing_inlay=False, stringer="SIDE", stringer_w=0.06, railing_style="PIPE",
        hand_shape="ROUND", newel_mode="NONE", led_rail=False, led_steps=False, rail_end="NONE")),
    "FLOATING": ("Floating Minimal", "SMOKED_OAK_BLACK", dict(
        structure="CLOSED", thk_mode="TOTAL", tread_thk=0.07, use_finish=True, finish_thk=0.03, underlay_thk=0.0,
        use_risers=False, nosing=0.0, nosing_style="CHAMFER", nosing_size=0.012, nosing_inlay=False,
        stringer="CENTER", stringer_w=0.08, railing_style="GLASS_BTN", hand_shape="ROUND", newel_mode="ENDS",
        newel_shape="ROUND", newel_cap="DOME", led_rail=True, led_steps=True, rail_end="RETURN")),
    "GOLD_GLASS": ("Noir, Gold & Glass", "NOIR_GOLD", dict(
        structure="CLOSED", thk_mode="ADD", tread_thk=0.04, use_finish=True, finish_thk=0.025, underlay_thk=0.01,
        nosing=0.03, nosing_style="DROP_ROUND", nosing_size=0.012, lip_depth=0.035, nosing_inlay=True,
        stringer="SIDE", railing_style="GLASS_MID", hand_shape="ROUND", newel_mode="ALL", newel_shape="ROUND",
        newel_cap="FINIAL", newel_base="COLLAR", led_rail=True, led_steps=False, rail_end="BALL")),
}


def _targets(context):
    return [o for o in context.selected_objects if o.type == "MESH" and not o.get("ps_src")]


def props_to_dict(p):
    d = {}
    for k in p.bl_rna.properties.keys():
        if k in ("rna_type", "name", "generated"):
            continue
        if p.bl_rna.properties[k].type == "POINTER":
            continue
        d[k] = getattr(p, k)
    return d


def apply_dict(p, d):
    """Set many properties but rebuild only once."""
    live = p.live
    p.live = False
    for k, v in d.items():
        if k in ("live", "generated"):
            continue
        try:
            setattr(p, k, v)
        except Exception:
            pass
    p.live = live
    if p.generated and not live:
        rebuild(p.id_data)


class PSTAIRS_OT_preset(bpy.types.Operator):
    bl_idname = "pstairs.preset"
    bl_label = "Apply Style Preset"
    bl_description = "Set thickness, nosing, railings, newels, lighting and materials in one go"
    bl_options = {"REGISTER", "UNDO"}
    preset: EnumProperty(name="Preset", items=[(k, v[0], "") for k, v in PRESETS.items()])

    def execute(self, context):
        label, look, props = PRESETS[self.preset]
        for o in _targets(context):
            apply_dict(o.pstairs, dict(props, look=look))
        apply_look(look)
        return {"FINISHED"}


class PSTAIRS_OT_apply_look(bpy.types.Operator):
    bl_idname = "pstairs.apply_look"
    bl_label = "Apply Look"
    bl_description = "Recolour the shared PS_* materials (affects every stair in the file)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if context.object is None or context.object.type != "MESH":
            return {"CANCELLED"}
        apply_look(context.object.pstairs.look)
        return {"FINISHED"}


class PSTAIRS_OT_preset_save(bpy.types.Operator, ExportHelper):
    bl_idname = "pstairs.preset_save"
    bl_label = "Save Settings"
    bl_description = "Write the stair settings of the active object to a .json file"
    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    def execute(self, context):
        ob = context.object
        if ob is None or ob.type != "MESH":
            return {"CANCELLED"}
        with open(self.filepath, "w") as fh:
            json.dump(props_to_dict(ob.pstairs), fh, indent=1)
        self.report({"INFO"}, "Saved %s" % os.path.basename(self.filepath))
        return {"FINISHED"}


class PSTAIRS_OT_preset_load(bpy.types.Operator, ImportHelper):
    bl_idname = "pstairs.preset_load"
    bl_label = "Load Settings"
    bl_description = "Load stair settings from a .json file onto the selected object(s)"
    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    def execute(self, context):
        try:
            with open(self.filepath) as fh:
                d = json.load(fh)
        except Exception as e:
            self.report({"ERROR"}, "Could not read file: %s" % e)
            return {"CANCELLED"}
        for o in _targets(context):
            apply_dict(o.pstairs, d)
        return {"FINISHED"}


# =============================================================================
#  UI
# =============================================================================

class _SubBase:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Stairs"
    bl_parent_id = "PSTAIRS_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        ob = context.object
        return ob is not None and ob.type == "MESH" and not ob.get("ps_src")


class PSTAIRS_PT_main(bpy.types.Panel):
    bl_label = "Parametric Stairs"
    bl_idname = "PSTAIRS_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Stairs"

    def draw(self, context):
        lay = self.layout
        row = lay.row(align=True)
        row.operator("pstairs.sample", icon="MESH_PLANE")
        row.operator("pstairs.add_param", icon="ADD")
        lay.operator("pstairs.repair", icon="FILE_REFRESH")
        ob = context.object
        if ob is None or ob.type != "MESH":
            lay.label(text="Select a plane / mesh")
            return
        if ob.get("ps_src"):
            lay.label(text="Generated mesh of '%s'" % ob.get("ps_src"), icon="INFO")
            return
        p = ob.pstairs
        col = lay.column(align=True)
        if p.generated:
            row = col.row(align=True)
            row.operator("pstairs.update", icon="FILE_REFRESH")
            row.operator("pstairs.clear", icon="X")
            col.operator("pstairs.freeze", icon="UNLINKED")
        else:
            col.scale_y = 1.4
            col.operator("pstairs.generate", icon="MOD_BUILD")
        lay.prop(p, "live")
        lay.prop(p, "hide_source_render")
        lay.label(text="Sloped faces = flights, flat faces = landings", icon="INFO")
        lay.label(text="Mark edges as Seam to skip railings there")


class PSTAIRS_OT_add_param(bpy.types.Operator):
    bl_idname = "pstairs.add_param"
    bl_label = "Add Parametric Stair"
    bl_description = "Add a control plane that generates a stair from floor height, tread depth, width and landings"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        me = bpy.data.meshes.new("Stair Control")
        me.from_pydata([(-0.3, -0.3, 0), (0.3, -0.3, 0), (0.3, 0.3, 0), (-0.3, 0.3, 0)], [], [(0, 1, 2, 3)])
        me.update()
        ob = bpy.data.objects.new("Stair Control", me)
        ob.location = context.scene.cursor.location
        context.collection.objects.link(ob)
        for o in context.selected_objects:
            o.select_set(False)
        ob.select_set(True)
        context.view_layer.objects.active = ob
        p = ob.pstairs
        p.engine = "PARAM"
        p.generated = True
        if p.hide_source_render:
            ob.hide_render = True
        rebuild(ob)
        return {"FINISHED"}


class PSTAIRS_OT_bake(bpy.types.Operator):
    bl_idname = "pstairs.bake"
    bl_label = "Bake to Editable Plane"
    bl_description = "Write the parametric layout into this object's mesh and switch to From Planes, so you can edit the planes by hand"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        ob = context.object
        if ob is None or ob.type != "MESH" or ob.mode != "OBJECT":
            self.report({"ERROR"}, "Select a stair object in Object Mode")
            return {"CANCELLED"}
        p = ob.pstairs
        if p.engine != "PARAM" or p.layout in ("CURVED", "HELICAL", "SPIRAL"):
            self.report({"ERROR"}, "Only straight / L / U / multi-flight layouts can be baked to planes")
            return {"CANCELLED"}
        z0, H = _levels(ob, p)
        verts, faces, edges, meta = build_virtual(p, ob.matrix_world, z0, H)
        inv = ob.matrix_world.inverted()
        if ob.data.users > 1:
            ob.data = ob.data.copy()
        me = ob.data
        me.clear_geometry()
        me.from_pydata([tuple(inv @ v) for v in verts], [], [f["vi"] for f in faces])
        me.update()
        apply_dict(p, dict(engine="PLANE", riser_mode="HEIGHT", riser_height=meta["r"]))
        rebuild(ob)
        self.report({"INFO"}, "Baked %d risers of %.1f mm" % (meta["N"], meta["r"] * 1000))
        return {"FINISHED"}


class PSTAIRS_OT_repair(bpy.types.Operator):
    bl_idname = "pstairs.repair"
    bl_label = "Rebuild All / Repair"
    bl_description = "Rebuild every generated stair in the file and remove duplicated parts"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        n = 0
        for o in list(bpy.data.objects):
            if o.type == "MESH" and not o.get("ps_part") and o.pstairs.generated:
                rebuild(o)
                n += 1
        self.report({"INFO"}, "Rebuilt %d stair(s)" % n)
        return {"FINISHED"}


class PSTAIRS_PT_presets(_SubBase, bpy.types.Panel):
    bl_label = "Presets && Looks"
    bl_idname = "PSTAIRS_PT_presets"
    bl_options = set()

    def draw(self, context):
        p = context.object.pstairs
        lay = self.layout
        lay.operator_menu_enum("pstairs.preset", "preset", text="Style Preset", icon="PRESET")
        row = lay.row(align=True)
        row.prop(p, "look", text="")
        row.operator("pstairs.apply_look", text="Apply")
        row = lay.row(align=True)
        row.operator("pstairs.preset_save", icon="EXPORT")
        row.operator("pstairs.preset_load", icon="IMPORT")
        lay.separator()
        lay.label(text="My Preset Library")
        row = lay.row(align=True)
        row.operator("pstairs.lib_save", text="Save Current...", icon="ADD")
        row.operator("pstairs.lib_refresh", text="", icon="FILE_REFRESH")
        row.operator("pstairs.lib_open", text="", icon="FILE_FOLDER")
        items = lib_items()
        if not items:
            lay.label(text="No saved presets yet", icon="INFO")
        col = lay.column(align=True)
        for it in items:
            row = col.row(align=True)
            op = row.operator("pstairs.lib_load", text=it["name"],
                              icon="BRUSH_DATA" if it["scope"] == "STYLE" else "PRESET")
            op.name = it["name"]
            op = row.operator("pstairs.lib_export", text="", icon="EXPORT")
            op.name = it["name"]
            op = row.operator("pstairs.lib_delete", text="", icon="TRASH")
            op.name = it["name"]
        lay.operator("pstairs.lib_import", icon="IMPORT")


class PSTAIRS_PT_steps(_SubBase, bpy.types.Panel):
    bl_label = "Steps && Detection"
    bl_idname = "PSTAIRS_PT_steps"

    def draw(self, context):
        p = context.object.pstairs
        c = self.layout.column()
        c.prop(p, "riser_mode", text="")
        c.prop(p, "riser_height" if p.riser_mode == "HEIGHT" else "step_count")
        c.prop(p, "flat_tol")
        c.prop(p, "max_angle")


class PSTAIRS_PT_structure(_SubBase, bpy.types.Panel):
    bl_label = "Treads, Risers, Structure"
    bl_idname = "PSTAIRS_PT_structure"

    def draw(self, context):
        p = context.object.pstairs
        c = self.layout.column()
        c.prop(p, "structure", text="")
        if p.structure == "SOLID":
            c.prop(p, "solid_fill")
            if not p.solid_fill:
                c.prop(p, "waist")
        else:
            c.prop(p, "thk_mode", text="")
            c.prop(p, "tread_thk")
            c.prop(p, "side_overhang")
            c.prop(p, "use_risers")
            if p.use_risers:
                c.prop(p, "riser_thk")
            c.separator()
            c.prop(p, "stringer")
            if p.stringer != "NONE":
                c.prop(p, "stringer_w")
                c.prop(p, "stringer_depth")
                c.prop(p, "stringer_offset")
        c.separator()
        c.prop(p, "landing_thk")
        # build-up summary so the thickness is always explicit
        L = layer_info(p)
        box = self.layout.box()
        col = box.column(align=True)
        col.label(text="Step build-up (top to bottom)", icon="MOD_SOLIDIFY")
        if L["ft"] > 0:
            col.label(text="Finish   %.1f mm" % (L["ft"] * 1000))
        if L["ut"] > 0:
            col.label(text="Underlay %.1f mm" % (L["ut"] * 1000))
        if p.structure == "SOLID":
            col.label(text="Solid concrete mass")
            col.label(text="Total above mass: %.1f mm" % ((L["ut"] + L["ft"]) * 1000))
        else:
            col.label(text="Board    %.1f mm" % (L["tt"] * 1000))
            col.label(text="Total step: %.1f mm   Landing: %.1f mm" % (L["tot"] * 1000, L["ltot"] * 1000))
            if p.thk_mode == "TOTAL" and p.tread_thk < L["ft"] + L["ut"] + 0.005:
                col.label(text="Total too thin for the layers", icon="ERROR")


class PSTAIRS_PT_nosing(_SubBase, bpy.types.Panel):
    bl_label = "Nosing && Tread Details"
    bl_idname = "PSTAIRS_PT_nosing"

    def draw(self, context):
        p = context.object.pstairs
        c = self.layout.column()
        c.prop(p, "nosing")
        c.prop(p, "nosing_style", text="")
        if p.nosing_style not in ("SQUARE", "WATERFALL"):
            c.prop(p, "nosing_size")
        if p.nosing_style in ("DROP", "DROP_ROUND"):
            c.prop(p, "lip_depth")
        c.separator()
        c.prop(p, "nosing_inlay")
        if p.nosing_inlay:
            c.prop(p, "inlay_w")
            c.prop(p, "inlay_inset")
        c.separator()
        c.prop(p, "metal_nosing")
        if p.metal_nosing != "NONE":
            c.prop(p, "mn_w")
            if p.metal_nosing == "ANGLE":
                c.prop(p, "mn_h")
            c.prop(p, "mn_t")
        c.separator()
        c.prop(p, "strip_mode")
        if p.strip_mode != "NONE":
            c.prop(p, "strip_n")
            c.prop(p, "strip_w")
            c.prop(p, "strip_gap")
            c.prop(p, "strip_off")
            c.prop(p, "strip_inset")
            c.prop(p, "strip_depth")
            if p.strip_mode == "RECESSED":
                c.prop(p, "strip_recess")
        c.separator()
        c.prop(p, "led_channel")
        if p.led_channel:
            c.prop(p, "led_w")
            c.prop(p, "led_d")


class PSTAIRS_PT_engine(_SubBase, bpy.types.Panel):
    bl_label = "Stair Engine"
    bl_idname = "PSTAIRS_PT_engine"
    bl_options = set()

    def draw(self, context):
        ob = context.object
        p = ob.pstairs
        c = self.layout.column()
        c.prop(p, "engine", expand=True)
        if p.engine != "PARAM":
            c.label(text="Sloped faces = flights, flat = landings", icon="INFO")
            return
        c.prop(p, "layout", text="")
        curved = p.layout in ("CURVED", "HELICAL", "SPIRAL")
        col = c.column(align=True)
        col.prop(p, "floor_height")
        col.prop(p, "lower_ref")
        if p.lower_ref:
            col.prop(p, "lower_level_offset")
        col.prop(p, "upper_ref")
        if p.upper_ref:
            col.prop(p, "upper_level_offset")
        c.prop(p, "riser_mode", text="")
        c.prop(p, "riser_height" if p.riser_mode == "HEIGHT" else "step_count")
        if p.layout != "SPIRAL":
            c.prop(p, "st_width")
        if not curved:
            c.prop(p, "going")
            if p.layout in ("L_SHAPED", "U_SHAPED", "MULTI"):
                c.prop(p, "turn_dir")
                c.prop(p, "land_d")
                c.prop(p, "land_w")
            if p.layout in ("L_SHAPED", "U_SHAPED"):
                c.prop(p, "split")
            if p.layout == "MULTI":
                c.prop(p, "flight_count")
                c.prop(p, "multi_turn")
            if p.layout == "U_SHAPED" or (p.layout == "MULTI" and p.multi_turn == "SWITCHBACK"):
                c.prop(p, "well_gap")
        else:
            c.prop(p, "turn_dir")
            if p.layout == "SPIRAL":
                c.prop(p, "pole_r")
                c.prop(p, "spiral_r")
                c.prop(p, "step_ang")
            else:
                c.prop(p, "curve_radius")
                c.prop(p, "sweep")
        row = c.row(align=True)
        row.prop(p, "lower_land")
        row.prop(p, "upper_land")
        if p.lower_land or p.upper_land:
            c.prop(p, "end_land_d")
        if not curved:
            c.operator("pstairs.bake", icon="MESH_GRID")
        c.label(text="Position and Z rotation of this object place the stair")


class PSTAIRS_PT_kind(_SubBase, bpy.types.Panel):
    bl_label = "Stair Type && Supports"
    bl_idname = "PSTAIRS_PT_kind"

    def draw(self, context):
        p = context.object.pstairs
        c = self.layout.column()
        c.prop(p, "stair_kind", text="")
        k = p.stair_kind
        if k in ("ZIGZAG", "SAWTOOTH") and p.engine == "PARAM" and p.layout in ("CURVED", "HELICAL", "SPIRAL"):
            c.label(text="Straight flights only - curves use Standard", icon="ERROR")
        if k in ("FLOATING", "CANTILEVER", "SUSPENDED"):
            c.prop(p, "support_side")
        if k == "FLOATING":
            c.prop(p, "wall_anchor")
            c.prop(p, "embed")
            c.prop(p, "tread_thk")
        elif k == "CANTILEVER":
            col = c.column(align=True)
            col.prop(p, "stringer_w", text="Beam Width")
            col.prop(p, "stringer_depth", text="Beam Depth")
            col.prop(p, "beam_top")
            col = c.column(align=True)
            col.prop(p, "embed", text="Bracket Length")
            col.prop(p, "stub_t")
            col.prop(p, "stub_pos")
        elif k == "SUSPENDED":
            col = c.column(align=True)
            col.prop(p, "rod_layout", text="")
            col.prop(p, "rod_d")
            col.prop(p, "rod_inset")
            col.prop(p, "rod_pos")
            col.prop(p, "susp_top")
        elif k == "STEEL":
            c.prop(p, "steel_sec")
            c.prop(p, "stringer")
            col = c.column(align=True)
            col.prop(p, "stringer_w")
            col.prop(p, "stringer_depth")
            col.prop(p, "stringer_offset")
            if p.steel_sec != "BOX":
                col.prop(p, "steel_t")
            col = c.column(align=True)
            col.prop(p, "stub_t", text="Bracket Thickness")
            col.prop(p, "stub_pos", text="Bracket Position")
        elif k == "SAWTOOTH":
            c.prop(p, "stringer")
            col = c.column(align=True)
            col.prop(p, "stringer_w")
            col.prop(p, "stringer_depth")
            col.prop(p, "stringer_offset")
        elif k == "ZIGZAG":
            c.prop(p, "fold_t")
        elif k == "MONOLITHIC":
            c.prop(p, "solid_fill")
            if not p.solid_fill:
                c.prop(p, "waist")
        c.separator()
        c.prop(p, "show_attach")
        if p.show_attach:
            c.prop(p, "attach_posts")


class PSTAIRS_PT_finish(_SubBase, bpy.types.Panel):
    bl_label = "Finishes"
    bl_idname = "PSTAIRS_PT_finish"

    def draw_header(self, context):
        self.layout.prop(context.object.pstairs, "use_finish", text="")

    def draw(self, context):
        p = context.object.pstairs
        c = self.layout.column()
        c.active = p.use_finish
        c.prop(p, "finish_thk")
        c.prop(p, "riser_finish_thk")
        c.prop(p, "underlay_thk")


class PSTAIRS_PT_rails(_SubBase, bpy.types.Panel):
    bl_label = "Railings"
    bl_idname = "PSTAIRS_PT_rails"
    bl_options = set()

    def draw_header(self, context):
        self.layout.prop(context.object.pstairs, "use_rails", text="")

    def draw(self, context):
        p = context.object.pstairs
        lay = self.layout
        lay.active = p.use_rails
        lay.template_icon_view(p, "railing_style", show_labels=True, scale=6.0, scale_popup=5.0)
        lay.prop(p, "rail_sides")
        box = lay.box()
        box.label(text="Reference Edge Railings")
        box.label(text="Edit Mode: select a stair-plane edge")
        row = box.row(align=True)
        row.operator("pstairs.mark_rail_edges", text="Remove Railing").action = "EXCLUDE"
        row.operator("pstairs.mark_rail_edges", text="Restore Railing").action = "RESET"
        box.operator("pstairs.mark_rail_edges", text="Force Railing on Selected").action = "ASSIGN"
        box.operator("pstairs.mark_rail_edges", text="Select Assigned").action = "SELECT"
        box.prop(p, "rail_edge_mode")
        box.prop(p, "detect_walls")
        if p.detect_walls:
            box.prop(p, "wall_collection")
            box.prop(p, "wall_detect_distance")
            box.prop(p, "wall_probe_height")
            box.label(text="After moving walls, use Update Now", icon="INFO")
        if p.engine == "PARAM":
            box.label(text="Edge rules apply to plane engine", icon="INFO")
        col2 = lay.column(align=True)
        col2.prop(p, "rail_style_left", text="Left Side")
        col2.prop(p, "rail_style_right", text="Right Side")
        lay.prop(p, "rail_landing")
        if p.rail_landing:
            lay.prop(p, "landing_style", text="Landings")
        col = lay.column(align=True)
        col.prop(p, "rail_height")
        col.prop(p, "rail_offset")
        col.prop(p, "post_size")
        col.prop(p, "post_spacing")
        col.prop(p, "hand_size")
        kind = _style(p).get("kind")
        if kind in ("bal", "flat", "diag", "turned", "twist", "lattice"):
            col.prop(p, "baluster_size")
            col.prop(p, "baluster_spacing")
        if kind == "horiz":
            col.prop(p, "bar_count")
        if kind in ("glass", "glass_ch"):
            col.prop(p, "glass_thk")
        if kind == "wall":
            col.prop(p, "wall_thk")
        kinds = {kind}
        for k_ in (p.rail_style_left, p.rail_style_right):
            if k_ in STYLE_BY_ID:
                kinds.add(STYLE_BY_ID[k_]["kind"])
        if "cable" in kinds:
            col.prop(p, "cable_dia")
            col.prop(p, "cable_gap")
        if "bracket" in kinds:
            col.prop(p, "wall_gap")
            col.prop(p, "bracket_spacing")


_HEADROOM = {}
_CLASH = {}
_FIT_OPTIONS = {}

class PSTAIRS_OT_compare_fit(bpy.types.Operator):
    bl_idname = "pstairs.compare_fit"
    bl_label = "Compare Fit Options"
    bl_description = "Show the best straight, L and U candidates without changing the stair"
    def execute(self, context):
        ob = context.object
        P = ob.pstairs
        if P.engine != "PARAM":
            self.report({"ERROR"}, "Select a parametric stair")
            return {"CANCELLED"}
        z0, H = _levels(ob, P)
        if H < 0.05:
            self.report({"ERROR"}, "Upper finished level must exceed lower level")
            return {"CANCELLED"}
        wo = P.well_obj
        if wo:
            cs = [Vector(cc) for cc in wo.bound_box]
            A = (max(c.x for c in cs) - min(c.x for c in cs)) * Vector(wo.matrix_world.col[0][:3]).length
            B = (max(c.y for c in cs) - min(c.y for c in cs)) * Vector(wo.matrix_world.col[1][:3]).length
        else:
            A, B = P.well_w, P.well_l
        choices = []
        fit_stair(P, H, A, B, P.well_start, choices)
        _FIT_OPTIONS[ob.name] = ["%s | %dR x %.0f | G %.0f | W %.0f mm | %.2f x %.2f m" %
            (x["layout"].replace("_SHAPED", ""), x["N"], x["r"]*1000, x["g"]*1000,
             x["W"]*1000, x["dx"], x["dy"]) for x in choices]
        if not choices:
            _FIT_OPTIONS[ob.name] = ["No candidates fit this opening"]
        self.report({"INFO"}, "Compared %d options; fitting assumptions need review" % len(choices))
        return {"FINISHED"}

class PSTAIRS_OT_headroom(bpy.types.Operator):
    bl_idname = "pstairs.measure_headroom"
    bl_label = "Measure Sampled Headroom"
    bl_description = "Cast upward rays from generated top faces to objects in the chosen overhead collection"
    def execute(self, context):
        ob = context.object
        P = ob.pstairs
        if not P.generated or P.headroom_collection is None:
            self.report({"ERROR"}, "Generate stairs and select an overhead objects collection")
            return {"CANCELLED"}
        found, _ = _find_parts(ob, ob.get("ps_uid") or "")
        # Prefer finish top faces, to measure from the walking surface.
        surfaces = [found[n] for n in ("Finish",) if n in found]
        if not surfaces:
            surfaces = [found[n] for n in ("Treads", "SolidSteps", "Landings") if n in found]
        samples = []
        for part in surfaces:
            mesh = part.data
            mesh.calc_loop_triangles()
            for triangle in mesh.loop_triangles:
                a, b, c = [part.matrix_world @ mesh.vertices[i].co for i in triangle.vertices]
                cross = (b-a).cross(c-a)
                if cross.length < 1e-8 or cross.normalized().z <= 0.95:
                    continue
                # Interior barycentric points reduce the chance of missing a narrow beam.
                samples.extend([(a+b+c)/3.0, a*0.6+b*0.2+c*0.2,
                                a*0.2+b*0.6+c*0.2, a*0.2+b*0.2+c*0.6])
        if not samples:
            self.report({"ERROR"}, "No upward stair surfaces found to sample")
            return {"CANCELLED"}
        if len(samples) > 600:
            stride = int(math.ceil(len(samples) / 600.0))
            samples = samples[::stride]
        dg = context.evaluated_depsgraph_get()
        trees = []
        for item in P.headroom_collection.all_objects:
            if item.type != "MESH" or item == ob or item.get("ps_src") == ob.name:
                continue
            ev = item.evaluated_get(dg)
            mesh = None
            try:
                mesh = ev.to_mesh()
                if mesh and mesh.polygons:
                    trees.append((item.name, BVHTree.FromPolygons([ev.matrix_world @ v.co for v in mesh.vertices],
                        [tuple(f.vertices) for f in mesh.polygons], all_triangles=False)))
            finally:
                if mesh is not None:
                    ev.to_mesh_clear()
        if not trees:
            self.report({"ERROR"}, "No overhead mesh objects found in the collection")
            return {"CANCELLED"}
        best, where, name = None, None, None
        for point in samples:
            for candidate, tree in trees:
                hit = tree.ray_cast(point + Z * 0.001, Z, P.headroom_range)
                if hit[0] is not None:
                    distance = (hit[0] - point).length
                    if best is None or distance < best:
                        best, where, name = distance, tuple(point), candidate
        _HEADROOM[ob.name] = dict(distance=best, point=where, obstacle=name, count=len(samples),
                                  range=P.headroom_range, sig=_SIG.get(ob.name))
        self.report({"INFO"}, "Sampled %d walking-surface points" % len(samples))
        return {"FINISHED"}

def _coordination_tree(item, depsgraph):
    ev = item.evaluated_get(depsgraph)
    mesh = None
    try:
        mesh = ev.to_mesh()
        if not mesh or not mesh.polygons:
            return None
        if len(mesh.polygons) > 100000:
            raise ValueError("Object %s exceeds 100,000 polygons; use a simplified clash proxy" % item.name)
        return BVHTree.FromPolygons([ev.matrix_world @ v.co for v in mesh.vertices],
                                   [tuple(f.vertices) for f in mesh.polygons], all_triangles=False)
    finally:
        if mesh is not None:
            ev.to_mesh_clear()

class PSTAIRS_OT_surface_clashes(bpy.types.Operator):
    bl_idname = "pstairs.surface_clashes"
    bl_label = "Check Surface Intersections"
    bl_description = "Find intersecting stair and obstacle mesh surfaces in the selected collection"
    def execute(self, context):
        obj = context.object
        P = obj.pstairs
        if not P.generated or not P.clash_collection:
            self.report({"ERROR"}, "Generate stairs and select a clash collection")
            return {"CANCELLED"}
        found, _ = _find_parts(obj, obj.get("ps_uid") or "")
        candidates = [o for o in P.clash_collection.all_objects if o.type == "MESH" and
                      o != obj and o.get("ps_src") != obj.name and not o.get("ps_rail_source")]
        if not candidates:
            self.report({"ERROR"}, "No obstacle meshes in the selected collection")
            return {"CANCELLED"}
        if len(candidates) > 50:
            self.report({"ERROR"}, "More than 50 obstacle meshes; use a smaller collection")
            return {"CANCELLED"}
        try:
            dg = context.evaluated_depsgraph_get()
            trees = [(o.name, _coordination_tree(o, dg)) for o in candidates]
            clashes = []
            for part_name, part in found.items():
                if part_name in ("Lights",):
                    continue
                ptree = _coordination_tree(part, dg)
                if ptree is None:
                    continue
                for name, other in trees:
                    if other is not None and ptree.overlap(other):
                        clashes.append((part_name, name))
            _CLASH[obj.name] = {"items": clashes, "checked": len(candidates), "sig": _SIG.get(obj.name)}
            self.report({"INFO"}, "Found %d intersecting part/object pairs" % len(clashes))
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, "Intersection check failed: " + str(exc))
            return {"CANCELLED"}

class PSTAIRS_OT_export_sketch(bpy.types.Operator, ExportHelper):
    bl_idname = "pstairs.export_coordination_svg"
    bl_label = "Export Coordination Sketch (SVG)"
    bl_description = "Export a schematic top-view edge projection; requires drafting review"
    filename_ext = ".svg"
    filter_glob: StringProperty(default="*.svg", options={"HIDDEN"})
    def invoke(self, context, event):
        self.filepath = bpy.path.clean_name(context.object.name) + "_stair_plan.svg"
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}
    def execute(self, context):
        from xml.sax.saxutils import escape
        ob = context.object
        if not ob or not ob.pstairs.generated:
            self.report({"ERROR"}, "Select a generated stair source")
            return {"CANCELLED"}
        found, _ = _find_parts(ob, ob.get("ps_uid") or "")
        segments = []
        for n in ("Treads", "SolidSteps", "Landings", "Finish"):
            part = found.get(n)
            if part is None:
                continue
            mesh = part.data
            for edge in mesh.edges:
                a, b = [part.matrix_world @ mesh.vertices[i].co for i in edge.vertices]
                if (a-b).length > 1e-6 and math.hypot(a.x-b.x, a.y-b.y) > 1e-6:
                    segments.append((a.x, a.y, b.x, b.y))
        if not segments:
            self.report({"ERROR"}, "No generated stair edges found; update the stair first")
            return {"CANCELLED"}
        xs = [v for a,b,c,d in segments for v in (a,c)]
        ys = [v for a,b,c,d in segments for v in (b,d)]
        xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
        scale, pad = 1000.0, 100.0
        width, height = (xmax-xmin)*scale+2*pad, (ymax-ymin)*scale+2*pad+100
        with open(self.filepath, "w", encoding="utf-8") as f:
            f.write('<svg xmlns="http://www.w3.org/2000/svg" width="%.2fmm" height="%.2fmm" viewBox="0 0 %.2f %.2f">\n' % (width,height,width,height))
            f.write('<title>%s - stair coordination sketch</title>\n' % escape(ob.name))
            f.write('<g fill="none" stroke="black" stroke-width="2">\n')
            for a,b,c,d in segments:
                f.write('<line x1="%.3f" y1="%.3f" x2="%.3f" y2="%.3f"/>\n' %
                    ((a-xmin)*scale+pad, (ymax-b)*scale+pad, (c-xmin)*scale+pad, (ymax-d)*scale+pad))
            f.write('</g><text x="%.1f" y="%.1f" font-size="25">%s - schematic edge projection; verify before drafting</text></svg>\n' %
                    (pad,height-35,escape(ob.name)))
        self.report({"INFO"}, "Exported schematic SVG; hidden edges are not removed")
        return {"FINISHED"}

def _triangle_section(points, plane_x, eps=1e-8):
    """Return two (y,z) coordinates where a triangle crosses local X=plane_x."""
    ds = [p[0] - plane_x for p in points]
    if all(abs(d) <= eps for d in ds):
        return None  # coplanar face has no unique cut line
    hits = []
    for i in range(3):
        a, b = points[i], points[(i+1) % 3]
        da, db = ds[i], ds[(i+1) % 3]
        if abs(da) <= eps:
            hits.append((a[1], a[2]))
        if (da < -eps and db > eps) or (da > eps and db < -eps):
            t = da / (da-db)
            hits.append((a[1] + (b[1]-a[1])*t, a[2] + (b[2]-a[2])*t))
    unique = []
    for point in hits:
        if not any(abs(point[0]-q[0]) < eps and abs(point[1]-q[1]) < eps for q in unique):
            unique.append(point)
    return (unique[0], unique[1]) if len(unique) == 2 else None

class PSTAIRS_OT_export_section(bpy.types.Operator, ExportHelper):
    bl_idname = "pstairs.export_section_svg"
    bl_label = "Export Cut Section (SVG)"
    bl_description = "Intersect generated geometry with a vertical plane at the source's local X offset"
    filename_ext = ".svg"
    filter_glob: StringProperty(default="*.svg", options={"HIDDEN"})
    def invoke(self, context, event):
        self.filepath = bpy.path.clean_name(context.object.name) + "_stair_section.svg"
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}
    def execute(self, context):
        from xml.sax.saxutils import escape
        ob = context.object
        if not ob or not ob.pstairs.generated:
            self.report({"ERROR"}, "Select a generated stair source")
            return {"CANCELLED"}
        basis = ob.matrix_world.to_3x3()
        if any(abs(basis.col[i].length - 1.0) > 1e-4 for i in range(3)) or abs(basis.col[2].normalized().dot(Z) - 1.0) > 1e-4:
            self.report({"ERROR"}, "Section export needs an upright source with unit scale")
            return {"CANCELLED"}
        found, _ = _find_parts(ob, ob.get("ps_uid") or "")
        inverse = ob.matrix_world.inverted_safe()
        segments = []
        for name in ("Treads", "Risers", "SolidSteps", "Landings", "Underlay", "Finish", "Stringers"):
            part = found.get(name)
            if not part:
                continue
            mesh = part.data
            mesh.calc_loop_triangles()
            transform = inverse @ part.matrix_world
            for tri in mesh.loop_triangles:
                points = [transform @ mesh.vertices[i].co for i in tri.vertices]
                cut = _triangle_section(points, ob.pstairs.section_offset)
                if cut:
                    segments.append(cut)
        if not segments:
            self.report({"ERROR"}, "Section plane does not intersect generated meshes; adjust Section X Offset")
            return {"CANCELLED"}
        ys = [p[0] for seg in segments for p in seg]
        zs = [p[1] for seg in segments for p in seg]
        ymin, ymax, zmin, zmax = min(ys), max(ys), min(zs), max(zs)
        scale, pad = 1000.0, 100.0
        width = (ymax-ymin)*scale+pad*2
        height = (zmax-zmin)*scale+pad*2+100
        with open(self.filepath, "w", encoding="utf-8") as f:
            f.write('<svg xmlns="http://www.w3.org/2000/svg" width="%.3fmm" height="%.3fmm" viewBox="0 0 %.3f %.3f">\n' % (width,height,width,height))
            f.write('<title>%s - vertical cut section</title>\n' % escape(ob.name))
            f.write('<g fill="none" stroke="black" stroke-width="2">\n')
            for a,b in segments:
                f.write('<line x1="%.4f" y1="%.4f" x2="%.4f" y2="%.4f"/>\n' %
                    ((a[0]-ymin)*scale+pad, (zmax-a[1])*scale+pad, (b[0]-ymin)*scale+pad, (zmax-b[1])*scale+pad))
            f.write('</g><text x="%.2f" y="%.2f" font-size="24">%s - cut at local X %.3f m; review dimensions and geometry</text></svg>\n' %
                    (pad, height-35, escape(ob.name), ob.pstairs.section_offset))
        self.report({"INFO"}, "Exported section cut; verify before issuing")
        return {"FINISHED"}

class PSTAIRS_OT_viewport_detail(bpy.types.Operator):
    bl_idname = "pstairs.viewport_detail"
    bl_label = "Stair Viewport Detail"
    bl_description = "Temporarily simplify generated objects in the viewport, without changing render geometry"
    bl_options = {"REGISTER", "UNDO"}
    draft: BoolProperty(default=True)
    def execute(self, context):
        obj = context.object
        uid = obj.get("ps_uid") if obj else None
        if not uid:
            self.report({"ERROR"}, "Select a source with generated parts")
            return {"CANCELLED"}
        parts, duplicates = _find_parts(obj, uid)
        objects = list(parts.values()) + duplicates + [o for o in bpy.data.objects if o.get("ps_rail_source") == uid]
        for item in objects:
            if self.draft:
                if "ps_prior_display" not in item:
                    item["ps_prior_display"] = item.display_type
                item.display_type = "BOUNDS"
            elif "ps_prior_display" in item:
                item.display_type = item["ps_prior_display"]
                del item["ps_prior_display"]
        self.report({"INFO"}, "Updated viewport display on %d objects" % len(objects))
        return {"FINISHED"}

class PSTAIRS_PT_coordination(_SubBase, bpy.types.Panel):
    bl_label = "Architectural Coordination"
    bl_idname = "PSTAIRS_PT_coordination"
    def draw(self, context):
        ob = context.object
        p = ob.pstairs
        c = self.layout
        c.label(text="Sampled headroom (not code compliance)")
        c.prop(p, "headroom_collection")
        c.prop(p, "target_headroom")
        c.prop(p, "headroom_range")
        c.operator("pstairs.measure_headroom", icon="VIEWZOOM")
        data = _HEADROOM.get(ob.name)
        if data:
            if data["distance"] is None:
                c.label(text="No hit within %.2f m (%d samples)" % (data["range"], data["count"]))
            else:
                c.label(text="Minimum sampled: %.3f m at %s" % (data["distance"], data["obstacle"]),
                        icon="ERROR" if data["distance"] < p.target_headroom else "INFO")
                c.label(text="XY %.2f, %.2f m; %d samples" % (data["point"][0], data["point"][1], data["count"]))
            c.label(text="Rerun after moving overhead objects", icon="INFO")
        c.separator()
        c.label(text="Surface intersection review")
        c.prop(p, "clash_collection")
        c.operator("pstairs.surface_clashes", icon="VIEWZOOM")
        clashes = _CLASH.get(ob.name)
        if clashes:
            c.label(text="%d intersecting pairs; %d obstacles" % (len(clashes["items"]), clashes["checked"]))
            for part, obstacle in clashes["items"][:8]:
                c.label(text="%s / %s" % (part[:25], obstacle[:25]), icon="ERROR")
            c.label(text="Rerun after changing obstacle geometry")
        c.label(text="Surface intersections only; review containment")
        c.separator()
        row = c.row(align=True)
        row.operator("pstairs.viewport_detail", text="Draft View").draft = True
        row.operator("pstairs.viewport_detail", text="Restore View").draft = False
        c.label(text="Draft uses bounds; renders stay unchanged")
        c.operator("pstairs.export_coordination_svg", icon="EXPORT")
        c.prop(p, "section_offset")
        c.operator("pstairs.export_section_svg", icon="EXPORT")
        c.label(text="SVGs need drafting and dimension review")
        c.label(text="Verify dimensions, levels and IFC mapping")


class PSTAIRS_PT_standalone(_SubBase, bpy.types.Panel):
    bl_label = "Standalone Railings"
    bl_idname = "PSTAIRS_PT_standalone"
    bl_options = set()

    def draw(self, context):
        p = context.object.pstairs
        lay = self.layout
        lay.label(text="Select mesh edges in Edit Mode", icon="INFO")
        lay.template_icon_view(p, "standalone_style", show_labels=True, scale=6.0, scale_popup=5.0)
        lay.prop(p, "standalone_rail_height")
        lay.prop(p, "standalone_rail_offset")
        lay.prop(p, "standalone_post_spacing")
        lay.prop(p, "standalone_post_size")
        lay.prop(p, "standalone_hand_size")
        kind = STYLE_BY_ID.get(p.standalone_style, STYLES[0]).get("kind")
        if kind in ("bal", "flat", "diag", "turned", "twist", "lattice"):
            lay.prop(p, "standalone_baluster_size")
            lay.prop(p, "standalone_baluster_spacing")
        if kind == "horiz":
            lay.prop(p, "standalone_bar_count")
        if kind in ("glass", "glass_ch"):
            lay.prop(p, "standalone_glass_thk")
        if kind == "wall":
            lay.prop(p, "standalone_wall_thk")
        if kind == "cable":
            lay.prop(p, "standalone_cable_dia")
            lay.prop(p, "standalone_cable_gap")
        if kind == "bracket":
            lay.prop(p, "standalone_wall_gap")
            lay.prop(p, "standalone_bracket_spacing")
        lay.operator("pstairs.standalone_rails", text="Generate / Update Railings", icon="MOD_BUILD")
        lay.operator("pstairs.remove_edge_rails", text="Remove Standalone Railings", icon="X")
        lay.label(text="Object Mode updates the saved edge selection")


class PSTAIRS_PT_luxury(_SubBase, bpy.types.Panel):
    bl_label = "Handrail, Newels && Lights"
    bl_idname = "PSTAIRS_PT_luxury"

    def draw(self, context):
        p = context.object.pstairs
        c = self.layout.column()
        c.prop(p, "hand_shape")
        c.prop(p, "rail_end")
        c.separator()
        c.prop(p, "newel_mode")
        if p.newel_mode != "NONE":
            if p.newel_mode in ("CORNERS", "ALL"):
                c.prop(p, "corner_angle")
            c.prop(p, "newel_shape")
            c.prop(p, "newel_size")
            c.prop(p, "newel_extra")
            c.prop(p, "newel_cap")
            c.prop(p, "newel_base")
        c.prop(p, "post_plate")
        c.separator()
        c.prop(p, "led_rail")
        c.prop(p, "led_steps")


class PSTAIRS_PT_stats(_SubBase, bpy.types.Panel):
    bl_label = "Stair Stats"
    bl_idname = "PSTAIRS_PT_stats"

    def draw(self, context):
        ob = context.object
        lay = self.layout
        err = _ERR.get(ob.name)
        if err:
            lay.label(text="Last build failed:", icon="ERROR")
            lay.label(text=err[:60])
        data = _STATS_BY_OBJ.get(ob.name)
        if not ob.pstairs.generated or not data:
            lay.label(text="Generate or update to see stats")
            return
        steps = sum(d[0] for d in data)
        rise = sum(d[3] for d in data)
        lay.label(text="%d flight(s), %d risers, total rise %.2f m" % (len(data), steps, rise), icon="INFO")
        flights = _FL_BY_OBJ.get(ob.name, [])
        if flights:
            lay.label(text="Narrowest modelled flight: %.0f mm" % (min(f["width"] for f in flights) * 1000))
        lay.label(text="Sum of flight runs: %.3f m (excludes landings)" % sum(d[4] for d in data))
        meta = _META.get(ob.name)
        if meta and ob.pstairs.engine == "PARAM":
            ok = abs(meta["rise"] - meta["H"]) < 1e-4
            lay.label(text="Floor to floor %.3f m, stair rise %.3f m" % (meta["H"], meta["rise"]),
                      icon="CHECKMARK" if ok else "ERROR")
        lay.prop(ob.pstairs, "target_riser_max")
        lay.prop(ob.pstairs, "target_going_min")
        lay.label(text="Targets are user-defined; verify local rules", icon="INFO")
        for k, (n, r, g, H, Ls) in enumerate(data, 1):
            ang = math.degrees(math.atan2(r, g))
            bad = r > ob.pstairs.target_riser_max or g < ob.pstairs.target_going_min
            col = lay.column(align=True)
            col.label(text="Flight %d: %d steps, %.1f deg" % (k, n, ang), icon="ERROR" if bad else "INFO")
            col.label(text="   riser %.0f mm, going %.0f mm (2R+G %.0f)" % (r * 1000, g * 1000, (2 * r + g) * 1000))
        chk = _CHK.get(ob.name)
        if chk:
            lay.separator()
            lay.label(text="Support and railing checks")
            col = lay.column(align=True)
            icons = {"WARN": "ERROR", "INFO": "INFO", "OK": "CHECKMARK"}
            for lv, txt in chk[:12]:
                col.label(text=txt[:70], icon=icons[lv])


# =============================================================================
#  Live update handler
# =============================================================================

@persistent
def _depsgraph_handler(scene, depsgraph):
    if _busy:
        return
    todo = {}
    touched = []
    for u in depsgraph.updates:
        idb = u.id
        if not isinstance(idb, bpy.types.Object):
            continue
        if not (u.is_updated_geometry or u.is_updated_transform):
            continue
        ob = getattr(idb, "original", idb)
        touched.append(ob)
        try:
            if ob.type == "MESH" and ob.pstairs.generated and ob.pstairs.live:
                todo[ob.name] = ob
        except Exception:
            continue
    if touched:
        # stairs whose lower / upper reference plane moved
        try:
            for o in bpy.data.objects:
                if o.type != "MESH" or o.name in todo or o.get("ps_part") is not None:
                    continue
                p = o.pstairs
                if p.generated and p.live and p.engine == "PARAM" and (
                        (p.lower_ref is not None and p.lower_ref in touched)
                        or (p.upper_ref is not None and p.upper_ref in touched)):
                    todo[o.name] = o
        except Exception:
            pass
    for ob in todo.values():
        rebuild(ob, force=False)


# =============================================================================
#  Registration
# =============================================================================

class PSTAIRS_PT_well(_SubBase, bpy.types.Panel):
    bl_label = "Stairwell Fit"
    bl_idname = "PSTAIRS_PT_well"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        ob = context.object
        p = ob.pstairs
        c = self.layout.column()
        if p.engine != "PARAM" or p.layout in ("CURVED", "HELICAL", "SPIRAL"):
            c.label(text="Needs a parametric straight / L / U stair", icon="INFO")
            return
        c.prop(p, "well_obj")
        if p.well_obj is None:
            col = c.column(align=True)
            col.prop(p, "well_w")
            col.prop(p, "well_l")
            c.label(text="Void corner = 3D cursor", icon="PIVOT_CURSOR")
        c.prop(p, "well_start")
        c.prop(p, "fit_min_width")
        c.prop(p, "fit_choice")
        c.operator("pstairs.compare_fit", icon="VIEWZOOM")
        for label in _FIT_OPTIONS.get(ob.name, []):
            c.label(text=label)
        c.operator("pstairs.fit_well", icon="SNAP_FACE")
        c.separator()
        c.label(text="Slab opening")
        c.prop(p, "slab_obj")
        c.prop(p, "opening_margin")
        c.prop(p, "fit_cut")
        row = c.row(align=True)
        op = row.operator("pstairs.cut_opening", text="Cut Opening", icon="MOD_BOOLEAN")
        op.apply = False
        op = row.operator("pstairs.cut_opening", text="Make Permanent", icon="CHECKMARK")
        op.apply = True
        msg = _FIT_MSG.get(ob.name)
        if msg:
            for i in range(0, len(msg), 52):
                c.label(text=msg[i:i + 52])


class PSTAIRS_PT_materials(_SubBase, bpy.types.Panel):
    bl_label = "Materials && UVs"
    bl_idname = "PSTAIRS_PT_materials"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        p = context.object.pstairs
        c = self.layout.column()
        c.prop(p, "gen_uvs")
        if p.gen_uvs:
            col = c.column(align=True)
            col.prop(p, "uv_timber")
            col.prop(p, "uv_finish")
            col.prop(p, "uv_concrete")
            col.prop(p, "uv_other")
        c.separator()
        c.prop(p, "tex_finish")
        row = c.row(align=True)
        row.operator("pstairs.textures", text="Procedural").mode = "PROCEDURAL"
        row.operator("pstairs.textures", text="UV Grid").mode = "UV_GRID"
        row.operator("pstairs.textures", text="Remove").mode = "CLEAR"
        col = c.column(align=True)
        col.prop(p, "tex_img_timber", text="Timber")
        col.prop(p, "tex_img_finish", text="Finish")
        col.prop(p, "tex_img_concrete", text="Concrete")
        c.operator("pstairs.textures", text="Apply Image Textures", icon="IMAGE_DATA").mode = "IMAGES"


class PSTAIRS_PT_boq(_SubBase, bpy.types.Panel):
    bl_label = "Quantities (BOQ)"
    bl_idname = "PSTAIRS_PT_boq"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        ob = context.object
        p = ob.pstairs
        c = self.layout.column()
        if not p.generated:
            c.label(text="Generate the stair first", icon="INFO")
            return
        c.prop(p, "boq_waste")
        c.label(text="Open material shells omitted; verify all estimates", icon="INFO")
        row = c.row(align=True)
        row.operator("pstairs.boq_calc", icon="FILE_REFRESH")
        row.operator("pstairs.boq_export", icon="EXPORT")
        got = _BOQ.get(ob.name)
        if not got:
            return
        sig, rows = got
        if sig != _SIG.get(ob.name):
            c.label(text="Out of date - recalculate", icon="ERROR")
        w = 1.0 + p.boq_waste / 100.0
        sec = None
        col = c.column(align=True)
        for s_, item, unit, q, note, wa in rows:
            if s_ != sec:
                sec = s_
                col.separator()
                col.label(text=s_)
            col.label(text="%s: %.3g %s" % (item[:34], q * w if wa else q, unit))


CLASSES = (PSProps, PSTAIRS_OT_export_section, PSTAIRS_OT_surface_clashes, PSTAIRS_OT_viewport_detail, PSTAIRS_OT_compare_fit, PSTAIRS_OT_headroom, PSTAIRS_OT_export_sketch, PSTAIRS_OT_mark_edges, PSTAIRS_OT_standalone_rails, PSTAIRS_OT_remove_edge_rails, PSTAIRS_OT_lib_save, PSTAIRS_OT_lib_load, PSTAIRS_OT_lib_delete, PSTAIRS_OT_lib_import,
           PSTAIRS_OT_lib_export, PSTAIRS_OT_lib_refresh, PSTAIRS_OT_lib_open, PSTAIRS_OT_textures, PSTAIRS_OT_cut_opening, PSTAIRS_OT_boq_calc, PSTAIRS_OT_boq_export, PSTAIRS_OT_fit_well, PSTAIRS_OT_generate, PSTAIRS_OT_update, PSTAIRS_OT_clear, PSTAIRS_OT_freeze,
           PSTAIRS_OT_sample, PSTAIRS_OT_add_param, PSTAIRS_OT_bake, PSTAIRS_OT_repair, PSTAIRS_OT_preset, PSTAIRS_OT_apply_look, PSTAIRS_OT_preset_save,
           PSTAIRS_OT_preset_load, PSTAIRS_PT_main, PSTAIRS_PT_presets, PSTAIRS_PT_engine, PSTAIRS_PT_well, PSTAIRS_PT_kind, PSTAIRS_PT_steps,
           PSTAIRS_PT_structure, PSTAIRS_PT_nosing, PSTAIRS_PT_finish, PSTAIRS_PT_rails, PSTAIRS_PT_standalone, PSTAIRS_PT_coordination, PSTAIRS_PT_luxury,
           PSTAIRS_PT_stats, PSTAIRS_PT_materials, PSTAIRS_PT_boq)


def register():
    load_previews()
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Object.pstairs = PointerProperty(type=PSProps)
    if _depsgraph_handler not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_depsgraph_handler)


def unregister():
    global _pcoll
    if _depsgraph_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_depsgraph_handler)
    del bpy.types.Object.pstairs
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
    if _pcoll:
        bpy.utils.previews.remove(_pcoll)
        _pcoll = None


if __name__ == "__main__":
    try:
        unregister()
    except Exception:
        pass
    register()
