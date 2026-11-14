import os
import shutil
import threading
import uuid
from dataclasses import dataclass, field
from typing import Dict, Any
from model import run_model_train
from result_export import build_web_bundle

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULT_DIR = os.path.join(BASE_DIR, "result")


@dataclass
class TrainTask:
    task_id: str
    status: str       # waiting / running / finished / failed
    progress: float   # 0~100
    msg: str
    result_raster_path: str = ""
    metrics: Dict[str, float] = None
    result_bundle: Dict[str, Any] = field(default=None)

class TaskManager:
    def __init__(self):
        self.tasks: Dict[str, TrainTask] = {}

    def create_task(self) -> str:
        tid = str(uuid.uuid4())
        self.tasks[tid] = TrainTask(
            task_id=tid,
            status="waiting",
            progress=0.0,
            msg="任务已创建，等待开始"
        )
        return tid

    def get_task_info(self, task_id: str) -> Dict[str, Any]:
        t = self.tasks.get(task_id)
        if not t:
            return {"status": "not_found", "msg": "任务不存在"}
        return {
            "task_id": t.task_id,
            "status": t.status,
            "progress": t.progress,
            "msg": t.msg,
            "result_raster_path": t.result_raster_path,
            "metrics": t.metrics,
            "result_bundle": t.result_bundle,
        }

    def list_tasks(self):
        return [
            {
                "task_id": t.task_id,
                "status": t.status,
                "progress": t.progress,
                "msg": t.msg,
                "metrics": t.metrics,
            }
            for t in self.tasks.values()
        ]

    def remove_task(self, task_id: str):
        """移除任务记录，返回被移除的任务；运行中的任务拒绝删除"""
        t = self.tasks.get(task_id)
        if t is None:
            return None
        if t.status in ("waiting", "running"):
            raise RuntimeError("任务正在运行，无法删除，请等待训练结束")
        return self.tasks.pop(task_id)

task_manager = TaskManager()


def _progress_msg(p: float) -> str:
    if p < 10:
        return "读取并校验因子栅格（投影 / 网格对齐）"
    if p < 25:
        return "自动采样滑坡正样本与非滑坡负样本"
    if p < 40:
        return "划分训练集与验证集"
    if p < 70:
        return "训练随机森林模型"
    if p < 85:
        return "评估模型精度（AUC / 准确率 / 召回率）"
    if p < 100:
        return "全区预测并生成分级渲染图层"
    return "训练完成"


def _train_worker(task_id: str, factor_files, sample_shp, model_type, study_area_shp=None):
    task = task_manager.tasks[task_id]
    task.status = "running"
    task.msg = "开始GIS数据预处理"

    def on_progress(p):
        task.progress = p
        task.msg = _progress_msg(p)

    try:
        result = run_model_train(
            factor_files=factor_files,
            landslide_shp=sample_shp,
            study_area_shp=study_area_shp,
            model_type=model_type,
            progress_callback=on_progress,
        )

        # 每个任务保留独立结果栅格，避免并发任务互相覆盖
        task_tif = os.path.join(RESULT_DIR, f"landslide_susceptibility_{task_id}.tif")
        shutil.copy2(result["raster_path"], task_tif)
        task.result_raster_path = task_tif
        task.metrics = result["metrics"]

        task.progress = 95
        task.msg = "重投影易发性栅格并生成 Web 渲染图层"
        task.result_bundle = build_web_bundle(
            task_id, task_tif, sample_shp, study_area_shp
        )

        task.status = "finished"
        task.progress = 100.0
        task.msg = "训练完成，滑坡风险图已生成"
    except Exception as e:
        import traceback
        traceback.print_exc()
        task.status = "failed"
        task.msg = f"训练失败：{str(e)}"

def start_train_task(factor_files, sample_shp, model_type, study_area_shp=None):
    tid = task_manager.create_task()
    th = threading.Thread(
        target=_train_worker,
        args=(tid, factor_files, sample_shp, model_type, study_area_shp),
        daemon=True
    )
    th.start()
    return tid
