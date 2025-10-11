# Custom Priority Tag Format Proposal

To support user-defined priority tags with flexible aliasing across different model types, the configuration will be stored as editable strings. The format balances readability with enough structure for parsing on both the backend and frontend.

## Format Overview

- Each model type is declared on its own line: `model_type: entries`.
- Entries are comma-separated and ordered by priority from highest to lowest.
- An entry may be a single canonical tag (e.g., `realistic`) or a canonical tag with aliases.
- Canonical tags define the final folder name that should be used when matching that entry.
- Aliases are enclosed in parentheses and separated by `|` (vertical bar).
- All matching is case-insensitive; stored canonical names preserve the user-specified casing for folder creation and UI suggestions.

### Grammar

```
priority-config := model-config { "\n" model-config }
model-config    := model-type ":" entry-list
model-type      := <identifier without spaces>
entry-list      := entry { "," entry }
entry           := canonical [ "(" alias { "|" alias } ")" ]
canonical       := <tag text without parentheses or commas>
alias           := <tag text without parentheses, commas, or pipes>
```

Examples:

```
lora: celebrity(celeb|celebrity), stylized, character(char)
checkpoint: realistic(realism|realistic), anime(anime-style|toon)
embedding: face, celeb(celebrity|celeb)
```

## Parsing Notes

- Whitespace around separators is ignored to make manual editing more forgiving.
- Duplicate canonical tags within the same model type collapse to a single entry; the first definition wins.
- Aliases map to their canonical tag. When generating folder names, the canonical form is used.
- Tags that do not match any alias or canonical entry fall back to the first tag in the model's tag list, preserving current behavior.

## Usage

- **Backend:** Convert each model type's string into an ordered list of canonical tags with alias sets. During path generation, iterate by priority order and match tags against both canonical names and their aliases.
- **Frontend:** Surface canonical tags as suggestions, optionally displaying aliases in tooltips or secondary text. Input validation should warn about duplicate aliases within the same model type.

This format allows users to customize priority tag handling per model type while keeping editing simple and avoiding proliferation of folder names through alias normalization.
