# Обучение и тонкая настройка YOLO-моделей

## Введение

MuraveiVision PRO поддерживает тонкую настройку (fine-tuning) моделей YOLO на пользовательских наборах данных. Данный раздел описывает полный цикл подготовки данных, обучения, оценки и развёртывания моделей.

## Подготовка данных

### Структура набора данных

Набор данных для обучения должен иметь следующую структуру:

```
dataset/
├── images/
│   ├── train/
│   │   ├── img001.jpg
│   │   ├── img002.jpg
│   │   └── ...
│   └── val/
│       ├── img010.jpg
│       ├── img011.jpg
│       └── ...
├── labels/
│   ├── train/
│   │   ├── img001.txt
│   │   ├── img002.txt
│   │   └── ...
│   └── val/
│       ├── img010.txt
│       ├── img011.txt
│       └── ...
└── data.yaml
```

**Правила организации:**

| Параметр | Значение |
|----------|----------|
| Соотношение train/val | 80/20 или 90/10 |
| Минимальное количество изображений | 100 на класс |
| Рекомендуемое количество | 500+ на класс |
| Формат изображений | JPG, PNG, BMP |
| Разрешение изображений | От 640x640 до 1920x1080 |
| Имена файлов | Без пробелов и спецсимволов |

### Аннотация объектов

Каждое изображение должно иметь соответствующий файл меток в формате YOLO:

```
# Формат строки в файле меток:
<class_id> <x_center> <y_center> <width> <height>
```

Все значения координат нормализованы относительно размеров изображения (0.0 — 1.0).

**Пример файла `img001.txt`:**

```
0 0.450 0.320 0.120 0.180
1 0.720 0.550 0.080 0.150
0 0.200 0.600 0.100 0.140
```

### Конфигурационный файл `data.yaml`

```yaml
# data.yaml — конфигурация набора данных

# Пути к каталогам (относительно расположения data.yaml)
path: ../datasets/muravei_custom  # базовый путь
train: images/train               # каталог обучающих изображений
val: images/val                   # каталог валидационных изображений

# Количество классов
nc: 3

# Имена классов (в порядке class_id)
names:
  0: beetle
  1: ant
  2: spider
```

## Форматы наборов данных

### Поддерживаемые форматы

MuraveiVision PRO поддерживает три основных формата аннотаций:

| Формат | Расширение | Описание |
|--------|-----------|----------|
| YOLO | `.txt` | Простая структура, нормализованные координаты |
| COCO | `.json` | Стандартный формат, поддерживает полигоны |
| Pascal VOC | `.xml` | Формат PASCAL VOC 2012 |

### Конвертация форматов

```python
# Конвертация COCO -> YOLO
from ultralytics.data.converter import convert_coco

convert_coco(
    dataset_dir="path/to/coco_dataset",
    use_segments=False,   # False для bbox, True для сегментации
    use_keypoints=False,  # False для bbox, True для keypoints
    single_cls=False,     # False для мультикласс
    flatten=True,         # Размещение всех файлов в корне
)
```

## Конфигурация обучения

### Пример файла конфигурации

```yaml
# model.yaml — конфигурация обучения

# Базовая модель
model: yolo26n.pt  # yolo26s.pt, yolo26m.pt, yolo26l.pt, yolo26n.pt

# Параметры данных
data: data.yaml
epochs: 100
batch: 16
imgsz: 640

# Оптимизация
lr0: 0.01              # начальный learning rate
lrf: 0.01              # конечный learning rate (lr0 * lrf)
momentum: 0.937        # SGD momentum/Adam beta1
weight_decay: 0.0005   # weight decay
warmup_epochs: 3.0
warmup_momentum: 0.8
warmup_bias_lr: 0.1

# Аугментации
hsv_h: 0.015           # augmentation HSV hue
hsv_s: 0.7             # augmentation HSV saturation
hsv_v: 0.4             # augmentation HSV value
degrees: 0.0           # rotation
translate: 0.1         # translation
scale: 0.5             # scale
flipud: 0.0            # flip up-down (0.0 = disabled)
fliplr: 0.5            # flip left-right
mosaic: 1.0            # mosaic augmentation
mixup: 0.0             # MixUp augmentation
copy_paste: 0.0        # copy-paste augmentation

# Разделение на GPU
device: 0               # GPU device (0, 1, 2, 3 или cpu)
workers: 8              # workers per GPU
project: runs/train     # директория сохранения
name: exp               # имя эксперимента
exist_ok: False         # перезаписывать существующие

# Сохранение
save_period: 10         # сохранять чекпоинт каждые N эпох
save_json: False        # сохранять результаты в COCO JSON
save_txt: True          # сохранять результаты в TXT
```

### Рекомендуемые параметры по размеру набора данных

| Размер набора данных | Модель | Epochs | Batch | Image Size |
|---------------------|--------|--------|-------|------------|
| < 500 изображений | YOLO26n | 50 | 8 | 640 |
| 500 — 2000 | YOLO26n/s | 100 | 16 | 640 |
| 2000 — 10000 | YOLO26s/m | 150 | 16 | 1280 |
| > 10000 | YOLO26m/l | 200 | 32 | 1280 |

## Трансферное обучение

### Использование предобученных весов

MuraveiVision PRO автоматически загружает предобученные веса при начале обучения:

```python
# Использование предобученной модели
from ultralytics import YOLO

# Загрузка предобученной модели
model = YOLO("yolo26n.pt")

# Тонкая настройка на собственном наборе данных
results = model.train(
    data="data.yaml",
    epochs=100,
    imgsz=640,
    batch=16,
    device=0,
    patience=20,       # остановка при отсутствии улучшений 20 эпох
    amp=True,          # автоматическое смешанное масштабирование
    optimizer="SGD",   # SGD или AdamW
)
```

### Перенос с другой задачи

```python
# Перенос с детекции на классификацию
model = YOLO("yolo26n.pt")
results = model.train(
    data="classification_data.yaml",
    model="yolov8n.pt",
    epochs=50,
    imgsz=224,
    task="classify",   # задача классификации
)
```

## Процесс обучения

### Диаграмма конвейера обучения

```
┌─────────────────────────────────────────────────────────────┐
│                    КОНВЕЙЕР ОБУЧЕНИЯ                         │
│                                                             │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│  │ Подготовка│───>│ Аугментация│───>│ Обучение │              │
│  │ данных    │    │ изображений│    │ (Epochs) │              │
│  └──────────┘    └──────────┘    └─────┬────┘              │
│         │                              │                     │
│         ▼                              ▼                     │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│  │ Аннотация │    │ Мозаика   │    │ Forward   │              │
│  │ (YOLO/COCO)│   │ MixUp    │    │ Backward │              │
│  └──────────┘    └──────────┘    │ Update   │              │
│                                  └─────┬────┘              │
│                                        │                     │
│                                        ▼                     │
│                                  ┌──────────┐              │
│                                  │ Валидация │              │
│                                  │ mAP@50/75 │              │
│                                  └─────┬────┘              │
│                                        │                     │
│                           ┌────────────┼────────────┐       │
│                           ▼            ▼            ▼       │
│                     ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│                     │ Сохранить │ │ Логирование│ │ Продолжить│  │
│                     │ чекпоинт │ │ TensorBoard│ │ обучение │  │
│                     └──────────┘ └──────────┘ └──────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Типичный процесс обучения

1. **Подготовка данных** — аннотация изображений, проверка формата
2. **Разделение данных** — train/val (80/20 или 90/10)
3. **Настройка конфигурации** — выбор модели, параметров обучения
4. **Запуск обучения** — мониторинг метрик в реальном времени
5. **Оценка результатов** — анализ метрик, выбор лучшей модели
6. **Развёртывание** — экспорт модели, интеграция в MuraveiVision PRO

## Мониторинг обучения

### Метрики обучения

Во время обучения отслеживаются следующие метрики:

| Метрика | Описание | Целевое значение |
|---------|----------|-----------------|
| `box/loss` | Потери бокса | Уменьшается к 0.05-0.15 |
| `cls/loss` | Потери классификации | Уменьшается к 0.1-0.5 |
| `dfl/loss` | Потери распределения | Уменьшается к 0.3-0.8 |
| `mAP50` | mAP при IoU=0.5 | > 0.7 для хорошего качества |
| `mAP50-95` | mAP при IoU=0.5:0.95 | > 0.5 для хорошего качества |
| `precision` | Точность | > 0.7 |
| `recall` | Полнота | > 0.6 |

### График потерь

```
Loss
 │
 │  box/loss  ───╲
 │               ╲
 │  cls/loss  ────╲
 │                 ╲
 │  dfl/loss  ─────╲
 │                  ╲
 │──────────────────╲───────────── Epoch
 0                   50
```

### TensorBoard мониторинг

```bash
# Запуск TensorBoard
tensorboard --logdir runs/train/exp

# Открыть в браузере
# http://localhost:6006
```

## Чекпоинты и возобновление обучения

### Проблема P2-3 и её решение

В версиях MuraveiVision PRO до v3.1.5 возникала проблема с возобновлением обучения:

```
# Ошибка при resume:
RuntimeError: Expected all tensors to be on the same device
```

**Решение (фикс P2-3):**

```python
# Правильное возобновление обучения
model = YOLO("runs/train/exp/weights/last.pt")

# Resume с сохранением состояния оптимизатора
results = model.train(
    resume=True,           # возобновить обучение
    data="data.yaml",
    epochs=200,            # общее количество эпох
    batch=16,
    device=0,
)
```

### Управление чекпоинтами

```
runs/train/exp/
├── weights/
│   ├── best.pt          # лучшая модель (по mAP)
│   ├── last.pt          # последняя сохранённая модель
│   ├── epoch001.pt      # чекпоинт эпохи 1
│   ├── epoch010.pt      # чекпоинт эпохи 10
│   └── epoch020.pt      # чекпоинт эпохи 20
├── results.png          # графики обучения
├── results.csv          # метрики в CSV
└── confusion_matrix.png # матрица ошибок
```

## Оценка и выбор модели

### Метрики оценки

| Метрика | Формула | Описание |
|---------|---------|----------|
| Precision | TP / (TP + FP) | Доля правильных предсказаний |
| Recall | TP / (TP + FN) | Доля найденных объектов |
| mAP50 | Среднее AP при IoU=0.5 | Основная метрика качества |
| mAP50-95 | Среднее AP IoU 0.5:0.95 | Строгая метрика качества |
| F1-Score | 2 * P * R / (P + R) | Гармоническое среднее P и R |

### Выбор лучшей модели

```python
# Анализ результатов
from ultralytics import YOLO

# Загрузка обучённой модели
model = YOLO("runs/train/exp/weights/best.pt")

# Оценка на валидационном наборе
metrics = model.val(data="data.yaml")

# Вывод метрик
print(f"mAP50: {metrics.box.map50:.4f}")
print(f"mAP50-95: {metrics.box.map:.4f}")
print(f"Precision: {metrics.box.mp:.4f}")
print(f"Recall: {metrics.box.mr:.4f}")

# Класс-специфичные метрики
for i, name in enumerate(["beetle", "ant", "spider"]):
    print(f"{name}: mAP50 = {metrics.box.maps[i]:.4f}")
```

## Развёртывание моделей

### Экспорт моделей

```python
# Экспорт в различные форматы
model = YOLO("runs/train/exp/weights/best.pt")

# ONNX (универсальный формат)
model.export(format="onnx", dynamic=True, simplify=True)

# OpenVINO (для Intel GPU/CPU)
model.export(format="openvino")

# TensorRT (для NVIDIA GPU)
model.export(format="engine", device=0)

# TorchScript
model.export(format="torchscript")
```

### Интеграция в MuraveiVision PRO

```python
# Загрузка модели в MuraveiVision PRO
from muraveivision import ModelManager

mm = ModelManager()

# Регистрация модели
mm.register_model(
    name="custom_beetle_detector",
    path="runs/train/exp/weights/best.onnx",
    format="onnx",
    classes=["beetle", "ant", "spider"],
    confidence_threshold=0.5,
    iou_threshold=0.45,
)

# Проверка работы
result = mm.detect(
    image_path="test_image.jpg",
    model_name="custom_beetle_detector",
)
```

## API для обучения

### POST /api/v1/train/start

Запуск обучения модели.

```json
// Request
{
    "model": "yolov8n.pt",
    "data": "/path/to/data.yaml",
    "epochs": 100,
    "batch": 16,
    "imgsz": 640,
    "device": 0,
    "project": "runs/train",
    "name": "custom_model_001",
    "pretrained": true,
    "optimizer": "SGD",
    "lr0": 0.01,
    "weight_decay": 0.0005,
    "warmup_epochs": 3,
    "patience": 20,
    "amp": true
}

// Response
{
    "status": "started",
    "experiment_id": "exp_20240115_001",
    "path": "/path/to/runs/train/custom_model_001",
    "message": "Training started successfully"
}
```

### GET /api/v1/train/status

Получение статуса обучения.

```json
// Response
{
    "experiment_id": "exp_20240115_001",
    "status": "training",
    "current_epoch": 45,
    "total_epochs": 100,
    "progress": 45.0,
    "metrics": {
        "box/loss": 0.0823,
        "cls/loss": 0.2341,
        "dfl/loss": 0.5120,
        "mAP50": 0.7234,
        "mAP50-95": 0.5612
    },
    "eta_seconds": 3600
}
```

### POST /api/v1/train/resume

Возобновление обучения.

```json
// Request
{
    "experiment_id": "exp_20240115_001",
    "resume": true,
    "total_epochs": 200
}

// Response
{
    "status": "resumed",
    "current_epoch": 45,
    "remaining_epochs": 155,
    "checkpoint": "runs/train/custom_model_001/weights/last.pt"
}
```

### GET /api/v1/train/results

Получение результатов обучения.

```json
// Response
{
    "experiment_id": "exp_20240115_001",
    "status": "completed",
    "best_metrics": {
        "mAP50": 0.8234,
        "mAP50-95": 0.6712,
        "precision": 0.8456,
        "recall": 0.7890
    },
    "class_metrics": {
        "beetle": {"mAP50": 0.89, "precision": 0.91, "recall": 0.87},
        "ant": {"mAP50": 0.78, "precision": 0.82, "recall": 0.74},
        "spider": {"mAP50": 0.79, "precision": 0.77, "recall": 0.79}
    },
    "best_model": "runs/train/custom_model_001/weights/best.pt",
    "training_duration": "02:34:15"
}
```

## Распространённые проблемы и решения

### Проблема: Низкий mAP

| Причина | Решение |
|---------|---------|
| Мало данных | Увеличить набор данных до 500+ изображений на класс |
| Плохие аннотации | Проверить корректность bounding boxes |
| Слишком мало эпох | Увеличить epochs до 100-200 |
| Неподходящая модель | Попробовать более ёмкую модель (s/m/l) |
| Дисбаланс классов | Использовать class weights или oversampling |

### Проблема: Переобучение (overfitting)

```yaml
# Признаки: train loss низкий, val loss растёт

# Решения:
# 1. Увеличить аугментации
hsv_h: 0.015
hsv_s: 0.7
hsv_v: 0.4
degrees: 15.0
translate: 0.1
scale: 0.5
mosaic: 1.0
mixup: 0.2

# 2. Увеличить weight decay
weight_decay: 0.001

# 3. Добавить early stopping
patience: 15
```

### Проблема: Ошибки памяти (OOM)

```yaml
# Решение: уменьшить batch size
batch: 8          # вместо 16
imgsz: 640        # уменьшить размер изображений
amp: true         # включить AMP (mixed precision)

# Альтернатива: gradient accumulation
accumulate: 4     # накопление градиентов (эффективный batch = 4 * 8 = 32)
```

### Проблема: Медленное обучение

| Оптимизация | Ускорение |
|-------------|-----------|
| AMP (mixed precision) | 1.5-2x |
| workers > 8 | 1.2-1.5x |
| imgsz 640 vs 1280 | 4x |
| YOLO26n vs YOLO26x | 3-5x |
| NVMe SSD | 1.5-2x |

### Проблема: Ошибки формата данных

```
# Ошибка: ValueError: Invalid label format
# Причина: координаты не в диапазоне [0, 1]

# Решение: проверить нормализацию координат
# Все значения должны быть в диапазоне 0.0 - 1.0
```

## Рекомендации поbest practices

1. **Начинайте с предобученных весов** — всегда используйте `pretrained: true`
2. **Используйте аугментации** — mosaic и mixup значительно улучшают обобщение
3. **Мониторьте TensorBoard** — следите за расхождением train/val потерь
4. **Сохраняйте чекпоинты** — используйте `save_period` для промежуточных сохранений
5. **Используйте early stopping** — параметр `patience` предотвращает переобучение
6. **Тестируйте на отдельных данных** — создайте holdout-набор для финальной оценки
7. **Экспортируйте в ONNX** — наиболее совместимый формат для развёртывания
