# AI 错误案例集

| 项目 | 内容 |
|---|---|
| 文档编号 | LS-AI-ERR-001 |
| 版本 | V1.3 |
| 编写日期 | 2026-11-16（V1.0）；2026-11-18 修订至 V1.2（新增 EC-09）；2026-11-19 修订至 V1.3（新增 EC-10/EC-11，共 11 例） |
| 记录范围 | 滑坡易发性评价 WebGIS 平台 AI 协同开发过程中 **AI 生成的错误代码**、引发的问题及人工发现与修复过程 |
| 关联文档 | 《AI协作开发日志》、《系统测试报告》、《空间逻辑校验报告》、《常见问题排查手册》 |

---

## 1 概述

### 1.1 记录目的

AI 协同开发中，AI 生成的代码并非天然正确。本案例集如实记录开发周期内 **AI 产出的典型错误代码**（含占位要求点名的 405 错误、投影偏移），以及"人工发现 → 协作定位 → 修复验证"的完整过程，达到三个目的：

1. **可核查**：每个案例保留原始错误写法、修复后写法与源码佐证位置，不靠事后美化；
2. **可复盘**：归纳错误类型规律与发现方式，暴露 AI 协同的薄弱环节；
3. **可预防**：错误催生的防御性设计（版本锁、路由注册顺序注释、空间自动校验）沉淀为机制，防止复发。

### 1.2 案例分级

| 级别 | 含义 | 本集数量 |
|---|---|---|
| 严重 | 核心功能不可用（登录不可用、成果位置错误、接口 500 等） | 6 |
| 一般 | 功能可用但存在兼容/数据卫生隐患 | 4 |
| 提示 | 不影响运行，影响一致性/可维护性 | 1 |

### 1.3 记录口径

- **错误代码**：以 AI 当时产出的写法为准（伪代码/节选），修复后写法对照给出；
- **发现方式**：人工实测/联调、代码审阅、依赖安装复现、文档核对、页面级冒烟、逐接口审计、用户反馈、AI 自审等；
- **修复过程**：如实区分"人工定位 + AI 改写"与"AI 自查 + 人工验证"两种协作路径；
- 每个案例末尾给**经验沉淀**与**测试追溯**（对应《测试用例表》编号），形成"错误→用例→防复发"闭环。

---

## 2 案例总览

| 编号 | 案例 | 类型 | 级别 | 发现方式 | 修复路径 | 追溯用例 |
|---|---|---|---|---|---|---|
| EC-01 | DELETE 携带请求体不兼容（405） | 接口设计 | 一般 | 人工实测（Apifox/前端联调） | 人工发现 + AI 改写 | TC-AUX-04 |
| EC-02 | StaticFiles 挂载吞掉认证路由（405/404） | 框架挂载顺序 | **严重** | 人工实测（登录全挂） | 人工发现 + AI 定位修复 | TC-AUTH-01 |
| EC-03 | 渲染 PNG 与底图/矢量套合**投影偏移** | GIS 空间 | **严重** | 人工目视套合抽查 | 人工发现 + AI 重写渲染管线 | TC-GIS-L04 |
| EC-04 | bcrypt 4.1+ 与 passlib 不兼容（登录 500） | 依赖版本 | **严重** | 人工安装复现 | 人工复现 + AI 定位锁版本 | TC-AUTH-02 |
| EC-05 | 调试工具将 JSON 对象包成数组（422） | 客户端兼容 | 提示 | 人工联调 | AI 自查兼容 + 人工验证 | TC-AUX-02 |
| EC-06 | shp 边车残留 / ZIP 多 shp 歧义 | 文件处理 | 一般 | 代码审阅（人工加严） | 人工提出 + AI 补防御 | TC-DATA-13/14 |
| EC-07 | 文档与实现漂移（旧稿"无登录模块"） | 文档一致性 | 一般 | 文档核对（AI 主动发现） | AI 发现 + 人工确认重写 | TC-AUX-06 |
| EC-08 | 超参数传递链断裂（params 被静默丢弃） | 业务链路传参 | **严重** | 人工要求实测（落盘模型回读） | 人工发现 + AI 修复两处断点 | TC-TRAIN-12/13/14 |
| EC-09 | 并发原语误用（信号量重复获取 / 函数内无效锁） | 并发语义 | 一般 | AI 代码自审（实现期内部） | AI 自查发现 + 自行修复 | TC-CONC-01/03/08 |
| EC-10 | 登录态读写位置不一致（用户面板/退出按钮消失） | 前端状态一致性 | **严重** | 用户使用反馈（部署冒烟阶段） | 人工发现 + AI 定位统一存储约定 | TC-USER-12/13 |
| EC-11 | os.makedirs 参数位误用（user.id 传成 mode） | 标准库 API 语义 | **严重** | 人工指令全功能审计（26 项 API 实测） | 人工指令 + AI 定位修复并补用户隔离 | TC-DATA-21 |

---

## 3 案例详情

### EC-01 DELETE 携带请求体不兼容（405）

| 项 | 内容 |
|---|---|
| 级别 | 一般 |
| 阶段 | P3 API 与异步训练 |
| 发现方式 | 人工联调实测（浏览器 fetch / Apifox 发送 DELETE+JSON） |
| 修复路径 | 人工发现 + AI 改写 |

**现象**：前端删除文件/任务时，接口偶发 405 Method Not Allowed 或"请求体为空"类 422 报错；同样的请求在 Postman 可以、在浏览器 fetch 却不行。

**AI 生成的错误代码**：

```python
class DeleteBody(BaseModel):
    target: str          # "task" | "file"
    task_id: Optional[str] = None
    path: Optional[str] = None

@app.delete("/api/delete")
async def delete_resource(body: DeleteBody, user: User = Depends(get_current_user)):
    ...
```

**原因分析**：HTTP 规范（RFC 9110）未禁止 DELETE 带请求体，但**不要求**中间件/客户端转发它。部分浏览器 fetch 实现、反向代理、调试工具会丢弃或拒绝带 body 的 DELETE，落到 FastAPI 时体为空 → Pydantic 422，或被网关判为畸形请求 → 405。AI 生成时按"RESTful 常见写法"套用了 POST 的请求体模式，未考虑 DELETE 的实现差异。

**引发问题**：删除功能在部分客户端下不可用，且报错形态随客户端而异（405/422 混杂），排查成本高。

**人工发现与修复过程**：
1. 人工在前端联调时发现删除按钮报错，但用 Apifox 手动发同样的 DELETE 却成功，判断为请求形态兼容问题而非业务逻辑问题；
2. 人工提出"参数能不能不放 body"，AI 评估后改为**查询参数承载**：

```python
@app.delete("/api/delete")
async def delete_resource(
    target: str = Query(..., pattern="^(task|file)$"),
    task_id: Optional[str] = None,
    path: Optional[str] = None,
    user: User = Depends(get_current_user),
):
    """
    用查询参数承载，规避 DELETE 携带请求体在部分客户端下不兼容的问题
    """
```

3. 修复后人工用浏览器前端 + curl + Apifox 三方复测删除任务/文件，行为一致。

**经验沉淀**：DELETE/GET 不携带请求体，参数一律走查询串或路径参数；该约定已写入《API接口设计文档》通用约定，并在源码保留原因注释防回退。对应测试用例 TC-AUX-04（运行中删除 409 场景）顺带覆盖参数形态。

---

### EC-02 StaticFiles 挂载吞掉认证路由（POST 登录 405 / GET /me 404）

| 项 | 内容 |
|---|---|
| 级别 | **严重**（登录全链路不可用） |
| 阶段 | P5 认证与安全 |
| 发现方式 | 人工实测（登录接口直接打不通） |
| 修复路径 | 人工发现现象 + AI 定位根因并修复 |

**现象**：新增登录功能后，`POST /api/auth/login` 返回 **405 Method Not Allowed**，`GET /api/auth/me` 返回 **404**——而 `/api/auth` 的路由代码看起来完全正确，Swagger 里也看不到这些接口。

**AI 生成的错误代码**：

```python
# 顺序错误：先挂载静态目录，后注册路由
app = FastAPI()

# ... 其他业务路由 ...

FRONTEND_DIST = os.path.join(os.path.dirname(BASE_DIR), "frontend", "dist")
if os.path.isdir(FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")

app.include_router(auth.router)   # ← 太晚了，已被 "/" 挂载点拦截
```

**原因分析**：`app.mount("/", ...)` 是**前缀匹配的挂载点**，一旦注册，所有未被更早注册路由匹配的请求（包括 `/api/auth/*`）都会落到 StaticFiles 处理器：静态目录里没有 `api/auth/login` 文件，POST 对静态资源自然回 405，GET 则 404。AI 在"单服务托管前端"的收尾处追加挂载时，没有意识到它会截断**之后**注册的 APIRouter。

**引发问题**：登录功能 100% 不可用（405/404），且报错极具迷惑性——路由明明写了，报错却像"路径不存在/方法不允许"，容易误判为前端 URL 写错。

**人工发现与修复过程**：
1. 人工启动前后端点登录按钮，前端报错；用 curl 直接打 `/api/auth/login` 同样 405，排除前端问题；
2. 人工把"为什么 login 是 405"丢给 AI 排查；AI 检查路由注册链路，发现 StaticFiles 挂载在 include_router 之前，根因锁定；
3. AI 调整注册顺序（路由先于挂载），并**把教训写成永久注释**：

```python
# 注册认证路由（必须在 StaticFiles 挂载之前，否则 "/" 挂载点会吞掉 /api/auth/*，
# 导致 POST 登录返回 405、GET /me 返回 404）
app.include_router(auth.router)

if os.path.isdir(FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
```

4. 人工复测：登录 → /me → 路由守卫跳转全通。

**经验沉淀**：FastAPI 中 `include_router` 必须在根路径 `mount` 之前；该顺序约束以注释形式固化在 `main.py`，并在《常见问题排查手册》A 类 FAQ 收录"登录 405"排查条目。对应 TC-AUTH-01（登录成功用例）即为回归防线。

---

### EC-03 渲染 PNG 与底图/矢量套合投影偏移（占位点名案例）

| 项 | 内容 |
|---|---|
| 级别 | **严重**（成果图空间位置错误，验收硬伤） |
| 阶段 | P2 成果导出 → P4 前端叠加（P6 测试期确认根因） |
| 发现方式 | 人工目视套合抽查（TC-GIS-10） |
| 修复路径 | 人工发现偏移 + AI 重写渲染管线 + 自动校验固化 |

**现象**：风险渲染 PNG 贴到 Leaflet 底图后，与灾害点图层整体错位：北部偏移小、南部偏移大，呈"扇形张开"状；灾害点密集带与高易发区条带对不上，目视明显可疑。

**AI 生成的错误代码（初版思路）**：

```python
# 初版：直接把投影栅格的 bounds 当经纬度用（或转 Web Mercator PNG 后线性贴图）
rgba = colorize(arr)                              # arr 仍是 EPSG:32647 的米制网格
png = Image.fromarray(rgba)
bounds = [[south, west], [north, east]]           # ← bounds 来自 UTM 米制坐标误当经纬度
# 或：png 转 3857 后，bounds 用 4326 标注 → ImageOverlay 线性拉伸必然错位
L.imageOverlay(pngUrl, bounds).addTo(map)
```

**原因分析**（两层）：
1. **坐标系误用**：EPSG:32647（UTM 47N）是米制投影，其 bounds 数值（如 X≈448861）不是经纬度；即便换算成经纬度 bounds，**UTM 网格与经纬网并不平行**（子午线收敛角），按矩形 bounds 线性贴图必有旋转性错位；
2. **墨卡托非线性**：若转 Web Mercator（EPSG:3857）出 PNG，再按 4326 bounds 交给 ImageOverlay 线性拉伸，纬度方向存在非线性拉伸误差，南北边缘偏移放大——正是"南大北小"扇形偏移的特征。

**引发问题**：成果图空间位置错误属于 GIS 项目的**验收一票否决项**（空间逻辑不正确）；且错误在低纬度小范围不明显、在图幅边缘放大，容易漏检。

**人工发现与修复过程**：
1. 人工按 TC-GIS-10 做目视套合抽查（灾害点叠加风险图），发现扇形偏移，判定为投影管线问题而非样式问题；
2. 人工反馈"点和图对不上，肯定是投影的事"，AI 排查渲染链路后确认上述两层根因；
3. AI 重写渲染管线（`_reproject_to_wgs84`）——核心约束：**PNG 的行列必须与经纬度严格线性对应**：

```python
def _reproject_to_wgs84(src, src_arr):
    """投影栅格 -> WGS84(EPSG:4326) 等经纬网格。
    输出 PNG 的每行对应等纬度、每列对应等经度，行列号与经纬度严格线性关系，
    Leaflet ImageOverlay 在经纬度 bounds 内线性贴图时与数据同构，
    与同样为 EPSG:4326 的灾害点 GeoJSON 像素级对齐，不存在墨卡托非线性拉伸。
    """
    dst_transform, dst_w, dst_h = calculate_default_transform(
        src.crs, WGS84, src.width, src.height, *src.bounds)
    ...
    reproject(source=src_arr, destination=dst_arr, ..., dst_crs=WGS84,
              resampling=Resampling.nearest, ...)
    # dst 本身就是经纬度网格，边界直接取，不再经过任何二次投影/densify
    west, south, east, north = array_bounds(dst_h, dst_w, dst_transform)
```

4. 配套修复：矢量导出统一 `to_crs(epsg=4326)`；shp 缺 .prj 直接拒绝导出（防"无基准叠加"再次发生）；
5. 人工复测套合无偏移后，AI 把该项目**升级为自动校验**（spatial_check 坐标往返误差 < 0.05 m + PNG/TIF 边界比对），后续每次训练产出自动运行，防止回归。

**经验沉淀**：
- Web 端栅格叠加的唯一正确做法：**重投影到 WGS84 等经纬网格出图**，bounds 与行列线性同构；
- 空间类错误不能靠目视验收收尾，必须量化（往返误差 0.0 m、边界差 0.46 像元——见《空间逻辑校验报告》SL-04）；
- 对应 TC-GIS-L04（成果空间一致）、TC-GIS-10（套合抽查）；《常见问题排查手册》B 类收录"风险图与点位错位"条目。

---

### EC-04 bcrypt 4.1+ 与 passlib 不兼容（登录 500）

| 项 | 内容 |
|---|---|
| 级别 | **严重**（认证模块启动即崩/哈希即崩） |
| 阶段 | P5 认证与安全 |
| 发现方式 | 人工本地 pip install 复现 |
| 修复路径 | 人工复现 + AI 定位并锁版本 |

**现象**：安装依赖后启动，登录接口报 500；日志出现 `AttributeError: module 'bcrypt' has no attribute '__about__'`（或 passlib 初始化告警后哈希行为异常）。

**AI 生成的错误代码**：

```txt
# requirements.txt（初版）
passlib[bcrypt]
```

**原因分析**：passlib 1.7.x 通过读取 `bcrypt.__about__.__version__` 探测版本；bcrypt 4.1.0 起移除了 `__about__` 属性 → passlib 抛 AttributeError，`hash_password/verify_password` 全链路失效。AI 生成依赖时只写了功能包名（"口令哈希用 passlib+bcrypt"），未锁兼容版本——AI 的训练语料中该组合多为旧版本环境，缺省写法在 2024+ 的新环境即踩坑。

**引发问题**：认证模块不可用（创建用户/登录全部 500），且报错栈指向 passlib 内部，不看版本号很难联想到"依赖太新"。

**人工发现与修复过程**：
1. 人工按 requirements 装依赖后启动即报错，把 traceback 交给 AI；
2. AI 对照已知兼容矩阵，定位为 bcrypt 4.1+ 与 passlib 的接口变更问题；
3. AI 在 requirements.txt **锁版本**并在文档标注"刻意约束"：

```txt
passlib[bcrypt]
bcrypt<4.1        # passlib 与 bcrypt 4.1+ 不兼容，勿升级
```

4. 人工重建 venv 验证：注册哈希、登录校验全通；《环境依赖与安装说明》4.1 节保留该约束的醒目提示，防止后人"顺手升级"复发。

**经验沉淀**：AI 生成依赖清单时必须考虑版本兼容窗口而非只写包名；凡涉及"生态里已知有断裂兼容史"的依赖，锁上界并写明原因。对应 TC-AUTH-02（口令哈希存储用例）。

---

### EC-05 调试工具将 JSON 对象包成数组（422）

| 项 | 内容 |
|---|---|
| 级别 | 提示 |
| 阶段 | P3 联调期 |
| 发现方式 | 人工联调（Apifox 发参异常） |
| 修复路径 | AI 自查兼容 + 人工验证 |

**现象**：人工用 Apifox 调 `/api/train/start`，明明填的是 JSON 对象，接口回 422 "Input should be a valid dictionary"；用 curl 发同样的内容却正常。

**AI 生成的错误代码**：

```python
@app.post("/api/train/start")
async def train_start(payload: TrainStartRequest, user: User = Depends(get_current_user)):
    ...
```

**原因分析**：Apifox 等调试工具在某些导入/批量模式下会把 JSON 对象**包成单元素数组**（`[{...}]`）发送；Pydantic 严格按对象校验即 422。这不算纯粹的"AI 写错"——服务端契约是对的——但 AI 初版未给客户端形态差异留兼容余量，导致联调摩擦。

**引发问题**：联调期误判为"接口挂了"，浪费约半小时排查。

**人工发现与修复过程**：人工抓包看到请求体外层多了 `[]`，反馈给 AI；AI 增加并集兼容并取第一条：

```python
@app.post("/api/train/start")
async def train_start(payload: Union[TrainStartRequest, List[TrainStartRequest]], ...):
    # Apifox 可能把 JSON 对象包成单元素数组；统一取第一条
    if isinstance(payload, list):
        if not payload:
            raise HTTPException(status_code=422, detail="请求体不能为空")
        req = payload[0]
    else:
        req = payload
```

人工复测 Apifox/curl/前端三方一致。

**经验沉淀**：对外接口对"等价形态"宽容（对象/单元素数组），对语义严格（字段校验）；该兼容逻辑已写入《API接口设计文档》训练接口说明。对应 TC-AUX-02。

---

### EC-06 shp 边车残留 / ZIP 多 shp 歧义

| 项 | 内容 |
|---|---|
| 级别 | 一般 |
| 阶段 | P2 上传功能 → P5 删除安全加严期 |
| 发现方式 | 人工代码审阅（删除规则评审） |
| 修复路径 | 人工提出场景 + AI 补防御 |

**现象**（两处文件处理疏漏）：
1. 删除上传的 `xxx.shp` 后，同目录残留 `xxx.dbf / xxx.shx / xxx.prj / xxx.cpg` 孤儿文件，uploads 目录越积越乱，且后续上传同名 shp 时新旧边车混杂；
2. ZIP 里打了多个 shp（如同时放灾害点和研究区），初版解压后**默默取第一个**，用户选错主文件时训练用错数据且无提示。

**AI 生成的错误代码**：

```python
# 初版删除：只删主文件
os.remove(real_path)

# 初版 ZIP 解压：静默取第一个 shp
shp_files = [...]
abs_shp = os.path.abspath(shp_files[0])   # 多个 shp 时无任何提示
```

**原因分析**：Shapefile 是"一主多边"的多文件格式，AI 初版按单文件思维处理；ZIP 多 shp 的歧义则属于"静默降级"反模式——程序猜用户意图且不告知。

**引发问题**：边车残留污染存储目录（长期数据卫生问题）；多 shp 场景下训练数据可能张冠李戴且不可察。

**人工发现与修复过程**：人工在评审删除保护规则（EC-01 同期）时提出"shp 是一组文件，删一个留一堆算什么"；AI 补两级防御：

```python
# 1. 删除时级联清理边车
stem = os.path.splitext(real_path)[0]
for ext in _SHP_SIDECARS:            # .dbf/.shx/.prj/.cpg/.sbn/.sbx/.xml...
    side = stem + ext
    if os.path.exists(side):
        os.remove(side)

# 2. ZIP 多 shp 显式报错，不猜
if len(shp_files) > 1:
    raise HTTPException(status_code=400,
        detail=f"ZIP 中有多个 .shp 文件，请只放一个：{shp_files}")
```

人工用"打包两个 shp 的 zip"实测得到 400 明确提示，删除后目录确认无残留。

**经验沉淀**：多文件格式按"文件组"心智处理增删；歧义输入显式报错优于静默猜测。对应 TC-DATA-13（zip 异常）、TC-SEC-07（边车级联）；《常见问题排查手册》C 类收录"ZIP 中有多个 .shp 文件"条目。

---

### EC-07 文档与实现漂移（旧稿"无登录模块"）

| 项 | 内容 |
|---|---|
| 级别 | 一般（文档一致性） |
| 阶段 | P7 文档工程 |
| 发现方式 | 文档核对（AI 主动发现） |
| 修复路径 | AI 发现 + 人工确认后重写 |

**现象**：`附件/` 目录旧版《需求分析书》写明"系统无登录模块"，但代码现状已有完整 JWT 登录（admin/user 角色）。若照旧稿抄写新文档，将出现"文档描述的功能与系统不符"的验收硬伤。

**错误形态**（非代码，属 AI 协作中"照单全收旧材料"的风险）：若 AI 接到"根据需求写文档"指令后直接沿用旧稿结论，会产出与实现矛盾的文档。

**人工发现与修复过程**：
1. 人工给出"根据这个项目实际来写需求分析说明书"的指令（强调以现状为准）；
2. AI 在动笔前交叉核对 readme、旧稿与源码（`security.py`/`routers/auth.py` 实际存在），**主动指出**旧稿"无登录"表述过时，以实现为准重写；
3. 人工确认后，新文档按现状写 AUTH 模块（FR-AUTH-01~05），并删除旧目录下与新体系冲突的旧稿引用。

**经验沉淀**：文档写作的 Prompt 规范中固化"以源码现状为准，旧稿仅作背景参考"；《AI协作开发日志》P7-1 记录该纠偏。对应 TC-AUX-06（Swagger 可用性间接验证接口体系与文档一致）。

---

### EC-08 超参数传递链断裂（params 被静默丢弃，功能级失效）

| 项 | 内容 |
|---|---|
| 级别 | **严重**（功能缺陷：界面设置与训练结果不符） |
| 阶段 | P9 V1.1 功能迭代 |
| 发现方式 | 人工指令"测试这些功能是否有问题"→ AI 用**落盘模型属性回读**实测发现 |
| 修复路径 | 人工确认后 AI 修复两处断点 + 复测 |

**现象**：V1.1 新增超参数面板（负样本比例、决策树数量、LR 的 C、SVM 的 C 与核函数）。前端在 `train/start` 请求体中正确携带 `params: {n_estimators: 5, svm_C: 2.5, ...}`，训练也正常完成——但落盘模型回读发现全部是默认值：请求 5 棵树的 RF 实际 100 棵、请求 C=2.5 的 SVC 实际 C=1.0。**5 个滑杆全部静默无效**，且界面无任何报错。

**错误形态**（AI 生成代码的典型"链路断点"）：每一环单独看都语法正确、局部合理，但数据在环与环之间悄悄丢失：

1. `TrainStartRequest`（pydantic 模型）声明了 `sample_shp`/`factor_files`/`custom_model_path`/`pipeline_config`，**唯独漏了 `params` 字段**——pydantic 默认静默忽略多余字段，前端提交的 params 在 API 边界直接蒸发；
2. `_train_worker` 调用训练函数时写成 `run_model_train(..., **(task.params or {}))`——字典被**解包成关键字参数**（如 `neg_ratio=3.0`）落入 `**kwargs` 兜底桶；而 `run_model_train` 是从**命名参数 `params` 字典**取值（`params.get('neg_ratio', 3.0)`）→ `params` 恒为 None → 永远取默认值。

**为什么测试没第一时间拦住**：训练"成功"、指标正常、进度正常——所有表层断言都过。只有**回读落盘模型的内部属性**（`joblib.load(...).n_estimators == 5`）才能证伪。这推动了 TC-TRAIN-12/13/14 用例的写法设计：**参数类功能必须断言产物属性，不能只看状态码**。

**人工发现与修复过程**：
1. 人工在 V1.1 功能更新后给出指令"测试这些功能是否有问题，有问题就不做下一步（文档更新）"；
2. AI 静态审阅发现 `params` 传递链疑点，设计对照实测：RF 请求 n_estimators=5、SVM 请求 svm_C=2.5，训练完成后 joblib 回读——两组均证实参数未生效；
3. 按约定**阻断文档更新**，先报缺陷；
4. 人工回复"需要（修复）"后，AI 定位并修复两处断点：`TrainStartRequest` 补 `params: Optional[dict]` 字段并显式透传；`_train_worker` 改 `params=task.params` 命名传参（**禁止 `**` 解包**）；
5. 复测：n_estimators=5 → 落盘 5 棵 ✓；svm_C=2.5/kernel=poly → C=2.5/poly ✓；随后才恢复文档同步。

**经验沉淀**：
- **参数透传链要整体测试**：HTTP 请求体 → pydantic 模型 → 任务对象 → 训练函数，任何一环的字段遗漏或 `**` 解包都会让参数"合法地消失"；约定跨函数传可变参数字典时**必须命名传参（params=params）**，禁止 `**dict` 解包进带 `**kwargs` 的函数；
- **pydantic 默认静默丢弃多余字段**是双刃剑：向前兼容好，但拼错/漏声明字段无任何告警——重要请求模型建议逐字段核对；
- **参数类功能的验收断言落在产物属性上**（模型文件回读），不看界面不看日志。对应 TC-TRAIN-12/13/14（落盘模型属性回读断言）；《系统测试报告》DEF-02 完整记录。

### EC-09 并发原语误用（信号量重复获取 / 函数内无效锁）

| 项 | 内容 |
|---|---|
| 级别 | 一般（实现期内部缺陷，提交前自审修复，未外显至用户） |
| 阶段 | P10 V1.2 并发承载 |
| 发现方式 | AI 在写完并发闸门后**代码自审**发现（提交前） |
| 修复路径 | AI 自行重写排队循环 + 锁改模块级，随后 5 并发实测验证 |

**现象**：为限制并发训练数，AI 首版写了"信号量闸门 + 排队提示"逻辑，两处并发原语误用：

1. **信号量重复获取（槽位泄漏风险）**：首版用 `if _train_slots.acquire(blocking=False): 开跑` + `else: 刷新排队提示; _train_slots.acquire(timeout=1.0)`——失败分支的第二次 acquire 一旦与另一线程释放竞争成功，会**再占一个槽位**，而 finally 只 release 一次 → 每泄漏一个槽位就永久少一路并发，极端情况全部训练永远排队。局部看"两次尝试获取"合理，成对审计 acquire/release 次数后暴露；
2. **函数内新建锁（互斥完全无效）**：`joblib.dump` 防覆盖首版把 `lock = threading.Lock()` 写在函数体内——**每次调用都是新锁**，跨线程互斥形同虚设（等于没加锁）。锁必须是共享对象（模块级/类级），局部锁是并发编程的典型"安慰剂"。

**修复**：
1. 排队逻辑重写为**单循环单获取**：`while True: if acquire(timeout=1.0): break; 刷新排队提示`——每轮至多一次 acquire，try/finally 保证恰好一次 release；
2. `joblib.dump` 锁改**模块级 `_dump_lock`**，进程内所有训练线程共享。

**经验沉淀**：
- **并发原语审计按"对象作用域 + 获取/释放配对"两条线走**：锁/信号量必须共享作用域；acquire 与 release 数量必须严格配对（用 try/finally 兜底），任何"两次尝试获取"的写法都要重画成单循环；
- **局部锁 = 无锁**：`threading.Lock()` 建在函数体内每调用新建，互斥语义为零——写锁时先问"几个线程看到的是同一个对象吗"；
- 实现期自查（写完并发代码先推演竞态）能在缺陷外显前拦截；并发类改动仍以**多线程实测**（5 并发限流、槽位计数）收尾验证。对应 TC-CONC-01/03/08；《系统测试报告》10.3 节记录。

---

### EC-10 登录态读写位置不一致（用户管理面板与退出按钮消失）

| 项 | 内容 |
|---|---|
| 级别 | 严重（admin 管理入口与退出入口双双不可见，功能级失效） |
| 阶段 | 11-18 项目更新登录功能时埋入（sessionStorage 混用），Docker 部署冒烟阶段外显 |
| 发现方式 | 用户使用反馈（"用户管理面板和退出功能怎么没了"） |
| 修复路径 | 人工发现 + AI 单轮定位根因并统一存储约定，重建前端镜像复测 |

**现象**：登录成功后页面右上角不渲染"退出登录"按钮，admin 也看不到"用户管理"面板——两个入口的 `v-if` 条件（`userInfo`、`userInfo?.role==='admin'`）恒假，但接口层一切正常。

**错误写法（读写分家）**：

```js
// Login.vue（写侧）：登录后存 sessionStorage
sessionStorage.setItem('landslide_user', JSON.stringify(user))

// Home.vue（读侧，初版）：却去 localStorage 取 → 恒为 null
const userInfo = JSON.parse(localStorage.getItem('landslide_user') || 'null')
```

连带缺陷：logout 清理业务状态时也清错了位置——`landslide_factorFiles`/`landslide_taskId` 等业务状态实际存于 **localStorage**（刷新恢复用），退出时却去清 **sessionStorage**，导致"退出后换账号登录仍看到上一账号的业务状态"隐患。

**修复**（约定先行）：
1. **统一约定**：用户/令牌走 sessionStorage（与 axios 拦截器、401 清理一致）；业务状态（factorFiles/sampleShp/studyArea/taskId）留 localStorage 供刷新恢复；
2. Home.vue 读侧改 `sessionStorage.getItem('landslide_user')`；
3. logout 两处都清：sessionStorage 清 token/user，localStorage 清 4 项业务状态。

**经验沉淀**：
- **同一份状态的读写侧必须落在同一个存储键**，前端 localStorage/sessionStorage 混用是"局部都对、整体失效"的典型——改登录/状态持久化时先画一张"哪个键存哪、谁读谁写"的表再动手；
- 清理逻辑必须与**实际写入位置**逐键核对，不能凭印象清另一个存储；
- 该缺陷在接口测试中不可见（API 全通），只有**页面级人工冒烟**能暴露——印证"接口全通 ≠ 功能在位"。对应 TC-USER-12/13；《系统测试报告》DEF-03。

---

### EC-11 os.makedirs 参数位误用（批量上传 500）

| 项 | 内容 |
|---|---|
| 级别 | 严重（/api/upload/batch 全量 500，批量因子上传不可用） |
| 阶段 | P9 V1.1 数据隔离强化（上传目录按用户隔离改造） |
| 发现方式 | 人工指令全功能审计（26 项 API 逐项实测） |
| 修复路径 | 人工指令"仔仔细细检查一遍"驱动 + AI 定位修复并补用户隔离，回归复测 |

**现象**：`POST /api/upload/batch` 上传文件返回 500 TypeError。

**错误写法（位置参数错位）**：

```python
# 初版：把 user.id 想着"拼进目录名"，却传进了 makedirs 的第二个位置参数
subdir = os.path.join(UPLOAD_DIR, str(uuid.uuid4()))
os.makedirs(subdir, str(user.id), exist_ok=True)   # ← 第二位置参数是 mode（目录权限），不是路径片段！
```

`os.makedirs(name, mode, exist_ok)` 的第二位置参数是**目录权限 mode**，`str(user.id)` 类型不符直接抛 TypeError；且该写法目录名里根本没有 user_id，用户隔离也没实现——一个笔误同时造成"接口挂掉 + 隔离缺失"两个问题。

**修复**：

```python
# 修复后：目录名带用户隔离，makedirs 只传路径
subdir = os.path.join(UPLOAD_DIR, str(user.id), str(uuid.uuid4()))
os.makedirs(subdir, exist_ok=True)
```

与 upload_compat 的落盘约定统一为 `uploads/{user_id}/{uuid}/`，并经越权测试复核（他目录 403）。

**经验沉淀**：
- **标准库位置参数是静默错位的高发区**：调用前对照签名（`makedirs(name, mode=0o777, exist_ok=False)`），路径片段要拼进 `os.path.join`，绝不能"顺手"塞进后续位置参数；
- 多入口（upload / upload_compat / upload_files_batch / shapefile）落盘逻辑应**收敛到同一处写法**，本次即因批量入口未与兼容入口对齐而漏测漏改；
- "功能保留"类审计要**逐接口真实发请求**（本例 API 实测 26 项才发现），只看代码或只跑主链路会漏掉低频入口。对应 TC-DATA-21；《系统测试报告》DEF-04。

---

## 4 统计与规律分析

### 4.1 错误类型分布

| 类型 | 案例 | 数量 | 占比 |
|---|---|---|---|
| 框架/接口形态（HTTP 语义、挂载顺序、客户端兼容） | EC-01、EC-02、EC-05 | 3 | 27.3% |
| 业务链路传参（字段遗漏、解包语义） | EC-08 | 1 | 9.1% |
| 并发语义（原语作用域、获取/释放配对） | EC-09 | 1 | 9.1% |
| 前端状态一致性（存储读写位置） | EC-10 | 1 | 9.1% |
| 标准库 API 语义（位置参数） | EC-11 | 1 | 9.1% |
| GIS 空间逻辑 | EC-03 | 1 | 9.1% |
| 依赖版本生态 | EC-04 | 1 | 9.1% |
| 数据/文件处理边界 | EC-06 | 1 | 9.1% |
| 文档一致性 | EC-07 | 1 | 9.1% |

**规律**：AI 错误集中在**"正确语法 + 错误上下文"**——代码本身合法，但没站到部署环境（挂载顺序）、客户端生态（DELETE body）、依赖生态（bcrypt 断裂）、GIS 特殊性（投影非线性）、**调用链语义**（pydantic 静默丢字段、`**` 解包进 `**kwargs`）、**并发语义**（锁作用域、acquire/release 配对）或**状态/参数语义**（localStorage/sessionStorage 读写分家、makedirs 位置参数错位）里推演。EC-08~EC-11 提醒：链路、并发、状态与 API 签名错误比想象中隐蔽——每环局部正确、全程静默失效，只有产物级断言（EC-08）、并发实测（EC-09）、页面级冒烟（EC-10）与逐接口实测（EC-11）能证伪。

### 4.2 发现方式分布

| 发现方式 | 案例 | 数量 |
|---|---|---|
| 人工实测/联调 | EC-01、EC-02、EC-04、EC-05 | 4 |
| 人工目视/领域判断 | EC-03 | 1 |
| 人工审阅/加严 | EC-06 | 1 |
| AI 主动核对发现 | EC-07 | 1 |
| 人工指令实测（产物回读/全功能审计） | EC-08、EC-11 | 2 |
| AI 实现期自审 | EC-09 | 1 |
| 用户使用反馈 | EC-10 | 1 |

**规律**：**11 个案例中 9 个靠人工把关发现（含用户反馈与人工指令实测）、2 个 AI 自查/自审拦截**，印证《AI协作开发日志》"人工握验收决策权"的分工必要性；AI 的自查优势体现在发现后的定位速度（EC-02/EC-03/EC-10 均在单轮内锁定根因）与修复后的机制固化（自动校验/注释/文档）。

### 4.3 修复效果与防复发

| 案例 | 修复后验证 | 防复发机制 |
|---|---|---|
| EC-01 | 浏览器/curl/Apifox 三方复测一致 | API 文档通用约定 + 源码注释 |
| EC-02 | 登录全链路复测通过 | 源码永久注释 + FAQ 条目 |
| EC-03 | 套合目视 + 往返误差 0.0 m + 边界差 0.46 像元 | spatial_check 自动校验（每次训练运行） |
| EC-04 | 重建 venv 全通 | requirements 版本锁 + 安装说明警示 |
| EC-05 | 三种客户端行为一致 | API 文档记录兼容策略 |
| EC-06 | 400 明确报错 + 目录无残留 | _SHP_SIDECARS 级联 + 显式校验 |
| EC-07 | 新文档与源码逐字段核对 | 文档 Prompt 规范"以源码为准" |
| EC-08 | 落盘模型回读：n_estimators=5→5、C=2.5→2.5 | TC-TRAIN-12/13/14 产物级断言 + "params 必须命名传参"编码约定 |
| EC-09 | 5 并发实测：限流 ≤2、槽位无泄漏、全部完成 | "锁必须模块级共享 + acquire/release 成对（try/finally）"并发编码约定 + TC-CONC-01/03/08 |
| EC-10 | 重建镜像后页面级复测：面板/退出按钮渲染、退出清理完整 | "登录态 sessionStorage / 业务态 localStorage"存储约定 + TC-USER-12/13 |
| EC-11 | 批量上传 200、落盘 uploads/{uid}/{uuid}/、越权 403 | 四入口落盘写法收敛 + "位置参数对照签名"编码约定 + TC-DATA-21 |

全部 11 个案例均已闭环：**0 个遗留未修复**。所有修复均进入《测试用例表》回归范围（TC-AUTH/TRAIN/GIS/DATA/SEC/AUX/USER/CONC 对应用例）。

---

## 5 错误催生的机制清单

这些错误不只是"修好就完了"，它们改变了系统与流程：

| 机制 | 来源案例 | 落点 |
|---|---|---|
| 空间逻辑自动校验（spatial_check 4 项） | EC-03 | result_export.py，每次训练产出自动运行 |
| 路由注册顺序约束 | EC-02 | main.py 注释 + FAQ |
| 依赖版本上界锁定 | EC-04 | requirements.txt + 环境文档 |
| DELETE 参数形态约定 | EC-01 | API 文档通用约定 |
| 多文件格式级联清理 | EC-06 | 删除接口 _SHP_SIDECARS |
| 歧义输入显式报错 | EC-06 | ZIP 多 shp 400 |
| 文档"以源码为准"写作规范 | EC-07 | AI 协作文档 Prompt 规范 |
| 实测+交叉复算的验收流程 | EC-03 | 测试报告/空间逻辑校验报告成文流程 |
| params 命名传参约定（禁止 `**` 解包进 `**kwargs`） | EC-08 | train_task.py 调用约定 + 测试用例产物级断言 |
| 并发编码约定（锁共享作用域 + acquire/release 成对） | EC-09 | train_task.py/model.py 模块级锁 + try/finally |
| 前端状态存储约定（登录态 sessionStorage / 业务态 localStorage，logout 双清） | EC-10 | Home.vue/Login.vue 注释 + TC-USER-12/13 |
| 标准库位置参数对照签名约定 + 上传落盘写法四入口收敛 | EC-11 | main.py 各上传路由统一 `uploads/{uid}/{uuid}` + TC-DATA-21 |

---

## 6 总结

1. **共记录 11 个 AI 生成错误案例**：6 个严重（认证路由被吞、投影偏移、依赖不兼容、超参数链断裂、登录态读写分家、makedirs 参数错位）、4 个一般（DELETE 405、文件边界、文档漂移、并发原语误用）、1 个提示（数组包装 422），覆盖占位要求点名的 **405 错误**（EC-01/EC-02）与**投影偏移**（EC-03）；
2. **错误画像清晰**：AI 的失误集中在环境/生态上下文（HTTP 语义、挂载顺序、依赖版本、投影特性）、调用链语义（EC-08 的字段遗漏 + `**` 解包）、并发语义（EC-09 的锁作用域/获取配对）与状态/API 签名语义（EC-10 的存储读写分家、EC-11 的位置参数错位），而非业务算法本身；这正是人工领域判断不可替代的部分；
3. **协作修复有效**：9/11 由人工把关发现（含用户反馈与人工指令实测）、2 个 AI 实现期自查拦截，AI 负责快速定位与机制化修复；每个案例均完成"修复→验证→固化→回归用例"闭环，0 遗留；
4. **最大教训（EC-03）**：GIS 空间错误最隐蔽、后果最重，必须用量化校验（往返误差/边界比对）替代目视验收——该教训已物化为系统的自动空间校验能力，也是《空间逻辑校验报告》存在的意义；
5. **第二教训（EC-08）**：参数类功能"跑通≠生效"，验收断言必须落在**产物内部属性**上；跨函数传参字典必须命名传参，`**` 解包是静默失效的高发区；
6. **第三教训（EC-09~EC-11）**："语法对≠语义对"是 AI 代码的系统性风险——并发原语作用域、前端状态读写位置、标准库位置参数三类错误都属此类，局部看完全合法；对策是**约定固化**（存储约定/参数签名对照/落盘写法收敛）+ **针对性实测**（并发计数、页面级冒烟、逐接口审计）。

---
