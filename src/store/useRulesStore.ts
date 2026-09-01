import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { DetectedObject } from '../types/muravei';

export type RuleSoundType = 'beep' | 'alarm' | 'none';

export type DetectionRule = {
  id: string;
  className: string;
  minConfidence: number;
  enabled: boolean;
  sound: boolean;
  /** Sound type for the alert. Defaults from `sound` (true -> 'beep'). */
  soundType?: RuleSoundType;
  /** Alert volume 0..100. Default 70. */
  soundVolume?: number;
};

export type DetectionAlert = {
  id: string;
  ruleId: string;
  className: string;
  confidence: number;
  sourceVideo: string;
  timeSec: number;
  createdAt: number;
};

type RulesState = {
  rules: DetectionRule[];
  alerts: DetectionAlert[];
  addRule: (rule: Omit<DetectionRule, 'id'>) => void;
  removeRule: (id: string) => void;
  toggleRule: (id: string) => void;
  updateRule: (id: string, patch: Partial<Omit<DetectionRule, 'id'>>) => void;
  clearAlerts: () => void;
  evaluate: (
    objects: DetectedObject[],
    sourceVideo: string,
    timeSec: number,
  ) => { object: DetectedObject; rule: DetectionRule }[];
};

const lastFired = new Map<string, number>();
const RULE_COOLDOWN_MS = 3_000;

export const useRulesStore = create<RulesState>()(
  persist(
    (set, get) => ({
      rules: [],
      alerts: [],
      addRule: (rule) =>
        set((state) => ({
          rules: [
            ...state.rules,
            {
              ...rule,
              id: crypto.randomUUID(),
              minConfidence: Math.max(0.01, Math.min(1, rule.minConfidence)),
            },
          ],
        })),
      removeRule: (id) =>
        set((state) => ({ rules: state.rules.filter((rule) => rule.id !== id) })),
      toggleRule: (id) =>
        set((state) => ({
          rules: state.rules.map((rule) =>
            rule.id === id ? { ...rule, enabled: !rule.enabled } : rule,
          ),
        })),
      updateRule: (id, patch) =>
        set((state) => ({
          rules: state.rules.map((rule) =>
            rule.id === id ? { ...rule, ...patch } : rule,
          ),
        })),
      clearAlerts: () => set({ alerts: [] }),
      evaluate: (objects, sourceVideo, timeSec) => {
        const now = Date.now();
        const matches: { object: DetectedObject; rule: DetectionRule }[] = [];
        for (const rule of get().rules) {
          if (!rule.enabled) continue;
          const object = objects.find(
            (candidate) =>
              (rule.className === '*' || candidate.class_en === rule.className) &&
              candidate.confidence >= rule.minConfidence,
          );
          if (!object) continue;
          const key = `${rule.id}:${sourceVideo}:${object.class_en}`;
          if (now - (lastFired.get(key) ?? 0) < RULE_COOLDOWN_MS) continue;
          lastFired.set(key, now);
          matches.push({ object, rule });
        }
        if (matches.length) {
          set((state) => ({
            alerts: [
              ...matches.map(({ object, rule }) => ({
                id: crypto.randomUUID(),
                ruleId: rule.id,
                className: object.class_en,
                confidence: object.confidence,
                sourceVideo,
                timeSec,
                createdAt: now,
              })),
              ...state.alerts,
            ].slice(0, 200),
          }));
        }
        return matches;
      },
    }),
    {
      name: 'muravei-detection-rules',
      partialize: (state) => ({ rules: state.rules, alerts: state.alerts }),
    },
  ),
);

export function playRuleAlertTone(soundType: RuleSoundType = 'beep', volume = 70) {
  if (soundType === 'none') return;
  try {
    const Context =
      window.AudioContext ??
      (window as typeof window & { webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext;
    if (!Context) return;
    const context = new Context();
    const gain = context.createGain();
    const vol = Math.max(0, Math.min(1, volume / 100));
    gain.connect(context.destination);

    if (soundType === 'alarm') {
      // Two-tone alarm: 660 Hz -> 880 Hz over ~0.5s.
      const osc = context.createOscillator();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(660, context.currentTime);
      osc.frequency.setValueAtTime(880, context.currentTime + 0.25);
      gain.gain.setValueAtTime(vol, context.currentTime);
      gain.gain.setValueAtTime(vol, context.currentTime + 0.45);
      gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + 0.5);
      osc.connect(gain);
      osc.start();
      osc.stop(context.currentTime + 0.5);
      osc.addEventListener('ended', () => void context.close());
    } else {
      // beep: 880 Hz, 0.10s
      const osc = context.createOscillator();
      osc.frequency.value = 880;
      gain.gain.setValueAtTime(vol, context.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + 0.1);
      osc.connect(gain);
      osc.start();
      osc.stop(context.currentTime + 0.1);
      osc.addEventListener('ended', () => void context.close());
    }
  } catch {
    // Browser autoplay policy may reject sound before the first operator gesture.
  }
}
