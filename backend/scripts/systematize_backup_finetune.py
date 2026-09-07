"""Systematize backup datasets → balanced YOLO detect subset (nc=238) + finetune.

Uses local Ollama vision (qwen2.5vl) to triage downloaded/ subfolders.
Keeps the full 238-class military_classes.yaml taxonomy — nothing dropped.
Only down-samples aviation / naval classes (14, 15, 17).
"""
from __future__ import annotations

import argparse
import base64
import json
import random
import re
import shutil
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[2]
BACKUP_DS = ROOT / ".backup" / "MuraveiVision" / "dataset"
MIL_YAML = ROOT / "military_classes.yaml"
OUT_DIR = ROOT / "cache" / "backup_finetune_ds"
INV_JSON = ROOT / "logs" / "backup_dataset_inventory.json"
TRIAGE_JSON = ROOT / "logs" / "backup_ollama_triage.json"
REPORT_JSON = ROOT / "logs" / "backup_finetune_report.json"
OLLAMA_BASE = "http://127.0.0.1:11434"
OLLAMA_VISION = "qwen2.5vl:7b"

# Per-class image caps (files containing the class). None → default.
LOW_SAMPLE_IDS = {14, 15, 17}  # helicopter, aircraft, boat — меньше, но не выкидываем
MAX_PER_CLASS_DEFAULT = 400
MAX_PER_CLASS_LOW = 60
MAX_IMAGES = 6000
ROOT_LABEL_CAP = 25000  # random subsample of huge root train+val
MOD12_LABEL_CAP = 8000
VAL_RATIO = 0.12
EPOCHS = 12
SEED = 42

# military_object_dataset (12 cls) → 238 yaml ids
MOD12_TO_238: dict[int, int | None] = {
    0: 20,  # camouflage_soldier
    1: 26,  # weapon → rifle
    2: 0,  # tank
    3: 6,  # truck
    4: 3,  # vehicle
    5: None,  # civilian
    6: 19,  # soldier
    7: None,  # civilian_vehicle
    8: 12,  # artillery
    9: 43,  # trench
    10: 15,  # aircraft
    11: 17,  # warship → boat
}

# Heuristic pre-filter before Ollama (still overridable by triage cache)
HEURISTIC_SKIP = {
    "visdrone",
    "terrains-dataset",
    "aerialdata",
    "visdrone2019",
}
HEURISTIC_KEEP = {
    "military_object_dataset",
    "military_merged",
    "kiit-mita",
    "uav military",
    "manual",
    "raw",
}


def load_238_names() -> dict[int, str]:
    data = yaml.safe_load(MIL_YAML.read_text(encoding="utf-8")) or {}
    names = data.get("names", data)
    if isinstance(names, dict):
        return {int(k): str(v) for k, v in names.items()}
    return {i: str(v) for i, v in enumerate(names)}


def _token_float(token: str) -> float | None:
    token = token.strip()
    if not token:
        return None
    try:
        return float(token)
    except ValueError:
        pass
    m = re.search(r"(-?\d+\.\d+|-?\d+)", token)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def parse_label_line(line: str) -> tuple[int, list[float]] | None:
    parts = line.split()
    if len(parts) < 5:
        return None
    try:
        cid = int(float(parts[0]))
    except ValueError:
        return None
    coords: list[float] = []
    for tok in parts[1:5]:
        val = _token_float(tok)
        if val is None:
            return None
        coords.append(val)
    if not all(0.0 <= c <= 1.05 for c in coords):
        return None
    return cid, coords


def parse_label(path: Path) -> list[tuple[int, list[float]]]:
    out: list[tuple[int, list[float]]] = []
    txt = path.read_text(encoding="utf-8", errors="ignore").strip()
    if not txt:
        return out
    for line in txt.splitlines():
        parsed = parse_label_line(line)
        if parsed:
            out.append(parsed)
    return out


def cap_for_class(cid: int) -> int:
    return MAX_PER_CLASS_LOW if cid in LOW_SAMPLE_IDS else MAX_PER_CLASS_DEFAULT


def find_image_for_label(label_path: Path, search_roots: list[Path]) -> Path | None:
    stem = label_path.stem
    exts = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
    for root in search_roots:
        for sub in ("", "images", "images/train", "images/val", "train/images", "val/images", "test/images"):
            base = root / sub if sub else root
            if not base.is_dir():
                continue
            for ext in exts:
                p = base / f"{stem}{ext}"
                if p.is_file():
                    return p
            hits = list(base.glob(f"{stem}.*"))
            if hits:
                return hits[0]
    return None


def remap_boxes(boxes: list[tuple[int, list[float]]], mapper: dict[int, int | None]) -> list[tuple[int, list[float]]]:
    out: list[tuple[int, list[float]]] = []
    for cid, xy in boxes:
        mapped = mapper.get(cid, cid)
        if mapped is None:
            continue
        if 0 <= mapped <= 237:
            out.append((mapped, xy))
    return out


def identity_mapper(_: int) -> int | None:
    return None  # placeholder unused


# ── Ollama triage ──────────────────────────────────────────────────────────

TRIAGE_PROMPT = (
    "Кадр из датасета для обучения детектора военных объектов с БПЛА (пехота, техника, "
    "укрепления, оружие, боеприпасы, пусковые установки). "
    "Ответь ОДНИМ словом: KEEP — если есть военные объекты; "
    "REDUCE — если смешанный/много гражданского; "
    "SKIP — если это аэродром, самолёты, корабли, городской VisDrone или нет военных объектов."
)


def _ollama_available() -> bool:
    try:
        with httpx.Client(timeout=3.0) as client:
            r = client.get(f"{OLLAMA_BASE}/api/tags")
        return r.status_code == 200
    except Exception:
        return False


def _image_to_b64(path: Path, max_side: int = 768) -> str:
    try:
        from PIL import Image
        import io

        img = Image.open(path).convert("RGB")
        w, h = img.size
        scale = min(1.0, max_side / max(w, h))
        if scale < 1.0:
            img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return base64.b64encode(path.read_bytes()).decode("ascii")


def ollama_triage_folder(folder: Path, sample_n: int = 2) -> dict:
    imgs: list[Path] = []
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
        imgs.extend(folder.rglob(ext))
    if not imgs:
        return {"verdict": "skip", "reason": "no_images", "samples": 0}

    random.seed(SEED)
    picks = random.sample(imgs, min(sample_n, len(imgs)))
    votes: Counter[str] = Counter()
    details: list[str] = []

    for img in picks:
        body = {
            "model": OLLAMA_VISION,
            "prompt": TRIAGE_PROMPT,
            "stream": False,
            "images": [_image_to_b64(img)],
        }
        try:
            with httpx.Client(timeout=90.0) as client:
                resp = client.post(f"{OLLAMA_BASE}/api/generate", json=body)
            if resp.status_code != 200:
                votes["keep"] += 1
                details.append(f"{img.name}: HTTP {resp.status_code} → keep(default)")
                continue
            text = str(resp.json().get("response") or "").strip().upper()
            if "SKIP" in text:
                votes["skip"] += 1
                verdict = "skip"
            elif "REDUCE" in text:
                votes["reduce"] += 1
                verdict = "reduce"
            else:
                votes["keep"] += 1
                verdict = "keep"
            details.append(f"{img.name}: {verdict} ({text[:80]})")
        except Exception as exc:
            votes["keep"] += 1
            details.append(f"{img.name}: error {exc} → keep(default)")

    verdict = votes.most_common(1)[0][0] if votes else "keep"
    return {"verdict": verdict, "votes": dict(votes), "samples": len(picks), "details": details}


def heuristic_verdict(name: str) -> str | None:
    low = name.lower()
    if any(k in low for k in HEURISTIC_SKIP):
        return "skip"
    if any(k in low for k in HEURISTIC_KEEP):
        return "keep"
    return None


def triage_downloaded(use_ollama: bool = True, force: bool = False) -> dict:
    downloaded = BACKUP_DS / "downloaded"
    if TRIAGE_JSON.is_file() and not force:
        return json.loads(TRIAGE_JSON.read_text(encoding="utf-8"))

    report: dict = {"generated_at": time.time(), "ollama": use_ollama and _ollama_available(), "folders": {}}
    if not downloaded.is_dir():
        TRIAGE_JSON.parent.mkdir(parents=True, exist_ok=True)
        TRIAGE_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report

    for entry in sorted(downloaded.iterdir()):
        if not entry.is_dir():
            continue
        name = entry.name
        h = heuristic_verdict(name)
        if h == "skip":
            row = {"verdict": "skip", "source": "heuristic", "samples": 0}
        elif h == "keep":
            row = {"verdict": "keep", "source": "heuristic", "samples": 0}
        elif use_ollama and report["ollama"]:
            row = ollama_triage_folder(entry)
            row["source"] = "ollama"
        else:
            row = {"verdict": "reduce", "source": "default", "samples": 0}
        report["folders"][name] = row
        print(f"[TRIAGE] {name}: {row['verdict']} ({row.get('source')})")

    TRIAGE_JSON.parent.mkdir(parents=True, exist_ok=True)
    TRIAGE_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[TRIAGE] wrote {TRIAGE_JSON}")
    return report


def folder_allowed(name: str, triage: dict) -> bool:
    row = (triage.get("folders") or {}).get(name) or {}
    v = str(row.get("verdict") or "keep").lower()
    return v in ("keep", "reduce")


def folder_scale(name: str, triage: dict) -> float:
    row = (triage.get("folders") or {}).get(name) or {}
    v = str(row.get("verdict") or "keep").lower()
    if v == "reduce":
        return 0.35
    if v == "skip":
        return 0.0
    return 1.0


# ── Collect sources ────────────────────────────────────────────────────────

def iter_root_backup() -> list[dict]:
    items: list[dict] = []
    mapper = {i: i for i in range(75)}
    all_labels: list[tuple[str, Path, Path]] = []
    for split in ("train", "val"):
        lbl_dir = BACKUP_DS / "labels" / split
        img_dir = BACKUP_DS / "images" / split
        if not lbl_dir.is_dir():
            continue
        for lp in lbl_dir.glob("*.txt"):
            all_labels.append((split, lp, img_dir))
    random.seed(SEED)
    total = len(all_labels)
    if total > ROOT_LABEL_CAP:
        all_labels = random.sample(all_labels, ROOT_LABEL_CAP)
        print(f"[COLLECT] root: subsampled {ROOT_LABEL_CAP} / {total} labels")
    for i, (_split, lp, img_dir) in enumerate(all_labels, 1):
        if i % 5000 == 0:
            print(f"[COLLECT] root: {i}/{len(all_labels)} parsed, kept={len(items)}")
        boxes = remap_boxes(parse_label(lp), mapper)
        if not boxes:
            continue
        img = find_image_for_label(lp, [img_dir])
        if img is None:
            continue
        items.append(
            {
                "stem": f"root_{lp.stem}",
                "source": "root",
                "image": img,
                "boxes": boxes,
                "cids": {c for c, _ in boxes},
            }
        )
    return items


def iter_military_object_dataset(scale: float = 1.0) -> list[dict]:
    root = BACKUP_DS / "downloaded" / "military_object_dataset"
    if not root.is_dir() or scale <= 0:
        return []
    items: list[dict] = []
    labels = list(root.rglob("labels/*.txt")) + list(root.rglob("**/labels/*.txt"))
    if not labels:
        labels = [p for p in root.rglob("*.txt") if "label" in str(p.parent).lower()]
    random.seed(SEED)
    cap = max(1, int(MOD12_LABEL_CAP * scale)) if scale < 1.0 else MOD12_LABEL_CAP
    if len(labels) > cap:
        labels = random.sample(labels, cap)
    elif scale < 1.0 and labels:
        labels = random.sample(labels, max(1, int(len(labels) * scale)))
    search = [root]
    for lp in labels:
        boxes = remap_boxes(parse_label(lp), MOD12_TO_238)
        if not boxes:
            continue
        img = find_image_for_label(lp, search)
        if img is None:
            continue
        items.append(
            {
                "stem": f"mod12_{lp.stem}",
                "source": "military_object_dataset",
                "image": img,
                "boxes": boxes,
                "cids": {c for c, _ in boxes},
            }
        )
    return items


def _is_label_file(p: Path) -> bool:
    return p.suffix.lower() == ".txt" and any(part.lower() == "labels" for part in p.parts)


def iter_yolo_folder(name: str, mapper: dict[int, int | None] | None, scale: float) -> list[dict]:
    root = BACKUP_DS / "downloaded" / name
    if not root.is_dir() or scale <= 0:
        return []
    id_map = mapper or {i: i for i in range(238)}
    items: list[dict] = []
    txts = [p for p in root.rglob("*.txt") if _is_label_file(p)]
    random.seed(SEED + hash(name) % 10000)
    if scale < 1.0 and txts:
        txts = random.sample(txts, max(1, int(len(txts) * scale)))
    for lp in txts:
        boxes = remap_boxes(parse_label(lp), id_map)
        if not boxes:
            continue
        img = find_image_for_label(lp, [root])
        if img is None:
            continue
        items.append(
            {
                "stem": f"{name[:8]}_{lp.stem}",
                "source": name,
                "image": img,
                "boxes": boxes,
                "cids": {c for c, _ in boxes},
            }
        )
    return items


def collect_all_items(triage: dict) -> list[dict]:
    items: list[dict] = []
    items.extend(iter_root_backup())
    print(f"[COLLECT] root backup: {len(items)}")

    for folder in sorted((triage.get("folders") or {}).keys()):
        scale = folder_scale(folder, triage)
        if scale <= 0:
            print(f"[COLLECT] skip {folder}")
            continue
        if folder == "military_object_dataset":
            chunk = iter_military_object_dataset(scale)
        elif folder in ("military_merged", "KIIT-MiTA") or "UAV Military" in folder:
            # merged datasets use 75-class ids aligned with military_classes 0-74
            chunk = iter_yolo_folder(folder, {i: i for i in range(75)}, scale)
        else:
            chunk = iter_yolo_folder(folder, {i: i for i in range(75)}, scale * 0.5)
        print(f"[COLLECT] {folder}: {len(chunk)} (scale={scale:.2f})")
        items.extend(chunk)

    print(f"[COLLECT] total raw items: {len(items)}")
    return items


def balanced_select(items: list[dict]) -> list[dict]:
    random.seed(SEED)
    by_class: dict[int, list[dict]] = defaultdict(list)
    for it in items:
        for c in it["cids"]:
            by_class[c].append(it)

    selected: dict[str, dict] = {}
    # Round-robin per class id 0..237 — nothing excluded from taxonomy
    for cid in range(238):
        cap = cap_for_class(cid)
        pool = by_class.get(cid, [])
        random.shuffle(pool)
        taken = 0
        for it in pool:
            if it["stem"] in selected:
                continue
            selected[it["stem"]] = it
            taken += 1
            if taken >= cap or len(selected) >= MAX_IMAGES:
                break
        if taken and cid % 20 == 0:
            print(f"[SEL] class {cid}: +{taken} (pool={len(pool)}, total={len(selected)})")
        if len(selected) >= MAX_IMAGES:
            break

    out = list(selected.values())[:MAX_IMAGES]
    print(f"[SEL] selected {len(out)} images")
    return out


def inventory(names: dict[int, str], items: list[dict] | None = None) -> dict:
    counts = Counter()
    files_with: Counter[int] = Counter()
    n_files = 0
    empty = 0

    if items is None:
        for split in ("train", "val"):
            for p in (BACKUP_DS / "labels" / split).glob("*.txt"):
                n_files += 1
                boxes = parse_label(p)
                if not boxes:
                    empty += 1
                    continue
                seen = set()
                for cid, _ in boxes:
                    if cid <= 237:
                        counts[cid] += 1
                        seen.add(cid)
                for c in seen:
                    files_with[c] += 1
    else:
        n_files = len(items)
        for it in items:
            boxes = it["boxes"]
            if not boxes:
                empty += 1
                continue
            seen = set()
            for cid, _ in boxes:
                counts[cid] += 1
                seen.add(cid)
            for c in seen:
                files_with[c] += 1

    rows = []
    for cid in range(238):
        rows.append(
            {
                "id": cid,
                "name": names[cid],
                "boxes": int(counts.get(cid, 0)),
                "files": int(files_with.get(cid, 0)),
                "low_sample": cid in LOW_SAMPLE_IDS,
            }
        )
    inv = {
        "source": str(BACKUP_DS),
        "nc": 238,
        "label_files": n_files,
        "empty_labels": empty,
        "total_boxes": int(sum(counts.values())),
        "classes": rows,
    }
    INV_JSON.parent.mkdir(parents=True, exist_ok=True)
    INV_JSON.write_text(json.dumps(inv, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[INV] files={n_files} boxes={sum(counts.values())} → {INV_JSON}")
    for r in rows:
        if r["boxes"]:
            tag = " LOW" if r["low_sample"] else ""
            print(f"  {r['id']:3d}{tag} boxes={r['boxes']:6d} files={r['files']:5d}  {r['name']}")
    return inv


def write_dataset(items: list[dict], names: dict[int, str]) -> tuple[Path, int, int]:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR, ignore_errors=True)
    for sub in ("images/train", "images/val", "labels/train", "labels/val"):
        (OUT_DIR / sub).mkdir(parents=True, exist_ok=True)

    random.seed(SEED)
    random.shuffle(items)
    n_val = max(1, int(len(items) * VAL_RATIO))
    val_stems = {it["stem"] for it in items[:n_val]}

    written = box_n = 0
    for it in items:
        split = "val" if it["stem"] in val_stems else "train"
        dst_img = OUT_DIR / "images" / split / f"{it['stem']}{it['image'].suffix.lower()}"
        if not dst_img.exists():
            try:
                dst_img.hardlink_to(it["image"])
            except Exception:
                shutil.copy2(it["image"], dst_img)
        lines = []
        for cid, xywh in it["boxes"]:
            if not (0 <= cid <= 237):
                continue
            lines.append(f"{cid} {xywh[0]:.6f} {xywh[1]:.6f} {xywh[2]:.6f} {xywh[3]:.6f}")
            box_n += 1
        (OUT_DIR / "labels" / split / f"{it['stem']}.txt").write_text(
            "\n".join(lines) + ("\n" if lines else ""),
            encoding="utf-8",
        )
        written += 1

    yaml_path = OUT_DIR / "dataset.yaml"
    ylines = [
        f"path: {OUT_DIR.as_posix()}",
        "train: images/train",
        "val: images/val",
        "task: detect",
        "nc: 238",
        "names:",
    ]
    for i in range(238):
        ylines.append(f"  {i}: {names[i]}")
    yaml_path.write_text("\n".join(ylines) + "\n", encoding="utf-8")
    print(f"[DS] {written} images, {box_n} boxes, nc=238 → {yaml_path}")
    return yaml_path, written, box_n


def _train_device() -> str | int:
    try:
        import torch

        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            print(f"[TRAIN] CUDA: {name}")
            return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[TRAIN] CUDA probe failed: {exc}")
    print("[TRAIN] fallback CPU (install torch+cu128 if GPU expected)")
    return "cpu"


def train(yaml_path: Path) -> dict:
    sys.path.insert(0, str(ROOT / "backend"))
    from config import BASE_DIR  # noqa: F401
    from services.trainer import WEIGHTS_DIR
    from services.yolo_engine import get_yolo_engine

    bases = [
        BASE_DIR / "assets" / "models" / "yolo26n-ft.pt",
        WEIGHTS_DIR / "yolo26n-ft.pt",
        WEIGHTS_DIR / "yolo26n.pt",
        BASE_DIR / "assets" / "models" / "yolo26n.pt",
    ]
    base = next((p for p in bases if p.is_file() and p.stat().st_size > 1024), None)
    if base is None:
        raise FileNotFoundError("No yolo26n / yolo26n-ft base weights")

    from ultralytics import YOLO

    device = _train_device()
    # RTX 5060 Laptop ~8GB: imgsz=1024 + nc=238 needs tiny batches
    batch_candidates = (4, 2, 1) if device != "cpu" else (8, 4, 2)
    imgsz = 640 if device != "cpu" else 1024

    print(f"[TRAIN] base={base.name} epochs={EPOCHS} nc=238 device={device} imgsz={imgsz}")
    run_name = "backup_finetune_run"
    run_parent = ROOT / "cache"
    if (run_parent / run_name).exists():
        shutil.rmtree(run_parent / run_name, ignore_errors=True)

    last_err = None
    for batch in batch_candidates:
        try:
            import torch

            if device != "cpu" and torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
            model = YOLO(str(base))
            model.train(
                data=str(yaml_path),
                task="detect",
                imgsz=imgsz,
                batch=batch,
                epochs=EPOCHS,
                optimizer="SGD",
                momentum=0.937,
                lr0=0.001,
                lrf=0.01,
                weight_decay=0.0005,
                box=7.5,
                cls=0.5,
                dfl=1.5,
                warmup_epochs=1.0,
                close_mosaic=max(1, int(EPOCHS * 0.2)),
                copy_paste=0.5,
                mosaic=0.5,
                mixup=0.0,
                project=str(run_parent),
                name=run_name,
                exist_ok=True,
                verbose=True,
                plots=False,
                save=True,
                device=device,
                workers=2,
                amp=True,
            )
            last_err = None
            break
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            msg = str(exc).lower()
            print(f"[TRAIN] batch={batch} failed: {exc}")
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
            if "out of memory" in msg or "cuda" in msg:
                continue
            raise
    if last_err:
        raise last_err

    hits = list((ROOT / "cache").rglob(f"{run_name}/**/best.pt"))
    best = hits[0] if hits else None
    if best is None:
        raise RuntimeError("best.pt not found")

    assets = ROOT / "assets" / "models"
    assets.mkdir(parents=True, exist_ok=True)
    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    target = assets / "yolo26n-ft.pt"
    mirror = WEIGHTS_DIR / "yolo26n-ft.pt"
    for dest in (target, mirror):
        if dest.is_file():
            backup = dest.with_suffix(dest.suffix + ".backup")
            if backup.exists():
                backup.unlink()
            shutil.copy2(dest, backup)
        shutil.copy2(best, dest)
    print(f"[TRAIN] promoted → {target}")

    try:
        eng = get_yolo_engine()
        if eng.force_load(target):
            print("[TRAIN] engine force-loaded ft")
    except Exception as exc:  # noqa: BLE001
        print(f"[TRAIN] reload skip: {exc}")

    return {"best": str(best), "promoted": str(target)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", action="store_true", help="inventory root labels only")
    ap.add_argument("--triage", action="store_true", help="Ollama triage downloaded/")
    ap.add_argument("--no-ollama", action="store_true", help="heuristics only for triage")
    ap.add_argument("--no-train", action="store_true", help="build dataset only")
    ap.add_argument("--train-only", action="store_true", help="train on existing cache/backup_finetune_ds")
    ap.add_argument("--force-triage", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    names = load_238_names()
    if len(names) != 238:
        print(f"[WARN] expected 238 classes, got {len(names)}")

    if args.inventory:
        inventory(names)
        return 0

    if args.triage or not TRIAGE_JSON.is_file():
        triage = triage_downloaded(use_ollama=not args.no_ollama, force=args.force_triage)
    else:
        triage = json.loads(TRIAGE_JSON.read_text(encoding="utf-8"))
        print(f"[TRIAGE] loaded cache {TRIAGE_JSON}")

    if args.triage:
        return 0

    if args.train_only:
        yaml_path = OUT_DIR / "dataset.yaml"
        if not yaml_path.is_file():
            print(f"[ERR] missing {yaml_path} — run full pipeline first")
            return 3
        device = _train_device()
        print(f"[TRAIN-ONLY] data={yaml_path} device={device}")
        train_result = train(yaml_path)
        report = {
            "train_only": True,
            "device": str(device),
            "yaml": str(yaml_path),
            "train": train_result,
            "seconds": round(time.time() - t0, 1),
        }
        REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[DONE] {REPORT_JSON}")
        return 0

    raw = collect_all_items(triage)
    if len(raw) < 50:
        print("[ERR] too few collected items")
        return 3

    selected = balanced_select(raw)
    inv = inventory(names, selected)
    yaml_path, n_img, box_n = write_dataset(selected, names)

    hist = Counter()
    for it in selected:
        for c, _ in it["boxes"]:
            hist[names[c]] += 1
    print("[SEL] top classes:")
    for k, v in hist.most_common(20):
        print(f"  {v:5d}  {k}")

    train_result = None
    if not args.no_train:
        train_result = train(yaml_path)

    report = {
        "inventory": str(INV_JSON),
        "triage": str(TRIAGE_JSON),
        "selected_images": n_img,
        "boxes": box_n,
        "nc": 238,
        "low_sample_ids": sorted(LOW_SAMPLE_IDS),
        "class_hist_top": dict(hist.most_common(40)),
        "train": train_result,
        "seconds": round(time.time() - t0, 1),
    }
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[DONE] {REPORT_JSON} in {report['seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
