# AI Analyst (Ollama) — MuraveiVision PRO

> **AI-анализ: Ollama integration, rules, alerts, session trace.**

## Overview

AI Analyst provides semantic analysis using local LLMs via Ollama.

## Supported Models

| Model | VRAM | Speed | Accuracy |
|-------|------|-------|----------|
| phi3-mini | 2 GB | 2s | Medium |
| llama3.2 | 4 GB | 5s | High |
| mistral-nemo | 6 GB | 8s | Maximum |

## Rules Engine

Define custom rules for alerts.

```yaml
rules:
  - name: "High density"
    condition: "ant_count > 50"
    action: "alert"
    level: "warning"
```

## Alerts

| Level | Color | Priority |
|-------|-------|----------|
| Critical | 🔴 Red | 1 |
| Warning | 🟡 Yellow | 2 |
| Info | 🔵 Blue | 3 |

## Health Score

Colony health scoring from 0-100.

```
Health: 85/100 ██████████░░ Good
├── Queen present: 20/20
├── Worker count: 18/20
├── Soldier ratio: 15/15
└── Predator presence: 5/10 ⚠️
```

## Версия

- **Приложение:** v3.2.0
