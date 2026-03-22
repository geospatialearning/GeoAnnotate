<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import {
  QDrawer,
  QTabs,
  QTab,
  QTabPanels,
  QTabPanel,
  QList,
  QItem,
  QItemSection,
  QItemLabel,
  QBtn,
  QBtnToggle,
  QIcon,
  QSelect,
  QSeparator,
  QSpinner,
  QBadge,
  QTooltip,
} from 'quasar'
import { Draw } from 'ol/interaction'
import VectorLayer from 'ol/layer/Vector'
import VectorSource from 'ol/source/Vector'
import { Style, Fill, Stroke, Circle as CircleStyle } from 'ol/style'
import type { Type as GeometryType } from 'ol/geom/Geometry'
import { useMapStore } from '@/stores/map'

// ── Types ───────────────────────────────────────────────────────────

interface RasterFile {
  name: string
  filename: string
  path: string
  size_mb: number
}

interface AnnotationScenario {
  label: string
  value: string
  color: string
}

interface DrawTool {
  label: string
  value: GeometryType
  icon: string
}

// ── Constants ───────────────────────────────────────────────────────

const API_BASE = 'http://localhost:8000'

const scenarios: AnnotationScenario[] = [
  { label: 'Vegetation', value: 'vegetation', color: '#4CAF50' },
  { label: 'Water Bodies', value: 'water_bodies', color: '#2196F3' },
]

const drawTools: DrawTool[] = [
  { label: 'Point', value: 'Point', icon: 'place' },
  { label: 'Line', value: 'LineString', icon: 'timeline' },
  { label: 'Polygon', value: 'Polygon', icon: 'pentagon' },
]

const scenarioOptions = scenarios.map((s) => ({
  label: s.label,
  value: s.value,
}))

// ── Store ───────────────────────────────────────────────────────────

const mapStore = useMapStore()
const { map, isReady, basemaps, rasterLayers } = storeToRefs(mapStore)

const open = defineModel<boolean>('modelValue', { default: true })
const activeTab = ref('layers')

// ── Layers tab: raster browsing ─────────────────────────────────────

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

// ── Layers tab: layer management ────────────────────────────────────

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

// ── Annotations tab: drawing ────────────────────────────────────────

const activeScenario = ref<string | null>(null)
const activeDrawTool = ref<GeometryType | null>(null)

const activeColor = computed(() => {
  const scenario = scenarios.find((s) => s.value === activeScenario.value)
  return scenario?.color ?? '#FF9800'
})

const createStyle = (color: string) =>
  new Style({
    fill: new Fill({ color: color + '33' }),
    stroke: new Stroke({ color, width: 2 }),
    image: new CircleStyle({
      radius: 6,
      fill: new Fill({ color }),
      stroke: new Stroke({ color: '#fff', width: 2 }),
    }),
  })

const vectorSource = new VectorSource()
const vectorLayer = new VectorLayer({
  source: vectorSource,
  style: createStyle('#FF9800'),
})

let activeDrawInteraction: Draw | null = null

const removeDrawInteraction = () => {
  if (activeDrawInteraction && map.value) {
    map.value.removeInteraction(activeDrawInteraction)
    activeDrawInteraction = null
  }
}

const addDrawInteraction = (geometryType: GeometryType) => {
  if (!map.value) return

  removeDrawInteraction()

  activeDrawInteraction = new Draw({
    source: vectorSource,
    type: geometryType,
    style: createStyle(activeColor.value),
  })

  activeDrawInteraction.on('drawend', (event) => {
    event.feature.set('scenario', activeScenario.value)
    event.feature.setStyle(createStyle(activeColor.value))
  })

  map.value.addInteraction(activeDrawInteraction)
}

const clearDrawings = () => {
  vectorSource.clear()
}

watch(isReady, (ready) => {
  if (ready && map.value) {
    map.value.addLayer(vectorLayer)
  }
})

watch(activeDrawTool, (tool) => {
  if (tool && activeScenario.value) {
    addDrawInteraction(tool)
  } else {
    removeDrawInteraction()
  }
})

watch(activeScenario, (scenario) => {
  if (!scenario) {
    activeDrawTool.value = null
    removeDrawInteraction()
    return
  }

  vectorLayer.setStyle(createStyle(activeColor.value))

  if (activeDrawTool.value) {
    addDrawInteraction(activeDrawTool.value)
  }
})

onUnmounted(() => {
  removeDrawInteraction()

  if (map.value) {
    map.value.removeLayer(vectorLayer)
  }
})
</script>

<template>
  <QDrawer v-model="open" side="left" :width="300" bordered class="layer-drawer">
    <!-- Tabs -->
    <QTabs
      v-model="activeTab"
      dense
      active-color="primary"
      indicator-color="primary"
      align="justify"
      narrow-indicator
      class="bg-grey-2"
    >
      <QTab name="layers" icon="layers" label="Layers" no-caps />
      <QTab name="annotate" icon="edit" label="Annotate" no-caps />
    </QTabs>

    <QSeparator />

    <QTabPanels v-model="activeTab" animated class="tab-panels">
      <!-- ── Layers Tab ──────────────────────────────────────────── -->
      <QTabPanel name="layers" class="q-pa-none">
        <!-- Add raster button -->
        <div class="row items-center q-pa-sm">
          <span class="text-caption text-weight-medium col">Map Layers</span>
          <QBtn flat dense round icon="add" size="sm" @click="toggleBrowser">
            <QTooltip>Add Raster</QTooltip>
          </QBtn>
        </div>

        <QSeparator />

        <!-- Raster browser section -->
        <div v-if="showBrowser" class="browser-section">
          <div class="row items-center q-px-sm q-py-xs">
            <span class="text-caption text-weight-medium col">Available Datasets</span>
            <QBtn flat dense round icon="refresh" size="xs" @click="fetchFiles" />
            <QBtn flat dense round icon="close" size="xs" @click="showBrowser = false" />
          </div>

          <div v-if="fetching" class="column items-center q-py-md">
            <QSpinner size="1.5em" />
            <span class="text-caption q-mt-xs">Scanning...</span>
          </div>

          <div v-else-if="error" class="q-pa-sm text-negative text-caption">
            {{ error }}
          </div>

          <QList v-else-if="files.length > 0" separator dense class="browser-list">
            <QItem
              v-for="file in files"
              :key="file.path"
              clickable
              :disable="isLoaded(file.name) || loadingFile === file.name"
              @click="loadRaster(file)"
            >
              <QItemSection avatar>
                <QIcon
                  :name="isLoaded(file.name) ? 'check_circle' : 'map'"
                  :color="isLoaded(file.name) ? 'positive' : 'grey'"
                  size="xs"
                />
              </QItemSection>
              <QItemSection>
                <QItemLabel>{{ file.filename }}</QItemLabel>
                <QItemLabel caption>{{ file.size_mb }} MB</QItemLabel>
              </QItemSection>
              <QItemSection side>
                <QSpinner v-if="loadingFile === file.name" size="1em" />
                <QBadge v-else-if="isLoaded(file.name)" color="positive" label="Loaded" />
              </QItemSection>
            </QItem>
          </QList>

          <div v-else class="q-pa-sm text-grey text-caption text-center">
            No raster files found
          </div>

          <QSeparator />
        </div>

        <!-- Layer list -->
        <QList v-if="rasterLayers.length > 0" separator dense class="layer-list">
          <QItem v-for="entry in rasterLayers" :key="entry.name">
            <QItemSection avatar>
              <QBtn
                flat
                dense
                round
                :icon="entry.visible ? 'visibility' : 'visibility_off'"
                :color="entry.visible ? 'primary' : 'grey'"
                size="sm"
                @click="toggleVisibility(entry.name)"
              />
            </QItemSection>
            <QItemSection>
              <QItemLabel>{{ entry.name }}</QItemLabel>
              <QItemLabel caption>{{ entry.width }} x {{ entry.height }}px</QItemLabel>
            </QItemSection>
            <QItemSection side>
              <QBtn
                flat
                dense
                round
                icon="delete_outline"
                size="sm"
                color="negative"
                @click="removeLayer(entry.name)"
              />
            </QItemSection>
          </QItem>
        </QList>

        <div v-else class="text-center text-grey text-caption q-pa-md">
          No layers added. Click <QIcon name="add" size="xs" /> to browse datasets.
        </div>

        <QSeparator />

        <!-- Basemaps -->
        <div class="q-pa-sm">
          <span class="text-caption text-weight-medium">Basemaps</span>
        </div>
        <QList separator dense>
          <QItem v-for="bm in basemaps" :key="bm.name">
            <QItemSection avatar>
              <QBtn
                flat
                dense
                round
                :icon="bm.visible ? 'visibility' : 'visibility_off'"
                :color="bm.visible ? 'primary' : 'grey'"
                size="sm"
                @click="mapStore.toggleBasemap(bm.name)"
              />
            </QItemSection>
            <QItemSection>
              <QItemLabel>{{ bm.name }}</QItemLabel>
            </QItemSection>
          </QItem>
        </QList>
      </QTabPanel>

      <!-- ── Annotate Tab ────────────────────────────────────────── -->
      <QTabPanel name="annotate" class="q-pa-sm">
        <div class="text-caption text-weight-medium q-mb-sm">Scenario</div>
        <QSelect
          v-model="activeScenario"
          :options="scenarioOptions"
          emit-value
          map-options
          dense
          outlined
          label="Select scenario"
          clearable
          class="q-mb-md"
        />

        <div class="text-caption text-weight-medium q-mb-sm">Draw Tool</div>
        <QBtnToggle
          v-model="activeDrawTool"
          :options="drawTools"
          toggle-color="primary"
          flat
          no-caps
          spread
          :disable="!activeScenario"
          clearable
          class="q-mb-md draw-toggle"
        />

        <QSeparator class="q-my-sm" />

        <QBtn
          flat
          no-caps
          icon="delete"
          label="Clear All Drawings"
          color="negative"
          class="full-width"
          @click="clearDrawings"
        />
      </QTabPanel>
    </QTabPanels>
  </QDrawer>
</template>

<style scoped>
.layer-drawer {
  background: rgba(255, 255, 255, 0.97);
  display: flex;
  flex-direction: column;
}

.tab-panels {
  flex: 1;
  overflow-y: auto;
}

.browser-section {
  background: #f5f5f5;
}

.browser-list {
  max-height: 200px;
  overflow-y: auto;
}

.layer-list {
  overflow-y: auto;
}

.draw-toggle {
  border: 1px solid #e0e0e0;
  border-radius: 4px;
}
</style>
