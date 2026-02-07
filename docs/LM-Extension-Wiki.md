## Overview

The **LoRA Manager Civitai Extension** is a Browser extension designed to work seamlessly with [LoRA Manager](https://github.com/willmiao/ComfyUI-Lora-Manager) to significantly enhance your browsing experience on [Civitai](https://civitai.com). With this extension, you can:

✅ Instantly see which models are already present in your local library  
✅ Download new models with a single click  
✅ Manage downloads efficiently with queue and parallel download support  
✅ Keep your downloaded models automatically organized according to your custom settings    

![Civitai Models page](https://github.com/willmiao/ComfyUI-Lora-Manager/blob/main/wiki-images/civitai-models-page.png) 

**Update:** It now also supports browsing on [CivArchive](https://civarchive.com/) (formerly CivitaiArchive). 

![CivArchive Models page](https://github.com/willmiao/ComfyUI-Lora-Manager/blob/main/wiki-images/civarchive-models-page.png)  

---

## Why Supporter Access?

LoRA Manager is built with love for the Stable Diffusion and ComfyUI communities. Your support makes it possible for me to keep improving and maintaining the tool full-time.

Supporter-exclusive features help ensure the long-term sustainability of LoRA Manager, allowing continuous updates, new features, and better performance for everyone.

Every contribution directly fuels development and keeps the core LoRA Manager free and open-source. In addition to monthly supporters, one-time donation supporters will also receive a license key, with the duration scaling according to the contribution amount. Thank you for helping keep this project alive and growing. ❤️


---

## Installation

### Supported Browsers & Installation Methods

| Browser            | Installation Method                                                                 |
|--------------------|-------------------------------------------------------------------------------------|
| **Google Chrome**   | [Chrome Web Store link](https://chromewebstore.google.com/detail/capigligggeijgmocnaflanlbghnamgm?utm_source=item-share-cb) |
| **Microsoft Edge**  | Install via Chrome Web Store (compatible)                                          |
| **Brave Browser**   | Install via Chrome Web Store (compatible)                                          |
| **Opera**           | Install via Chrome Web Store (compatible)                                          |
| **Firefox**         | <div id="firefox-install" class="install-ok"><a href="https://github.com/willmiao/lm-civitai-extension-firefox/releases/latest/download/extension.xpi">📦 Install Firefox Extension (reviewed and verified by Mozilla)</a></div>             |

For non-Chrome browsers (e.g., Microsoft Edge), you can typically install extensions from the Chrome Web Store by following these steps: open the extension’s Chrome Web Store page, click 'Get extension', then click 'Allow' when prompted to enable installations from other stores, and finally click 'Add extension' to complete the installation.

---

## Privacy & Security

I understand concerns around browser extensions and privacy, and I want to be fully transparent about how the **LM Civitai Extension** works:

- **Reviewed and Verified**  
  This extension has been **manually reviewed and approved by the Chrome Web Store**. The Firefox version uses the **exact same code** (only the packaging format differs) and has passed **Mozilla’s Add-on review**.

- **Minimal Network Access**  
  The only external server this extension connects to is:  
  **`https://willmiao.shop`** — used solely for **license validation**.

  It does **not collect, transmit, or store any personal or usage data**.  
  No browsing history, no user IDs, no analytics, no hidden trackers.

- **Local-Only Model Detection**  
  Model detection and LoRA Manager communication all happen **locally** within your browser, directly interacting with your local LoRA Manager backend.

I value your trust and are committed to keeping your local setup private and secure. If you have any questions, feel free to reach out!

---

## How to Use

After installing the extension, you'll automatically receive a **7-day trial** to explore all features.

When the extension is correctly installed and your license is valid:

- Open **Civitai**, and you'll see visual indicators added by the extension on model cards, showing:
  - ✅ Models already present in your local library  
  - ⬇️ A download button for models not in your library  

Clicking the download button adds the corresponding model version to the download queue, waiting to be downloaded. You can set up to **5 models to download simultaneously**.

### Visual Indicators Appear On:

- **Home Page** — Featured models  
- **Models Page**  
- **Creator Profiles** — If the creator has set their models to be visible  
- **Recommended Resources** — On individual model pages  

### Version Buttons on Model Pages

On a specific model page, visual indicators also appear on version buttons, showing which versions are already in your local library.

**Starting from v0.4.8**, model pages use a dedicated download button for better compatibility. When switching to a specific version by clicking a version button:

- The new **dedicated download button** directly triggers download via **LoRA Manager**
- The **original download button** remains unchanged for standard browser downloads

![Civitai Model Page](https://github.com/willmiao/ComfyUI-Lora-Manager/blob/main/wiki-images/civitai-model-page.png)

### Hide Models Already in Library (Beta)

**New in v0.4.8**: A new **Hide models already in library (Beta)** option makes it easier to focus on models you haven't added yet. It can be enabled from Settings, or toggled quickly using **Ctrl + Shift + H** (macOS: **Command + Shift + H**).

### Resources on Image Pages — now shows in-library indicators for image resources plus one-click recipe import

- **One-Click Import Civitai Image as Recipe** — Import any Civitai image as a recipe with a single click in the Resources Used panel.
- **Auto-Queue Missing Assets** — In Settings you can decide if LoRAs or checkpoints referenced by that image should automatically be added to your download queue.
- **More Accurate Metadata** — Importing directly from the page is faster than copying inside LM and keeps on-site tags and other metadata perfectly aligned.

![Civitai Image Page](https://github.com/willmiao/ComfyUI-Lora-Manager/blob/main/wiki-images/civitai-image-page.jpg)

[![alt](url)](https://github.com/user-attachments/assets/41fd4240-c949-4f83-bde7-8f3124c09494)

---

## Model Download Location & LoRA Manager Settings

To use the **one-click download function**, you must first set:

- Your **Default LoRAs Root**  
- Your **Default Checkpoints Root**  

These are set within LoRA Manager's settings.

When everything is configured, downloaded model files will be placed in:  

`<Default_Models_Root>/<Base_Model_of_the_Model>/<First_Tag_of_the_Model>`


### Update: Default Path Customization (2025-07-21)  

A new setting to customize the default download path has been added in the nightly version. You can now personalize where models are saved when downloading via the LM Civitai Extension.

![Default Path Customization](https://github.com/willmiao/ComfyUI-Lora-Manager/blob/main/wiki-images/default-path-customization.png)

The previous YAML path mapping file will be deprecated—settings will now be unified in settings.json to simplify configuration.

---

## Backend Port Configuration

If your **ComfyUI** or **LoRA Manager** backend is running on a port **other than the default 8188**, you must configure the backend port in the extension's settings.

After correctly setting and saving the port, you'll see in the extension's header area:  
- A **Healthy** status with the tooltip:  `Connected to LoRA Manager on port xxxx`


---

## Advanced Usage

### Connecting to a Remote LoRA Manager

If your LoRA Manager is running on another computer, you can still connect from your browser using port forwarding.

> **Why can't you set a remote IP directly?**
>
> For privacy and security, the extension only requests access to `http://127.0.0.1/*`. Supporting remote IPs would require much broader permissions, which may be rejected by browser stores and could raise user concerns.

**Solution: Port Forwarding with `socat`**

On your browser computer, run:

`socat TCP-LISTEN:8188,bind=127.0.0.1,fork TCP:REMOTE.IP.ADDRESS.HERE:8188`

- Replace `REMOTE.IP.ADDRESS.HERE` with the IP of the machine running LoRA Manager.
- Adjust the port if needed.

This lets the extension connect to `127.0.0.1:8188` as usual, with traffic forwarded to your remote server.

_Thanks to user **Temikus** for sharing this solution!_

---

## Roadmap

The extension will evolve alongside **LoRA Manager** improvements. Planned features include:

- [x] Support for **additional model types** (e.g., embeddings)
- [x] One-click **Recipe Import**
- [x] Display of in-library status for all resources in the **Resources Used** section of the image page
- [x] One-click **Auto-organize Models**
- [x] **Hide models already in library (Beta)** - Focus on models you haven't added yet

**Stay tuned — and thank you for your support!**

---
