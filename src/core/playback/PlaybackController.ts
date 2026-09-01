// src/core/playback/PlaybackController.ts
// OpenReel-inspired playback controller wired to timeline store actions

import type { Timeline, Action } from '../types/muravei';

export class PlaybackController {
  private timeline: Timeline;
  private isPlaying = false;
  private rafId: number | null = null;
  private lastTs = 0;
  private onTick?: (time: number) => void;

  constructor(timeline: Timeline, onTick?: (time: number) => void) {
    this.timeline = timeline;
    this.onTick = onTick;
  }

  play(): void {
    if (this.isPlaying) return;
    this.isPlaying = true;
    this.lastTs = performance.now();
    const loop = (now: number) => {
      if (!this.isPlaying) return;
      const dt = (now - this.lastTs) / 1000;
      this.lastTs = now;
      this.seek(this.timeline.currentTime + dt);
      if (this.timeline.currentTime >= this.timeline.duration) {
        this.pause();
        return;
      }
      this.rafId = requestAnimationFrame(loop);
    };
    this.rafId = requestAnimationFrame(loop);
  }

  pause(): void {
    this.isPlaying = false;
    if (this.rafId !== null) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
  }

  seek(time: number): void {
    this.timeline.currentTime = Math.max(0, Math.min(time, this.timeline.duration));
    this.onTick?.(this.timeline.currentTime);
  }

  dispatch(action: Action): void {
    switch (action.type) {
      case 'timeline/setCurrentTime':
        this.seek(action.payload.time);
        break;
      case 'timeline/setInPoint':
        this.timeline.inPoint = action.payload.time;
        break;
      case 'timeline/setOutPoint':
        this.timeline.outPoint = action.payload.time;
        break;
      case 'timeline/clearInOutPoints':
        this.timeline.inPoint = undefined;
        this.timeline.outPoint = undefined;
        break;
      default:
        console.log('Action dispatched:', action.type);
    }
  }

  getTimeline(): Timeline {
    return this.timeline;
  }

  isPlayingState(): boolean {
    return this.isPlaying;
  }
}
