# Class Catalog — MuraveiVision PRO

> **Формат каталога классов и примеры.**

## Format

```yaml
# config/class_catalog.yaml
classes:
  - id: 0
    name: "ant_worker"
    display: "Ant Worker"
    color: "#FF0000"
    category: "ant"
  - id: 1
    name: "ant_queen"
    display: "Ant Queen"
    color: "#FF00FF"
    category: "ant"
```

## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | int | Yes | Class ID |
| name | string | Yes | Internal name |
| display | string | Yes | Display name |
| color | string | Yes | Hex color |
| category | string | No | Group category |

## Версия

- **Приложение:** v3.2.0
