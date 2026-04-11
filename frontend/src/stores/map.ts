import { defineStore } from 'pinia'
import { computed, markRaw, ref, shallowRef } from 'vue'
import type Map from 'ol/Map'
import TileLayer from 'ol/layer/Tile'
import OSM from 'ol/source/OSM'
import XYZ from 'ol/source/XYZ'
import type { TileCoord } from 'ol/tilecoord'

export type LonLat = [number, number]

export interface BasemapEntry {
  name: string
  layer: TileLayer
  visible: boolean
}

export interface RasterLayerEntry {
  name: string
  path: string
  width: number
  height: number
  minValue: number
  maxValue: number
  bounds: [number, number, number, number]
  layer: TileLayer
  visible: boolean
}

const DEFAULT_CENTER: LonLat = [-98.5795, 39.8283]
const DEFAULT_ZOOM = 4
const API_BASE = 'http://localhost:8000'

/** Convert XYZ tile coordinates to a Bing Maps quadkey string. */
function tileToQuadkey(z: number, x: number, y: number): string {
  let quadkey = ''
  for (let i = z; i > 0; i--) {
    let digit = 0
    const mask = 1 << (i - 1)
    if ((x & mask) !== 0) digit += 1
    if ((y & mask) !== 0) digit += 2
    quadkey += digit
  }
  return quadkey
}

export const useMapStore = defineStore('map', () => {
  const map = shallowRef<Map | null>(null)
  const center = ref<LonLat>([...DEFAULT_CENTER] as LonLat)
  const zoom = ref(DEFAULT_ZOOM)
  const isReady = computed(() => map.value !== null)
  const rasterLayers = ref<RasterLayerEntry[]>([])

  const basemaps = ref<BasemapEntry[]>([
    {
      name: 'OpenStreetMap',
      layer: markRaw(
        new TileLayer({
          source: new OSM(),
        }),
      ),
      visible: true,
    },
    {
      name: 'Microsoft Satellite',
      layer: markRaw(
        new TileLayer({
          source: new XYZ({
            maxZoom: 19,
            tileUrlFunction: (coord: TileCoord) => {
              const z = coord[0]
              const x = coord[1]
              const y = coord[2]
              const quadkey = tileToQuadkey(z!, x!, y!)
              return `https://ecn.t0.tiles.virtualearth.net/tiles/a${quadkey}.jpeg?g=587&n=z`
            },
          }),
          visible: false,
        }),
      ),
      visible: false,
    },
  ])

  const setMap = (nextMap: Map | null) => {
    map.value = nextMap ? markRaw(nextMap) : null
  }

  const setCenter = (nextCenter: LonLat) => {
    center.value = [...nextCenter] as LonLat
  }

  const setZoom = (nextZoom: number) => {
    zoom.value = nextZoom
  }

  const syncViewState = (nextCenter: LonLat, nextZoom: number) => {
    setCenter(nextCenter)
    setZoom(nextZoom)
  }

  const resetView = () => {
    syncViewState(DEFAULT_CENTER, DEFAULT_ZOOM)
  }

  const toggleBasemap = (name: string) => {
    basemaps.value.forEach(entry => {
      if (entry.name === name) {
        entry.layer.setVisible(true);
        entry.visible = true;
      } else {
        entry.layer.setVisible(false)
        entry.visible = false
      }
    });
  }

  const addRasterLayer = (info: {
    name: string
    path: string
    width: number
    height: number
    min_value: number
    max_value: number
    bounds: [number, number, number, number]
  }) => {
    // Remove existing layer with same name
    removeRasterLayer(info.name)

    const tileLayer = new TileLayer({
      source: new XYZ({
        url: `${API_BASE}/tiles/${info.name}/{z}/{x}/{y}.png`,
      }),
    })

    if (map.value) {
      map.value.addLayer(tileLayer)
      // Zoom to raster extent (bounds are in EPSG:3857)
      map.value.getView().fit(info.bounds, { padding: [50, 50, 50, 50] })
    }

    rasterLayers.value.push({
      name: info.name,
      path: info.path,
      width: info.width,
      height: info.height,
      minValue: info.min_value,
      maxValue: info.max_value,
      bounds: info.bounds,
      layer: markRaw(tileLayer),
      visible: true,
    })
  }

  const removeRasterLayer = (name: string) => {
    const index = rasterLayers.value.findIndex((l) => l.name === name)
    if (index === -1) return

    const entry = rasterLayers.value[index]
    if (map.value) {
      map.value.removeLayer(entry.layer)
    }
    rasterLayers.value.splice(index, 1)
  }

  const toggleRasterLayer = (name: string) => {
    const entry = rasterLayers.value.find((l) => l.name === name)
    if (!entry) return

    entry.visible = !entry.visible
    entry.layer.setVisible(entry.visible)
  }

  return {
    map,
    center,
    zoom,
    isReady,
    basemaps,
    rasterLayers,
    setMap,
    setCenter,
    setZoom,
    syncViewState,
    resetView,
    toggleBasemap,
    addRasterLayer,
    removeRasterLayer,
    toggleRasterLayer,
  }
})
