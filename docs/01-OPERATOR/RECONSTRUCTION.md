# 3D-реконструкция

## Обзор методов

MuraveiVision PRO поддерживает несколько методов 3D-реконструкции, каждый из которых оптимизирован для различных сценариев использования.

### Диаграмма конвейера реконструкции

```
┌──────────────────────────────────────────────────────────────────┐
│                    КОНВЕЙЕР 3D-РЕКОНСТРУКЦИИ                      │
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐          │
│  │ Загрузка    │    │ Предобработка│    │ Выбор метода │          │
│  │ изображений │───>│ (калибровка, │───>│ (COLMAP/DA3/ │          │
│  │ и видео     │    │ нормализация)│    │ GSplat/     │          │
│  └─────────────┘    └─────────────┘    │ Flight3D)   │          │
│                                        └──────┬──────┘          │
│                                               │                  │
│                    ┌──────────────────────────┼──────────────┐   │
│                    ▼                          ▼              ▼   │
│            ┌─────────────┐          ┌─────────────┐ ┌────────┐ │
│            │ COLMAP SfM  │          │ DA3 Depth   │ │GSplat  │ │
│            │ Structure   │          │ Backend     │ │Gaussian│ │
│            │ from Motion │          │ (Depth      │ │Splatting│ │
│            └──────┬──────┘          │ Anything 3) │ └───┬────┘ │
│                   │                  └──────┬──────┘     │      │
│                   ▼                         ▼            ▼      │
│            ┌─────────────┐          ┌─────────────┐ ┌────────┐ │
│            │ Point Cloud │          │ Depth Map   │ │Volume  │ │
│            │ Generation  │          │ Estimation  │ │Fusion  │ │
│            └──────┬──────┘          └─────────────┘ └───┬────┘ │
│                   │                                      │      │
│                   ▼                                      ▼      │
│            ┌─────────────┐                    ┌─────────────┐   │
│            │ Mesh        │                    │ Flight3D    │   │
│            │ Generation  │                    │ Aerial      │   │
│            │ (Poisson/   │                    │ Reconstruction│  │
│            │  TSDF)      │                    └─────────────┘   │
│            └──────┬──────┘                                          │
│                   │                                                  │
│                   ▼                                                  │
│            ┌─────────────┐                                          │
│            │ Post-       │                                          │
│            │ processing  │                                          │
│            │ (smoothing, │                                          │
│            │  texturing) │                                          │
│            └──────┬──────┘                                          │
│                   │                                                  │
│                   ▼                                                  │
│            ┌─────────────┐                                          │
│            │ Export      │                                          │
│            │ (OBJ/PLY/   │                                          │
│            │  GLB/FBX)   │                                          │
│            └─────────────┘                                          │
└──────────────────────────────────────────────────────────────────┘
```

## Сравнение методов реконструкции

| Метод | Описание | Точность | Скорость | VRAM | Сценарий |
|-------|----------|----------|----------|------|----------|
| **COLMAP SfM** | Structure from Motion | Высокая | Средняя | 4-8 ГБ | Стандартная 3D |
| **DA3 Dense** | Depth Anything 3 | Очень высокая | Быстрая | 6-12 ГБ | Детальная геометрия |
| **GSplat** | Gaussian Splatting | Высокая | Быстрая | 8-16 ГБ | Фотореализм |
| **Flight3D** | Аэрофотосъёмка | Средняя | Быстрая | 4-8 ГБ | Дроны, aerial |

## COLMAP Structure from Motion (SfM)

### Описание

COLMAP — это стандартный инструмент для Structure from Motion. Он выполняет:

1. **Feature Detection** — обнаружение ключевых точек (AKAZE, SIFT, SuperPoint)
2. **Feature Matching** — сопоставление ключевых точек между изображениями
3. **Bundle Adjustment** — оптимизация камер и точек
4. **Point Cloud Generation** — генерация облака точек

### Настройка COLMAP

```yaml
# colmap_config.yaml
sift:
  num_threads: 8
  max_num_features: 16384
  enhancement: true
  max_orientation_diffs: 10

matching:
  max_num_matches: 8192
  max_error: 4.0
  min_error: 2.0
  geometry_check: true

sfm:
  tri_min_angle: 1.5
  tri_max_angle: 160.0
  max_reg_trials: 8

bundle_adjustment:
  ref_focal_length: true
  ref_principal_point: false
  ref_aspect_ratio: false
  ref_extra_params: true
  max_num_iterations: 512
  max_time: 3600
```

### Требования к изображениям для COLMAP

| Параметр | Минимум | Рекомендация |
|----------|---------|-------------|
| Количество изображений | 15 | 30-100 |
| Перекрытие кадров | 60% | 70-80% |
| Разрешение | 640x480 | 1920x1080+ |
| Фокусное расстояние | Известно | Зафиксировано |
| Освещение | Равномерное | Постоянное |

### Запуск COLMAP через API

```bash
# POST /api/v1/reconstruct/colmap

# Request
{
    "method": "colmap",
    "images_dir": "/data/scene_photos/",
    "camera_model": "PINHOLE",
    "feature_type": "SIFT",
    "max_num_features": 16384,
    "matching_strategy": "spatial",
    "tri_min_angle": 1.5,
    "max_reg_trials": 8,
    "ref_focal_length": true,
    "ref_principal_point": false,
    "output_format": "ply"
}

# Response
{
    "status": "started",
    "job_id": "recon_colmap_20240115_001",
    "estimated_time_minutes": 25,
    "stages": {
        "feature_detection": "pending",
        "feature_matching": "pending",
        "sfm": "pending",
        "point_cloud": "pending"
    }
}
```

## DA3 Dense Backend (Depth Anything 3)

### Описание

**Новое в версии v3.2.0.** DA3 Dense Backend использует модель Depth Anything 3 для оценки глубины из одиночных изображений. Этот метод обеспечивает высокую точность глубины без необходимости множественных ракурсов.

### Архитектура Depth Anything 3

```
                    ┌─────────────────────────────┐
                    │    Depth Anything 3 (DA3)    │
                    ├─────────────────────────────┤
                    │                             │
                    │  ┌─────────────────────┐    │
                    │  │   Image Encoder     │    │
                    │  │  (ViT-B / ViT-L)    │    │
                    │  └────────┬────────────┘    │
                    │           │                  │
                    │           ▼                  │
                    │  ┌─────────────────────┐    │
                    │  │   Depth Decoder     │    │
                    │  │  (Multi-scale FPN)  │    │
                    │  └────────┬────────────┘    │
                    │           │                  │
                    │           ▼                  │
                    │  ┌─────────────────────┐    │
                    │  │  Depth Refinement   │    │
                    │  │  (CRF / MLP)        │    │
                    │  └────────┬────────────┘    │
                    │           │                  │
                    │           ▼                  │
                    │  ┌─────────────────────┐    │
                    │  │   Depth Map Output   │    │
                    │  │   (1-channel, 0-1)   │    │
                    │  └─────────────────────┘    │
                    └─────────────────────────────┘
```

### Объяснение оценки глубины

Depth Anything 3 использует следующую архитектуру:

1. **Image Encoder (ViT)** — извлекает многоуровневые признаки изображения
2. **Depth Decoder (FPN)** — объединяет признаки разных масштабов
3. **Depth Refinement** — уточняет глубину с помощью CRF или MLP

**Входные данные:**
- Изображение: RGB, 518x518 (или кратно 14)
- Модель: `depth_anything_vit_b` (114M параметров) или `depth_anything_vit_l` (345M параметров)

**Выходные данные:**
- Карта глубины: 1 канал, нормализована [0, 1]
- Относительная глубина (не метрическая)

### Настройка DA3

```yaml
# da3_config.yaml
depth_anything:
  model_size: "vit_b"        # vit_b или vit_l
  pretrained: true
  device: "cuda"
  dtype: "float16"

preprocessing:
  resize: 518
  mean: [0.485, 0.456, 0.406]
  std: [0.229, 0.224, 0.225]

postprocessing:
  normalize: true
  scale_method: "silhouette"  # silhouette, minmax, robust
  outlier_threshold: 0.01

fusion:
  multi_view: true
  consistency_check: true
  outlier_removal: true
  smoothing_sigma: 1.0
```

### Запуск DA3 через API

```bash
# POST /api/v1/reconstruct/da3

# Request
{
    "method": "da3",
    "images_dir": "/data/scene_photos/",
    "model_size": "vit_b",
    "scale_method": "silhouette",
    "multi_view_fusion": true,
    "smoothing_sigma": 1.0,
    "output_format": "ply",
    "output_dir": "/data/reconstructions/da3_output/"
}

# Response
{
    "status": "started",
    "job_id": "recon_da3_20240115_001",
    "estimated_time_minutes": 15,
    "stages": {
        "depth_estimation": "in_progress",
        "multi_view_fusion": "pending",
        "point_cloud": "pending",
        "mesh_generation": "pending"
    },
    "progress": {
        "current": 12,
        "total": 45,
        "percentage": 26.7
    }
}
```

### VRAM бюджет для DA3

| Модель | Разрешение | VRAM | Время (1 изображение) |
|--------|-----------|------|----------------------|
| DA3 ViT-B | 518x518 | ~4 ГБ | 0.5 сек |
| DA3 ViT-B | 1024x1024 | ~6 ГБ | 1.5 сек |
| DA3 ViT-L | 518x518 | ~8 ГБ | 1.2 сек |
| DA3 ViT-L | 1024x1024 | ~12 ГБ | 3.0 сек |

**Оптимизация VRAM:**

```yaml
# Опции снижения потребления VRAM
optimization:
  dtype: "float16"        # half precision
  batch_size: 1           # обработка по одному
  cache_depth: true       # кэшировать карты глубины
  reuse_depth: true       # переиспользовать при multi-view
```

## GSplat Gaussian Splatting

### Описание

GSplat реализует метод 3D Gaussian Splatting для фотореалистичной рендеринга сцен. В отличие от традиционных методов, 3DGS не требует явной сетки (mesh).

### Архитектура 3DGS

```
┌──────────────────────────────────────────────┐
│            3D Gaussian Splatting              │
│                                              │
│  ┌──────────┐    ┌──────────┐                │
│  │ 3D Gauss │    │ Camera   │                │
│  │ ians     │◄──>│ Projections│              │
│  │ (N штук) │    │          │                │
│  │          │    │          │                │
│  │ position │    │ View     │                │
│  │ scale    │    │ Matrix   │                │
│  │ rotation │    │          │                │
│  │ opacity  │    └──────────┘                │
│  │ color    │         │                      │
│  └──────────┘         │                      │
│       │               ▼                      │
│       │       ┌──────────────┐               │
│       │       │ Rasterization│               │
│       │       │ (Splatting)  │               │
│       │       └──────┬───────┘               │
│       │              │                       │
│       ▼              ▼                       │
│  ┌──────────────────────────┐                │
│  │   Training Loop          │                │
│  │  • Loss: L1 + D-SSIM     │                │
│  │  • Adaptive densification│                │
│  │  • Pruning low-opacity   │                │
│  └──────────────────────────┘                │
└──────────────────────────────────────────────┘
```

### Настройка GSplat

```yaml
# gsplat_config.yaml
gsplat:
  num_gaussians_init: 100000
  num_iterations: 3000
  resolution: 1024
  
  # Loss weights
  loss:
    lambda_dssim: 0.2
    lambda_l1: 1.0
    
  # Adaptive densification
  densification:
    interval: 100
    gamma: 0.0002
    opacity_threshold: 0.005
    scale_threshold: 0.01
    
  # Pruning
  pruning:
    interval: 3000
    opacity_threshold: 0.005
    
  # Camera
  camera:
    near_plane: 0.01
    far_plane: 100.0
```

### Требования

| Компонент | Минимум | Рекомендация |
|-----------|---------|-------------|
| GPU VRAM | 8 ГБ | 12-24 ГБ |
| RAM | 16 ГБ | 32 ГБ |
| Изображений | 20 | 50-200 |
| Время обучения | 30 мин | 1-4 часа |

## Flight3D для аэрофотосъёмки

### Описание

Flight3D оптимизирован для обработки данных аэрофотосъёмки с дронов. Учитывает:

- Геометрию полёта (высота, наклон, курс)
- Ортофотопроекцию
- Цифровую модель рельефа (DEM)

### Настройка Flight3D

```yaml
# flight3d_config.yaml
flight3d:
  method: "sfm_dense"
  camera_model: "RADIAL"
  
  # Полёт
  flight:
    altitude: 50.0          # высота в метрах
    ground_sample_distance: 0.02  # GSD в м/пиксель
    overlap_side: 0.8       # боковое перекрытие
    overlap_forward: 0.7    # продольное перекрытие
    
  # Dense reconstruction
  dense:
    method: "mvs"
    num_disparity_levels: 192
    patch_size: 5
    patch_step: 1
```

## Генерация облака точек и визуализация

### Pipeline генерации

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Camera      │     │  Back-       │     │  Point Cloud │
│  Parameters  │────>│  projection  │────>│  Generation  │
│  (intrinsics,│     │  to 3D       │     │  (Triangul.) │
│   extrinsics) │     └──────────────┘     └──────┬───────┘
└──────────────┘                                  │
                                                  ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Point Cloud │     │  Filtering   │     │  Visualization│
│  Export      │<────│  (outliers,  │<────│  (colors,    │
│  (PLY/OBJ)   │     │  smoothing)  │     │   density)   │
└──────────────┘     └──────────────┘     └──────────────┘
```

### Параметры облака точек

| Параметр | Описание | Значение по умолчанию |
|----------|----------|---------------------|
| `density` | Плотность точек | 1.0 |
| `color_mode` | Режим цвета | `rgb` |
| `normalize` | Нормализация координат | `false` |
| `outlier_removal` | Удаление выбросов | `true` |
| `statistical_filter` | Статистическая фильтрация | `true` |
| `radius_outlier` | Радиус для outlier removal | 5 |
| `min_neighbors` | Мин. соседей для фильтра | 10 |

## Генерация сетки (Mesh)

### Методы генерации

| Метод | Описание | Качество | Скорость |
|-------|----------|----------|----------|
| **Poisson** | Поиссоновская реконструкция | Высокое | Медленно |
| **TSDF Fusion** | SDF-фьюжн | Высокое | Средне |
| **Delaunay** | Делоне-триангуляция | Среднее | Быстро |
| **Marching Cubes** | Лестничные кубы | Среднее | Быстро |

### Настройка генерации сетки

```yaml
# mesh_config.yaml
mesh:
  method: "poisson"
  depth: 11              # глубина для Poisson
  scale: 1.1             # масштаб
  samples: 1.0           # плотность сэмплов
  
  # TSDF параметры
  tsdf:
    voxel_size: 0.005
    truncation_factor: 10
    weight_threshold: 1.0
  
  # Post-processing
  smoothing:
    iterations: 5
    lambda: 0.5
    clip: 0.01
```

## Форматы экспорта

### Поддерживаемые форматы

| Формат | Расширение | Описание | Поддержка |
|--------|-----------|----------|-----------|
| **OBJ** | `.obj` | Wavefront OBJ | Вершины, грани, нормали, текстуры |
| **PLY** | `.ply` | Polygon File Format | Точки, цвета, сетка |
| **GLB** | `.glb` | GL Transmission Format | 3D-сцены, текстуры, анимация |
| **FBX** | `.fbx` | Autodesk FBX | Профессиональный 3D-формат |
| **STL** | `.stl` | Stereolithography | Только геометрия (3D-печать) |
| **XYZ** | `.xyz` | Простой формат точек | Только координаты |

### Параметры экспорта

```yaml
# export_config.yaml
export:
  format: "glb"
  
  # OBJ параметры
  obj:
    include_normals: true
    include_texcoords: true
    include_materials: true
    triangulate: true
  
  # PLY параметры
  ply:
    binary: true
    include_colors: true
    include_normals: true
  
  # GLB параметры
  glb:
    compress: true
    texture_size: 2048
    lod_levels: 3
  
  # Общие
  general:
    up_axis: "Y_UP"
    units: "meters"
    merge_vertices: true
    vertex_threshold: 0.0001
```

## Настройки качества и компромиссы

### Уровни качества

| Уровень | Точность | Скорость | VRAM | Детализация |
|---------|----------|----------|------|-------------|
| **Low** | Низкая | Очень быстрая | 2-4 ГБ | Грубая |
| **Medium** | Средняя | Быстрая | 4-8 ГБ | Умеренная |
| **High** | Высокая | Средняя | 8-16 ГБ | Детальная |
| **Ultra** | Максимальная | Медленная | 16+ ГБ | Фотореалистичная |

### Компромиссы

```
┌────────────────────────────────────────────┐
│           КАЧЕСТВО vs СКОРОСТЬ               │
│                                            │
│  Высокое качество                           │
│       │                                    │
│       │  • Больше эпох                      │
│       │  • Меньше batch size                │
│       │  • Высокое разрешение               │
│       │  • Детальная сетка                   │
│       │                                    │
│       │           ┌─── Высокая скорость     │
│       │          │                         │
│       │     Среднее                         │
│       │    качество                         │
│       │                                  │
│       │                             ┌───── Быстро,        │
│       │                            │    низкое качество   │
│       ▼                            │                      │
│  Низкое качество                  └─────                  │
│                                            │              │
└────────────────────────────────────────────┘
```

## API для реконструкции

### GET /api/v1/reconstruct/methods

Получение списка доступных методов.

```json
// Response
{
    "methods": [
        {
            "id": "colmap",
            "name": "COLMAP SfM",
            "description": "Structure from Motion с COLMAP",
            "requires_calibration": true,
            "min_images": 15,
            "vram_min_gb": 4,
            "vram_recommended_gb": 8
        },
        {
            "id": "da3",
            "name": "DA3 Dense (Depth Anything 3)",
            "description": "Глубина из одиночных изображений",
            "requires_calibration": false,
            "min_images": 1,
            "vram_min_gb": 6,
            "vram_recommended_gb": 12
        },
        {
            "id": "gsplat",
            "name": "GSplat Gaussian Splatting",
            "description": "Фотореалистичный рендеринг",
            "requires_calibration": true,
            "min_images": 20,
            "vram_min_gb": 8,
            "vram_recommended_gb": 16
        },
        {
            "id": "flight3d",
            "name": "Flight3D",
            "description": "Аэрофотосъёмка и дроны",
            "requires_calibration": true,
            "min_images": 10,
            "vram_min_gb": 4,
            "vram_recommended_gb": 8
        }
    ]
}
```

### POST /api/v1/reconstruct/start

Запуск реконструкции.

```json
// Request
{
    "method": "da3",
    "images_dir": "/data/scene_photos/",
    "model_size": "vit_b",
    "output_format": "ply",
    "output_dir": "/data/reconstructions/",
    "mesh": {
        "enabled": true,
        "method": "poisson",
        "depth": 10
    },
    "quality": "high"
}

// Response
{
    "status": "started",
    "job_id": "recon_da3_20240115_001",
    "estimated_time_minutes": 45,
    "stages": {
        "depth_estimation": "pending",
        "point_cloud": "pending",
        "mesh_generation": "pending",
        "export": "pending"
    }
}
```

### GET /api/v1/reconstruct/status

Статус реконструкции.

```json
// Response
{
    "job_id": "recon_da3_20240115_001",
    "status": "processing",
    "current_stage": "point_cloud",
    "progress": {
        "percentage": 65.0,
        "current": 29,
        "total": 45
    },
    "metrics": {
        "points_generated": 2500000,
        "mesh_faces": 1200000,
        "processing_time_seconds": 1800
    }
}
```

### GET /api/v1/reconstruct/results

Результаты реконструкции.

```json
// Response
{
    "job_id": "recon_da3_20240115_001",
    "status": "completed",
    "output_files": {
        "point_cloud": "/data/reconstructions/da3_output/point_cloud.ply",
        "mesh": "/data/reconstructions/da3_output/mesh.obj",
        "depth_maps": "/data/reconstructions/da3_output/depth/",
        "camera_params": "/data/reconstructions/da3_output/cameras.json"
    },
    "statistics": {
        "num_points": 3250000,
        "num_faces": 1500000,
        "bounding_box": {
            "min": [-2.5, -1.0, -3.0],
            "max": [2.5, 3.0, 3.0]
        },
        "file_size_mb": 450
    }
}
```

### POST /api/v1/reconstruct/export

Экспорт в указанный формат.

```json
// Request
{
    "job_id": "recon_da3_20240115_001",
    "format": "glb",
    "options": {
        "compress": true,
        "texture_size": 2048
    }
}

// Response
{
    "status": "exported",
    "output_file": "/data/reconstructions/da3_output/output.glb",
    "file_size_mb": 120,
    "download_url": "/api/v1/download/recon_da3_20240115_001.glb"
}
```

## Рекомендации

1. **Для интерьеров** — используйте DA3 Dense для быстрой и точной реконструкции
2. **Для экстерьеров** — COLMAP SfM с множеством ракурсов
3. **Для фотореализма** — GSplat Gaussian Splatting
4. **Для дронов** — Flight3D с учётом геометрии полёта
5. **Для экономии VRAM** — обрабатывайте по частям и кэшируйте промежуточные результаты
6. **Для максимальной точности** — комбинируйте COLMAP + DA3 (SfM + Dense)
