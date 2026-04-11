<script setup lang="ts">
import { ref } from 'vue'
import { storeToRefs } from 'pinia'
import {
  QBtn,
  QIcon,
  QSpinner,
  QBadge,
  QTooltip,
  QLinearProgress,
} from 'quasar'
import { useMapStore } from '@/stores/map'

// ── Types ───────────────────────────────────────────────────────────

interface RasterFile {
  name: string
  filename: string
  path: string
  size_mb: number
}

// ── Constants ───────────────────────────────────────────────────────

const API_BASE = 'http://localhost:8000'

// ── Store ───────────────────────────────────────────────────────────

const mapStore = useMapStore()
const { basemaps, rasterLayers } = storeToRefs(mapStore)

// ── Raster browsing ─────────────────────────────────────────────────

const showBrowser = ref(false)
const files = ref<RasterFile[]>([])
const fetching = ref(false)
const loadingFile = ref<string | null>(null)
const error = ref<string | null>(null)

const toggleBrowser = async () => {
  showBrowser.value = !showBrowser.value
  if (showBrowser.value && files.value.length === 0) {
    await fetchFiles()
  }
}

const fetchFiles = async () => {
  fetching.value = true
  error.value = null

  try {
    const res = await fetch(`${API_BASE}/browse/`)
    if (!res.ok) {
      const body = await res.json()
      throw new Error(body.detail || 'Failed to fetch datasets')
    }
    const data = await res.json()
    files.value = data.files
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Failed to fetch datasets'
  } finally {
    fetching.value = false
  }
}

const loadRaster = async (file: RasterFile) => {
  if (isLoaded(file.name)) return

  loadingFile.value = file.name
  error.value = null

  try {
    const params = new URLSearchParams({ name: file.name, file_path: file.path })
    const res = await fetch(`${API_BASE}/rasters/?${params}`, { method: 'POST' })

    if (!res.ok) {
      const body = await res.json()
      throw new Error(body.detail || 'Failed to load raster')
    }

    const data = await res.json()
    mapStore.addRasterLayer(data.info)
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Failed to load raster'
  } finally {
    loadingFile.value = null
  }
}

const isLoaded = (name: string) =>
  mapStore.rasterLayers.some((l) => l.name === name)

// ── Layer management ────────────────────────────────────────────────

const toggleVisibility = (name: string) => {
  mapStore.toggleRasterLayer(name)
}

const removeLayer = async (name: string) => {
  mapStore.removeRasterLayer(name)

  try {
    await fetch(`${API_BASE}/rasters/${name}`, { method: 'DELETE' })
  } catch {
    // best-effort backend cleanup
  }
}
</script>

<template>
  <!-- Section: Raster Layers -->
  <div class="section-header">
    <QIcon name="map" size="16px" class="section-icon" />
    <span>Raster Layers</span>
    <div class="section-actions">
      <QBtn
        flat
        dense
        round
        :icon="showBrowser ? 'close' : 'add_circle_outline'"
        size="sm"
        class="section-btn"
        @click="toggleBrowser"
      >
        <QTooltip>{{ showBrowser ? 'Close' : 'Add Raster' }}</QTooltip>
      </QBtn>
    </div>
  </div>

  <!-- Raster browser section -->
  <transition name="slide-down">
    <div v-if="showBrowser" class="browser-section">
      <div class="browser-header">
        <span>Available Datasets</span>
        <QBtn flat dense round icon="refresh" size="xs" class="section-btn" @click="fetchFiles">
          <QTooltip>Refresh</QTooltip>
        </QBtn>
      </div>

      <div v-if="fetching" class="browser-loading">
        <QSpinner color="cyan" size="1.8em" :thickness="2" />
        <span>Scanning datasets...</span>
      </div>

      <div v-else-if="error" class="browser-error">
        <QIcon name="error_outline" size="16px" />
        <span>{{ error }}</span>
      </div>

      <div v-else-if="files.length > 0" class="browser-list">
        <div
          v-for="file in files"
          :key="file.path"
          class="file-card"
          :class="{
            'file-loaded': isLoaded(file.name),
            'file-loading': loadingFile === file.name,
          }"
          @click="loadRaster(file)"
        >
          <div class="file-icon">
            <QIcon
              :name="isLoaded(file.name) ? 'check_circle' : 'image'"
              :class="{ 'icon-loaded': isLoaded(file.name) }"
              size="20px"
            />
          </div>
          <div class="file-info">
            <div class="file-name">{{ file.filename }}</div>
            <div class="file-size">{{ file.size_mb }} MB</div>
          </div>
          <div class="file-status">
            <QSpinner v-if="loadingFile === file.name" color="cyan" size="1.2em" :thickness="3" />
            <QBadge v-else-if="isLoaded(file.name)" color="teal-8" label="Loaded" class="loaded-badge" />
          </div>
          <QLinearProgress
            v-if="loadingFile === file.name"
            indeterminate
            color="cyan"
            class="file-progress"
          />
        </div>
      </div>

      <div v-else class="browser-empty">
        <QIcon name="folder_open" size="24px" />
        <span>No raster files found</span>
      </div>
    </div>
  </transition>

  <!-- Active layer list -->
  <div v-if="rasterLayers.length > 0" class="layer-list">
    <div v-for="entry in rasterLayers" :key="entry.name" class="layer-card">
      <QBtn
        flat
        dense
        round
        :icon="entry.visible ? 'visibility' : 'visibility_off'"
        :class="entry.visible ? 'vis-btn-on' : 'vis-btn-off'"
        size="sm"
        @click="toggleVisibility(entry.name)"
      />
      <div class="layer-info">
        <div class="layer-name">{{ entry.name }}</div>
        <div class="layer-meta">{{ entry.width }} × {{ entry.height }} px</div>
      </div>
      <QBtn
        flat
        dense
        round
        icon="close"
        size="xs"
        class="remove-btn"
        @click="removeLayer(entry.name)"
      >
        <QTooltip>Remove layer</QTooltip>
      </QBtn>
    </div>
  </div>

  <div v-else class="empty-layers">
    <QIcon name="add_photo_alternate" size="32px" />
    <span>No layers loaded</span>
    <span class="empty-hint">Click <b>+</b> above to browse datasets</span>
  </div>

  <!-- Basemaps -->
  <div class="section-header basemap-header">
    <QIcon name="public" size="16px" class="section-icon" />
    <span>Basemaps</span>
  </div>

  <div class="basemap-list">
    <div
      v-for="bm in basemaps"
      :key="bm.name"
      class="basemap-card"
      :class="{ 'basemap-active': bm.visible }"
      @click="mapStore.toggleBasemap(bm.name)"
    >
      <QIcon
        :name="bm.name === 'OpenStreetMap' ? 'map' : 'satellite'"
        size="18px"
        :class="bm.visible ? 'basemap-icon-on' : 'basemap-icon-off'"
      />
      <span class="basemap-name">{{ bm.name }}</span>
      <div class="basemap-indicator" :class="{ active: bm.visible }"></div>
    </div>
  </div>
</template>

<style scoped>
/* ── Section headers ───────────────────────────────────────────── */
.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  color: #64748b;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}
.section-icon {
  color: #475569;
}
.section-actions {
  margin-left: auto;
}
.section-btn {
  color: #64748b;
}
.section-btn:hover {
  color: #38bdf8;
}

/* ── Browser section ───────────────────────────────────────────── */
.browser-section {
  background: rgba(255, 255, 255, 0.02);
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}
.browser-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  font-size: 11px;
  font-weight: 500;
  color: #94a3b8;
}
.browser-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 24px 14px;
  font-size: 12px;
  color: #64748b;
}
.browser-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 14px;
  font-size: 12px;
  color: #f87171;
  background: rgba(248, 113, 113, 0.06);
}
.browser-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 24px 14px;
  color: #475569;
  font-size: 12px;
}
.browser-list {
  max-height: 240px;
  overflow-y: auto;
  padding: 4px 8px 8px;
}

/* ── File cards ────────────────────────────────────────────────── */
.file-card {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  margin-bottom: 4px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s ease;
  overflow: hidden;
}
.file-card:hover {
  background: rgba(255, 255, 255, 0.06);
}
.file-card.file-loaded {
  cursor: default;
  opacity: 0.6;
}
.file-card.file-loading {
  background: rgba(56, 189, 248, 0.06);
}
.file-icon {
  color: #475569;
  flex-shrink: 0;
}
.icon-loaded {
  color: #2dd4bf;
}
.file-info {
  flex: 1;
  min-width: 0;
}
.file-name {
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.file-size {
  font-size: 11px;
  color: #64748b;
  margin-top: 1px;
}
.file-status {
  flex-shrink: 0;
}
.loaded-badge {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 4px;
}
.file-progress {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 2px;
}

/* ── Layer list ────────────────────────────────────────────────── */
.layer-list {
  padding: 8px;
}
.layer-card {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  margin-bottom: 4px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.04);
  transition: background 0.15s ease, border-color 0.15s ease;
}
.layer-card:hover {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.08);
}
.vis-btn-on {
  color: #38bdf8;
}
.vis-btn-off {
  color: #475569;
}
.layer-info {
  flex: 1;
  min-width: 0;
}
.layer-name {
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.layer-meta {
  font-size: 11px;
  color: #64748b;
  margin-top: 1px;
}
.remove-btn {
  color: #475569;
  opacity: 0;
  transition: opacity 0.15s ease;
}
.layer-card:hover .remove-btn {
  opacity: 1;
}
.remove-btn:hover {
  color: #f87171;
}

/* ── Empty state ───────────────────────────────────────────────── */
.empty-layers {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 32px 14px;
  color: #475569;
  font-size: 13px;
}
.empty-hint {
  font-size: 11px;
  color: #334155;
}

/* ── Basemaps ──────────────────────────────────────────────────── */
.basemap-header {
  margin-top: 4px;
}
.basemap-list {
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.basemap-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s ease;
}
.basemap-card:hover {
  background: rgba(255, 255, 255, 0.06);
}
.basemap-card.basemap-active {
  background: rgba(56, 189, 248, 0.08);
}
.basemap-icon-on {
  color: #38bdf8;
}
.basemap-icon-off {
  color: #475569;
}
.basemap-name {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
}
.basemap-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #334155;
  transition: background 0.2s ease;
}
.basemap-indicator.active {
  background: #38bdf8;
  box-shadow: 0 0 6px rgba(56, 189, 248, 0.4);
}

/* ── Transitions ───────────────────────────────────────────────── */
.slide-down-enter-active,
.slide-down-leave-active {
  transition: all 0.25s ease;
  max-height: 400px;
  overflow: hidden;
}
.slide-down-enter-from,
.slide-down-leave-to {
  max-height: 0;
  opacity: 0;
}
</style>
