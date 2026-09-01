import React, { useState } from 'react';
import { Bell, Trash2, Volume2 } from 'lucide-react';
import { useMuraveiStore } from '../../store/useMuraveiStore';
import { useRulesStore, playRuleAlertTone, type RuleSoundType } from '../../store/useRulesStore';

export const RulesPanel: React.FC = () => {
  const catalog = useMuraveiStore((state) => state.classCatalog);
  const rules = useRulesStore((state) => state.rules);
  const alerts = useRulesStore((state) => state.alerts);
  const addRule = useRulesStore((state) => state.addRule);
  const removeRule = useRulesStore((state) => state.removeRule);
  const toggleRule = useRulesStore((state) => state.toggleRule);
  const updateRule = useRulesStore((state) => state.updateRule);
  const clearAlerts = useRulesStore((state) => state.clearAlerts);
  const [className, setClassName] = useState('*');
  const [confidence, setConfidence] = useState(0.6);
  const [defaultSoundType, setDefaultSoundType] = useState<RuleSoundType>('beep');
  const [defaultVolume, setDefaultVolume] = useState(70);

  return (
    <section className="border border-[var(--dv-border)] bg-[var(--dv-bg-deep)] p-3 space-y-2">
      <div className="flex items-center gap-2 font-semibold">
        <Bell size={14} className="text-amber-400" />
        Правила и тревоги
      </div>
      <div className="flex gap-2">
        <select
          aria-label="Класс правила"
          className="min-w-0 flex-1 bg-[#1a1a1a] border border-[var(--dv-border)] px-2 py-1"
          value={className}
          onChange={(event) => setClassName(event.target.value)}
        >
          <option value="*">Любой класс</option>
          {catalog
            .filter((item) => item.enabled !== false)
            .map((item) => (
              <option key={item.id} value={item.name_en}>
                {item.name_ru || item.name_en}
              </option>
            ))}
        </select>
        <input
          aria-label="Минимальная уверенность"
          type="number"
          min="0.01"
          max="1"
          step="0.05"
          className="w-20 bg-[#1a1a1a] border border-[var(--dv-border)] px-2 py-1"
          value={confidence}
          onChange={(event) => setConfidence(Number(event.target.value))}
        />
        <button
          type="button"
          className="bg-amber-500 px-2 py-1 text-black disabled:opacity-40"
          onClick={() =>
            addRule({
              className,
              minConfidence: confidence,
              enabled: true,
              sound: defaultSoundType !== 'none',
              soundType: defaultSoundType,
              soundVolume: defaultVolume,
            })
          }
        >
          Добавить
        </button>
      </div>
      <div className="flex items-center gap-2 text-[10px] text-[var(--dv-text-muted)]">
        <span>Звук:</span>
        <select
          aria-label="Тип звука по умолчанию"
          className="bg-[#1a1a1a] border border-[var(--dv-border)] px-1 py-0.5"
          value={defaultSoundType}
          onChange={(e) => setDefaultSoundType(e.target.value as RuleSoundType)}
        >
          <option value="beep">beep</option>
          <option value="alarm">alarm</option>
          <option value="none">none</option>
        </select>
        <input
          aria-label="Громкость по умолчанию"
          type="range"
          min={0}
          max={100}
          className="flex-1"
          value={defaultVolume}
          onChange={(e) => setDefaultVolume(Number(e.target.value))}
        />
        <button
          type="button"
          className="px-1 py-0.5 bg-[#333] rounded-sm inline-flex items-center gap-1"
          title="Проверить звук"
          onClick={() => playRuleAlertTone(defaultSoundType, defaultVolume)}
        >
          <Volume2 size={12} /> Тест
        </button>
      </div>
      {rules.length === 0 ? (
        <p className="text-[10px] text-[var(--dv-text-muted)]">
          Правило подаёт звук и автоматически фиксирует совпадение в галерее.
        </p>
      ) : (
        <div className="space-y-1">
          {rules.map((rule) => {
            const soundType: RuleSoundType = rule.soundType ?? (rule.sound ? 'beep' : 'none');
            const volume = rule.soundVolume ?? 70;
            return (
            <div key={rule.id} className="flex items-center gap-2 text-[10px]">
              <input
                type="checkbox"
                checked={rule.enabled}
                onChange={() => toggleRule(rule.id)}
              />
              <span className="flex-1 truncate">
                {rule.className === '*' ? 'любой класс' : rule.className} ≥{' '}
                {rule.minConfidence.toFixed(2)}
              </span>
              <select
                aria-label="Тип звука правила"
                className="bg-[#1a1a1a] border border-[var(--dv-border)] px-1 py-0.5"
                value={soundType}
                onChange={(e) =>
                  updateRule(rule.id, {
                    soundType: e.target.value as RuleSoundType,
                    sound: e.target.value !== 'none',
                  })
                }
              >
                <option value="beep">beep</option>
                <option value="alarm">alarm</option>
                <option value="none">none</option>
              </select>
              <input
                aria-label="Громкость правила"
                type="range"
                min={0}
                max={100}
                className="w-16"
                value={volume}
                onChange={(e) => updateRule(rule.id, { soundVolume: Number(e.target.value) })}
              />
              <button
                type="button"
                aria-label="Проверить звук правила"
                title="Проверить"
                onClick={() => playRuleAlertTone(soundType, volume)}
              >
                <Volume2 size={12} />
              </button>
              <button
                type="button"
                aria-label="Удалить правило"
                onClick={() => removeRule(rule.id)}
              >
                <Trash2 size={12} />
              </button>
            </div>
            );
          })}
        </div>
      )}
      <div className="flex items-center justify-between text-[10px] text-[var(--dv-text-muted)]">
        <span>Срабатываний: {alerts.length}</span>
        <button type="button" onClick={clearAlerts} disabled={alerts.length === 0}>
          Очистить журнал
        </button>
      </div>
    </section>
  );
};
