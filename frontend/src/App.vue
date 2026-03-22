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
        <QBtn
          class="drawer-toggle"
          flat
          dense
          round
          icon="menu"
          size="md"
          @click="drawerOpen = !drawerOpen"
        />
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
  top: 10px;
  left: 10px;
  z-index: 1000;
  background: rgba(255, 255, 255, 0.95);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.2);
}
</style>
