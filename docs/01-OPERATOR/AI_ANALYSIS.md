# AI Analysis — MuraveiVision PRO

> **Интеграция с Ollama для семантического анализа объектов и сцен.**

## Обзор

AI Analysis — система семантического анализа данных с использованием локальных LLM через Ollama. Позволяет задавать правила, получать alerts и автоматический анализ сессий.

## Архитектура AI analysis

```
AI Analysis Pipeline:
┌──────────────────┐
│  Detection Data  │ (objects, classes, coords)
└───────┬──────────┘
        │
        ▼
┌─────────────────────────────────────────┐
│  Context Building                       │
│  • Object list with metadata            │
│  • Scene description                    │
│  • Historical data                      │
│  • Rules configuration                  │
└───────┬─────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────┐
│  Ollama LLM Inference                   │
│  • llama3.2 / mistral-nemo              │
│  • Prompt with rules & context          │
│  • Structured output (JSON)             │
└───────┬─────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────┐
│  Rule Evaluation                        │
│  • Check against defined rules          │
│  • Generate alerts                      │
│  • Calculate scores                     │
└───────┬─────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────┐
│  Results & Alerts                       │
│  • Analysis report                      │
│  • Alerts (critical, warning, info)    │
│  • Recommendations                     │
│  • Session trace                        │
└─────────────────────────────────────────┘
```

## Правила (Rules)

### Создание правил

```
Rules Editor:
┌─────────────────────────────────────────┐
│  Rule name: [High ant density]          │
│                                         │
│  Condition:                             │
│  ☑ Ant count > [50]                    │
│  ☑ Per area > [10] per m²              │
│  ☑ Confidence > [0.80]                 │
│                                         │
│  Action:                                │
│  ☑ Alert: [HIGH DENSITY]               │
│  ☑ Level: [Warning]                    │
│  ☑ Score: [+15]                        │
│                                         │
│  ☑ Enable rule                          │
│                                         │
│  [Save] [Test] [Reset]                 │
└─────────────────────────────────────────┘
```

### Предопределённые правила

| Rule | Condition | Action | Level |
|------|-----------|--------|-------|
| **High density** | Ants > 50/m² | Alert | Warning |
| **New species** | Unknown class detected | Alert | Info |
| **Low activity** | Objects < 5/hr | Alert | Info |
| **Predator detected** | Spider/beetle with ants | Alert | Critical |
| **Colony healthy** | Queen + workers present | Score | +20 |
| **Colony stressed** | Workers < 10, no queen | Alert | Critical |

### Rule levels

| Level | Color | Priority | Response |
|-------|-------|----------|----------|
| **Critical** | 🔴 Red | 1 | Immediate action |
| **Warning** | 🟡 Yellow | 2 | Review required |
| **Info** | 🔵 Blue | 3 | For awareness |

## Alerts

### Панель alerts

```
Alerts Panel:
┌─────────────────────────────────────────┐
│  Active Alerts: 5                       │
│                                         │
│  ┌───────────────────────────────────┐  │
│  │ 🔴 CRITICAL                       │  │
│  │ Predator detected: Spider        │  │
│  │ Time: 10:23:45                    │  │
│  │ Location: IMG_0123.jpg           │  │
│  │ [👁 View] [🗑 Dismiss]           │  │
│  ├───────────────────────────────────┤  │
│  │ 🟡 WARNING                        │  │
│  │ High ant density: 67/m²          │  │
│  │ Time: 10:20:12                    │  │
│  │ Location: IMG_0120.jpg           │  │
│  │ [👁 View] [🗑 Dismiss]           │  │
│  ├───────────────────────────────────┤  │
│  │ 🔵 INFO                           │  │
│  │ New species: Unknown beetle      │  │
│  │ Time: 10:15:33                    │  │
│  │ Location: IMG_0115.jpg           │  │
│  │ [👁 View] [🗑 Dismiss]           │  │
│  └───────────────────────────────────┘  │
│                                         │
│  Filters: [All] [Critical] [Warning]   │
│           [Info] [Dismissed]           │
└─────────────────────────────────────────┘
```

### Alert details

```
Alert Details:
┌─────────────────────────────────────────┐
│  🔴 CRITICAL: Predator detected         │
│                                         │
│  Time: 2026-09-19 10:23:45             │
│  Source: IMG_0123.jpg                   │
│  Location: 55.7558N, 37.6173E          │
│                                         │
│  Details:                               │
│  • Spider detected near ant colony     │
│  • Distance: 15 cm from nearest ant    │
│  • Confidence: 0.92                    │
│  • Spider class: Araneomorphae         │
│                                         │
│  AI Analysis:                           │
│  "Spider detected in close proximity   │
│   to ant colony. Possible predation    │
│   behavior. Monitor for colony response."│
│                                         │
│  Recommendations:                       │
│  1. Monitor this location closely      │
│  2. Check colony health next visit     │
│  3. Consider relocation if frequent   │
│                                         │
│  [📸 View image] [📊 View stats]      │
│  [🗑 Dismiss] [📝 Add note]           │
└─────────────────────────────────────────┘
```

## Сессии анализа

### Session trace

```
Session Trace:
┌─────────────────────────────────────────┐
│  Session: field_session_01              │
│  Started: 10:00:00                      │
│  Duration: 2h 30m                       │
│                                         │
│  Timeline:                              │
│  ┌───────────────────────────────────┐  │
│  │ 10:00 │ Session start             │  │
│  │ 10:15 │ First detection: 12 objs  │  │
│  │ 10:23 │ ⚠️ High density alert     │  │
│  │ 10:45 │ 🐜 Queen detected         │  │
│  │ 11:00 │ AI analysis: Healthy      │  │
│  │ 11:30 │ 🔴 Predator alert         │  │
│  │ 12:00 │ Session end               │  │
│  └───────────────────────────────────┘  │
│                                         │
│  Summary:                               │
│  • Total objects: 247                   │
│  • Alerts: 5 (1 critical, 2 warning)   │
│  • AI score: 85/100                     │
│  • Health: Good                         │
│                                         │
│  [📄 Full report] [💾 Export]          │
└─────────────────────────────────────────┘
```

## Ollama интеграция

### Настройка Ollama

```
Ollama Configuration:
┌─────────────────────────────────────────┐
│  Ollama server:                         │
│  URL: [http://localhost:11434]         │
│  Status: [✓ Connected]                 │
│                                         │
│  Model:                                 │
│  ┌───────────────────────────────────┐  │
│  │ llama3.2  ✓                       │  │
│  │ mistral-nemo                      │  │
│  │ phi3-mini                         │  │
│  └───────────────────────────────────┘  │
│                                         │
│  Settings:                              │
│  Temperature: [0.7]                    │
│  Max tokens: [500]                     │
│  Timeout: [30] seconds                 │
│                                         │
│  [Test connection] [Save]              │
└─────────────────────────────────────────┘
```

### Prompt templates

```
Prompt Templates:
┌─────────────────────────────────────────┐
│  Template: [Species identification]     │
│                                         │
│  System prompt:                         │
│  "You are a myrmecology assistant.      │
│   Analyze the detected objects and      │
│   provide species-level identification  │
│   and ecological assessment."           │
│                                         │
│  User prompt:                           │
│  "Detected objects:                    │
│   {objects}                             │
│   Location: {location}                 │
│   Time: {time}                         │
│                                         │
│   Provide:                              │
│   1. Species identification             │
│   2. Colony health assessment           │
│   3. Risk factors                       │
│   4. Recommendations"                  │
│                                         │
│  [Save template] [Test]                │
└─────────────────────────────────────────┘
```

## AI Analysis output

### Структура ответа

```json
{
  "analysis": {
    "timestamp": "2026-09-19T10:30:00Z",
    "model": "llama3.2",
    "session_id": "field_session_01",
    "summary": {
      "total_objects": 247,
      "classes": {
        "ant_worker": 180,
        "ant_queen": 1,
        "ant_soldier": 25,
        "cricket": 35,
        "beetle": 6
      },
      "health_score": 85,
      "health_status": "Good"
    },
    "alerts": [
      {
        "level": "warning",
        "type": "high_density",
        "message": "Ant density 67/m² exceeds threshold",
        "confidence": 0.92
      }
    ],
    "recommendations": [
      "Monitor colony growth rate",
      "Check for predator activity",
      "Schedule next inspection in 2 weeks"
    ],
    "ecological_notes": "Healthy colony with queen present. " +
                       "Good worker-to-queen ratio. " +
                       "Some predator presence detected."
  }
}
```

### Health score

```
Colony Health Score:
┌─────────────────────────────────────────┐
│  Overall: 85/100 ██████████░░ Good     │
│                                         │
│  Components:                            │
│  ┌───────────────────────────────────┐  │
│  │ Queen present:     20/20         │  │
│  │ Worker count:      18/20         │  │
│  │ Soldier ratio:     15/15         │  │
│  │ Diversity:         12/15         │  │
│  │ Predator presence:  5/10 ⚠️     │  │
│  │ Environment:       15/20         │  │
│  └───────────────────────────────────┘  │
│                                         │
│  Trend: ↑ +5 from last session          │
└─────────────────────────────────────────┘
```

## API Reference

### Run AI analysis

```bash
# Analyze detection results
curl -X POST http://localhost:8000/api/ai/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "field_session_01",
    "objects": [
      {"class": "ant_worker", "confidence": 0.95, "bbox": [120,45,180,95]},
      {"class": "ant_queen", "confidence": 0.92, "bbox": [340,210,380,250]}
    ],
    "rules": ["high_density", "predator_detected", "colony_healthy"],
    "template": "species_identification"
  }'

# Response:
{
  "status": "success",
  "analysis": {
    "health_score": 85,
    "health_status": "Good",
    "alerts": [...],
    "recommendations": [...]
  }
}
```

### Create rule

```bash
# Add new rule
curl -X POST http://localhost:8000/api/ai/rules \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Low worker count",
    "condition": "ant_worker < 10",
    "action": "alert",
    "level": "critical",
    "message": "CRITICAL: Low worker count detected"
  }'
```

## Производительность

### Время анализа

| Модель | Время/сессия | VRAM | Точность |
|--------|--------------|------|----------|
| **phi3-mini** | 2s | 2 GB | Средняя |
| **llama3.2** | 5s | 4 GB | Высокая |
| **mistral-nemo** | 8s | 6 GB | Максимальная |

### Оптимизация

1. **Batch analysis** — группировка сессий
2. **Caching** — кэширование результатов
3. **Async** — неблокирующий анализ

## Troubleshooting

### Проблема: Ollama не подключается

```
Ollama connection failed
Solution:
1. Проверьте URL: http://localhost:11434
2. Проверьте запущен ли Ollama: ollama list
3. Проверьте модель: ollama pull llama3.2
4. Проверьте firewall
```

### Проблема: Медленный анализ

```
Slow AI analysis
Solution:
1. Используйте phi3-mini для скорости
2. Уменьшите max tokens
3. Уменьшите temperature
4. Проверьте GPU для Ollama
```

### Проблема: Неточный анализ

```
Inaccurate AI analysis
Solution:
1. Используйте llama3.2 или mistral-nemo
2. Увеличьте max tokens (1000+)
3. Улучшите prompt template
4. Добавьте more context
```

## Советы по эффективности

### Для точного анализа

1. llama3.2 или mistral-nemo
2. Detailed prompt template
3. All rules enabled
4. Max tokens 1000+

### Для быстрой оценки

1. phi3-mini
2. Basic rules only
3. Max tokens 250
4. Temperature 0.5

### Для отчётов

1. Full analysis с health score
2. Recommendations included
3. Session trace enabled
4. Export в JSON

## Следующие шаги

1. **[Training](./TRAINING.md)** — fine-tuning моделей
2. **[Reconstruction](./RECONSTRUCTION.md)** — 3D реконструкция
3. **[Network](./NETWORK.md)** — сетевое взаимодействие
4. **[Troubleshooting](./TROUBLESHOOTING.md)** — устранение неполадок

## Версия

- **Приложение:** v3.2.0
- **Дата:** 2026-09-19
