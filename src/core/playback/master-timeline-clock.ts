/**
 * Master timeline clock — adapted from OpenReel concepts.
 * Single source of truth for monotonic media time while playing.
 */
export class MasterTimelineClock {
  private timeSec = 0;
  private rate = 1;
  private running = false;
  private lastPerf = 0;
  private listeners = new Set<(t: number) => void>();

  get currentTime(): number {
    return this.timeSec;
  }

  setRate(rate: number): void {
    this.rate = Math.max(0.1, Math.min(4, rate));
  }

  seek(time: number): void {
    this.timeSec = Math.max(0, time);
    this.emit();
  }

  play(): void {
    if (this.running) return;
    this.running = true;
    this.lastPerf = performance.now();
    const loop = (now: number) => {
      if (!this.running) return;
      const dt = ((now - this.lastPerf) / 1000) * this.rate;
      this.lastPerf = now;
      this.timeSec += dt;
      this.emit();
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
  }

  pause(): void {
    this.running = false;
  }

  subscribe(fn: (t: number) => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private emit(): void {
    for (const fn of this.listeners) fn(this.timeSec);
  }
}

export const masterClock = new MasterTimelineClock();
