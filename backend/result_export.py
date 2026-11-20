# -*- coding: utf-8 -*-
"""
训练结果后处理：
- 将投影坐标系（如 EPSG:32647）下的易发性栅格重投影到 WGS84，并渲染为带透明背景的 PNG
- 输出图例阈值、分级统计、经纬度边界，供 Leaflet ImageOverlay 精确叠加
- 导出灾害点 / 研究区 GeoJSON
- 空间正确性校验（投影、边界、坐标往返、风险分布）
"""

import os
import json
import hashlib
import numpy as np
import rasterio
from rasterio.warp import (
    calculate_default_transform,
    reproject,
    transform_bounds,
    Resampling,
)
from rasterio.transform import array_bounds
from rasterio.features import geometry_mask
from rasterio.windows import Window
from pyproj import Transformer
import geopandas as gpd
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULT_DIR = os.path.join(BASE_DIR, "result")
os.makedirs(RESULT_DIR, exist_ok=True)

WGS84 = "EPSG:4326"
MAX_PNG_WIDTH = 1600

# 5 级易发性分级（固定阈值，保证分级范围不偏移）
BREAKS = [0.2, 0.4, 0.6, 0.8]
CLASSES = [
    {"key": "very_low", "name": "极低易发", "min": 0.0, "max": 0.2, "color": "#2c7bb6"},
    {"key": "low", "name": "低易发", "min": 0.2, "max": 0.4, "color": "#7fcdbb"},
    {"key": "moderate", "name": "中易发", "min": 0.4, "max": 0.6, "color": "#ffffb2"},
    {"key": "high", "name": "高易发", "min": 0.6, "max": 0.8, "color": "#fdae61"},
    {"key": "very_high", "name": "极高易发", "min": 0.8, "max": 1.0, "color": "#d7191c"},
]

# 连续渐变色带锚点（位置相同，颜色在相邻锚点间线性插值）
GRADIENT_STOPS = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
GRADIENT_COLORS = ["#2c7bb6", "#7fcdbb", "#ffffb2", "#fdae61", "#d7191c", "#7f0000"]

# 因子栅格通用色带（viridis 风格，归一化到数据 2%~98% 分位以增强对比）
FACTOR_STOPS = [0.0, 0.25, 0.5, 0.75, 1.0]
FACTOR_COLORS = ["#440154", "#3b528b", "#21918c", "#5ec962", "#fde725"]

# 各等级对应的建议话术（key 与 CLASSES 一一对应）
RISK_ADVICE = {
    "very_low":  "建议保持正常监管即可。",
    "low":       "建议保持关注，留意天气变化。",
    "moderate":  "建议重点排查陡坡、沟谷区段，跟踪预警信息。",
    "high":      "建议列为重点防范区域，加密日常巡查频次。",
    "very_high": "建议加密巡查监测，做好避险转移准备，发现险情及时上报。",
}


# ---------------------------------------------------------------- 工具函数

def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _class_index(values):
    """按固定阈值分级，返回 0~4"""
    return np.clip(np.digitize(values, BREAKS, right=False), 0, len(CLASSES) - 1)


def classify_value(value):
    """单个数值 -> 分级信息"""
    if value is None or not np.isfinite(value):
        return None
    idx = int(np.clip(np.digitize([value], BREAKS, right=False)[0], 0, len(CLASSES) - 1))
    return {**CLASSES[idx], "value": round(float(value), 4)}

def format_risk_message(value, lng=None, lat=None):
    """把点击点的风险值拼成一句话，供弹窗直接展示。"""
    info = classify_value(value)
    if info is None:
        return "该点暂无有效风险数据（可能位于研究区外或无数据区域）。"

    v = float(np.clip(value, 0.0, 1.0))
    msg = f"该点风险值为{v:.2f}，属于{info['name']}，{RISK_ADVICE[info['key']]}"

    if lng is not None and lat is not None:
        msg = f"（{lng:.5f}, {lat:.5f}）" + msg
    return msg


# ---------------------------------------------------------------- 渲染函数
def _colorize(arr):
    """连续渐变色带渲染 -> RGBA（无效像元透明）"""
    h, w = arr.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    valid = np.isfinite(arr)
    if valid.any():
        stops = np.array(GRADIENT_STOPS, dtype=np.float64)
        cols = np.array([_hex_to_rgb(c) for c in GRADIENT_COLORS], dtype=np.float64)
        vals = np.clip(arr[valid], 0.0, 1.0)
        for i in range(3):
            rgba[..., i][valid] = np.interp(vals, stops, cols[:, i]).astype(np.uint8)
        rgba[..., 3][valid] = 255
    return rgba, valid


def _reproject_to_wgs84(src, src_arr):
    """投影栅格 -> WGS84(EPSG:4326) 等经纬网格，返回 (重投影数组, (w,s,e,n), (宽,高))。

    输出 PNG 的每行对应等纬度、每列对应等经度，行列号与经纬度严格线性关系，
    Leaflet ImageOverlay 在经纬度 bounds 内线性贴图时与数据同构，
    与同样为 EPSG:4326 的灾害点 GeoJSON 像素级对齐，不存在墨卡托非线性拉伸。
    """
    dst_transform, dst_w, dst_h = calculate_default_transform(
        src.crs, WGS84, src.width, src.height, *src.bounds
    )
    if dst_w > MAX_PNG_WIDTH:
        scale = MAX_PNG_WIDTH / float(dst_w)
        dst_w = MAX_PNG_WIDTH
        dst_h = max(1, int(round(dst_h * scale)))
        dst_transform, dst_w, dst_h = calculate_default_transform(
            src.crs, WGS84, src.width, src.height, *src.bounds,
            dst_width=dst_w, dst_height=dst_h,
        )

    dst_arr = np.full((dst_h, dst_w), np.nan, dtype=np.float32)
    reproject(
        source=src_arr,
        destination=dst_arr,
        src_transform=src.transform,
        src_crs=src.crs,
        dst_transform=dst_transform,
        dst_crs=WGS84,
        resampling=Resampling.nearest,
        src_nodata=np.nan,
        dst_nodata=np.nan,
    )
    # dst 本身就是经纬度网格，边界直接取，不再经过任何二次投影/ densify
    west, south, east, north = array_bounds(dst_h, dst_w, dst_transform)
    return dst_arr, (west, south, east, north), (dst_w, dst_h)


def _colorize_factor(arr):
    """因子栅格渲染：按 2%~98% 分位归一化后套用 viridis 风格色带"""
    h, w = arr.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    valid = np.isfinite(arr)
    if valid.any():
        lo, hi = np.nanpercentile(arr[valid], [2, 98])
        if hi <= lo:
            hi = lo + 1e-6
        t = np.clip((arr[valid] - lo) / (hi - lo), 0.0, 1.0)
        stops = np.array(FACTOR_STOPS, dtype=np.float64)
        cols = np.array([_hex_to_rgb(c) for c in FACTOR_COLORS], dtype=np.float64)
        for i in range(3):
            rgba[..., i][valid] = np.interp(t, stops, cols[:, i]).astype(np.uint8)
        rgba[..., 3][valid] = 255
    return rgba


# ----------------------------------------------------------------------
# 1. 易发性栅格 -> 经纬度 PNG + 边界 / 图例 / 分级统计
# ----------------------------------------------------------------------
def export_web_overlay(task_id, tif_path):
    with rasterio.open(tif_path) as src:
        if src.crs is None:
            raise ValueError("结果栅格缺少 CRS 投影信息，无法进行 Web 渲染")

        src_arr = src.read(1).astype(np.float32)
        if src.nodata is not None and np.isfinite(src.nodata):
            src_arr = np.where(src_arr == src.nodata, np.nan, src_arr)
        src_arr[~np.isfinite(src_arr)] = np.nan

        # 重投影到 WGS84 等经纬网格：PNG 行列与经纬度线性对应，
        # Leaflet ImageOverlay 线性贴图时与灾害点 GeoJSON(4326) 严格对齐
        dst_arr, (west, south, east, north), (dst_w, dst_h) = _reproject_to_wgs84(src, src_arr)
        rgba, valid = _colorize(dst_arr)

        png_name = f"susceptibility_{task_id}.png"
        png_path = os.path.join(RESULT_DIR, png_name)
        Image.fromarray(rgba, mode="RGBA").save(png_path, optimize=True)

        # 分级统计基于原始投影栅格，避免重采样造成统计偏差
        finite = np.isfinite(src_arr)
        total = int(finite.sum())
        stats = []
        if total:
            idx = _class_index(src_arr[finite])
            for i, c in enumerate(CLASSES):
                cnt = int((idx == i).sum())
                stats.append({
                    **c,
                    "count": cnt,
                    "percent": round(100.0 * cnt / total, 2),
                })
            vals = src_arr[finite]
            value_stats = {
                "min": round(float(np.min(vals)), 4),
                "max": round(float(np.max(vals)), 4),
                "mean": round(float(np.mean(vals)), 4),
                "total_pixels": total,
            }
        else:
            value_stats = {"min": 0, "max": 0, "mean": 0, "total_pixels": 0}

        return {
            "png_url": f"/static/{png_name}",
            "tif_url": f"/static/{os.path.basename(tif_path)}",
            "bounds": {
                "west": round(float(west), 7),
                "south": round(float(south), 7),
                "east": round(float(east), 7),
                "north": round(float(north), 7),
            },
            "size": {"width": dst_w, "height": dst_h},
            "crs": str(src.crs),
            "source_shape": [src.height, src.width],
            "pixel_size": [round(abs(src.transform.a), 3), round(abs(src.transform.e), 3)],
            "legend": {
                "breaks": BREAKS,
                "classes": CLASSES,
                "gradient": {
                    "stops": GRADIENT_STOPS,
                    "colors": GRADIENT_COLORS,
                },
            },
            "class_stats": stats,
            "value_stats": value_stats,
        }


# ----------------------------------------------------------------------
# 1.5 因子栅格 -> PNG 叠加层（供前端按需开关显示）
# ----------------------------------------------------------------------
def export_factor_overlay(factor_path):
    """任意单波段因子栅格 -> Web Mercator PNG，返回叠加所需元数据"""
    name = os.path.splitext(os.path.basename(factor_path))[0]
    with rasterio.open(factor_path) as src:
        if src.crs is None:
            raise ValueError(f"因子栅格缺少 CRS 投影信息：{name}")
        arr = src.read(1).astype(np.float32)
        if src.nodata is not None and np.isfinite(src.nodata):
            arr = np.where(arr == src.nodata, np.nan, arr)
        arr[~np.isfinite(arr)] = np.nan
        dst_arr, (west, south, east, north), (dst_w, dst_h) = _reproject_to_wgs84(src, arr)

        rgba = _colorize_factor(dst_arr)
        digest = hashlib.md5(os.path.abspath(factor_path).encode("utf-8")).hexdigest()[:10]
        png_name = f"factor_{digest}.png"
        Image.fromarray(rgba, mode="RGBA").save(
            os.path.join(RESULT_DIR, png_name), optimize=True
        )

        finite = np.isfinite(arr)
        vrange = None
        if finite.any():
            vrange = [round(float(np.nanmin(arr)), 3), round(float(np.nanmax(arr)), 3)]

        return {
            "name": name,
            "path": factor_path,
            "png_url": f"/static/{png_name}",
            "bounds": {
                "west": round(float(west), 7),
                "south": round(float(south), 7),
                "east": round(float(east), 7),
                "north": round(float(north), 7),
            },
            "size": {"width": dst_w, "height": dst_h},
            "value_range": vrange,
        }


# ----------------------------------------------------------------------
# 2. 矢量图层导出为 WGS84 GeoJSON
# ----------------------------------------------------------------------
def _write_geojson(gdf, filename):
    path = os.path.join(RESULT_DIR, filename)
    data = json.loads(gdf.to_json())
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return path


def export_vectors(task_id, sample_shp=None, study_area_shp=None):
    points = {"url": "", "count": 0}
    study = {"url": "", "count": 0}

    if sample_shp and os.path.exists(sample_shp):
        gdf_pts = gpd.read_file(sample_shp)
        if gdf_pts.crs is None:
            raise ValueError(f"灾害点矢量缺少坐标系（.prj）定义，无法转换 WGS84：{sample_shp}")
        if not gdf_pts.empty:
            # 显式转到 EPSG:4326，保证与栅格 PNG 的经纬度 bounds 同一坐标系
            gdf_pts = gdf_pts.to_crs(epsg=4326)
            path = _write_geojson(gdf_pts, f"points_{task_id}.geojson")
            points = {"url": f"/static/{os.path.basename(path)}", "count": int(len(gdf_pts))}

    if study_area_shp and os.path.exists(study_area_shp):
        gdf_area = gpd.read_file(study_area_shp)
        if gdf_area.crs is None:
            raise ValueError(f"研究区矢量缺少坐标系（.prj）定义，无法转换 WGS84：{study_area_shp}")
        if not gdf_area.empty:
            gdf_area = gdf_area.to_crs(epsg=4326)
            path = _write_geojson(gdf_area, f"study_area_{task_id}.geojson")
            study = {"url": f"/static/{os.path.basename(path)}", "count": int(len(gdf_area))}

    return {"points": points, "study_area": study}


# ----------------------------------------------------------------------
# 3. 空间正确性校验
# ----------------------------------------------------------------------
def spatial_check(tif_path, sample_shp=None, study_area_shp=None):
    with rasterio.open(tif_path) as src:
        arr = src.read(1).astype(np.float32)
        if src.nodata is not None and np.isfinite(src.nodata):
            arr = np.where(arr == src.nodata, np.nan, arr)
        crs = src.crs
        transform = src.transform
        shape = (src.height, src.width)

    checks = []
    valid = np.isfinite(arr)

    # ---- 投影一致性 ----
    crs_list = [str(crs)]
    if sample_shp and os.path.exists(sample_shp):
        crs_list.append(str(gpd.read_file(sample_shp).crs))
    if study_area_shp and os.path.exists(study_area_shp):
        crs_list.append(str(gpd.read_file(study_area_shp).crs))
    projection_ok = len(set(crs_list)) == 1
    checks.append({
        "name": "投影匹配",
        "passed": bool(projection_ok),
        "detail": f"栅格/矢量统一为 {crs}" if projection_ok
        else f"检测到不同投影：{crs_list}（已自动重投影，仍建议统一数据源）",
    })

    # ---- 经纬度边界 ----
    w, s, e, n = transform_bounds(crs, WGS84, *src.bounds, densify_pts=101)
    bounds_ok = (-180 <= w <= 180 and -180 <= e <= 180
                 and -90 <= s <= 90 and -90 <= n <= 90 and e > w and n > s)
    checks.append({
        "name": "经纬度边界合法",
        "passed": bool(bounds_ok),
        "detail": f"WGS84 范围 [{w:.6f}, {s:.6f}] ~ [{e:.6f}, {n:.6f}]",
    })

    # ---- 坐标往返误差 ----
    roundtrip_error = 0.0
    if sample_shp and os.path.exists(sample_shp):
        gdf_pts_4326 = gpd.read_file(sample_shp).to_crs(WGS84)
        fwd = Transformer.from_crs(WGS84, crs, always_xy=True)
        back = Transformer.from_crs(crs, WGS84, always_xy=True)
        errors = []
        for geom in gdf_pts_4326.geometry:
            if geom is None or geom.is_empty:
                continue
            x, y = geom.x, geom.y
            x2, y2 = fwd.transform(x, y)
            x3, y3 = back.transform(x2, y2)
            errors.append(float(np.hypot(x3 - x, y3 - y)))
        roundtrip_error = round(max(errors), 5) if errors else 0.0
    checks.append({
        "name": "坐标往返误差",
        "passed": bool(roundtrip_error < 0.05),
        "detail": f"最大往返偏差 {roundtrip_error} m（<0.05 m 视为无偏移）",
    })

    # ---- 风险分布逻辑：灾害点易发性应高于研究区背景 ----
    points_total = 0
    points_in_study = 0
    points_valid = 0
    points_high = 0
    mean_points = None
    mean_study = None
    mean_all = float(np.nanmean(arr[valid])) if valid.any() else None

    study_mask = None
    if study_area_shp and os.path.exists(study_area_shp):
        gdf_study = gpd.read_file(study_area_shp).to_crs(crs)
        geoms = [g for g in gdf_study.geometry if g is not None and not g.is_empty]
        if geoms:
            study_mask = geometry_mask(geoms, out_shape=shape, transform=transform, invert=True)
            from shapely.ops import unary_union
            study_union = unary_union(geoms)
        else:
            study_union = None
    else:
        study_union = None

    if study_mask is not None:
        study_valid = valid & study_mask
        mean_study = float(np.nanmean(arr[study_valid])) if study_valid.any() else None

    if sample_shp and os.path.exists(sample_shp):
        gdf_pts = gpd.read_file(sample_shp).to_crs(crs)
        pts_in = []
        for geom in gdf_pts.geometry:
            if geom is None or geom.is_empty:
                continue
            if geom.geom_type != "Point":
                geom = geom.centroid
            points_total += 1
            if study_union is not None and study_union.contains(geom):
                points_in_study += 1
            row, col = rasterio.transform.rowcol(transform, geom.x, geom.y)
            row, col = int(row), int(col)
            if not (0 <= row < shape[0] and 0 <= col < shape[1]):
                continue
            if not valid[row, col]:
                continue
            value = float(arr[row, col])
            points_valid += 1
            pts_in.append(value)
            if value >= 0.6:
                points_high += 1
        if pts_in:
            mean_points = float(np.mean(pts_in))

    high_hit_ratio = round(points_high / points_valid, 4) if points_valid else 0.0
    distribution_ok = bool(
        points_valid > 0 and high_hit_ratio >= 0.5 and (
            mean_points is not None and mean_study is not None and mean_points > mean_study
        )
    )
    checks.append({
        "name": "风险分布合理",
        "passed": distribution_ok,
        "detail": f"{points_high}/{points_valid} 个灾害点落在高易发区（{high_hit_ratio * 100:.1f}%）；"
                  f"灾害点均值 {mean_points:.4f}，研究区背景均值 {mean_study:.4f}"
        if points_valid and mean_points is not None and mean_study is not None
        else "缺少灾害点或研究区数据，暂无法校验风险分布",
    })

    # 研究区内的分级面积占比
    class_area_percent = []
    if study_mask is not None and (valid & study_mask).any():
        in_study = arr[valid & study_mask]
        idx = _class_index(in_study)
        for i, c in enumerate(CLASSES):
            class_area_percent.append({
                "name": c["name"],
                "color": c["color"],
                "percent": round(100.0 * int((idx == i).sum()) / len(in_study), 2),
            })

    return {
        "checks": checks,
        "passed": all(c["passed"] for c in checks),
        "crs": str(crs),
        "bounds_wgs84": {
            "west": round(float(w), 7),
            "south": round(float(s), 7),
            "east": round(float(e), 7),
            "north": round(float(n), 7),
        },
        "roundtrip_error_m": roundtrip_error,
        "points_total": points_total,
        "points_in_study": points_in_study,
        "points_valid": points_valid,
        "points_high": points_high,
        "high_hit_ratio": high_hit_ratio,
        "mean_points": round(mean_points, 4) if mean_points is not None else None,
        "mean_study": round(mean_study, 4) if mean_study is not None else None,
        "mean_all": round(mean_all, 4) if mean_all is not None else None,
        "class_area_percent": class_area_percent,
    }


# ----------------------------------------------------------------------
# 4. 点位查询（点击地图弹窗）
# ----------------------------------------------------------------------
def query_point(tif_path, lat, lng):
    with rasterio.open(tif_path) as src:
        transformer = Transformer.from_crs(WGS84, src.crs, always_xy=True)
        x, y = transformer.transform(lng, lat)
        if not (src.bounds.left <= x <= src.bounds.right
                and src.bounds.bottom <= y <= src.bounds.top):
            return {"inside": False, "lat": lat, "lng": lng,
                    "msg": "该位置超出结果栅格覆盖范围"}
        row, col = rasterio.transform.rowcol(src.transform, x, y)
        row, col = int(row), int(col)
        if not (0 <= row < src.height and 0 <= col < src.width):
            return {"inside": False, "lat": lat, "lng": lng,
                    "msg": "该位置超出结果栅格覆盖范围"}
        value = src.read(1, window=Window(col, row, 1, 1))[0, 0]
        if src.nodata is not None and np.isfinite(src.nodata) and value == src.nodata:
            value = np.nan
        if not np.isfinite(value):
            return {"inside": True, "valid": False, "lat": lat, "lng": lng,
                    "msg": "该像元无有效易发性值（数据缺失或不在研究区）"}
        cls = classify_value(float(value))
        cls["advice"] = RISK_ADVICE.get(cls["key"], "暂无建议")
        # 像元中心经纬度，便于前端核对位置
        cx, cy = src.transform * (col + 0.5, row + 0.5)
        back = Transformer.from_crs(src.crs, WGS84, always_xy=True)
        pix_lng, pix_lat = back.transform(cx, cy)
        return {
            "inside": True,
            "valid": True,
            "lat": lat,
            "lng": lng,
            "pixel": {"row": row, "col": col, "lat": pix_lat, "lng": pix_lng},
            **cls,
        }


# ----------------------------------------------------------------------
# 5. 上传因子元数据检查
# ----------------------------------------------------------------------
def inspect_factors(paths):
    if not paths:
        raise ValueError("未提供因子栅格")
    factors = []
    ref = None
    aligned = True
    crs_value = ""
    shape_value = None
    for p in paths:
        if not os.path.exists(p):
            raise FileNotFoundError(f"文件不存在：{p}")
        with rasterio.open(p) as src:
            info = {
                "name": os.path.basename(p),
                "path": p,
                "crs": str(src.crs),
                "shape": [src.height, src.width],
                "resolution": [round(abs(src.transform.a), 3), round(abs(src.transform.e), 3)],
                "nodata": None if src.nodata is None else float(src.nodata),
            }
            # 抽样统计，避免读取整幅大栅格
            sample = src.read(1, out_shape=(min(256, src.height), min(256, src.width))).astype(np.float32)
            if src.nodata is not None and np.isfinite(src.nodata):
                sample = np.where(sample == src.nodata, np.nan, sample)
            finite = np.isfinite(sample)
            info["value_range"] = (
                [round(float(np.nanmin(sample)), 3), round(float(np.nanmax(sample)), 3)]
                if finite.any() else None
            )
            key = (info["shape"], info["crs"], tuple(round(v, 6) for v in src.transform[:6]))
        if ref is None:
            ref = key
            crs_value = info["crs"]
            shape_value = info["shape"]
        elif key != ref:
            aligned = False
        factors.append(info)

    return {
        "aligned": bool(aligned),
        "crs": crs_value,
        "shape": shape_value,
        "factor_count": len(factors),
        "factors": factors,
        "bounds_wgs84": bounds_wgs84(paths[0]),
    }


def bounds_wgs84(raster_path):
    """栅格范围 -> WGS84 经纬度边界（供前端定位）"""
    with rasterio.open(raster_path) as src:
        if src.crs is None:
            return None
        w, s, e, n = transform_bounds(src.crs, WGS84, *src.bounds, densify_pts=21)
    return {
        "west": round(float(w), 7),
        "south": round(float(s), 7),
        "east": round(float(e), 7),
        "north": round(float(n), 7),
    }


# ----------------------------------------------------------------------
# 6. 汇总构建前端所需结果包
# ----------------------------------------------------------------------
def build_web_bundle(task_id, tif_path, sample_shp=None, study_area_shp=None):
    overlay = export_web_overlay(task_id, tif_path)
    vectors = export_vectors(task_id, sample_shp, study_area_shp)
    check = spatial_check(tif_path, sample_shp, study_area_shp)
    return {
        "overlay": overlay,
        "vectors": vectors,
        "spatial_check": check,
    }
