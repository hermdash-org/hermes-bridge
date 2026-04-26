/**
 * Advanced JavaScript example: A task queue system with
 * concurrency control, retry logic, and event handling.
 */

// ─── Event Emitter ────────────────────────────────────
class EventEmitter {
    constructor() {
        this._listeners = new Map();
    }

    on(event, callback) {
        if (!this._listeners.has(event)) {
            this._listeners.set(event, []);
        }
        this._listeners.get(event).push(callback);
        return this; // chainable
    }

    off(event, callback) {
        const cbs = this._listeners.get(event);
        if (cbs) {
            this._listeners.set(event, cbs.filter(cb => cb !== callback));
        }
        return this;
    }

    emit(event, ...args) {
        (this._listeners.get(event) || []).forEach(cb => {
            try { cb(...args); } catch (e) { console.error(`[EventEmitter] Error in '${event}' handler:`, e); }
        });
    }
}

// ─── Retry Helper ─────────────────────────────────────
async function withRetry(fn, { maxAttempts = 3, backoff = 1000, onRetry } = {}) {
    let lastError;
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            return await fn(attempt);
        } catch (err) {
            lastError = err;
            if (attempt < maxAttempts) {
                const delay = backoff * Math.pow(2, attempt - 1); // exponential backoff
                if (onRetry) onRetry({ attempt, error: err, nextDelay: delay });
                await sleep(delay);
            }
        }
    }
    throw lastError;
}

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

// ─── Task Queue ───────────────────────────────────────
class TaskQueue extends EventEmitter {
    constructor({ concurrency = 3, defaultRetries = 2 } = {}) {
        super();
        this._concurrency = concurrency;
        this._defaultRetries = defaultRetries;
        this._pending = [];
        this._active = 0;
        this._results = [];
        this._paused = false;
    }

    /** Add a task to the queue */
    add(name, taskFn, { retries = this._defaultRetries, priority = 0 } = {}) {
        const entry = { name, taskFn, retries, priority, status: 'pending' };
        // Insert sorted by priority (higher priority first)
        const idx = this._pending.findIndex(e => e.priority < priority);
        if (idx === -1) this._pending.push(entry);
        else this._pending.splice(idx, 0, entry);
        this.emit('task:added', entry);
        this._process();
        return this;
    }

    /** Pause queue processing */
    pause() { this._paused = true; this.emit('queue:paused'); return this; }

    /** Resume queue processing */
    resume() { this._paused = false; this.emit('queue:resumed'); this._process(); return this; }

    /** Wait until all tasks finish */
    async drain() {
        return new Promise(resolve => {
            if (this._active === 0 && this._pending.length === 0) return resolve(this._results);
            this.on('queue:drained', () => resolve(this._results));
        });
    }

    /** Internal processing loop */
    async _process() {
        while (this._pending.length > 0 && this._active < this._concurrency && !this._paused) {
            const task = this._pending.shift();
            this._active++;
            this.emit('task:started', task);
            this._execute(task).finally(() => {
                this._active--;
                this._process();
            });
        }
        if (this._active === 0 && this._pending.length === 0) {
            this.emit('queue:drained');
        }
    }

    /** Execute a single task with retry support */
    async _execute(task) {
        const startTime = Date.now();
        try {
            const result = await withRetry(task.taskFn, {
                maxAttempts: task.retries,
                backoff: 500,
                onRetry: ({ attempt, error, nextDelay }) => {
                    this.emit('task:retry', { name: task.name, attempt, error: error.message, nextDelay });
                }
            });
            task.status = 'completed';
            task.result = result;
            this._results.push(task);
            this.emit('task:completed', { name: task.name, result, duration: Date.now() - startTime });
        } catch (err) {
            task.status = 'failed';
            task.error = err.message;
            this._results.push(task);
            this.emit('task:failed', { name: task.name, error: err.message, duration: Date.now() - startTime });
        }
    }
}

// ─── Usage Demo ───────────────────────────────────────
async function main() {
    const queue = new TaskQueue({ concurrency: 2 });

    // Wire up event listeners
    queue.on('task:started', t => console.log(`  ▶ STARTED: ${t.name}`));
    queue.on('task:completed', ({ name, duration }) => console.log(`  ✔ DONE: ${name} (${duration}ms)`));
    queue.on('task:failed', ({ name, error }) => console.log(`  ✖ FAILED: ${name} — ${error}`));
    queue.on('task:retry', ({ name, attempt, error }) => console.log(`  ↻ RETRY: ${name} attempt #${attempt} — ${error}`));

    // Add a mix of successful and failing tasks
    queue.add('fetchUser',     () => fetchUser(42));
    queue.add('fetchPosts',    () => fetchPosts(42));
    queue.add('flakyService',  () => flakyService(), { retries: 3 });
    queue.add('cleanupCache',  () => sleep(300).then(() => 'cache cleared'), { priority: 10 });

    console.log('Processing…\n');
    const results = await queue.drain();
    console.log('\nAll done! Results:', JSON.stringify(results, null, 2));
}

// ─── Simulated async services ─────────────────────────
async function fetchUser(id) {
    await sleep(150);
    return { id, name: 'Alice', email: 'alice@example.com' };
}

async function fetchPosts(userId) {
    await sleep(400);
    return [
        { id: 1, userId, title: 'Hello World' },
        { id: 2, userId, title: 'Advanced JS Patterns' },
    ];
}

let flakyCalls = 0;
async function flakyService() {
    await sleep(200);
    flakyCalls++;
    if (flakyCalls < 3) throw new Error('Service unavailable');
    return 'flaky-but-ok';
}

main().catch(console.error);
