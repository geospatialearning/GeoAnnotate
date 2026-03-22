import './assets/main.css'
import 'quasar/dist/quasar.css'
import '@quasar/extras/material-icons/material-icons.css'
import 'ol/ol.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { Quasar } from 'quasar'

import App from './App.vue'

createApp(App).use(createPinia()).use(Quasar, { plugins: {} }).mount('#app')
