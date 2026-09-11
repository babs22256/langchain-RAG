import { defineStore } from 'pinia'
import { login as loginApi, register as registerApi, getMe, changePassword } from '../api/auth'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('token') || '',
    user: JSON.parse(localStorage.getItem('user') || 'null')
  }),
  getters: {
    isLoggedIn: (state) => !!state.token,
    isAdmin: (state) => state.user?.role === 'admin'
  },
  actions: {
    async login(username, password) {
      const data = await loginApi({ username, password })
      this.token = data.access_token
      this.user = data.user
      localStorage.setItem('token', data.access_token)
      localStorage.setItem('user', JSON.stringify(data.user))
      return data
    },
    async register(username, password) {
      return await registerApi({ username, password })
    },
    logout() {
      this.token = ''
      this.user = null
      localStorage.removeItem('token')
      localStorage.removeItem('user')
    },
    async fetchMe() {
      const user = await getMe()
      this.user = user
      localStorage.setItem('user', JSON.stringify(user))
      return user
    },
    async changePassword(old_password, new_password) {
      return await changePassword({ old_password, new_password })
    }
  }
})
