import { describe, it, expect, beforeEach } from 'vitest';
import {
    isSoftwareRendererString,
    applyModalBackdropBlurPolicy,
} from '../../../static/js/utils/renderingCapability.js';

describe('isSoftwareRendererString', () => {
    it('detects SwiftShader (Chrome with hardware acceleration disabled)', () => {
        expect(isSoftwareRendererString(
            'WebKit WebGL SwiftShader'
        )).toBe(true);
        expect(isSoftwareRendererString(
            'ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)'
        )).toBe(true);
    });

    it('detects Mesa software rasterizers (Linux)', () => {
        expect(isSoftwareRendererString('llvmpipe (LLVM 17.0.6, 256 bits)')).toBe(true);
        expect(isSoftwareRendererString('softpipe')).toBe(true);
    });

    it('detects generic software renderer strings', () => {
        expect(isSoftwareRendererString('Software Renderer')).toBe(true);
        expect(isSoftwareRendererString('Microsoft Basic Render Driver')).toBe(true);
    });

    it('accepts hardware GPU strings', () => {
        expect(isSoftwareRendererString(
            'ANGLE (NVIDIA, NVIDIA GeForce RTX 4090 Direct3D11 vs_5_0 ps_5_0, D3D11)'
        )).toBe(false);
        expect(isSoftwareRendererString(
            'ANGLE (AMD, AMD Radeon RX 7900 XTX (0x0000744C) Direct3D11 vs_5_0 ps_5_0, D3D11)'
        )).toBe(false);
        expect(isSoftwareRendererString('Apple M4 Pro')).toBe(false);
        expect(isSoftwareRendererString('Mesa Intel(R) UHD Graphics 620 (KBL GT2)')).toBe(false);
    });

    it('handles empty input', () => {
        expect(isSoftwareRendererString('')).toBe(false);
        expect(isSoftwareRendererString(null)).toBe(false);
    });
});

describe('applyModalBackdropBlurPolicy', () => {
    beforeEach(() => {
        document.documentElement.classList.remove('no-modal-backdrop-blur');
    });

    it('adds the disabling class under software rendering', () => {
        applyModalBackdropBlurPolicy(true);
        expect(document.documentElement.classList.contains('no-modal-backdrop-blur')).toBe(true);
    });

    it('removes the disabling class under hardware rendering', () => {
        document.documentElement.classList.add('no-modal-backdrop-blur');
        applyModalBackdropBlurPolicy(false);
        expect(document.documentElement.classList.contains('no-modal-backdrop-blur')).toBe(false);
    });
});
