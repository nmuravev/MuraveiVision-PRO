# Change Detection — MuraveiVision PRO

> **Сравнение "до/после" для анализа изменений в экосистемах.**

## Обзор

Change Detection — система сравнения двух наборов изображений ("до" и "после") для выявления изменений в окружающей среде: пожары, наводнения, рост колоний, воздействие деятельности.

## Архитектура change detection

```
Change Detection Pipeline:
┌──────────────┐    ┌──────────────┐
│  Before set  │    │  After set   │
│  (t1 images) │    │ (t2 images)  │
└──────┬───────┘    └──────┬───────┘
       │                   │
       ▼                   ▼
┌─────────────────────────────────────────┐
│         Image Matching                  │
│  • By filename                          │
│  • By GPS coordinates                  │
│  • By visual similarity                │
│  • Manual pairing                      │
└──────┬──────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│         Feature Extraction              │
│  • Object detection (both sets)        │
│  • Semantic segmentation               │
│  • Visual features (SIFT/SURF)         │
└──────┬──────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│         Change Analysis                 │
│  • Object appearance/disappearance     │
│  • Object size changes                 │
│  • Area coverage changes               │
│  • Visual difference (pixel-level)     │
└──────┬──────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│         Results                         │
│  • Change map                           │
│  • Change confidence                   │
│  • Change categories                   │
│  • Statistics                           │
└─────────────────────────────────────────┘
```

## Режимы сопоставления

### 1. By Filename

```
Matching: By Filename
┌─────────────────────────────────────────┐
│  Before:                                │
│  IMG_001.jpg  ←→  IMG_001.jpg          │
│  IMG_002.jpg  ←→  IMG_002.jpg          │
│                                         │
│  Rule: Exact filename match             │
│  Requirement: Same filenames in both    │
│               folders                   │
│                                         │
│  Matched: 89/89 pairs                   │
│  Unmatched: 0                           │
└─────────────────────────────────────────┘
```

### 2. By GPS

```
Matching: By GPS
┌─────────────────────────────────────────┐
│  Before:                                │
│  IMG_001.jpg  📍55.7558,37.6173        │
│  IMG_002.jpg  📍55.7559,37.6174        │
│                                         │
│  After:                                 │
│  IMG_101.jpg  📍55.7558,37.6173        │
│  IMG_102.jpg  📍55.7560,37.6175        │
│                                         │
│  Distance threshold: [10] meters        │
│                                         │
│  Matched: 85/89 pairs                   │
│  Unmatched: 4 (GPS too far)            │
└─────────────────────────────────────────┘
```

### 3. By Visual Similarity

```
Matching: By Visual Similarity
┌─────────────────────────────────────────┐
│  Algorithm: [SSIM] [Cosine] [L2]      │
│                                         │
│  Before: IMG_001.jpg                    │
│  ┌───────────────────────────────────┐  │
│  │  Most similar in After set:       │  │
│  │  IMG_101.jpg (98.2% similar)     │  │
│  │  IMG_102.jpg (87.5% similar)     │  │
│  │  IMG_103.jpg (65.3% similar)     │  │
│  └───────────────────────────────────┘  │
│                                         │
│  Matched: 92/92 pairs                   │
└─────────────────────────────────────────┘
```

### 4. Manual Pairing

```
Matching: Manual
┌─────────────────────────────────────────┐
│  Drag & drop pairs:                     │
│                                         │
│  Before:          After:                │
│  ┌──────────┐    ┌──────────┐          │
│  │ IMG_001  │──→│ IMG_101  │          │
│  └──────────┘    └──────────┘          │
│  ┌──────────┐    ┌──────────┐          │
│  │ IMG_002  │──→│ IMG_102  │          │
│  └──────────┘    └──────────┘          │
│                                         │
│  [Auto-match remaining]                │
└─────────────────────────────────────────┘
```

## Анализ изменений

### Категории изменений

| Категория | Описание | Пример |
|-----------|----------|--------|
| **Appearance** | Новый объект появился | Новая колония муравьёв |
| **Disappearance** | Объект исчез | Уничтожение гнезда |
| **Growth** | Объект вырос | Увеличение площади |
| **Shrink** | Объект уменьшился | Высыхание зоны |
| **Movement** | Объект переместился | Сдвиг конструкции |
| **Transformation** | Объект изменился | Пожар → пепел |

### Change map visualization

```
Change Map:
┌─────────────────────────────────────────┐
│  Before (t1)     After (t2)    Change  │
│  ┌──────┐       ┌──────┐       ┌────┐ │
│  │🐜🐜🐜│       │🐜🐜🐜│       │✅ │ │
│  │🐜 🐜 │  →    │🐜 🐜 │  →   │  │ │
│  │ 🐜🐜🐜│       │ 🐜🐜🐜│       │✅ │ │
│  └──────┘       └──────┘       └────┘ │
│                                         │
│  ┌──────┐       ┌──────┐       ┌────┐ │
│  │🦗🦗🦗│       │      │       │❌ │ │
│  │🦗 🦗 │  →    │      │  →   │  │ │
│  │🦗🦗🦗│       │      │       │❌ │ │
│  └──────┘       └──────┘       └────┘ │
│                                         │
│  Legend:                                │
│  ✅ Present in both                     │
│  ❌ Disappeared                         │
│  🆕 Appeared (new)                     │
│  ⚠️  Changed (size/shape)             │
└─────────────────────────────────────────┘
```

## Статистика изменений

### Summary report

```
Change Detection Results:
┌─────────────────────────────────────────┐
│  Pairs compared: 89                     │
│  Matched pairs: 85                      │
│                                         │
│  Changes detected:                      │
│  ┌────────────┬───────────┬──────────┐  │
│  │ Category   │ Count     │ % Change │  │
│  ├────────────┼───────────┼──────────┤  │
│  │ Stable     │ 62        │ 73%      │  │
│  │ New objects│ 18        │ 21%      │  │
│  │ Removed    │ 5         │ 6%       │  │
│  │ Changed    │ 12        │ 14%      │  │
│  └────────────┴───────────┴──────────┘  │
│                                         │
│  Object-level changes:                  │
│  • Ant colonies: +3 (new)              │
│  • Ant colonies: -1 (destroyed)        │
│  • Cricket count: -15% decrease        │
│  • Beetle count: +8% increase          │
│                                         │
│  Confidence: 0.89 (high)                │
│                                         │
│  [📊 Details] [💾 Export]              │
└─────────────────────────────────────────┘
```

### Per-pair analysis

```
Per-pair breakdown:
┌─────────────────────────────────────────┐
│  Pair | Before | After  | Change | %    │
│  ───────────────────────────────────────│
│  #001 |  12 ob |  11 ob |  -1   │ 8.3%│
│  #002 |   5 ob |   8 ob |  +3   │60.0%│
│  #003 |   8 ob |   8 ob |   0   │ 0.0%│
│  ...                                   │
│  #089 |   3 ob |   1 ob |  -2   │66.7%│
│                                         │
│  Avg change: +5.2%                      │
│  Max increase: +60% (#002)             │
│  Max decrease: -67% (#089)             │
└─────────────────────────────────────────┘
```

## Настройки анализа

### Configuration

```
Change Detection Settings:
┌─────────────────────────────────────────┐
│  Analysis:                              │
│  ☑ Object-level changes                │
│  ☑ Pixel-level differences             │
│  ☑ Area changes                        │
│  ☑ Semantic changes                    │
│                                         │
│  Sensitivity: [Medium] [High] [Low]    │
│  Min change size: [50] px              │
│  Min confidence: [0.70]                │
│                                         │
│  Output:                                │
│  ☑ Change map images                   │
│  ☑ Statistics CSV                       │
│  ☑ Per-pair JSON                        │
│  ☑ Heatmap overlay                     │
│                                         │
│  [Apply] [Run Analysis]                │
└─────────────────────────────────────────┘
```

### Sensitivity levels

| Level | Min change | False positives | Use case |
|-------|------------|-----------------|----------|
| **Low** | >20% | Минимум | Крупные изменения |
| **Medium** | >10% | Среднее | Полевая работа |
| **High** | >5% | Больше | Детальный анализ |

## Экспорт результатов

### Форматы экспорта

| Формат | Содержимое | Использование |
|--------|------------|---------------|
| **CSV** | Таблица изменений | Excel, анализ |
| **JSON** | Полный JSON | API, интеграции |
| **Change maps** | PNG изображения | Отчёты, презентации |
| **Heatmap** |热力图 | Визуализация зон |

### Пример JSON

```json
{
  "change_detection": {
    "version": "3.2.0",
    "timestamp": "2026-09-19T10:30:00Z",
    "pairs_compared": 89,
    "pairs_matched": 85,
    "changes": [
      {
        "pair_id": 1,
        "before": "IMG_001_before.jpg",
        "after": "IMG_001_after.jpg",
        "object_changes": {
          "appeared": 2,
          "disappeared": 0,
          "stable": 10,
          "changed_area": 1
        },
        "total_change_percent": 8.3,
        "confidence": 0.92
      }
    ]
  }
}
```

## Use cases

### 1. Оценка воздействия пожара

```
Fire impact assessment:
┌─────────────────────────────────────────┐
│  Before: Healthy forest                 │
│  After: Post-fire scene                 │
│                                         │
│  Results:                               │
│  • Area burned: 2.3 km²                │
│  • Object loss: -89%                   │
│  • New colonies: 0                     │
│  • Recovery estimate: 6-12 months      │
│                                         │
│  [📊 Full report] [💾 Export]          │
└─────────────────────────────────────────┘
```

### 2. Мониторинг колоний

```
Colony monitoring:
┌─────────────────────────────────────────┐
│  Month 1: 3 colonies detected          │
│  Month 2: 5 colonies (+2 new)          │
│  Month 3: 4 colonies (-1 destroyed)    │
│  Month 4: 7 colonies (+3 new)          │
│                                         │
│  Growth rate: +133% over 4 months      │
│  Health index: 0.85 (good)             │
│                                         │
│  [📈 Trend chart] [💾 Export]          │
└─────────────────────────────────────────┘
```

### 3. Сравнение методов обработки

```
Method comparison:
┌─────────────────────────────────────────┐
│  Method A vs Method B:                  │
│                                         │
│  Method A: 85 pairs matched             │
│  Method B: 89 pairs matched             │
│                                         │
│  Changes (A): 23 detected               │
│  Changes (B): 27 detected               │
│                                         │
│  Consensus: 19 changes (both methods)   │
│  Unique A: 4 changes                    │
│  Unique B: 8 changes                    │
│                                         │
│  Recommendation: Use Method B           │
└─────────────────────────────────────────┘
```

## Troubleshooting

### Проблема: Мало совпадений

```
Low match rate
Solution:
1. Увеличьте GPS threshold (20m вместо 10m)
2. Используйте visual similarity
3. Проверьте filenames
4. Попробуйте manual pairing
```

### Проблема: Ложные изменения

```
False change detection
Solution:
1. Увеличьте min confidence (0.80)
2. Увеличьте min change size (100 px)
3. Используйте higher sensitivity
4. Добавьте more reference points
```

### Проблема: Медленный анализ

```
Slow processing
Solution:
1. Уменьшите resolution
2. Отключите pixel-level analysis
3. Используйте object-level only
4. Уменьшите batch size
```

## Советы по эффективности

### Для точного анализа

1. GPS matching с threshold 10m
2. Visual similarity как fallback
3. High sensitivity для мелких изменений
4. Pixel-level + object-level combined

### Для быстрой оценки

1. Filename matching (самое быстрое)
2. Object-level only
3. Medium sensitivity
4. Low confidence threshold

### Для отчётов

1. Change map images в экспорт
2. Heatmap overlay
3. JSON для детальной статистики
4. CSV для Excel

## Следующие шаги

1. **[AI Analysis](./AI_ANALYSIS.md)** — семантический анализ
2. **[Training](./TRAINING.md)** — fine-tuning
3. **[Reconstruction](./RECONSTRUCTION.md)** — 3D реконструкция
4. **[Troubleshooting](./TROUBLESHOOTING.md)** — устранение неполадок

## Версия

- **Приложение:** v3.2.0
- **Дата:** 2026-09-19
