"""產生語音（edge-tts）與靜態網站（docs/，供 GitHub Pages 發佈）。"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DOCS = ROOT / "docs"


# --------------------------------------------------------------------------
# 語音
# --------------------------------------------------------------------------
async def _synth(sem: asyncio.Semaphore, text: str, out: Path, voice: str, rate: str, report: dict) -> None:
    import edge_tts

    async with sem:
        for attempt in range(3):
            try:
                await asyncio.wait_for(edge_tts.Communicate(text, voice, rate=rate).save(str(out)), timeout=60)
                if out.exists() and out.stat().st_size > 500:
                    report["ok"] += 1
                    return
                raise RuntimeError("empty audio")
            except Exception as e:  # noqa: BLE001
                out.unlink(missing_ok=True)
                if attempt == 2:
                    report["failed"] += 1
                    report["errors"].append(f"{out.name}: {re.sub(r'\\s+', ' ', str(e))[:120]}")
                else:
                    await asyncio.sleep(2 * (attempt + 1))


def build_audio(date_str: str, items: list, tts_cfg: dict) -> tuple[dict, dict]:
    """為每則摘要、每個單字與例句產生 MP3。回傳 (檔案對照表, 報告)。
    對照表只包含「成功產生」的檔案；缺的會在網頁上改用瀏覽器內建朗讀。"""
    report = {"enabled": True, "ok": 0, "failed": 0, "skipped": 0, "errors": []}
    outdir = DOCS / "audio" / date_str
    outdir.mkdir(parents=True, exist_ok=True)
    voice, rate = tts_cfg["voice"], tts_cfg.get("summary_rate", "-10%")

    jobs = []  # (key, text, rate)
    for i, it in enumerate(items, 1):
        jobs.append((f"n{i}-summary", it["summary_en"], rate))
        for j, v in enumerate(it["vocab"], 1):
            jobs.append((f"n{i}-w{j}", v["word"], "-15%"))
            jobs.append((f"n{i}-w{j}-ex", v["sentence_en"], "-5%"))

    async def run():
        sem = asyncio.Semaphore(tts_cfg.get("concurrency", 4))
        tasks = []
        for key, text, r in jobs:
            out = outdir / f"{key}.mp3"
            if out.exists() and out.stat().st_size > 500:
                report["skipped"] += 1
                continue
            tasks.append(_synth(sem, text, out, voice, r, report))
        await asyncio.gather(*tasks)

    try:
        import edge_tts  # noqa: F401
        asyncio.run(run())
    except Exception as e:  # noqa: BLE001
        report["errors"].append(f"tts aborted: {e}")
    files = {k: f"audio/{date_str}/{k}.mp3" for k, _, _ in jobs if (outdir / f"{k}.mp3").exists()}
    report["voice"] = voice
    return files, report


# --------------------------------------------------------------------------
# 網站（介面見 site_ui.py）
# --------------------------------------------------------------------------
def build_site(date_str: str, news: list, result_dict: dict, audio: dict) -> None:
    """寫入 docs/data/DATE.json、docs/DATE.html，並重建 docs/index.html。"""
    (DOCS / "data").mkdir(parents=True, exist_ok=True)
    data = {
        "date": date_str,
        "news": [{"source": a["source"], "link": a["link"]} for a in news],
        "items": result_dict["items"],
        "audio": audio,
    }
    (DOCS / "data" / f"{date_str}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    rebuild_all()


def rebuild_all() -> None:
    import site_ui

    days = []
    for f in sorted((DOCS / "data").glob("2*.json"), reverse=True):  # 新 -> 舊
        try:
            days.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception as ex:  # noqa: BLE001
            print(f"[WARN] 讀取 {f.name} 失敗: {ex}", file=sys.stderr)
    for k, d in enumerate(days):
        older = days[k + 1]["date"] if k + 1 < len(days) else None
        newer = days[k - 1]["date"] if k > 0 else None
        (DOCS / f"{d['date']}.html").write_text(site_ui.render_day(d, d.get("audio", {}), older, newer), encoding="utf-8")
    index = [(d["date"], [it["title_en"] for it in d["items"]], sum(len(it["vocab"]) for it in d["items"])) for d in days]
    (DOCS / "index.html").write_text(site_ui.render_index(index), encoding="utf-8")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")


if __name__ == "__main__":  # python site_gen.py：不重新呼叫 API，只用既有資料重建網站
    rebuild_all()
