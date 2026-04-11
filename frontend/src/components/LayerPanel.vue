<script setup lang="ts">
import { ref } from 'vue'
import {
  QDrawer,
  QTabs,
  QTab,
  QTabPanels,
  QTabPanel,
  QBtn,
  QIcon,
  QBadge,
} from 'quasar'
import LayersTab from './LayersTab.vue'
import AnnotateTab from './AnnotateTab.vue'

const open = defineModel<boolean>('modelValue', { default: true })
const activeTab = ref('layers')
const annotateTabRef = ref<InstanceType<typeof AnnotateTab> | null>(null)
</script>

<template>
  <QDrawer v-model="open" side="left" :width="320" :breakpoint="0" class="layer-drawer">
    <!-- Header -->
    <div class="drawer-header">
      <div class="header-brand">
        <QIcon name="satellite_alt" size="22px" />
        <span class="header-title">GeoAnnotate</span>
      </div>
      <QBtn
        flat
        dense
        round
        icon="chevron_left"
        size="sm"
        class="header-close"
        @click="open = false"
      />
    </div>

    <!-- Tabs -->
    <QTabs
      v-model="activeTab"
      dense
      active-color="white"
      indicator-color="white"
      align="justify"
      narrow-indicator
      class="panel-tabs"
    >
      <QTab name="layers" icon="layers" label="Layers" no-caps />
      <QTab name="annotate" icon="edit" label="Annotate" no-caps>
        <QBadge
          v-if="annotateTabRef?.annotationCount && annotateTabRef.annotationCount > 0"
          color="cyan"
          floating
        >
          {{ annotateTabRef.annotationCount }}
        </QBadge>
      </QTab>
    </QTabs>

    <QTabPanels v-model="activeTab" animated class="tab-panels">
      <QTabPanel name="layers" class="q-pa-none panel-content">
        <LayersTab />
      </QTabPanel>

      <QTabPanel name="annotate" class="q-pa-none panel-content">
        <AnnotateTab ref="annotateTabRef" />
      </QTabPanel>
    </QTabPanels>
  </QDrawer>
</template>

<style scoped>
/* ── Drawer shell ──────────────────────────────────────────────── */
.layer-drawer {
  background: #0f172a;
  color: #e2e8f0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid rgba(255, 255, 255, 0.06);
}

/* ── Header ────────────────────────────────────────────────────── */
.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  background: #0c1324;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}
.header-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #38bdf8;
}
.header-title {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.3px;
}
.header-close {
  color: #64748b;
}
.header-close:hover {
  color: #e2e8f0;
}

/* ── Tabs ──────────────────────────────────────────────────────── */
.panel-tabs {
  background: #1e293b;
}
.panel-tabs :deep(.q-tab__label) {
  font-size: 12px;
  font-weight: 500;
}
.panel-tabs :deep(.q-tab__icon) {
  font-size: 18px;
}
.panel-tabs :deep(.q-tab) {
  color: #64748b;
}
.panel-tabs :deep(.q-tab--active) {
  color: #e2e8f0;
}

/* ── Tab panels ────────────────────────────────────────────────── */
.tab-panels {
  flex: 1;
  overflow-y: auto;
  background: transparent;
}
.tab-panels :deep(.q-tab-panel) {
  background: transparent;
}
.panel-content {
  padding: 0;
}
</style>
