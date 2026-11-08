/**
 * Throughput estimator for example-image downloads.
 *
 * The download manager reports progress in completed *models*, and models are
 * not equal units of work: one may own two images, the next twenty. Two
 * failure modes follow from that:
 *
 * - A lifetime average (`completed / elapsed`) is stable but keeps a slow
 *   startup, a skip burst, or an old throughput phase in the estimate for the
 *   rest of the run.
 * - A short window follows the current phase but overreacts to one slow model
 *   and turns a 30-second stall into a wildly pessimistic ETA.
 *
 * This tracker blends both: a baseline rate measured from the start of the
 * current phase (reset after a skip burst or a pause) and a recent window.
 * The baseline provides the stability the old formula had; the window lets
 * the estimate move when throughput genuinely changes. A large jump in the
 * completed counter (a resumed run marking hundreds of already-populated
 * folders as processed) restarts the phase, so the skip burst is never counted
 * as download throughput.
 */
export class ThroughputEtaTracker {
    /**
     * @param {object} [options]
     * @param {number} [options.windowMs] Recent-rate window.
     * @param {number} [options.minSpanMs] Minimum observed span before estimating.
     * @param {number} [options.minCompleted] Minimum completed units in a window.
     * @param {number} [options.stableWeight] Share of the baseline rate (0..1).
     * @param {number} [options.burstThreshold] Counter jump treated as a skip burst.
     * @param {number} [options.burstRate] Minimum jump rate (units/s) for a burst.
     */
    constructor({
        windowMs = 120000,
        minSpanMs = 20000,
        minCompleted = 4,
        stableWeight = 0.7,
        burstThreshold = 20,
        burstRate = 5,
    } = {}) {
        this.windowMs = windowMs;
        this.minSpanMs = minSpanMs;
        this.minCompleted = minCompleted;
        this.stableWeight = stableWeight;
        this.burstThreshold = burstThreshold;
        this.burstRate = burstRate;
        this.reset();
    }

    reset() {
        this.samples = [];
        this.baseline = null;
        this.lastCompleted = null;
        this.pendingReset = false;
    }

    /**
     * Feed the latest counters.
     *
     * Call once per progress poll, including polls where `completed` did not
     * change: the unchanged sample is what lets a stall age the window.
     *
     * @param {number} completed Completed unit count (models).
     * @param {number} total Total unit count (models).
     * @param {object} [options]
     * @param {number} [options.now] Current wall-clock time in ms.
     * @param {boolean} [options.running] Whether work is currently advancing.
     * @returns {number|null} Remaining seconds, or null while warming up.
     */
    update(completed, total, { now = Date.now(), running = true } = {}) {
        if (!Number.isFinite(completed) || !Number.isFinite(total)) {
            return null;
        }
        if (total <= 0) {
            // The status endpoint reports total=0 until the scanner list has
            // been assembled; there is nothing to estimate against yet.
            return null;
        }

        if (!running) {
            // Wall-clock time spent paused must never be mistaken for a slow
            // download. The next running sample starts a fresh phase.
            this.pendingReset = true;
            return null;
        }
        if (this.pendingReset) {
            this.reset();
        }

        if (this.lastCompleted !== null && completed < this.lastCompleted) {
            // A new run reused the manager: do not mix two counter series.
            this.reset();
        }
        this.lastCompleted = completed;

        const last = this.samples[this.samples.length - 1];
        if (last && completed > last.completed) {
            const delta = completed - last.completed;
            const elapsedSeconds = Math.max(0, now - last.t) / 1000;
            const jumpRate = elapsedSeconds > 0 ? delta / elapsedSeconds : Infinity;
            if (delta >= this.burstThreshold && jumpRate >= this.burstRate) {
                // A skip burst advances the counter without download work.
                this.samples = [];
                this.baseline = null;
            }
        }

        if (this.samples.length && this.samples[this.samples.length - 1].t === now) {
            this.samples[this.samples.length - 1].completed = completed;
        } else {
            this.samples.push({ t: now, completed });
        }

        if (this.baseline === null) {
            this.baseline = { t: now, completed };
        }

        const cutoff = now - this.windowMs;
        while (this.samples.length > 2 && this.samples[0].t < cutoff) {
            this.samples.shift();
        }

        if (total <= completed) {
            return 0;
        }

        const windowRate = this._rate(
            completed - this.samples[0].completed,
            now - this.samples[0].t
        );
        const stableRate = this._rate(
            completed - this.baseline.completed,
            now - this.baseline.t
        );

        let rate = null;
        if (windowRate !== null && stableRate !== null) {
            rate = this.stableWeight * stableRate
                + (1 - this.stableWeight) * windowRate;
        } else {
            rate = stableRate ?? windowRate;
        }
        if (!(rate > 0)) {
            return null;
        }
        return Math.ceil((total - completed) / rate);
    }

    _rate(done, elapsedMs) {
        if (done < this.minCompleted || elapsedMs < this.minSpanMs) {
            return null;
        }
        return done / (elapsedMs / 1000);
    }
}
