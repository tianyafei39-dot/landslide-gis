<template>
  <div class="login-container">
    <el-card class="login-card">
      <div class="brand-mark">GIS</div>
      <!-- 动态标题 -->
      <h2 class="title">{{ isRegister ? '注册新账号' : '滑坡易发性评价平台' }}</h2>
      
      <el-form :model="form" @submit.prevent="handleSubmit">
        <el-form-item>
          <el-input v-model="form.username" placeholder="请输入用户名" size="large" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="form.password" type="password" placeholder="请输入密码" size="large" show-password @keyup.enter="handleSubmit" />
        </el-form-item>
        <!-- 注册模式下需要确认密码 -->
        <el-form-item v-if="isRegister">
          <el-input v-model="form.confirmPassword" type="password" placeholder="请再次输入密码" size="large" show-password @keyup.enter="handleSubmit" />
        </el-form-item>
        
        <el-button type="primary" size="large" style="width: 100%" :loading="loading" @click="handleSubmit">
          {{ isRegister ? '注 册' : '登 录' }}
        </el-button>
      </el-form>

      <!-- 切换登录/注册 -->
      <div class="switch-mode">
        <el-button link type="primary" @click="toggleMode">
          {{ isRegister ? '已有账号？返回登录' : '没有账号？立即注册' }}
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import axios from 'axios'

const router = useRouter()
const route = useRoute()
const loading = ref(false)
const isRegister = ref(false) // 控制当前是登录还是注册模式

const form = reactive({
  username: '',
  password: '',
  confirmPassword: ''
})

// 切换模式，清空表单
const toggleMode = () => {
  isRegister.value = !isRegister.value
  form.username = ''
  form.password = ''
  form.confirmPassword = ''
}

// 提交表单（登录或注册）
const handleSubmit = async () => {
  if (!form.username || !form.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }

  // 如果是注册模式，需要确认密码一致
  if (isRegister.value && form.password !== form.confirmPassword) {
    ElMessage.warning('两次输入的密码不一致')
    return
  }

  loading.value = true
  try {
    if (isRegister.value) {
      // 执行注册逻辑
      await axios.post('/api/auth/register', {
        username: form.username,
        password: form.password
      })
      ElMessage.success('注册成功，请使用新账号登录')
      // 注册成功后自动切回登录模式，并保留刚才注册的用户名
      const savedUser = form.username
      toggleMode()
      form.username = savedUser
    } else {
      // 执行登录逻辑
      const { data } = await axios.post('/api/auth/login', {
        username: form.username,
        password: form.password
      })
      sessionStorage.setItem('landslide_token', data.access_token)
      sessionStorage.setItem('landslide_user', JSON.stringify(data.user))
      ElMessage.success('登录成功')
      const redirect = route.query.redirect || '/home' // 👈 默认跳转到 /home
      router.replace(redirect)
    }
  } catch (error) {
    // 捕获后端返回的错误信息（如“用户名已存在”、“密码错误”）
    ElMessage.error(error.response?.data?.detail || '操作失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  display: flex; justify-content: center; align-items: center; height: 100vh;
  background: linear-gradient(135deg, #0f172a, #1e3a8a);
}
.login-card {
  width: 380px; padding: 20px; border-radius: 12px; text-align: center;
}
.brand-mark {
  width: 48px; height: 48px; background: #2563eb; color: white; font-weight: bold;
  font-size: 18px; border-radius: 12px; display: flex; align-items: center; justify-content: center;
  margin: 0 auto 12px;
}
.title { margin-bottom: 24px; color: #0f172a; }
.switch-mode {
  margin-top: 15px;
  text-align: right;
}
</style>