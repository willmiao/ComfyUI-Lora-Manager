# i18n Translation Guidelines

This document is the canonical set of conventions for translating LoRA Manager UI strings.
It applies to **human translators and AI agents** alike. Read it before editing anything in
`locales/`.

Source of truth: `locales/en.json` (10 locales, 2105 leaf keys; all locales share the exact
same key structure).

Locales: `en`, `zh-CN`, `zh-TW`, `ja`, `ko`, `fr`, `de`, `es`, `ru`, `he` (RTL).

> **Status (2026-08 sweep):** a full audit was executed and the terminology, placeholder,
> stale-text, and untranslated-block fixes described in §2–§6 were applied across all locales
> (commits `3c3ac49f` … `fd1227d3`). The tables below are now the **normative target state**,
> not a to-do list — future edits should preserve these renderings and only add what is new.
>
> **Status (2026-09, Other Models):** the `other` model type (VAE / Upscaler / Text Encoder /
> CLIP Vision / ControlNet) and the Other Models opt-in toggles added 36 new keys; all of them
> are now translated in all 9 locales (terminology in §2 "Other Models feature"). There are no
> remaining `[TODO: Translate]` placeholders in any locale.
>
> **Status (2026-09, revision):** `other.disabled.description`, `banners.otherModels.content` and
> `settings.folderSettings.enableOtherModelsHelp` were refreshed in `en.json` to name all five
> sub_types (they had listed four, which read as "these are what enabling manages") and
> re-translated in all 9 locales in the same pass. `clip_vision` and `controlnet` are now both
> opt-in, so the first two describe **capability** and the third the **master switch**, not the
> default set — keep all three enumerating the full five (`VAE / upscaler / text encoder /
> CLIP vision / ControlNet` in `en`; locale slash-list casing follows each file's existing
> `VAE / Upscaler / Text Encoder / …` style, de compounds as `CLIP-Vision- und ControlNet-Ordner`).
>
> **Status (2026-09, "no folders found" state):** the Other Models page gained an *enabled but
> nothing to scan* empty state with 6 new keys (`other.noPaths.*`); translated in all 9 locales
> in the same pass. The `folder_paths` JSON snippet shown in that state lives in
> `templates/other.html`, **not** in the locale files, so it is never translated — only the
> surrounding prose is. Terminology added in §2.
>
> **Status (2026-09, model sources):** models can now be linked to ModelScope and TensorArt
> alongside Hugging Face, which added 15 keys (`modelCard.actions.viewOnSource`,
> `loras.contextMenu.linkModelSource`, `modals.linkModelSource.*`,
> `modals.model.versions.sourceGroupInfo`, `toast.contextMenu.enrichNeedsSource`,
> `toast.contextMenu.enrichUnsupportedSource`) and refreshed the two `enrichHfAgent` labels,
> which had hardcoded "HF" for a button that now also enriches ModelScope models. The
> `modals.linkModelSource.urlPlaceholder` value stays byte-identical to `en.json` (it is a URL,
> the §6 exception). Terminology in §2, "Model source feature".
>
> **Status (2026-09, folder sidebar):** the model-root sidebar gained on-disk folder management
> (create / rename / delete folders, show empty folders, tree vs list view) plus its `...`
> view-options menu, adding 35 `sidebar.*` keys. Those were the only `[TODO: Translate]`
> placeholders left behind by the feature series, and all 35 are now translated in all 9
> locales, so the "no remaining placeholders" claim above holds again. Terminology in §2,
> "Folder sidebar feature".
>
> **Status (2026-09, chip reordering):** model tags and trigger words now share one drag/`⠿`
> grip reorder affordance, which added the single `common.reorder.dragHandle` key (it lives
> under `common` because both editors render it). All 9 locales are translated (renderings in
> §2, "Chip reordering"). Reordering is pointer-only by design: an `Alt + Arrow` shortcut was
> prototyped and removed because it collided with the browser's Alt + Arrow handling and the
> modal's arrow-key navigation.

> **Status (2026-09, standalone no-paths guidance):** the standalone branch of the
> `other.noPaths` empty state now shows the real `settings.json` path plus an
> `other.noPaths.openSettingsFolder` button (each locale reuses its
> `settings.openSettingsFileLocation.label` rendering), and `descriptionStandalone` was
> reworded in `en.json` — from "none of the configured folders exist on disk" to "no
> other-model folders were found; add the folder keys you need to the `folder_paths`
> section" — and re-translated in all 9 locales. The `on disk` phrase now survives only in
> the ComfyUI variant (`descriptionComfyUI`).

> **Status (2026-09, settings Organization tab):** the settings modal split its overloaded
> Library tab, adding the single `settings.nav.organization` key (renderings in §2,
> "Settings Organization tab"). All 9 locales are translated, so the "no remaining
> placeholders" claim holds again.

> **Status (2026-09, filename templates):** the Filename Templates feature (per-model-type
> download filename templates + bulk "Apply to Library Now" rename, with an empty template
> restoring recorded original filenames) added 26 keys across `settings.filenameTemplates.*`,
> `loras.bulkOperations.filenameTemplateProgress.*`, `modals.filenameTemplateConfirm.*` and
> the `toast.loras.filenameTemplate*` / `toast.settings.filenameTemplates*` toasts. All 9
> locales are translated (terminology in §2, "Filename Templates feature").

> **Status (2026-09, folder delete verification):** the folder delete modal no longer trusts the
> sidebar's "empty folder" prediction — it dry-runs the delete against the backend and renders
> the answer, so a folder whose models are all *excluded* (invisible to the model lists, still
> real weight files on disk) is refused with an explanation instead of contradicting itself.
> That added 5 keys (`sidebar.deleteFolderModal.notEmptyMessageCount`,
> `.notEmptyMessageExcluded`, `.busyTitle`, `.checking`, `sidebar.deleteFolderResult.notEmptyWithCount`);
> all 9 locales are translated (terminology in §2, "Folder sidebar feature"), so the
> "no remaining placeholders" claim holds again.

---

## 1. Hard rules (do not violate)

### R1 — Key structure is sacred
- Only `locales/en.json` may add/remove/rename keys. All other locales must keep the exact
  same nested key set. `tests/i18n/test_i18n.py` enforces this.
- When a new UI string is added to `en.json`, run
  `python scripts/sync_translation_keys.py` (adds the missing keys to all locales with
  `[TODO: Translate]` placeholder copies) — **then stop**. Do NOT translate proactively:
  placeholders are the expected end state during feature development, and translations are
  filled in only when the feature owner explicitly asks (workflow details in §7).
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
| recipe | Rezept/Rezepte | leftover English "Recipe" keys → Rezept (e.g. `toast.recipes.recipeSaved`) |
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
| recipe counter | 件 or 個 | `globalContextMenu.rematchRecipes.success` uses 件, `.cancelled` uses 個 — unify |

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

### Other Models feature (VAE / Upscaler / Text Encoder / CLIP Vision / ControlNet)

The `other` model type exposes five sub_types. They are **model-type names**, so they follow
R3 and stay in Latin in every locale. The `settings.folderSettings.subType*` values are
therefore **intentionally byte-identical to `en.json`** (same precedent as
`settings.priorityTags.modelTypes` / `checkpoints.modelTypes.checkpoint`) — a §6 sweep must
not "fix" them.

| Term | Rendering | Note |
|---|---|---|
| VAE | `VAE` everywhere | acronym, always upper-case |
| Upscaler | `Upscaler` everywhere | CivitAI `ModelType` name |
| Text Encoder | `Text Encoder` everywhere | de compounds as `Text-Encoder-Stammordner` |
| CLIP Vision | `CLIP Vision` everywhere | de compounds as `CLIP-Vision-Stammordner` |
| ControlNet | `ControlNet` everywhere | brand casing, capital N |

In prose these names sit next to localized nouns the same way `Diffusion Model` does
(zh `VAE 根目录`, ja `VAEルート`, ko `VAE 루트`, ru `Корневая папка VAE`).

**"Other Models" is the page/feature name, not a model type — translate it:**

| Locale | `other.title` | `header.navigation.other` |
|---|---|---|
| fr | Autres modèles | Autres |
| zh-CN | 其他模型 | 其他 |
| zh-TW | 其他模型 | 其他 |
| ja | その他のモデル | その他 |
| ko | 기타 모델 | 기타 |
| de | Weitere Modelle | Andere |
| es | Otros modelos | Otros |
| ru | Другие модели | Другое |
| he | מודלים אחרים | אחרים |

`settings.folderSettings.otherSubTypes` ("Managed Types") must name **model** types, matching
each locale's `header.filter.modelTypes` rendering (zh `管理的模型类型`, ja `管理するモデルタイプ`,
de `Verwaltete Modelltypen`, …).

The "no folders found" empty state (`other.noPaths.*`) uses two phrases that must stay
consistent whenever that copy is edited. `folder key` means the `folder_paths` key name
(`vae`, `upscale_models`, … — Latin per the table above); `on disk` means the folder must
physically exist:

| Phrase | Rendering |
|---|---|
| folder key | zh-CN 文件夹键 · zh-TW 資料夾鍵 · ja フォルダーキー · ko 폴더 키 · fr clé de dossier · de Ordnerschlüssel · es clave de carpeta · ru ключ папки · he מפתח תיקייה |
| on disk | zh-CN 在磁盘上 · zh-TW 在磁碟上 · ja ディスク上 · ko 디스크에 · fr sur le disque · de auf dem Datenträger · es en el disco · ru на диске · he בדיסק |

`settings.json` and `ComfyUI` stay verbatim in every locale; "reload this page" / "restart
LoRA Manager" reuse each locale's existing restart wording (`settings.extraFolderPaths.*`).

### Model source feature (Hugging Face / ModelScope / TensorArt)

A model file can be linked to the page of an external model site. **Hugging Face**,
**ModelScope** and **TensorArt** are brand names and stay Latin in every locale (R3); the
generic nouns around them are translated:

| Term | Rendering |
|---|---|
| model source | zh-CN 模型来源 · zh-TW 模型來源 · ja モデルソース · ko 모델 소스 · fr source de modèle · de Modellquelle · es fuente de modelo · ru источник модели · he מקור מודל |
| model page | zh-CN 模型页面 · zh-TW 模型頁面 · ja モデルページ · ko 모델 페이지 · fr page du modèle · de Modellseite · es página del modelo · ru страница модели · he עמוד המודל |
| model card | zh-CN 模型卡 · zh-TW 模型卡 · ja モデルカード · ko 모델 카드 · fr fiche de modèle · de Modellkarte · es ficha de modelo · ru карточка модели · he כרטיס מודל |
| AI enrichment (noun) | reuse the existing pair per locale: zh-CN 增强 · zh-TW 增強 · ja 補完 · ko 보강 · fr enrichissement (par IA) · de Anreicherung (KI-) · es enriquecimiento (con IA) · ru обогащение (с помощью ИИ) · he העשרה (AI) |

`modelCard.actions.viewOnSource` ("View on {source}") follows each locale's existing
`viewOnHuggingFace` pattern — de `Auf … ansehen`, ru `Открыть …`, he `צפייה ב-…`,
ja `… で見る`, ko `…에서 보기`, zh `在 … 查看`, fr `Voir sur …`, es `Ver en …`. `{source}` is
replaced at runtime with the untranslated platform name, so the brand never appears inside the
translated text.

`modals.linkModelSource.enrichNote` states the rule that only sites exposing a readable model
card can be enriched and names TensorArt as the current exception. Keep the parenthetical
exception in sync if another link-only source is ever added — the sentence is deliberately
phrased as a rule, not as an apology for one site.

The context-menu and bulk-operation enrichment entry points read **"Enrich Metadata with AI"**
in `en`, not "Enrich HF Metadata": they cover ModelScope as well, so no locale may reintroduce
an `HF` qualifier in `loras.contextMenu.enrichHfAgent` / `loras.bulkOperations.enrichHfAgent`
(the key names keep the historical `Hf`; only the values changed).

The gated/private-repository download support added `settings.huggingfaceApiKey*` (label,
placeholder, help, and the three status strings). "Access token" renderings, and the status
strings reuse each locale's existing `civitaiApiKey*` forms ("Configured" / "Not configured" /
"Set up") verbatim:

| Term | Rendering |
|---|---|
| access token | zh-CN 访问令牌 · zh-TW 存取權杖 · ja アクセストークン · ko 액세스 토큰 · fr jeton d'accès · de Access Token (Latin, like `CivitAI API Key`) · es token de acceso · ru токен доступа · he אסימון גישה |
| gated repository | zh-CN 受限（gated）仓库 · zh-TW 受限（gated）倉庫 · ja ゲート付きリポジトリ · ko 게이트가 설정된 저장소 · fr dépôt restreint (gated) · de gated Repository (loanword) · es repositorio restringido (gated) · ru закрытый (gated) репозиторий · he מאגר מוגבל (gated) |

The help text tells the user to create a **read-only** token at
`huggingface.co/settings/tokens` and to accept the repository's terms on its page first —
keep both clauses: a token alone does not unlock a gated repository.

### Folder sidebar feature (create / rename / delete folders, empty folders, view options)

The model-root sidebar manages on-disk folders. "Folder" reuses the noun already fixed in §2
(the `folder key` row); the rest is new surface:

| Term | Rendering |
|---|---|
| folder | zh-CN 文件夹 · zh-TW 資料夾 · ja フォルダ · ko 폴더 · fr dossier · de Ordner · es carpeta · ru папка · he תיקייה |
| model root (as in "no model root is configured") | zh-CN 模型根目录 · zh-TW 模型根目錄 · ja モデルルート · ko 모델 루트 · fr racine de modèle · de Modell-Stammverzeichnis · es raíz de modelo · ru корневая папка моделей · he שורש מודלים — note `sidebar.modelRoot` alone is the shorter 根目录 / 根目錄 / ルート / 루트 / Racine / Stammverzeichnis / Raíz / Корень / שורש |
| tree view / list view | zh-CN 树形视图 / 列表视图 · zh-TW 樹狀檢視 / 清單檢視 · ja ツリー表示 / リスト表示 · ko 트리 보기 / 목록 보기 · fr Vue arborescente / Vue liste · de Baumansicht / Listenansicht · es Vista de árbol / Vista de lista · ru Дерево / Список · he תצוגת עץ / תצוגת רשימה |
| sidebar | reuse each locale's `sidebar.hideOnThisPage` noun: zh-CN 侧边栏 · zh-TW 側邊欄 · ja サイドバー · ko 사이드바 · fr barre latérale · de Seitenleiste · es barra lateral · ru боковая панель · he סרגל צד |

Deleting a folder **never cascades over model files** — the backend refuses it and the
`sidebar.deleteFolderModal.notEmptyMessage*` keys state the rule in every locale, so keep that
clause (and its `—`) when the copy is edited. The three variants split by what the modal knows:
`notEmptyMessage` (no counts), `notEmptyMessageCount` (`{count}`, the blocking models are all
listed) and `notEmptyMessageExcluded` (`{count}` + `{excluded}`, at least one is hidden by the
`exclude` flag — the case where the folder legitimately looks empty). `checking` ("Checking the
folder contents...", ASCII ellipsis) shows while the backend dry run is pending, `busyTitle`
titles the already-pending-staged-delete state, and `notEmptyWithCount` mirrors
`deleteFolderResult.notEmpty` with the count for the stale-tree toast.

| Term | Rendering |
|---|---|
| excluded from the library | zh-CN 已从模型库中排除 · zh-TW 已從模型庫中排除 · ja ライブラリから除外 · ko 라이브러리에서 제외 · fr exclu de la bibliothèque · de von der Bibliothek ausgeschlossen · es excluido de la biblioteca · ru исключены из библиотеки · he מוחרגים מהספרייה |
| un-exclude (verb) | zh-CN 取消排除 · zh-TW 取消排除 · ja 除外を解除 · ko 제외를 해제 · fr annuler l'exclusion · de den Ausschluss aufheben · es anular la exclusión · ru снять исключение · he לבטל את ההחרגה |
| "Manage Excluded Models" quoted in prose | zh-CN “管理已排除的模型” · zh-TW 「管理已排除的模型」 · ja 「除外モデルを管理」 · ko '제외된 모델 관리' · fr « Gérer les modèles exclus » · de „Ausgeschlossene Modelle verwalten“ · es «Gestionar modelos excluidos» · ru «Управление исключёнными моделями» · he «ניהול מודלים מוחרגים» |

A UI label quoted inside prose follows each locale's existing help-text style (zh-CN “ ”,
zh-TW/ja 「 」, ko ASCII `' '`, fr/ru/es/he « », de „ “) — see `settings.hideEarlyAccessUpdates.help`
/ `settings.civitaiHost.help` as the precedent. `קובצי מודלים` is the Hebrew model-file noun
(`notEmptyMessage`); keep it identical in all four Hebrew keys.

The `{name}` / `{count}` / `{excluded}` / `{message}` tokens in `sidebar.createFolderResult.*`,
`sidebar.deleteFolderResult.*` and `sidebar.renameFolderResult.*` are verbatim §1-R2
placeholders. The keys carrying `{count}` are `successWithFiles`, `notEmptyMessageCount`,
`notEmptyMessageExcluded` and `notEmptyWithCount`; `notEmptyMessageExcluded` is the only key
carrying `{excluded}`.

### Settings Organization tab

The settings modal's fourth nav tab groups everything about how files are arranged on
disk: download path templates, priority tags, and auto-organize exclusions. The label is
the **noun for arranging files**, matching each locale's existing
`settings.sections.autoOrganize` rendering minus the "auto":

| Locale | `settings.nav.organization` |
|---|---|
| fr | Organisation |
| zh-CN | 整理 |
| zh-TW | 整理 |
| ja | 整理 |
| ko | 정리 |
| de | Organisation |
| es | Organización |
| ru | Организация |
| he | ארגון |

zh-CN/zh-TW use 整理 ("tidying/arranging"), not 组织/組織 (an organization as a group).

### Filename Templates feature

Per-model-type templates that name downloaded model files; "Apply to Library Now"
bulk-renames existing files, and an **empty template restores the recorded original
filenames** (recorded in each model's metadata at its first rename). "Template" follows
each locale's existing download-path-template noun (zh-CN 模板 vs zh-TW 範本 — note the
split); progress strings mirror `loras.bulkOperations.autoOrganizeProgress` verbatim with
the locale's "moved" verb swapped for its "renamed" verb, and the toasts mirror the
`autoOrganize*` / `downloadTemplates*` toast shapes.

| Term | Rendering |
|---|---|
| filename template(s) | zh-CN 文件名模板 · zh-TW 檔案名稱範本 · ja ファイル名テンプレート · ko 파일명 템플릿 · fr modèle(s) de nom de fichier · de Dateinamen-Vorlage(n) · es plantilla(s) de nombres de archivo · ru шаблон(ы) имён файлов · he תבנית שם קובץ / תבניות שמות קבצים |
| Apply to Library Now (button) | zh-CN 立即应用到库 · zh-TW 立即套用至模型庫 · ja ライブラリに今すぐ適用 · ko 지금 라이브러리에 적용 · fr Appliquer à la bibliothèque maintenant · de Jetzt auf Bibliothek anwenden · es Aplicar a la biblioteca ahora · ru Применить к библиотеке сейчас · he החל על הספרייה כעת |
| Restore original filenames (modal title / button) | zh-CN 恢复原始文件名？/ 恢复原始文件名 · zh-TW 要還原原始檔案名稱嗎？/ 還原原始檔案名稱 · ja 元のファイル名を復元しますか？/ 元のファイル名を復元 · ko 원본 파일명을 복원하시겠습니까? / 원본 파일명 복원 · fr Restaurer les noms de fichier d'origine ? / Restaurer les noms de fichier d'origine · de Ursprüngliche Dateinamen wiederherstellen? / Ursprüngliche Dateinamen wiederherstellen · es ¿Restaurar los nombres de archivo originales? / Restaurar nombres de archivo originales · ru Восстановить исходные имена файлов? / Восстановить исходные имена файлов · he לשחזר שמות קבצים מקוריים? / שחזר שמות קבצים מקוריים |
| "renamed" (progress/toast counter) | zh-CN 已重命名 · zh-TW 已重新命名 · ja リネーム · ko 이름 변경 · fr renommés · de umbenannt · es renombrados · ru переименовано · he שונו שמותם |

### Chip reordering (model tags / trigger words)

Model tags and trigger-word chips share a single reorder affordance (drag the chip, or its
`⠿` grip where the chip body is click-to-edit), so the copy sits in `common.reorder.dragHandle`
instead of a feature namespace. It is used twice per editor: as the grip tooltip and as the
hint shown in the edit controls row. There is deliberately **no keyboard shortcut** — an
`Alt + Arrow` binding fought the browser's own Alt + Arrow handling and the modal's arrow-key
navigation, so reordering is pointer-only and the grip is a decorative, non-focusable
affordance. Do not reintroduce a shortcut or a "position X of Y" screen-reader string without
re-adding the corresponding keys.

`dragHandle` is a fragment, not a sentence: it labels both the grip and the hint, so keep it
short and imperative and do not append a keyboard hint in any locale.

| Term | Rendering |
|---|---|
| drag to reorder | zh-CN 拖拽以调整顺序 · zh-TW 拖曳以調整順序 · ja ドラッグして並べ替え · ko 드래그하여 순서 변경 · fr Glisser pour réordonner · de Zum Neuordnen ziehen · es Arrastra para reordenar · ru Перетащите, чтобы изменить порядок · he גרור כדי לשנות סדר |

The grip itself is an icon and is never translated.

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
(`CivitAI → CivArchive → Archive DB`), model-type names (`settings.priorityTags.modelTypes.*`,
`settings.folderSettings.subTypeVae` … `subTypeControlnet` — see §2), and the external playlist
title (`help.updateVlogs.playlistTitle`, de: translated to "LoRA Manager-Update-Playlist").

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