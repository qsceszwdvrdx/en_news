"""產生語音（edge-tts）與靜態網站（docs/，供 GitHub Pages 發佈）。"""
from __future__ import annotations

import asyncio
import html
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
# 網站
# --------------------------------------------------------------------------
CSS = """
:root{--bg:#fafafa;--fg:#1c1c1e;--muted:#6b7280;--card:#fff;--line:#e5e7eb;--accent:#2563eb;--chip:#eef2ff}
@media (prefers-color-scheme:dark){:root{--bg:#0f1115;--fg:#e5e7eb;--muted:#9ca3af;--card:#181b22;--line:#2a2f3a;--accent:#60a5fa;--chip:#1e2a44}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.65 -apple-system,"Segoe UI","Noto Sans TC",sans-serif}
.wrap{max-width:760px;margin:0 auto;padding:16px}
h1{font-size:1.4rem;margin:.4rem 0}h2{font-size:1.15rem;margin:0 0 .2rem}h3{font-size:.95rem;color:var(--muted);margin:1rem 0 .4rem}
a{color:var(--accent)}.muted{color:var(--muted);font-size:.9rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:14px 0}
.bar{position:sticky;top:0;background:var(--bg);padding:8px 0;border-bottom:1px solid var(--line);z-index:2;display:flex;gap:12px;flex-wrap:wrap;align-items:center}
button.play{border:1px solid var(--line);background:var(--chip);color:var(--fg);border-radius:999px;padding:2px 10px;cursor:pointer;font-size:.9rem}
button.play:active{opacity:.6}
.row{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}
.vocab{border-top:1px solid var(--line);padding:10px 0}.vocab:first-of-type{border-top:0}
.word{font-weight:700;font-size:1.05rem}.kk{color:var(--muted)}.tag{font-size:.75rem;background:var(--chip);border-radius:6px;padding:0 6px}
.ex{margin:.2rem 0 0 0}.zh{color:var(--muted)}body.en-only .zh{display:none}
ul.list{list-style:none;padding:0}ul.list li{padding:8px 0;border-bottom:1px solid var(--line)}
"""

JS = """
const AUDIO = {};
function play(btn){
  const src = btn.dataset.src, text = btn.dataset.text;
  document.querySelectorAll('audio.cur').forEach(a=>{a.pause();a.classList.remove('cur')});
  speechSynthesis.cancel();
  if(src){const a=new Audio(src);a.classList.add('cur');a.playbackRate=parseFloat(document.getElementById('speed').value);
    a.play().catch(()=>speak(text));document.body.appendChild(a);a.onended=()=>a.remove();}
  else speak(text);
}
function speak(t){const u=new SpeechSynthesisUtterance(t);u.lang='en-US';u.rate=parseFloat(document.getElementById('speed').value);speechSynthesis.speak(u)}
function setMode(){const on=document.getElementById('zh').checked;document.body.classList.toggle('en-only',!on);try{localStorage.zh=on?1:0}catch(e){}}
window.addEventListener('DOMContentLoaded',()=>{try{if(localStorage.zh==='0')document.getElementById('zh').checked=false}catch(e){}setMode()});
"""


def e(s: str) -> str:
    return html.escape(s or "", quote=True)


def btn(label: str, text: str, src: str | None) -> str:
    return f'<button class="play" onclick="play(this)" data-text="{e(text)}" data-src="{e(src or "")}" aria-label="play">{label}</button>'


def page(title: str, body: str) -> str:
    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)}</title>
<style>{CSS}</style></head><body><div class="wrap">{body}</div><script>{JS}</script></body></html>"""


def render_day(data: dict, audio: dict) -> str:
    date_str = data["date"]
    parts = [f'<p class="muted"><a href="index.html">← 全部日期</a></p><h1>每日新聞 × 單字學習 · {e(date_str)}</h1>',
             '<div class="bar"><label><input type="checkbox" id="zh" checked onchange="setMode()"> 顯示中文</label>'
             '<label>速度 <select id="speed"><option value="0.8">0.8x</option><option value="1" selected>1x</option>'
             '<option value="1.2">1.2x</option></select></label>'
             f'<a href="../news_en/{e(date_str)}.md">Markdown（English）</a></div>']
    for i, it in enumerate(data["items"], 1):
        src = data["news"][i - 1] if i - 1 < len(data["news"]) else {}
        parts.append('<section class="card">')
        parts.append(f'<h2>{i}. {e(it["title_en"])}</h2><div class="zh">{e(it["title_zh"])}</div>')
        if src:
            parts.append(f'<div class="muted">Source: <a href="{e(src["link"])}" target="_blank" rel="noopener">{e(src["source"])}</a></div>')
        parts.append(f'<h3>Summary</h3><div class="row">{btn("▶ 朗讀", it["summary_en"], audio.get(f"n{i}-summary"))}</div>')
        parts.append(f'<p>{e(it["summary_en"])}</p><p class="zh">{e(it["summary_zh"])}</p>')
        parts.append(f'<h3>Why it matters</h3><p>{e(it["why_important_en"])}</p><p class="zh">{e(it["why_important_zh"])}</p>')
        parts.append("<h3>Vocabulary</h3>")
        for j, v in enumerate(it["vocab"], 1):
            toeic = '<span class="tag">TOEIC</span>' if v["toeic_common"] else ""
            syn = ", ".join(v["synonyms"][:2]) or "-"
            col = ", ".join(v["collocations"][:2]) or "-"
            parts.append(
                '<div class="vocab">'
                f'<div class="row"><span class="word">{e(v["word"])}</span><span class="kk">{e(v["kk"])}</span>'
                f'<span class="muted">{e(v["pos"])}</span>{toeic}{btn("🔊", v["word"], audio.get(f"n{i}-w{j}"))}</div>'
                f'<div>{e(v["definition_en"])}</div><div class="zh">{e(v["meaning_zh"])}</div>'
                f'<div class="ex row">{btn("▶", v["sentence_en"], audio.get(f"n{i}-w{j}-ex"))}<span>{e(v["sentence_en"])}</span></div>'
                f'<div class="zh">{e(v["sentence_zh"])}</div>'
                f'<div class="muted">Synonyms: {e(syn)} · Collocations: {e(col)}</div></div>')
        parts.append("</section>")
    return page(f"{date_str} 每日新聞 × 單字", "".join(parts))


def render_index(dates: list[tuple[str, list[str]]]) -> str:
    lis = "".join(f'<li><a href="{d}.html"><b>{d}</b></a><div class="muted">{e(" · ".join(t[:3]))}</div></li>' for d, t in dates)
    body = ('<h1>每日新聞 × 單字學習</h1><p class="muted">每天台灣時間 07:00 自動更新。點進任一天可以聽英文語音、切換中文顯示。</p>'
            f'<ul class="list">{lis}</ul>')
    return page("每日新聞 × 單字學習", body)


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
    dates = []
    for f in sorted((DOCS / "data").glob("2*.json"), reverse=True):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception as ex:  # noqa: BLE001
            print(f"[WARN] 讀取 {f.name} 失敗: {ex}", file=sys.stderr)
            continue
        (DOCS / f"{d['date']}.html").write_text(render_day(d, d.get("audio", {})), encoding="utf-8")
        dates.append((d["date"], [it["title_en"] for it in d["items"]]))
    (DOCS / "index.html").write_text(render_index(dates), encoding="utf-8")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")


if __name__ == "__main__":  # python site_gen.py：不重新呼叫 API，只用既有資料重建網站
    rebuild_all()
