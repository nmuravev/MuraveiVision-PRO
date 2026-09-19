# Устранение неполадок

## Введение

Данный раздел содержит руководство по диагностике и устранению распространённых проблем, с которыми может столкнуться оператор MuraveiVision PRO.

## Логи и файлы журналов

### Расположение файлов логов

| Файл | Путь | Описание |
|------|------|----------|
| **Основной лог** | `/var/log/muraveivision/app.log` | Общие события приложения |
| **Лог детекции** | `/var/log/muraveivision/detection.log` | Ошибки детекции и сегментации |
| **Лог обучения** | `/var/log/muraveivision/training.log` | Процесс обучения моделей |
| **Лог реконструкции** | `/var/log/muraveivision/reconstruction.log` | 3D-реконструкция |
| **Лог сети** | `/var/log/muraveivision/network.log` | Сетевые события |
| **Лог GPU** | `/var/log/muraveivision/gpu.log` | Состояние GPU |
| **Логи ошибок** | `/var/log/muraveivision/error.log` | Только ошибки и критические события |
| **Логи доступа** | `/var/log/muraveivision/access.log` | HTTP-запросы |

### Просмотр логов

```bash
# Последние 100 строк основного лога
tail -n 100 /var/log/muraveivision/app.log

# Фильтрация по ключевым словам
grep -i "error\|exception\|fail" /var/log/muraveivision/app.log

# Мониторинг в реальном времени
tail -f /var/log/muraveivision/app.log

# Поиск по дате
grep "2024-01-15 10:" /var/log/muraveivision/app.log

# Размер логов
ls -lh /var/log/muraveivision/

# Архивные логи
ls -lh /var/log/muraveivision/archive/
```

## Дерево диагностики

### Общая схема диагностики

```
                    ┌──────────────┐
                    │  Проблема    │
                    │  обнаружена  │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ Детекция │ │Сегментация│ │Реконстр. │
        │  проблемы │ │  проблемы │ │  проблемы│
        └────┬─────┘ └────┬─────┘ └────┬─────┘
             │            │            │
    ┌────────┼────────┐   │            │
    ▼        ▼        ▼   ▼            ▼
 Низкий   Ложные   Медл.  Нет        Ошибка
 счётчик  positive загрузка масок   памяти
    │        │        │    │            │
    ▼        ▼        ▼    ▼            ▼
 Проверить Проверить Проверить Проверить Проверить
 модель   аннотации GPU   калибровку VRAM
   │        │        │    │            │
    ▼        ▼        ▼    ▼            ▼
 Исправить Исправить Оптимиз. Исправить Исправить
 параметры данные настройки  данные   настройки
```

## Проблемы детекции

### Низкое количество обнаруженных объектов

| Причина | Диагностика | Решение |
|---------|-------------|---------|
| Низкий порог уверенности | `confidence < threshold` | Уменьшить `confidence_threshold` |
| Неверная модель | Модель не обучена на нужных объектах | Переобучить модель на новом датасете |
| Плохое качество изображения | Размытие, шум, неправильная экспозиция | Улучшить условия съёмки |
| Неправильный размер изображений | `imgsz != model training size` | Привести к размеру обучения |
| GPU не используется | Проверить `device` | Указать `device: 0` |

```bash
# Проверка использования GPU
nvidia-smi

# Проверка параметров детекции
cat /etc/muraveivision/detection.yaml | grep -A5 "thresholds"

# Тест на одном изображении
muraveivision detect --image test.jpg --model best.pt --verbose
```

### Ложные срабатывания (False Positives)

| Причина | Диагностика | Решение |
|---------|-------------|---------|
| Высокий порог уверенности | Много предсказаний с `conf > 0.3` | Увеличить `confidence_threshold` до 0.5-0.7 |
| Нет данных о негативных примерах | Модель не видела фоновых изображений | Добавить negative examples в датасет |
| Переобучение | `train mAP >> val mAP` | Увеличить аугментации, уменьшить epochs |
| Неподходящая модель | Модель слишком ёмкая для задачи | Попробовать более простую модель |

```yaml
# Оптимизация порогов
detection:
  thresholds:
    confidence: 0.6       # увеличить с 0.5
    iou: 0.45             # увеличить с 0.4
    
  # Дополнительные фильтры
  filters:
    min_area: 100         # минимальная площадь bbox
    max_area: 50000       # максимальная площадь bbox
    aspect_ratio_min: 0.1 # минимальное соотношение сторон
    aspect_ratio_max: 10.0 # максимальное соотношение сторон
```

### Медленная детекция

| Метрика | Нормально | Проблема | Решение |
|---------|-----------|----------|---------|
| FPS (YOLO26n) | 50-200 | < 30 | Проверить GPU |
| FPS (YOLO26x) | 20-80 | < 10 | Переключиться на n/s модель |
| Время на кадр | < 20ms | > 50ms | AMP, меньший imgsz |

```bash
# Диагностика производительности
muraveivision benchmark --model best.pt --device 0 --imgsz 640

# Проверка загрузки GPU
watch -n 1 nvidia-smi

# Проверка температуры GPU
nvidia-smi --query-gpu=temperature.gpu --format=csv
```

## Проблемы сегментации

### Неточные маски

| Причина | Диагностика | Решение |
|---------|-------------|---------|
| Плохие аннотации | Маски не совпадают с объектами | Переаннотировать данные |
| Недостаточно данных | Мало примеров на класс | Добавить изображения |
| Неподходящая модель | Модель сегментации слишком простая | Использовать YOLO26-seg m/l |
| Низкое разрешение | Детали теряются | Увеличить `imgsz` до 1280 |

### Нестабильная пропускная способность (propagation)

```
Проблема: Маски "прыгают" между кадрами

Причины:
├── Низкая частота кадров
├── Быстрое движение объектов
├── Неправильные параметры tracking
└── Шум в изображении

Решения:
├── Увеличить max_age в tracking
├── Уменьшить min_hits
├── Добавить temporal smoothing
└── Улучшить качество изображения
```

```yaml
# Настройки tracking для стабильности
tracking:
  max_age: 15            # увеличить с 5
  min_hits: 3            # увеличить с 1
  iou_threshold: 0.5     # увеличить с 0.3
  confidence_threshold: 0.6  # увеличить
  
  # Temporal smoothing
  smoothing:
    enabled: true
    window_size: 5
    method: "kalman"     # kalman или exponential
```

## Ошибки пакетной обработки (Batch Scan)

### Неподдерживаемый формат файла

```
Ошибка: ValueError: Unsupported image format: .webp

Причина: Формат не поддерживается движком обработки

Решение:
1. Конвертировать в поддерживаемый формат (JPG, PNG)
2. Или добавить поддержку в конфигурацию

# Конвертация
convert input.webp output.jpg

# Добавление формата в конфигурацию
image_formats:
  supported: [jpg, jpeg, png, bmp, tiff, webp]
```

### Недостаточно места на диске

```bash
# Проверка свободного места
df -h

# Проверка использования диска по каталогам
du -sh /data/muraveivision/*/

# Очистка временных файлов
rm -rf /tmp/muraveivision_*
rm -rf /data/muraveivision/cache/*

# Мониторинг в реальном времени
watch -n 5 'df -h / && du -sh /data/muraveivision/*/'
```

### Таймауты пакетной обработки

| Параметр | Значение по умолчанию | Рекомендуемое |
|----------|----------------------|---------------|
| `batch_timeout` | 300 сек | 600 сек для больших батчей |
| `max_batch_size` | 100 | Зависит от GPU |
| `per_image_timeout` | 30 сек | 60 сек для сегментации |

```yaml
# Настройки пакетной обработки
batch:
  timeout: 600           # увеличить с 300
  max_size: 200          # увеличить с 100
  per_image_timeout: 60  # увеличить с 30
  
  # Обработка ошибок
  error_handling:
    skip_on_error: true   # пропускать ошибки
    log_failed: true      # логировать неудачные
    max_failures: 10      # макс. ошибок на батч
```

## Проблемы AI-анализа

### Подключение к Ollama

```bash
# Проверка статуса Ollama
systemctl status ollama

# Проверка порта
curl http://localhost:11434/api/tags

# Перезапуск Ollama
systemctl restart ollama

# Проверка доступных моделей
ollama list

# Загрузка модели
ollama pull mistral
```

### Медленный инференс

| Причина | Диагностика | Решение |
|---------|-------------|---------|
| Модель не загружена | `model not found` | `ollama pull <model>` |
| CPU вместо GPU | Нет GPU acceleration | Установить CUDA |
| Маленькая модель | Низкое качество | Использовать larger модель |
| Конфликт ресурсов | Высокая CPU/GPU нагрузка | Закрыть другие приложения |

```bash
# Проверка GPU для Ollama
OLLAMA_GPU=all ollama serve

# Проверка доступной памяти
nvidia-smi --query-gpu=memory.total,memory.free --format=csv

# Оптимизация Ollama
cat ~/.ollama/config.json
{
    "num_gpu": 100,
    "main_gpu": 0,
    "low_vram": false,
    "f16": true
}
```

## Проблемы 3D-реконструкции

### Недостаточное перекрытие изображений

```
Проблема: COLMAP не находит достаточно общих точек

Признаки:
├── Мало matched features
├── Мало зарегистрированных камер
└── Разреженное облако точек

Решения:
├── Увеличить перекрытие до 70-80%
├── Использовать больше изображений
├── Уменьшить max_num_features для COLMAP
└── Использовать DA3 Dense как альтернативу
```

### Плохое освещение

```
Проблема: Неравномерное освещение снижает качество реконструкции

Признаки:
├── Тёмные области без деталей
├── Пересвеченные области
└── Резкие тени

Решения:
├── Равномерное освещение сцены
├── HDR-съёмка (несколько экспозиций)
├── Избегать прямых бликов
└── Использовать DA3 (устойчив к освещению)
```

### Ошибки генерации сетки

```bash
# Проверка облака точек
meshlabserver -i point_cloud.ply -o mesh.obj -s mesh_filter.mlx

# Проверка валидности mesh
python -c "
import trimesh
mesh = trimesh.load('mesh.obj')
print(f'Valid: {mesh.is_valid}')
print(f'Faces: {len(mesh.faces)}')
print(f'Vertices: {len(mesh.vertices)}')
"
```

## Оптимизация производительности

### Советы по оптимизации

| Область | Оптимизация | Прирост |
|---------|-------------|---------|
| **Детекция** | AMP (mixed precision) | 1.5-2x |
| **Детекция** | imgsz 640 вместо 1280 | 4x |
| **Детекция** | YOLO26n вместо v8x | 3-5x |
| **Сегментация** | Пропуск кадров | 2-4x |
| **Реконструкция** | Кэширование depth maps | 1.5-2x |
| **Общее** | NVMe SSD для данных | 1.5-2x |
| **Общее** | workers=16 вместо 8 | 1.2-1.5x |

### GPU оптимизация

```yaml
# GPU конфигурация
gpu:
  # Mixed precision
  amp: true
  dtype: "float16"
  
  # Batch processing
  batch_size: 16
  workers: 16
  
  # Memory management
  memory_fraction: 0.8   # использовать 80% VRAM
  allow_growth: true     # выделять память по мере необходимости
  
  # Caching
  cache_models: true
  cache_features: true
```

## Устранение проблем GPU

### CUDA ошибки

```bash
# Проверка версии CUDA
nvcc --version

# Проверка совместимости драйвера
nvidia-smi

# Проверка доступных GPU
python -c "import torch; print(torch.cuda.device_count())"

# Тест CUDA
python -c "
import torch
x = torch.randn(3, 3).cuda()
print('CUDA works:', x.device)
"
```

### Ошибки Out of Memory (OOM)

```
Ошибка: RuntimeError: CUDA out of memory

Решения:
├── 1. Уменьшить batch size
├── 2. Уменьшить imgsz
├── 3. Использовать AMP (float16)
├── 4. Очистить кэш GPU
├── 5. Закрыть другие приложения
└── 6. Использовать gradient accumulation
```

```python
# Очистка GPU кэша
import torch
torch.cuda.empty_cache()

# Gradient accumulation для увеличения effective batch size
# При batch=2 и accumulate=8: effective_batch = 16
model.train(
    batch=2,
    accumulate=8,
    amp=True
)

# Проверка использования VRAM
nvidia-smi --query-gpu=memory.used,memory.total --format=csv
```

### Проблемы с драйвером

```bash
# Проверка версии драйвера
nvidia-smi --query-gpu=driver_version --format=csv

# Перезапуск драйвера (требует root)
sudo rmmod nvidia_uvm
sudo rmmod nvidia_drm
sudo rmmod nvidia
sudo modprobe nvidia

# Проверка ошибок ядра
dmesg | grep -i nvidia

# Установка актуального драйвера
sudo apt install nvidia-driver-535
```

## Справочник кодов ошибок

| Код | Категория | Описание | Решение |
|-----|-----------|----------|---------|
| **E001** | Детекция | Модель не найдена | Проверить путь к модели |
| **E002** | Детекция | Неверный формат модели | Конвертировать в ONNX |
| **E003** | Детекция | GPU OOM | Уменьшить batch/imgsz |
| **E004** | Детекция | Неверные входные данные | Проверить формат изображения |
| **E005** | Сегментация | Маска не сгенерирована | Проверить модель сегментации |
| **E006** | Сегментация | Несоответствие размеров | Привести к размеру модели |
| **E007** | Обучение | Неверный формат данных | Проверить data.yaml |
| **E008** | Обучение | Недостаточно данных | Добавить изображения |
| **E009** | Обучение | Ошибка памяти | Уменьшить batch/epochs |
| **E010** | Обучение | Разрыв соединения | Проверить GPU |
| **E020** | Реконструкция | COLMAP не найден | Установить COLMAP |
| **E021** | Реконструкция | Мало изображений | Добавить больше кадров |
| **E022** | Реконструкция | Нет перекрытия | Изменить стратегию съёмки |
| **E023** | Реконструкция | Ошибка памяти VRAM | Уменьшить resolution |
| **E024** | Реконструкция | DA3 модель не загружена | Загрузить Depth Anything 3 |
| **E030** | Сеть | Невозможно подключиться | Проверить Hub-сервер |
| **E031** | Сеть | JWT токен истёк | Обновить токен |
| **E032** | Сеть | Нет разрешений | Проверить role/permissions |
| **E033** | Сеть | Превышен лимит | Уменьшить частоту запросов |
| **E040** | Файлы | Недостаточно места | Освободить диск |
| **E041** | Файлы | Недостаточно прав | Проверить permissions |
| **E042** | Файлы | Формат не поддерживается | Конвертировать файл |
| **E050** | Ollama | Сервер недоступен | Проверить ollama serve |
| **E051** | Ollama | Модель не найдена | `ollama pull <model>` |
| **E052** | Ollama | Ошибка инференса | Проверить модель |

## Диагностические команды

### Общая диагностика системы

```bash
#!/bin/bash
# diagnostic.sh — полная диагностика системы

echo "=== MuraveiVision PRO Diagnostic ==="
echo ""

echo "1. System Information"
echo "--------------------"
uname -a
echo ""

echo "2. GPU Information"
echo "------------------"
nvidia-smi --query-gpu=name,driver_version,memory.total,memory.used,temperature.gpu --format=csv
echo ""

echo "3. CUDA Version"
echo "---------------"
nvcc --version 2>/dev/null || echo "CUDA not installed"
echo ""

echo "4. Python Environment"
echo "---------------------"
python --version
pip show ultralytics 2>/dev/null | grep Version
pip show torch 2>/dev/null | grep Version
echo ""

echo "5. Disk Usage"
echo "-------------"
df -h /
du -sh /var/log/muraveivision/ 2>/dev/null || echo "Logs not found"
echo ""

echo "6. Process Status"
echo "-----------------"
systemctl status muraveivision 2>/dev/null || echo "Service not running"
systemctl status ollama 2>/dev/null || echo "Ollama not running"
echo ""

echo "7. Network Status"
echo "-----------------"
curl -s http://localhost:8080/api/v1/health 2>/dev/null || echo "API not responding"
echo ""

echo "8. Recent Errors"
echo "----------------"
grep -i "error\|exception" /var/log/muraveivision/app.log 2>/dev/null | tail -20
echo ""

echo "=== Diagnostic Complete ==="
```

### Быстрая диагностика GPU

```bash
#!/bin/bash
# gpu_check.sh — быстрая проверка GPU

echo "GPU Status:"
nvidia-smi --query-gpu=name,temperature.gpu,memory.used,memory.total,power.draw --format=csv,noheader,nounits

echo ""
echo "CUDA Test:"
python -c "
import torch
if torch.cuda.is_available():
    print(f'GPU: {torch.cuda.get_device_name(0)}')
    print(f'Memory: {torch.cuda.get_device_properties(0).total_mem / 1024**3:.1f} GB')
    print(f'CUDA: {torch.version.cuda}')
else:
    print('CUDA NOT AVAILABLE')
"
```

## Бенчмарки для справки

### Производительность детекции

| Модель | GPU | imgsz | FPS | mAP50 |
|--------|-----|-------|-----|-------|
| YOLO26n | RTX 3060 | 640 | 150 | 0.45 |
| YOLO26n | RTX 3060 | 1280 | 40 | 0.48 |
| YOLO26s | RTX 3060 | 640 | 80 | 0.52 |
| YOLO26m | RTX 3060 | 640 | 35 | 0.58 |
| YOLO26n | RTX 4090 | 640 | 400 | 0.45 |
| YOLO26s | RTX 4090 | 640 | 200 | 0.52 |

### Производительность сегментации

| Модель | GPU | imgsz | FPS | mAP50 |
|--------|-----|-------|-----|-------|
| YOLO26n-seg | RTX 3060 | 640 | 100 | 0.42 |
| YOLO26s-seg | RTX 3060 | 640 | 55 | 0.50 |
| YOLO26m-seg | RTX 3060 | 640 | 25 | 0.56 |

### Производительность реконструкции

| Метод | GPU | Изображений | Время | Точность |
|-------|-----|-------------|-------|----------|
| COLMAP SfM | RTX 3060 | 50 | 15 мин | Средняя |
| DA3 Dense | RTX 3060 | 50 | 5 мин | Высокая |
| GSplat | RTX 3060 | 50 | 2 часа | Очень высокая |
| Flight3D | RTX 3060 | 30 | 10 мин | Средняя |

## Когда обращаться в поддержку

### Предварительная проверка

Перед обращением в поддержку выполните следующие шаги:

```
1. [ ] Проверить логи на наличие ошибок
2. [ ] Выполнить diagnostic.sh
3. [ ] Проверить версию MuraveiVision PRO
4. [ ] Собрать информацию о системе (GPU, RAM, OS)
5. [ ] Подготовить примеры (изображения, конфиги)
6. [ ] Описать шаги воспроизведения
```

### Информация для обращения

```
При обращении в поддержку предоставьте:

1. Версия MuraveiVision PRO: _______________
2. Версия Python: _________________________
3. Версия PyTorch: _______________________
4. GPU модель: ___________________________
5. Операционная система: __________________
6. Код ошибки: ___________________________
7. Логи (файл или вывод): ________________
8. Шаги воспроизведения: __________________
9. Ожидаемое поведение: ___________________
10. Фактическое поведение: ________________
```

### Контакты поддержки

| Канал | Описание | Время работы |
|-------|----------|-------------|
| **Email** | support@muraveivision.pro | 24/7 |
| **Telegram** | @muraveivision_support | 9:00-21:00 MSK |
| **GitHub Issues** | bug reports | 24/7 |
| **Срочная** | critical issues | 24/7 |

### Приоритеты обращений

| Приоритет | Критерии | Время ответа |
|-----------|----------|-------------|
| **P0 - Critical** | Система не работает, данные потеряны | 1 час |
| **P1 - High** | Критическая функция сломана | 4 часа |
| **P2 - Medium** | Функция работает с ограничениями | 24 часа |
| **P3 - Low** | Улучшение, рекомендация | 72 часа |

## Рекомендации

1. **Регулярно проверяйте логи** — минимум раз в день
2. **Мониторьте GPU** — температура, загрузка, память
3. **Следите за местом на диске** — минимум 20% свободного пространства
4. **Обновляйте драйверы** — используйте актуальные версии NVIDIA
5. **Делайте бэкапы моделей** — сохраняйте best.pt и last.pt
6. **Тестируйте на малых данных** — перед большими батчами
7. **Документируйте проблемы** — для быстрого поиска решений
