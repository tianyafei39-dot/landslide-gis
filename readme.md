# 滑坡易发性评价 WebGIS 平台

前端 Vue3 + Vite + Element Plus + Leaflet，后端 FastAPI + GDAL/Rasterio + 随机森林。
采用**前后端分离部署**：前端跑 Vite 开发服务器（5173 端口），后端跑 FastAPI（8000 端口），
前端通过 Vite 代理把 `/api`、`/static` 请求转发到后端，浏览器无跨域问题。
另保留单服务（后端托管构建产物）作为备选模式。

---

## 一、环境要求（首次运行前检查一次即可）

| 依赖 | 版本要求 | 检查命令 |
|---|---|---|
| Python | 3.10+ | `python --version` |
| Node.js | 18+ | `node --version` |

---

## 二、首次部署（只做一次）

在项目根目录 `d:\my\landslide-webgis-platform` 下执行：

### 1. 后端环境

```powershell
cd backend
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

> 如果 `backend\venv` 文件夹已存在，跳过本节。

### 2. 前端依赖

```powershell
cd frontend
npm install
```

> 分离部署模式下不需要 `npm run build`；`npm run dev` 直接跑源码，改代码即时热更新。
> 仅当使用文末"备选：单服务模式"时才需要构建。

---

## 三、日常启动（前后端分离模式）

需要同时运行**两个**服务，各占一个控制台窗口。

### 方法 A：一键启动（推荐）

**双击项目根目录的 `start.bat`**，会自动弹出两个黑色控制台窗口：

| 窗口标题 | 服务 | 地址 |
|---|---|---|
| Landslide Backend :8000 | FastAPI 后端 | http://127.0.0.1:8000 |
| Landslide Frontend :5173 | Vite 前端开发服务器 | http://127.0.0.1:5173 |

浏览器打开前端地址：<http://127.0.0.1:5173>

> 注意：两个黑色窗口都是服务器，**都不要关闭**，关了对应服务就停了。

### 方法 B：手动分别启动

窗口 1 —— 后端：

```powershell
cd d:\my\landslide-webgis-platform\backend
.\venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

窗口 2 —— 前端：

```powershell
cd d:\my\landslide-webgis-platform\frontend
npm run dev
```

浏览器访问 <http://127.0.0.1:5173>。前端的 `/api`、`/static` 请求由 Vite 自动代理到 8000 端口
（配置见 `frontend/vite.config.js` 的 `server.proxy`）。

### 备选：单服务模式（只需一个窗口）

前端先构建，再由后端直接托管静态产物：

```powershell
cd frontend
npm run build
cd ..\backend
.\venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

此时浏览器访问 <http://127.0.0.1:8000>，不再需要 5173 端口。

---

## 四、页面使用流程

1. 打开 <http://127.0.0.1:5173>，地图自动加载卫星影像底图
2. 点击 **「载入示例数据」**：自动装配 6 个因子栅格（DEM/Slope/aspect 等）+ 96 个滑坡灾害点 + 研究区边界，并显示投影校验结果；因子栅格图层列表出现，DEM 默认叠加显示，可逐个开关
3. 点击 **「启动训练」**：进度条实时反馈（采样 → 训练 → 评估 → 渲染），约 10 秒完成
4. 训练完成后：渐变分级风险图自动叠加到地图，右侧显示 AUC 等模型指标和各级面积占比
5. **单击地图任意位置**：弹窗显示该点易发性等级、概率值和防护建议
6. **成果导出与删除**（图层渲染卡片底部）：
   - 「导出风险图 PNG」：Canvas 合成风险图 + 渐变色带图例 + 分级占比 + 模型指标，直接下载成图
   - 「下载结果 TIF」：下载带投影的易发性栅格源文件，可在 ArcGIS/QGIS 中继续分析
   - 「删除结果」：经确认后删除训练任务及其全部产物（TIF/PNG/GeoJSON）
   - 因子标签的 × 和样本框右上角 ×：从列表移除并删除服务端上传文件（内置示例数据受保护，仅前端移除）
7. 也可用自己的数据：上传因子栅格（.tif，需带投影坐标）+ 灾害点矢量 + 研究区矢量，再走第 3 步

---

## 五、停止服务

关闭两个黑色控制台窗口即可（后端窗口标题 `Landslide Backend :8000`，前端窗口标题 `Landslide Frontend :5173`）。

---

## 六、常见问题

| 现象 | 原因与处理 |
|---|---|
| 浏览器提示"无法访问 127.0.0.1:5173" | 前端 dev server 没在运行。双击 `start-frontend.bat`（或 `start.bat` 一键拉起两个） |
| 页面能打开但数据加载失败 | 后端 8000 没在运行。双击 `start-backend.bat`，确认窗口显示 `Uvicorn running on http://127.0.0.1:8000` |
| 端口被占用（`address already in use`） | 已有另一个实例在跑，直接访问对应地址即可；或先结束旧的 python/node 进程再启动 |
| 地图底图空白 | 底图瓦片来自外网（ArcGIS/OSM），需要联网；可切换"无底图"模式，风险图仍正常显示 |
| 改了前端代码页面没变化 | 分离模式下 Vite 会自动热更新，保存即生效；若不生效刷新浏览器。单服务模式才需要重新 `npm run build` |
| 上传数据后提示投影/网格不一致 | 检查所有因子栅格是否为同一投影（推荐 EPSG:32647 或统一投影系）且行列数、范围完全对齐 |

---

## 七、主要接口速览

| 接口 | 方式 | 说明 |
|---|---|---|
| `/api/upload`、`/api/upload/batch`、`/api/upload/shapefile` | POST | 上传栅格 / 批量文件 / shp 的 zip 包 |
| `/api/factors/inspect` | POST | 因子投影与网格对齐校验 |
| `/api/factors/overlays` | POST | 因子栅格渲染为地图叠加 PNG |
| `/api/train/start` | POST | 启动异步训练，返回 task_id |
| `/api/train/status/{task_id}` | GET | 轮询训练进度、指标与结果图层 |
| `/api/task/list` | GET | 历史训练任务列表 |
| `/api/result/raster` | GET | 获取结果栅格地址与结果包 |
| `/api/result/query` | GET | 点查询：等级、概率、防护建议 |
| `/api/delete?target=task&task_id=xxx` | DELETE | 删除训练任务及其全部结果产物 |
| `/api/delete?target=file&path=xxx` | DELETE | 删除上传文件（限 uploads 目录，含 shp 边车文件） |
| `/api/demo/dataset` | GET | 一键载入内置示例数据 |

> 删除接口用查询参数而非请求体，规避 DELETE 携带 body 的兼容性问题；
> 文件删除带目录越权校验，`data/raw` 示例数据无法通过接口删除。

---

## 八、目录结构

```
landslide-webgis-platform/
├── start.bat              ← 一键启动脚本
├── backend/               ← FastAPI 后端（同时托管前端页面）
│   ├── venv/              ← Python 虚拟环境
│   ├── main.py            ← API 入口
│   ├── gis_preprocess.py  ← GIS 数据预处理
│   ├── model.py           ← 随机森林模型
│   ├── train_task.py      ← 异步训练任务管理
│   └── result_export.py   ← 栅格重投影/分级渲染/点查询
├── frontend/              ← Vue3 前端
│   ├── src/App.vue        ← 主界面（地图、图层、训练面板、导出与删除）
│   └── dist/              ← 构建产物（单服务模式下由后端托管）
├── data/                  ← 示例 GIS 数据（受保护，不可通过删除接口移除）
└── backend/
    ├── uploads/           ← 用户上传文件（删除接口的允许范围）
    ├── models/            ← 训练好的模型（joblib）
    └── result/            ← 训练结果 TIF / 渲染 PNG / GeoJSON
```

接口文档：<http://127.0.0.1:8000/docs>
