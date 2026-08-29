# i18n Translation Guidelines

This document is the canonical set of conventions for translating LoRA Manager UI strings.
It applies to **human translators and AI agents** alike. Read it before editing anything in
`locales/`.

Source of truth: `locales/en.json` (10 locales, 1810 leaf keys; all locales share the exact
same key structure).

Locales: `en`, `zh-CN`, `zh-TW`, `ja`, `ko`, `fr`, `de`, `es`, `ru`, `he` (RTL).

> **Status (2026-08 sweep):** a full audit was executed and the terminology, placeholder,
> stale-text, and untranslated-block fixes described in §2–§6 were applied across all locales
> (commits `3c3ac49f` … `fd1227d3`). The tables below are now the **normative target state**,
> not a to-do list — future edits should preserve these renderings and only add what is new.

---

## 1. Hard rules (do not violate)

### R1 — Key structure is sacred
- Only `locales/en.json` may add/remove/rename keys. All other locales must keep the exact
  same nested key set. `tests/i18n/test_i18n.py` enforces this.
- When a new UI string is added to `en.json`, run
  `python scripts/sync_translation_keys.py` (adds the missing keys to all locales with
  placeholder copies), then translate the newly added keys in every locale.
- Never reorder, re-indent, or reformat a locale file "for tidiness". The sync script
  preserves formatting; manual reformatting creates noisy diffs.

### R2 — Placeholders and HTML must be preserved verbatim
- `{name}`-style placeholders must appear in the translation exactly as in `en.json`.
  Do not invent placeholders the source string does not have — the caller may not pass them
  (example bug: `zh-CN recipes.controls.import.downloadLocationPreview` added `{path}`; the
  template renders this key with no parameters, so the literal text `{path}` shows in the UI).
- `{{...}}` in a locale value is an escaped literal brace — keep it identical.
- Keep embedded HTML tags (e.g. `<strong>...</strong>`, `<code>...</code>`) intact.
  You may move the tag around the sentence if the target language needs different word order.

### R3 — Never translate or transliterate these
- Model types: **LoRA, Checkpoint, Embedding, Diffusion Model**
- Products/brands: **LoRA Manager, ComfyUI, CivitAI, CivArchive, HuggingFace, Ko-fi**
- Ecosystem names: **LyCORIS, DoRA**, trigger-adjacent jargon **Prompt, Workflow**
  (these are used as-is in the target-language SD community; see §2 per-language policy)
- Theme names: **Nord, Midnight, Monokai, Dracula, Solarized**

### R4 — The "Recipe" convention (the most important domain term)
Product intent: a *Recipe* records a **LoRA combination + generation parameters**
(prompt, seed, sampler, …) that reproduces an image style. The metaphor is a **cooking
recipe** — "follow it and you get a similar dish". It is **not** a menu, not a dish list,
not a prescription.

Decision per language — translate only into a word whose everyday primary meaning is a
cooking recipe; where that word would mislead users, **keep the English "Recipe(s)"**:

| Locale | Use | Never use |
|---|---|---|
| fr | **Recipe / Recipes** (keep English) | recette(s) — cooking reading is secondary and it was explicitly judged misleading |
| zh-CN / zh-TW | 配方 | 食谱 (reads as "food cookbook") |
| ja | レシピ | — (leftover English "Recipe" in `initialization.recipes.title` / `toast.recipes.recipeSaved` → translate) |
| ko | 레시피 | — |
| de | Rezept / Rezepte | — (cooking meaning dominant; prescription reading acceptable) |
| es | receta / recetas | — (cooking meaning dominant) |
| ru | рецепт / рецепты | — (leftover English "Recipe" in `initialization.recipes.title` / `toast.recipes.recipeSaved` → translate) |
| he | מתכון / מתכונים | — (cooking meaning dominant) |

Whatever the choice, **one concept = one noun within a locale**. Currently violated in:
- `fr` — "Recipe" (~97 keys, incl. nav) mixed with "recette" (~58 keys)
- `zh-CN` / `zh-TW` — 配方 (126/122 keys) mixed with 食谱 / 食譜 (14/17 keys, all in the
  *rematch* flow: `globalContextMenu.rematchRecipes.*`, `toast.recipes.rematch*`)
- `de` — "Rezept" (136 keys) mixed with leftover English "Recipe" (5 keys)
- `ja` / `ru` — leftover English "Recipe" in `initialization.recipes.title` ("Recipe Manager
  zu initialisieren" / «Инициализация Recipe Manager») and `toast.recipes.recipeSaved`

### R5 — One term, one rendering (within each locale)
Same source word must not be translated several ways in one file. Known offender areas
(see §5 for the full fix list): recipe, Checkpoint, Embedding, prompt, base model, preset,
workflow, hash, metadata, tags, bulk. Every locale currently mixes variants of at least one
of these — pick the preferred form in the §2 tables and normalize.

### R6 — Register consistency
- `zh-CN` / `zh-TW`: pick 你 or 您 once. Do not mix (zh-CN has 44×你 + 5×您; zh-TW has
  27×您 + 18×你).
- `de`: pick "du" or "Sie" once (currently 143×Sie + ~7×du).
- `es`: pick "tú" or "usted" once.

### R7 — Punctuation per script
- Full-width punctuation `：（）` is correct **only in CJK locales** (zh-CN, zh-TW, ja, ko).
- Latin/Cyrillic/Hebrew locales must use ASCII `: ()` — full-width colons leaked in there
  are machine-translation artifacts. Known: `fr toast.recipes.createError/createFailed`,
  `es toast.recipes.createError/createFailed` (e.g. "…de la receta：" should be "…de la receta:").
- `fr` apostrophes must be U+2019 `'` / ASCII `'`, never a straight double quote:
  `fr header.filter.allowSellingGeneratedContentTooltip` currently reads
  `vendre d"images` → fix to `d'images`. Do not mix `'` and `'` in one file (fr has 299 vs 15).
- Ellipsis: use ASCII `...` (project style). Don't introduce `…`.
- Keep the sentence-ending period/omission consistent with the source string where the
  language allows it.
- `he` is RTL: mix of Hebrew and Latin scripts is normal; keep Latin term ordering natural.

### R8 — No untranslated English leftovers
Full sentences left byte-identical to `en.json` are bugs (brand names and URL placeholders
are the exception). Every locale has them; see §6 for the per-locale checklist.
`[TODO: Translate]` placeholders are the sanctioned intermediate state during feature
development (see §7) — do not "fix" them unless the feature owner asked for translations.

### R9 — Mirror the source even when the source is wrong
If `en.json` itself contains an inconsistency (e.g. the `Civitai` vs `CivitAI` casing split,
or the `CivitArchive` typo in `modals.relinkCivitai.helpText.format4`), translate/transcribe
it as-is in your locale and instead **fix the source** in `en.json` (then propagate by
re-syncing and re-translating affected keys). Do not silently diverge in one locale only.

---

## 2. Per-language term maps

Preferred rendering per term. "Fix" means the locale currently contains the wrong variant
and must be normalized. `en` = keep the English word as-is.

### fr

| Term | Use | Fix |
|---|---|---|
| recipe | Recipe(s) | Replace all "recette(s)" (58 keys, e.g. `recipes.actions.deleteRecipeWithShortcut`, `toast.recipes.rematchComplete`) with "Recipe(s)" |
| Checkpoint | Checkpoint | `statistics.modelTypes.checkpoint` = "Point de contrôle" → "Checkpoint" |
| trigger words | mot(s)-clé(s) | unify: `modals.model.triggerWords.editWord` uses "mot déclencheur" — pick one |
| prompt / negative prompt | Prompt / prompt négatif | — |
| base model | modèle(s) de base | — |
| preset | préréglage | unify: `modals.model.usageTips.addPresetParameter` "prédéfini", `toast.presets.restored` "par défaut" |
| hash | hash | `conflictConfirm.message` "hachage" → "hash" |
| tags | tags | `settings.sections.priorityTags` "Étiquettes" → "Tags" |
| metadata | métadonnées | `loras.controls.refresh.fullTooltip` keeps English "metadata" |
| duplicates | doublon(s) | unify with "dupliqué(e)s" |
| bulk | groupé(e) | unify with "par lot / mode lot" variants |

### de

| Term | Use | Fix |
|---|---|---|
| recipe | Rezept/Rezepte | 5 leftover English "Recipe" keys → Rezept (e.g. `globalContextMenu.repairRecipes.label`, `toast.recipes.recipeSaved`) |
| base model | pick Basis-Modell or Basismodell | currently 27× hyphenated vs 15× closed |
| metadata | Metadaten | 4 keys use "Modelldaten" (`onboarding.steps.fetch.title/content`) → Metadaten |
| bulk | pick Massen- or Sammelmodus | `loras.controls.bulk.action` = "Massen" reads as "crowds" — use "Massenbearbeitung"/"Mehrfachauswahl" |
| register | Sie (formal) | 7 keys use "du/dein" (`settings.backup.managementHelp`, `modals.checkUpdates.message/tip`, `doctor.footer`, …) |

### es

| Term | Use | Fix |
|---|---|---|
| recipe | receta(s) | — |
| Checkpoint | Checkpoint | 5 statistics keys "Punto(s) de control" → "Checkpoints" (`statistics.metrics.checkpoints`, `statistics.insights.unusedCheckpoints.*`, `statistics.modelTypes.checkpoint`) |
| trigger words | palabra(s) de activación | 2 keys already use it; ~15 keys "palabra(s) clave" (reads as search keyword) → unify |
| base model | modelo base | — |
| preset | preajuste | 3 keys keep English "preset", 1 "preestablecido" → preajuste |
| workflow | pick flujo de trabajo or workflow | currently 21× "flujo de trabajo" vs 10× "workflow" |
| bulk | masivo / por lotes | unify; "Batch Import" → traducción |
| tags | etiquetas | — |

### ru

| Term | Use | Fix |
|---|---|---|
| recipe | рецепт(ы) | English leftovers: `initialization.recipes.title`, `recipes.batchImport.*`, `toast.recipes.recipeSaved` → translate |
| Checkpoint | Checkpoint (recommended) | 3 variants today: "Checkpoint" (17 keys), «Чекпойнт», «Контрольная точка» (statistics, 6 keys) — statistics MUST drop «Контрольная точка» |
| Embedding | Embedding | «Эмбеддинг» variant exists in `settings.priorityTags.modelTypes.embedding` — unify |
| prompt | промпт | 8 keys use «запрос» (reads as "database/HTTP request") → «промпт» |
| base model | базовая модель | — |
| preset | пресет | `header.theme.presets` "Предустановки" → пресеты |
| workflow | Workflow (recommended) | «рабочий процесс» used in 4 keys — unify |
| hash | pick хеш or хэш | both spellings co-occur |
| tag(s) | тег(и) | — |
| typos | — | `settings.misc.loraSyntaxFormatHelp`: «безпотерьного» → «беспотерьного» |

### he

| Term | Use | Fix |
|---|---|---|
| recipe | מתכון / מתכונים | — |
| Checkpoint | Checkpoint | 5 statistics keys «נקודת/נקודות ביקורת» (road/security checkpoint) → "Checkpoint(s)" (`statistics.metrics.checkpoints`, `statistics.modelTypes.checkpoint`, `statistics.insights.unusedCheckpoints.*`) |
| Embedding | Embedding | `statistics` keys use הטמעות → Embedding |
| prompt | pick הנחיה or פרומפט | 9 keys הנחיה vs 3 פרומפט — unify (recommend פרומפט, SD-community loanword) |
| preset | קביעה מראש | `header.filter.presetOverwriteConfirm` uses פריסט → unify |
| hash | pick one of האש / גיבוב / hash | 3 variants co-occur — unify (recommend hash or גיבוב) |
| metadata | pick מטא-דאטה or מטא-נתונים | 38 vs 17 keys — unify |
| model | מודל | 13 keys use דגם/דגמים — unify |
| bulk | pick one of 5 variants | 5 different renderings ("כמות גדולה", "המוני", "קבוצתי", "אצווה", …) — unify; `loras.controls.bulk.action` "כמות גדולה" reads as "large quantity" |

### ja

| Term | Use | Fix |
|---|---|---|
| recipe | レシピ | `initialization.recipes.title` keeps English "Recipe Manager" — translate to レシピマネージャー |
| Checkpoint | Checkpoint or チェックポイント (pick one) | 3 variants: Checkpoint (~14), checkpoint lowercase (4), チェックポイント (4, e.g. `settings.priorityTags.modelTypes.checkpoint`) |
| Embedding | Embedding | 4 keys lowercase "embedding" mid-sentence |
| bulk | 一括 | `modals.checkUpdates.tip` "バルクモード" → 一括モード |
| recipe counter | 件 or 個 | `repairRecipes.success` uses 件, `.cancelled` uses 個 — unify |

### ko

| Term | Use | Fix |
|---|---|---|
| recipe | 레시피 | — |
| Checkpoint | Checkpoint (recommended) | 4 keys transliterate 체크포인트 (`settings.priorityTags.modelTypes.checkpoint`, `toast.recipes.missingCheckpointPath/missingCheckpointInfo/downloadCheckpointFailed`) |
| Embedding | Embedding | 3 keys 임베딩 (`settings.priorityTags.modelTypes.embedding`, `uiHelpers.nodeSelector.embedding`) |
| base model | 베이스 모델 | 6 keys «기본 모델» read as "default model" → 베이스 모델 (`settings.downloadSkipBaseModels.*`, `toast.loras.downloadSkippedByBaseModel`) |
| workflow | pick 워크플로 or 워크플로우 | 26 vs 6 keys — unify |
| bulk | 일괄 | `modals.checkUpdates.tip` "벌크 모드" → 일괄 모드 |
| tag logic | — | `header.filter.tagLogicAny` = "모든 태그 일치 (OR)" is **inverted** (should be "하나 이상의 태그 일치") and identical to `tagLogicAll` |
| particle | — | `modelCard.sendToWorkflow.checkpointNotImplemented`: "Checkpoint을" → "Checkpoint를" |

### zh-CN / zh-TW

| Term | zh-CN | zh-TW |
|---|---|---|
| recipe | 配方 (fix 食谱 → 配方, 14 keys in rematch flow) | 配方 (fix 食譜 → 配方, 17 keys in rematch flow) |
| Checkpoint | Checkpoint (fix 检查点 → Checkpoint, 5 keys: `toast.recipes.missingCheckpointPath/missingCheckpointInfo/downloadCheckpointFailed`, `modelCard.actions.checkpointNameCopied`, `modelCard.sendToWorkflow.checkpointNotImplemented`) | Checkpoint (fix 檢查點 → Checkpoint, 4 keys: `modelCard.actions.copyCheckpointName`, `toast.recipes.missing*`×2, `toast.recipes.downloadCheckpointFailed`) |
| base model | 基础模型 (fix 基模型 → 基础模型, 3 keys in `modals.model.versions.filters.*`) | 基礎模型 ✓ consistent |
| prompt | 提示词 ✓ | 提示詞 ✓ |
| preset | 预设 ✓ | 預設 ✓ |
| workflow | 工作流 ✓ | 工作流 ✓ |
| trigger words | 触发词 ✓ | 觸發詞 ✓ |
| hash | 哈希 (哈希值 variant OK) | 雜湊 ✓ |
| register | 你 (fix 5×您 → 你) | 您 (fix 18×你 → 您) |

---

## 3. Cross-cutting confusion hot-spots (must-fix list)

All items below were **resolved** in the 2026-08 sweep — treat them as a regression
watch-list: do not reintroduce these renderings.

1. **Checkpoint rendered as a literal security/road checkpoint** — fr, es, ru, he, zh-CN,
   zh-TW all had 4–6 keys in the `statistics.*` domain reading as "control point"; reverted
   to "Checkpoint".
2. **"recipe" variants that break the one-noun rule** — fr "recette" → "Recipe", zh
   食谱/食譜 → 配方, de/ja/ru leftover English "Recipe" translated.
3. **ko `header.filter.tagLogicAny`** — was inverted ("모든 태그 일치 (OR)") and identical
   to `tagLogicAll`; now "어느 하나의 태그와 일치 (OR)".
4. **ja `modals.model.versions.actions.viewLocalTooltip`** — was the stale "近日対応予定"
   ("coming soon"); all 9 locales now describe the actual action.
5. **Stale help texts** — `settings.downloadSkipBaseModels.help`,
   `settings.aiProvider.apiBaseHelp`, `settings.hideEarlyAccessUpdates.help` retranslated
   in all locales to the current `en.json` wording.
6. **en.json source bugs** (fixed in source, then mirrored):
   - "Civitai" → "CivitAI" brand casing (values only; key names `relinkCivitai` etc. keep
     their lowercase form and must not be renamed)
   - `modals.relinkCivitai.helpText.format4` "CivitArchive" typo → "CivArchive"
   - `zh-CN recipes.controls.import.downloadLocationPreview` invented `{path}` removed

---

## 4. Placeholder contract deviations (current)

`{...}` token sets must match `en.json` per key. All deviations found in the 2026-08 sweep
were fixed, with one *intentional* exception:

**`toast.settings.mappingsUpdated`** — the caller passes a hardcoded English inflection
(`plural: count !== 1 ? 's' : ''`). Languages that cannot build a plural by appending that
`s` (zh-CN/zh-TW, ja, ko, de, ru, he) **drop `{plural}`** and render a count-friendly form
(`({count})` or a measure word); fr and es keep it (`mappage{plural}`, `mapeo{plural}`).

```python
# keep a copy of this rule next to the key if it ever moves:
#   fr/es:  "... ({count} mappage{plural})"
#   de/ru/he: "... ({count})"
#   zh-CN: "（{count} 条映射）" / zh-TW: "（{count} 個對應）" / ja: "（{count} マッピング）"
```

Do NOT add `{...}` tokens the source lacks (the caller will not supply them, and the literal
text renders in the UI), and do NOT rename source tokens (`{typePlural}` stays `{typePlural}`).

---

## 5. One term, one rendering — offender matrix

Cross-locale summary of §2 inconsistencies. "✓" = already consistent. All ✗ cells were
resolved in the 2026-08 sweep; the row shows the single rendering now in force per locale.

| Term | fr | de | es | ru | he | ja | ko | zh-CN | zh-TW |
|---|---|---|---|---|---|---|---|---|---|
| recipe | Recipe | Rezept | receta | рецепт | מתכון | レシピ | 레시피 | 配方 | 配方 |
| Checkpoint | Checkpoint | Checkpoint | Checkpoint | Checkpoint | Checkpoint | Checkpoint | Checkpoint | Checkpoint | Checkpoint |
| Embedding | Embedding | Embedding | Embedding | Embedding | Embedding | Embedding | Embedding | Embedding | Embedding |
| prompt | Prompt | Prompt | prompt | промпт | פרומפט | プロンプト | 프롬프트 | 提示词 | 提示詞 |
| base model | modèle de base | Basismodell | modelo base | базовая модель | מודל בסיס | ベースモデル | 베이스 모델 | 基础模型 | 基礎模型 |
| preset | préréglage | Voreinstellung | preajuste | пресет | קביעה מראש | プリセット | 프리셋 | 预设 | 預設 |
| workflow | Workflow | Workflow | workflow | Workflow | workflow | ワークフロー | 워크플로 | 工作流 | 工作流 |
| hash | hash | Hash | hash | хеш | hash | ハッシュ | 해시 | 哈希 | 雜湊 |
| metadata | métadonnées | Metadaten | metadatos | метаданные | מטא-נתונים | メタデータ | 메타데이터 | 元数据 | 中繼資料 |
| tags | Tags | Tags | etiquetas | теги | תגיות | タグ | 태그 | 标签 | 標籤 |
| duplicates | en double | Duplikate | duplicados | дубликаты | כפילויות | 重複 | 중복 | 重复项 | 重複項 |
| bulk | groupé | Massen- | por lotes | пакетный | בכמות גדולה | 一括 | 일괄 | 批量 | 批量 |

Watch: ja/ko keep the model-type names **Checkpoint/Embedding** and `Diffusion Model` in
Latin (consistent with their model-type sections) — do not transliterate them as
チェックポイント/체크포인트.

---

## 6. Untranslated English leftovers (status)

Values byte-identical to `en.json` that are actual UI sentences are bugs (brand names and
URL placeholders are the exception). As of the 2026-08 sweep, **all previously untranslated
blocks are translated** in every locale: `recipes.batchImport.*` + `toast.recipes.batchImport*`
(fr/de/es/ru/he/ja/ko), `banners.communitySupport.*`, `modals.model.license.*`,
`globalContextMenu.fetchMissingLicenses.*`, the `doctor.*` issue/action/label subset,
`toast.settings.libraryLoadFailed` / `libraryActivateFailed`, `toast.api.moveFailed`,
`settings.extraFolderPaths.restartRequired`, `toast.recipes.recipeSaved`,
`sidebar.dragDrop.moveUnsupported`, `checkpoints.modelTypes.diffusion_model`
(ja/ko keep the English loanword), `initialization.recipes.title`.

The only values that remain intentionally identical to `en.json` are non-translatable:
URL/path placeholders (`https://…`, `C:/…`), numeric presets (`5 (1080p), 6 (2K), 8 (4K)`),
example token lists (`character, concept, style(toon|toon_style)`), service/provider names
(`CivitAI → CivArchive → Archive DB`), and the external playlist title
(`help.updateVlogs.playlistTitle`, de: translated to "LoRA Manager-Update-Playlist").

Rule for `uiHelpers.workflow.noPromptTargets`: the second line (`Mark as → Send Prompt
Target`) quotes literal ComfyUI context-menu items — keep those menu labels in English in
every locale because that is what the user actually sees in ComfyUI.

License labels (`modals.model.license.*`): the restriction labels are now translated in all
locales (the sibling `creditRequired` has always been translated).

---

## 7. Workflow for agents and translators

### Adding a new UI string
1. Add the key to `locales/en.json` only.
2. Run `python scripts/sync_translation_keys.py` — it inserts the key into the other 9
   locales (as a `[TODO: Translate]` placeholder) preserving formatting.
3. **During feature development, stop here.** While the UI copy is still in flux, leave the
   `[TODO: Translate]` placeholders as-is — translating churning strings into 9 locales is
   wasted work. Placeholders are a normal intermediate state, not a bug.
4. Once the wording is final and the feature owner explicitly asks for translations,
   translate **all** pending `[TODO: Translate]` keys in every locale (not just the latest
   feature's), applying §1–§3 (placeholders verbatim, Recipe rule, term maps, register).
   Find pending keys with: `grep -c "TODO: Translate" locales/*.json`
5. If the new string contains new terminology, extend §2 tables.

### Fixing a translation bug
1. Locate the key (dotted path) in the relevant locale file.
2. Check the corresponding `en.json` value and the actual caller (grep `static/js` or
   `web/comfyui` for the key) to learn which placeholders are passed.
3. Fix trivially; for normalization sweeps (e.g. "recette" → "Recipe"), do it file-wide for
   the offending keys only — do not touch unrelated lines.
4. If the bug is in `en.json` itself (R9), fix the source first, then re-sync and update all
   locales.

### Verification
```bash
pytest tests/i18n/test_i18n.py     # key parity + JSON validity + JS key references
python scripts/sync_translation_keys.py --dry-run   # shows which keys would change; add --verbose for per-key detail
npm test                           # frontend tests incl. i18n helpers
```

`pytest tests/i18n` only checks structure. Quality conventions in this document are not
machine-enforced — a human/agent review pass is required.

### Anti-patterns checklist
- [ ] Placeholders `{x}` / `{{x}}` differ from `en.json`
- [ ] Same source term translated 2+ ways in the same file (see §5)
- [ ] "Checkpoint" became a literal checkpoint; "recipe" became menu/prescription/food-cookbook
- [ ] Brand names translated or transliterated (LoRA, CivitAI, ComfyUI, …)
- [ ] Latin locale using full-width `：（）`; fr using `"` as apostrophe
- [ ] Mixed 你/您, du/Sie, tú/usted
- [ ] Full English sentences left behind (see §6)
- [ ] Register/typos/mojibake; source string is stale vs `en.json` (compare semantics, not
  just words)