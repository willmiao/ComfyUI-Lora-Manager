# Lora Cycler Node

The **Lora Cycler** node allows you to automatically cycle or randomize through your LoRA collection on each workflow execution. This is useful for:
- Testing different LoRAs automatically
- Creating variety in batch generations
- Exploring your LoRA library systematically

## Quick Start

### Basic Connection Pattern

```
[Lora Cycler] ─── LORA_STACK ───► [Lora Loader (LoraManager)]
      │
      └───── trigger_words ────► [TriggerWord Toggle]
```

**Important:** Connect the `trigger_words` output directly to a TriggerWord Toggle node for real-time trigger word preview. The node will show the selected LoRA's trigger words **before** you run the workflow.

### Node Outputs

| Output | Type | Description |
|--------|------|-------------|
| `LORA_STACK` | LORA_STACK | Connect to a Lora Loader node's `lora_stack` input |
| `trigger_words` | STRING | Connect directly to TriggerWord Toggle for real-time updates |
| `selected_lora` | STRING | Shows the selected LoRA in `<lora:name:strength>` format |
| `total_count` | INT | Number of LoRAs matching your filters |
| `current_index` | INT | Index of the currently selected LoRA (0-based) |

## Selection Modes

| Mode | Description |
|------|-------------|
| **fixed** | Always use the LoRA at the specified index |
| **increment** | Move to the next LoRA each execution (wraps around) |
| **decrement** | Move to the previous LoRA each execution (wraps around) |
| **random** | Pick a random LoRA each execution |

### Random Mode Seeds
- **Seed = 0**: Different random LoRA every time
- **Seed > 0**: Reproducible random selection (same seed = same LoRA)

## Filtering Options

Filter your LoRA collection to cycle through specific subsets:

| Filter | Description | Example |
|--------|-------------|---------|
| `folder_filter` | Match folder path (case-insensitive) | `"characters"` matches `characters/`, `my_characters/` |
| `base_model_filter` | Match base model type | `"sdxl"`, `"pony"`, `"illustrious"` |
| `tag_filter` | Match LoRA tags from Civitai | `"style"`, `"character"` |
| `name_filter` | Match filename or model name | `"anime"`, `"realistic"` |

**Tip:** Use the base model dropdown for quick selection from available base models in your library.

## First Trigger Word Only

Enable `first_trigger_word_only` when working with LoRAs that have multiple trigger words (e.g., a Disney princess LoRA with "elsa", "ariel", "cinderella" as separate trigger words). This ensures only the first trigger word is output, preventing accidental activation of multiple characters.

## How Trigger Words Work

### Real-Time Preview (Before Execution)
The Lora Cycler updates the connected TriggerWord Toggle node **immediately** when:
- You change any filter settings
- You change the selection mode or index
- You enable/disable `first_trigger_word_only`

This preview shows you exactly which LoRA will be used and what trigger words will be applied.

### Why Connect Directly to TriggerWord Toggle?

The Lora Loader node's trigger word output only updates **during execution**. For real-time preview before running the workflow, connect the Cycler's `trigger_words` output directly to the TriggerWord Toggle.

**Correct setup:**
```
[Lora Cycler] ── trigger_words ──► [TriggerWord Toggle]
      │
      └── LORA_STACK ──► [Lora Loader]
```

**Not recommended for real-time preview:**
```
[Lora Cycler] ── LORA_STACK ──► [Lora Loader] ── trigger_words ──► [TriggerWord Toggle]
```
(This works during execution but won't show real-time preview)

## Using with Lora Stack Input

You can connect a `LORA_STACK` from another node (like Lora Stacker) to the Cycler's input. When connected, the Cycler will select from that specific list instead of scanning your LoRA folders.

```
[Lora Stacker] ── LORA_STACK ──► [Lora Cycler] ── LORA_STACK ──► [Lora Loader]
```

## Display Widget

The node shows a **"Next Up"** display at the top showing:
- `[current/total] LoRA Name` - Which LoRA is currently selected
- `(no matching LoRAs)` - When no LoRAs match your filters

This updates in real-time as you change settings.

## Tips

1. **Start with no filters** to see all your LoRAs, then narrow down with filters
2. **Use increment mode** to systematically test each LoRA in your collection
3. **Combine filters** to target specific LoRA types (e.g., `base_model="sdxl"` + `tag_filter="style"`)
4. **Check the total_count output** to see how many LoRAs match your filters
