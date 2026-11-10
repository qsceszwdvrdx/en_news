#!/usr/bin/env python3
"""每日檢查：列出超過 N 天的檔案（依檔名日期判斷），並刪除過期的語音檔。

- 檢查範圍：news/、news_en/、anki/、docs/（網頁、data、audio）、logs/
- 只會刪除 docs/audio/YYYY-MM-DD/ 底下超過 N 天的音檔；其他檔案只列報告，不刪除。
- 報告輸出到 logs/stale-files.md。
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).parent
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"


def size_of(p: Path) -> int:
    return p.stat().st_size if p.is_file() else sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def file_date(p: Path) -> date | None:
    m = DATE_RE.search(p.name)
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d").date() if m else None
    except ValueError:
        return None


# (類別, 資料夾, glob) —— audio 以「日期資料夾」為單位
TARGETS = [
    ("日報（中文）", "news", "*.md"),
    ("日報（英文）", "news_en", "*.md"),
    ("Anki", "anki", "*.csv"),
    ("網頁", "docs", "2*.html"),
    ("網頁資料", "docs/data", "*.json"),
    ("語音", "docs/audio", "*"),
    ("執行記錄", "logs", "2*.json"),
]


def main() -> int:
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    sc = cfg.get("stale", {})
    days = int(sc.get("days", 7))
    delete_audio = bool(sc.get("delete_audio", True))
    tz = timezone(timedelta(hours=cfg.get("timezone_offset", 8)))
    today = datetime.now(tz).date()
    cutoff = today - timedelta(days=days)  # 日期早於 cutoff 視為過期

    found = []  # (類別, path, date, size)
    for label, folder, pattern in TARGETS:
        base = ROOT / folder
        if not base.is_dir():
            continue
        for p in sorted(base.glob(pattern)):
            d = file_date(p)
            if d and d < cutoff:
                found.append((label, p, d, size_of(p)))

    deleted, errors = [], []
    audio_dates = set()
    if delete_audio:
        audio_root = (ROOT / "docs" / "audio").resolve()
        for label, p, d, size in found:
            if label != "語音" or not p.is_dir():
                continue
            target = p.resolve()
            # 安全檢查：必須是 docs/audio/ 底下、名稱為日期的資料夾
            if target.parent != audio_root or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", target.name):
                errors.append(f"略過不安全的路徑: {p}")
                continue
            try:
                shutil.rmtree(target)
                deleted.append((p.name, size))
                audio_dates.add(p.name)
            except Exception as e:  # noqa: BLE001
                errors.append(f"刪除 {p.name} 失敗: {e}")

    # 音檔刪除後，網頁資料不再引用 mp3（改用瀏覽器內建朗讀），並重建網站
    if audio_dates:
        for ds in audio_dates:
            f = ROOT / "docs" / "data" / f"{ds}.json"
            if f.exists():
                data = json.loads(f.read_text(encoding="utf-8"))
                data["audio"] = {}
                f.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        try:
            sys.path.insert(0, str(ROOT))
            import site_gen
            site_gen.rebuild_all()
        except Exception as e:  # noqa: BLE001
            errors.append(f"重建網站失敗: {e}")

    # ---- 報告 ----
    deleted_names = {n for n, _ in deleted}
    lines = [
        "# 過期檔案檢查", "",
        f"- 檢查時間（台灣）：{datetime.now(tz).strftime('%Y-%m-%d %H:%M')}",
        f"- 規則：檔名日期早於 {cutoff}（超過 {days} 天）視為過期",
        f"- 自動刪除過期語音：{'開啟' if delete_audio else '關閉'}",
        f"- 過期項目：{len(found)} 個；本次已刪除語音資料夾：{len(deleted)} 個"
        f"（釋出 {human(sum(s for _, s in deleted))}）", "",
    ]
    if found:
        lines += ["| 類別 | 路徑 | 日期 | 大小 | 處理 |", "| --- | --- | --- | --- | --- |"]
        for label, p, d, size in found:
            rel = p.relative_to(ROOT).as_posix()
            action = "🗑️ 已刪除" if (label == "語音" and p.name in deleted_names) else "僅列出"
            lines.append(f"| {label} | `{rel}` | {d} | {human(size)} | {action} |")
    else:
        lines.append("沒有超過期限的檔案。")
    if errors:
        lines += ["", "## 錯誤", *[f"- {e}" for e in errors]]
    (ROOT / "logs").mkdir(exist_ok=True)
    (ROOT / "logs" / "stale-files.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"[INFO] 過期檔案 {len(found)} 個，已刪除語音 {len(deleted)} 個")
    for e in errors:
        print(f"[WARN] {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
