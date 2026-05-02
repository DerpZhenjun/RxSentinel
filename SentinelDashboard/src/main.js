/**
 * 应用入口：Pinia → DataV → `#app` 挂载。
 * Pinia 须先于 mount 注册，各组件才能读到同一套 `sentinel` store。
 */
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import './assets/global.css'
import DataVVue3 from '@kjgl77/datav-vue3'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(DataVVue3)

app.mount('#app')
