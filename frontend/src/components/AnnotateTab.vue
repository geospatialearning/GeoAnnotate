<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import {
  QBtn,
  QIcon,
  QSelect,
  QBadge,
  QTooltip,
  QLinearProgress,
} from 'quasar'
import { Draw } from 'ol/interaction'
import VectorLayer from 'ol/layer/Vector'
import VectorSource from 'ol/source/Vector'
import { Style, Fill, Stroke } from 'ol/style'
import type Feature from 'ol/Feature'
import type Polygon from 'ol/geom/Polygon'
import { useMapStore } from '@/stores/map'

// ── Types ───────────────────────────────────────────────────────────

interface AnnotationScenario {
  label: string
  value: string
  color: string
}

interface AnnotationEntry {
  id: number
  scenario: string
  color: string
  feature: Feature
}

// ── Constants ───────────────────────────────────────────────────────

const API_BASE = 'http://localhost:8000'

const scenarios: AnnotationScenario[] = [
  { label: 'Crops', value: 'crops', color: '#5CAE70' },
  { label: 'Vegetation', value: 'vegetation', color: '#4CAF50' },
  { label: 'Water Bodies', value: 'water_bodies', color: '#2196F3' },
]

const scenarioOptions = scenarios.map((s) => ({
  label: s.label,
  value: s.value,
}))

// ── Store ───────────────────────────────────────────────────────────

const mapStore = useMapStore()
const { map, isReady, rasterLayers } = storeToRefs(mapStore)

// ── State ───────────────────────────────────────────────────────────

const selectedRaster = ref<string | null>(null)
const activeScenario = ref<string | null>(null)
const isDrawing = ref(false)
const annotations = ref<AnnotationEntry[]>([])
const submitting = ref(false)
const submitProgress = ref(0)
const submitTotal = ref(0)
const submitError = ref<string | null>(null)
let nextAnnotationId = 1

// ── Expose annotation count for parent badge ────────────────────────

const annotationCount = computed(() => annotations.value.length)
defineExpose({ annotationCount })

// ── Computed ────────────────────────────────────────────────────────

const rasterOptions = computed(() =>
  rasterLayers.value.map((l) => ({
    label: l.name,
    value: l.name,
  })),
)

const activeColor = computed(() => {
  const scenario = scenarios.find((s) => s.value === activeScenario.value)
  return scenario?.color ?? '#FF9800'
})

const canDraw = computed(() => !!selectedRaster.value && !!activeScenario.value)

const canSubmit = computed(() => annotations.value.length > 0 && !submitting.value)

// ── Drawing ─────────────────────────────────────────────────────────

const createStyle = (color: string) =>
  new Style({
    fill: new Fill({ color: color + '33' }),
    stroke: new Stroke({ color, width: 2 }),
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
  isDrawing.value = false
}

const startDrawing = () => {
  if (!map.value || !canDraw.value) return

  removeDrawInteraction()

  activeDrawInteraction = new Draw({
    source: vectorSource,
    type: 'Polygon',
    style: createStyle(activeColor.value),
  })

  activeDrawInteraction.on('drawend', (event) => {
    const scenario = activeScenario.value!
    const color = activeColor.value
    event.feature.set('scenario', scenario)
    event.feature.set('raster', selectedRaster.value)
    event.feature.setStyle(createStyle(color))

    annotations.value.push({
      id: nextAnnotationId++,
      scenario,
      color,
      feature: event.feature,
    })
  })

  map.value.addInteraction(activeDrawInteraction)
  isDrawing.value = true
}

const stopDrawing = () => {
  removeDrawInteraction()
}

const removeAnnotation = (id: number) => {
  const idx = annotations.value.findIndex((a) => a.id === id)
  if (idx === -1) return

  const entry = annotations.value[idx]!
  vectorSource.removeFeature(entry.feature as Feature)
  annotations.value.splice(idx, 1)
}

const clearAnnotations = () => {
  vectorSource.clear()
  annotations.value = []
}

// ── Submission ──────────────────────────────────────────────────────

const submitAnnotations = async () => {
  if (!canSubmit.value) return

  submitting.value = true
  submitError.value = null
  submitProgress.value = 0
  submitTotal.value = annotations.value.length

  const toSubmit = [...annotations.value]

  for (let i = 0; i < toSubmit.length; i++) {
    const entry = toSubmit[i]!
    const geom = entry.feature.getGeometry() as Polygon
    const coords = geom.getCoordinates()[0]

    try {
      const res = await fetch(`${API_BASE}/annotations/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          raster_name: selectedRaster.value,
          scenario: entry.scenario,
          polygon: coords,
        }),
      })

      if (!res.ok) {
        const body = await res.json()
        throw new Error(body.detail || `Failed to submit annotation ${i + 1}`)
      }

      submitProgress.value = i + 1
    } catch (e: unknown) {
      submitError.value = e instanceof Error ? e.message : `Failed at annotation ${i + 1}`
      submitting.value = false
      return
    }
  }

  clearAnnotations()
  submitting.value = false
}

// ── Watchers ────────────────────────────────────────────────────────

watch(isReady, (ready) => {
  if (ready && map.value) {
    map.value.addLayer(vectorLayer)
  }
}, { immediate: true })

watch(canDraw, (can) => {
  if (!can) {
    removeDrawInteraction()
  }
})

watch(activeScenario, () => {
  if (isDrawing.value && canDraw.value) {
    startDrawing()
  }
})

// Clear selected raster if it gets removed from loaded layers
watch(rasterLayers, (layers) => {
  if (selectedRaster.value && !layers.some((l) => l.name === selectedRaster.value)) {
    selectedRaster.value = null
  }
}, { deep: true })

onUnmounted(() => {
  removeDrawInteraction()

  if (map.value) {
    map.value.removeLayer(vectorLayer)
  }
})
</script>

<template>
  <div class="section-header">
    <QIcon name="edit_note" size="16px" class="section-icon" />
    <span>Annotation Settings</span>
  </div>

  <div class="annotate-body">
    <!-- Raster selection -->
    <label class="field-label">Target Raster</label>
    <QSelect
      v-model="selectedRaster"
      :options="rasterOptions"
      emit-value
      map-options
      dense
      outlined
      :label="rasterOptions.length > 0 ? 'Select loaded raster' : 'No rasters loaded'"
      :disable="rasterOptions.length === 0 || submitting"
      clearable
      class="dark-select"
    />

    <div v-if="rasterOptions.length === 0" class="hint-box">
      <QIcon name="info" size="14px" />
      <span>Load a raster in the Layers tab first</span>
    </div>

    <!-- Scenario selection -->
    <label class="field-label" style="margin-top: 16px">Scenario</label>
    <QSelect
      v-model="activeScenario"
      :options="scenarioOptions"
      emit-value
      map-options
      dense
      outlined
      label="Select scenario"
      :disable="!selectedRaster || submitting"
      clearable
      class="dark-select"
    />

    <!-- Draw controls -->
    <div class="divider"></div>

    <div class="draw-controls">
      <QBtn
        v-if="!isDrawing"
        no-caps
        icon="pentagon"
        label="Draw Polygon"
        class="draw-btn"
        :disable="!canDraw || submitting"
        @click="startDrawing"
      />
      <QBtn
        v-else
        no-caps
        icon="stop"
        label="Stop Drawing"
        class="draw-btn drawing-active"
        @click="stopDrawing"
      />
    </div>

    <div v-if="isDrawing" class="draw-hint">
      <QIcon name="mouse" size="14px" />
      <span>Click on the map to draw polygon vertices. Double-click to finish.</span>
    </div>
  </div>

  <!-- Annotations list -->
  <div class="section-header" style="margin-top: 4px">
    <QIcon name="format_list_bulleted" size="16px" class="section-icon" />
    <span>Annotations</span>
    <QBadge v-if="annotationCount > 0" color="cyan" class="count-badge">
      {{ annotationCount }}
    </QBadge>
    <div class="section-actions">
      <QBtn
        v-if="annotationCount > 0"
        flat
        dense
        round
        icon="delete_sweep"
        size="sm"
        class="section-btn clear-all-btn"
        :disable="submitting"
        @click="clearAnnotations"
      >
        <QTooltip>Clear all</QTooltip>
      </QBtn>
    </div>
  </div>

  <div v-if="annotations.length > 0" class="annotation-list">
    <div v-for="ann in annotations" :key="ann.id" class="annotation-card">
      <div class="annotation-dot" :style="{ background: ann.color }"></div>
      <div class="annotation-info">
        <div class="annotation-label">{{ ann.scenario }}</div>
        <div class="annotation-id">Polygon #{{ ann.id }}</div>
      </div>
      <QBtn
        flat
        dense
        round
        icon="close"
        size="xs"
        class="remove-btn"
        :disable="submitting"
        @click="removeAnnotation(ann.id)"
      >
        <QTooltip>Remove</QTooltip>
      </QBtn>
    </div>
  </div>

  <div v-else class="empty-annotations">
    <QIcon name="draw" size="28px" />
    <span>No annotations yet</span>
    <span class="empty-hint">Select a raster and scenario, then draw polygons</span>
  </div>

  <!-- Submit section -->
  <div v-if="annotations.length > 0" class="submit-section">
    <div class="divider"></div>

    <div v-if="submitError" class="submit-error">
      <QIcon name="error_outline" size="14px" />
      <span>{{ submitError }}</span>
    </div>

    <div v-if="submitting" class="submit-progress">
      <div class="submit-progress-text">
        Submitting {{ submitProgress }} / {{ submitTotal }}...
      </div>
      <QLinearProgress
        :value="submitProgress / submitTotal"
        color="cyan"
        class="submit-bar"
      />
    </div>

    <QBtn
      no-caps
      icon="cloud_upload"
      :label="submitting ? 'Submitting...' : `Submit ${annotationCount} Annotation${annotationCount > 1 ? 's' : ''}`"
      class="submit-btn"
      :disable="!canSubmit"
      :loading="submitting"
      @click="submitAnnotations"
    />
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

/* ── Annotate body ─────────────────────────────────────────────── */
.annotate-body {
  padding: 14px;
}
.field-label {
  display: block;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: #64748b;
  margin-bottom: 8px;
}

.hint-box {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  background: rgba(56, 189, 248, 0.06);
  color: #94a3b8;
  font-size: 12px;
}

.dark-select :deep(.q-field__control) {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.1);
  color: #e2e8f0;
  border-radius: 8px;
}
.dark-select :deep(.q-field__label) {
  color: #64748b;
}
.dark-select :deep(.q-field__native) {
  color: #e2e8f0;
}
.dark-select :deep(.q-field__append) {
  color: #64748b;
}

.divider {
  height: 1px;
  background: rgba(255, 255, 255, 0.06);
  margin: 16px 0;
}

/* ── Draw controls ─────────────────────────────────────────────── */
.draw-controls {
  display: flex;
  gap: 8px;
}
.draw-btn {
  flex: 1;
  color: #38bdf8;
  border: 1px solid rgba(56, 189, 248, 0.2);
  border-radius: 8px;
  background: rgba(56, 189, 248, 0.06);
}
.draw-btn:hover {
  background: rgba(56, 189, 248, 0.12);
}
.draw-btn.drawing-active {
  color: #fbbf24;
  border-color: rgba(251, 191, 36, 0.3);
  background: rgba(251, 191, 36, 0.08);
  animation: pulse-border 2s ease-in-out infinite;
}
@keyframes pulse-border {
  0%, 100% { border-color: rgba(251, 191, 36, 0.15); }
  50% { border-color: rgba(251, 191, 36, 0.4); }
}

.draw-hint {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 10px;
  padding: 8px 12px;
  border-radius: 6px;
  background: rgba(251, 191, 36, 0.06);
  color: #fbbf24;
  font-size: 12px;
  line-height: 1.4;
}

/* ── Annotation list ───────────────────────────────────────────── */
.count-badge {
  margin-left: 4px;
  font-size: 10px;
  padding: 1px 6px;
}
.clear-all-btn:hover {
  color: #f87171 !important;
}
.annotation-list {
  padding: 8px;
}
.annotation-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  margin-bottom: 4px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.04);
  transition: background 0.15s ease, border-color 0.15s ease;
}
.annotation-card:hover {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.08);
}
.annotation-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.annotation-info {
  flex: 1;
  min-width: 0;
}
.annotation-label {
  font-size: 13px;
  font-weight: 500;
  text-transform: capitalize;
}
.annotation-id {
  font-size: 11px;
  color: #64748b;
  margin-top: 1px;
}
.remove-btn {
  color: #475569;
  opacity: 0;
  transition: opacity 0.15s ease;
}
.annotation-card:hover .remove-btn {
  opacity: 1;
}
.remove-btn:hover {
  color: #f87171;
}

.empty-annotations {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 24px 14px;
  color: #475569;
  font-size: 13px;
}
.empty-hint {
  font-size: 11px;
  color: #334155;
}

/* ── Submit section ────────────────────────────────────────────── */
.submit-section {
  padding: 0 14px 14px;
}
.submit-error {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 8px 12px;
  border-radius: 6px;
  background: rgba(248, 113, 113, 0.08);
  color: #f87171;
  font-size: 12px;
}
.submit-progress {
  margin-bottom: 12px;
}
.submit-progress-text {
  font-size: 12px;
  color: #94a3b8;
  margin-bottom: 6px;
}
.submit-bar {
  border-radius: 4px;
  height: 4px;
}
.submit-btn {
  width: 100%;
  color: #0f172a;
  background: #38bdf8;
  border-radius: 8px;
  font-weight: 600;
}
.submit-btn:hover {
  background: #22d3ee;
}
.submit-btn[disabled] {
  opacity: 0.5;
}
</style>
