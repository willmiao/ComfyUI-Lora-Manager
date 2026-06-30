import { describe, it, expect } from 'vitest';
import { DownloadManager } from '../../../static/js/managers/DownloadManager.js';

describe('DownloadManager.detectUrlType — HF URL detection', () => {

    it('detects HF resolve URL with file', () => {
        const result = DownloadManager.detectUrlType(
            'https://huggingface.co/dx8152/Flux2-Klein-9B-Consistency/resolve/main/Flux2-Klein-9B-consistency-V2.safetensors'
        );
        expect(result).toEqual({
            type: 'hf-resolve',
            repo: 'dx8152/Flux2-Klein-9B-Consistency',
            revision: 'main',
            filename: 'Flux2-Klein-9B-consistency-V2.safetensors',
        });
    });

    it('detects HF resolve URL with subdirectory file', () => {
        const result = DownloadManager.detectUrlType(
            'https://huggingface.co/user/repo/resolve/main/subdir/model.safetensors'
        );
        expect(result).toEqual({
            type: 'hf-resolve',
            repo: 'user/repo',
            revision: 'main',
            filename: 'subdir/model.safetensors',
        });
    });

    it('detects HF repo URL (full URL)', () => {
        const result = DownloadManager.detectUrlType(
            'https://huggingface.co/dx8152/Flux2-Klein-9B-Consistency'
        );
        expect(result).toEqual({
            type: 'hf-repo',
            repo: 'dx8152/Flux2-Klein-9B-Consistency',
        });
    });

    it('detects HF repo URL (bare user/repo)', () => {
        const result = DownloadManager.detectUrlType('dx8152/Flux2-Klein-9B-Consistency');
        expect(result).toEqual({
            type: 'hf-repo',
            repo: 'dx8152/Flux2-Klein-9B-Consistency',
        });
    });

    it('detects HF repo URL with trailing slash', () => {
        const result = DownloadManager.detectUrlType(
            'https://huggingface.co/user/repo/'
        );
        expect(result).toEqual({
            type: 'hf-repo',
            repo: 'user/repo',
        });
    });

    it('detects CivitAI URL', () => {
        const result = DownloadManager.detectUrlType(
            'https://civitai.com/models/123/some-model'
        );
        expect(result).toEqual({ type: 'civitai' });
    });

    it('detects CivArchive URL', () => {
        const result = DownloadManager.detectUrlType(
            'https://civarchive.com/models/456'
        );
        expect(result).toEqual({ type: 'civitai' });
    });

    it('detects direct HTTP URL', () => {
        const result = DownloadManager.detectUrlType(
            'https://example.com/file.zip'
        );
        expect(result).toEqual({ type: 'direct-http' });
    });

    it('returns null for invalid input', () => {
        expect(DownloadManager.detectUrlType('')).toBeNull();
        expect(DownloadManager.detectUrlType('   ')).toBeNull();
    });

    it('returns null for unrecognized path', () => {
        expect(DownloadManager.detectUrlType('justrandomtext')).toBeNull();
    });

    it('prefers HF resolve over repo when both match', () => {
        const result = DownloadManager.detectUrlType(
            'https://huggingface.co/user/repo/resolve/main/file.safetensors'
        );
        expect(result?.type).toBe('hf-resolve');
    });

    it('prefers CivitAI over HF when both match', () => {
        // CivitAI check comes first in detectUrlType
        // This URL should be detected as CivitAI, not HF
        const result = DownloadManager.detectUrlType(
            'https://civitai.com/models/123?huggingface.co/test/repo'
        );
        expect(result?.type).toBe('civitai');
    });
});
