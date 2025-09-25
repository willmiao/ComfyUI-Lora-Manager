## Overview

The **LoRA Manager Civitai Extension** is a Browser extension designed to work seamlessly with [LoRA Manager](https://github.com/willmiao/ComfyUI-Lora-Manager) to significantly enhance your browsing experience on [Civitai](https://civitai.com).
It also supports browsing on [CivArchive](https://civarchive.com/) (formerly CivitaiArchive).

With this extension, you can:

✅ Instantly see which models are already present in your local library  
✅ Download new models with a single click  
✅ Manage downloads efficiently with queue and parallel download support  
✅ Keep your downloaded models automatically organized according to your custom settings    

![Civitai Models page](https://github.com/willmiao/ComfyUI-Lora-Manager/blob/main/wiki-images/civitai-models-page.png)  
![CivArchive Models page](https://github.com/willmiao/ComfyUI-Lora-Manager/blob/main/wiki-images/civarchive-models-page.png)  

---

## Why Are All Features for Supporters Only?

I love building tools for the Stable Diffusion and ComfyUI communities, and LoRA Manager is a passion project that I've poured countless hours into. When I created this companion extension, my hope was to offer its core features for free, as a thank-you to all of you.

Unfortunately, I've reached a point where I need to be realistic. The level of support from the free model has been far lower than what's needed to justify the continuous development and maintenance for both projects. It was a difficult decision, but I've chosen to make the extension's features exclusive to supporters.

This change is crucial for me to be able to continue dedicating my time to improving the free and open-source LoRA Manager, which I'm committed to keeping available for everyone.

Your support does more than just unlock a few features—it allows me to keep innovating and ensures the core LoRA Manager project thrives. I'm incredibly grateful for your understanding and any support you can offer. ❤️

(_For those who previously supported me on Ko-fi with a one-time donation, I'll be sending out license keys individually as a thank-you._)


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

When switching to a specific version by clicking a version button:

- Clicking the download button will open a dropdown:
  - Download via **LoRA Manager**  
  - Download via **Original Download** (browser download)  

You can check **Remember my choice** to set your preferred default. You can change this setting anytime in the extension's settings.

![Civitai Model Page](https://github.com/willmiao/ComfyUI-Lora-Manager/blob/main/wiki-images/civitai-model-page.png)

### Resources on Image Pages (2025-08-05) — now shows in-library indicators for image resources. ‘Import image as recipe’ coming soon!

![Civitai Image Page](https://github.com/willmiao/ComfyUI-Lora-Manager/blob/main/wiki-images/civitai-image-page.jpg)

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
- [ ] One-click **Recipe Import**  
- [x] Display of in-library status for all resources in the **Resources Used** section of the image page  
- [x] One-click **Auto-organize Models**

**Stay tuned — and thank you for your support!**

---

