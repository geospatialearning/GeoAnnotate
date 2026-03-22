<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { onMounted, onUnmounted, ref, watch } from 'vue'
import Map from 'ol/Map'
import View from 'ol/View'
import type { EventsKey } from 'ol/events'
import { unByKey } from 'ol/Observable'
import { fromLonLat, toLonLat } from 'ol/proj'
import { useMapStore } from '@/stores/map'

const mapTarget = ref<HTMLElement | null>(null)
const mapStore = useMapStore()
const { center, zoom, basemaps } = storeToRefs(mapStore)

let map: Map | null = null
let moveEndListener: EventsKey | null = null

const areNumbersClose = (left: number, right: number, tolerance = 0.000001) =>
  Math.abs(left - right) <= tolerance

const areLonLatClose = (
  currentCenter: [number, number],
  nextCenter: [number, number],
  tolerance = 0.000001,
) =>
  areNumbersClose(currentCenter[0], nextCenter[0], tolerance) &&
  areNumbersClose(currentCenter[1], nextCenter[1], tolerance)

const syncStoreFromMap = () => {
  if (!map) {
    return
  }

  const view = map.getView()
  const currentCenter = view.getCenter()
  const currentZoom = view.getZoom()

  if (!currentCenter || currentZoom === undefined) {
    return
  }

  const nextCenter = toLonLat(currentCenter) as [number, number]
  mapStore.syncViewState(nextCenter, currentZoom)
}

onMounted(() => {
  if (!mapTarget.value) {
    return
  }

  map = new Map({
    target: mapTarget.value,
    layers: basemaps.value.map((b) => b.layer) as unknown as import('ol/layer/Tile').default[],
    view: new View({
      center: fromLonLat(center.value),
      zoom: zoom.value,
    }),
  })

  mapStore.setMap(map)
  moveEndListener = map.on('moveend', syncStoreFromMap)
  syncStoreFromMap()
})

onUnmounted(() => {
  if (moveEndListener) {
    unByKey(moveEndListener)
    moveEndListener = null
  }

  if (!map) {
    return
  }

  map.setTarget(undefined)
  mapStore.setMap(null)
  map = null
})

watch(
  () => [center.value[0], center.value[1], zoom.value] as const,
  ([lon, lat, nextZoom]) => {
    if (!map) {
      return
    }

    const view = map.getView()
    const currentCenter = view.getCenter()
    const currentZoom = view.getZoom()
    const nextCenter: [number, number] = [lon, lat]

    if (currentCenter) {
      const currentLonLat = toLonLat(currentCenter) as [number, number]

      if (!areLonLatClose(currentLonLat, nextCenter)) {
        view.setCenter(fromLonLat(nextCenter))
      }
    } else {
      view.setCenter(fromLonLat(nextCenter))
    }

    if (currentZoom === undefined || !areNumbersClose(currentZoom, nextZoom)) {
      view.setZoom(nextZoom)
    }
  },
)
</script>

<template>
  <div ref="mapTarget" class="map-viewer"></div>
</template>

<style scoped>
.map-viewer {
  width: 100%;
  height: 100%;
}
</style>
