/**
 * Example-image entry ↔ local file pairing.
 *
 * A model's example entries live in the `.metadata.json` sidecar
 * (`civitai.images` / `civitai.customImages`), while the actual media files
 * sit in the model's folder under `example_images_path`. Entries imported from
 * disk deliberately carry an empty `url` — the file is served through
 * `/example_images_static/...` instead — so anything that needs a displayable
 * URL has to pair the entry with its file first.
 *
 * Local file names encode the entry they belong to:
 *   - `custom_<id>.<ext>` for `customImages` entries (matched by `img.id`)
 *   - `image_<index>.<ext>` for CivitAI `images` entries (matched by position)
 *
 * Kept in its own module (rather than in MediaRenderers) so lightweight
 * consumers such as the card preview cycler do not pull in the whole showcase
 * rendering stack.
 */
import { isVideoPreviewUrl } from '../../../utils/mediaTypes.js';

/**
 * Find the local example file backing a metadata entry.
 *
 * @param {Object} img - Image/video metadata entry
 * @param {number} index - Position of the entry in its source array (only
 *   meaningful for regular CivitAI images; custom entries match by id)
 * @param {Array} exampleFiles - Files from `/api/lm/example-image-files`
 * @returns {Object|null} The matching file record, or null
 */
export function findLocalFile(img, index, exampleFiles) {
    if (!exampleFiles || exampleFiles.length === 0) return null;

    let localFile = null;

    if (typeof img.id === 'string' && img.id) {
        // This is a custom image, find by custom_<id>
        const customPrefix = `custom_${img.id}`;
        localFile = exampleFiles.find(file => file.name.startsWith(customPrefix));
    } else {
        // This is a regular image from civitai, find by index
        localFile = exampleFiles.find(file => {
            const match = file.name.match(/image_(\d+)\./);
            return match && parseInt(match[1]) === index;
        });
    }

    return localFile ?? null;
}

/**
 * Resolve a metadata entry to something displayable.
 *
 * The downloaded local copy wins when one exists: it is served by this server
 * (no CDN round trip) and already has the size the download produced, which
 * matters for consumers that swap frames faster than a cold remote fetch.
 * Downloaded entries keep their CivitAI `url` in the sidecar, so the remote
 * URL is only the fallback for entries the download never reached; entries
 * imported from disk have no remote URL at all and are local-only.
 *
 * @param {Object} img - Image/video metadata entry
 * @param {number} index - Position of the entry in its source array
 * @param {Array} exampleFiles - Files from `/api/lm/example-image-files`
 * @returns {{localFile: Object|null, url: string, isVideo: boolean}}
 *   `url` is empty when neither a local file nor a remote URL exists
 */
export function resolveExampleMedia(img, index, exampleFiles = []) {
    const localFile = findLocalFile(img, index, exampleFiles);
    const remoteUrl = typeof img?.url === 'string' ? img.url : '';
    const url = localFile?.path || remoteUrl || '';
    const isVideo = Boolean(localFile?.is_video)
        || isVideoPreviewUrl(remoteUrl)
        || (typeof img?.type === 'string' && img.type.toLowerCase() === 'video');

    return { localFile, url, isVideo };
}
