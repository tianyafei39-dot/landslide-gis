# -*- coding: utf-8 -*-
"""
滑坡易发性建模主流程：
采样 → 划分 → 训练 → 评估 → 全区预测 → 输出栅格 + 模型
"""

import os
import numpy as np
import joblib
import geopandas as gpd

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    roc_auc_score, accuracy_score,
    precision_score, recall_score, f1_score,
)

from gis_preprocess import (
    sample_points_auto_label,
    read_raster,
    save_prediction_raster,
    check_rasters_aligned,
    _raster_valid_mask,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULT_DIR = os.path.join(BASE_DIR, "result")
MODEL_DIR = os.path.join(BASE_DIR, "models")
os.makedirs(RESULT_DIR, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)


# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------
def run_model_train(
    factor_files,
    landslide_shp,
    study_area_shp=None,
    model_type="randomforest",
    neg_ratio=3.0,            # 负:正 = 3:1
    min_dist_pixels=3,
    test_size=0.3,
    random_state=42,
    progress_callback=None,
):
    def report(p):
        if progress_callback:
            progress_callback(p)

    # ---------- step0 校验 ----------
    report(3)
    check_rasters_aligned(factor_files)

    # ---------- step1 采样 ----------
    report(10)
    X, y = sample_points_auto_label(
        factor_files,
        landslide_shp,
        study_area_shp,
        neg_ratio=neg_ratio,
        min_dist_pixels=min_dist_pixels,
        random_state=random_state,
    )

    # ---------- step2 划分 ----------
    report(25)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=test_size,
        random_state=random_state,
        stratify=y,
    )

    # ---------- step3 训练 ----------
    report(40)
    if model_type == "randomforest":
        clf = RandomForestClassifier(
            n_estimators=100,
            random_state=random_state,
            n_jobs=-1,
        )
    elif model_type == "logistic":
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
        from sklearn.pipeline import Pipeline
        clf = Pipeline([
            ("scaler", StandardScaler()),
            ("lr", LogisticRegression(max_iter=1000, random_state=random_state)),
        ])
    else:
        raise ValueError(f"未知 model_type: {model_type}")

    clf.fit(X_train, y_train)

    # ---------- step4 评估 ----------
    report(70)
    y_prob = clf.predict_proba(X_test)[:, 1]
    y_hat = (y_prob > 0.5).astype(int)

    metrics = {
        "AUC":       round(roc_auc_score(y_test, y_prob), 4),
        "Accuracy":  round(accuracy_score(y_test, y_hat), 4),
        "Precision": round(precision_score(y_test, y_hat, zero_division=0), 4),
        "Recall":    round(recall_score(y_test, y_hat, zero_division=0), 4),
        "F1":        round(f1_score(y_test, y_hat, zero_division=0), 4),
    }
    print("[评估指标]", metrics)

    # ---------- step5 全区预测 ----------
    report(85)
    ref_arr, ref_profile, ref_transform, ref_crs, _ = read_raster(factor_files[0])
    h, w = ref_arr.shape

    # 拼接所有因子为 (h*w, F)，保持与训练时相同的顺序
    full_features = np.stack(
        [read_raster(fp)[0].ravel() for fp in factor_files],
        axis=1,
    )

    # 有效像元掩膜：仅对研究区内、且因子有值的像元做预测，避免研究区外出现无意义风险值
    study_gdf = None
    if study_area_shp:
        study_gdf = gpd.read_file(study_area_shp).to_crs(ref_crs)
    valid = _raster_valid_mask(
        factor_files,
        study_area_gdf=study_gdf,
        ref_transform=ref_transform,
        ref_shape=(h, w),
    ).ravel()

    pred_flat = np.full(h * w, np.nan, dtype=np.float32)
    if valid.any():
        pred_flat[valid] = clf.predict_proba(full_features[valid])[:, 1]
    pred_raster = pred_flat.reshape(h, w)

    # ---------- step6 输出 ----------
    out_tif = os.path.join(RESULT_DIR, "landslide_susceptibility.tif")
    save_prediction_raster(ref_profile, pred_raster, out_tif)

    model_path = os.path.join(MODEL_DIR, f"{model_type}_model.joblib")
    joblib.dump(clf, model_path)

    report(100)
    return {
        "raster_path": out_tif,
        "model_path": model_path,
        "metrics": metrics,
    }


# ----------------------------------------------------------------------
# 直接运行示例
# ----------------------------------------------------------------------
if __name__ == "__main__":
    factor_files = [
        "D:/my/landslide-webgis-platform/data/raw/slope.tif",
        "D:/my/landslide-webgis-platform/data/raw/dem.tif",
        "D:/my/landslide-webgis-platform/data/raw/ndvi.tif",
        "D:/my/landslide-webgis-platform/data/raw/rain.tif",
    ]
    landslide_shp = "D:/my/landslide-webgis-platform/data/raw/disaster-site.shp"   # 只有灾害点
    study_area_shp = "D:/my/landslide-webgis-platform/data/raw/researcharea.shp"         # 研究区面

    result = run_model_train(
        factor_files=factor_files,
        landslide_shp=landslide_shp,
        study_area_shp=study_area_shp,
        model_type="randomforest",
        neg_ratio=3.0,          # 负:正 = 3:1
        min_dist_pixels=3,
        test_size=0.3,
        random_state=42,
        progress_callback=lambda p: print(f"进度 {p}%"),
    )
    print(result)