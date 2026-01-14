<template>
  <div class="dual-range-slider" :class="{ disabled, 'is-dragging': dragging !== null, 'has-segments': scaleMode === 'segmented' && effectiveSegments.length > 0 }" @wheel="onWheel">
    <div class="slider-track" ref="trackEl">
      <!-- Background track -->
      <div class="slider-track__bg"></div>
      
      <!-- Segment backgrounds for segmented scale mode -->
      <template v-if="scaleMode === 'segmented' && effectiveSegments.length > 0">
        <div
          v-for="(seg, index) in effectiveSegments"
          :key="'segment-' + index"
          class="slider-track__segment"
          :class="{
            'slider-track__segment--common': seg.wheelStepMultiplier && seg.wheelStepMultiplier < 1,
            'slider-track__segment--expanded': seg.wheelStepMultiplier && seg.wheelStepMultiplier < 1
          }"
          :style="getSegmentStyle(seg, index)"
        ></div>
      </template>
      
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

type ScaleMode = 'linear' | 'segmented'

interface Segment {
  min: number
  max: number
  widthPercent: number
  wheelStepMultiplier?: number
}

const props = withDefaults(defineProps<{
  min: number
  max: number
  valueMin: number
  valueMax: number
  step: number
  defaultRange?: { min: number; max: number }
  disabled?: boolean
  scaleMode?: ScaleMode
  segments?: Segment[]
}>(), {
  disabled: false,
  scaleMode: 'linear',
  segments: () => []
})

const emit = defineEmits<{
  'update:valueMin': [value: number]
  'update:valueMax': [value: number]
}>()

const trackEl = ref<HTMLElement | null>(null)
const dragging = ref<'min' | 'max' | null>(null)

const effectiveSegments = computed<Segment[]>(() => {
  if (props.scaleMode === 'segmented' && props.segments.length > 0) {
    return props.segments
  }
  return []
})

const minPercent = computed(() => {
  if (props.scaleMode === 'segmented' && effectiveSegments.value.length > 0) {
    return valueToPercent(props.valueMin)
  }
  const range = props.max - props.min
  return ((props.valueMin - props.min) / range) * 100
})

const maxPercent = computed(() => {
  if (props.scaleMode === 'segmented' && effectiveSegments.value.length > 0) {
    return valueToPercent(props.valueMax)
  }
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
  if (props.scaleMode === 'segmented' && effectiveSegments.value.length > 0) {
    return valueToPercent(props.defaultRange.max)
  }
  const range = props.max - props.min
  return ((props.defaultRange.max - props.min) / range) * 100
})

const valueToPercent = (value: number): number => {
  const segments = effectiveSegments.value
  if (segments.length === 0) {
    const range = props.max - props.min
    return ((value - props.min) / range) * 100
  }

  let accumulatedPercent = 0
  for (const seg of segments) {
    if (value >= seg.max) {
      accumulatedPercent += seg.widthPercent
    } else if (value >= seg.min) {
      const segRange = seg.max - seg.min
      const valueInSeg = value - seg.min
      accumulatedPercent += (valueInSeg / segRange) * seg.widthPercent
      return accumulatedPercent
    } else {
      break
    }
  }
  return accumulatedPercent
}

const percentToValue = (percent: number): number => {
  const segments = effectiveSegments.value
  if (segments.length === 0) {
    const range = props.max - props.min
    return props.min + (percent / 100) * range
  }

  let accumulatedPercent = 0
  for (const seg of segments) {
    const segEndPercent = accumulatedPercent + seg.widthPercent
    if (percent <= segEndPercent) {
      const segRange = seg.max - seg.min
      const percentInSeg = (percent - accumulatedPercent) / seg.widthPercent
      return seg.min + percentInSeg * segRange
    }
    accumulatedPercent = segEndPercent
  }
  return props.max
}

const getSegmentStyle = (seg: Segment, index: number) => {
  let leftPercent = 0
  for (let i = 0; i < index; i++) {
    leftPercent += effectiveSegments.value[i].widthPercent
  }
  return {
    left: leftPercent + '%',
    width: seg.widthPercent + '%'
  }
}

const formatValue = (val: number): string => {
  if (Number.isInteger(val)) return val.toString()
  return val.toFixed(stepToDecimals(props.step))
}

const stepToDecimals = (step: number): number => {
  const str = step.toString()
  const decimalIndex = str.indexOf('.')
  return decimalIndex === -1 ? 0 : str.length - decimalIndex - 1
}

const snapToStep = (value: number, segmentMultiplier?: number): number => {
  const effectiveStep = segmentMultiplier ? props.step * segmentMultiplier : props.step
  const steps = Math.round((value - props.min) / effectiveStep)
  return Math.max(props.min, Math.min(props.max, props.min + steps * effectiveStep))
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
  const percent = Math.max(0, Math.min(100, (clientX - rect.left) / rect.width * 100))

  const rawValue = percentToValue(percent)
  const multiplier = getSegmentStepMultiplier(rawValue)
  const value = snapToStep(rawValue, multiplier)

  if (dragging.value === 'min') {
    const maxMultiplier = getSegmentStepMultiplier(props.valueMax)
    const maxAllowed = props.valueMax - (props.step * maxMultiplier)
    const newValue = Math.min(value, maxAllowed)
    emit('update:valueMin', newValue)
  } else {
    const minMultiplier = getSegmentStepMultiplier(props.valueMin)
    const minAllowed = props.valueMin + (props.step * minMultiplier)
    const newValue = Math.max(value, minAllowed)
    emit('update:valueMax', newValue)
  }
}

const getSegmentStepMultiplier = (value: number): number => {
  if (props.scaleMode !== 'segmented' || effectiveSegments.value.length === 0) {
    return 1
  }
  
  for (const seg of effectiveSegments.value) {
    if (value >= seg.min && value < seg.max) {
      return seg.wheelStepMultiplier || 1
    }
  }
  return 1
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
    const multiplier = getSegmentStepMultiplier(props.valueMin)
    const effectiveStep = props.step * multiplier
    const newValue = snapToStep(props.valueMin + delta * effectiveStep, multiplier)
    const maxMultiplier = getSegmentStepMultiplier(props.valueMax)
    const maxAllowed = props.valueMax - (props.step * maxMultiplier)
    emit('update:valueMin', Math.min(newValue, maxAllowed))
  } else if (relativeX > maxPixel) {
    const multiplier = getSegmentStepMultiplier(props.valueMax)
    const effectiveStep = props.step * multiplier
    const newValue = snapToStep(props.valueMax + delta * effectiveStep, multiplier)
    const minMultiplier = getSegmentStepMultiplier(props.valueMin)
    const minAllowed = props.valueMin + (props.step * minMultiplier)
    emit('update:valueMax', Math.max(newValue, minAllowed))
  } else {
    const minMultiplier = getSegmentStepMultiplier(props.valueMin)
    const maxMultiplier = getSegmentStepMultiplier(props.valueMax)
    const newMin = snapToStep(props.valueMin - delta * props.step * minMultiplier, minMultiplier)
    const newMax = snapToStep(props.valueMax + delta * props.step * maxMultiplier, maxMultiplier)

    if (newMin < props.valueMin) {
      emit('update:valueMin', Math.max(newMin, props.min))
      emit('update:valueMax', Math.min(newMax, props.max))
    } else {
      const minAllowed = props.valueMin + (props.step * minMultiplier)
      if (newMin < newMax - (props.step * minMultiplier)) {
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

.dual-range-slider.is-dragging {
  cursor: grabbing;
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

.slider-track__segment {
  position: absolute;
  top: 0;
  bottom: 0;
  background: rgba(66, 153, 225, 0.08);
  border-radius: 2px;
}

.slider-track__segment--expanded {
  background: rgba(66, 153, 225, 0.15);
}

.slider-track__segment:not(:last-child)::after {
  content: '';
  position: absolute;
  top: -1px;
  bottom: -1px;
  right: 0;
  width: 1px;
  background: rgba(255, 255, 255, 0.1);
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
