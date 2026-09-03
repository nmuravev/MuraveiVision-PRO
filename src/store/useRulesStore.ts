import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { DetectedObject } from '../types/muravei';

export type AlertSoundType = 'beep' | 'alarm' | 'none';

export type DetectionRule = {
  id: string;
  className: string;
  minConfidence: number;
  enabled: boolean;
  sound: boolean;
  soundType?: AlertSoundType;
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

export function playRuleAlertTone(
  soundType: AlertSoundType = 'beep',
  volume = 70,
) {
  if (soundType === 'none') return;
  try {
    const Context =
      window.AudioContext ??
      (window as typeof window & { webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext;
    if (!Context) return;
    const context = new Context();
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.frequency.value = soundType === 'alarm' ? 440 : 880;
    const amp = Math.max(0.001, Math.min(1, volume / 100)) * 0.08;
    gain.gain.setValueAtTime(amp, context.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + 0.18);
    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.start();
    oscillator.stop(context.currentTime + 0.18);
    oscillator.addEventListener('ended', () => void context.close());
  } catch {
    // Browser autoplay policy may reject sound before the first operator gesture.
  }
}
