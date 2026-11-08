import { describe, expect, it } from 'vitest';

import { ThroughputEtaTracker } from '../../../static/js/utils/throughputEta.js';

describe('ThroughputEtaTracker', () => {
    it('waits for enough observations before estimating', () => {
        const tracker = new ThroughputEtaTracker({
            windowMs: 90000,
            minSpanMs: 20000,
            minCompleted: 4,
        });

        expect(tracker.update(0, 100, { now: 0 })).toBeNull();
        expect(tracker.update(1, 100, { now: 5000 })).toBeNull();
        expect(tracker.update(2, 100, { now: 10000 })).toBeNull();
        expect(tracker.update(3, 100, { now: 15000 })).toBeNull();
    });

    it('derives the rate from the recent window', () => {
        const tracker = new ThroughputEtaTracker({
            windowMs: 90000,
            minSpanMs: 20000,
            minCompleted: 4,
        });

        for (let index = 0; index <= 4; index += 1) {
            expect(tracker.update(index, 100, { now: index * 5000 })).toBe(
                index === 4 ? 480 : null
            );
        }
    });

    it('does not count a paused interval as download time', () => {
        const tracker = new ThroughputEtaTracker({
            windowMs: 90000,
            minSpanMs: 20000,
            minCompleted: 4,
        });

        for (let index = 0; index <= 4; index += 1) {
            tracker.update(index, 100, { now: index * 5000 });
        }

        // Paused for ten minutes: the callback still runs, but running=false.
        expect(tracker.update(4, 100, { now: 25000, running: false })).toBeNull();
        expect(tracker.update(4, 100, { now: 625000, running: true })).toBeNull();

        for (let index = 5; index <= 8; index += 1) {
            tracker.update(index, 100, {
                now: 625000 + (index - 4) * 5000,
                running: true,
            });
        }

        // Four more models in 20s = 0.2 models/s, 92 remaining = 460s. An
        // estimator that kept the paused gap would report hours here.
        expect(tracker.update(8, 100, { now: 645000, running: true })).toBe(460);
    });

    it('drops the window when the run counter restarts', () => {
        const tracker = new ThroughputEtaTracker({
            windowMs: 90000,
            minSpanMs: 20000,
            minCompleted: 4,
        });

        for (let index = 0; index <= 4; index += 1) {
            tracker.update(index, 100, { now: index * 5000 });
        }
        expect(tracker.update(4, 100, { now: 20000 })).toBe(480);

        // A new run starts at completed=0.
        expect(tracker.update(0, 100, { now: 25000 })).toBeNull();
        for (let index = 1; index <= 4; index += 1) {
            tracker.update(index, 100, { now: 25000 + index * 5000 });
        }
        expect(tracker.update(4, 100, { now: 45000 })).toBe(480);
    });

    it('rejects a skip burst at the start of a resumed run', () => {
        const tracker = new ThroughputEtaTracker({
            windowMs: 60000,
            minSpanMs: 20000,
            minCompleted: 4,
        });

        expect(tracker.update(0, 1000, { now: 0 })).toBeNull();
        // 282 already-populated folders are marked processed in one poll.
        expect(tracker.update(282, 1000, { now: 3000 })).toBeNull();

        for (let index = 1; index <= 12; index += 1) {
            tracker.update(282 + index, 1000, { now: 3000 + index * 1833 });
        }

        // Twelve real downloads over 22s: 706 remaining / 0.545 = 1295s.
        // Counting the 282-model jump would make this look like a minute.
        expect(tracker.update(294, 1000, { now: 25000 })).toBe(1295);
    });

    it('forgets a resumed run\'s skipped-models burst', () => {
        const tracker = new ThroughputEtaTracker({
            windowMs: 60000,
            minSpanMs: 20000,
            minCompleted: 4,
        });

        // A resumed run first walks 282 already-populated folders in 25s.
        tracker.update(0, 1000, { now: 0 });
        tracker.update(282, 1000, { now: 25000 });

        // Downloads then settle at one model every two seconds.
        for (let index = 1; index <= 30; index += 1) {
            tracker.update(282 + index, 1000, { now: 25000 + index * 2000 });
        }

        // The 60s window now contains only the 30 post-resume downloads:
        // 688 remaining / 0.5 models/s = 1376s. A lifetime average would
        // still be showing roughly three minutes here.
        expect(tracker.update(312, 1000, { now: 85000 })).toBe(1376);
    });

    it('blends the phase baseline with the recent window', () => {
        const tracker = new ThroughputEtaTracker({
            windowMs: 30000,
            minSpanMs: 20000,
            minCompleted: 4,
            stableWeight: 0.7,
        });

        // 20 models in 20s, then 5 models in the next 20s.
        for (let index = 0; index <= 20; index += 1) {
            tracker.update(index, 100, { now: index * 1000 });
        }
        for (let index = 1; index <= 5; index += 1) {
            tracker.update(20 + index, 100, { now: 20000 + index * 4000 });
        }

        // Baseline: 25 models / 40s = 0.625/s. Window: 15 / 30s = 0.5/s.
        // Blend: 0.7 * 0.625 + 0.3 * 0.5 = 0.5875/s; 75 remaining = 128s.
        expect(tracker.update(25, 100, { now: 40000 })).toBe(128);
    });

    it('reports zero when the run is finished', () => {
        const tracker = new ThroughputEtaTracker();
        expect(tracker.update(100, 100, { now: 0 })).toBe(0);
    });

    it('does not estimate before the total is known', () => {
        const tracker = new ThroughputEtaTracker();
        expect(tracker.update(0, 0, { now: 0 })).toBeNull();
        expect(tracker.update(5, 0, { now: 5000 })).toBeNull();
    });

    it('keeps a baseline estimate when a long stall empties the window', () => {
        const tracker = new ThroughputEtaTracker({
            windowMs: 90000,
            minSpanMs: 20000,
            minCompleted: 4,
        });

        for (let index = 0; index <= 10; index += 1) {
            tracker.update(index, 100, { now: index * 5000 });
        }

        // The recent window has too little work to measure, but the phase
        // baseline still knows the run is slow: 10 models in 200s = 0.05/s,
        // so 90 remaining models take 1800s. The estimate recovers once
        // completions resume.
        expect(tracker.update(10, 100, { now: 200000 })).toBe(1800);
    });
});
