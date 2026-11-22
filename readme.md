# 滑坡易发性评价 WebGIS 平台

前端 Vue3 + Vite + Element Plus + Leaflet，后端 FastAPI + Rasterio/GeoPandas + scikit-learn。
支持 JWT 登录注册、用户管理、因子栅格上传与空间校验、三种模式模型训练（随机森林 / 逻辑回归 / 自定义流水线 SVM，带超参数与特征重要性）、自定义模型上传、异步训练排队、风险图渲染、点查询、成果导出与删除。

提供两种运行方式：

- **方式一（推荐）：Docker 一键部署** —— docker-compose 双容器（backend + nginx frontend），浏览器访问 <http://localhost:8080>
- **方式二：本地开发双进程** —— Vite 前端（5173）+ FastAPI 后端（8000），前端代理 `/api`、`/static` 无跨域；改代码即时热更新

真实空间数据见 `data/raw/`（DEM/Slope/NDVI 等多因子栅格 + 96 个滑坡灾害点 + 研究区边界，随仓库直接入库，克隆即用），完整工程文档见 `docs/`（目录见文末）。

---

## 一、环境要求（首次运行前检查一次即可）

| 依赖 | 版本要求 | 检查命令 |
|---|---|---|
| Python | 3.11+（实测 3.14） | `python --version` |
| Node.js | 18+ | `node --version` |
| Docker Desktop | 4.x+（仅方式一需要） | `docker --version` |

> 后端依赖已按实测版本精确锁定在 `backend/requirements.txt`（SQLAlchemy 2.1.8 要求 Python ≥ 3.11）。

---

## 二、首次部署（只做一次）

### 方式一：Docker（推荐）

```powershell
cd d:\my\landslide-webgis-platform
docker compose up -d --build
```

- 国内网络拉取基础镜像可能超时，`docker/` 已内置 DaoCloud 镜像源与清华 pip 源，详见《系统部署与启动手册》第 8 章
- 数据挂载：`data/raw` 示例数据只读挂载；`uploads`/`models`/`result` 与 SQLite（`data/db`）落宿主机，**容器重启数据不丢**
- 首次构建约 7 分钟（含依赖安装），之后 `docker compose up -d` 秒级启动

### 方式二：本地开发（双进程）

1. 后端环境：

```powershell
cd backend
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

> 如果 `backend\venv` 文件夹已存在，跳过本节。

2. 前端依赖：

```powershell
cd frontend
npm install
```

3. 环境变量：确认 `backend/.env` 存在（JWT 密钥、管理员账号、跨域等，键名见《系统部署与启动手册》）。管理员账号由 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 初始化。

> 分离部署模式下不需要 `npm run build`；`npm run dev` 直接跑源码。
> 仅当使用文末"备选：单服务模式"时才需要构建。

---

## 三、日常启动

### 方式一：Docker

浏览器打开 <http://localhost:8080>（nginx 同源反代 `/api`、`/static`，无跨域）。

### 方式二：本地开发（推荐一键启动）

**双击项目根目录的 `start.bat`**，会自动弹出两个黑色控制台窗口：

| 窗口标题 | 服务 | 地址 |
|---|---|---|
| Landslide Backend :8000 | FastAPI 后端 | http://127.0.0.1:8000 |
| Landslide Frontend :5173 | Vite 前端开发服务器 | http://127.0.0.1:5173 |

浏览器打开前端地址：<http://127.0.0.1:5173>

> 两个黑色窗口都是服务器，**都不要关闭**，关了对应服务就停了。
> 也可手动分别运行 `start-backend.bat`、`start-frontend.bat`。

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

1. 打开页面首先进入**登录页**：已有账号直接登录；首次使用点「注册」创建普通账号；管理员账号见 `backend/.env`
2. 登录后进入主界面，地图自动加载卫星影像底图
3. 点击 **「载入示例数据」**：自动装配 6 个因子栅格（DEM/Slope/aspect 等）+ 96 个滑坡灾害点 + 研究区边界，并显示投影校验结果
4. **训练面板三种模式**：
   - 随机森林 / 逻辑回归（`model_type`）：可调超参数（负正样本比 `neg_ratio`、树数 `n_estimators`、正则 `lr_C` 等）
   - 自定义流水线（`pipeline_config`）：标准化 / PCA + 随机森林 / SVM（`svm_C`、`svm_kernel`）/ 逻辑回归自由组合
   - 上传自定义模型：`joblib` 模型文件（如 `custom_model_test.joblib`），按文件名清洗后落盘 `models/`，可被训练引用
5. 点击 **「启动训练」**：进度条实时反馈（采样 → 训练 → 评估 → 渲染），约 10 秒完成；多任务并发提交时自动排队（最大同时训练 2 个）
6. 训练完成后：渐变分级风险图自动叠加，右侧显示 AUC 等指标、**特征重要性**（卡片右上「下载图片」可导出图表 PNG）和各级面积占比
7. **单击地图任意位置**：弹窗显示该点易发性等级、概率值和防护建议
8. **成果导出与删除**（图层渲染卡片底部）：
   - 「导出风险图 PNG」：Canvas 合成风险图 + 渐变色带图例 + 分级占比 + 模型指标
   - 「下载结果 TIF」：带投影的易发性栅格源文件，可在 ArcGIS/QGIS 继续分析
   - 「删除结果」：经确认后删除训练任务及其全部产物（TIF/PNG/GeoJSON）
   - 因子标签的 × 和样本框右上角 ×：从列表移除并删除服务端上传文件（内置示例数据受保护，仅前端移除）
9. 也可用自己的数据：上传因子栅格（.tif，需带投影坐标）+ 灾害点矢量 + 研究区矢量，再走第 5 步；上传文件按用户隔离存储（`uploads/{用户ID}/`）
10. **右上角「退出登录」**；管理员账号额外可见 **「用户管理」** 面板（用户列表、改角色、删除用户）

---

## 五、停止服务

- **Docker**：`docker compose down`（数据在挂载目录，下次 `up` 保留）
- **本地开发**：关闭两个黑色控制台窗口（`Landslide Backend :8000` / `Landslide Frontend :5173`）

---

## 六、常见问题

| 现象 | 原因与处理 |
|---|---|
| 浏览器提示"无法访问 127.0.0.1:5173" | 前端 dev server 没在运行。双击 `start-frontend.bat`（或 `start.bat` 一键拉起两个） |
| 页面能打开但数据加载失败 | 后端没在运行。双击 `start-backend.bat`，确认窗口显示 `Uvicorn running on http://127.0.0.1:8000`；Docker 模式先 `docker compose ps` 看两个容器是否 Up |
| 登录失败 / 提示 401 未登录 | 账号密码错误或登录态过期，重新登录；管理员初始账号见 `backend/.env` |
| 训练按钮提示"排队中（前方 N 个任务）" | 并发闸门限制最大同时训练数为 2，属于正常限流，等待前面任务完成即可 |
| `docker compose build` 拉镜像超时 | 国内网络直连 Docker Hub 不稳定，按《系统部署与启动手册》第 8 章换 DaoCloud 镜像源重试 |
| 要用 SVM 但训练提示不支持 | `model_type` 只接受 `randomforest` / `logistic`（设计行为）；SVM 走「自定义流水线」（`pipeline_config.algorithm='svm'`） |
| 端口被占用（`address already in use`） | 已有另一个实例在跑，直接访问对应地址即可；或先结束旧的 python/node 进程再启动 |
| 地图底图空白 | 底图瓦片来自外网（ArcGIS/OSM），需要联网；可切换"无底图"模式，风险图仍正常显示 |
| 改了前端代码页面没变化 | 分离模式下 Vite 自动热更新，保存即生效；单服务 / Docker 模式需重新构建 |
| 上传数据后提示投影/网格不一致 | 所有因子栅格须同一投影（推荐 EPSG:32647）且行列数、范围完全对齐 |

> 更多条目见 `docs/04-部署与运维/常见问题排查手册.md`（A~F 六类 68 条）。

---

## 七、主要接口速览

| 接口 | 方式 | 说明 |
|---|---|---|
| `/api/auth/register`、`/api/auth/login`、`/api/auth/me` | POST/GET | 注册、登录（返回 JWT）、当前用户信息 |
| `/api/users`、`/api/users/{user_id}` | GET/PATCH/DELETE | 用户管理（仅 admin） |
| `/api/upload`、`/api/upload/batch`、`/api/upload/shapefile` | POST | 上传栅格 / 批量文件 / shp 的 zip 包（按用户隔离目录） |
| `/api/model/upload` | POST | 上传自定义模型（joblib） |
| `/api/factors/inspect` | POST | 因子投影与网格对齐校验 |
| `/api/factors/overlays` | POST | 因子栅格渲染为地图叠加 PNG |
| `/api/train/start` | POST | 启动异步训练（`model_type` / `pipeline_config` / `params` 超参数），返回 task_id |
| `/api/train/status/{task_id}` | GET | 轮询训练进度、指标、特征重要性与结果图层 |
| `/api/task/list` | GET | 历史训练任务列表 |
| `/api/result/raster` | GET | 获取结果栅格地址与结果包 |
| `/api/result/query` | GET | 点查询：等级、概率、防护建议 |
| `/api/delete?target=task&task_id=xxx` | DELETE | 删除训练任务及其全部结果产物 |
| `/api/delete?target=file&path=xxx` | DELETE | 删除上传文件（限 uploads 目录，含 shp 边车文件） |
| `/api/demo/dataset` | GET | 一键载入内置示例数据 |

> 除登录注册外均需请求头携带 JWT；删除接口用查询参数而非请求体，规避 DELETE 携带 body 的兼容性问题；
> 文件删除带目录越权校验，`data/raw` 示例数据无法通过接口删除；非 admin 只能使用自己目录或示例数据中的文件训练。
> 交互式接口文档（Swagger）：本地模式 <http://127.0.0.1:8000/docs>（Docker 模式下 nginx 仅暴露 `/api`、`/static`，Swagger 不对外）。

---

## 八、目录结构

```
landslide-webgis-platform/
├── start.bat / start-backend.bat / start-frontend.bat   ← 本地一键/分别启动
├── docker-compose.yml          ← Docker 双容器编排（backend + frontend）
├── docker/                     ← Dockerfile.backend / Dockerfile.frontend / nginx.conf
├── backend/                    ← FastAPI 后端
│   ├── main.py                 ← 业务 API 入口（上传/训练/查询/导出/删除/示例数据）
│   ├── routers/                ← auth.py（登录注册 JWT）、users.py（用户管理）
│   ├── security.py / database.py / db_models.py / config.py  ← 认证、SQLAlchemy(WAL)、配置
│   ├── algorithms.py           ← 自定义训练流水线（标准化/PCA/RF/SVM/LR）
│   ├── gis_preprocess.py       ← GIS 预处理（投影统一 EPSG:32647、网格对齐）
│   ├── model.py                ← 模型训练与超参数落盘（joblib）
│   ├── train_task.py           ← 异步训练任务（并发闸门 + 排队提示）
│   ├── result_export.py        ← 栅格重投影/分级渲染/点查询
│   └── requirements.txt        ← 依赖精确版本锁
├── frontend/                   ← Vue3 前端
│   ├── src/views/Login.vue     ← 登录/注册页
│   ├── src/views/Home.vue      ← 主界面（地图、图层、训练面板、导出、用户管理）
│   └── dist/                   ← 构建产物（Docker/nginx 或单服务模式托管）
├── data/raw/                   ← 真实空间数据（受保护，不可通过删除接口移除）
├── docs/                       ← 全生命周期文档（见下节导航）
└── backend/uploads|models|result  ← 用户上传 / 训练模型 / 结果产物（Docker 挂载持久化）
```

---

## 九、文档导航

| 文档 | 位置 |
|---|---|
| 文档总目录 | `docs/README.md` |
| 需求分析 | `docs/01-需求分析/需求分析说明书.md` |
| 系统设计（概要/详细、API、数据库） | `docs/02-系统设计/` |
| 测试与安全（121 条用例、四轮系统测试报告） | `docs/03-测试与安全/` |
| 部署与运维（部署手册、运维、FAQ 68 条） | `docs/04-部署与运维/` |
| AI 与项目管理（AI协作开发日志、AI错误案例集） | `docs/05-AI与项目管理/` |
| 空间逻辑校验 | `docs/06-空间逻辑校验/` |
