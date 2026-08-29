# i18n Translation Guidelines

This document is the canonical set of conventions for translating LoRA Manager UI strings.
It applies to **human translators and AI agents** alike. Read it before editing anything in
`locales/`.

Source of truth: `locales/en.json` (10 locales, 1810 leaf keys; all locales share the exact
same key structure).

Locales: `en`, `zh-CN`, `zh-TW`, `ja`, `ko`, `fr`, `de`, `es`, `ru`, `he` (RTL).

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

Ordered by impact. Key paths refer to the current broken values documented in §2.

1. **Checkpoint rendered as a literal security/road checkpoint** — fr, es, ru, he, zh-CN,
   zh-TW all have 4–6 keys in the `statistics.*` domain that must revert to "Checkpoint".
   This is the single most misleading pattern in the codebase.
2. **"recipe" variants that break the one-noun rule** — fr "recette" (keep Recipe), zh
   食谱/食譜 (use 配方), de/ja/ru leftover English "Recipe".
3. **ko `header.filter.tagLogicAny`** — inverted semantics + identical to `tagLogicAll`.
4. **ja `modals.model.versions.actions.viewLocalTooltip`** = "近日対応予定" ("coming soon") —
   stale string from an old version of the key; the button actually shows local versions.
5. **Stale help texts that no longer describe the current `en.json` source** (the
   en string changed, the translation is from an older wording):
   - `settings.downloadSkipBaseModels.help` — es/ko/ja/ru describe "applies to all download
     flows / only supported base models can be selected", source says "versions using the
     selected base models will be skipped"
   - `settings.aiProvider.providerHelp` / `apiBaseHelp` — ru/es/fr hard-code provider names
     or invent "leave empty" instructions not in source
   - `settings.hideEarlyAccessUpdates.help` — fr/ja are truncated fragments of the current
     source sentence
6. **en.json source bugs** (fix in `en.json` first, then re-sync + retranslate):
   - "Civitai" (50×) vs "CivitAI" (11×) casing split — pick the official "CivitAI" and propagate
   - `modals.relinkCivitai.helpText.format4` — "CivitArchive" typo → "CivArchive"
   - `zh-CN recipes.controls.import.downloadLocationPreview` — remove the invented `{path}`

---

## 4. Placeholder contract deviations (current)

`{...}` token sets differ from `en.json` in these keys (callers pass the full param set, so
they render today, but they violate the contract and would break if the caller changes):

| Locale | Key | Deviation |
|---|---|---|
| zh-CN | `modals.checkUpdates.title`, `.message` | `{typePlural}` → `{type}` — restore `{typePlural}` |
| zh-TW | `modals.checkUpdates.title`, `.message` | same |
| ja | `modals.checkUpdates.title`, `.message` | same |
| ko | `modals.checkUpdates.title`, `.message` | same |
| zh-CN | `recipes.controls.import.downloadLocationPreview` | **adds** `{path}` the source lacks (renders literally) — remove |
| zh-TW | `toast.settings.mappingsUpdated` | drops `{plural}` (`({count} 個對應)`) — acceptable (no plural morphology) but keep source token if possible |
| zh-TW | `toast.controls.refreshFailed` | drops `{action}` — restore |
| ko | `toast.settings.mappingsUpdated` | drops `{plural}` — acceptable in Korean, keep if possible |

---

## 5. One term, one rendering — offender matrix

Cross-locale summary of §2 inconsistencies. "✓" = already consistent.

| Term | fr | de | es | ru | he | ja | ko | zh-CN | zh-TW |
|---|---|---|---|---|---|---|---|---|---|
| recipe | ✗ Recipe/recette | ✗ Rezept/Recipe | ✓ receta | ✗ рецепт/Recipe | ✓ מתכון | ✗ レシピ/Recipe | ✓ 레시피 | ✗ 配方/食谱 | ✗ 配方/食譜 |
| Checkpoint | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Embedding | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ |
| prompt | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ | ✓ | ✓ | ✓ |
| base model | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ |
| preset | ✗ | ✓ | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ | ✓ |
| workflow | ✓ | ✓ | ✗ | ✗ | ✓ | ✓ | ✗ | ✓ | ✓ |
| hash | ✗ | ✓ | ✓ | ✗ | ✗ | ✓ | ✓ | ✓ | ✓ |
| metadata | ✗ | ✗ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ |
| tags | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| duplicates | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| bulk | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ | ✓ | ✓ |

---

## 6. Untranslated English leftovers (per locale)

Values byte-identical to `en.json` that are actual UI sentences (brand names and URL
placeholders are excluded). Translate them.

| Feature area | fr | de | es | ru | he | ja | ko | zh-CN | zh-TW |
|---|---|---|---|---|---|---|---|---|---|
| `recipes.batchImport.*` (whole modal, ~25–56 keys) | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ |
| `toast.recipes.batchImport*` (7 keys) | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ |
| `globalContextMenu.fetchMissingLicenses.*` (5 keys) | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ |
| `banners.communitySupport.*` (4 keys incl. long prose) | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ |
| `modals.model.license.noImageSell/noRentCivit/noRent/noSell` | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `doctor.*` (subset: issues/actions/labels) | ✗ | ✗ | ✗ | ✗ | ✗ | — | — | — | — |
| `toast.recipes.recipeSaved` | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | — | — |
| `toast.settings.libraryLoadFailed / libraryActivateFailed` | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `toast.api.moveFailed` | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `settings.extraFolderPaths.restartRequired` | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `checkpoints.modelTypes.diffusion_model` | — | ✗ | — | ✗ | — | ✗ | ✗ | — | — |
| `sidebar.dragDrop.moveUnsupported` | — | — | — | — | — | — | — | ✗ | ✗ |
| `initialization.recipes.title` (English "Recipe Manager") | — | — | — | ✗ | — | ✗ | — | — | — |
| `uiHelpers.workflow.noPromptTargets` menu path line | — | — | ✗ | ✗ | — | — | — | ✗ | — |

Legend: ✗ = untranslated (needs work), ✓ = translated and consistent, — = not flagged in
the audit (assume translated; verify).

Note on the license labels (`modals.model.license.*`): if they are intentionally kept in
English (CivitAI license boilerplate), make that decision explicit for all locales instead of
leaving it inconsistent — `zh-CN` already translates the sibling `creditRequired`.

---

## 7. Workflow for agents and translators

### Adding a new UI string
1. Add the key to `locales/en.json` only.
2. Run `python scripts/sync_translation_keys.py` — it inserts the key into the other 9
   locales (as an English placeholder) preserving formatting.
3. Translate the new key in every locale, applying §1–§3 (placeholders verbatim, Recipe
   rule, term maps, register).
4. If the new string contains new terminology, extend §2 tables.

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