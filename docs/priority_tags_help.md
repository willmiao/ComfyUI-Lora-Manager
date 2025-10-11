# Priority Tags Configuration Guide

This guide explains how to tailor the tag priority order that powers folder naming and tag suggestions in the LoRA Manager. You only need to edit the comma-separated list of entries shown in the **Priority Tags** field for each model type.

## 1. Pick the Model Type

In the **Priority Tags** dialog you will find one tab per model type (LoRA, Checkpoint, Embedding). Select the tab you want to update; changes on one tab do not affect the others.

## 2. Edit the Entry List

Inside the textarea you will see a line similar to:

```
character, concept, style(toon|toon_style)
```

This entire line is the **entry list**. Replace it with your own ordered list.

### Entry Rules

Each entry is separated by a comma, in order from highest to lowest priority:

- **Canonical tag only:** `realistic`
- **Canonical tag with aliases:** `character(char|chars)`

Aliases live inside `()` and are separated with `|`. The canonical name is what appears in folder names and UI suggestions when any of the aliases are detected. Matching is case-insensitive.

## 3. Save the Settings

After editing the entry list, press **Enter** to save. Use **Shift+Enter** whenever you need a new line. Clicking outside the field also saves automatically. A success toast confirms the update.

## Examples

| Goal | Entry List |
| --- | --- |
| Prefer people over styles | `character, portraits, style(anime\|toon)` |
| Group sci-fi variants | `sci-fi(scifi\|science_fiction), cyberpunk(cyber\|punk)` |
| Alias shorthand tags | `realistic(real\|realisim), photorealistic(photo_real)` |

## Tips

- Keep canonical names short and meaningful—they become folder names.
- Place the most important categories first; the first match wins.
- Avoid duplicate canonical names within the same list; only the first instance is used.

## Troubleshooting

- **Unexpected folder name?** Check that the canonical name you want is placed before other matches.
- **Alias not working?** Ensure the alias is inside parentheses and separated with `|`, e.g. `character(char|chars)`.
- **Validation error?** Look for missing parentheses or stray commas. Each entry must follow the `canonical(alias|alias)` pattern or just `canonical`.

With these basics you can quickly adapt Priority Tags to match your library’s organization style.
