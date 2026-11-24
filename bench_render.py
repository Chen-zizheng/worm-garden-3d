"""性能基准：用真实迷宫关卡测各画质档 / 投影 / 过滤模式的每帧耗时。

    python bench_render.py            # 默认每个配置渲染 20 帧
    python bench_render.py 40         # 指定帧数
    python bench_render.py --md perf.md

输出既打印到终端，也可以写成 Markdown 表格，直接粘进 README / 技术报告。
测试场景与游戏完全一致（23x15 迷宫 + 9 个水坑 + 4 个苹果 + 3 只鸟 + 粒子），
不依赖 pygame，因此可以在没有显示器的机器上跑。
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "vendor"))
sys.path.insert(0, HERE)

import numpy as np

import config as C
from camera import Camera
from raster import Renderer
from render_scene import draw_world
from world import World

FPS_TARGET = 60.0
QUALITY_NAMES = {0: "480x300 (F1)", 1: "800x500 (F2)", 2: "1120x700 (F3)"}
MODES = [
    ("chase / perspective", 1, "perspective"),
    ("chase / orthographic", 1, "orthographic"),
    ("top-down / perspective", 2, "perspective"),
    ("top-down / orthographic", 2, "orthographic"),
    ("overview / perspective", 3, "perspective"),
    ("overview / orthographic", 3, "orthographic"),
]


def measure(quality, preset, mode, frames, warmup=2, bilinear=False):
    rw, rh = C.QUALITY_PRESETS[quality]
    r = Renderer(rw, rh)
    w = World(seed=7)
    cam = Camera()
    cam.set_preset(preset)
    if mode != cam.mode:
        cam.toggle_projection()
    # 让相机/世界先动起来，避免首帧缓存未命中影响均值
    for _ in range(warmup):
        w.update(1.0 / C.FPS, np.array([1.0, 0.0]), False)
        cam.update(w, 1.0 / C.FPS)
        draw_world(r, w, cam, w.time, bilinear=bilinear)

    times = []
    for i in range(frames):
        w.update(1.0 / C.FPS, np.array([1.0, 0.0]), False)
        cam.update(w, 1.0 / C.FPS)
        t0 = time.perf_counter()
        tri, drawn = draw_world(r, w, cam, w.time, bilinear=bilinear)
        times.append((time.perf_counter() - t0) * 1000.0)
    return dict(quality=quality, preset=preset, mode=mode,
                tris=tri, drawn=drawn,
                mean=float(np.mean(times)), median=float(np.median(times)),
                p95=float(np.percentile(times, 95)),
                min=float(np.min(times)), max=float(np.max(times)))


def main(argv):
    frames = 20
    md_path = None
    for i, a in enumerate(argv):
        if a == "--md":
            md_path = argv[i + 1]
        elif a.isdigit():
            frames = int(a)

    rows = []
    print(f"Worm Garden Adventure 3D - render benchmark ({frames} frames per config)\n")
    header = f"{'config':<26}{'res':<14}{'tris':>7}{'drawn':>7}{'mean ms':>9}{'p95 ms':>8}{'fps':>8}"
    print(header)
    print("-" * len(header))
    for quality in (0, 1, 2):
        for label, preset, mode in MODES:
            res = measure(quality, preset, mode, frames)
            res["label"] = label
            rows.append(res)
            print(f"{label:<26}{QUALITY_NAMES[quality]:<14}{res['tris']:>7}{res['drawn']:>7}"
                  f"{res['mean']:>9.1f}{res['p95']:>8.1f}{1000.0 / res['mean']:>8.1f}")

    # ---- 各后处理/采样特性的单独开销（固定 800x500 追逐视角）----
    print("\nfeature cost (chase / perspective, 800x500):")
    saved = (C.FOG_ENABLED, C.BLOOM_ENABLED, C.TEXTURE_BILINEAR)
    combos = [
        ("flat, no fog, no bloom", False, False, False),
        ("+ depth fog", True, False, False),
        ("+ fog + bloom", True, True, False),
        ("+ fog + bloom + bilinear", True, True, True),
    ]
    variants = []
    for name, fog, bloom, bil in combos:
        C.FOG_ENABLED = fog
        C.BLOOM_ENABLED = bloom
        res = measure(1, 1, "perspective", frames, bilinear=bil)
        res["label"] = name
        res["fog"] = fog
        res["bloom"] = bloom
        res["bilinear"] = bil
        variants.append(res)
        print(f"{name:<28}{res['mean']:>9.1f} ms   p95 {res['p95']:>7.1f} ms"
              f"   {1000.0 / res['mean']:>6.1f} fps")
    C.FOG_ENABLED, C.BLOOM_ENABLED, C.TEXTURE_BILINEAR = saved

    with open(os.path.join(HERE, "bench_results.json"), "w", encoding="utf-8") as f:
        json.dump({"frames_per_config": frames, "camera_speed": "walking east",
                   "scene": "seed 7, level 1, 23x15 maze",
                   "features": {"fog": True, "bloom": True,
                                "bilinear": C.TEXTURE_BILINEAR},
                   "rows": rows, "feature_costs": variants}, f, indent=2)
    print("\nsaved bench_results.json")

    if md_path:
        lines = ["| Camera / projection | Resolution | Triangles | Drawn | Mean ms | FPS |",
                 "|---|---|---|---|---|---|"]
        for res in rows:
            label = f"{res['label']}"
            if res["quality"] == 1:
                lines.append(f"| {label} | {QUALITY_NAMES[res['quality']]} | {res['tris']} | "
                             f"{res['drawn']} | {res['mean']:.1f} | {1000.0 / res['mean']:.1f} |")
        with open(os.path.join(HERE, md_path), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print("saved", md_path)


if __name__ == "__main__":
    main(sys.argv[1:])
