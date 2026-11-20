from security import get_current_user, require_admin
from db_models import User
from database import Base, engine, SessionLocal
from db_models import User
from security import hash_password,get_current_user, require_admin
from routers import auth, users
from config import CORS_ORIGINS, ADMIN_USERNAME, ADMIN_PASSWORD
from fastapi import FastAPI, HTTPException, UploadFile, File, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, Field
import os
import uuid
import zipfile
import shutil
from typing import List, Optional, Union
from train_task import task_manager, start_train_task
from result_export import inspect_factors, query_point, export_factor_overlay, RISK_ADVICE, classify_value
from fastapi.staticfiles import StaticFiles
from algorithms import build_custom_pipeline

app = FastAPI(title="滑坡易发性评价WebGIS后端API")

# 跨域，前端vue访问必须开启
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# GZip 压缩：大 JSON（result_bundle 等）省带宽、加快并发传输
app.add_middleware(GZipMiddleware, minimum_size=1024)
# ==========================================
# 核心路径配置：基于 main.py 所在目录固定
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
DEMO_DATA_DIR = os.path.join(os.path.dirname(BASE_DIR), "data", "raw")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DEMO_DATA_DIR, exist_ok=True)
# ===================== 新增静态挂载代码=====================
# result文件夹 和main.py同级
tif_dir = os.path.join(BASE_DIR, "result")
os.makedirs(tif_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=tif_dir), name="static")


@app.middleware("http")
async def _static_cache_headers(request, call_next):
    """PNG/TIF/GeoJSON 内容随 task_id/哈希命名不变，客户端缓存 1 天减少重复下载"""
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=86400"
    return response
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
    custom_model_path: Optional[str] = None # 👈 方案一：自定义模型路径
    pipeline_config: Optional[dict] = None  # 👈 方案二：搭积木配置
    params: Optional[dict] = None           # 👈 超参数（neg_ratio / n_estimators / lr_C / svm_C / svm_kernel）

class InspectFactorsRequest(BaseModel):
    factor_files: List[str] = Field(default_factory=list)


# ---------- 0. 兼容上传接口（支持 file 单文件 / files 多文件） ----------
@app.post("/api/upload")
async def upload_compat(
    file: Optional[UploadFile] = File(None),
    files: Optional[List[UploadFile]] = File(None),
    user: User = Depends(get_current_user)  # 添加守门员
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

    subdir = os.path.join(UPLOAD_DIR, str(user.id), str(uuid.uuid4()))
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
async def upload_files_batch(files: List[UploadFile] = File(...),
                             user: User = Depends(get_current_user)):
    subdir = os.path.join(UPLOAD_DIR, str(user.id), str(uuid.uuid4()))
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


# ---------- 2. 上传（适合 Shapefile） ----------
@app.post("/api/upload/shapefile")
async def upload_shapefile_zip(
    files: List[UploadFile] = File(...), # 👈 这里改成接收多个文件
    user: User = Depends(get_current_user)
):
    # 1. 建一个专属的文件夹存放这一组 shp 文件
    subdir = os.path.join(UPLOAD_DIR, str(user.id), str(uuid.uuid4()))
    os.makedirs(subdir, exist_ok=True)

    saved_paths = []
    shp_path = None
    
    # 2. 把多选框里选中的所有文件都存下来
    for file in files:
        filename = os.path.basename(file.filename)
        save_path = os.path.join(subdir, filename)
        with open(save_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        saved_paths.append(save_path)
        if filename.endswith(".shp"):
            shp_path = save_path

    if not shp_path:
        raise HTTPException(status_code=400, detail="未找到 .shp 文件")
    if not os.path.exists(shp_path.replace(".shp", ".prj")):
        raise HTTPException(status_code=400, detail="缺少 .prj 投影文件，无法定位")

    # 3. 解析并强制转换为 WGS84，返回给前端预览
    try:
        import geopandas as gpd
        gdf = gpd.read_file(shp_path)
        
        # 如果没有投影，或投影不是 4326，强制转换
        if gdf.crs is None:
            gdf.set_crs(epsg=4326, inplace=True)
        elif gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)
            
        # 提取边界范围
        bounds = gdf.total_bounds # [minx, miny, maxx, maxy]
        # 转成前端需要的格式 (南, 西, 北, 东)
        leaflet_bounds = {
            "south": float(bounds[1]), "west": float(bounds[0]),
            "north": float(bounds[3]), "east": float(bounds[2])
        }
        
        # 转成 GeoJSON
        geojson_data = gdf.__geo_interface__
        # 提取预览图用的属性（取前8个字段供点击弹窗）
        preview_geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": f["geometry"],
                    "properties": f["properties"]
                } for f in geojson_data["features"]
            ]
        }
        
        return {
            "shp_path": shp_path,
            "bounds": leaflet_bounds,
            "geojson": preview_geojson,
            "msg": "Shapefile 解析成功"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析失败：{str(e)}")

@app.post("/api/model/upload")
async def upload_model(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    if not file.filename.endswith(('.joblib', '.pkl')):
        raise HTTPException(status_code=400, detail="仅支持 .joblib 或 .pkl 文件")
    # 文件名清洗：只保留纯文件名，防止 ../ 路径穿越
    safe_name = os.path.basename(file.filename.replace("\\", "/"))
    if not safe_name or safe_name.startswith("."):
        raise HTTPException(status_code=400, detail="文件名不合法")
    model_dir = os.path.join(UPLOAD_DIR, str(user.id), "models")
    os.makedirs(model_dir, exist_ok=True)
    save_path = os.path.join(model_dir, safe_name)
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"model_path": os.path.abspath(save_path), "msg": "模型上传成功"}

# ---------- 3. 启动训练任务 ----------
@app.post("/api/train/start")
async def train_start(payload: Union[TrainStartRequest, List[TrainStartRequest]], 
                      user: User = Depends(get_current_user)):
    # Apifox 可能把 JSON 对象包成单元素数组；统一取第一条
    if isinstance(payload, list):
        if not payload:
            raise HTTPException(status_code=422, detail="请求体不能为空")
        req = payload[0]
    else:
        req = payload

       # 路径安全校验：非 admin 只能使用自己目录下的文件，或者使用内置示例数据
    if user.role != "admin":
        user_dir = os.path.join(UPLOAD_DIR, str(user.id))
        all_paths = [_abs(p) for p in req.factor_files] + [_abs(req.sample_shp)]
        if req.study_area_shp:
            all_paths.append(_abs(req.study_area_shp))
        if req.custom_model_path:
            all_paths.append(_abs(req.custom_model_path))
            
        # 统一定义检查函数，防止路径斜杠和大小写引起的误判
        def check_path_valid(target_path, allowed_dir):
            abs_target = os.path.abspath(target_path).lower()
            abs_allowed = os.path.abspath(allowed_dir).lower()
            try:
                # relpath 返回相对路径，如果不以 '..' 开头，说明在允许的目录内
                return not os.path.relpath(abs_target, abs_allowed).startswith('..')
            except ValueError:
                return False # 跨盘符会报错，直接拦截

        for p in all_paths:
            # 只要满足以下两个条件之一即可放行：
            # 1. 文件在用户自己的专属目录下 (uploads/用户ID/)
            # 2. 文件在系统示例数据目录下 (data/raw/)
            is_in_user_dir = check_path_valid(p, user_dir)
            is_in_demo_dir = check_path_valid(p, DEMO_DATA_DIR)
            
            if not (is_in_user_dir or is_in_demo_dir):
                raise HTTPException(status_code=403, detail="无权使用他人的数据文件")
    # 把 user.id 传给异步任务
    task_id = start_train_task(
        [_abs(p) for p in req.factor_files],
        _abs(req.sample_shp),
        req.model_type,
        _abs(req.study_area_shp) if req.study_area_shp else None,
        user_id=user.id,
        custom_model_path=_abs(req.custom_model_path) if req.custom_model_path else None,
        pipeline_config=req.pipeline_config,
        params=req.params,  # 👈 透传超参数
    )
    return {"task_id": task_id}


# ---------- 4. 查询训练进度 ----------
@app.get("/api/train/status/{task_id}")
async def get_task_status(task_id: str, user: User = Depends(get_current_user)):
    info = task_manager.get_task_info(task_id)
    # 校验归属
    if user.role != "admin" and info.get("user_id") != user.id:
        raise HTTPException(status_code=403, detail="无权查看该任务")
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
async def get_task_list(user: User = Depends(get_current_user)):  # 加锁
    all_tasks = task_manager.list_tasks()
    if user.role == "admin":
        return {"tasks": all_tasks}
    # 普通用户只返回自己的
    my_tasks = [t for t in all_tasks if t.get("user_id") == user.id]
    return {"tasks": my_tasks}

# ---------- 6. 获取结果栅格路径 ----------
@app.get("/api/result/raster")
async def get_result_raster(task_id: str = Query(...), user: User = Depends(get_current_user) ):
    task_info = task_manager.get_task_info(task_id)
    # 校验任务是否存在
    if task_info["status"] == "not_found":
        raise HTTPException(status_code=404, detail="任务不存在")
    # 越权校验
    if user.role != "admin" and task_info.get("user_id") != user.id:
        raise HTTPException(status_code=403, detail="无权查看该任务结果")
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
    user: User = Depends(get_current_user) # 加锁
):
    task_info = task_manager.get_task_info(task_id)
     # 校验任务是否存在
    if task_info["status"] == "not_found":
        raise HTTPException(status_code=404, detail="任务不存在")
        
    # 越权校验
    if user.role != "admin" and task_info.get("user_id") != user.id:
        raise HTTPException(status_code=403, detail="无权查询该任务结果")
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
    user: User = Depends(get_current_user) # 加锁
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
            
        info = task_manager.get_task_info(task_id)
        if info["status"] == "not_found":
            raise HTTPException(status_code=404, detail="任务不存在或已被删除")
            
        # 2. 越权校验：不是管理员且不是发起人，不让删
        if user.role != "admin" and info.get("user_id") != user.id:
            raise HTTPException(status_code=403, detail="无权删除该任务")
            
        try:
            removed = task_manager.remove_task(task_id)
        except RuntimeError as e:
            raise HTTPException(status_code=409, detail=str(e))
            
        if removed is None:
            raise HTTPException(status_code=404, detail="任务不存在或已被删除")

        # 清理该任务在 result 目录下的全部产物
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
        
    # 3. 针对文件的越权校验
    if user.role != "admin":
        # 普通用户只能删自己 ID 对应目录下的文件
        user_upload_dir = os.path.join(UPLOAD_DIR, str(user.id))
        real_user_dir = os.path.realpath(user_upload_dir)
        real_target = os.path.realpath(abs_path)
        # 判断目标文件是否在用户自己的目录内
        if os.path.commonpath([real_user_dir, real_target]) != real_user_dir:
            raise HTTPException(status_code=403, detail="无权删除他人的文件")

    # 原有的安全校验
    real_path = _ensure_within(abs_path, UPLOAD_DIR)

    deleted = []
    if os.path.isdir(real_path):
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

# 注册认证路由（必须在 StaticFiles 挂载之前，否则 "/" 挂载点会吞掉 /api/auth/*，
# 导致 POST 登录返回 405、GET /me 返回 404）
app.include_router(auth.router)
app.include_router(users.router)
# ---------- 10. 托管前端构建产物（单服务部署，html=True 支持 SPA） ----------
#FRONTEND_DIST = os.path.join(os.path.dirname(BASE_DIR), "frontend", "dist")
#if os.path.isdir(FRONTEND_DIST):
   # app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")

@app.on_event("startup")
def on_startup():
    # 1. 自动建表
    Base.metadata.create_all(bind=engine)
    # 2. 初始化管理员
    db = SessionLocal()
    try:
        exists = db.query(User).filter(User.username == ADMIN_USERNAME).first()
        if not exists:
            db.add(User(
                username=ADMIN_USERNAME,
                password_hash=hash_password(ADMIN_PASSWORD),
                role="admin",
                is_active=True,
            ))
            db.commit()
            print(f"✅ 管理员账号 {ADMIN_USERNAME} 初始化成功！")
    finally:
        db.close()

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