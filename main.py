#!/usr/bin/env python3
"""每日新聞 × 單字學習：抓 RSS -> Gemini 一次處理 -> 輸出 Markdown / Anki CSV / README。"""
from __future__ import annotations

import csv
import html
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


# --------------------------------------------------------------------------
# Gemini 回傳的 JSON 結構
# --------------------------------------------------------------------------
class Vocab(BaseModel):
    word: str
    pos: str                  # 詞性
    kk: str                   # KK 音標
    meaning_zh: str
    sentence_en: str          # 新聞原句
    sentence_zh: str
    synonyms: List[str]       # 1–2 個
    collocations: List[str]   # 1–2 個
    toeic_common: bool


class NewsItem(BaseModel):
    index: int
    title_en: str
    title_zh: str
    summary_zh: str
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
    try:
        parsed = feedparser.parse(feed["url"], agent=USER_AGENT)
        if parsed.bozo and not parsed.entries:
            raise RuntimeError(parsed.get("bozo_exception"))
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] 跳過來源 {feed['name']}: {e}", file=sys.stderr)
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
        picked.append(max(c, key=lambda x: len(x["summary"])))
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
        articles.extend(fetch_feed(cfg["fallback_feed"], cutoff))

    # 同連結去重
    seen_links, deduped = set(), []
    for a in articles:
        if a["link"] not in seen_links:
            seen_links.add(a["link"])
            deduped.append(a)

    picked = cluster_and_pick(deduped, n)
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
- summary_zh：3 句以內的繁體中文摘要（只根據提供的內容，不要編造細節）
- why_important_zh：為什麼重要（繁體中文，1–2 句）
- vocab：挑 {cfg['learner']['words_per_news']} 個「多益常考、日常實用」的單字；略過太艱深的專業術語、專有名詞、人名地名。每個單字：
  - word（原形）、pos（詞性，如 n. / v. / adj.）、kk（KK 音標，如 [ˈkraɪsɪs]）、meaning_zh（繁體中文意思，貼合句中用法）
  - sentence_en：必須是上面提供的標題或內文中「實際出現」該單字的原句；sentence_zh：該句中文翻譯
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
    for model in models:
        for attempt in range(g["max_retries"] + 1):
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
                print(f"[INFO] 使用模型 {model}")
                return resp.parsed if isinstance(resp.parsed, DailyResult) else DailyResult.model_validate_json(resp.text)
            except errors.APIError as e:
                last_err = e
                code = getattr(e, "code", None)
                if code in (429, 503) and attempt < g["max_retries"]:
                    print(f"[WARN] {model} {code}，{g['retry_wait_seconds']} 秒後重試 ({attempt + 1}/{g['max_retries']})", file=sys.stderr)
                    time.sleep(g["retry_wait_seconds"])
                    continue
                print(f"[WARN] 模型 {model} 失敗: {code}", file=sys.stderr)
                break
            except Exception as e:  # noqa: BLE001  (例如 JSON 解析失敗)
                last_err = e
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
    out = [f"# 每日新聞 × 單字學習 — {date_str}", ""]
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
            f"**摘要**：{it.summary_zh}",
            "",
            f"**為什麼重要**：{it.why_important_zh}",
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


def update_readme(date_str: str, news_titles: list) -> None:
    dates = sorted((p.stem for p in (ROOT / "news").glob("*.md")), reverse=True)
    latest = "\n".join(f"{i}. {t}" for i, t in enumerate(news_titles, 1))
    history = "\n".join(f"- [{d}](news/{d}.md)（[Anki](anki/{d}.csv)）" for d in dates)
    content = f"""# 每日新聞 × 單字學習

每天台灣時間 07:00 由 GitHub Actions 自動產生 5 則英文新聞、中文摘要與多益單字。

## 最新一期：[{date_str}](news/{date_str}.md)

{latest}

## 歷史清單

{history}

---
設定檔：`config.yaml`　｜　Anki 匯入：分隔符號選「分號」，欄位為 單字;中文意思;例句
"""
    (ROOT / "README.md").write_text(content, encoding="utf-8")


def main() -> int:
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    tz = timezone(timedelta(hours=cfg["timezone_offset"]))
    date_str = datetime.now(tz).strftime("%Y-%m-%d")

    news = collect_news(cfg)
    print(f"[INFO] 選出 {len(news)} 則新聞")
    result = call_gemini(build_prompt(news, cfg), cfg)

    (ROOT / "news").mkdir(exist_ok=True)
    (ROOT / "anki").mkdir(exist_ok=True)
    (ROOT / "news" / f"{date_str}.md").write_text(render_markdown(date_str, news, result), encoding="utf-8")
    write_anki(ROOT / "anki" / f"{date_str}.csv", result)
    update_readme(date_str, [it.title_en for it in result.items])
    print(f"[OK] 已輸出 news/{date_str}.md、anki/{date_str}.csv、README.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
