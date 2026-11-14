# Canvas Quick Pickers

## Entry points

The full manager and canvas quick tools have separate primary entry points:

- Clicking the top-bar LoRA Manager button opens the full manager in a new tab.
- Shift+clicking it opens the full manager in a new window.
- A single chevron beside the main button opens the **Quick Actions** menu.
  **Quick LoRA Picker** displays its `Alt+L` keybinding using ComfyUI's menu
  keybinding visual treatment; **Open LoRA Manager** remains available there too.
- `Alt+L` toggles the Quick LoRA Picker through a registered ComfyUI command and
  keybinding.
- LoRA nodes expose **Quick LoRA Picker** in their context menu. ComfyUI's
  current extension-menu converter does not pass shortcut badges through for
  extension items, so the node menu uses the plain label rather than custom HTML
  that would behave differently between legacy and Vue menus.
- The **+** button in the LoRA widget header opens the picker with that node as
  its initial target. It remains available when the widget is empty, and its
  tooltip displays the `Alt+L` shortcut.

Quick pickers are contextual canvas tools. They do not each need a permanent
top-bar button. The top bar continues to use `actionBarButtons` on supported
frontends, with direct menu DOM insertion retained only as the legacy fallback.

The picker uses one keyboard-driven selection across folders and LoRAs. Up and
Down follow the visible row order, Right or Enter opens a selected folder, Left
returns to its parent, and Enter applies a selected LoRA. Navigation is handled
at panel level rather than only while the search field is focused.

**Full details** opens the manager in the named `lm-lora-manager` tab. Repeated
requests reuse that tab, and the manager handles `hashchange` so a reused tab
opens the requested model modal without reloading.

## Growth strategy

Do not add one top-bar button per picker. Top-bar space is shared with ComfyUI
and other custom nodes, so independent buttons for LoRAs, workflows, recipes,
and future asset types would not scale.

The existing chevron opens a single **Quick Actions** menu. As tools are added,
it can contain entries such as:

- Quick LoRA Picker
- Quick Workflow Picker
- Open LoRA Manager

The main button keeps its existing click behavior. New tools add menu items and
registered commands, not more permanent buttons. A single chevron is preferable
to a row of feature-specific icons, and modifier-only click overloads should not
become the primary way to discover tools.

When roughly three or four quick tools exist, evaluate a unified Quick Launcher:

- One search field with `LoRAs`, `Workflows`, and `Recipes` views.
- The most recently used view is restored.
- The current node context selects the initial view when relevant.
- The existing floating-panel shell and keyboard navigation are shared, while
  each asset type keeps a result layout suited to its data and actions.
- Existing commands and shortcuts remain available as direct routes to a view.

This is an evolution path, not a requirement to build the launcher before the
additional tools exist.
