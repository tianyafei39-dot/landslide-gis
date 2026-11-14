from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import os
import uuid
import zipfile
import shutil
from typing import List, Optional, Union
from train_task import task_manager, start_train_task
from result_export import inspect_factors, query_point, export_factor_overlay, RISK_ADVICE, classify_value
from fastapi.staticfiles import StaticFiles


app = FastAPI(title="滑坡易发性评价WebGIS后端API")

# 跨域，前端vue访问必须开启
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ==========================================
# 核心路径配置：基于 main.py 所在目录固定
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
# ===================== 新增静态挂载代码=====================
# result文件夹 和main.py同级
tif_dir = os.path.join(BASE_DIR, "result")
os.makedirs(tif_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=tif_dir), name="static")
# =====================================================================

def _abs(p: str) -> str:
    """将相对路径转为基于 BASE_DIR 的绝对路径，绝对路径原样返回"""
    if not p:
        return p
    return p if os.path.isabs(p) else os.path.join(BASE_DIR, p)


def _flatten_extract(subdir: str):
    """如果 ZIP 解压后只有一层子目录，把文件上移一层，避免路径结构混乱"""
    entries = [e for e in os.listdir(subdir) if not e.endswith(".zip")]
    if len(entries) == 1 and os.path.isdir(os.path.join(subdir, entries[0])):
        inner = os.path.join(subdir, entries[0])
        for f in os.listdir(inner):
            shutil.move(os.path.join(inner, f), os.path.join(subdir, f))
        os.rmdir(inner)


class TrainStartRequest(BaseModel):
    sample_shp: str
    model_type: str = "randomforest"
    factor_files: List[str] = Field(default_factory=list)
    study_area_shp: Optional[str] = None


class InspectFactorsRequest(BaseModel):
    factor_files: List[str] = Field(default_factory=list)


# ---------- 0. 兼容上传接口（支持 file 单文件 / files 多文件） ----------
@app.post("/api/upload")
async def upload_compat(
    file: Optional[UploadFile] = File(None),
    files: Optional[List[UploadFile]] = File(None),
):
    incoming: List[UploadFile] = []
    if files:
        incoming.extend(files)
    if file is not None:
        incoming.append(file)

    if not incoming:
        raise HTTPException(
            status_code=400,
            detail="未接收到任何文件，请使用 file 或 files 字段上传",
        )

    subdir = os.path.join(UPLOAD_DIR, str(uuid.uuid4()))
    os.makedirs(subdir, exist_ok=True)

    saved = []
    for f in incoming:
        filename = os.path.basename(f.filename)
        save_path = os.path.join(subdir, filename)
        with open(save_path, "wb") as out:
            shutil.copyfileobj(f.file, out)
        
        # 返回绝对路径，方便直接喂给训练接口
        saved.append({"filename": filename, "path": os.path.abspath(save_path)})

        # 【可选扩展】如果上传的是 ZIP，自动解压并一起返回内部的 .shp
        if filename.lower().endswith(".zip"):
            extract_dir = os.path.join(subdir, filename[:-4])
            os.makedirs(extract_dir, exist_ok=True)
            try:
                with zipfile.ZipFile(save_path, "r") as z:
                    z.extractall(extract_dir)
                _flatten_extract(extract_dir)
                for root, _, fs in os.walk(extract_dir):
                    for ff in fs:
                        if ff.endswith(".shp"):
                            full = os.path.abspath(os.path.join(root, ff))
                            saved.append({
                                "filename": ff,
                                "path": full,
                                "from_zip": filename,
                            })
            except zipfile.BadZipFile:
                pass  # 不是合法 ZIP 或解压失败，忽略

    return {
        "upload_dir": subdir,
        "files": saved,
        "msg": f"成功上传 {len(incoming)} 个文件",
    }


# ---------- 1. 普通多文件上传（适合 tif 等单文件） ----------
@app.post("/api/upload/batch")
async def upload_files_batch(files: List[UploadFile] = File(...)):
    subdir = os.path.join(UPLOAD_DIR, str(uuid.uuid4()))
    os.makedirs(subdir, exist_ok=True)

    saved = []
    for file in files:
        filename = os.path.basename(file.filename)
        save_path = os.path.join(subdir, filename)
        with open(save_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        saved.append({"filename": filename, "path": os.path.abspath(save_path)})

    return {
        "upload_dir": subdir,
        "files": saved,
        "msg": f"成功上传 {len(saved)} 个文件",
    }


# ---------- 2. ZIP 上传（适合 Shapefile） ----------
@app.post("/api/upload/shapefile")
async def upload_shapefile_zip(file: UploadFile = File(...)):
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="请上传 ZIP 格式的 Shapefile 压缩包")

    subdir = os.path.join(UPLOAD_DIR, str(uuid.uuid4()))
    os.makedirs(subdir, exist_ok=True)

    zip_path = os.path.join(subdir, os.path.basename(file.filename))
    with open(zip_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(subdir)
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="ZIP 文件损坏或格式不正确")

    # 抹平多余的文件夹层级
    _flatten_extract(subdir)

    shp_files = []
    for root, _, files in os.walk(subdir):
        for f in files:
            if f.endswith(".shp"):
                shp_files.append(os.path.join(root, f))

    if not shp_files:
        raise HTTPException(status_code=400, detail="ZIP 中未找到 .shp 文件")
    if len(shp_files) > 1:
        raise HTTPException(
            status_code=400,
            detail=f"ZIP 中有多个 .shp 文件，请只放一个：{shp_files}",
        )

    abs_shp = os.path.abspath(shp_files[0])
    return {
        "shp_path": abs_shp,
        "upload_dir": subdir,
        "msg": "Shapefile 上传并解压成功",
    }


# ---------- 3. 启动训练任务 ----------
@app.post("/api/train/start")
async def train_start(payload: Union[TrainStartRequest, List[TrainStartRequest]]):
    # Apifox 可能把 JSON 对象包成单元素数组；统一取第一条
    if isinstance(payload, list):
        if not payload:
            raise HTTPException(status_code=422, detail="请求体不能为空")
        req = payload[0]
    else:
        req = payload

    # 核心：将所有路径兜底转换为绝对路径
    task_id = start_train_task(
        [_abs(p) for p in req.factor_files],
        _abs(req.sample_shp),
        req.model_type,
        _abs(req.study_area_shp) if req.study_area_shp else None,
    )
    return {"task_id": task_id}


# ---------- 4. 查询训练进度 ----------
@app.get("/api/train/status/{task_id}")
async def get_task_status(task_id: str):
    info = task_manager.get_task_info(task_id)
    bundle = info.get("result_bundle")
    raster_path = info.get("result_raster_path", "")
    if raster_path and info["status"] == "finished":
        info["tif_url"] = f"/static/{os.path.basename(raster_path)}"
    else:
        info["tif_url"] = ""
    # 前端渲染所需的完整结果包（图层地址、经纬度边界、图例、分级统计、空间校验）
    info["result"] = bundle
    return info

# ---------- 5. 获取任务列表 ----------
@app.get("/api/task/list")
async def get_task_list():
    return {"tasks": task_manager.list_tasks()}


# ---------- 6. 获取结果栅格路径 ----------
@app.get("/api/result/raster")
async def get_result_raster(task_id: str = Query(...)):
    task_info = task_manager.get_task_info(task_id)
    if task_info["status"] != "finished":
        raise HTTPException(status_code=400, detail="任务未完成")
    raster_path = task_info["result_raster_path"]
    tif_name = os.path.basename(raster_path)
    return {
        "raster_path": raster_path,
        "tif_url": f"/static/{tif_name}",
        "result": task_info.get("result_bundle"),
    }


# ---------- 7. 地图点击查询像元易发性 ----------
@app.get("/api/result/query")
async def query_result(
    task_id: str = Query(...),
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
):
    task_info = task_manager.get_task_info(task_id)
    if task_info["status"] != "finished":
        raise HTTPException(status_code=400, detail="任务未完成，暂无法查询")
    return query_point(task_info["result_raster_path"], lat, lng)


# ---------- 8. 上传因子栅格元数据校验 ----------
@app.post("/api/factors/inspect")
async def factors_inspect(req: InspectFactorsRequest):
    try:
        return inspect_factors([_abs(p) for p in req.factor_files])
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"栅格解析失败：{str(e)}")


# ---------- 8b. 因子栅格渲染为地图叠加层 ----------
@app.post("/api/factors/overlays")
async def factors_overlays(req: InspectFactorsRequest):
    overlays = []
    for p in req.factor_files:
        ap = _abs(p)
        if not os.path.exists(ap):
            raise HTTPException(status_code=400, detail=f"文件不存在：{p}")
        try:
            overlays.append(export_factor_overlay(ap))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"因子渲染失败（{os.path.basename(ap)}）：{str(e)}")
    return {"overlays": overlays, "count": len(overlays)}


# ---------- 8c. 删除：上传文件 / 训练任务结果 ----------
# Shapefile 主文件的同名附属文件，删 shp 时一并清理
_SHP_SIDECARS = (".shx", ".dbf", ".prj", ".cpg", ".sbn", ".sbx", ".qpj", ".shp.xml")


def _ensure_within(target_path: str, allowed_dir: str):
    """路径安全校验：目标必须位于允许目录内，防止越权删除系统文件"""
    real_allowed = os.path.realpath(allowed_dir)
    real_target = os.path.realpath(target_path)
    if os.path.commonpath([real_allowed, real_target]) != real_allowed:
        raise HTTPException(status_code=403, detail="仅允许删除上传目录内的文件")
    return real_target


@app.delete("/api/delete")
async def delete_resource(
    target: str = Query(..., pattern="^(task|file)$"),
    task_id: Optional[str] = None,
    path: Optional[str] = None,
):
    """
    DELETE /api/delete?target=task&task_id=xxx   删除训练任务及其结果产物
    DELETE /api/delete?target=file&path=xxx      删除上传的文件（限 uploads 目录）
    用查询参数承载，规避 DELETE 携带请求体在部分客户端下不兼容的问题
    """
    # ---------- 删除训练任务 ----------
    if target == "task":
        if not task_id:
            raise HTTPException(status_code=422, detail="删除任务必须提供 task_id")
        try:
            removed = task_manager.remove_task(task_id)
        except RuntimeError as e:
            raise HTTPException(status_code=409, detail=str(e))
        if removed is None:
            raise HTTPException(status_code=404, detail="任务不存在或已被删除")

        # 清理该任务在 result 目录下的全部产物（tif / png / geojson，均以 task_id 命名）
        removed_files = []
        for name in os.listdir(tif_dir):
            if task_id in name:
                fp = os.path.join(tif_dir, name)
                try:
                    os.remove(fp)
                    removed_files.append(name)
                except OSError:
                    pass
        return {
            "success": True,
            "target": "task",
            "task_id": task_id,
            "deleted_files": removed_files,
            "msg": f"任务 {task_id} 已删除，清理产物 {len(removed_files)} 个",
        }

    # ---------- 删除上传文件 ----------
    if not path:
        raise HTTPException(status_code=422, detail="删除文件必须提供 path")
    abs_path = _abs(path)
    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail="文件不存在或已被删除")
    real_path = _ensure_within(abs_path, UPLOAD_DIR)

    deleted = []
    if os.path.isdir(real_path):
        # 上传时按 uuid 建的子目录：整目录删除
        shutil.rmtree(real_path, ignore_errors=True)
        deleted.append(os.path.basename(real_path))
    else:
        os.remove(real_path)
        deleted.append(os.path.basename(real_path))
        # Shapefile 附带的同名边车文件一起清理
        stem = os.path.splitext(real_path)[0]
        for ext in _SHP_SIDECARS:
            side = stem + ext
            if os.path.exists(side):
                os.remove(side)
                deleted.append(os.path.basename(side))

    return {
        "success": True,
        "target": "file",
        "deleted_files": deleted,
        "msg": f"已删除 {len(deleted)} 个文件",
    }


# ---------- 9. 内置示例数据（真实滑坡研究区） ----------
@app.get("/api/demo/dataset")
async def demo_dataset():
    project_dir = os.path.dirname(BASE_DIR)
    raw_dir = os.path.join(project_dir, "data", "raw")

    factor_names = ["DEM.tif", "Slope.tif", "aspect.tif", "plan_cur.tif", "curvature.tif", "NDVI.tif"]
    factors = [os.path.join(raw_dir, n) for n in factor_names if os.path.exists(os.path.join(raw_dir, n))]
    sample_shp = os.path.join(raw_dir, "disaster-site", "disaster-site.shp")
    study_shp = os.path.join(raw_dir, "researcharea", "researcharea.shp")

    if not factors or not os.path.exists(sample_shp):
        raise HTTPException(status_code=404, detail="内置示例数据缺失，请手动上传数据")

    return {
        "factor_files": factors,
        "sample_shp": sample_shp,
        "study_area_shp": study_shp if os.path.exists(study_shp) else None,
        "msg": "已载入示例数据（研究区 + 滑坡灾害点 + 6 个因子栅格）",
    }

# ---------- 10. 托管前端构建产物（单服务部署，html=True 支持 SPA） ----------
FRONTEND_DIST = os.path.join(os.path.dirname(BASE_DIR), "frontend", "dist")
if os.path.isdir(FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    # 注意：启动时必须用绝对路径确保 cwd 在 backend 目录下
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_dirs=[BASE_DIR]
    )