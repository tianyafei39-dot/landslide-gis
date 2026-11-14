# -*- coding: utf-8 -*-
"""
GIS 预处理工具：
- 栅格读取 / 对齐校验
- 正样本（灾害点）+ 负样本（研究区内随机点）自动采样
- 易发性栅格保存
"""

import importlib

try:
    # Import dynamically so editors without the optional GIS dependency installed
    # can still load this module; rasterio is required when GIS functions run.
    rasterio = importlib.import_module("rasterio")
except ModuleNotFoundError as exc:
    if exc.name != "rasterio":
        raise
    raise ModuleNotFoundError(
        "缺少 rasterio 依赖，请在当前 Python 环境中运行: pip install rasterio"
    ) from exc
import geopandas as gpd
import numpy as np
import os
from typing import Optional
from shapely.geometry import Point
from rasterio.features import geometry_mask
from sklearn.neighbors import NearestNeighbors


# ----------------------------------------------------------------------
# 1. 栅格读取
# ----------------------------------------------------------------------
def read_raster(raster_path):
    """
    读取单波段栅格。
    返回：arr(float32), profile, transform, crs, nodata
    """
    with rasterio.open(raster_path) as src:
        arr = src.read(1).astype(np.float32)
        profile = src.profile
        transform = src.transform
        crs = src.crs
        nodata = src.nodata

    # 把文件声明为 nodata 的值也置为 NaN，便于后续统一处理
    if nodata is not None:
        arr = np.where(arr == nodata, np.nan, arr)
    return arr, profile, transform, crs, nodata


# ----------------------------------------------------------------------
# 2. 栅格对齐校验
# ----------------------------------------------------------------------
def check_rasters_aligned(factor_paths):
    """校验所有因子栅格 shape / transform / crs 是否一致"""
    if not factor_paths:
        raise ValueError("未提供因子栅格文件，请上传 tif 或在请求中传入 factor_files")
    ref = None
    ref_name = ""
    for fp in factor_paths:
        if not os.path.exists(fp):
            raise FileNotFoundError(f"栅格文件不存在: {fp}")
        with rasterio.open(fp) as src:
            if src.crs is None:
                raise ValueError(f"栅格缺少 CRS 投影信息: {os.path.basename(fp)}")
            info = (src.shape, src.transform, src.crs)
        if ref is None:
            ref = info
            ref_name = os.path.basename(fp)
        elif info != ref:
            raise ValueError(
                f"栅格未对齐：{os.path.basename(fp)} "
                f"(shape={info[0]}, crs={info[2]}) 与参考栅格 "
                f"{ref_name} (shape={ref[0]}, crs={ref[2]}) 不一致。"
                f"请确保所有因子使用相同的行列数、像元大小与投影。"
            )
    return True


# ----------------------------------------------------------------------
# 3. 有效像元掩膜
# ----------------------------------------------------------------------
def _raster_valid_mask(factor_paths, study_area_gdf=None,
                       ref_transform=None, ref_shape=None):
    """
    生成有效像元掩膜（True=有效）：
    - 所有因子在该像元均非 nodata、非 NaN
    - 若给定研究区矢量面，则像元须落在研究区内
    """
    if ref_shape is None:
        with rasterio.open(factor_paths[0]) as src:
            ref_shape = src.shape

    valid = np.ones(ref_shape, dtype=bool)

    for fp in factor_paths:
        arr, _, _, _, _ = read_raster(fp)
        valid &= ~np.isnan(arr)

    if study_area_gdf is not None:
        geoms = [g for g in study_area_gdf.geometry if g is not None and not g.is_empty]
        inside = geometry_mask(
            geoms,
            out_shape=ref_shape,
            transform=ref_transform,
            invert=True,       # invert=True → 区内为 True
        )
        valid &= inside

    return valid


# ----------------------------------------------------------------------
# 4. 从掩膜中随机采样行列号
# ----------------------------------------------------------------------
def _sample_points_from_mask(mask, n, rng,
                             exclude_rc=None, min_dist=0):
    """
    从 mask=True 的像元中随机采样 n 个 (row, col)
    - exclude_rc : 需排除的 (row, col) 集合（如正样本）
    - min_dist   : 与排除点的最小像元距离（0 表示不约束）
    """
    rows, cols = np.where(mask)
    if len(rows) == 0:
        return []

    idx = rng.permutation(len(rows))
    rows, cols = rows[idx], cols[idx]

    if exclude_rc is None or len(exclude_rc) == 0:
        return list(zip(rows[:n], cols[:n]))

    excl = np.array(list(exclude_rc))
    nn = NearestNeighbors(n_neighbors=1).fit(excl)

    selected = []
    for r, c in zip(rows, cols):
        if min_dist > 0:
            d, _ = nn.kneighbors(np.array([[r, c]]), return_distance=True)
            if d[0][0] < min_dist:
                continue
        selected.append((r, c))
        if len(selected) >= n:
            break
    return selected


# ----------------------------------------------------------------------
# 5. 自动构建正负样本训练集
# ----------------------------------------------------------------------
def sample_points_auto_label(
    factor_paths: list,
    landslide_shp: str,
    study_area_shp: Optional[str] = None,
    neg_ratio: float = 3.0,
    min_dist_pixels: int = 3,
    random_state: int = 42,
    study_area_buffer: float = 0.0,
):
    """
    自动构建训练集：
    - 正样本：landslide_shp 中所有落在研究区内、且因子栅格有效的点
    - 负样本：研究区内、避开正样本、因子有效的随机点
    - 负样本数量 = 正样本数 * neg_ratio（默认 3.0）

    返回
    ----
    X : ndarray (N, F)
    y : ndarray (N,)  1=滑坡, 0=非滑坡
    """
    check_rasters_aligned(factor_paths)
    rng = np.random.default_rng(random_state)

    # 参考栅格信息
    ref_arr, ref_profile, ref_transform, ref_crs, _ = read_raster(factor_paths[0])
    h, w = ref_arr.shape

    # 读取矢量并统一 CRS
    gdf_pts = gpd.read_file(landslide_shp).to_crs(ref_crs)
    gdf_area = None
    if study_area_shp:
        gdf_area = gpd.read_file(study_area_shp).to_crs(ref_crs)
        # 可选：研究区向内缓冲
        if study_area_buffer and study_area_buffer > 0:
            gdf_area = gdf_area.copy()
            gdf_area["geometry"] = gdf_area.geometry.buffer(-study_area_buffer)

    # 读取全部因子
    factor_arrays = [read_raster(fp)[0] for fp in factor_paths]

    # 有效像元掩膜（含研究区约束）
    valid_mask = _raster_valid_mask(
        factor_paths,
        study_area_gdf=gdf_area,
        ref_transform=ref_transform,
        ref_shape=(h, w),
    )

    # ---------- 正样本 ----------
    pos_rc, pos_feat, pos_label = [], [], []
    for geom in gdf_pts.geometry:
        if geom is None or geom.is_empty:
            continue
        if geom.geom_type != "Point":
            geom = geom.centroid
        row, col = rasterio.transform.rowcol(ref_transform, geom.x, geom.y)
        row = int(np.asarray(row).reshape(-1)[0])
        col = int(np.asarray(col).reshape(-1)[0])
        if not (0 <= row < h and 0 <= col < w):
            continue
        if not valid_mask[row, col]:
            continue
        vals = [fa[row, col] for fa in factor_arrays]
        if any(np.isnan(v) for v in vals):
            continue
        pos_rc.append((row, col))
        pos_feat.append(vals)
        pos_label.append(1)

    n_pos = len(pos_feat)
    if n_pos == 0:
        raise RuntimeError("没有可用正样本点，请检查灾害点是否落在研究区/因子范围内。")

    # ---------- 负样本 ----------
    neg_mask = valid_mask.copy()
    for r, c in pos_rc:
        neg_mask[r, c] = False

    n_neg = int(round(n_pos * neg_ratio))
    neg_rc = _sample_points_from_mask(
        neg_mask, n_neg, rng,
        exclude_rc=set(pos_rc), min_dist=min_dist_pixels,
    )
    if len(neg_rc) < n_neg:
        print(f"[警告] 负样本仅采样到 {len(neg_rc)} 个（目标 {n_neg} 个），"
              f"请检查研究区大小或 min_dist_pixels 设置。")

    neg_feat = [[fa[r, c] for fa in factor_arrays] for r, c in neg_rc]
    neg_label = [0] * len(neg_feat)

    X = np.array(pos_feat + neg_feat, dtype=np.float32)
    y = np.array(pos_label + neg_label, dtype=np.int32)

    print(f"[采样完成] 正样本 {n_pos} 个, 负样本 {len(neg_feat)} 个, 共 {len(y)} 个")
    return X, y


# ----------------------------------------------------------------------
# 6. 保存预测栅格
# ----------------------------------------------------------------------
def save_prediction_raster(ref_profile, pred_arr, out_tif_path):
    """把预测结果写入 GeoTIFF（float32 单波段，NaN 作为 nodata）"""
    profile = ref_profile.copy()
    profile.update(dtype=rasterio.float32, count=1, nodata=np.nan)
    with rasterio.open(out_tif_path, "w", **profile) as dst:
        dst.write(pred_arr.astype(np.float32), 1)
    return out_tif_path