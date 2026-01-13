<template>
  <div class="dual-range-slider" :class="{ disabled }" @wheel="onWheel">
    <div class="slider-track" ref="trackEl">
      <!-- Background track -->
      <div class="slider-track__bg"></div>
      <!-- Active track (colored range between handles) -->
      <div
        class="slider-track__active"
        :style="{ left: minPercent + '%', width: (maxPercent - minPercent) + '%' }"
      ></div>
      <!-- Default range indicators -->
      <div
        v-if="defaultRange"
        class="slider-track__default"
        :style="{
          left: defaultMinPercent + '%',
          width: (defaultMaxPercent - defaultMinPercent) + '%'
        }"
      ></div>
    </div>

    <!-- Handles with value labels -->
    <div
      class="slider-handle slider-handle--min"
      :style="{ left: minPercent + '%' }"
      @mousedown="startDrag('min', $event)"
      @touchstart="startDrag('min', $event)"
    >
      <div class="slider-handle__thumb"></div>
      <div class="slider-handle__value">{{ formatValue(valueMin) }}</div>
    </div>

    <div
      class="slider-handle slider-handle--max"
      :style="{ left: maxPercent + '%' }"
      @mousedown="startDrag('max', $event)"
      @touchstart="startDrag('max', $event)"
    >
      <div class="slider-handle__thumb"></div>
      <div class="slider-handle__value">{{ formatValue(valueMax) }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'

const props = withDefaults(defineProps<{
  min: number
  max: number
  valueMin: number
  valueMax: number
  step: number
  defaultRange?: { min: number; max: number }
  disabled?: boolean
}>(), {
  disabled: false
})

const emit = defineEmits<{
  'update:valueMin': [value: number]
  'update:valueMax': [value: number]
}>()

const trackEl = ref<HTMLElement | null>(null)
const dragging = ref<'min' | 'max' | null>(null)

const minPercent = computed(() => {
  const range = props.max - props.min
  return ((props.valueMin - props.min) / range) * 100
})

const maxPercent = computed(() => {
  const range = props.max - props.min
  return ((props.valueMax - props.min) / range) * 100
})

const defaultMinPercent = computed(() => {
  if (!props.defaultRange) return 0
  const range = props.max - props.min
  return ((props.defaultRange.min - props.min) / range) * 100
})

const defaultMaxPercent = computed(() => {
  if (!props.defaultRange) return 100
  const range = props.max - props.min
  return ((props.defaultRange.max - props.min) / range) * 100
})

const formatValue = (val: number): string => {
  if (Number.isInteger(val)) return val.toString()
  return val.toFixed(stepToDecimals(props.step))
}

const stepToDecimals = (step: number): number => {
  const str = step.toString()
  const decimalIndex = str.indexOf('.')
  return decimalIndex === -1 ? 0 : str.length - decimalIndex - 1
}

const snapToStep = (value: number): number => {
  const steps = Math.round((value - props.min) / props.step)
  return Math.max(props.min, Math.min(props.max, props.min + steps * props.step))
}

const startDrag = (handle: 'min' | 'max', event: MouseEvent | TouchEvent) => {
  if (props.disabled) return

  event.preventDefault()
  dragging.value = handle

  document.addEventListener('mousemove', onDrag)
  document.addEventListener('mouseup', stopDrag)
  document.addEventListener('touchmove', onDrag, { passive: false })
  document.addEventListener('touchend', stopDrag)
}

const onDrag = (event: MouseEvent | TouchEvent) => {
  if (!trackEl.value || !dragging.value) return

  event.preventDefault()

  const clientX = 'touches' in event ? event.touches[0].clientX : event.clientX
  const rect = trackEl.value.getBoundingClientRect()
  const percent = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
  const rawValue = props.min + percent * (props.max - props.min)
  const value = snapToStep(rawValue)

  if (dragging.value === 'min') {
    const maxAllowed = props.valueMax - props.step
    const newValue = Math.min(value, maxAllowed)
    emit('update:valueMin', newValue)
  } else {
    const minAllowed = props.valueMin + props.step
    const newValue = Math.max(value, minAllowed)
    emit('update:valueMax', newValue)
  }
}

const onWheel = (event: WheelEvent) => {
  if (props.disabled) return

  const rect = trackEl.value?.getBoundingClientRect()
  if (!rect) return

  const rootRect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  if (event.clientX < rootRect.left || event.clientX > rootRect.right ||
      event.clientY < rootRect.top || event.clientY > rootRect.bottom) return

  event.preventDefault()

  const delta = event.deltaY > 0 ? -1 : 1
  const relativeX = event.clientX - rect.left
  const rangeWidth = rect.width

  const minPixel = (minPercent.value / 100) * rangeWidth
  const maxPixel = (maxPercent.value / 100) * rangeWidth

  if (relativeX < minPixel) {
    const newValue = snapToStep(props.valueMin + delta * props.step)
    const maxAllowed = props.valueMax - props.step
    emit('update:valueMin', Math.min(newValue, maxAllowed))
  } else if (relativeX > maxPixel) {
    const newValue = snapToStep(props.valueMax + delta * props.step)
    const minAllowed = props.valueMin + props.step
    emit('update:valueMax', Math.max(newValue, minAllowed))
  } else {
    const newMin = snapToStep(props.valueMin - delta * props.step)
    const newMax = snapToStep(props.valueMax + delta * props.step)

    if (newMin < props.valueMin) {
      emit('update:valueMin', Math.max(newMin, props.min))
      emit('update:valueMax', Math.min(newMax, props.max))
    } else {
      if (newMin < newMax - props.step) {
        emit('update:valueMin', newMin)
        emit('update:valueMax', newMax)
      }
    }
  }
}

const stopDrag = () => {
  dragging.value = null
  document.removeEventListener('mousemove', onDrag)
  document.removeEventListener('mouseup', stopDrag)
  document.removeEventListener('touchmove', onDrag)
  document.removeEventListener('touchend', stopDrag)
}

onUnmounted(() => {
  stopDrag()
})
</script>

<style scoped>
.dual-range-slider {
  position: relative;
  width: 100%;
  height: 32px;
  user-select: none;
}

.dual-range-slider.disabled {
  opacity: 0.4;
  pointer-events: none;
}

.slider-track {
  position: absolute;
  top: 14px;
  left: 0;
  right: 0;
  height: 4px;
  background: var(--comfy-input-bg, #333);
  border-radius: 2px;
}

.slider-track__bg {
  position: absolute;
  inset: 0;
  background: rgba(66, 153, 225, 0.15);
  border-radius: 2px;
}

.slider-track__active {
  position: absolute;
  top: 0;
  bottom: 0;
  background: rgba(66, 153, 225, 0.6);
  border-radius: 2px;
  transition: left 0.05s linear, width 0.05s linear;
}

.slider-track__default {
  position: absolute;
  top: 0;
  bottom: 0;
  background: rgba(66, 153, 225, 0.1);
  border-radius: 2px;
}

.slider-handle {
  position: absolute;
  top: 0;
  transform: translateX(-50%);
  cursor: grab;
  z-index: 2;
}

.slider-handle:active {
  cursor: grabbing;
}

.slider-handle__thumb {
  width: 12px;
  height: 12px;
  background: var(--fg-color, #fff);
  border-radius: 50%;
  position: absolute;
  top: 10px;
  left: 0;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
  transition: transform 0.15s ease;
}

.slider-handle:hover .slider-handle__thumb {
  transform: scale(1.1);
}

.slider-handle:active .slider-handle__thumb {
  transform: scale(1.15);
}

.slider-handle__value {
  position: absolute;
  top: 0;
  left: 50%;
  transform: translateX(-50%);
  font-size: 10px;
  font-family: 'SF Mono', 'Roboto Mono', monospace;
  color: var(--fg-color, #fff);
  opacity: 0.8;
  white-space: nowrap;
  pointer-events: none;
}

.slider-handle--min .slider-handle__value {
  text-align: center;
}

.slider-handle--max .slider-handle__value {
  text-align: center;
}
</style>
