<script setup lang="ts">
import { ref } from 'vue'
import { QLayout, QBtn, QPage, QPageContainer } from 'quasar'
import MapViewer from './components/MapViewer.vue'
import LayerPanel from './components/LayerPanel.vue'

const drawerOpen = ref(true)
</script>

<template>
  <QLayout view="lHh Lpr lFf" class="app-shell">
    <LayerPanel v-model="drawerOpen" />

    <QPageContainer>
      <QPage class="map-page">
        <MapViewer />
        <transition name="fade-slide">
          <QBtn
            v-show="!drawerOpen"
            class="drawer-toggle"
            flat
            dense
            round
            icon="chevron_right"
            size="md"
            @click="drawerOpen = true"
          />
        </transition>
      </QPage>
    </QPageContainer>
  </QLayout>
</template>

<style scoped>
.app-shell {
  height: 100%;
}

.map-page {
  height: 100dvh;
}

.drawer-toggle {
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 1000;
  background: #1e293b;
  color: #e2e8f0;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(255, 255, 255, 0.08);
  width: 36px;
  height: 36px;
}
.drawer-toggle:hover {
  background: #334155;
}

.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.fade-slide-enter-from,
.fade-slide-leave-to {
  opacity: 0;
  transform: translateX(-8px);
}
</style>
