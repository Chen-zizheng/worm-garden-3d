"""生成技术报告 report.docx（6-10 页，用 python-docx 排版）。

    python make_report.py

报告里的所有数字与图片都可以由仓库里的脚本重新生成：
    python bench_render.py 20     -> bench_results.json（性能表）
    python make_screenshots.py    -> screenshots/（全部截图与对比图）
    python run_tests.py           -> 55 个单元测试
"""
import json
import os

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(HERE, "screenshots")
CMP = os.path.join(SHOTS, "comparisons")
OUT = os.path.join(HERE, "report.docx")

BODY_FONT = "Calibri"
MONO_FONT = "Consolas"
ACCENT = RGBColor(0x1F, 0x4E, 0x79)
GREY = RGBColor(0x59, 0x59, 0x59)


# ----------------------------------------------------------------------
# 排版辅助
# ----------------------------------------------------------------------
def setup(document):
    st = document.styles["Normal"]
    st.font.name = BODY_FONT
    st.font.size = Pt(10)
    st.paragraph_format.space_after = Pt(3)
    st.paragraph_format.line_spacing = 1.06

    for name, size in (("Heading 1", 15), ("Heading 2", 12.5), ("Heading 3", 11)):
        s = document.styles[name]
        s.font.name = BODY_FONT
        s.font.size = Pt(size)
        s.font.color.rgb = ACCENT
        s.font.bold = True
        s.paragraph_format.space_before = Pt(8 if name == "Heading 1" else 6)
        s.paragraph_format.space_after = Pt(3)

    for s in document.sections:
        s.top_margin = Cm(1.7)
        s.bottom_margin = Cm(1.7)
        s.left_margin = Cm(2.2)
        s.right_margin = Cm(2.2)


def add_page_number(section):
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = footer.add_run()
    for instr, kind in (("begin", None), (None, "PAGE"), ("end", None)):
        if kind:
            f = OxmlElement("w:instrText")
            f.set(qn("xml:space"), "preserve")
            f.text = kind
            run._r.append(f)
        else:
            f = OxmlElement("w:fldChar")
            f.set(qn("w:fldCharType"), instr)
            run._r.append(f)


def para(document, text, style=None, size=None, italic=False, space_after=None,
         align=None, color=None):
    p = document.add_paragraph(style=style)
    run = p.add_run(text)
    if size:
        run.font.size = Pt(size)
    if italic:
        run.italic = True
    if color:
        run.font.color.rgb = color
    if space_after is not None:
        p.paragraph_format.space_after = Pt(space_after)
    if align is not None:
        p.alignment = align
    return p


def bullets(document, items):
    for it in items:
        p = document.add_paragraph(style="List Bullet")
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.left_indent = Cm(0.6)
        if isinstance(it, tuple):
            head, rest = it
            r = p.add_run(head)
            r.bold = True
            p.add_run(rest)
        else:
            p.add_run(it)


def mono(document, text):
    p = document.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.left_indent = Cm(0.4)
    for i, line in enumerate(text.split("\n")):
        run = p.add_run(line)
        run.font.name = MONO_FONT
        run.font.size = Pt(9)
        run._element.rPr.rFonts.set(qn("w:eastAsia"), MONO_FONT)
        if i < len(text.split("\n")) - 1:
            run.add_break()
    return p


def figure(document, path, caption, width_cm=12.6):
    p = document.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(2)
    p.add_run().add_picture(path, width=Cm(width_cm))
    cap = document.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.space_after = Pt(6)
    run = cap.add_run(caption)
    run.italic = True
    run.font.size = Pt(9)
    run.font.color.rgb = GREY


def table(document, header, rows, widths=None, caption=None, font_size=9):
    if caption:
        cap = document.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = cap.add_run(caption)
        run.italic = True
        run.font.size = Pt(9)
        run.font.color.rgb = GREY
    t = document.add_table(rows=1, cols=len(header))
    t.style = "Light Grid Accent 1"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = t.rows[0].cells
    for i, text in enumerate(header):
        hdr[i].text = ""
        run = hdr[i].paragraphs[0].add_run(text)
        run.bold = True
        run.font.size = Pt(font_size)
    for row in rows:
        cells = t.add_row().cells
        for i, value in enumerate(row):
            cells[i].text = ""
            run = cells[i].paragraphs[0].add_run(str(value))
            run.font.size = Pt(font_size)
    if widths:
        for row in t.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Cm(w)
    p = document.add_paragraph()
    p.paragraph_format.space_after = Pt(2)
    return t


def load_bench():
    path = os.path.join(HERE, "bench_results.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ----------------------------------------------------------------------
# 报告内容
# ----------------------------------------------------------------------
def build():
    doc = Document()
    setup(doc)
    add_page_number(doc.sections[0])

    # ---------- 标题页 ----------
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("Worms Garden Adventure 3D")
    run.bold = True
    run.font.size = Pt(24)
    run.font.color.rgb = ACCENT
    title.paragraph_format.space_before = Pt(44)

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = sub.add_run("A software-rasterised 3D remake of the 2D maze game")
    run.font.size = Pt(14)
    run.italic = True

    info = doc.add_paragraph()
    info.alignment = WD_ALIGN_PARAGRAPH.CENTER
    info.paragraph_format.space_before = Pt(26)
    info.add_run(
        "Technical report for the final assignment (Labs 10 and 11)\n"
        "GEIAL31L-B2a Computer Graphics Programming\n"
        "Institute of Information Science, University of Miskolc\n\n"
        "Student: Chen Zizheng\n"
        "Neptun code: EO8UMY\n"
        "Date: 23 November 2026"
    ).font.size = Pt(11)

    figure(doc, os.path.join(SHOTS, "06_overview_perspective.png"),
           "Figure 1 - Overview of one procedurally generated 23x15 level. "
           "Everything is drawn by the NumPy software renderer described in this report.",
           width_cm=12.0)
    doc.add_page_break()

    # ---------- 1. 引言 ----------
    doc.add_heading("1. Introduction and objectives", level=1)
    para(doc,
         "The assignment was to convert the 2D maze game developed during Labs 6-8 into a fully "
         "interactive 3D game, using only Python, NumPy, Pillow and Pygame, and to demonstrate the "
         "fundamental computer-graphics techniques listed in the handbook: 3D coordinate systems, "
         "transformations, camera positioning and projection, clipping, back-face culling, depth "
         "buffering, lighting and shading, texture mapping, animation, particles and rendering "
         "optimisation.")
    para(doc,
         "The design decision that shapes the whole project is that nothing is drawn by the graphics "
         "driver: the game writes a complete frame into a NumPy array (a colour buffer plus a depth "
         "buffer) and Pygame is used only as a window, an input device and a bitmap blitter. Every "
         "stage that a GPU would normally hide - the model/view/projection matrices, the near-plane "
         "clipping, the triangle setup, the barycentric interpolation, the depth test, the lighting "
         "equation and the texture sampler - is therefore explicit, inspectable, and mathematically "
         "verifiable, which is exactly what a computer graphics course asks for.")
    para(doc,
         "The report is organised as follows. Section 2 summarises the game and the mandatory 3D "
         "features. Section 3 describes the architecture of the program. Section 4 derives the "
         "mathematics of the pipeline. Section 5 explains the performance work, Section 6 the three "
         "Part B extensions, Section 7 the automated tests, and Section 8 the measured performance. "
         "Section 9 lists the known limitations and Section 10 concludes.")

    # ---------- 2. 游戏 ----------
    doc.add_heading("2. Game overview and mandatory features", level=1)
    para(doc,
         "The world is a 23 x 15 cell maze generated with a recursive backtracker, so every level is a "
         "perfect maze (all 345 cells are reachable and there is exactly one path between any two "
         "cells). One world unit equals one maze cell, which reproduces the 50-pixel cell size of the "
         "2D original; wall height is 0.75 and wall thickness 0.16, exactly as in the handbook. The "
         "player controls a worm built from three shaded spheres; nine water holes reset the run, four "
         "medals (three silver worth 50 points and one gold worth 100) have to be collected before the "
         "finish flag opens, and three birds patrol the corridors. There are no checkpoints: the start "
         "flag is only the spawn point, as in the 2D original, and every reset is reported on the HUD "
         "(water hole, bird or closed finish flag) so that being sent back never looks like a broken "
         "control. A 1.2 s spawn guard after each reset keeps a bird from hitting the worm again before "
         "the player can react.")
    para(doc,
         "Table 1 maps the mandatory requirements of the handbook to the place in the code where they "
         "are implemented.")
    table(doc,
          ["Requirement", "Implementation"],
          [["Maze, ground, walls, worm, birds, apples, water, flags", "scene.py (static and dynamic meshes), world.py (rules)"],
           ["Movable camera, three presets", "camera.py - chase, top-down, overview"],
           ["Perspective and orthographic projection", "math3d.perspective / orthographic, toggled with P"],
           ["Filled triangles and depth buffer", "raster.Renderer._raster_tri: edge functions + z-buffer"],
           ["Near-plane clipping", "raster.clip_near (Sutherland-Hodgman in camera space)"],
           ["Back-face culling", "signed screen-space area test in draw_mesh"],
           ["Ambient and diffuse lighting", "draw_mesh: ambient + key light + fill light, per-triangle normal"],
           ["At least one Pillow texture", "assets.make_grass, make_stone, make_checker (128x128 PNGs)"],
           ["3D animation", "worm squash/stretch and walk cycle, bird wing flapping in scene.build_dynamic"],
           ["3D particles", "sparks behind the moving worm, billboard quads, pool capped at 250"],
           ["Procedural maze, collision, jump, score, timer", "world.py (unchanged 2D rules, moved to 3D)"],
           ["Part B: >= 2 extensions, >= 1 graphics",
            "A: bilinear texture filtering, B: depth fog, C: screen-space bloom (Section 6)"]],
          widths=[8.0, 8.4], caption="Table 1 - Mandatory features and where they live.",
          font_size=8.5)

    # ---------- 3. 架构 ----------
    doc.add_heading("3. System architecture", level=1)
    para(doc,
         "The program is split into a game-logic half that knows nothing about pixels and a graphics "
         "half that knows nothing about the rules of the game. The game half (world.py) is the 2D "
         "logic from Labs 6-8 with the position vector extended from (x, y) to (x, z) and a separate "
         "height y for jumping. The graphics half turns the current state of the world into triangle "
         "meshes and rasterises them.")
    mono(doc,
         "main.py            window, input, HUD, frame loop\n"
         "  world.py         game rules: maze, collision, player, medals, enemies, particles\n"
         "  scene.py         world -> meshes (static maze merged into 173 wall runs, dynamic actors)\n"
         "  render_scene.py  per-frame entry: static cache, camera matrices, fog + bloom + grade\n"
         "  camera.py        3 presets, orbit, projection switching\n"
         "  raster.py        clip -> project -> cull -> rasterise -> shade -> texture -> fog\n"
         "  math3d.py        mat4 helpers (translation, scaling, rotation, projections, look_at)\n"
         "  geometry.py      mesh builders (box, quad, disc, cylinder, sphere, merge, transform)\n"
         "  assets.py        procedural textures (Pillow), loaded into float32 arrays")
    para(doc,
         "A frame costs one pass over the world state (a few hundred microseconds) and one pass over "
         "the triangles. Static geometry - the ground, the merged wall mesh, water, flags - is built "
         "once per level and cached against a generation counter, so a level change invalidates it "
         "automatically. Only the worm, medals, birds and particles are rebuilt every frame, and they "
         "are cheap because they are small meshes (a sphere with 4 rings x 8 segments is 64 triangles).")
    para(doc,
         "The meshes used throughout are simple dictionaries (vertices, triangle indices, per-face "
         "colours, optional uv coordinates and texture name, and the culling flags) rather than "
         "classes. That keeps the hot loop free of attribute lookups and makes the renderer usable "
         "from the unit tests with three-line fixtures.")

    # ---------- 4. 数学 ----------
    doc.add_heading("4. Mathematics of the pipeline", level=1)
    doc.add_heading("4.1 Coordinate spaces and matrix convention", level=2)
    para(doc,
         "Points are column vectors (x, y, z, 1) and matrices are 4x4, row-major in memory, applied as "
         "p' = M p. The chain is model -> world -> view (camera) -> clip -> NDC -> screen. Right-handed "
         "coordinates are used: +x is east, +y is up, +z is south, and the camera looks down its own "
         "-z axis. This is the OpenGL convention, which keeps the near plane at a negative z in camera "
         "space and makes the sign of the perspective divide predictable.")
    para(doc,
         "Transformations compose by right multiplication, so a point is transformed by "
         "P V M p, i.e. the model matrix is applied first. In this project the model matrix is only "
         "used for the animated objects (translation to the actor position, rotation for the heading, "
         "and a non-uniform scale for the squash/stretch of the worm).")

    doc.add_heading("4.2 Perspective projection", level=2)
    para(doc,
         "A point (x, y, z) in camera space is projected onto the image plane at distance d by "
         "x_ndc = (x / -z) / (tan(fov_y / 2) * aspect) and y_ndc = (y / -z) / tan(fov_y / 2). "
         "The homogeneous form packs the division by -z into the w component:")
    mono(doc,
         "| 1/(tan(fov/2)*aspect)      0            0              0 |\n"
         "|        0            1/tan(fov/2)        0              0 |\n"
         "|        0                  0       (far+near)/(near-far)   2*far*near/(near-far) |\n"
         "|        0                  0           -1               0 |")
    para(doc,
         "so that after the divide by w = -z the depth becomes")
    mono(doc,
         "z_ndc = ((far + near) / (near - far) * z + 2*far*near/(near - far)) / (-z)")
    para(doc,
         "which maps the near plane to -1 and the far plane to +1. The non-linearity of this mapping "
         "is the reason a z-buffer with limited precision concentrates its resolution near the camera; "
         "with float32 and a 0.1 - 120 range that was not a practical problem here, but it is one of the "
         "reasons the project keeps the near plane as far out as the chase camera allows.")

    doc.add_heading("4.3 Orthographic projection", level=2)
    para(doc,
         "In orthographic mode the divisor is a constant instead of -z: x_ndc = x / (aspect * ortho_h/2), "
         "y_ndc = y / (ortho_h/2), z_ndc = (2z - (far+near)) / (far - near) with the sign adjusted for "
         "the -z forward axis. There is no foreshortening and no perspective divide, which is exactly "
         "the property used by the top-down and overview comparison shots: parallel corridor walls stay "
         "parallel, so the maze reads like the original 2D map. Because the depth mapping is affine, "
         "texture coordinates can be interpolated linearly in orthographic mode (the renderer passes "
         "perspective=False to skip the u/z division).")

    doc.add_heading("4.4 View matrix", level=2)
    para(doc,
         "look_at(eye, target, up) builds an orthonormal basis: forward f = normalize(eye - target) "
         "(pointing from the target towards the eye, because the camera looks down -z), right "
         "r = normalize(cross(up, f)), and the corrected up u = cross(f, r). The view matrix is the "
         "inverse of the camera frame, i.e. a rotation whose rows are (r, u, f) plus the translation "
         "-R eye. This is why the third camera preset can be placed at an arbitrary point above the "
         "maze with up = (0, 1, 0) and still produce a correct, non-mirrored image.")
    para(doc,
         "The same matrix solves the input problem. Camera.ground_basis() reads two rows of the view "
         "matrix - the right vector r and the negated third row, which is the camera's viewing "
         "direction - drops their y component, normalises them and returns the pair. A key vector "
         "(forward, right) is then mapped to a world-space step move = f * forward + r * right, so the "
         "arrow keys keep their on-screen meaning in every preset and after any orbit. In the top-down "
         "preset the viewing direction is almost vertical, so the ground direction is taken from the "
         "camera's up vector instead; the length test is done before normalising, because the eye has "
         "a 0.001 offset to avoid a degenerate look_at and normalising first would amplify that "
         "numerical noise into a bogus direction - which is exactly the 'left sometimes walks right' "
         "bug that appeared in testing.")

    doc.add_heading("4.5 Near-plane clipping", level=2)
    para(doc,
         "Clipping happens in camera space, before the perspective divide, against the plane z = -near. "
         "Doing it after the divide would be wrong, because points behind the camera have a negative w "
         "and would be mirrored into the visible half of the screen. Each triangle is classified by the "
         "sign of (z + near) at its vertices: fully inside -> keep, fully outside -> drop, otherwise "
         "intersect the triangle with the plane using Sutherland-Hodgman and re-triangulate the "
         "resulting polygon (a triangle clipped by one plane produces at most one quadrilateral, "
         "i.e. two triangles). The intersection parameter t = (z_a + near) / (z_a - z_b) is reused to "
         "interpolate the texture coordinates at the new vertices, so clipped geometry keeps its "
         "texture alignment.")
    para(doc,
         "The near plane is set to 0.1 world units. Together with the fill-rate dominance measured in "
         "Section 8 this is a deliberate trade-off: a smaller near value would give more visible depth "
         "where the camera enters a wall, but would also make the huge ground quad project far outside "
         "the screen and pay for pixels it never shows.")

    doc.add_heading("4.6 Triangle rasterisation and the z-buffer", level=2)
    para(doc,
         "After projection each triangle has three screen positions (x, y) and three NDC depths. The "
         "rasteriser computes the integer bounding box, clips it to the screen, and evaluates the "
         "screen-space edge functions")
    mono(doc,
         "e0(p) = (x1 - x0)(py - y0) - (y1 - y0)(px - x0)\n"
         "e1(p) = (x2 - x1)(py - y1) - (y2 - y1)(px - x1)\n"
         "e2(p) = (x0 - x2)(py - y2) - (y0 - y2)(px - x2)")
    para(doc,
         "for every pixel of the bounding box at once with NumPy broadcasting. A pixel is inside the "
         "triangle when all three edge functions have the same sign as the triangle area; the "
         "normalised barycentric coordinates are then e0/area, e1/area and e2/area, and the depth is "
         "their weighted sum of the vertex depths. The depth test is a strict less-than against the "
         "z-buffer, and the colour is written with the same mask, so a pixel is only ever coloured by "
         "the triangle that actually wins - this was the single most important correctness fix during "
         "development (see Section 5).")
    para(doc,
         "The same signed area also gives back-face culling for free: if the projected triangle winds "
         "the wrong way the area has the opposite sign, and the triangle is rejected before any pixel "
         "work is done. Two-sided meshes (water discs, particle billboards) can disable the test.")

    doc.add_heading("4.7 Illumination", level=2)
    para(doc,
         "Shading is per triangle, using the face normal n = normalize(cross(v1 - v0, v2 - v0)) "
         "computed from the *world-space* vertices (so camera motion never changes the lighting). Two "
         "directional lights are used:")
    mono(doc,
         "shade = ambient + (1 - ambient) * clamp(0.80 * max(0, n . L_key)\n"
         "                                      + 0.34 * max(0, n . L_fill), 0, 1)\n"
         "colour_pixel = texture(u, v) * face_colour * shade")
    para(doc,
         "The ambient term (0.35) keeps shadowed sides readable; the key light comes from behind-left "
         "and above, the fill light from the opposite side at lower weight, which is enough to separate "
         "the four walls of a corridor without a third light. Wall tops use a slightly brighter tint "
         "than the sides, because in the overview camera most of what the player sees is wall tops and "
         "the maze needs to stay legible from above.")

    doc.add_heading("4.8 Perspective-correct texture mapping", level=2)
    para(doc,
         "Affine interpolation of (u, v) in screen space is wrong under perspective projection: the "
         "texture visibly swims on a floor viewed at a grazing angle. The correct quantity to "
         "interpolate linearly is (u/z, v/z, 1/z), because the projected parameterisation is rational "
         "in screen space:")
    mono(doc,
         "u_screen = (u_0/z_0 * b0 + u_1/z_1 * b1 + u_2/z_2 * b2)\n"
         "         / ( 1/z_0 * b0 +   1/z_1 * b1 +   1/z_2 * b2)")
    para(doc,
         "so the rasteriser interpolates u/z, v/z and 1/z with the same barycentric weights as the "
         "depth, divides at the end, and samples the texel at (u, v). In orthographic mode 1/z is "
         "constant over the triangle and the division cancels, so the renderer switches to plain linear "
         "interpolation there (and the extra per-pixel divide disappears).")
    para(doc,
         "The sampler comes in two flavours. Nearest-neighbour takes the texel that contains (u, v), "
         "which is cheap and keeps the textures crisp but produces hard blocky edges. Bilinear "
         "filtering (extension A) takes the four surrounding texels and blends them by the fractional "
         "part, which is described in Section 6.")

    # ---------- 5. 性能 ----------
    doc.add_heading("5. Implementation and performance work", level=1)
    para(doc,
         "A pure-NumPy rasteriser is fill-rate bound, so most of the engineering effort went into "
         "doing less per pixel and touching fewer pixels. The measurements in Section 8 were taken "
         "with the same renderer as the final submission.")
    bullets(doc, [
        ("Merged static geometry. ",
         "The maze is generated cell by cell but adjacent wall faces are merged into 173 long runs "
         "before meshing, so the maze is about 1730 triangles instead of about 6000. The merged mesh "
         "is cached per level."),
        ("Front-to-back submission. ",
         "Meshes are submitted roughly front to back (water, flags, walls, ground) so that the ground "
         "pixels hidden behind a wall fail the depth test before their texture is sampled."),
        ("Vectorised triangle setup. ",
         "One bounding box, one pair of coordinate arrays and one set of edge functions per triangle; "
         "pixels are processed as arrays, not as a Python loop. Replacing np.meshgrid by broadcast "
         "views and using np.copyto(where=mask) instead of fancy indexing took the 480x300 frame from "
         "56.8 ms to 52.6 ms in the textured path."),
        ("Cheap clipping and culling. ",
         "The near-plane test is three scalar comparisons per triangle, and back-face culling is one "
         "signed area, so both happen before any pixel work."),
        ("Textures only where they pay off. ",
         "Ground and walls are textured; the worm, medals, birds and particles are flat shaded. "
         "Texturing every triangle cost about 70% more time for objects that occupy a few hundred "
         "pixels each."),
        ("Selectable internal resolution. ",
         "The window is always 1280x800 but the 3D scene can be rendered at 480x300, 800x500 or "
         "1120x700 and is smooth-scaled up (F1/F2/F3). This is the same trade-off a real console "
         "generation makes, and it is what allows the game to stay interactive on a CPU."),
    ])
    figure(doc, os.path.join(SHOTS, "01_chase_perspective.png"),
           "Figure 2 - Chase camera, perspective projection: the case that has to stay interactive. "
           "Only ~300 of the 2498 triangles survive culling and clipping.", width_cm=12.0)

    # ---------- 6. 扩展 ----------
    doc.add_heading("6. Part B extensions", level=1)
    doc.add_heading("6.1 Extension A: bilinear texture filtering", level=2)
    para(doc,
         "Bilinear sampling replaces the hard texel choice by a weighted average of the 2x2 "
         "neighbourhood. With fu, fv the fractional parts of (u, v) scaled to texel space:")
    mono(doc,
         "c_top    = lerp(texel[v][u],     texel[v][u+1],     fu)\n"
         "c_bottom = lerp(texel[v+1][u],   texel[v+1][u+1],   fu)\n"
         "colour   = lerp(c_top, c_bottom, fv)")
    para(doc,
         "Both taps use the same wrap-around (bitwise AND) indexing as the nearest sampler, because "
         "the textures are 128x128, a power of two. The switch is the B key, the HUD shows the active "
         "mode, and both code paths are covered by unit tests (a constant texture must give bit-identical "
         "results in both modes; a checkerboard must give exactly two colours with nearest sampling and "
         "many intermediate values with bilinear). Figure 3 shows the same 3x-magnified pixels in both "
         "modes: the brick edges are visibly smoother in the bilinear half, at a cost of roughly 60-100% "
         "extra time in the textured fill path.")
    figure(doc, os.path.join(CMP, "filter_nearest_vs_bilinear.png"),
           "Figure 3 - Extension A. Same pixels, 3x magnification: nearest (left) vs bilinear (right).",
           width_cm=14.5)
    para(doc,
         "The checkerboard toggle (T key) turns the comparison into an aliasing experiment "
         "(Figure 4). Nearest sampling produces harsh moire; bilinear softens the pattern but cannot "
         "remove it, because both point-sample a signal that is far above the Nyquist limit of the "
         "screen. That is the honest limit of the extension and is listed in Section 9: the real fix "
         "is a mip pyramid with trilinear selection.")
    figure(doc, os.path.join(CMP, "checker_aliasing.png"),
           "Figure 4 - High-frequency checkerboard, 2x magnification. Bilinear filtering softens but "
           "does not remove the aliasing.", width_cm=14.5)

    doc.add_heading("6.2 Extension B: depth fog computed from the z-buffer", level=2)
    para(doc,
         "Fog needs a per-pixel distance, and the renderer already stores exactly that. After the "
         "scene is rasterised, the NDC depth of every pixel is converted back to a view-space distance "
         "with the inverse of the projection mapping:")
    mono(doc,
         "perspective:  d = b / (z_ndc + a),  a = (far + near)/(near - far),\n"
         "                                    b = 2*far*near/(near - far)\n"
         "orthographic: d = (z_ndc*(far - near) + (far + near)) / 2  -  eye_back")
    para(doc,
         "and the pixel colour is blended towards the fog colour with "
         "f = clamp((d - fog_start) / (fog_end - fog_start), 0, 1). Pixels that were never written "
         "(sky, depth = infinity) get f = 0 and keep the sky gradient. The default range is 7 to 34 "
         "world units (it starts just past the chase camera and ends past the far corner of the maze); "
         "Figure 5 uses a tighter 6 to 22 range so that the effect is clearly visible "
         "in a still image. The whole pass is one vectorised expression over the colour buffer, and it "
         "was verified numerically by projecting known distances through the camera matrices and "
         "recovering them from the fog formula.")
    figure(doc, os.path.join(CMP, "depth_fog_before_after.png"),
           "Figure 5 - Extension B. Left: fog disabled. Right: fog enabled. The far half of the maze "
           "fades into the sky colour, which also hides the edge of the finite ground plane.",
           width_cm=14.5)

    doc.add_heading("6.3 Extension C: screen-space bloom", level=2)
    para(doc,
         "The night art direction wants light to spill out of the bright things: the worm is a glowing "
         "neon body, the medals and the water glints catch the moon. Bloom is the standard screen-space "
         "way to produce that halo, and it is a pure image operation - a second image-processing "
         "extension on top of bilinear filtering.")
    para(doc,
         "After the scene and the fog have been rasterised, a bright pass isolates the pixels above a "
         "threshold, the result is blurred, and the blurred copy is added back to the frame:")
    mono(doc,
         "bright   = max(0, colour - threshold) / (1 - threshold)\n"
         "blurred  = box_blur(box_blur(bright, r) horizontally, r) vertically\n"
         "colour'  = colour + strength * upsample(blurred)")
    para(doc,
         "Both box blurs are implemented with running row and column sums (prefix sums), so their cost "
         "is independent of the radius: a 10-pixel blur costs the same as a 2-pixel blur. The pass runs "
         "on a quarter-resolution copy of the frame, blurs there and upscales it before adding, which is "
         "the same downscale-blur-upscale trick a real engine uses to keep bloom cheap. The threshold "
         "(0.50), radius (10), strength (0.70) and downscale factor (4) are all in config.py, and the "
         "effect can be toggled at runtime with F9, which is how Figure 6 was captured.")
    figure(doc, os.path.join(CMP, "bloom_before_after.png"),
           "Figure 6 - Extension C. Left: bloom disabled. Right: bloom enabled. The worm, the medals "
           "and the moon pick up a soft halo, and the dark corridors gain a lit-from-within feel.",
           width_cm=15.0)
    para(doc,
         "Because the threshold is applied to the final colour, bloom never brightens the sky gradient "
         "(its peak is below the threshold) and only the worm, the medals, the water and the moon glow. "
         "The cost at 800x500 is recorded in Table 5, next to the other feature costs, so the extension "
         "can be judged on price as well as on looks.")

    doc.add_heading("6.4 Projection comparison", level=2)
    para(doc,
         "The two projections are compared on the same camera preset in Figure 7. With perspective the "
         "corridors converge and the player gets a strong sense of depth; with orthographic projection "
         "parallel walls stay parallel and the maze reads as a map, which is exactly the trade-off the "
         "handbook asks students to be able to explain.")
    figure(doc, os.path.join(SHOTS, "03_chase_orthographic.png"),
           "Figure 7 - Chase camera with orthographic projection (press P at any time).",
           width_cm=12.0)

    # ---------- 7. 测试 ----------
    doc.add_heading("7. Automated testing", level=1)
    para(doc,
         "Every non-trivial piece of the pipeline has a unit test that does not need a display, a "
         "window or Pygame - the suite runs on plain NumPy and Pillow, which also means it can run in "
         "CI. python run_tests.py executes 55 tests in well under a second.")
    table(doc,
          ["Test file", "Coverage"],
          [["test_math3d.py", "matrix construction, look_at, perspective/orthographic mappings, near and far behaviour"],
           ["test_geometry.py", "vertex and face counts, outward winding of boxes and spheres, uv generation, transforms do not mutate the source mesh"],
           ["test_raster.py", "screen mapping, near-plane clipping with uv interpolation, z-buffer ordering independent of submission order, back-face culling, nearest vs bilinear output, fog distance inversion"],
           ["test_world.py", "maze connectivity (all 345 cells reachable) and closed border, wall collision, wall sliding, jump apex and air time against the analytic solution, medal scoring, water reset, finish conditions, particle cap and expiry, restart"],
           ["test_assets.py", "textures exist, load, stay in [0, 1], power-of-two size, grass vs stone colour statistics, checkerboard has exactly two values"]],
          widths=[4.2, 12.2], caption="Table 2 - Unit tests (55 assertions groups in total).",
          font_size=8.5)
    para(doc,
         "Writing the tests paid for itself twice. The jump test compares the simulated apex and air "
         "time with the closed-form values v0^2 / 2g = 0.512 and 2v0 / g = 0.64 s, which pinned down "
         "the integration order. More importantly, the depth-buffer and clipping tests found the "
         "single real bug in the rasteriser: the pixel mask was overwritten by the depth comparison, so "
         "each triangle painted its whole bounding box instead of its interior. In the chase camera "
         "this looked like slightly thick walls, but in the overview camera the long boundary walls "
         "turned into huge smeared slabs. The fix was one line (mask = inside & (z < depth)) and is now "
         "guarded by two tests.")

    doc.add_heading("7.1 Visual and gameplay test matrix", level=2)
    para(doc,
         "The handbook's section 16.2 test matrix was executed on the final build. Each row lists the "
         "procedure and the observed result; the two screenshot columns in the README link every claim "
         "to a capture from the same build.")
    table(doc,
          ["Test", "Procedure", "Pass condition", "Result"],
          [
           ["Projection", "Render equal-size cubes at near and far distances", "Perspective changes size; orthographic does not", "Pass - preset 1 vs P key, Figure 7"],
           ["Occlusion", "Put geometry behind opaque walls", "Hidden surfaces never appear", "Pass - z-buffer, all screenshots"],
           ["Near plane", "Move the camera close to a wall and through it", "No inverted polygons or crashes", "Pass - Sutherland-Hodgman clip, test_raster.py"],
           ["Lighting", "Rotate the light direction", "Face brightness changes predictably", "Pass - two-light Lambert term, Figure 3"],
           ["Collision", "Press against every wall direction", "No penetration, no invisible barrier", "Pass - per-axis sliding, test_world.py"],
           ["Jump", "Jump next to water, a bird and a wall", "Height-aware behaviour as documented", "Pass - v0 = 3.2, g = 10, apex 0.512"],
           ["Collectibles", "Collect exactly four apples", "Original scoring retained (3 x 50 + 1 x 100)", "Pass - 250 points, test_world.py"],
           ["New level", "Reach the flag with all apples collected", "Maze and objects regenerate, level increments", "Pass - level 2 in the video at 2:37"],
           ["Restart", "Press R during level 2 or later", "Score, level and particles reset cleanly", "Pass - test_world.py"],
           ["Stress", "Full maze plus particles and effects", "Stable, no runaway particle count", "Pass - 250-particle pool cap"],
           ["Image quality", "Compare 480x300 and 1120x700 internal resolution", "Higher sampling is sharper; cost recorded", "Pass - screenshots 01-07 / Table 4"],
           ["Window resize", "Run fullscreen and windowed", "Shapes keep proportions, HUD visible", "Pass - fixed 1280x800 window, smooth-scaled buffer"]
          ],
          widths=[2.4, 4.6, 4.6, 4.8],
          caption="Table 3 - Visual and gameplay test matrix (handbook section 16.2).",
          font_size=7.8)

    # ---------- 8. 性能 ----------
    doc.add_heading("8. Measured performance", level=1)
    bench = load_bench()
    if bench:
        rows = []
        for r in bench["rows"]:
            if r["quality"] == 1:
                rows.append([r["label"], "800x500", r["tris"], r["drawn"],
                             f"{r['mean']:.1f}", f"{r['p95']:.1f}", f"{1000.0 / r['mean']:.1f}"])
        table(doc, ["Camera / projection", "Resolution", "Triangles", "Drawn",
                    "Mean ms", "p95 ms", "FPS"], rows,
              widths=[4.6, 2.2, 1.8, 1.6, 1.8, 1.6, 1.6],
              caption="Table 4 - Frame times at the 800x500 internal resolution (20 frames per "
                      "configuration, seed 7, level 1).", font_size=8.5)
        costs = bench.get("feature_costs")
        if costs:
            cost_rows = [[c["label"], f"{c['mean']:.1f}", f"{c['p95']:.1f}",
                          f"{1000.0 / c['mean']:.1f}"] for c in costs]
            table(doc, ["Feature set (800x500, chase camera)", "Mean ms", "p95 ms", "FPS"],
                  cost_rows, widths=[8.0, 2.6, 2.6, 2.2],
                  caption="Table 5 - What each feature costs: same camera, same frame, with the "
                          "features switched on one at a time.", font_size=8.5)
    para(doc,
         "The measurements were taken on the development laptop (AMD64, Windows 11, Python 3.13.13, "
         "numpy 2.5.1, Pillow 12.3.0). The renderer is single-threaded, so the core count does not "
         "matter; what matters is that the cost scales almost linearly with the number of shaded "
         "pixels and only weakly with the number of triangles. The chase camera submits 2498 "
         "triangles but writes fewer than 310 of them, so it stays above 25 fps at the default "
         "480x300 resolution; the overview camera sees nearly the whole maze (about 1550 surviving "
         "triangles) and is the worst case at around 5 fps at the highest resolution.")
    para(doc,
         "This is the honest characterisation of a NumPy software rasteriser: it is roughly two orders "
         "of magnitude away from a GPU renderer of the same scene, and it becomes interactive only "
         "because the game renders into a small buffer and upscales. The full table for all three "
         "resolutions is in bench_results.json, and the numbers can be reproduced with "
         "python bench_render.py 20.")

    # ---------- 9. 局限 ----------
    doc.add_heading("9. Known limitations and future work", level=1)
    bullets(doc, [
        ("No mip-mapping. ",
         "Bilinear filtering reduces but does not eliminate aliasing when a texture is minified. A mip "
         "pyramid with trilinear selection, and anisotropic filtering for grazing angles, would be the "
         "next step - the sampler interface already has the (bilinear) switch that such an extension "
         "would generalise."),
        ("Single-threaded rasteriser. ",
         "Triangles are rasterised in a Python loop. Splitting the screen into tiles and rendering them "
         "in parallel processes, or moving the inner loop into a compiled kernel, are the obvious "
         "large wins."),
        ("Flat shading on curved objects. ",
         "The worm, apples and birds are spheres with per-face normals, so they look faceted. "
         "Interpolated vertex normals (Gouraud) or a per-pixel Phong model would smooth them, at the "
         "cost of one more attribute to carry through clipping and rasterisation."),
        ("No shadows. ",
         "The two directional lights do not cast shadows, so the worm does not darken the ground "
         "beneath it. A shadow map would require a second depth pass plus a matrix to project into the "
         "light's view."),
        ("Fog is a post-process. ",
         "It blends the finished colour buffer rather than being part of the shading equation, and it "
         "is linear rather than exponential. For an outdoor scene an exponential-squared falloff looks "
         "more natural."),
        ("Bloom is a fixed-threshold post-process. ",
         "The pipeline is not HDR: the bright pass saturates at 1.0, the threshold is a constant and "
         "the effect is applied after the colour grade, so the brightest areas lose contrast instead "
         "of rolling off. An HDR buffer with an exposure curve and a physically based threshold would "
         "handle highlights better, at the cost of carrying a float render target."),
        ("Finite ground and no level progression. ",
         "The ground plane ends 26 units outside the maze (partly hidden by fog) and the game keeps a "
         "single run per session: reaching the goal generates the next maze but nothing is persisted."),
    ])

    # ---------- 10. 结论 ----------
    doc.add_heading("10. Conclusion", level=1)
    para(doc,
         "The project covers the full mandatory feature list of the handbook with a renderer written "
         "from scratch: transformation matrices, perspective and orthographic projection, "
         "Sutherland-Hodgman near-plane clipping, barycentric rasterisation with a z-buffer, "
         "back-face culling, two-light Lambert shading, perspective-correct texture mapping, a 3D "
         "animation and a 3D particle system, plus three Part B extensions (bilinear filtering, depth fog "
         "and screen-space bloom) and a 55-test suite. The main "
         "engineering lesson is how much of a renderer's behaviour that a GPU hides becomes visible "
         "once it has to be written by hand: the depth-mask bug produced a completely different image "
         "in one camera preset than in another, and the perspective-correct texture mapping was only "
         "convincing after the u/z, v/z, 1/z formulation replaced naive screen-space interpolation. The "
         "main performance lesson is that a CPU rasteriser is fill-rate bound long before it is "
         "triangle-bound, which is why the game renders into a smaller buffer and upscales.")

    # ---------- 附录 ----------
    doc.add_heading("Appendix A - How to run and controls", level=1)
    para(doc,
         "Requirements: Python 3.10+ with numpy, Pillow and pygame(-ce) "
         "(pip install -r requirements.txt); run python main.py or run.bat. The supporting scripts are "
         "bench_render.py (performance table), make_screenshots.py (all figures here, headless), "
         "make_wireframe.py (the two section 16.3 wireframe renders), run_tests.py (unit tests) and "
         "make_video.py (the submission video, needs ffmpeg).")
    table(doc, ["Key", "Action"],
          [["W A S D / arrows", "move (screen-relative: up = into the screen, right = screen right)"],
           ["Space", "jump"],
           ["1 / 2 / 3", "camera preset: chase / top-down / overview"],
           ["P or Tab", "toggle perspective <-> orthographic"],
           ["B or F6", "toggle nearest <-> bilinear texture filtering"],
           ["T or F7", "swap grass/stone for a checkerboard (aliasing demo)"],
           ["F or F8", "toggle the depth fog on/off"],
           ["R or F5", "restart"],
           ["F1 / F2 / F3", "internal resolution 480x300 (default) / 800x500 / 1120x700"],
           ["F12", "screenshot"],
           ["Q / E or mouse drag", "rotate / orbit the camera"],
           ["Esc", "quit"]],
          widths=[4.0, 12.4], caption="Table 6 - Controls. The game starts at 480x300 and scales "
                  "that buffer to the 1280x800 window; the letter keys have IME-proof aliases "
                  "because pygame.key.stop_text_input() is called at start-up. Movement is screen-relative (Camera.ground_basis()); the chase camera never rotates on its own.", font_size=7.0)

    # table() 会在表格后留一个空段落做间距；如果表格刚好排到页底，
    # 这个空段落会被挤到新的一页，生成一张只有页码的空白页。删掉它。
    last = doc.paragraphs[-1]
    if not last.text.strip():
        last._element.getparent().remove(last._element)

    doc.save(OUT)
    print("saved", OUT)


if __name__ == "__main__":
    build()