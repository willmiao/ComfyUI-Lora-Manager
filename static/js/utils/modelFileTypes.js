// CivitAI ModelFile.type values eligible as the main download file.
// Mirrors the backend constant MODEL_WEIGHT_FILE_TYPES (py/utils/constants.py).
// Keep both lists in sync when CivitAI introduces new file types.
export const MODEL_WEIGHT_FILE_TYPES = [
    'Model',
    'Pruned Model',
    'Negative',
    'UNet',
    'Diffusion Model',
    'Enhancement LoRA',
];

export function isModelWeightFile(type) {
    return MODEL_WEIGHT_FILE_TYPES.includes(type);
}
