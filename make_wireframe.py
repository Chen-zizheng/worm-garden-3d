"""Wireframe evidence renders (handbook 16.3: "wireframe cube and small maze").

Headless: only numpy + Pillow.  Draws mesh edges with the same camera and the same
projection matrices that the solid renderer uses, so the wireframe and the shaded
screenshots share one pipeline.

    python make_wireframe.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "vendor"))
sys.path.insert(0, HERE)

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import config as C
import geometry as geo
import math3d as M
from camera import Camera
from world import World

SHOTS = os.path.join(HERE, "screenshots")
FONT = "C:/Windows/Fonts/consola.ttf"
FONT_B = "C:/Windows/Fonts/consolab.ttf"

W, H = 1280, 800
BAR = 64
BG_TOP = (14, 22, 40)
BG_BOT = (6, 10, 20)
EDGE = (120, 235, 210)
EDGE_FAR = (60, 120, 110)
WATER = (110, 175, 245)
FLAG = (250, 250, 250)
TEXT = (230, 240, 250)
DIM = (150, 190, 215)


def project(camera, pts, w, h):
    """world points (N,3) -> screen (N,2) inside a w x h panel, plus eye z."""
    ph = np.concatenate([pts, np.ones((len(pts), 1), np.float32)], axis=1).astype(np.float32)
    eye = ph @ camera.view_matrix().T
    proj = camera.proj_matrix(w / float(h))
    hh = np.hstack([np.asarray(eye[:, :3], np.float64), np.ones((len(pts), 1))])
    clip = hh @ proj.T
    ww = np.where(np.abs(clip[:, 3]) < 1e-9, 1e-9, clip[:, 3])
    ndc = clip[:, :3] / ww[:, None]
    sx = (ndc[:, 0] * 0.5 + 0.5) * w
    sy = (1.0 - (ndc[:, 1] * 0.5 + 0.5)) * h
    # look_at keeps the right-handed convention: points in front of the camera have
    # negative eye z, so report positive depth along the view direction.
    return np.stack([sx, sy], axis=1), -eye[:, 2]


def segments_from_faces(faces):
    edges = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]], axis=0)
    edges = np.sort(edges, axis=1)
    return np.unique(edges, axis=0)


def draw_edges(draw, cam, pts, eye_z, edges, near, color, alpha_far=0.35):
    n = len(pts)
    ok = eye_z > near
    for a, b in edges:
        if not (ok[a] and ok[b]):
            continue
        depth = float(min(eye_z[a], eye_z[b]))
        f = np.clip((depth - 3.0) / 30.0, 0.0, 1.0)
        c = tuple(int(round(color[i] * (1 - f * alpha_far) + 20 * f * alpha_far)) for i in range(3))
        draw.line([tuple(pts[a]), tuple(pts[b])], fill=c, width=2)


def gradient():
    img = Image.new("RGB", (W, H - BAR), BG_TOP)
    d = ImageDraw.Draw(img)
    for y in range(H - BAR):
        t = y / float(H - BAR)
        d.line([(0, y), (W, y)], fill=tuple(int(BG_TOP[i] * (1 - t) + BG_BOT[i] * t) for i in range(3)))
    return img


def finish(img, title, subtitle):
    out = Image.new("RGB", (W, H), BG_BOT)
    out.paste(img, (0, 0))
    d = ImageDraw.Draw(out)
    f_t = ImageFont.truetype(FONT_B, 26)
    f_s = ImageFont.truetype(FONT, 19)
    d.text((28, 18), title, font=f_t, fill=TEXT)
    d.text((28, H - BAR + 20), subtitle, font=f_s, fill=DIM)
    return out


def cube_shot():
    """Left panel perspective, right panel orthographic - same camera distance."""
    meshes = [geo.box(0.0, 0.75, 0.0, 1.5, 1.5, 1.5, (1, 1, 1))]
    # a second, smaller cube further away to show the projection difference
    meshes.append(geo.box(3.2, 0.35, -1.6, 0.7, 0.7, 0.7, (1, 1, 1)))
    pts_list, edges_list = [], []
    for m in meshes:
        pts_list.append(m["verts"])
        edges_list.append(segments_from_faces(m["faces"]))
    verts = np.concatenate(pts_list, axis=0)
    off = 0
    edges = []
    for m, e in zip(meshes, edges_list):
        edges.append(e + off)
        off += len(m["verts"])
    edges = np.concatenate(edges, axis=0)

    img = gradient()
    d = ImageDraw.Draw(img)
    pw = W // 2
    for i in range(2):
        cam = Camera()
        cam.mode = "perspective" if i == 0 else "orthographic"
        cam.eye = np.array([5.6, 3.4, 7.0], np.float32)
        cam.target = np.array([1.4, 0.8, -0.2], np.float32)
        cam.up = np.array([0.0, 1.0, 0.0], np.float32)
        cam.ortho_h = 8.6
        cam._update_basis()
        pts, ez = project(cam, verts, pw, H - BAR)
        sx = np.clip(pts[:, 0] + i * pw, -5000, 5000)
        sy = np.clip(pts[:, 1], -5000, 5000)
        pts2 = np.stack([sx, sy], axis=1)
        clip = d
        draw_edges(clip, cam, pts2, ez, edges, C.NEAR, EDGE)
        label = "perspective (P key)" if i == 0 else "orthographic (P key)"
        f = ImageFont.truetype(FONT, 20)
        d.text((i * pw + 30, H - BAR - 44), label, font=f, fill=DIM)
    d.line([(pw, 0), (pw, H - BAR)], fill=(60, 80, 100), width=2)
    return finish(img, "Wireframe cube - the same two cubes, two projections",
                  "Edge list from the triangle mesh, projected with the same view/projection matrices as the solid renderer.")


def maze_shot():
    w = World(seed=7)
    img = gradient()
    d = ImageDraw.Draw(img)
    cam = Camera()
    cam.set_preset(3)
    cam.mode = "perspective"
    cam.update(w, 0.016)


    # wall prisms: top rectangle + four vertical edges (all walls have equal height)
    top = []
    vertical = []
    for (x0, z0, x1, z1) in w.wall_rects:
        y = C.WALL_H
        corners = [(x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)]
        for i in range(4):
            a = corners[i]
            b = corners[(i + 1) % 4]
            top.append((a, b))
            vertical.append(((a[0], 0.0, a[2]), a))
    verts = []
    edges = []
    for a, b in top + vertical:
        i = len(verts)
        verts.extend([a, b])
        edges.append((i, i + 1))
    verts = np.array(verts, np.float32)
    edges = np.array(edges, np.int64)

    pts, ez = project(cam, verts, W, H - BAR)
    draw_edges(d, cam, pts, ez, edges, C.NEAR, EDGE)

    # ground outline
    gx0, gz0, gx1, gz1 = -1.0, -1.0, C.MAZE_W + 1.0, C.MAZE_H + 1.0
    gp = np.array([[gx0, 0.02, gz0], [gx1, 0.02, gz0], [gx1, 0.02, gz1], [gx0, 0.02, gz1]], np.float32)
    gpts, gez = project(cam, gp, W, H - BAR)
    for i in range(4):
        if gez[i] > C.NEAR and gez[(i + 1) % 4] > C.NEAR:
            d.line([tuple(gpts[i]), tuple(gpts[(i + 1) % 4])], fill=(120, 160, 190), width=2)

    # the four medals and the finish flag as markers
    for m in w.medals:
        p = m["pos"]
        mp = np.array([[p[0], 0.0, p[1]], [p[0], C.MEDAL_HOVER, p[1]]], np.float32)
        mpts, mez = project(cam, mp, W, H - BAR)
        if (mez > C.NEAR).all():
            d.line([tuple(mpts[0]), tuple(mpts[1])], fill=(250, 230, 120), width=3)

    return finish(img, "Wireframe maze - 23 x 15 cells, %d wall prisms" % len(w.wall_rects),
                  "Same geometry the shaded renderer draws, shown as edges: top rectangles plus vertical corner edges.")


def main():
    os.makedirs(SHOTS, exist_ok=True)
    for name, img in (("16_wireframe_cube.png", cube_shot()),
                      ("17_wireframe_maze.png", maze_shot())):
        path = os.path.join(SHOTS, name)
        img.save(path)
        print("saved", path)


if __name__ == "__main__":
    main()
