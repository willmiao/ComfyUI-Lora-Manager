import { describe, it, expect, vi, afterEach } from 'vitest';

import {
  probeExtension,
  delegateReimport,
  getCivitaiImageInfo,
} from '../../../static/js/utils/extensionReimportBridge.js';

const dispatchedEvents = [];

function dispatchProtocolEvent(type, payload) {
  document.dispatchEvent(
    new CustomEvent(type, { detail: JSON.stringify(payload) })
  );
}

// Installs a fake extension that answers probes with the given result.
function installProbeResponder(result) {
  const listener = () => dispatchProtocolEvent('lm:reimportProbeResult', result);
  document.addEventListener('lm:reimportProbe', listener);
  return () => document.removeEventListener('lm:reimportProbe', listener);
}

afterEach(() => {
  dispatchedEvents.length = 0;
});

describe('probeExtension', () => {
  it('resolves null when no extension answers within the timeout', async () => {
    const result = await probeExtension({ timeoutMs: 20 });
    expect(result).toBeNull();
  });

  it('resolves the probe result when the extension answers', async () => {
    const uninstall = installProbeResponder({
      supported: true,
      licenseValid: true,
      extensionVersion: '1.2.3',
    });
    try {
      const result = await probeExtension({ timeoutMs: 1000 });
      expect(result).toEqual({
        supported: true,
        licenseValid: true,
        extensionVersion: '1.2.3',
        reason: undefined,
      });
    } finally {
      uninstall();
    }
  });

  it('reports unsupported/unlicensed answers verbatim', async () => {
    const uninstall = installProbeResponder({
      supported: false,
      licenseValid: false,
      reason: 'license expired',
    });
    try {
      const result = await probeExtension({ timeoutMs: 1000 });
      expect(result.supported).toBe(false);
      expect(result.licenseValid).toBe(false);
      expect(result.reason).toBe('license expired');
    } finally {
      uninstall();
    }
  });

  it('ignores malformed probe results and times out', async () => {
    const listener = () => {
      document.dispatchEvent(
        new CustomEvent('lm:reimportProbeResult', { detail: '{broken json' })
      );
    };
    document.addEventListener('lm:reimportProbe', listener);
    try {
      const result = await probeExtension({ timeoutMs: 20 });
      expect(result).toBeNull();
    } finally {
      document.removeEventListener('lm:reimportProbe', listener);
    }
  });
});

describe('delegateReimport', () => {
  const recipes = [
    { recipeId: 'r1', imageId: 123, imageUrl: 'https://civitai.com/images/123', title: 'One' },
    { recipeId: 'r2', imageId: 456, imageUrl: 'https://civitai.com/images/456', title: 'Two' },
  ];

  it('rejects immediately for an empty recipe list', async () => {
    await expect(delegateReimport([])).rejects.toThrow('non-empty');
  });

  it('rejects on timeout when the extension never answers', async () => {
    await expect(
      delegateReimport(recipes, { timeoutMs: 20 })
    ).rejects.toThrow('timed out');
  });

  it('dispatches the batch with a requestId and resolves on batchDone', async () => {
    const progressEvents = [];
    let seenRequest = null;

    const listener = (event) => {
      seenRequest = JSON.parse(event.detail);
      const { requestId } = seenRequest;
      // Progress for a DIFFERENT batch must be ignored.
      dispatchProtocolEvent('lm:reimportProgress', {
        requestId: 'other-batch',
        current: 99,
        total: 99,
        recipeId: 'nope',
        title: 'nope',
        status: 'success',
      });
      dispatchProtocolEvent('lm:reimportProgress', {
        requestId,
        current: 1,
        total: 2,
        recipeId: 'r1',
        title: 'One',
        status: 'success',
      });
      dispatchProtocolEvent('lm:reimportProgress', {
        requestId,
        current: 2,
        total: 2,
        recipeId: 'r2',
        title: 'Two',
        status: 'failed',
        message: 'boom',
      });
      dispatchProtocolEvent('lm:reimportBatchDone', {
        requestId,
        completed: 1,
        failed: 1,
      });
    };
    document.addEventListener('lm:reimportViaExtension', listener);
    try {
      const result = await delegateReimport(recipes, {
        onProgress: (progress) => progressEvents.push(progress),
        timeoutMs: 1000,
      });

      expect(seenRequest.recipes).toEqual(recipes);
      expect(typeof seenRequest.requestId).toBe('string');
      expect(seenRequest.requestId.length).toBeGreaterThan(0);
      expect(result).toEqual({ completed: 1, failed: 1 });
      // Only this batch's progress events reach the callback.
      expect(progressEvents.map((p) => p.recipeId)).toEqual(['r1', 'r2']);
      expect(progressEvents[1].status).toBe('failed');
    } finally {
      document.removeEventListener('lm:reimportViaExtension', listener);
    }
  });

  it('resets the timeout on every progress heartbeat', async () => {
    vi.useFakeTimers();
    let requestId = null;
    const listener = (event) => {
      requestId = JSON.parse(event.detail).requestId;
    };
    document.addEventListener('lm:reimportViaExtension', listener);
    try {
      const promise = delegateReimport(recipes, { timeoutMs: 1000 });

      // At t=900ms a progress event arrives, pushing the deadline to t=1900ms.
      await vi.advanceTimersByTimeAsync(900);
      dispatchProtocolEvent('lm:reimportProgress', {
        requestId,
        current: 1,
        total: 2,
        recipeId: 'r1',
        title: 'One',
        status: 'started',
      });
      // t=1800ms: past the original deadline, still alive thanks to heartbeat.
      await vi.advanceTimersByTimeAsync(900);
      dispatchProtocolEvent('lm:reimportBatchDone', {
        requestId,
        completed: 2,
        failed: 0,
      });

      await expect(promise).resolves.toEqual({ completed: 2, failed: 0 });
    } finally {
      document.removeEventListener('lm:reimportViaExtension', listener);
      vi.useRealTimers();
    }
  });
});

describe('getCivitaiImageInfo', () => {
  it.each([
    'https://civitai.com/images/12345',
    'https://civitai.red/images/12345',
    'https://civitai.green/images/12345',
    'https://civitai.com/images/12345?foo=bar',
  ])('extracts the image id from %s', (url) => {
    expect(getCivitaiImageInfo(url)).toEqual({ imageId: 12345, imageUrl: url });
  });

  it.each([
    null,
    '',
    'not a url',
    'ftp://civitai.com/images/12345',
    'https://civitai.com/models/12345',
    'https://example.com/images/12345',
    'https://image.civitai.com/x/y/original=true/pic.png',
  ])('returns null for %s', (url) => {
    expect(getCivitaiImageInfo(url)).toBeNull();
  });
});
