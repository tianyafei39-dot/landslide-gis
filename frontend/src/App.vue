<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">GIS</div>
        <div>
          <div class="brand-title">滑坡易发性评价平台</div>
          <div class="brand-sub">Machine Learning · WebGIS</div>
        </div>
      </div>

      <div class="panel-body">
        <section class="card">
          <div class="card-head">
            <span class="step">01</span>
            <div>
              <h3>数据接入</h3>
              <p class="card-desc">因子栅格与滑坡样本统一投影后参与建模</p>
            </div>
          </div>

          <div class="row">
            <el-button size="small" type="primary" plain :loading="demoLoading" @click="loadDemo">
              载入示例数据
            </el-button>
            <el-upload
              :http-request="uploadFactor"
              :show-file-list="false"
              multiple
              accept=".tif,.tiff"
            >
              <el-button size="small">上传因子 .tif</el-button>
            </el-upload>
          </div>

          <div v-if="factorFiles.length" class="chip-list">
            <el-tag
              v-for="(f, i) in factorFiles"
              :key="f.path"
              size="small"
              closable
              @close="removeFactor(i)"
            >
              {{ f.name }}
            </el-tag>
          </div>
          <p v-else class="empty-text">尚未选择因子栅格</p>

          <div class="upload-grid">
            <div class="upload-box">
              <span class="upload-label">灾害点样本</span>
              <el-upload :http-request="(o) => uploadZip(o, 'sample')" :show-file-list="false" accept=".zip">
                <el-button size="small" text>选择 shp.zip</el-button>
              </el-upload>
              <span class="file-state" :class="{ on: sampleShp }">{{ sampleShp ? sampleShp.name : '未上传' }}</span>
              <i v-if="sampleShp" class="clear-x" title="移除并删除服务端文件" @click="clearShp('sample')">×</i>
            </div>
            <div class="upload-box">
              <span class="upload-label">研究区范围</span>
              <el-upload :http-request="(o) => uploadZip(o, 'study')" :show-file-list="false" accept=".zip">
                <el-button size="small" text>选择 shp.zip</el-button>
              </el-upload>
              <span class="file-state" :class="{ on: studyArea }">{{ studyArea ? studyArea.name : '未上传' }}</span>
              <i v-if="studyArea" class="clear-x" title="移除并删除服务端文件" @click="clearShp('study')">×</i>
            </div>
          </div>

          <div v-if="inspect" class="meta-box">
            <div class="meta-line">
              <span class="dot" :class="inspect.aligned ? 'ok' : 'bad'"></span>
              投影 {{ inspect.crs }} · {{ inspect.shape?.[0] }}×{{ inspect.shape?.[1] }} · {{ inspect.factor_count }} 个因子
            </div>
            <div v-if="!inspect.aligned" class="meta-warn">因子网格 / 投影不一致，训练将被阻断</div>
          </div>
        </section>

        <section class="card">
          <div class="card-head">
            <span class="step">02</span>
            <div>
              <h3>异步训练</h3>
              <p class="card-desc">后台线程训练，实时轮询进度</p>
            </div>
          </div>

          <div class="train-row">
            <el-select v-model="modelType" size="small" style="width: 148px">
              <el-option label="随机森林" value="randomforest" />
              <el-option label="逻辑回归" value="logistic" />
            </el-select>
            <el-button
              type="danger"
              size="small"
              :loading="training"
              :disabled="!canTrain"
              @click="startTrain"
            >
              启动训练
            </el-button>
          </div>

          <el-progress
            :percentage="displayProgress"
            :status="progressStatus"
            :stroke-width="9"
            :show-text="true"
          />
          <div class="progress-meta">
            <span>{{ msg || '等待开始' }}</span>
            <span v-if="training" class="mono">{{ elapsed }}s</span>
          </div>

          <div v-if="metrics" class="metrics">
            <div v-for="m in metricItems" :key="m.label" class="metric">
              <span class="metric-value">{{ m.value }}</span>
              <span class="metric-label">{{ m.label }}</span>
            </div>
          </div>
        </section>

        <section class="card">
          <div class="card-head">
            <span class="step">03</span>
            <div>
              <h3>图层渲染</h3>
              <p class="card-desc">连续渐变分级色带 · 图层开关 · 点击查询</p>
            </div>
          </div>

          <div class="switch-row">
            <span>滑坡易发性图层</span>
            <el-switch v-model="layerVisible.result" size="small" :disabled="!hasResult" />
          </div>
          <div class="switch-row">
            <span>滑坡灾害点</span>
            <el-switch v-model="layerVisible.points" size="small" :disabled="!hasResult" />
          </div>
          <div class="switch-row">
            <span>研究区边界</span>
            <el-switch v-model="layerVisible.study" size="small" :disabled="!hasResult" />
          </div>
          <div class="slider-row">
            <span>图层透明度</span>
            <el-slider v-model="opacity" :min="0.2" :max="1" :step="0.05" size="small" :disabled="!hasResult" />
          </div>

          <div v-if="factorOverlays.length" class="factor-layers">
            <div class="factor-title">因子栅格图层（{{ factorOverlays.length }}）</div>
            <div v-for="f in factorOverlays" :key="f.name" class="switch-row">
              <span class="factor-name">
                {{ f.name }}
                <em v-if="f.value_range">{{ f.value_range[0] }} ~ {{ f.value_range[1] }}</em>
              </span>
              <el-switch
                :model-value="!!factorVisible[f.name]"
                size="small"
                @change="(v) => toggleFactor(f, v)"
              />
            </div>
          </div>
          <div v-if="factorsLoading" class="factor-loading"><span class="spinner"></span>正在渲染因子图层…</div>

          <div v-if="legend" class="legend">
            <div class="legend-bar" :style="{ background: legendGradient }"></div>
            <div class="legend-ticks">
              <span>0</span><span>0.2</span><span>0.4</span><span>0.6</span><span>0.8</span><span>1</span>
            </div>
            <div class="legend-classes">
              <span v-for="c in legend.classes" :key="c.key">
                <i :style="{ background: c.color }"></i>{{ c.name }}
              </span>
            </div>
          </div>

          <div v-if="hasResult" class="class-stats">
            <div v-for="c in bundle.overlay.class_stats" :key="c.key" class="stat-row">
              <span class="stat-name">{{ c.name }}</span>
              <div class="stat-bar"><i :style="{ width: c.percent + '%', background: c.color }"></i></div>
              <span class="stat-num">{{ c.percent }}%</span>
            </div>
          </div>

          <div v-if="hasResult" class="result-actions">
            <el-button size="small" text @click="fitResult">定位到结果范围</el-button>
            <el-button size="small" type="primary" text :loading="exporting" @click="exportPng">导出风险图 PNG</el-button>
            <el-button size="small" text @click="downloadTif">下载结果 TIF</el-button>
            <el-button size="small" type="danger" text @click="deleteTaskResult">删除结果</el-button>
          </div>
        </section>

        <section v-if="spatial" class="card">
          <div class="card-head">
            <span class="step">04</span>
            <div>
              <h3>GIS 空间校验</h3>
              <p class="card-desc">投影 · 边界 · 坐标往返 · 风险分布</p>
            </div>
          </div>

          <div class="pass-badge" :class="spatial.passed ? 'ok' : 'bad'">
            {{ spatial.passed ? '空间校验通过' : '存在校验项未通过' }}
          </div>

          <div v-for="c in spatial.checks" :key="c.name" class="check-row">
            <span class="check-icon" :class="c.passed ? 'ok' : 'bad'">{{ c.passed ? '✓' : '!' }}</span>
            <div>
              <div class="check-name">{{ c.name }}</div>
              <div class="check-detail">{{ c.detail }}</div>
            </div>
          </div>

          <div class="space-grid">
            <div><span>灾害点命中率</span><b>{{ (spatial.high_hit_ratio * 100).toFixed(1) }}%</b></div>
            <div><span>灾害点均值</span><b>{{ spatial.mean_points }}</b></div>
            <div><span>研究区背景均值</span><b>{{ spatial.mean_study }}</b></div>
            <div><span>坐标往返误差</span><b>{{ spatial.roundtrip_error_m }} m</b></div>
          </div>
        </section>
      </div>
    </aside>

    <main class="map-area">
      <div ref="mapRef" class="map"></div>

      <div class="map-topbar">
        <button :class="{ active: baseKey === 'imagery' }" @click="setBase('imagery')">遥感影像</button>
        <button :class="{ active: baseKey === 'osm' }" @click="setBase('osm')">OSM 底图</button>
        <button :class="{ active: baseKey === 'blank' }" @click="setBase('blank')">无底图</button>
      </div>

      <div class="map-hint">
        {{ hasResult ? '单击地图查看该位置滑坡易发性等级' : '载入示例数据并启动训练后，可查看滑坡易发性分级图' }}
      </div>

      <div v-if="overlayLoading" class="map-loading">
        <span class="spinner"></span>正在加载风险栅格…
      </div>

      <div v-if="hasResult" class="map-caption">
        <span>源投影 {{ bundle.overlay.crs }} → WGS84</span>
        <span>像元 {{ bundle.overlay.pixel_size?.[0] }} m</span>
        <span>渲染 {{ bundle.overlay.size.width }}×{{ bundle.overlay.size.height }}</span>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import axios from 'axios'
import L from 'leaflet'
import { ElMessage, ElMessageBox } from 'element-plus'

/* ---------------------------- 状态 ---------------------------- */
const mapRef = ref(null)
const factorFiles = ref([])
const sampleShp = ref(null)
const studyArea = ref(null)
const inspect = ref(null)
const inspectLoading = ref(false)
const demoLoading = ref(false)

const modelType = ref('randomforest')
const training = ref(false)
const trainFailed = ref(false)
const progress = ref(0)
const msg = ref('')
const elapsed = ref(0)
const metrics = ref(null)
const taskId = ref('')
const bundle = ref(null)

const layerVisible = reactive({ result: true, points: true, study: true })
const opacity = ref(0.82)
const overlayLoading = ref(false)
const baseKey = ref('imagery')
const factorOverlays = ref([])
const factorVisible = reactive({})
const factorsLoading = ref(false)
const exporting = ref(false)

let map = null
let overlay = null
let pointsLayer = null
let studyLayer = null
const factorLayers = {}
let pollTimer = null
let elapsedTimer = null
let tileWarned = false
const baseLayers = {}

/* ---------------------------- 计算属性 ---------------------------- */
const hasResult = computed(() => !!bundle.value?.overlay)
const spatial = computed(() => bundle.value?.spatial_check || null)
const legend = computed(() => bundle.value?.overlay?.legend || null)
const canTrain = computed(() =>
  factorFiles.value.length > 0 && !!sampleShp.value && (!inspect.value || inspect.value.aligned)
)
const displayProgress = computed(() => Math.min(100, Math.round(progress.value)))
const progressStatus = computed(() => {
  if (trainFailed.value) return 'exception'
  if (!training.value && metrics.value) return 'success'
  return undefined
})
const metricItems = computed(() => {
  if (!metrics.value) return []
  const m = metrics.value
  return [
    { label: 'AUC', value: Number(m.AUC).toFixed(3) },
    { label: '准确率', value: Number(m.Accuracy).toFixed(3) },
    { label: '精确率', value: Number(m.Precision).toFixed(3) },
    { label: '召回率', value: Number(m.Recall).toFixed(3) },
    { label: 'F1', value: Number(m.F1).toFixed(3) },
  ]
})
const legendGradient = computed(() => {
  const g = legend.value?.gradient
  if (!g) return ''
  return `linear-gradient(90deg, ${g.colors
    .map((c, i) => `${c} ${(g.stops[i] * 100).toFixed(0)}%`)
    .join(', ')})`
})

/* ---------------------------- 地图 ---------------------------- */
function initMap() {
  map = L.map(mapRef.value, { zoomControl: false, minZoom: 3 }).setView([31.2, 98.7], 9)
  // 容器高度在挂载瞬间可能尚未完成布局，延迟校准一次尺寸，防止地图空白
  requestAnimationFrame(() => map?.invalidateSize())
  setTimeout(() => map?.invalidateSize(), 300)
  L.control.zoom({ position: 'bottomright' }).addTo(map)
  L.control.scale({ position: 'bottomright', imperial: false }).addTo(map)

  function onTileError() {
    if (tileWarned) return
    tileWarned = true
    ElMessage.warning('底图瓦片加载失败（网络受限）。风险图层不受影响，可切换底图或使用无底图模式')
  }

  baseLayers.imagery = L.tileLayer(
    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    { maxZoom: 18, attribution: 'Tiles &copy; Esri' }
  )
  baseLayers.imagery.on('tileerror', onTileError)
  baseLayers.osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap contributors',
  })
  baseLayers.osm.on('tileerror', onTileError)
  baseLayers.blank = L.layerGroup()
  baseLayers.imagery.addTo(map)

  // 结果栅格放在低于矢量图层的独立 pane，保证灾害点与边界始终可见
  const resultPane = map.createPane('resultPane')
  resultPane.style.zIndex = 350
  // 因子图层在结果图层之下、底图之上
  const factorPane = map.createPane('factorPane')
  factorPane.style.zIndex = 340

  map.on('click', onMapClick)
  window.addEventListener('resize', onResize)
}

function onResize() {
  map?.invalidateSize()
}

function setBase(key) {
  if (!map || baseKey.value === key) return
  if (map.hasLayer(baseLayers[baseKey.value])) map.removeLayer(baseLayers[baseKey.value])
  baseLayers[key].addTo(map)
  baseKey.value = key
}

/* ---------------------------- 数据上传 ---------------------------- */
function fileName(path) {
  return (path || '').split(/[\\/]/).pop()
}

function errMsg(e) {
  const detail = e?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail) return JSON.stringify(detail)
  return e?.message || '请求失败'
}

async function runInspect() {
  if (!factorFiles.value.length) {
    inspect.value = null
    return
  }
  inspectLoading.value = true
  try {
    const { data } = await axios.post('/api/factors/inspect', {
      factor_files: factorFiles.value.map((f) => f.path),
    })
    inspect.value = data
    if (!data.aligned) ElMessage.warning('因子栅格网格或投影不一致，请检查数据')
    await loadFactorOverlays()
  } catch (e) {
    inspect.value = null
    clearFactorLayers()
    ElMessage.error('栅格校验失败：' + errMsg(e))
  } finally {
    inspectLoading.value = false
  }
}

function uploadFactor(option) {
  const file = option.file
  if (!/\.(tif|tiff)$/i.test(file.name)) {
    ElMessage.error('仅支持 .tif / .tiff 栅格文件')
    return Promise.reject(new Error('invalid file'))
  }
  const form = new FormData()
  form.append('file', file)
  return axios
    .post('/api/upload', form, { onUploadProgress: (e) => option.onProgress?.({ percent: Math.round((e.loaded / e.total) * 100) }) })
    .then(async ({ data }) => {
      const saved = (data.files || []).find((f) => /\.(tif|tiff)$/i.test(f.filename))
      if (!saved) throw new Error('服务端未返回栅格路径')
      if (!factorFiles.value.some((f) => f.path === saved.path)) {
        factorFiles.value.push({ name: saved.filename, path: saved.path })
      }
      await runInspect()
      ElMessage.success(`已上传 ${saved.filename}`)
      option.onSuccess?.(data)
    })
    .catch((e) => {
      ElMessage.error('因子上传失败：' + errMsg(e))
      option.onError?.(e)
    })
}

function uploadZip(option, kind) {
  const file = option.file
  if (!/\.zip$/i.test(file.name)) {
    ElMessage.error('Shapefile 请打包为 .zip 后上传')
    return Promise.reject(new Error('invalid file'))
  }
  const form = new FormData()
  form.append('file', file)
  return axios
    .post('/api/upload/shapefile', form)
    .then(({ data }) => {
      const item = { name: fileName(data.shp_path), path: data.shp_path }
      if (kind === 'sample') sampleShp.value = item
      else studyArea.value = item
      ElMessage.success(`${kind === 'sample' ? '灾害点样本' : '研究区'}已上传：${item.name}`)
      option.onSuccess?.(data)
    })
    .catch((e) => {
      ElMessage.error('Shapefile 上传失败：' + errMsg(e))
      option.onError?.(e)
    })
}

/* 判断是否为用户上传文件（示例数据在 data/raw 下，不允许通过接口删除） */
function isUploaded(p) {
  return /[\\/]uploads[\\/]/i.test(p || '')
}

/* 调用后端删除接口；示例数据仅在前端移除，不发请求 */
async function deleteServerFile(p) {
  if (!isUploaded(p)) return
  await axios.delete('/api/delete', { params: { target: 'file', path: p } })
}

async function removeFactor(i) {
  const f = factorFiles.value[i]
  factorFiles.value.splice(i, 1)
  try {
    await deleteServerFile(f.path)
  } catch (e) {
    ElMessage.warning('服务端文件删除失败：' + errMsg(e))
  }
  runInspect()
}

async function clearShp(kind) {
  const item = kind === 'sample' ? sampleShp.value : studyArea.value
  if (!item) return
  try {
    await ElMessageBox.confirm(`确定移除并删除「${item.name}」及其服务端文件吗？`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  if (kind === 'sample') sampleShp.value = null
  else studyArea.value = null
  try {
    await deleteServerFile(item.path)
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.warning('服务端文件删除失败：' + errMsg(e))
  }
}

async function deleteTaskResult() {
  if (!taskId.value) return
  try {
    await ElMessageBox.confirm('确定删除当前训练任务及其全部结果产物（栅格 TIF、渲染图层）吗？', '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await axios.delete('/api/delete', { params: { target: 'task', task_id: taskId.value } })
    resetResult()
    taskId.value = ''
    metrics.value = null
    progress.value = 0
    msg.value = ''
    trainFailed.value = false
    ElMessage.success('训练任务及结果已删除')
  } catch (e) {
    ElMessage.error('删除失败：' + errMsg(e))
  }
}

/* ---------------------------- 因子图层 ---------------------------- */
function clearFactorLayers() {
  for (const name of Object.keys(factorLayers)) {
    if (map?.hasLayer(factorLayers[name])) map.removeLayer(factorLayers[name])
    delete factorLayers[name]
  }
  factorOverlays.value = []
  Object.keys(factorVisible).forEach((k) => delete factorVisible[k])
}

async function loadFactorOverlays() {
  if (!factorFiles.value.length || !inspect.value?.aligned) {
    clearFactorLayers()
    return
  }
  factorsLoading.value = true
  clearFactorLayers()
  try {
    const { data } = await axios.post('/api/factors/overlays', {
      factor_files: factorFiles.value.map((f) => f.path),
    })
    factorOverlays.value = data.overlays || []
    // 默认显示第一个因子，让用户立刻看到栅格
    if (factorOverlays.value.length) toggleFactor(factorOverlays.value[0], true)
  } catch (e) {
    ElMessage.error('因子图层渲染失败：' + errMsg(e))
  } finally {
    factorsLoading.value = false
  }
}

function toggleFactor(meta, visible) {
  factorVisible[meta.name] = visible
  let layer = factorLayers[meta.name]
  if (!layer) {
    const b = meta.bounds
    layer = L.imageOverlay(meta.png_url, [[b.south, b.west], [b.north, b.east]], {
      opacity: 0.75,
      pane: 'factorPane',
      interactive: false,
    })
    layer.on('error', () => ElMessage.error(`因子图层 ${meta.name} 加载失败`))
    factorLayers[meta.name] = layer
  }
  if (visible && !map.hasLayer(layer)) layer.addTo(map)
  if (!visible && map.hasLayer(layer)) map.removeLayer(layer)
}

async function loadDemo() {
  demoLoading.value = true
  try {
    const { data } = await axios.get('/api/demo/dataset')
    factorFiles.value = data.factor_files.map((p) => ({ name: fileName(p), path: p }))
    sampleShp.value = { name: fileName(data.sample_shp), path: data.sample_shp }
    studyArea.value = data.study_area_shp
      ? { name: fileName(data.study_area_shp), path: data.study_area_shp }
      : null
    await runInspect()
    fitToBounds(inspect.value?.bounds_wgs84)
    ElMessage.success(data.msg || '示例数据已载入')
  } catch (e) {
    ElMessage.error('示例数据载入失败：' + errMsg(e))
  } finally {
    demoLoading.value = false
  }
}

/* ---------------------------- 训练 ---------------------------- */
function startElapsed() {
  elapsed.value = 0
  clearInterval(elapsedTimer)
  elapsedTimer = setInterval(() => { elapsed.value += 1 }, 1000)
}

function stopTimers() {
  clearTimeout(pollTimer)
  clearInterval(elapsedTimer)
  pollTimer = null
  elapsedTimer = null
}

function resetResult() {
  if (overlay && map?.hasLayer(overlay)) map.removeLayer(overlay)
  overlay = null
  if (pointsLayer && map?.hasLayer(pointsLayer)) map.removeLayer(pointsLayer)
  if (studyLayer && map?.hasLayer(studyLayer)) map.removeLayer(studyLayer)
  pointsLayer = null
  studyLayer = null
  bundle.value = null
  overlayLoading.value = false
}

async function startTrain() {
  if (!canTrain.value) {
    ElMessage.warning('请先上传因子栅格与灾害点样本，并确保因子网格对齐')
    return
  }
  training.value = true
  trainFailed.value = false
  progress.value = 0
  metrics.value = null
  msg.value = '正在提交训练任务…'
  taskId.value = ''
  resetResult()
  startElapsed()

  try {
    const { data } = await axios.post('/api/train/start', {
      sample_shp: sampleShp.value.path,
      model_type: modelType.value,
      factor_files: factorFiles.value.map((f) => f.path),
      study_area_shp: studyArea.value?.path || null,
    })
    taskId.value = data.task_id
    pollStatus()
  } catch (e) {
    training.value = false
    stopTimers()
    ElMessage.error('训练任务提交失败：' + errMsg(e))
  }
}

async function pollStatus() {
  if (!taskId.value) return
  try {
    const { data } = await axios.get(`/api/train/status/${taskId.value}`)
    progress.value = Number(data.progress ?? 0)
    msg.value = data.msg || ''

    if (data.status === 'running' || data.status === 'waiting') {
      pollTimer = setTimeout(pollStatus, 900)
      return
    }

    stopTimers()
    training.value = false

    if (data.status === 'finished') {
      metrics.value = data.metrics
      if (data.result) {
        applyResult(data.result)
        ElMessage.success('训练完成，滑坡易发性分级图已生成')
      } else {
        ElMessage.warning('训练完成，但结果图层生成失败，请查看后端日志')
      }
    } else if (data.status === 'failed') {
      trainFailed.value = true
      ElMessage.error(data.msg || '训练失败')
    } else {
      trainFailed.value = true
      ElMessage.error('任务状态异常：' + (data.msg || data.status))
    }
  } catch (e) {
    stopTimers()
    training.value = false
    trainFailed.value = true
    ElMessage.error('查询训练状态失败：' + errMsg(e))
  }
}

/* ---------------------------- 结果渲染 ---------------------------- */
function applyResult(result) {
  resetResult()
  bundle.value = result
  layerVisible.result = true
  layerVisible.points = true
  layerVisible.study = true

  const o = result.overlay
  const bounds = [
    [o.bounds.south, o.bounds.west],
    [o.bounds.north, o.bounds.east],
  ]

  overlayLoading.value = true
  overlay = L.imageOverlay(o.png_url, bounds, {
    opacity: opacity.value,
    pane: 'resultPane',
    interactive: false,
  })
  overlay.on('load', () => {
    overlayLoading.value = false
  })
  overlay.on('error', () => {
    overlayLoading.value = false
    ElMessage.error('风险栅格图像加载失败')
  })
  if (layerVisible.result) overlay.addTo(map)
  map.fitBounds(bounds, { padding: [26, 26] })

  loadVectors(result.vectors)
}

function loadVectors(vectors) {
  if (vectors?.study_area?.url) {
    axios.get(vectors.study_area.url).then(({ data }) => {
      studyLayer = L.geoJSON(data, {
        style: { color: '#1d4ed8', weight: 2, fillColor: '#3b82f6', fillOpacity: 0.04, dashArray: '5 4' },
      })
      if (layerVisible.study) studyLayer.addTo(map)
    }).catch(() => {})
  }

  if (vectors?.points?.url) {
    axios.get(vectors.points.url).then(({ data }) => {
      pointsLayer = L.geoJSON(data, {
        pointToLayer: (feature, latlng) =>
          L.circleMarker(latlng, {
            radius: 4,
            color: '#111827',
            weight: 1,
            fillColor: '#fbbf24',
            fillOpacity: 0.95,
          }),
        onEachFeature: (feature, layer) => {
          const props = feature.properties || {}
          const rows = Object.entries(props)
            .filter(([k]) => !/^(geometry|bbox)/i.test(k))
            .slice(0, 8)
            .map(([k, v]) => `<div class="pop-row"><span>${escapeHtml(k)}</span><b>${escapeHtml(String(v))}</b></div>`)
            .join('')
          layer.bindPopup(
            `<div class="pop-title">滑坡灾害点</div>${rows || '<div class="pop-muted">无属性信息</div>'}`
          )
        },
      })
      if (layerVisible.points) pointsLayer.addTo(map)
    }).catch(() => {})
  }
}

function fitResult() {
  if (!hasResult.value) return
  const b = bundle.value.overlay.bounds
  map.fitBounds([[b.south, b.west], [b.north, b.east]], { padding: [26, 26] })
}

/* ---------------------------- 成果导出 ---------------------------- */
function loadImage(url) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = reject
    img.src = url
  })
}

async function exportPng() {
  if (!hasResult.value) return
  exporting.value = true
  try {
    const o = bundle.value.overlay
    // 经 Vite 代理/同源加载，画布不会被污染，可正常 toDataURL
    const img = await loadImage(o.png_url)

    const pad = 28
    const headerH = 72
    const panelW = 300
    const W = pad + img.width + pad + panelW + pad
    const H = headerH + pad + Math.max(img.height, 600) + pad
    const canvas = document.createElement('canvas')
    canvas.width = W
    canvas.height = H
    const ctx = canvas.getContext('2d')
    const FONT = '"Microsoft YaHei","PingFang SC",sans-serif'

    // 白底
    ctx.fillStyle = '#ffffff'
    ctx.fillRect(0, 0, W, H)

    // 标题区
    ctx.fillStyle = '#0f172a'
    ctx.font = `bold 26px ${FONT}`
    ctx.fillText('滑坡易发性评价图', pad, 40)
    ctx.fillStyle = '#64748b'
    ctx.font = `13px ${FONT}`
    const now = new Date()
    const stamp = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
    ctx.fillText(`生成时间 ${stamp} · 源投影 ${o.crs} · 网格 ${o.size.width}×${o.size.height}`, pad, 62)

    // 风险图
    const imgX = pad
    const imgY = headerH + pad
    ctx.drawImage(img, imgX, imgY)
    ctx.strokeStyle = '#cbd5e1'
    ctx.strokeRect(imgX + 0.5, imgY + 0.5, img.width, img.height)

    // 右侧信息面板
    const px = imgX + img.width + pad
    let py = imgY
    ctx.fillStyle = '#0f172a'
    ctx.font = `bold 17px ${FONT}`
    ctx.fillText('图例与分级统计', px, py)
    py += 18

    // 渐变色带
    const g = o.legend.gradient
    const grad = ctx.createLinearGradient(px, 0, px + panelW, 0)
    g.colors.forEach((c, i) => grad.addColorStop(g.stops[i], c))
    ctx.fillStyle = grad
    ctx.fillRect(px, py + 8, panelW, 18)
    ctx.strokeStyle = '#94a3b8'
    ctx.strokeRect(px + 0.5, py + 8.5, panelW, 18)
    ctx.fillStyle = '#64748b'
    ctx.font = `12px ${FONT}`
    ;[0, 0.2, 0.4, 0.6, 0.8, 1].forEach((v, i) => {
      const x = px + (panelW * i) / 5
      ctx.fillText(String(v), x, py + 42)
    })
    py += 56

    // 分级行
    ctx.font = `13px ${FONT}`
    for (const c of o.class_stats) {
      ctx.fillStyle = c.color
      ctx.fillRect(px, py - 11, 16, 16)
      ctx.strokeStyle = '#94a3b8'
      ctx.strokeRect(px + 0.5, py - 10.5, 16, 16)
      ctx.fillStyle = '#1f2937'
      ctx.fillText(c.name, px + 24, py + 2)
      ctx.fillStyle = '#475569'
      ctx.textAlign = 'right'
      ctx.fillText(`${c.percent}%`, px + panelW, py + 2)
      ctx.textAlign = 'left'
      py += 28
    }

    // 模型指标
    py += 10
    ctx.fillStyle = '#0f172a'
    ctx.font = `bold 17px ${FONT}`
    ctx.fillText('模型指标', px, py)
    py += 14
    ctx.font = `13px ${FONT}`
    if (metrics.value) {
      for (const m of metricItems.value) {
        ctx.fillStyle = '#475569'
        ctx.fillText(m.label, px, py + 14)
        ctx.fillStyle = '#1d4ed8'
        ctx.textAlign = 'right'
        ctx.fillText(m.value, px + panelW, py + 14)
        ctx.textAlign = 'left'
        py += 26
      }
    }

    // 底部说明
    ctx.fillStyle = '#94a3b8'
    ctx.font = `12px ${FONT}`
    ctx.fillText('值域 [0,1]，按 0.2 间隔分为五级 · 滑坡易发性评价 WebGIS 平台', pad, H - 10)

    const a = document.createElement('a')
    a.href = canvas.toDataURL('image/png')
    a.download = `滑坡易发性评价图_${(taskId.value || 'result').slice(0, 8)}.png`
    document.body.appendChild(a)
    a.click()
    a.remove()
    ElMessage.success('风险图 PNG 已导出')
  } catch (e) {
    ElMessage.error('图片导出失败：' + errMsg(e))
  } finally {
    exporting.value = false
  }
}

function downloadTif() {
  if (!hasResult.value) return
  const a = document.createElement('a')
  a.href = bundle.value.overlay.tif_url
  a.download = `landslide_susceptibility_${(taskId.value || 'result').slice(0, 8)}.tif`
  document.body.appendChild(a)
  a.click()
  a.remove()
}

function fitToBounds(b) {
  if (!b || !map) return
  map.fitBounds([[b.south, b.west], [b.north, b.east]], { padding: [30, 30] })
}

/* ---------------------------- 图层开关 ---------------------------- */
watch(() => layerVisible.result, (v) => {
  if (!overlay || !map) return
  if (v && !map.hasLayer(overlay)) overlay.addTo(map)
  if (!v && map.hasLayer(overlay)) map.removeLayer(overlay)
})

watch(() => layerVisible.points, (v) => {
  if (!pointsLayer || !map) return
  if (v && !map.hasLayer(pointsLayer)) pointsLayer.addTo(map)
  if (!v && map.hasLayer(pointsLayer)) map.removeLayer(pointsLayer)
})

watch(() => layerVisible.study, (v) => {
  if (!studyLayer || !map) return
  if (v && !map.hasLayer(studyLayer)) studyLayer.addTo(map)
  if (!v && map.hasLayer(studyLayer)) map.removeLayer(studyLayer)
})

watch(opacity, (v) => { overlay?.setOpacity(v) })

/* ---------------------------- 点击查询 ---------------------------- */
function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
}

async function onMapClick(e) {
  const { lat, lng } = e.latlng
  const coord = `<span class="pop-muted">经度 ${lng.toFixed(6)} · 纬度 ${lat.toFixed(6)}</span>`

  if (!taskId.value || !hasResult.value) {
    L.popup().setLatLng(e.latlng)
      .setContent(`<div class="pop-title">位置坐标</div>${coord}<div class="pop-muted">训练完成后可查询该点易发性</div>`)
      .openOn(map)
    return
  }

  try {
    const { data } = await axios.get('/api/result/query', {
      params: { task_id: taskId.value, lat, lng },
    })
    if (!data.inside) {
      L.popup().setLatLng(e.latlng).setContent(`<div class="pop-title">超出结果范围</div>${coord}<div class="pop-muted">${escapeHtml(data.msg || '')}</div>`).openOn(map)
      return
    }
    if (!data.valid) {
      L.popup().setLatLng(e.latlng).setContent(`<div class="pop-title">无有效值</div>${coord}<div class="pop-muted">${escapeHtml(data.msg || '')}</div>`).openOn(map)
      return
    }
     // 兼容两种后端返回格式：如果有 data.message 直接用；否则用 value、name、advice 拼一句
    const sentence = data.message 
      ? data.message 
      : `该点风险值为 ${Number(data.value).toFixed(2)}，属于 ${escapeHtml(data.name)}，${escapeHtml(data.advice || '暂无建议')}`
    const html = `
      <div class="pop-title">滑坡易发性</div>
      <div class="pop-value-row">
        <span class="pop-dot" style="background:${data.color}"></span>
        <span class="pop-name">${escapeHtml(data.name)}</span>
        <b class="pop-value" style="color:${data.color}">${Number(data.value).toFixed(3)}</b>
      </div>
      <div class="pop-scale"><i style="width:${Math.round(Number(data.value) * 100)}%;background:${data.color}"></i></div>
      ${coord}
      <div class="pop-muted">像元行列 ${data.pixel?.row}, ${data.pixel?.col} · 概率区间 ${data.min}–${data.max}</div>
      <div style="margin-top: 8px; padding-top: 8px; border-top: 1px dashed #ccc; font-size: 13px; color: #333; line-height: 1.4;">
        <b>💡 建议：</b>${escapeHtml(data.advice || data.message || '暂无建议')}
      </div>
    `
    L.popup().setLatLng(e.latlng).setContent(html).openOn(map)
  } catch (err) {
    L.popup().setLatLng(e.latlng).setContent(`<div class="pop-title">查询失败</div><div class="pop-muted">${escapeHtml(errMsg(err))}</div>`).openOn(map)
  }
}

/* ---------------------------- 生命周期 ---------------------------- */
onMounted(initMap)

onUnmounted(() => {
  stopTimers()
  window.removeEventListener('resize', onResize)
  map?.remove()
  map = null
})
</script>

<style>
:root {
  --el-color-primary: #2563eb;
}

body {
  margin: 0;
  background: #eef1f6;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  color: #1f2937;
}

.leaflet-popup-content {
  margin: 12px 14px;
  font-size: 13px;
  line-height: 1.4;
  min-width: 190px;
}
.pop-title {
  font-weight: 600;
  font-size: 13px;
  color: #111827;
  margin-bottom: 6px;
}
.pop-muted {
  color: #8a94a6;
  font-size: 12px;
  margin-top: 4px;
}
.pop-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px dashed #eef0f4;
  padding: 2px 0;
}
.pop-row span { color: #6b7280; }
.pop-row b { color: #111827; font-weight: 500; }
.pop-value-row { display: flex; align-items: center; gap: 8px; margin: 6px 0 4px; }
.pop-dot { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
.pop-name { font-weight: 600; }
.pop-value { margin-left: auto; font-size: 20px; font-weight: 700; }
.pop-scale { height: 5px; background: #eef0f4; border-radius: 3px; overflow: hidden; margin: 4px 0 2px; }
.pop-scale i { display: block; height: 100%; }
</style>

<style scoped>
.app-shell {
  display: flex;
  height: 100vh;
  min-height: 620px;
}

.sidebar {
  width: 384px;
  flex: 0 0 384px;
  background: #ffffff;
  border-right: 1px solid #e3e8ef;
  display: flex;
  flex-direction: column;
  box-shadow: 2px 0 14px rgba(15, 23, 42, 0.05);
  z-index: 5;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 18px 20px;
  border-bottom: 1px solid #eef1f6;
  background: linear-gradient(135deg, #0f172a, #1e3a8a);
  color: #fff;
}
.brand-mark {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.14);
  display: grid;
  place-items: center;
  font-weight: 700;
  letter-spacing: 1px;
  font-size: 13px;
}
.brand-title { font-size: 15px; font-weight: 600; letter-spacing: 0.3px; }
.brand-sub { font-size: 11px; opacity: 0.7; letter-spacing: 1px; margin-top: 2px; }

.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 14px 14px 28px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.card {
  border: 1px solid #e9edf4;
  border-radius: 10px;
  padding: 14px;
  background: #fff;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
}
.card-head {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  margin-bottom: 10px;
}
.step {
  font-size: 11px;
  font-weight: 700;
  color: #2563eb;
  background: #eaf1ff;
  border-radius: 6px;
  padding: 3px 6px;
  letter-spacing: 0.5px;
  margin-top: 2px;
}
.card h3 { margin: 0; font-size: 14px; font-weight: 600; color: #0f172a; }
.card-desc { margin: 2px 0 0; font-size: 11px; color: #94a3b8; line-height: 1.35; }

.row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-list { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.empty-text { margin: 8px 0 0; font-size: 12px; color: #a1aabb; }

.upload-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 10px; }
.upload-box {
  position: relative;
  border: 1px dashed #d7deea;
  border-radius: 8px;
  padding: 8px 10px;
  background: #fafcff;
}
.upload-label { display: block; font-size: 11px; color: #64748b; margin-bottom: 2px; }
.file-state { display: block; font-size: 11px; color: #a1aabb; margin-top: 2px; word-break: break-all; padding-right: 14px; }
.file-state.on { color: #047857; }
.clear-x {
  position: absolute;
  top: 6px;
  right: 8px;
  width: 16px;
  height: 16px;
  line-height: 14px;
  text-align: center;
  border-radius: 50%;
  background: #e2e8f0;
  color: #475569;
  font-style: normal;
  font-size: 13px;
  cursor: pointer;
}
.clear-x:hover { background: #ef4444; color: #fff; }

.result-actions { display: flex; flex-wrap: wrap; gap: 4px 8px; margin-top: 6px; border-top: 1px dashed #eef1f6; padding-top: 8px; }

.meta-box { margin-top: 10px; background: #f6f9ff; border-radius: 8px; padding: 8px 10px; font-size: 11px; color: #475569; }
.meta-line { display: flex; align-items: center; gap: 6px; line-height: 1.5; }
.meta-warn { color: #b91c1c; margin-top: 4px; }
.dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; flex: 0 0 7px; }
.dot.ok { background: #10b981; }
.dot.bad { background: #ef4444; }

.train-row { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
.progress-meta { display: flex; justify-content: space-between; font-size: 11px; color: #64748b; margin-top: 6px; gap: 8px; }
.mono { font-family: ui-monospace, Consolas, monospace; }

.metrics {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 6px;
  margin-top: 12px;
}
.metric {
  background: #f8fafc;
  border: 1px solid #eef2f7;
  border-radius: 8px;
  padding: 6px 4px;
  text-align: center;
}
.metric-value { display: block; font-size: 14px; font-weight: 700; color: #0f172a; }
.metric-label { display: block; font-size: 10px; color: #94a3b8; margin-top: 2px; }

.switch-row { display: flex; justify-content: space-between; align-items: center; font-size: 12px; color: #334155; padding: 5px 0; }
.factor-layers { margin-top: 8px; border-top: 1px dashed #eef1f6; padding-top: 6px; }
.factor-title { font-size: 11px; color: #94a3b8; margin-bottom: 2px; }
.factor-name { display: flex; flex-direction: column; line-height: 1.3; }
.factor-name em { font-style: normal; font-size: 10px; color: #a1aabb; }
.factor-loading { display: flex; align-items: center; gap: 8px; font-size: 12px; color: #64748b; margin-top: 8px; }
.factor-loading .spinner { width: 14px; height: 14px; border-width: 2px; }
.slider-row { display: flex; align-items: center; gap: 12px; margin-top: 4px; }
.slider-row > span { font-size: 12px; color: #334155; white-space: nowrap; }
.slider-row .el-slider { flex: 1; }

.legend { margin-top: 8px; }
.legend-bar { height: 10px; border-radius: 5px; border: 1px solid #e2e8f0; }
.legend-ticks { display: flex; justify-content: space-between; font-size: 10px; color: #94a3b8; margin-top: 2px; }
.legend-classes { display: flex; flex-wrap: wrap; gap: 6px 10px; margin-top: 6px; font-size: 11px; color: #475569; }
.legend-classes span { display: inline-flex; align-items: center; gap: 4px; }
.legend-classes i { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }

.class-stats { margin-top: 10px; display: flex; flex-direction: column; gap: 4px; }
.stat-row { display: flex; align-items: center; gap: 6px; font-size: 11px; color: #64748b; }
.stat-name { width: 58px; flex: 0 0 58px; white-space: nowrap; }
.stat-bar { flex: 1; height: 6px; background: #f1f5f9; border-radius: 3px; overflow: hidden; }
.stat-bar i { display: block; height: 100%; border-radius: 3px; }
.stat-num { width: 46px; text-align: right; font-family: ui-monospace, Consolas, monospace; }

.pass-badge {
  display: inline-block;
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 999px;
  margin-bottom: 8px;
}
.pass-badge.ok { background: #ecfdf5; color: #047857; }
.pass-badge.bad { background: #fef2f2; color: #b91c1c; }

.check-row { display: flex; gap: 8px; padding: 5px 0; border-top: 1px dashed #eef1f6; }
.check-icon {
  width: 18px; height: 18px; border-radius: 50%;
  display: grid; place-items: center;
  font-size: 11px; font-weight: 700; flex: 0 0 18px; margin-top: 1px;
}
.check-icon.ok { background: #ecfdf5; color: #059669; }
.check-icon.bad { background: #fef2f2; color: #dc2626; }
.check-name { font-size: 12px; color: #0f172a; font-weight: 500; }
.check-detail { font-size: 11px; color: #8a94a6; line-height: 1.4; word-break: break-all; }

.space-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-top: 10px; }
.space-grid > div {
  background: #f8fafc; border: 1px solid #eef2f7; border-radius: 8px; padding: 7px 9px;
  display: flex; flex-direction: column; gap: 2px;
}
.space-grid span { font-size: 10px; color: #94a3b8; }
.space-grid b { font-size: 14px; color: #0f172a; }

.map-area { flex: 1; position: relative; min-width: 0; background: #dbe3ee; }
.map { position: absolute; inset: 0; width: 100%; height: 100%; }

.map-topbar {
  position: absolute; top: 14px; left: 14px; z-index: 999;
  background: rgba(255, 255, 255, 0.94);
  border-radius: 9px; padding: 4px;
  display: flex; gap: 4px;
  box-shadow: 0 2px 10px rgba(15, 23, 42, 0.14);
  backdrop-filter: blur(6px);
}
.map-topbar button {
  border: 0; background: transparent; padding: 5px 11px; border-radius: 6px;
  font-size: 12px; color: #475569; cursor: pointer;
}
.map-topbar button.active { background: #2563eb; color: #fff; }

.map-hint {
  position: absolute; left: 14px; bottom: 20px; z-index: 999;
  max-width: 460px;
  background: rgba(15, 23, 42, 0.82);
  color: #e2e8f0;
  font-size: 12px;
  padding: 7px 12px;
  border-radius: 8px;
  pointer-events: none;
}
.map-caption {
  position: absolute; right: 14px; top: 14px; z-index: 999;
  display: flex; gap: 12px; flex-wrap: wrap;
  background: rgba(255, 255, 255, 0.94);
  border-radius: 9px; padding: 7px 12px;
  font-size: 11px; color: #475569;
  box-shadow: 0 2px 10px rgba(15, 23, 42, 0.12);
}

.map-loading {
  position: absolute; inset: 0; z-index: 1000;
  background: rgba(241, 245, 249, 0.55);
  display: flex; align-items: center; justify-content: center; gap: 10px;
  font-size: 13px; color: #334155;
  backdrop-filter: blur(2px);
}
.spinner {
  width: 18px; height: 18px; border-radius: 50%;
  border: 2px solid #c7d2fe; border-top-color: #2563eb;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

@media (max-width: 1100px) {
  .app-shell { flex-direction: column; height: auto; }
  .sidebar { width: 100%; flex: none; }
  .map-area { height: 70vh; }
}
</style>
