# ComfyUI LoRA Manager

> **Revolutionize your workflow with the ultimate LoRA companion for ComfyUI!**

[![Discord](https://img.shields.io/discord/1346296675538571315?color=7289DA&label=Discord&logo=discord&logoColor=white)](https://discord.gg/vcqNrWVFvM)
[![Release](https://img.shields.io/github/v/release/willmiao/ComfyUI-Lora-Manager?include_prereleases&color=blue&logo=github)](https://github.com/willmiao/ComfyUI-Lora-Manager/releases)
[![Release Date](https://img.shields.io/github/release-date/willmiao/ComfyUI-Lora-Manager?color=green&logo=github)](https://github.com/willmiao/ComfyUI-Lora-Manager/releases)

A comprehensive toolset that streamlines organizing, downloading, and applying LoRA models in ComfyUI. With powerful features like recipe management, checkpoint organization, and one-click workflow integration, working with models becomes faster, smoother, and significantly easier. Access the interface at: `http://localhost:8188/loras`

![Interface Preview](https://github.com/willmiao/ComfyUI-Lora-Manager/blob/main/static/images/screenshot.png)

## 📺 Tutorial: One-Click LoRA Integration
Watch this quick tutorial to learn how to use the new one-click LoRA integration feature:

[![One-Click LoRA Integration Tutorial](https://github.com/willmiao/ComfyUI-Lora-Manager/blob/main/static/images/video-thumbnails/getting-started.jpg)](https://youtu.be/hvKw31YpE-U)

## 🌐 Browser Extension
Enhance your Civitai browsing experience with our companion browser extension! See which models you already have, download new ones with a single click, and manage your downloads efficiently.

![LM Civitai Extension Preview](https://github.com/willmiao/ComfyUI-Lora-Manager/blob/main/wiki-images/civitai-models-page.png)

<div>
  <a href="https://chromewebstore.google.com/detail/lm-civitai-extension/capigligggeijgmocnaflanlbghnamgm?utm_source=item-share-cb" style="display: inline-block; background-color: #4285F4; color: white; padding: 8px 16px; text-decoration: none; border-radius: 4px; font-weight: bold; margin: 10px 0;">
    <img src="https://www.google.com/chrome/static/images/chrome-logo.svg" width="20" style="vertical-align: middle; margin-right: 8px;"> Get Extension from Chrome Web Store
  </a>
</div>

<div id="firefox-install" class="install-ok"><a href="https://github.com/willmiao/lm-civitai-extension-firefox/releases/latest/download/extension.xpi">📦 Install Firefox Extension (reviewed and verified by Mozilla)</a></div>

📚 [Learn More: Complete Tutorial](https://github.com/willmiao/ComfyUI-Lora-Manager/wiki/LoRA-Manager-Civitai-Extension-(Chrome-Extension))

---

## Release Notes

### v0.9.14
* **LoRA Cycler Node** - Introduced a new LoRA Cycler node that enables iteration through specified LoRAs with support for repeat count and pause iteration functionality. Refer to the new "Lora Cycler" template workflow for concrete example.
* **Enhanced Prompt Node with Tag Autocomplete** - Enhanced the Prompt node with comprehensive tag autocomplete based on merged Danbooru + e621 tags. Supports tag search and autocomplete functionality. Implemented a command system with shortcuts like `/char` or `/artist` for category-specific tag searching. Added `/ac` or `/noac` commands to quickly enable or disable autocomplete. Refer to the "Lora Manager Basic" template workflow in ComfyUI -> Templates -> ComfyUI-Lora-Manager for detailed tips.
* **Bug Fixes & Stability** - Addressed multiple bugs and improved overall stability.

### v0.9.12
* **LoRA Randomizer System** - Introduced a comprehensive LoRA randomization system featuring LoRA Pool and LoRA Randomizer nodes for flexible and dynamic generation workflows.
* **LoRA Randomizer Template** - Refer to the new "LoRA Randomizer" template workflow for detailed examples of flexible randomization modes, lock & reuse options, and other features.
* **Recipe Folders** - Introduced a folder system for the Recipes page, allowing users to freely organize recipes just like they do with models.
* **Recipe Bulk Operations** - Added bulk mode support for batch moving, deleting, and setting base models for selected recipes with intuitive controls like click-and-drag selection, drag-to-folder, and Ctrl+A (Select All).
* **Prompt Search & Sorting** - Search recipes by prompt content and sort by Recipe Name, Imported Date, or LoRA Count for better browsing.
* **Recipe Favorites** - Mark specific recipes as favorites for quick access.
* **Video Recipe Support** - Enabled support for video recipes (import via LM extension or URL; video file import not supported).
* **Performance Improvements** - Fixed performance issues for dramatically improved startup and loading speed. After first scan, subsequent loads are instant regardless of collection size.
* **ComfyUI Nodes 2.0 Support** - Basic support for ComfyUI Nodes 2.0.

### v0.9.10
* **Smarter Update Matching** - Users can now choose to check and group updates by matching base model only or with no base-model constraint; version lists also support toggling between same-base versions or all versions.
* **Flexible Tag Filtering** - The filter panel now supports tag exclusion: click a tag to include, click again to exclude, and click a third time to clear, enabling stronger and more flexible tag filters.
* **License Visibility & Controls** - Model detail headers and ComfyUI preview popups now show Civitai license icons. The filter panel gains license include/exclude options, and a new global context menu action, "Refresh license metadata," fetches missing license data.
* **Recipe Improvements** - Recipes now allow importing with zero LoRAs, and recipe detail pages show the related checkpoint for easier reference.
* **Better ZIP Downloads** - When downloading models packaged in ZIPs, model files are extracted into the target model folder; ZIPs containing multiple model files (e.g., WanVideo high/low LoRA pairs) are added as separate models.
* **Template Workflow Update** - Refreshed the "Illustrious Pony Example" template workflow with usage guidance for each LoRA Manager node.
* **Bug Fixes & Stability** - General fixes and stability improvements.

### v0.9.9
* **Check for Updates Feature** - Users can now check for updates for all models or selected models in bulk mode. Models with available updates will display an "update available" badge on their model card, and users can filter to show only models with updates.
* **Model Versions Management** - Added a new Versions tab in the model modal that centralizes all versions of a model, providing download, delete, and ignore update functions.
* **Send Checkpoint to ComfyUI** - Users can now click the send button on a checkpoint card to send the checkpoint directly to the current workflow's checkpoint or diffusion model loader node in ComfyUI.
* **Customizable Model Card Display** - Added a new setting that allows users to choose whether to display the model name or filename on model cards.
* **New Path Template Placeholders** - Added new path template placeholders: `{model_name}` and `{version_name}` for more flexible organization.
* **ComfyUI Auto Path Correction Setting** - Added a new setting within ComfyUI to enable or disable the auto path correction feature.

### v0.9.8
* **Full CivArchive API Support** - Added complete support for the CivArchive API as a fallback metadata source beyond Civitai API. Models deleted from Civitai can now still retrieve metadata through the CivArchive API.
* **Download Models from CivArchive** - Added support for downloading models directly from CivArchive, similar to downloading from Civitai. Simply click the Download button and paste the model URL to download the corresponding model.
* **Custom Priority Tags** - Introduced Custom Priority Tags feature, allowing users to define custom priority tags. These tags will appear as suggestions when editing tags or during auto organization/download using default paths, providing more precise and controlled folder organization. [Guide](https://github.com/willmiao/ComfyUI-Lora-Manager/wiki/Priority-Tags-Configuration-Guide)
* **Drag and Drop Tag Reordering** - Added drag and drop functionality to reorder tags in the tags edit mode for improved usability.
* **Download Control in Example Images Panel** - Added stop control in the Download Example Images Panel for better download management.
* **Prompt (LoraManager) Node with Autocomplete** - Added new Prompt (LoraManager) node with autocomplete feature for adding embeddings.
* **Lora Manager Nodes in Subgraphs** - Lora Manager nodes now support being placed within subgraphs for more flexible workflow organization.

### v0.9.6
* **Metadata Archive Database Support** - Added the ability to download and utilize a metadata archive database, enabling access to metadata for models that have been deleted from CivitAI.
* **App-Level Proxy Settings** - Introduced support for configuring a global proxy within the application, making it easier to use the manager behind network restrictions.
* **Bug Fixes** - Various bug fixes for improved stability and reliability.

### v0.9.2
* **Bulk Auto-Organization Action** - Added a new bulk auto-organization feature. You can now select multiple models and automatically organize them according to your current path template settings for streamlined management.
* **Bug Fixes** - Addressed several bugs to improve stability and reliability.

### v0.9.1
* **Enhanced Bulk Operations** - Improved bulk operations with Marquee Selection and a bulk operation context menu, providing a more intuitive, desktop-application-like user experience.
* **New Bulk Actions** - Added bulk operations for adding tags and setting base models to multiple models simultaneously.

### v0.9.0
* **UI Overhaul for Enhanced Navigation** - Replaced the top flat folder tags with a new folder sidebar and breadcrumb navigation system for a more intuitive folder browsing and selection experience.
* **Dual-Mode Folder Sidebar** - The new folder sidebar offers two display modes: 'List Mode,' which mirrors the classic folder view, and 'Tree Mode,' which presents a hierarchical folder structure for effortless navigation through nested directories.
* **Internationalization Support** - Introduced multi-language support, now available in English, Simplified Chinese, Traditional Chinese, Spanish, Japanese, Korean, French, Russian, and German. Feedback from native speakers is welcome to improve the translations.
* **Automatic Filename Conflict Resolution** - Implemented automatic file renaming (`original name + short hash`) to prevent conflicts when downloading or moving models.
* **Performance Optimizations & Bug Fixes** - Various performance improvements and bug fixes for a more stable and responsive experience.

[View Update History](./update_logs.md)

---

## **⚠ Important Note**: To use the CivitAI download feature, you'll need to:

1. Get your CivitAI API key from your profile settings
2. Add it to the LoRA Manager settings page
3. Save the settings

---

## Key Features

- 🚀 **High Performance**
  - Fast model loading and browsing
  - Smooth scrolling through large collections
  
- 🌐 **Rich Model Integration**
  - Direct download from CivitAI
  - Preview images and videos
  - Model descriptions and version selection
  - Trigger words at a glance
  - One-click workflow integration with preset values
  
- 🔄 **Checkpoint Management**
  - Scan and organize checkpoint models
  - Filter and search your collection
  - View and edit metadata
  - Clean up and manage disk space
  
- 🧩 **LoRA Recipes**
  - Save and share favorite LoRA combinations
  - Preserve generation parameters for future reference
  - Quick application to workflows
  - Import/export functionality for community sharing
  
- 💻 **User Friendly**
  - One-click access from ComfyUI menu
  - Context menu for quick actions
  - Custom notes and usage tips
  - Multi-folder support
  - Visual progress indicators during initialization

---

## Installation

### Option 1: **ComfyUI Manager** (Recommended for ComfyUI users)

1. Open **ComfyUI**.
2. Go to **Manager > Custom Node Manager**.
3. Search for `lora-manager`.
4. Click **Install**.

### Option 2: **Portable Standalone Edition** (No ComfyUI required)

1. Download the [Portable Package](https://github.com/willmiao/ComfyUI-Lora-Manager/releases/download/v0.9.8/lora_manager_portable.7z)
2. Copy the provided `settings.json.example` file to create a new file named `settings.json` in `comfyui-lora-manager` folder.
3. Edit the new `settings.json` to include your correct model folder paths and CivitAI API key
   - Set `"use_portable_settings": true` if you want the configuration to remain inside the repository folder instead of your user settings directory.
4. Run run.bat
    - To change the startup port, edit `run.bat` and modify the parameter (e.g. `--port 9001`)

### Option 3: **Manual Installation**

```bash
git clone https://github.com/willmiao/ComfyUI-Lora-Manager.git
cd ComfyUI-Lora-Manager
pip install -r requirements.txt
```

## Usage

1. There are two ways to access the LoRA manager:
   - Click the "Launch LoRA Manager" button in the ComfyUI menu
   - Visit http://localhost:8188/loras directly
2. From the interface, you can:
   - Browse and organize your LoRA models
   - Download models directly from CivitAI
   - Automatically fetch or manually set preview images
   - View and copy trigger words associated with each LoRA
   - Add personal notes and usage tips
3. To use LoRAs in your workflow:
   - Add the "Lora Loader (LoraManager)" node to your workflow
   - Select a LoRA in the manager interface
   - Click copy button or use right-click menu "Copy LoRA syntax"
   - Paste into the Lora Loader node's text input
   - The node will automatically apply preset strength and trigger words

### Filename Format Patterns for Save Image Node

The Save Image Node supports dynamic filename generation using pattern codes. You can customize how your images are named using the following format patterns:

#### Available Pattern Codes

- `%seed%` - Inserts the generation seed number
- `%width%` - Inserts the image width
- `%height%` - Inserts the image height
- `%pprompt:N%` - Inserts the positive prompt (limited to N characters)
- `%nprompt:N%` - Inserts the negative prompt (limited to N characters)
- `%model:N%` - Inserts the model/checkpoint name (limited to N characters)
- `%date%` - Inserts current date/time as "yyyyMMddhhmmss"
- `%date:FORMAT%` - Inserts date using custom format with:
  - `yyyy` - 4-digit year
  - `yy` - 2-digit year
  - `MM` - 2-digit month
  - `dd` - 2-digit day
  - `hh` - 2-digit hour
  - `mm` - 2-digit minute
  - `ss` - 2-digit second

#### Examples

- `image_%seed%` → `image_1234567890`
- `gen_%width%x%height%` → `gen_512x768`
- `%model:10%_%seed%` → `dreamshape_1234567890`
- `%date:yyyy-MM-dd%` → `2025-04-28`
- `%pprompt:20%_%seed%` → `beautiful landscape_1234567890`
- `%model%_%date:yyMMdd%_%seed%` → `dreamshaper_v8_250428_1234567890`

You can combine multiple patterns to create detailed, organized filenames for your generated images.

### Standalone Mode

You can now run LoRA Manager independently from ComfyUI:

1. **For ComfyUI users**:
   - Launch ComfyUI with LoRA Manager at least once to initialize the necessary path information in the `settings.json` file located in your user settings folder (see paths above).
   - Make sure dependencies are installed: `pip install -r requirements.txt`
   - From your ComfyUI root directory, run:
     ```bash
     python custom_nodes\comfyui-lora-manager\standalone.py
     ```
   - Access the interface at: `http://localhost:8188/loras`
   - You can specify a different host or port with arguments:
     ```bash
     python custom_nodes\comfyui-lora-manager\standalone.py --host 127.0.0.1 --port 9000
     ```

2. **For non-ComfyUI users**:
   - Copy the provided `settings.json.example` file to create a new file named `settings.json`. Update the API key, optional language, and folder paths only—the library registry is created automatically when LoRA Manager starts.
   - Edit `settings.json` to include your correct model folder paths and CivitAI API key (you can leave the defaults until ready to configure them)
   - Enable portable mode by setting `"use_portable_settings": true` if you prefer LoRA Manager to read and write the `settings.json` located in the project directory.
   - Install required dependencies: `pip install -r requirements.txt`
   - Run standalone mode:
     ```bash
     python standalone.py
     ```
   - Access the interface through your browser at: `http://localhost:8188/loras`

   > **Note:** Existing installations automatically migrate the legacy `settings.json` from the plugin folder to the user settings directory the first time you launch this version.

This standalone mode provides a lightweight option for managing your model and recipe collection without needing to run the full ComfyUI environment, making it useful even for users who primarily use other stable diffusion interfaces.

## Testing & Coverage

### Backend

Install the development dependencies and run pytest with coverage reports:

```bash
pip install -r requirements-dev.txt
COVERAGE_FILE=coverage/backend/.coverage pytest \
  --cov=py \
  --cov=standalone \
  --cov-report=term-missing \
  --cov-report=html:coverage/backend/html \
  --cov-report=xml:coverage/backend/coverage.xml \
  --cov-report=json:coverage/backend/coverage.json
```

HTML, XML, and JSON artifacts are stored under `coverage/backend/` so you can inspect hot spots locally or from CI artifacts.

### Frontend

Run the Vitest coverage suite to analyze widget hot spots:

```bash
npm run test:coverage
```

---

## Contributing

Thank you for your interest in contributing to ComfyUI LoRA Manager! As this project is currently in its early stages and undergoing rapid development and refactoring, we are temporarily not accepting pull requests.

However, your feedback and ideas are extremely valuable to us:
- Please feel free to open issues for any bugs you encounter
- Submit feature requests through GitHub issues
- Share your suggestions for improvements

We appreciate your understanding and look forward to potentially accepting code contributions once the project architecture stabilizes.

---

## Credits

This project has been inspired by and benefited from other excellent ComfyUI extensions:

- [ComfyUI-SaveImageWithMetaData](https://github.com/nkchocoai/ComfyUI-SaveImageWithMetaData) - For the image metadata functionality
- [rgthree-comfy](https://github.com/rgthree/rgthree-comfy) - For the lora loader functionality

---

## ☕ Support

If you find this project helpful, consider supporting its development:

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/pixelpawsai)

[![Patreon](https://img.shields.io/badge/Become%20a%20Patron-F96854.svg?style=for-the-badge&logo=patreon&logoColor=white)](https://patreon.com/PixelPawsAI)

WeChat: [Click to view QR code](https://raw.githubusercontent.com/willmiao/ComfyUI-Lora-Manager/main/static/images/wechat-qr.webp)

## 💬 Community

Join our Discord community for support, discussions, and updates:
[Discord Server](https://discord.gg/vcqNrWVFvM)

---
## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=willmiao/ComfyUI-Lora-Manager&type=Date)](https://star-history.com/#willmiao/ComfyUI-Lora-Manager&Date)
