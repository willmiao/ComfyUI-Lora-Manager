<template>
  <div class="single-slider" :class="{ disabled, 'is-dragging': dragging }" data-capture-wheel="true" @wheel="onWheel">
    <div class="slider-track" ref="trackEl">
      <div class="slider-track__bg"></div>
      <div
        class="slider-track__active"
        :style="{ width: percent + '%' }"
      ></div>
      <div
        v-if="defaultRange"
        class="slider-track__default"
        :style="{
          left: defaultMinPercent + '%',
          width: (defaultMaxPercent - defaultMinPercent) + '%'
        }"
      ></div>
    </div>

    <div
      class="slider-handle"
      :style="{ left: percent + '%' }"
      @pointerdown.stop="startDrag"
      @pointermove.stop="onDrag"
      @pointerup.stop="stopDrag"
      @pointercancel.stop="stopDrag"
    >
      <div class="slider-handle__thumb"></div>
      <div class="slider-handle__value">{{ formatValue(value) }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

const props = withDefaults(defineProps<{
  min: number
  max: number
  value: number
  step: number
  defaultRange?: { min: number; max: number }
  disabled?: boolean
}>(), {
  disabled: false
})

const emit = defineEmits<{
  'update:value': [value: number]
}>()

const trackEl = ref<HTMLElement | null>(null)
const dragging = ref(false)
const activePointerId = ref<number | null>(null)

const percent = computed(() => {
  const range = props.max - props.min
  return ((props.value - props.min) / range) * 100
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

const startDrag = (event: PointerEvent) => {
  if (props.disabled) return

  event.preventDefault()
  event.stopPropagation()

  dragging.value = true
  activePointerId.value = event.pointerId

  // Capture pointer to receive all subsequent events regardless of stopPropagation
  const target = event.currentTarget as HTMLElement
  target.setPointerCapture(event.pointerId)

  // Process initial position
  updateValue(event)
}

const onDrag = (event: PointerEvent) => {
  if (!dragging.value) return
  event.stopPropagation()
  updateValue(event)
}

const updateValue = (event: PointerEvent) => {
  if (!trackEl.value || !dragging.value) return

  const rect = trackEl.value.getBoundingClientRect()
  const percent = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width))
  const rawValue = props.min + percent * (props.max - props.min)
  const value = snapToStep(rawValue)

  emit('update:value', value)
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
  const newValue = snapToStep(props.value + delta * props.step)
  emit('update:value', newValue)
}

const stopDrag = (event?: PointerEvent) => {
  if (!dragging.value) return

  if (event) {
    event.stopPropagation()
    // Release pointer capture
    const target = event.currentTarget as HTMLElement
    if (activePointerId.value !== null) {
      target.releasePointerCapture(activePointerId.value)
    }
  }

  dragging.value = false
  activePointerId.value = null
}
</script>

<style scoped>
.single-slider {
  position: relative;
  width: 100%;
  height: 24px;
  user-select: none;
  cursor: default !important;
  touch-action: none;
}

.single-slider.disabled {
  opacity: 0.4;
  pointer-events: none;
}

.single-slider.is-dragging {
  cursor: ew-resize !important;
}

.slider-track {
  position: absolute;
  top: 12px;
  left: 0;
  right: 0;
  height: 4px;
  background: var(--comfy-input-bg, #333);
  border-radius: 4px;
  cursor: default !important;
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
  left: 0;
  background: rgba(66, 153, 225, 0.6);
  border-radius: 2px;
  transition: width 0.05s linear;
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
  cursor: ew-resize !important;
  z-index: 2;
  touch-action: none;
}

.slider-handle__thumb {
  width: 14px;
  height: 14px;
  background: var(--fg-color, #fff);
  border-radius: 50%;
  position: absolute;
  top: 7px;
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
  font-size: 12px;
  font-family: 'SF Mono', 'Roboto Mono', monospace;
  color: var(--fg-color, #fff);
  opacity: 0.8;
  white-space: nowrap;
  pointer-events: none;
}
</style>
