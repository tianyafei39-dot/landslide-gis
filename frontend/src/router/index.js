import { createRouter, createWebHistory } from 'vue-router'
import { ElMessage } from 'element-plus'

const routes = [
  {
    path: '/',
    redirect: '/login' // 👈 核心：只要访问根路径，直接重定向到登录页
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue')
  },
  {
    path: '/home', // 👈 把主页的路径改成 /home
    name: 'Home',
    component: () => import('../views/Home.vue'),
    meta: { requiresAuth: true } // 需要登录
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, from, next) => {
  const token = sessionStorage.getItem('landslide_token')
  
  // 如果要去的页面需要登录，但没有 token
  if (to.meta.requiresAuth && !token) {
    ElMessage.warning('请先登录')
    next(`/login?redirect=${encodeURIComponent(to.fullPath)}`)
  } 
  // 如果已经有 token，还要去登录页，直接踢回主页
  else if (to.path === '/login' && token) {
    next('/home') // 👈 这里也要改成 /home
  } 
  else {
    next()
  }
})

export default router