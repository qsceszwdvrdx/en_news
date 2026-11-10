#!/usr/bin/env python3
"""每日新聞 × 單字學習：抓 RSS -> Gemini 一次處理 -> 輸出 Markdown / Anki CSV / README。"""
from __future__ import annotations

import csv
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

import feedparser
import yaml
from pydantic import BaseModel

ROOT = Path(__file__).parent
USER_AGENT = "Mozilla/5.0 (compatible; daily-news-vocab/1.0)"

# 本次執行的過程記錄（最後寫入 logs/YYYY-MM-DD.json）
LOG: dict = {"feeds": [], "fallback_used": False, "picked": [], "gemini": {"attempts": [], "used_model": None}}


def short(e: object, n: int = 200) -> str:
    return re.sub(r"\s+", " ", str(e))[:n]


# --------------------------------------------------------------------------
# Gemini 回傳的 JSON 結構
# --------------------------------------------------------------------------
class Vocab(BaseModel):
    word: str
    pos: str                  # 詞性
    kk: str                   # KK 音標
    meaning_zh: str
    definition_en: str        # 簡單英文解釋（給純英文版）
    sentence_en: str         # 日常生活例句（與新聞無關）
    sentence_zh: str
    synonyms: List[str]       # 1–2 個
    collocations: List[str]   # 1–2 個
    toeic_common: bool


class NewsItem(BaseModel):
    index: int
    title_en: str
    title_zh: str
    summary_en: str
    summary_zh: str
    why_important_en: str
    why_important_zh: str
    vocab: List[Vocab]


class DailyResult(BaseModel):
    items: List[NewsItem]


# --------------------------------------------------------------------------
# RSS 抓取與挑選
# --------------------------------------------------------------------------
def clean_text(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def normalize_title(title: str) -> str:
    title = re.sub(r"\s[-–|]\s[^-–|]+$", "", title)  # 去掉 " - Reuters" 之類的尾巴
    return title.strip()


STOP = set("a an the of to in on for and or at by with from as is are was were be after over amid says say new".split())


def tokens(title: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", title.lower()) if w not in STOP and len(w) > 2}


def similarity(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def fetch_feed(feed: dict, cutoff: datetime) -> list:
    """抓單一 RSS，失敗時回傳空 list（不中斷流程）。"""
    t0 = time.time()
    rec = {"name": feed["name"], "url": feed["url"], "status": "ok", "entries_total": 0, "entries_recent": 0, "error": None}
    LOG["feeds"].append(rec)
    try:
        parsed = feedparser.parse(feed["url"], agent=USER_AGENT)
        rec["http_status"] = parsed.get("status")
        if parsed.bozo and not parsed.entries:
            raise RuntimeError(parsed.get("bozo_exception"))
        rec["entries_total"] = len(parsed.entries)
        if not parsed.entries:
            rec["status"] = "empty"
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] 跳過來源 {feed['name']}: {e}", file=sys.stderr)
        rec.update(status="failed", error=short(e), seconds=round(time.time() - t0, 2))
        return []

    out = []
    for rank, e in enumerate(parsed.entries):
        ts = e.get("published_parsed") or e.get("updated_parsed")
        if ts:
            published = datetime(*ts[:6], tzinfo=timezone.utc)
            if published < cutoff:
                continue
        else:
            published = None  # 無日期：視為最新
        title = normalize_title(clean_text(e.get("title", "")))
        if not title or not e.get("link"):
            continue
        out.append({
            "source": feed["name"],
            "title": title,
            "summary": clean_text(e.get("summary", ""))[:600],
            "link": e["link"],
            "published": published,
            "rank": rank,  # 在該來源中的排序（越前面通常越重要）
            "tokens": tokens(title),
        })
    rec.update(entries_recent=len(out), seconds=round(time.time() - t0, 2))
    print(f"[INFO] {feed['name']}: {len(out)} 則 24 小時內新聞")
    return out


def cluster_and_pick(articles: list, n: int) -> list:
    """把相似標題聚成同一主題；多家媒體都報導的主題視為較重要。回傳 n 個不同主題。"""
    clusters: list[list] = []
    for a in articles:
        for c in clusters:
            if similarity(a["tokens"], c[0]["tokens"]) >= 0.5:
                c.append(a)
                break
        else:
            clusters.append([a])

    def score(c):
        sources = {x["source"] for x in c}
        return len(sources)

    # 穩定排序：覆蓋媒體數多者優先；同分保持原本（來源順序 + 發布順序）
    # 同分時：來源內排名靠前者優先，達到各來源輪流的效果
    ranked = sorted(clusters, key=lambda c: (-score(c), min(x["rank"] for x in c)))
    picked = []
    for c in ranked:
        # 優先挑摘要較長的版本，Gemini 才有較多內容可用
        best = dict(max(c, key=lambda x: len(x["summary"])))
        best["cluster_sources"] = sorted({x["source"] for x in c})
        picked.append(best)
        if len(picked) == n:
            break
    return picked


def collect_news(cfg: dict) -> list:
    n = cfg["news_count"]
    cutoff = datetime.now(timezone.utc) - timedelta(hours=cfg["lookback_hours"])

    articles = []
    for feed in cfg["feeds"]:
        articles.extend(fetch_feed(feed, cutoff))

    # 先依發布時間排序各來源內部（新→舊），再 round-robin 讓來源公平
    def unique_topics(arts):
        seen = []
        for a in arts:
            if not any(similarity(a["tokens"], s["tokens"]) >= 0.5 for s in seen):
                seen.append(a)
        return seen

    if len(unique_topics(articles)) < n and cfg.get("fallback_feed"):
        print("[INFO] 新聞不足，使用 Google News 補足")
        LOG["fallback_used"] = True
        articles.extend(fetch_feed(cfg["fallback_feed"], cutoff))

    # 同連結去重
    seen_links, deduped = set(), []
    for a in articles:
        if a["link"] not in seen_links:
            seen_links.add(a["link"])
            deduped.append(a)

    picked = cluster_and_pick(deduped, n)
    LOG["articles_after_dedupe"] = len(deduped)
    LOG["picked"] = [
        {"source": a["source"], "title": a["title"], "link": a["link"], "cluster_sources": a["cluster_sources"]}
        for a in picked
    ]
    if not picked:
        raise RuntimeError("所有 RSS 都抓不到新聞")
    return picked


# --------------------------------------------------------------------------
# Gemini
# --------------------------------------------------------------------------
def build_prompt(news: list, cfg: dict) -> str:
    lines = []
    for i, a in enumerate(news, 1):
        lines.append(f"[{i}] Source: {a['source']}\nTitle: {a['title']}\nText: {a['summary'] or '(no summary)'}")
    joined = "\n\n".join(lines)
    return f"""你是一位英文老師，學生程度：{cfg['learner']['level']}。
以下是 {len(news)} 則今日英文新聞（只有標題與簡短內文）。請針對每一則回傳 JSON，items 依序對應 index 1..{len(news)}。

每則包含：
- title_en：原文標題；title_zh：中文翻譯（繁體中文）
- summary_en：3 句以內的英文摘要，用 A2–B1 程度的簡單英文改寫（只根據提供的內容，不要編造細節）；summary_zh：同一份摘要的繁體中文版
- why_important_en：為什麼重要（簡單英文，1–2 句）；why_important_zh：同上的繁體中文版
- vocab：挑 {cfg['learner']['words_per_news']} 個「多益常考、日常實用」的單字；略過太艱深的專業術語、專有名詞、人名地名。每個單字：
  - word（原形）、pos（詞性，如 n. / v. / adj.）、kk（KK 音標，如 [ˈkraɪsɪs]）、meaning_zh（繁體中文意思，貼合句中用法）、definition_en（A2–B1 程度的簡單英文解釋，貼合句中用法）
  - sentence_en：一個包含該單字的「生活例句」，**不要**使用或改寫新聞內容，也不要與該則新聞主題相關。用美國或英國人日常真的會說的口語、自然的說法（像在工作、購物、旅行、聊天、餐廳、通勤等場合）；若該單字日常很少用到，就直接放一個它最常出現的常見場合句子（例如會議、電子郵件、訂房、面試）。句子簡短（約 8–15 字），符合 A2–B1 程度；sentence_zh：該句中文翻譯
  - 單字的選擇仍然來自該則新聞，但例句與新聞無關
  - synonyms：最常用的 1–2 個同義詞；collocations：最常見的 1–2 個搭配詞（短語）
  - toeic_common：是否為多益常見字（true/false）

新聞：

{joined}
"""


def call_gemini(prompt: str, cfg: dict) -> DailyResult:
    from google import genai
    from google.genai import errors, types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("未設定環境變數 GEMINI_API_KEY")
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=120_000))  # 毫秒
    g = cfg["gemini"]

    models = [g["model"]] + list(g.get("fallback_models", []))
    try:  # 自動補上 API 實際可用的 flash 模型作為備援
        for m in client.models.list():
            name = (m.name or "").replace("models/", "")
            if "flash" in name and "generateContent" in (m.supported_actions or [])                     and not any(x in name for x in ("image", "tts", "live", "audio", "preview-")) and name not in models:
                models.append(name)
        print(f"[INFO] 候選模型: {models}")
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] 無法列出模型: {e}", file=sys.stderr)
    last_err = None
    glog = LOG["gemini"]
    glog["candidate_models"] = models
    for model in models:
        for attempt in range(g["max_retries"] + 1):
            t0 = time.time()
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=DailyResult,
                        temperature=0.3,
                    ),
                )
                result = resp.parsed if isinstance(resp.parsed, DailyResult) else DailyResult.model_validate_json(resp.text)
                print(f"[INFO] 使用模型 {model}")
                glog["attempts"].append({"model": model, "attempt": attempt + 1, "result": "ok", "seconds": round(time.time() - t0, 1)})
                glog["used_model"] = model
                return result
            except errors.APIError as e:
                last_err = e
                code = getattr(e, "code", None)
                glog["attempts"].append({"model": model, "attempt": attempt + 1, "result": "error", "code": code,
                                         "message": short(e), "seconds": round(time.time() - t0, 1)})
                if code in (429, 503) and attempt < g["max_retries"]:
                    print(f"[WARN] {model} {code}，{g['retry_wait_seconds']} 秒後重試 ({attempt + 1}/{g['max_retries']})", file=sys.stderr)
                    time.sleep(g["retry_wait_seconds"])
                    continue
                print(f"[WARN] 模型 {model} 失敗: {code}", file=sys.stderr)
                break
            except Exception as e:  # noqa: BLE001  (例如 JSON 解析失敗)
                last_err = e
                glog["attempts"].append({"model": model, "attempt": attempt + 1, "result": "parse_error",
                                         "message": short(e), "seconds": round(time.time() - t0, 1)})
                print(f"[WARN] 模型 {model} 回傳無法解析: {e}", file=sys.stderr)
                break
    if last_err:
        raise last_err
    raise RuntimeError("Gemini 重試次數用盡")


# --------------------------------------------------------------------------
# 輸出
# --------------------------------------------------------------------------
def md_cell(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def render_markdown(date_str: str, news: list, result: DailyResult) -> str:
    """中文版（雙語）：英文原文摘要 + 中文翻譯。"""
    out = [f"# 每日新聞 × 單字學習 — {date_str}", "", f"> 純英文版：[news_en/{date_str}.md](../news_en/{date_str}.md)", ""]
    by_index = {it.index: it for it in result.items}
    for i, a in enumerate(news, 1):
        it = by_index.get(i) or (result.items[i - 1] if i - 1 < len(result.items) else None)
        if it is None:
            continue
        out += [
            f"## {i}. {it.title_en}",
            f"**{it.title_zh}**",
            "",
            f"來源：[{a['source']}]({a['link']})",
            "",
            "**摘要 Summary**",
            "",
            f"{it.summary_en}",
            "",
            f"{it.summary_zh}",
            "",
            "**為什麼重要 Why it matters**",
            "",
            f"{it.why_important_en}",
            "",
            f"{it.why_important_zh}",
            "",
            "### 單字",
            "",
        ]
        for v in it.vocab:
            toeic = "✅ 多益常見字" if v.toeic_common else "—"
            syn = "、".join(v.synonyms[:2]) or "—"
            col = "、".join(v.collocations[:2]) or "—"
            out += [
                f"- **{v.word}** {v.kk} （{v.pos}）{v.meaning_zh}　{toeic}",
                f"  - 例句：{v.sentence_en}",
                f"  - 翻譯：{v.sentence_zh}",
                f"  - 同義詞：{syn}　搭配詞：{col}",
            ]
        out += [""]
    return "\n".join(out).rstrip() + "\n"


def render_markdown_en(date_str: str, news: list, result: DailyResult) -> str:
    """純英文版：沒有任何中文內容。"""
    out = [f"# Daily News × Vocabulary — {date_str}", "", f"> Chinese version: [news/{date_str}.md](../news/{date_str}.md)", ""]
    by_index = {it.index: it for it in result.items}
    for i, a in enumerate(news, 1):
        it = by_index.get(i) or (result.items[i - 1] if i - 1 < len(result.items) else None)
        if it is None:
            continue
        out += [
            f"## {i}. {it.title_en}",
            "",
            f"Source: [{a['source']}]({a['link']})",
            "",
            f"**Summary**: {it.summary_en}",
            "",
            f"**Why it matters**: {it.why_important_en}",
            "",
            "### Vocabulary",
            "",
        ]
        for v in it.vocab:
            toeic = " — *TOEIC common*" if v.toeic_common else ""
            syn = ", ".join(v.synonyms[:2]) or "-"
            col = ", ".join(v.collocations[:2]) or "-"
            out += [
                f"- **{v.word}** {v.kk} ({v.pos}) {v.definition_en}{toeic}",
                f"  - Example: {v.sentence_en}",
                f"  - Synonyms: {syn}; Collocations: {col}",
            ]
        out += [""]
    return "\n".join(out).rstrip() + "\n"


def write_anki(path: Path, result: DailyResult) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";", lineterminator="\n")
        seen = set()
        for it in result.items:
            for v in it.vocab:
                key = v.word.lower()
                if key in seen:
                    continue
                seen.add(key)
                w.writerow([v.word, f"{v.pos} {v.meaning_zh}", f"{v.sentence_en} ({v.sentence_zh})"])


def update_readme(date_str: str, news_titles: list, site_url: str | None = None) -> None:
    dates = sorted((p.stem for p in (ROOT / "news").glob("*.md")), reverse=True)
    latest = "\n".join(f"{i}. {t}" for i, t in enumerate(news_titles, 1))
    def hist(d: str) -> str:
        en = f"｜[English only](news_en/{d}.md)" if (ROOT / "news_en" / f"{d}.md").exists() else ""
        return f"- {d}：[中文版](news/{d}.md){en}｜[Anki](anki/{d}.csv)"

    history = "\n".join(hist(d) for d in dates)
    site_line = f"\n🎧 **網站版（可播放英文語音）：{site_url}**\n" if site_url else ""
    content = f"""# 每日新聞 × 單字學習

每天台灣時間 07:00 由 GitHub Actions 自動產生 5 則英文新聞、中文摘要與多益單字。
{site_line}
## 最新一期：{date_str}（[中文版](news/{date_str}.md)｜[English only](news_en/{date_str}.md)）

{latest}

## 歷史清單

{history}

---
設定檔：`config.yaml`　｜　Anki 匯入：分隔符號選「分號」，欄位為 單字;中文意思;例句
"""
    (ROOT / "README.md").write_text(content, encoding="utf-8")


# --------------------------------------------------------------------------
# 執行記錄：logs/YYYY-MM-DD.json（每次執行一筆）+ logs/summary.md（總表）
# --------------------------------------------------------------------------
def write_run_log(date_str: str, run: dict) -> None:
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    path = logs / f"{date_str}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        data = {"date": date_str, "runs": []}
    data["runs"].append(run)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    update_log_summary()


def update_log_summary() -> None:
    files = sorted((ROOT / "logs").glob("2*.json"), reverse=True)
    rows, stats = [], {}
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        runs = data.get("runs", [])
        if not runs:
            continue
        last = runs[-1]
        feeds = last.get("feeds", [])
        ok = [x for x in feeds if x["status"] == "ok"]
        bad = [x["name"] for x in feeds if x["status"] != "ok"]
        g = last.get("gemini", {})
        fails = sum(1 for a in g.get("attempts", []) if a["result"] != "ok")
        status = "✅ 成功" if last["status"] == "success" else "❌ 失敗"
        err = "" if last["status"] == "success" else md_cell(last.get("error") or "")[:80]
        rows.append(
            f"| [{data['date']}]({f.name}) | {status} | {len(ok)}/{len(feeds)}"
            f"{'（' + '、'.join(bad) + ' 異常）' if bad else ''}"
            f"{'，用了備援' if last.get('fallback_used') else ''} | {g.get('used_model') or '-'} | {fails} | "
            f"{last.get('seconds', '-')} | {len(runs)} | {err} |"
        )
        for r in runs:  # 各來源可靠度：累計所有執行
            for x in r.get("feeds", []):
                s = stats.setdefault(x["name"], [0, 0])
                s[0 if x["status"] == "ok" else 1] += 1
    src_rows = [f"| {n} | {a} | {b} |" for n, (a, b) in sorted(stats.items())]
    text = "\n".join([
        "# 執行記錄總表", "",
        "每次執行的詳細過程見同資料夾的 `YYYY-MM-DD.json`（每個 RSS 的狀態、選出的新聞、Gemini 嘗試過程）。", "",
        "## 每日狀態（取當天最後一次執行）", "",
        "| 日期 | 結果 | RSS 成功 | 使用模型 | Gemini 失敗次數 | 耗時(秒) | 當天執行次數 | 錯誤 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |", *rows, "",
        "## 各來源累計狀況", "",
        "| 來源 | 成功次數 | 異常次數 |", "| --- | --- | --- |", *src_rows, "",
    ])
    (ROOT / "logs" / "summary.md").write_text(text, encoding="utf-8")


def main() -> int:
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    tz = timezone(timedelta(hours=cfg["timezone_offset"]))
    started = datetime.now(tz)
    date_str = started.strftime("%Y-%m-%d")
    t0 = time.time()
    status, error = "success", None
    try:
        run_pipeline(cfg, date_str)
    except Exception as e:  # noqa: BLE001
        status, error = "failed", f"{type(e).__name__}: {short(e, 300)}"
        print(f"[ERROR] {error}", file=sys.stderr)
    run = {
        "started_at": started.isoformat(timespec="seconds"),
        "seconds": round(time.time() - t0, 1),
        "status": status,
        "error": error,
        "run_trigger": os.environ.get("GITHUB_EVENT_NAME", "local"),
        "run_url": (f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
                    if os.environ.get("GITHUB_RUN_ID") else None),
        **LOG,
    }
    write_run_log(date_str, run)
    return 0 if status == "success" else 1


def run_pipeline(cfg: dict, date_str: str) -> None:
    news = collect_news(cfg)
    print(f"[INFO] 選出 {len(news)} 則新聞")
    result = call_gemini(build_prompt(news, cfg), cfg)

    (ROOT / "news").mkdir(exist_ok=True)
    (ROOT / "news_en").mkdir(exist_ok=True)
    (ROOT / "anki").mkdir(exist_ok=True)
    (ROOT / "news_en" / f"{date_str}.md").write_text(render_markdown_en(date_str, news, result), encoding="utf-8")
    (ROOT / "news" / f"{date_str}.md").write_text(render_markdown(date_str, news, result), encoding="utf-8")
    write_anki(ROOT / "anki" / f"{date_str}.csv", result)
    update_readme(date_str, [it.title_en for it in result.items], cfg.get("site_url"))
    try:  # 語音與網站失敗不影響日報本身
        import site_gen
        tts_cfg = cfg.get("tts", {})
        if tts_cfg.get("enabled"):
            audio, report = site_gen.build_audio(date_str, result.model_dump()["items"], tts_cfg)
        else:
            audio, report = {}, {"enabled": False}
        LOG["tts"] = report
        print(f"[INFO] 語音: {report}")
        site_gen.build_site(date_str, news, result.model_dump(), audio)
    except Exception as e:  # noqa: BLE001
        LOG["tts"] = {**LOG.get("tts", {}), "site_error": short(e)}
        print(f"[WARN] 網站 / 語音產生失敗: {e}", file=sys.stderr)
    print(f"[OK] 已輸出 news/{date_str}.md、news_en/{date_str}.md、anki/{date_str}.csv、README.md")


if __name__ == "__main__":
    sys.exit(main())
