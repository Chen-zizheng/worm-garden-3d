"""
软件光栅化器（纯 NumPy 实现）

渲染管线：
    世界空间 --(视图矩阵)--> 相机空间 --(近平面裁剪)--> 投影 --> 屏幕空间
                                                           |
                                     背面剔除 + 环境光/漫反射 -> 逐像素
                                     重心坐标填充 + 深度缓冲(Z-Buffer)
                                     贴图: u/z、v/z、1/z 透视校正插值
                                     深度雾: 最后基于 Z-Buffer 的全屏后处理

要点：
    * 深度缓冲保证“近处遮挡远处”（手册要求的可见面判定方式）。
    * 贴图采样在“通过深度测试的像素”上做，避免为被遮挡像素付采样开销。
    * 插值公式见手册 Section 10：
          invz = b0/z0 + b1/z1 + b2/z2
          u    = (b0*u0/z0 + b1*u1/z1 + b2*u2/z2) / invz
"""
import numpy as np

F32 = np.float32


def clip_near(tri, near, attrs=None):
    """用平面 z = -near 裁剪相机空间三角形（Sutherland-Hodgman 多边形裁剪）。

    tri   : (3, 3) 相机空间顶点
    attrs : 可选的 (3, k) 顶点属性（纹理坐标），裁剪出的新顶点会线性插值属性
    返回  : attrs 为 None 时返回 0~2 个三角形；否则返回 [(三角形, 属性), ...]
    """
    out_p = []
    out_a = []
    n = len(tri)
    for i in range(n):
        a = tri[i]
        b = tri[(i + 1) % n]
        da = a[2] + near
        db = b[2] + near
        a_in = da <= 0.0
        b_in = db <= 0.0
        if a_in:
            out_p.append(a)
            if attrs is not None:
                out_a.append(attrs[i])
        if a_in != b_in:
            t = da / (da - db)
            out_p.append(a + (b - a) * t)
            if attrs is not None:
                out_a.append(attrs[i] + (attrs[(i + 1) % n] - attrs[i]) * t)
    if len(out_p) < 3:
        return []
    if attrs is None:
        return [np.array([out_p[0], out_p[i], out_p[i + 1]]) for i in range(1, len(out_p) - 1)]
    return [(np.array([out_p[0], out_p[i], out_p[i + 1]]),
             np.array([out_a[0], out_a[i], out_a[i + 1]]))
            for i in range(1, len(out_p) - 1)]


def _box_blur(a, radius, axis):
    """沿指定轴做盒式模糊（edge padding + 前缀和），复杂度与半径无关。

    a      : (..., N, ...) float32
    radius : 模糊半径（像素）
    axis   : 模糊所在的轴
    """
    if radius <= 0:
        return a
    pad = [(0, 0)] * a.ndim
    pad[axis] = (radius, radius)
    padded = np.pad(a, pad, mode="edge")
    cs = np.cumsum(padded, axis=axis, dtype=np.float32)
    zero_shape = list(a.shape)
    zero_shape[axis] = 1
    cs = np.concatenate([np.zeros(zero_shape, np.float32), cs], axis=axis)
    n = a.shape[axis]
    hi = np.arange(n) + 2 * radius + 1
    lo = np.arange(n)
    return ((np.take(cs, hi, axis=axis) - np.take(cs, lo, axis=axis))
            / np.float32(2 * radius + 1))


class Renderer:
    def __init__(self, width, height):
        self.w = int(width)
        self.h = int(height)
        self.color = np.zeros((self.h, self.w, 3), np.float32)
        self.depth = np.full((self.h, self.w), np.inf, np.float32)
        self.tri_count = 0
        self.drawn_count = 0
        # 像素中心坐标缓存：逐三角形算一次 np.arange 太浪费
        self._xs = np.arange(self.w, dtype=F32) + F32(0.5)
        self._ys = np.arange(self.h, dtype=F32) + F32(0.5)
        self.tex_pixels = 0      # 本帧做贴图采样的像素数（用于性能统计）

    # ------------------------------------------------------------------
    # 背景 / 清屏
    # ------------------------------------------------------------------
    def clear(self, sky=None, horizon=None, sun=None, stars=0, star_seed=5):
        """画天空渐变，可选叠加月亮光晕与星星。

        sky/horizon : 天顶 / 地平线颜色；None 用中性的默认蓝天
        sun         : (x, y, sigma, strength, color) 屏幕归一化坐标的圆形光晕
        stars       : 星星数量（画在屏幕上半部，固定种子保证不闪烁）
        """
        if sky is None:
            sky = (0.44, 0.60, 0.82)
        if horizon is None:
            horizon = (0.82, 0.89, 0.96)
        t = np.linspace(0.0, 1.0, self.h, dtype=np.float32)[:, None, None]
        top = np.array(sky, np.float32)
        bot = np.array(horizon, np.float32)
        self.color[:] = top * (1.0 - t) + bot * t
        if stars:
            rng = np.random.default_rng(int(star_seed))
            n = int(stars)
            xs = rng.integers(0, self.w, n)
            ys = rng.integers(0, max(1, int(self.h * 0.5)), n)
            bright = (rng.uniform(0.2, 1.0, n) ** 2.2).astype(np.float32) * 0.9
            np.add.at(self.color, (ys, xs), bright[:, None])
        if sun is not None:
            sx, sy, sigma, strength, col = sun
            gx = (np.arange(self.w, dtype=np.float32) / self.w)[None, :]
            gy = (np.arange(self.h, dtype=np.float32) / self.h)[:, None]
            d2 = (gx - sx) ** 2 * (self.w / self.h) ** 2 + (gy - sy) ** 2
            halo = (np.exp(-d2 / (2.0 * sigma * sigma)) * strength)[..., None]
            self.color += halo * np.array(col, np.float32)
            np.clip(self.color, 0.0, 1.2, out=self.color)
        self.depth.fill(np.inf)
        self.tri_count = 0
        self.drawn_count = 0
        self.tex_pixels = 0

    # ------------------------------------------------------------------
    # 投影
    # ------------------------------------------------------------------
    def project_eye(self, eye_pts, proj):
        """相机空间点 -> (屏幕 x, 屏幕 y, NDC z)。"""
        pts = np.asarray(eye_pts, np.float64)
        h = np.hstack([pts, np.ones((len(pts), 1))])
        clip = h @ proj.T
        w = clip[:, 3]
        w = np.where(np.abs(w) < 1e-9, 1e-9, w)
        ndc = clip[:, :3] / w[:, None]
        sx = (ndc[:, 0] * 0.5 + 0.5) * self.w
        sy = (1.0 - (ndc[:, 1] * 0.5 + 0.5)) * self.h
        return sx, sy, ndc[:, 2]

    # ------------------------------------------------------------------
    # 网格绘制
    # ------------------------------------------------------------------
    def draw_mesh(self, world_verts, faces, colors, view, proj, eye_pos,
                  light_dir, near, ambient=0.35, cull=True, two_sided=False,
                  fill_dir=None, fill_weight=0.34,
                  tex=None, uvs=None, bilinear=False, perspective=True,
                  fog=None):
        """绘制一个网格。

        world_verts : (N,3) 世界空间顶点
        faces       : (F,3) 顶点索引
        colors      : (F,3) 或 (1,3) 基色（贴图网格里当作染色/材质色）
        tex         : (H,W,3) float32 纹理，或 None
        uvs         : (N,2) 每顶点纹理坐标（世界单位 / tile），或 None
        bilinear    : True 用双线性过滤，False 用最近邻
        perspective : 透视投影时为 True（贴图做透视校正）；正交投影为 False
        fog         : 预留参数（雾目前在 draw_world 末尾整屏后处理，见 apply_fog）
        """
        verts = np.asarray(world_verts, np.float64)
        faces = np.asarray(faces, np.int32)
        if len(faces) == 0:
            return
        self.tri_count += len(faces)

        v0 = verts[faces[:, 0]]
        v1 = verts[faces[:, 1]]
        v2 = verts[faces[:, 2]]

        # --- 面法线与朝向（背面剔除依据） ---
        n = np.cross(v1 - v0, v2 - v0)
        ln = np.linalg.norm(n, axis=1)
        ln[ln < 1e-9] = 1e-9
        n = n / ln[:, None]

        centers = (v0 + v1 + v2) / 3.0
        eye = np.asarray(eye_pos, np.float64)
        facing = np.einsum("ij,ij->i", n, eye[None, :] - centers)

        if cull and not two_sided:
            keep = facing > 0.0
        else:
            keep = np.ones(len(faces), dtype=bool)
        if not keep.any():
            return

        # 双面物体的背向面：翻转法线后再算光照
        n_light = n.copy()
        n_light[facing < 0.0] *= -1.0
        light = np.asarray(light_dir, np.float64)
        light = light / max(float(np.linalg.norm(light)), 1e-9)
        fill = np.asarray(fill_dir, np.float64) if fill_dir is not None else np.array(
            [-light[0] * 0.4, 0.35, -light[2] * 0.4])
        fill = fill / max(float(np.linalg.norm(fill)), 1e-9)
        diffuse = np.clip(n_light @ light, 0.0, 1.0)
        fill_d = np.clip(n_light @ fill, 0.0, 1.0)
        shade = ambient + (1.0 - ambient) * np.clip(
            0.80 * diffuse + fill_weight * fill_d, 0.0, 1.0)

        base = np.asarray(colors, np.float32)
        if len(base) == 1 and len(faces) > 1:
            base = np.repeat(base, len(faces), axis=0)
        lit = np.clip(base * shade[:, None], 0.0, 1.0)

        # --- 相机空间 & 近平面分类 ---
        eye_verts = (np.hstack([verts, np.ones((len(verts), 1))]) @ view.T)[:, :3]
        fz = eye_verts[faces][:, :, 2]
        all_behind = np.all(fz > -near, axis=1)
        any_behind = np.any(fz > -near, axis=1)
        fully_front = ~any_behind

        sx, sy, sz = self.project_eye(eye_verts, proj)

        # 先把“三角形在屏幕外”的情况整批剔除，避免逐三角形的 Python/numpy 调用开销
        fx = sx[faces]
        fy = sy[faces]
        off = ((fx.max(axis=1) < -1.0) | (fx.min(axis=1) > self.w + 1.0) |
               (fy.max(axis=1) < -1.0) | (fy.min(axis=1) > self.h + 1.0))
        main_idx = np.nonzero(keep & fully_front & ~off)[0]
        clip_idx = np.nonzero(keep & any_behind)[0]

        textured = tex is not None and uvs is not None
        if textured:
            tex_flat = np.ascontiguousarray(tex, dtype=np.float32).reshape(-1, 3)
            th, tw = tex.shape[0], tex.shape[1]
            uv = np.asarray(uvs, np.float32)
            # 每顶点 1/z：透视校正用。正交投影下 1/z 不是屏幕空间线性量，
            # 手册也说明正交投影直接用 uv 线性插值即可，这里取 iz = 1。
            if perspective:
                zw = eye_verts[:, 2]
                iz_all = np.where(np.abs(zw) < 1e-9, 1e9, -1.0 / zw).astype(np.float32)
            else:
                iz_all = np.ones(len(verts), np.float32)
            qu_all = uv[:, 0] * iz_all
            qv_all = uv[:, 1] * iz_all

        sxl = sx.tolist()
        syl = sy.tolist()
        szl = sz.tolist()
        faces_l = faces.tolist()
        if textured:
            uvl = uv.tolist()
            izl = iz_all.tolist()
            qul = qu_all.tolist()
            qvl = qv_all.tolist()
            litl = lit.tolist()

        for fi in main_idx:
            i0, i1, i2 = faces_l[fi]
            if textured:
                q = (qul[i0], qvl[i0], qul[i1], qvl[i1], qul[i2], qvl[i2],
                     izl[i0], izl[i1], izl[i2])
                self._raster_tri_tex(
                    sxl[i0], syl[i0], szl[i0],
                    sxl[i1], syl[i1], szl[i1],
                    sxl[i2], syl[i2], szl[i2], litl[fi], q,
                    tex_flat, tw, th, bilinear)
            else:
                self._raster_tri(
                    sxl[i0], syl[i0], szl[i0],
                    sxl[i1], syl[i1], szl[i1],
                    sxl[i2], syl[i2], szl[i2], lit[fi])

        if len(clip_idx) and textured:
            for fi in clip_idx:
                i0, i1, i2 = faces[fi]
                tri_eye = eye_verts[[i0, i1, i2]]
                tri_uv = uv[[i0, i1, i2]]
                for poly, poly_uv in clip_near(tri_eye, near, tri_uv):
                    px, py, pz = self.project_eye(poly, proj)
                    if perspective:
                        iz = np.where(np.abs(poly[:, 2]) < 1e-9, 1e9,
                                      -1.0 / poly[:, 2]).astype(np.float32)
                    else:
                        iz = np.ones(3, np.float32)
                    q = tuple((poly_uv[:, 0] * iz).tolist()) + tuple((poly_uv[:, 1] * iz).tolist()) + tuple(iz.tolist())
                    self._raster_tri_tex(
                        px[0], py[0], pz[0], px[1], py[1], pz[1], px[2], py[2], pz[2],
                        lit[fi], q, tex_flat, tw, th, bilinear)
        elif len(clip_idx):
            for fi in clip_idx:
                i0, i1, i2 = faces[fi]
                tri_eye = eye_verts[[i0, i1, i2]]
                for poly in clip_near(tri_eye, near):
                    px, py, pz = self.project_eye(poly, proj)
                    self._raster_tri(
                        px[0], py[0], pz[0],
                        px[1], py[1], pz[1],
                        px[2], py[2], pz[2], lit[fi])

    # ------------------------------------------------------------------
    def _bbox(self, x0, y0, x1, y1, x2, y2):
        """整数包围盒（已裁剪到屏幕内），完全在屏幕外时返回 None。"""
        W, H = self.w, self.h
        minx = int(min(x0, x1, x2))
        maxx = int(max(x0, x1, x2)) + 1
        miny = int(min(y0, y1, y2))
        maxy = int(max(y0, y1, y2)) + 1
        if maxx <= 0 or minx >= W or maxy <= 0 or miny >= H:
            return None
        if minx < 0:
            minx = 0
        if miny < 0:
            miny = 0
        if maxx > W:
            maxx = W
        if maxy > H:
            maxy = H
        if minx >= maxx or miny >= maxy:
            return None
        return minx, miny, maxx, maxy

    def _raster_tri(self, x0, y0, z0, x1, y1, z1, x2, y2, z2, col):
        """纯色三角形：重心坐标填充 + 深度测试。"""
        bb = self._bbox(x0, y0, x1, y1, x2, y2)
        if bb is None:
            return
        minx, miny, maxx, maxy = bb

        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if -1e-9 < area < 1e-9:
            return

        f32 = F32
        inv = 1.0 / area
        xs = self._xs[minx:maxx]
        ys = self._ys[miny:maxy]
        # 归一化重心坐标是屏幕空间线性的：b_i = a_i*x + q_i*y + c_i。
        # 拆成“行向量 + 列向量 + 外积”只需 1 次二维加法。
        a0 = (y1 - y2) * inv
        q0 = (x2 - x1) * inv
        c0 = -(a0 * x2 + q0 * y2)
        a1 = (y2 - y0) * inv
        q1 = (x0 - x2) * inv
        c1 = -(a1 * x2 + q1 * y2)
        rx = xs * f32(a0)
        rx += f32(c0)
        ry = ys * f32(q0)
        b0 = rx[None, :] + ry[:, None]
        rx = xs * f32(a1)
        rx += f32(c1)
        ry = ys * f32(q1)
        b1 = rx[None, :] + ry[:, None]

        inside = b0 >= f32(0.0)
        inside &= b1 >= f32(0.0)
        np.add(b0, b1, out=b0)          # 借 b0 缓冲区算 b0+b1
        inside &= b0 <= f32(1.0)
        np.subtract(b0, b1, out=b0)     # 还原 b0
        if not inside.any():
            return

        self.drawn_count += 1
        np.multiply(b0, f32(z0 - z2), out=b0)
        np.multiply(b1, f32(z1 - z2), out=b1)
        b0 += b1
        b0 += f32(z2)
        z = b0

        depth = self.depth[miny:maxy, minx:maxx]
        mask = np.less(z, depth) & inside
        if not mask.any():
            return
        np.copyto(depth, z, where=mask)
        np.copyto(self.color[miny:maxy, minx:maxx], col, where=mask[..., None])

    def _raster_tri_tex(self, x0, y0, z0, x1, y1, z1, x2, y2, z2, col, q,
                        tex_flat, tw, th, bilinear):
        """贴图三角形：透视校正的 u/z、v/z、1/z 插值 + 最近邻/双线性采样。"""
        bb = self._bbox(x0, y0, x1, y1, x2, y2)
        if bb is None:
            return
        minx, miny, maxx, maxy = bb

        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if -1e-9 < area < 1e-9:
            return

        f32 = F32
        inv = 1.0 / area
        xs = self._xs[minx:maxx]
        ys = self._ys[miny:maxy]
        a0 = (y1 - y2) * inv
        q0 = (x2 - x1) * inv
        c0 = -(a0 * x2 + q0 * y2)
        a1 = (y2 - y0) * inv
        q1 = (x0 - x2) * inv
        c1 = -(a1 * x2 + q1 * y2)
        rx = xs * f32(a0)
        rx += f32(c0)
        ry = ys * f32(q0)
        b0 = rx[None, :] + ry[:, None]
        rx = xs * f32(a1)
        rx += f32(c1)
        ry = ys * f32(q1)
        b1 = rx[None, :] + ry[:, None]

        inside = b0 >= f32(0.0)
        inside &= b1 >= f32(0.0)
        np.add(b0, b1, out=b1)          # b1 <- b0+b1
        inside &= b1 <= f32(1.0)
        np.subtract(b1, b0, out=b1)     # 还原 b1
        if not inside.any():
            return

        # 深度（这里用屏幕空间线性的相机 z 做深度测试，与纯色路径一致）
        z = b0 * f32(z0 - z2)
        z += b1 * f32(z1 - z2)
        z += f32(z2)
        depth = self.depth[miny:maxy, minx:maxx]
        mask = np.less(z, depth) & inside
        if not mask.any():
            return
        self.drawn_count += 1
        np.copyto(depth, z, where=mask)

        qu0, qv0, qu1, qv1, qu2, qv2, iz0, iz1, iz2 = q
        b0m = b0[mask]
        b1m = b1[mask]
        n = len(b0m)
        iwm = b0m * f32(iz0 - iz2)
        iwm += b1m * f32(iz1 - iz2)
        iwm += f32(iz2)
        u = b0m * f32(qu0 - qu2)
        u += b1m * f32(qu1 - qu2)
        u += f32(qu2)
        v = b0m * f32(qv0 - qv2)
        v += b1m * f32(qv1 - qv2)
        v += f32(qv2)
        np.reciprocal(iwm, out=iwm)
        u *= iwm
        v *= iwm

        if bilinear:
            fu = u * tw
            fv = v * th
            ix = fu.astype(np.int32)
            iy = fv.astype(np.int32)
            fx = fu - ix
            fy = fv - iy
            ix &= tw - 1
            iy &= th - 1
            ix1 = (ix + 1) & (tw - 1)
            iy1 = (iy + 1) & (th - 1)
            fx = fx[:, None]
            fy = fy[:, None]
            r0 = iy * tw
            r1 = iy1 * tw
            c00 = tex_flat[r0 + ix]
            c10 = tex_flat[r0 + ix1]
            c01 = tex_flat[r1 + ix]
            c11 = tex_flat[r1 + ix1]
            top = c00 + (c10 - c00) * fx
            bot = c01 + (c11 - c01) * fx
            rgb = top + (bot - top) * fy
        else:
            tx = (u * tw).astype(np.int32)
            ty = (v * th).astype(np.int32)
            tx &= tw - 1
            ty &= th - 1
            tx += ty * tw
            rgb = tex_flat.take(tx, axis=0)

        self.tex_pixels += n
        np.multiply(rgb, col, out=rgb)
        np.clip(rgb, 0.0, 1.0, out=rgb)
        self.color[miny:maxy, minx:maxx][mask] = rgb

    # ------------------------------------------------------------------
    # 深度雾（后处理）
    # ------------------------------------------------------------------
    def apply_fog(self, start, end, fog_color, near=None, far=None,
                  perspective=True, distance_offset=0.0):
        """按 Z-Buffer 换算出的“相机空间距离”把颜色混合到雾色。

        Z-Buffer 里存的是 NDC 深度（非线性），这里用投影矩阵的逆变换还原成
        沿视线方向的距离 d = -z_eye，再做 start/end 线性雾。
        天空像素 depth = inf -> 距离取 0，雾系数 0，自然不受影响。
        """
        depth = self.depth
        if near is not None and far is not None:
            a = (float(far) + float(near)) / (float(near) - float(far))
            b = 2.0 * float(far) * float(near) / (float(near) - float(far))
            if perspective:
                with np.errstate(divide="ignore", invalid="ignore"):
                    dist = F32(b) / (depth + F32(a))
            else:
                dist = (depth * F32(float(far) - float(near))
                        + F32(float(far) + float(near))) * 0.5
        else:
            dist = -depth
        dist = np.where(np.isfinite(depth), dist, F32(0.0)).astype(F32, copy=False)
        # 正交模式把眼睛沿视线后移了 ORTHO_EYE_BACK，雾要用“离真实眼睛的距离”
        if distance_offset:
            dist = dist - F32(distance_offset)
        f = dist
        f -= F32(start)
        f *= F32(1.0 / max(float(end) - float(start), 1e-6))
        np.clip(f, 0.0, 1.0, out=f)
        fog = np.asarray(fog_color, np.float32)
        f = f[..., None]
        self.color *= (1.0 - f)
        self.color += fog * f

    # ------------------------------------------------------------------
    # 全屏后处理（Part B 扩展 2/3）
    # ------------------------------------------------------------------
    def apply_bloom(self, threshold=0.55, radius=10, strength=0.55, scale=4):
        """屏幕空间 bloom：亮部降采样 -> 盒式模糊 -> 加回原图。

        只对超过阈值的像素做模糊，所以天空、暗部不会被整体提亮；
        苹果/荧光虫/月亮这类高亮物体周围会出现柔和光晕。
        降采样到 1/scale 分辨率再做模糊，开销基本与分辨率无关。
        """
        if strength <= 0.0:
            return
        c = self.color
        h, w = c.shape[:2]
        scale = max(1, int(scale))
        sh = max(1, h // scale)
        sw = max(1, w // scale)
        hs, ws = sh * scale, sw * scale
        # 先降采样再做亮部提取：全分辨率上只做一次求均值，
        # 阈值/模糊都在 1/scale 的小图上完成（这里 1/4 -> 像素数少 16 倍）。
        small = c[:hs, :ws].reshape(sh, scale, sw, scale, 3).mean(axis=(1, 3))
        lum = small.max(axis=2)
        mask = lum - np.float32(threshold)
        mask *= np.float32(1.0 / max(1e-6, 1.0 - threshold))
        np.clip(mask, 0.0, 1.0, out=mask)
        small *= mask[..., None]
        r = max(1, int(radius))
        small = _box_blur(small, r, axis=1)
        small = _box_blur(small, r, axis=2)
        halo = small.repeat(scale, axis=0).repeat(scale, axis=1)
        c[:hs, :ws] += halo * np.float32(strength)
        np.clip(c, 0.0, 1.0, out=c)

    def apply_vignette(self, strength=0.5):
        """屏幕四周压暗（模拟镜头暗角），让视线集中在中部。"""
        if strength <= 0.0:
            return
        h, w = self.color.shape[:2]
        yy = (np.arange(h, dtype=np.float32) - h / 2) / (h / 2)
        xx = (np.arange(w, dtype=np.float32) - w / 2) / (w / 2)
        r2 = yy[:, None] ** 2 * 0.7 + xx[None, :] ** 2
        self.color *= np.clip(1.0 - strength * r2, 0.0, 1.0)[..., None]

    def apply_grade(self, gains):
        """整体通道增益（调色），最后一步。"""
        self.color *= np.asarray(gains, np.float32)[None, None, :]
        np.clip(self.color, 0.0, 1.0, out=self.color)

    # ------------------------------------------------------------------
    def to_image(self):
        return (np.clip(self.color, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
