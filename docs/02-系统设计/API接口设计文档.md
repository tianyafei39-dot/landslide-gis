# 滑坡易发性评价 WebGIS 平台 —— API 接口设计文档

| 项目名称 | 滑坡易发性评价 WebGIS 平台 |
|---|---|
| 文档编号 | LS-WGIS-API-001 |
| 版本 | V1.3 |
| 编写日期 | 2026-11-16（V1.0）；2026-11-18 修订至 V1.2（V1.1 功能同步、V1.2 并发承载）；2026-11-19 修订至 V1.3（model_type='svm' 设计澄清、Base URL 同源路径约定） |
| 文档状态 | 正式发布 |
| 实现依据 | `backend/main.py`、`backend/routers/auth.py`、`backend/result_export.py` |

---

## 1 引言

### 1.1 编写目的

本文档定义滑坡易发性评价 WebGIS 平台前后端交互的全部 RESTful 接口，包括请求方法、路径、参数、响应结构、错误码与调用示例，作为前后端联调、测试用例编写与验收的接口依据。

### 1.2 接口总览

| 分组 | 接口 | 方法 | 鉴权 |
|---|---|---|---|
| 认证 | /api/auth/login | POST | 否 |
| 认证 | /api/auth/register | POST | 否 |
| 认证 | /api/auth/me | GET | 是 |
| 用户管理 | /api/users | GET | 是（admin） |
| 用户管理 | /api/users | POST | 是（admin） |
| 用户管理 | /api/users/{user_id} | PATCH | 是（admin） |
| 用户管理 | /api/users/{user_id} | DELETE | 是（admin） |
| 数据上传 | /api/upload | POST | 是 |
| 数据上传 | /api/upload/batch | POST | 是 |
| 数据上传 | /api/upload/shapefile | POST | 是 |
| 模型上传 | /api/model/upload | POST | 是 |
| 数据校验 | /api/factors/inspect | POST | 是 |
| 数据校验 | /api/factors/overlays | POST | 是 |
| 训练 | /api/train/start | POST | 是 |
| 训练 | /api/train/status/{task_id} | GET | 是 |
| 任务 | /api/task/list | GET | 是 |
| 结果 | /api/result/raster | GET | 是 |
| 结果 | /api/result/query | GET | 是 |
| 删除 | /api/delete | DELETE | 是 |
| 示例 | /api/demo/dataset | GET | 是 |
| 静态资源 | /static/{filename} | GET | 否 |

---

## 2 通用约定

### 2.1 通信约定

| 项 | 约定 |
|---|---|
| Base URL | 开发模式经 Vite 代理同源访问（`/api`、`/static`）；Docker 模式经 nginx 反代（http://localhost:8080）。前端统一用**同源相对路径**请求，不硬编码后端地址 |
| 数据格式 | 请求与响应均为 `application/json`（文件上传除外，为 `multipart/form-data`） |
| 字符编码 | UTF-8 |
| 响应压缩 | GZipMiddleware 生效：响应体 ≥1KB 自动 gzip（请求头带 `Accept-Encoding: gzip` 时），大 JSON（result_bundle）省带宽 |
| 静态缓存 | `/static/*`（PNG/TIF/GeoJSON）返回 `Cache-Control: public, max-age=86400`，文件名含 task_id/哈希天然不可变，浏览器缓存 1 天 |
| 在线文档 | `http://127.0.0.1:8000/docs`（Swagger UI，FastAPI 自动生成） |

### 2.2 鉴权约定

1. 登录接口免鉴权；**其余全部接口需携带 JWT**；
2. 请求头格式：`Authorization: Bearer <access_token>`；
3. 令牌过期/无效/缺失统一返回 `401`，`detail` 为"登录已过期，请重新登录"；
4. 数据隔离：非 admin 用户只能访问 `user_id` 属于自己的任务与 `uploads/{user_id}/` 目录下的文件，越权返回 `403`。

### 2.3 路径约定

1. 上传/训练类接口中出现的文件路径，均为**服务端绝对路径**（上传接口返回，前端原样回传）；
2. 后端 `_abs()` 兼容相对路径（按 `backend/` 目录解析），但约定统一传绝对路径；
3. 静态资源（PNG/GeoJSON/结果 TIF）统一以 `/static/{文件名}` 访问，由后端挂载 `backend/result/` 目录提供。

### 2.4 通用错误响应

```json
{ "detail": "错误描述（面向用户的可读中文）" }
```

| 状态码 | 含义 | 典型场景 |
|---|---|---|
| 200 | 成功 | — |
| 400 | 请求/数据错误 | 文件格式错误、栅格未对齐、任务未完成、zip 损坏 |
| 401 | 未认证 | 令牌缺失/过期/无效、登录失败 |
| 403 | 越权 | 访问他人任务/文件、删除 uploads 外文件 |
| 404 | 不存在 | 任务不存在、文件不存在 |
| 409 | 冲突 | 删除运行中的任务 |
| 422 | 参数校验失败 | 缺 task_id/path、请求体为空、经纬度超范围 |

---

## 3 认证与用户管理接口

### 3.1 用户登录

`POST /api/auth/login`（免鉴权）

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| username | string | 是 | 用户名 |
| password | string | 是 | 密码（明文传输，服务端 bcrypt 比对） |

```json
{ "username": "admin", "password": "******" }
```

**成功响应（200）：**

| 字段 | 类型 | 说明 |
|---|---|---|
| access_token | string | JWT 访问令牌（HS256，有效期默认 480 分钟） |
| token_type | string | 固定 "bearer" |
| user | object | {id, username, role}，role 为 admin/user |

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "user": { "id": 1, "username": "admin", "role": "admin" }
}
```

**错误响应：**

| 状态码 | detail | 场景 |
|---|---|---|
| 401 | 用户名或密码错误 | 账号不存在或密码错 |
| 401 | 账号已禁用 | is_active=false |

### 3.2 查询当前用户

`GET /api/auth/me`（需鉴权）

**请求头：** `Authorization: Bearer <token>`

**成功响应（200）：**

```json
{ "id": 1, "username": "admin", "role": "admin" }
```

### 3.3 用户注册

`POST /api/auth/register`（无需鉴权）

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| username | string | 是 | 用户名（全局唯一） |
| password | string | 是 | 口令（经 bcrypt 哈希存储） |

**成功响应（200）：**

```json
{ "msg": "注册成功，请登录" }
```

**错误码：** 用户名已存在时返回 400。

### 3.4 用户列表（admin）

`GET /api/users`（需 admin）

**成功响应（200）：**

```json
[{ "id": 1, "username": "admin", "role": "admin", "is_active": true }]
```

非 admin 调用返回 403。

### 3.5 创建用户（admin）

`POST /api/users`（需 admin）

**请求体：** `{ "username": "u1", "password": "p123456", "role": "user" }`（role 仅 admin/user，默认 user）

**成功响应（200）：** `{ "id": 5, "username": "u1", "role": "user", "is_active": true }`

**错误码：** 400（用户名已存在 / 角色非法）。

### 3.6 修改用户角色（admin）

`PATCH /api/users/{user_id}`（需 admin）

**请求体：** `{ "role": "admin" | "user" }`

**成功响应（200）：** `{ "msg": "角色修改成功" }`

**错误码：** 400（改自己的角色——防失去管理权限 / 角色非法）、404（用户不存在）。

### 3.7 删除用户（admin）

`DELETE /api/users/{user_id}`（需 admin）

**成功响应（200）：** `{ "msg": "用户删除成功" }`

**错误码：** 400（删除自己）、404（用户不存在）。删除为物理删除。

---

## 4 数据上传接口

> 三个数据上传接口均需鉴权；返回的 `path` 为服务端绝对路径，供训练/校验接口使用。模型上传接口（4.4）返回 `model_path`，供训练接口的 `custom_model_path` 使用。

### 4.1 上传因子栅格（兼容单/多文件）

`POST /api/upload`（multipart/form-data）

**表单字段：**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| file | file | 二选一 | 单文件（.tif 或 .zip） |
| files | file[] | 二选一 | 多文件 |

**处理逻辑：** 文件保存至 `uploads/{user_id}/{uuid}/`；若为 .zip 自动解压并收集内部 .shp（单层子目录自动抹平）。

**成功响应（200）：**

| 字段 | 类型 | 说明 |
|---|---|---|
| upload_dir | string | 本次上传目录 |
| files | array | [{filename, path, from_zip?}]，from_zip 标记来自哪个 zip |
| msg | string | "成功上传 N 个文件" |

```json
{
  "upload_dir": "D:\\...\\backend\\uploads\\1\\3f2a...",
  "files": [
    { "filename": "DEM.tif", "path": "D:\\...\\uploads\\1\\3f2a...\\DEM.tif" }
  ],
  "msg": "成功上传 1 个文件"
}
```

**错误响应：** 400 "未接收到任何文件，请使用 file 或 files 字段上传"。

### 4.2 批量上传因子栅格

`POST /api/upload/batch`（multipart/form-data）

**表单字段：** `files`（file[]，必填）

**成功响应（200）：** 与 4.1 相同结构（files 不含 from_zip）。

### 4.3 上传 Shapefile（zip 包）

`POST /api/upload/shapefile`（multipart/form-data）

**表单字段：** `file`（file，必填，.zip 格式，内含 shp/dbf/shx/prj 等）

**处理逻辑：** 校验 .zip 后缀 → 解压 → 抹平单层子目录 → 全目录搜索 .shp。

**成功响应（200）：**

| 字段 | 类型 | 说明 |
|---|---|---|
| shp_path | string | 解压后 .shp 的绝对路径 |
| upload_dir | string | 解压目录 |
| msg | string | "Shapefile 上传并解压成功" |

```json
{
  "shp_path": "D:\\...\\uploads\\1\\8c1d...\\disaster-site.shp",
  "upload_dir": "D:\\...\\uploads\\1\\8c1d...",
  "msg": "Shapefile 上传并解压成功"
}
```

**错误响应：**

| 状态码 | detail | 场景 |
|---|---|---|
| 400 | 请上传 ZIP 格式的 Shapefile 压缩包 | 后缀非 .zip |
| 400 | ZIP 文件损坏或格式不正确 | 解压失败 |
| 400 | ZIP 中未找到 .shp 文件 | 无 shp |
| 400 | ZIP 中有多个 .shp 文件，请只放一个：[…] | 多 shp |

---

### 4.4 上传自定义模型

`POST /api/model/upload`（需鉴权，multipart/form-data）

**请求参数：**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| file | file | 是 | 模型文件，仅支持 .joblib / .pkl（sklearn 分类模型，须含 predict_proba） |

服务端保存到 `backend/uploads/{user_id}/models/` 下（文件名经清洗只保留纯文件名，防路径穿越），返回绝对路径供训练接口的 `custom_model_path` 使用。

**成功响应（200）：**

```json
{
  "model_path": "D:\\...\\backend\\uploads\\1\\models\\custom_model_test.joblib",
  "msg": "模型上传成功"
}
```

**错误码：**

| 状态码 | 场景 |
|---|---|
| 400 | 后缀不是 .joblib/.pkl，或文件名不合法 |
| 401 | 未携带令牌 |

---

## 5 数据校验与渲染接口

### 5.1 因子投影与网格对齐校验

`POST /api/factors/inspect`

**请求体：**

```json
{ "factor_files": ["D:\\...\\DEM.tif", "D:\\...\\Slope.tif"] }
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| factor_files | string[] | 是 | 因子栅格路径列表 |

**成功响应（200）：**

| 字段 | 类型 | 说明 |
|---|---|---|
| aligned | bool | 全部因子 shape/transform/crs 是否一致 |
| crs | string | 参考投影（如 "EPSG:32647"） |
| shape | [h, w] | 参考栅格行列数 |
| factor_count | int | 因子数量 |
| factors | array | 每因子：{name, path, crs, shape, resolution, nodata, value_range} |
| bounds_wgs84 | object | {west, south, east, north}，参考栅格 WGS84 边界 |

```json
{
  "aligned": true,
  "crs": "EPSG:32647",
  "shape": [620, 780],
  "factor_count": 6,
  "factors": [
    {
      "name": "DEM.tif",
      "path": "D:\\...\\DEM.tif",
      "crs": "EPSG:32647",
      "shape": [620, 780],
      "resolution": [30.0, 30.0],
      "nodata": -9999.0,
      "value_range": [120.5, 2310.8]
    }
  ],
  "bounds_wgs84": { "west": 100.12, "south": 25.34, "east": 100.56, "north": 25.71 }
}
```

**错误响应：** 400（未提供因子栅格 / 文件不存在 / 栅格解析失败）。

### 5.2 因子栅格渲染为地图叠加层

`POST /api/factors/overlays`

**请求体：** 同 5.1（factor_files）。

**成功响应（200）：**

| 字段 | 类型 | 说明 |
|---|---|---|
| overlays | array | 每因子叠加元数据，见下 |
| count | int | 叠加层数量 |

overlays 单项结构：

| 字段 | 类型 | 说明 |
|---|---|---|
| name | string | 因子名 |
| path | string | 源文件路径 |
| png_url | string | 渲染 PNG 地址（/static/factor_{md5}.png，viridis 色带） |
| bounds | object | {west, south, east, north} |
| size | {width, height} | PNG 像素尺寸 |
| value_range | [min, max] \| null | 数值范围（抽样统计） |

**错误响应：** 400（文件不存在 / 因子渲染失败）。

---

## 6 训练接口

### 6.1 启动异步训练

`POST /api/train/start`

**请求体**（`TrainStartRequest`，兼容单对象或单元素数组）：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| factor_files | string[] | 是 | 因子栅格路径列表（顺序即特征顺序） |
| sample_shp | string | 是 | 滑坡灾害点 shp 路径 |
| study_area_shp | string | 否 | 研究区 shp 路径（null 表示不限） |
| model_type | string | 否 | "randomforest"（默认）或 "logistic"。**不接受 "svm"**（设计行为，非缺陷）：SVM 仅在 `pipeline_config.algorithm='svm'` 时启用，传统模式仅 RF/LR |
| custom_model_path | string | 否 | 上传模型的绝对路径（来自 /api/model/upload）。提供时**跳过训练**直接加载模型预测，模型须含 predict_proba；文件不存在则任务失败（不静默回退） |
| pipeline_config | object | 否 | 搭积木配置 {preprocessor, reducer, algorithm}。preprocessor: none/standard/minmax；reducer: none/pca（PCA 保留 95% 方差）；algorithm: randomforest/svm/logistic。与 custom_model_path 二选一，custom_model_path 优先 |
| params | object | 否 | 超参数字典，见下表 |

**params 超参数：**

| 键 | 类型 | 默认 | 生效条件 | 说明 |
|---|---|---|---|---|
| neg_ratio | number | 3.0 | 所有模式 | 负:正样本比例（1~10） |
| n_estimators | int | 100 | randomforest（传统/pipeline） | 决策树数量 |
| lr_C | number | 1.0 | logistic（传统/pipeline） | L2 正则强度倒数 |
| svm_C | number | 1.0 | pipeline 的 svm | 惩罚系数 |
| svm_kernel | string | "rbf" | pipeline 的 svm | 核函数（rbf/linear/poly/sigmoid） |

```json
{
  "factor_files": ["D:\\...\\DEM.tif", "D:\\...\\Slope.tif", "D:\\...\\aspect.tif"],
  "sample_shp": "D:\\...\\disaster-site.shp",
  "study_area_shp": "D:\\...\\researcharea.shp",
  "model_type": "randomforest",
  "custom_model_path": null,
  "pipeline_config": null,
  "params": { "neg_ratio": 3, "n_estimators": 100 }
}
```

**处理逻辑：** 路径权限校验（非 admin 的全部路径——因子/样本/研究区/**自定义模型**——须位于 `uploads/{user_id}/` 或内置示例目录 `data/raw/`）→ 创建任务（记录 user_id 与 params）→ 后台线程启动训练 → 立即返回。训练时按优先级选择模型源：① custom_model_path 直接加载；② pipeline_config 动态组装 Pipeline 并 fit；③ 传统 RF/LR 按 params 调参训练。全部路径经 `_abs` 规范化。

**成功响应（200）：**

```json
{ "task_id": "5f3c2a1e-8b4d-4e2f-9a7c-1d2e3f4a5b6c" }
```

**错误响应：**

| 状态码 | detail | 场景 |
|---|---|---|
| 403 | 无权使用他人的数据文件 | 路径不在本人目录 |
| 422 | 请求体不能为空 | 空数组 |

### 6.2 查询训练进度

`GET /api/train/status/{task_id}`

**路径参数：** `task_id`（string，任务 ID）

**成功响应（200）：**

| 字段 | 类型 | 说明 |
|---|---|---|
| task_id | string | 任务 ID |
| user_id | int | 发起人 |
| status | string | waiting / running / finished / failed（waiting 含排队中：并发闸门已满时任务等待空闲槽位） |
| progress | number | 0~100 |
| msg | string | 阶段文案 / 排队提示 / 错误信息 |
| result_raster_path | string | 结果 TIF 路径（完成后非空） |
| metrics | object \| null | {AUC, Accuracy, Precision, Recall, F1, feature_importances}，完成后非空 |
| result | object \| null | 结果包 result_bundle（完成后非空），见附录 A |
| tif_url | string | 结果 TIF 静态地址（完成时为 /static/...，否则 ""） |

训练中示例：

```json
{
  "task_id": "5f3c2a1e-...",
  "user_id": 1,
  "status": "running",
  "progress": 40.0,
  "msg": "训练随机森林模型",
  "result_raster_path": "",
  "metrics": null,
  "result": null,
  "tif_url": ""
}
```

排队中示例（并发闸门已满，V1.2 新增）：

```json
{
  "task_id": "8a1b2c3d-...",
  "user_id": 2,
  "status": "waiting",
  "progress": 0.0,
  "msg": "排队中（前方 1 个任务），等待空闲训练资源",
  "result_raster_path": "",
  "metrics": null,
  "result": null,
  "tif_url": ""
}
```

完成后示例（节选）：

```json
{
  "status": "finished",
  "progress": 100.0,
  "msg": "训练完成，滑坡风险图已生成",
  "metrics": { "AUC": 0.9132, "Accuracy": 0.8521, "Precision": 0.8103, "Recall": 0.7945, "F1": 0.8023 },
  "tif_url": "/static/landslide_susceptibility_5f3c2a1e-....tif",
  "result": { "overlay": {}, "vectors": {}, "spatial_check": {} }
}
```

**进度语义（与后端 `_progress_msg` 一致）：**

| status / progress | msg |
|---|---|
| waiting / 0 | 任务已创建，等待开始 |
| waiting（闸门满） | 排队中（前方 N 个任务），等待空闲训练资源 |
| running / <10 | 读取并校验因子栅格（投影 / 网格对齐） |
| running / <25 | 自动采样滑坡正样本与非滑坡负样本 |
| running / <40 | 划分训练集与验证集 |
| running / <70 | 训练随机森林模型 |
| running / <85 | 评估模型精度（AUC / 准确率 / 召回率） |
| running / <100 | 全区预测并生成分级渲染图层 |
| finished / 100 | 训练完成，滑坡风险图已生成 |

**错误响应：**

| 状态码 | detail | 场景 |
|---|---|---|
| 403 | 无权查看该任务 | 非发起人且非 admin |
| 200 + status=not_found | msg: 任务不存在 | 任务 ID 无效（以业务字段表达） |

**轮询建议：** 前端每 900ms 轮询一次，status 为 waiting/running 时继续，finished/failed 终止。

---

## 7 任务接口

### 7.1 历史训练任务列表

`GET /api/task/list`

**成功响应（200）：**

| 字段 | 类型 | 说明 |
|---|---|---|
| tasks | array | 任务摘要列表；admin 返回全部，普通用户仅返回自己的 |

tasks 单项：`{task_id, user_id, status, progress, msg, metrics}`

```json
{
  "tasks": [
    {
      "task_id": "5f3c2a1e-...",
      "user_id": 1,
      "status": "finished",
      "progress": 100.0,
      "msg": "训练完成，滑坡风险图已生成",
      "metrics": { "AUC": 0.9132, "Accuracy": 0.8521, "Precision": 0.8103, "Recall": 0.7945, "F1": 0.8023 }
    }
  ]
}
```

---

## 8 结果接口

### 8.1 获取结果栅格与结果包

`GET /api/result/raster`

**查询参数：** `task_id`（string，必填）

**成功响应（200）：**

| 字段 | 类型 | 说明 |
|---|---|---|
| raster_path | string | 结果 TIF 绝对路径 |
| tif_url | string | /static/{文件名} 下载地址 |
| result | object | 结果包 result_bundle（见附录 A） |

**错误响应：** 404 任务不存在；403 无权查看该任务结果；400 任务未完成。

### 8.2 点查询易发性

`GET /api/result/query`

**查询参数：**

| 参数 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| task_id | string | 是 | — | 任务 ID |
| lat | float | 是 | -90 ~ 90 | 纬度（WGS84） |
| lng | float | 是 | -180 ~ 180 | 经度（WGS84） |

**成功响应（200）——有效点：**

| 字段 | 类型 | 说明 |
|---|---|---|
| inside | bool | true |
| valid | bool | true |
| lat / lng | float | 查询坐标 |
| pixel | object | {row, col, lat, lng} 像元位置与中心经纬度 |
| key | string | 分级键：very_low/low/moderate/high/very_high |
| name | string | 等级名：极低/低/中/高/极高易发 |
| min / max | float | 该级值域 |
| color | string | 该级配色 |
| value | float | 易发性概率（0~1） |
| advice | string | 防护建议文案 |

```json
{
  "inside": true,
  "valid": true,
  "lat": 25.52,
  "lng": 100.31,
  "pixel": { "row": 312, "col": 450, "lat": 25.5201, "lng": 100.3102 },
  "key": "high",
  "name": "高易发",
  "min": 0.6,
  "max": 0.8,
  "color": "#fdae61",
  "value": 0.6723,
  "advice": "建议列为重点防范区域，加密日常巡查频次。"
}
```

**成功响应（200）——出界/无值（业务正常，非 HTTP 错误）：**

```json
{ "inside": false, "lat": 25.1, "lng": 100.1, "msg": "该位置超出结果栅格覆盖范围" }
```

```json
{ "inside": true, "valid": false, "lat": 25.52, "lng": 100.31, "msg": "该像元无有效易发性值（数据缺失或不在研究区）" }
```

**错误响应：** 404 任务不存在；403 无权查询该任务结果；400 任务未完成；422 经纬度超范围。

---

## 9 删除接口

### 9.1 删除训练任务 / 上传文件

`DELETE /api/delete`（查询参数传参，规避 DELETE 携带 body 的兼容性问题）

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| target | string | 是 | "task" 或 "file" |
| task_id | string | target=task 时必填 | 任务 ID |
| path | string | target=file 时必填 | 文件/目录路径（服务端路径） |

**删除任务（target=task）成功响应（200）：**

```json
{
  "success": true,
  "target": "task",
  "task_id": "5f3c2a1e-...",
  "deleted_files": ["landslide_susceptibility_5f3c2a1e-....tif", "susceptibility_5f3c2a1e-....png", "points_5f3c2a1e-....geojson"],
  "msg": "任务 5f3c2a1e-... 已删除，清理产物 3 个"
}
```

**删除文件（target=file）成功响应（200）：**

```json
{
  "success": true,
  "target": "file",
  "deleted_files": ["disaster-site.shp", "disaster-site.shx", "disaster-site.dbf", "disaster-site.prj"],
  "msg": "已删除 4 个文件"
}
```

> 删除 .shp 时级联清理同名边车文件：.shx / .dbf / .prj / .cpg / .sbn / .sbx / .qpj / .shp.xml。

**安全约束：**

1. 文件删除仅限 `backend/uploads/` 目录内（`data/raw` 示例数据不可删）；
2. 非 admin 仅能删除 `uploads/{user_id}/` 内的文件；
3. 运行中任务不可删除。

**错误响应：**

| 状态码 | detail | 场景 |
|---|---|---|
| 422 | 删除任务必须提供 task_id / 删除文件必须提供 path | 参数缺失 |
| 404 | 任务不存在或已被删除 / 文件不存在或已被删除 | 目标不存在 |
| 403 | 无权删除该任务 / 无权删除他人的文件 / 仅允许删除上传目录内的文件 | 越权 |
| 409 | 任务正在运行，无法删除，请等待训练结束 | 运行中删除 |

---

## 10 示例数据接口

### 10.1 一键载入内置示例数据

`GET /api/demo/dataset`（需鉴权）

**成功响应（200）：**

| 字段 | 类型 | 说明 |
|---|---|---|
| factor_files | string[] | 6 个示例因子绝对路径（DEM/Slope/aspect/plan_cur/curvature/NDVI） |
| sample_shp | string | 96 个滑坡灾害点 shp |
| study_area_shp | string \| null | 研究区 shp |
| msg | string | 载入说明 |

```json
{
  "factor_files": ["D:\\...\\data\\raw\\DEM.tif", "D:\\...\\data\\raw\\Slope.tif"],
  "sample_shp": "D:\\...\\data\\raw\\disaster-site\\disaster-site.shp",
  "study_area_shp": "D:\\...\\data\\raw\\researcharea\\researcharea.shp",
  "msg": "已载入示例数据（研究区 + 滑坡灾害点 + 6 个因子栅格）"
}
```

**错误响应：** 404 "内置示例数据缺失，请手动上传数据"（data/raw 不完整时）。

---

## 11 静态资源接口

`GET /static/{filename}`（免鉴权）

由后端 `StaticFiles` 挂载 `backend/result/` 提供，资源类型包括：

| 资源 | 文件名模式 | 用途 |
|---|---|---|
| 风险图渲染 PNG | susceptibility_{task_id}.png | 前端 ImageOverlay 叠加 |
| 因子叠加 PNG | factor_{md5}.png | 因子图层开关 |
| 灾害点 GeoJSON | points_{task_id}.geojson | 矢量点图层 |
| 研究区 GeoJSON | study_area_{task_id}.geojson | 边界图层 |
| 结果 TIF | landslide_susceptibility_{task_id}.tif | 成果下载 |

---

## 12 附录 A：result_bundle 结构（训练结果包）

`GET /api/train/status` 的 `result` 字段、`GET /api/result/raster` 的 `result` 字段：

```json
{
  "overlay": {
    "png_url": "/static/susceptibility_xxx.png",
    "tif_url": "/static/landslide_susceptibility_xxx.tif",
    "bounds": { "west": 100.12, "south": 25.34, "east": 100.56, "north": 25.71 },
    "size": { "width": 1200, "height": 960 },
    "crs": "EPSG:32647",
    "source_shape": [620, 780],
    "pixel_size": [30.0, 30.0],
    "legend": {
      "breaks": [0.2, 0.4, 0.6, 0.8],
      "classes": [
        { "key": "very_low", "name": "极低易发", "min": 0.0, "max": 0.2, "color": "#2c7bb6" },
        { "key": "low", "name": "低易发", "min": 0.2, "max": 0.4, "color": "#7fcdbb" },
        { "key": "moderate", "name": "中易发", "min": 0.4, "max": 0.6, "color": "#ffffb2" },
        { "key": "high", "name": "高易发", "min": 0.6, "max": 0.8, "color": "#fdae61" },
        { "key": "very_high", "name": "极高易发", "min": 0.8, "max": 1.0, "color": "#d7191c" }
      ],
      "gradient": { "stops": [0.0, 0.2, 0.4, 0.6, 0.8, 1.0], "colors": ["#2c7bb6", "#7fcdbb", "#ffffb2", "#fdae61", "#d7191c", "#7f0000"] }
    },
    "class_stats": [
      { "key": "very_low", "name": "极低易发", "min": 0.0, "max": 0.2, "color": "#2c7bb6", "count": 12000, "percent": 32.5 }
    ],
    "value_stats": { "min": 0.01, "max": 0.98, "mean": 0.31, "total_pixels": 36000 }
  },
  "vectors": {
    "points": { "url": "/static/points_xxx.geojson", "count": 96 },
    "study_area": { "url": "/static/study_area_xxx.geojson", "count": 1 }
  },
  "spatial_check": { "checks": [] }
}
```

**要点：**
1. `bounds` 为 WGS84 经纬度，前端 `L.imageOverlay(png_url, bounds)` 精确贴图；
2. `legend.classes` 与点查询返回的分级字段同源；
3. `class_stats.percent` 为研究区内分级面积占比（基于原始投影栅格统计）。

---

## 13 附录 B：metrics 结构（模型指标）

```json
{
  "AUC": 0.9132,
  "Accuracy": 0.8521,
  "Precision": 0.8103,
  "Recall": 0.7945,
  "F1": 0.8023,
  "feature_importances": { "DEM": 0.4121, "Slope": 0.2712, "aspect": 0.1123, "plan_cur": 0.0831, "curvature": 0.0698, "NDVI": 0.0515 }
}
```

AUC/Accuracy/Precision/Recall/F1 均为验证集（test_size=0.3，分层抽样）上计算，保留 4 位小数；AUC 为主指标。

**feature_importances**：各因子重要性，按值降序的字典，保留 4 位小数。提取规则：

- 随机森林 / 含 feature_importances_ 的分类器 → `feature_importances_`
- 逻辑回归 / 含 coef_ 的线性模型 → `|coef_[0]|` 归一化
- 其他（如 SVM 无 coef 多分类）→ 全 0 占位
- 自定义模型（joblib 加载）与 Pipeline 取末级分类器的属性；提取失败时该键为空字典（不阻断训练）

---

*文档结束*
