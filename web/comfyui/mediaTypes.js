/**
 * Media type detection for preview URLs inside the ComfyUI widget bundle.
 *
 * Local previews are served through `/api/lm/previews?path=<encoded path>` and
 * the URL carries a cache-busting `&v=<mtime>` parameter, so the media type
 * cannot be read from the end of the URL string. The LM web UI uses the same
 * logic in `static/js/utils/mediaTypes.js`; the widget bundle is served from a
 * different mount, so it keeps its own copy.
 */

export const VIDEO_EXTENSIONS = [".mp4", ".webm", ".mov", ".mkv"];

/**
 * Extract the file extension from a single path fragment, query value or URL.
 * Anything from the first `?`/`#` onwards is dropped so
 * `/previews?path=...mp4&v=123` is treated as `/previews`.
 *
 * @param {*} value
 * @returns {string}
 */
export function extractMediaExtension(value) {
  if (value == null) {
    return "";
  }

  let candidate = String(value);
  const queryIndex = candidate.search(/[?#]/);
  if (queryIndex !== -1) {
    candidate = candidate.slice(0, queryIndex);
  }
  try {
    candidate = decodeURIComponent(candidate);
  } catch (error) {
    // Ignore malformed escape sequences and fall back to the raw value.
  }

  const lastDot = candidate.lastIndexOf(".");
  if (lastDot === -1) {
    return "";
  }
  const extension = candidate.slice(lastDot).toLowerCase();
  if (extension.includes("/") || extension.includes("\\")) {
    return "";
  }
  return extension;
}

function collectCandidates(url) {
  const candidates = new Set([url]);

  try {
    const parsed = new URL(url, window.location.origin);
    candidates.add(parsed.pathname);
    parsed.searchParams.forEach((value) => candidates.add(value));
  } catch (error) {
    // Ignore parse errors and rely on the raw value.
  }

  // Relative or malformed URLs may fail to parse; splitting on query
  // separators still exposes the encoded path segment.
  String(url)
    .split(/[?&=]/)
    .forEach((fragment) => {
      if (fragment) {
        candidates.add(fragment);
      }
    });

  return candidates;
}

/**
 * Best-effort extension of the media file a preview URL points at.
 *
 * @param {string} url
 * @returns {string}
 */
export function getPreviewMediaExtension(url) {
  if (!url || typeof url !== "string") {
    return "";
  }

  for (const candidate of collectCandidates(url)) {
    const extension = extractMediaExtension(candidate);
    if (extension) {
      return extension;
    }
  }

  return "";
}

/**
 * Return true when the preview URL points at a video file.
 *
 * @param {string} url
 * @returns {boolean}
 */
export function isVideoPreviewUrl(url) {
  const extension = getPreviewMediaExtension(url);
  return Boolean(extension) && VIDEO_EXTENSIONS.includes(extension);
}
