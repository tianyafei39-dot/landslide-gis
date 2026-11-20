import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'leaflet/dist/leaflet.css'
import './style.css'
import axios from 'axios'

// 同源相对路径：dev 走 Vite 代理（/api、/static → 8000），Docker/单服务模式走 nginx/后端同源反代
axios.defaults.baseURL = ''

// ====== 全局 axios 拦截器 ======
// 每次请求前自动带上 Token
axios.interceptors.request.use(config => {
  const token = sessionStorage.getItem('landslide_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 处理 401 过期
axios.interceptors.response.use(
  response => response,
  error => {
    if (error.response && error.response.status === 401) {
      sessionStorage.removeItem('landslide_token')
      sessionStorage.removeItem('landslide_user')
      if (router.currentRoute.value.path !== '/login') {
        router.replace('/login')
      }
    }
    return Promise.reject(error)
  }
)

const app = createApp(App)
app.use(router)
app.use(ElementPlus)
app.mount('#app')