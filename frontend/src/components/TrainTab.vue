<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import {
  QBtn,
  QIcon,
  QSelect,
  QInput,
  QLinearProgress,
  QTooltip,
} from 'quasar'
import { useMapStore } from '@/stores/map'

// ── Constants ───────────────────────────────────────────────────────

const API_BASE = 'http://localhost:8000'

const scenarios = [
  { label: 'Crops', value: 'crops' },
  { label: 'Vegetation', value: 'vegetation' },
  { label: 'Water Bodies', value: 'water_bodies' },
]

// ── Store ───────────────────────────────────────────────────────────

const mapStore = useMapStore()
const { rasterLayers } = storeToRefs(mapStore)

// ── State ───────────────────────────────────────────────────────────

const selectedRaster = ref<string | null>(null)
const selectedScenario = ref<string | null>(null)
const epochs = ref(50)
const learningRate = ref(0.001)
const batchSize = ref(4)

// Training state
const training = ref(false)
const trainJobId = ref<string | null>(null)
const trainEpoch = ref(0)
const trainTotalEpochs = ref(0)
const trainLoss = ref(0)
const trainFinished = ref(false)
const trainError = ref<string | null>(null)
let pollTimer: ReturnType<typeof setInterval> | null = null

// Prediction state
const predicting = ref(false)
const predictFinished = ref(false)
const predictError = ref<string | null>(null)
const predictionFile = ref<string | null>(null)

// Model check
const hasModel = ref(false)
const hasPrediction = ref(false)

// ── Computed ────────────────────────────────────────────────────────

const rasterOptions = computed(() =>
  rasterLayers.value.map((l) => ({
    label: l.name,
    value: l.name,
  })),
)

const canTrain = computed(
  () => !!selectedRaster.value && !!selectedScenario.value && !training.value && !predicting.value,
)

const canPredict = computed(
  () => !!selectedRaster.value && !!selectedScenario.value && hasModel.value && !training.value && !predicting.value,
)

const trainProgress = computed(() => {
  if (trainTotalEpochs.value === 0) return 0
  return trainEpoch.value / trainTotalEpochs.value
})

// ── Model check ─────────────────────────────────────────────────────

const checkModels = async () => {
  hasModel.value = false
  hasPrediction.value = false

  if (!selectedRaster.value) return

  try {
    const res = await fetch(`${API_BASE}/models/${selectedRaster.value}`)
    if (!res.ok) return
    const data = await res.json()
    const model = data.models?.find((m: { scenario: string }) => m.scenario === selectedScenario.value)
    if (model) {
      hasModel.value = true
      hasPrediction.value = model.has_prediction
    }
  } catch {
    // ignore
  }
}

// ── Training ────────────────────────────────────────────────────────

const startTraining = async () => {
  if (!canTrain.value) return

  training.value = true
  trainFinished.value = false
  trainError.value = null
  trainEpoch.value = 0
  trainLoss.value = 0

  try {
    const res = await fetch(`${API_BASE}/train/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        raster_name: selectedRaster.value,
        scenario: selectedScenario.value,
        epochs: epochs.value,
        learning_rate: learningRate.value,
        batch_size: batchSize.value,
      }),
    })

    if (!res.ok) {
      const body = await res.json()
      throw new Error(body.detail || 'Failed to start training')
    }

    const data = await res.json()
    trainJobId.value = data.job_id
    trainTotalEpochs.value = data.epochs

    // Start polling
    pollTimer = setInterval(pollTraining, 1500)
  } catch (e: unknown) {
    trainError.value = e instanceof Error ? e.message : 'Failed to start training'
    training.value = false
  }
}

const pollTraining = async () => {
  if (!trainJobId.value) return

  try {
    const res = await fetch(`${API_BASE}/train/${trainJobId.value}`)
    if (!res.ok) return

    const data = await res.json()
    trainEpoch.value = data.epoch
    trainTotalEpochs.value = data.total_epochs
    trainLoss.value = data.loss

    if (data.finished) {
      trainFinished.value = true
      training.value = false
      hasModel.value = true
      stopPolling()
    }

    if (data.error) {
      trainError.value = data.error
      training.value = false
      stopPolling()
    }
  } catch {
    // continue polling
  }
}

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// ── Prediction ──────────────────────────────────────────────────────

const runPrediction = async () => {
  if (!canPredict.value) return

  predicting.value = true
  predictFinished.value = false
  predictError.value = null
  predictionFile.value = null

  try {
    const res = await fetch(`${API_BASE}/predict/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        raster_name: selectedRaster.value,
        scenario: selectedScenario.value,
      }),
    })

    if (!res.ok) {
      const body = await res.json()
      throw new Error(body.detail || 'Prediction failed')
    }

    const data = await res.json()
    predictionFile.value = data.prediction_file
    predictFinished.value = true
    hasPrediction.value = true
  } catch (e: unknown) {
    predictError.value = e instanceof Error ? e.message : 'Prediction failed'
  } finally {
    predicting.value = false
  }
}

// ── Load prediction as map layer ────────────────────────────────────

const loadPredictionLayer = async () => {
  if (!selectedRaster.value || !selectedScenario.value) return

  const predPath = predictionFile.value
  if (!predPath) return

  const layerName = `${selectedRaster.value}_${selectedScenario.value}_prediction`

  // Load the prediction tif via the rasters endpoint
  try {
    const params = new URLSearchParams({ name: layerName, file_path: predPath })
    const res = await fetch(`${API_BASE}/rasters/?${params}`, { method: 'POST' })
    if (!res.ok) {
      const body = await res.json()
      throw new Error(body.detail || 'Failed to load prediction layer')
    }
    const data = await res.json()
    mapStore.addRasterLayer(data.info)
  } catch (e: unknown) {
    predictError.value = e instanceof Error ? e.message : 'Failed to load prediction layer'
  }
}

// Check models when raster/scenario changes
import { watch } from 'vue'

watch([() => selectedRaster.value, () => selectedScenario.value], () => {
  trainFinished.value = false
  trainError.value = null
  predictFinished.value = false
  predictError.value = null
  predictionFile.value = null
  checkModels()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<template>
  <div class="section-header">
    <QIcon name="model_training" size="16px" class="section-icon" />
    <span>Model Training</span>
  </div>

  <div class="train-body">
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
      :disable="rasterOptions.length === 0 || training"
      clearable
      class="dark-select"
    />

    <!-- Scenario -->
    <label class="field-label mt-16">Scenario</label>
    <QSelect
      v-model="selectedScenario"
      :options="scenarios"
      emit-value
      map-options
      dense
      outlined
      label="Select scenario"
      :disable="!selectedRaster || training"
      clearable
      class="dark-select"
    />

    <!-- Model status -->
    <div v-if="hasModel" class="status-box status-success">
      <QIcon name="check_circle" size="14px" />
      <span>Trained model available</span>
    </div>

    <div class="divider"></div>

    <!-- Hyperparameters -->
    <label class="field-label">Hyperparameters</label>
    <div class="param-grid">
      <div class="param-item">
        <span class="param-label">Epochs</span>
        <QInput
          v-model.number="epochs"
          type="number"
          dense
          outlined
          :disable="training"
          class="dark-input"
        />
      </div>
      <div class="param-item">
        <span class="param-label">Batch Size</span>
        <QInput
          v-model.number="batchSize"
          type="number"
          dense
          outlined
          :disable="training"
          class="dark-input"
        />
      </div>
      <div class="param-item param-wide">
        <span class="param-label">Learning Rate</span>
        <QInput
          v-model.number="learningRate"
          type="number"
          dense
          outlined
          step="0.0001"
          :disable="training"
          class="dark-input"
        />
      </div>
    </div>

    <!-- Train button -->
    <QBtn
      no-caps
      icon="model_training"
      :label="training ? 'Training...' : 'Train Model'"
      class="action-btn train-btn"
      :disable="!canTrain"
      :loading="training"
      @click="startTraining"
    />

    <!-- Training progress -->
    <div v-if="training || trainFinished" class="progress-section">
      <div class="progress-header">
        <span v-if="training">
          Epoch {{ trainEpoch }} / {{ trainTotalEpochs }}
        </span>
        <span v-else class="text-success">Training complete</span>
        <span class="loss-value">Loss: {{ trainLoss.toFixed(4) }}</span>
      </div>
      <QLinearProgress
        :value="trainProgress"
        :color="trainFinished ? 'teal' : 'cyan'"
        class="progress-bar"
      />
    </div>

    <div v-if="trainError" class="status-box status-error">
      <QIcon name="error_outline" size="14px" />
      <span>{{ trainError }}</span>
    </div>
  </div>

  <!-- Prediction section -->
  <div class="section-header" style="margin-top: 4px">
    <QIcon name="auto_fix_high" size="16px" class="section-icon" />
    <span>Prediction</span>
  </div>

  <div class="train-body">
    <div v-if="!hasModel" class="hint-box">
      <QIcon name="info" size="14px" />
      <span>Train a model first to run predictions</span>
    </div>

    <template v-else>
      <QBtn
        no-caps
        icon="auto_fix_high"
        :label="predicting ? 'Running inference...' : 'Run Prediction on Full Raster'"
        class="action-btn predict-btn"
        :disable="!canPredict"
        :loading="predicting"
        @click="runPrediction"
      />

      <div v-if="predicting" class="progress-section">
        <div class="progress-header">
          <span>Running sliding-window inference...</span>
        </div>
        <QLinearProgress indeterminate color="amber" class="progress-bar" />
      </div>

      <div v-if="predictFinished" class="status-box status-success">
        <QIcon name="check_circle" size="14px" />
        <span>Prediction saved as georeferenced GeoTIFF</span>
      </div>

      <QBtn
        v-if="predictFinished"
        no-caps
        icon="add_to_photos"
        label="Load Prediction on Map"
        class="action-btn load-btn"
        @click="loadPredictionLayer"
      >
        <QTooltip>Add the prediction result as a map layer</QTooltip>
      </QBtn>
    </template>

    <div v-if="predictError" class="status-box status-error">
      <QIcon name="error_outline" size="14px" />
      <span>{{ predictError }}</span>
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

/* ── Body ──────────────────────────────────────────────────────── */
.train-body {
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
.mt-16 {
  margin-top: 16px;
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

.dark-input :deep(.q-field__control) {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.1);
  color: #e2e8f0;
  border-radius: 6px;
}
.dark-input :deep(.q-field__native) {
  color: #e2e8f0;
}

.divider {
  height: 1px;
  background: rgba(255, 255, 255, 0.06);
  margin: 16px 0;
}

/* ── Hyperparameters grid ──────────────────────────────────────── */
.param-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-bottom: 16px;
}
.param-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.param-wide {
  grid-column: 1 / -1;
}
.param-label {
  font-size: 11px;
  color: #64748b;
}

/* ── Action buttons ────────────────────────────────────────────── */
.action-btn {
  width: 100%;
  border-radius: 8px;
  font-weight: 600;
  margin-bottom: 12px;
}
.train-btn {
  color: #0f172a;
  background: #38bdf8;
}
.train-btn:hover {
  background: #22d3ee;
}
.predict-btn {
  color: #0f172a;
  background: #fbbf24;
}
.predict-btn:hover {
  background: #f59e0b;
}
.load-btn {
  color: #38bdf8;
  border: 1px solid rgba(56, 189, 248, 0.2);
  background: rgba(56, 189, 248, 0.06);
}
.load-btn:hover {
  background: rgba(56, 189, 248, 0.12);
}
.action-btn[disabled] {
  opacity: 0.5;
}

/* ── Progress ──────────────────────────────────────────────────── */
.progress-section {
  margin-bottom: 12px;
}
.progress-header {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #94a3b8;
  margin-bottom: 6px;
}
.loss-value {
  color: #38bdf8;
  font-family: monospace;
  font-size: 11px;
}
.text-success {
  color: #2dd4bf;
}
.progress-bar {
  border-radius: 4px;
  height: 4px;
}

/* ── Status boxes ──────────────────────────────────────────────── */
.status-box {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 12px;
  margin-top: 10px;
  margin-bottom: 8px;
}
.status-success {
  background: rgba(45, 212, 191, 0.08);
  color: #2dd4bf;
}
.status-error {
  background: rgba(248, 113, 113, 0.08);
  color: #f87171;
}

.hint-box {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  background: rgba(56, 189, 248, 0.06);
  color: #94a3b8;
  font-size: 12px;
}
</style>
