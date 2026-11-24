"""渲染入口：静态场景缓存 + 动态物体 + 相机矩阵 + 纹理/雾。"""
import numpy as np

import assets
import config as C
import math3d as m3
import scene


_textures = None


def textures():
    """懒加载所有纹理（第一次渲染时读 PNG，之后复用）。"""
    global _textures
    if _textures is None:
        _textures = assets.load_textures()
    return _textures


def get_static(world):
    """静态几何体按“关卡代次”缓存，关卡重建后自动失效。"""
    key = world.generation
    cache = getattr(world, "_static_cache", None)
    if cache is not None and cache[0] == key:
        return cache[1]
    meshes = scene.build_static(world)
    world._static_cache = (key, meshes)
    return meshes


def draw_world(renderer, world, camera, t, bilinear=None, checker=False, bloom=None):
    """绘制一帧。

    bilinear : True = 双线性过滤，False = 最近邻；None 用 C.TEXTURE_BILINEAR
    checker  : True 时把草地/石墙换成棋盘纹理（用来演示过滤与走样差异）
    bloom    : True/False 强制开关 bloom；None 用 C.BLOOM_ENABLED
    """
    if bilinear is None:
        bilinear = C.TEXTURE_BILINEAR
    if bloom is None:
        bloom = C.BLOOM_ENABLED
    static_meshes = get_static(world)
    view = camera.view_matrix()
    proj = camera.proj_matrix(renderer.w / renderer.h)
    light = m3.normalize(C.LIGHT_DIR)
    perspective = (camera.mode == "perspective")
    tex_map = textures()

    # 天空由 config 的美术方向驱动：渐变 + 月亮光晕 + 星星
    renderer.clear(C.SKY_TOP, C.SKY_HORIZON, sun=C.MOON, stars=C.STARS,
                   star_seed=C.STAR_SEED)
    kwargs = dict(ambient=C.AMBIENT, fill_dir=C.FILL_DIR, fill_weight=C.FILL_WEIGHT,
                  bilinear=bilinear, perspective=perspective)

    def _draw(mesh):
        name = mesh.get("tex")
        if checker and name in ("grass", "stone"):
            name = "checker"
        tex = tex_map.get(name) if name else None
        renderer.draw_mesh(mesh["verts"], mesh["faces"], mesh["colors"],
                           view, proj, camera.eye, light, C.NEAR,
                           cull=mesh["cull"], two_sided=mesh["two_sided"],
                           tex=tex, uvs=(mesh.get("uvs") if tex is not None else None),
                           **kwargs)

    for mesh in static_meshes:
        _draw(mesh)
    for mesh in scene.build_dynamic(world, t, camera.right, camera.up):
        _draw(mesh)

    if C.FOG_ENABLED:
        renderer.apply_fog(C.FOG_START, C.FOG_END, C.FOG_COLOR,
                           near=C.NEAR, far=(C.FAR if perspective
                                             else camera.ORTHO_EYE_BACK + C.FAR),
                           perspective=perspective,
                           distance_offset=(0.0 if perspective
                                            else camera.ORTHO_EYE_BACK))
    # 屏幕空间后处理：bloom -> 调色 -> 暗角
    if bloom:
        renderer.apply_bloom(C.BLOOM_THRESHOLD, C.BLOOM_RADIUS,
                             C.BLOOM_STRENGTH, C.BLOOM_SCALE)
    renderer.apply_grade(C.GRADE)
    renderer.apply_vignette(C.VIGNETTE)
    return renderer.tri_count, renderer.drawn_count
