import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'vue-element-plus-x/es/styles/index.css'
import 'vue-element-plus-x/es/Bubble/index.css'
import 'vue-element-plus-x/es/BubbleList/index.css'
import 'vue-element-plus-x/es/Conversations/index.css'
import 'vue-element-plus-x/es/Prompts/index.css'
import 'vue-element-plus-x/es/Welcome/index.css'
import 'vue-element-plus-x/es/XSender/index.css'

import App from './App.vue'
import router from './router'
import './styles.css'

const app = createApp(App)
app.use(ElementPlus)
app.use(router)
app.mount('#app')
