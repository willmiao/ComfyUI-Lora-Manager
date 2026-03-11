import { describe, it, expect } from 'vitest';

describe('Version Detection Logic', () => {
    const parseVersion = (versionStr) => {
        if (!versionStr || typeof versionStr !== 'string') {
            return [0, 0, 0];
        }
        
        const cleanVersion = versionStr.replace(/^[vV]/, '').split('-')[0];
        const parts = cleanVersion.split('.').map(part => parseInt(part, 10) || 0);
        
        while (parts.length < 3) {
            parts.push(0);
        }
        
        return parts;
    };
    
    const compareVersions = (version1, version2) => {
        const v1 = typeof version1 === 'string' ? parseVersion(version1) : version1;
        const v2 = typeof version2 === 'string' ? parseVersion(version2) : version2;
        
        for (let i = 0; i < 3; i++) {
            if (v1[i] > v2[i]) return 1;
            if (v1[i] < v2[i]) return -1;
        }
        
        return 0;
    };
    
    const MIN_VERSION_FOR_ACTION_BAR = [1, 33, 9];
    
    const supportsActionBarButtons = (version) => {
        return compareVersions(version, MIN_VERSION_FOR_ACTION_BAR) >= 0;
    };
    
    it('should parse version strings correctly', () => {
        expect(parseVersion('1.33.9')).toEqual([1, 33, 9]);
        expect(parseVersion('v1.33.9')).toEqual([1, 33, 9]);
        expect(parseVersion('1.33.9-beta')).toEqual([1, 33, 9]);
        expect(parseVersion('1.33')).toEqual([1, 33, 0]);
        expect(parseVersion('1')).toEqual([1, 0, 0]);
        expect(parseVersion('')).toEqual([0, 0, 0]);
        expect(parseVersion(null)).toEqual([0, 0, 0]);
    });
    
    it('should compare versions correctly', () => {
        expect(compareVersions('1.33.9', '1.33.9')).toBe(0);
        expect(compareVersions('1.33.10', '1.33.9')).toBe(1);
        expect(compareVersions('1.34.0', '1.33.9')).toBe(1);
        expect(compareVersions('2.0.0', '1.33.9')).toBe(1);
        expect(compareVersions('1.33.8', '1.33.9')).toBe(-1);
        expect(compareVersions('1.32.0', '1.33.9')).toBe(-1);
        expect(compareVersions('0.9.9', '1.33.9')).toBe(-1);
    });
    
    it('should return false for versions below 1.33.9', () => {
        expect(supportsActionBarButtons('1.33.8')).toBe(false);
        expect(supportsActionBarButtons('1.32.0')).toBe(false);
        expect(supportsActionBarButtons('0.9.9')).toBe(false);
    });
    
    it('should return true for versions 1.33.9 and above', () => {
        expect(supportsActionBarButtons('1.33.9')).toBe(true);
        expect(supportsActionBarButtons('1.33.10')).toBe(true);
        expect(supportsActionBarButtons('1.34.0')).toBe(true);
        expect(supportsActionBarButtons('2.0.0')).toBe(true);
    });
    
    it('should handle edge cases in version parsing', () => {
        expect(supportsActionBarButtons('v1.33.9')).toBe(true);
        expect(supportsActionBarButtons('1.33.9-rc.1')).toBe(true);
        expect(supportsActionBarButtons('1.33.9-beta')).toBe(true);
    });
});
