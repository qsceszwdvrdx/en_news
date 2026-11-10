"""網站的 HTML / CSS / JS（純靜態，不依賴外部資源）。"""
from __future__ import annotations

import html
from datetime import datetime

WEEK = "一二三四五六日"

CSS = """
:root{
  --bg:#f6f7fb;--surface:#fff;--surface2:#f1f3f9;--fg:#1b1f2a;--muted:#667085;--line:#e4e7ee;
  --accent:#4f46e5;--accent-soft:#eef0ff;--accent-fg:#fff;--ok:#059669;--ok-soft:#e7f8f1;--warn-soft:#fff6e0;
  --shadow:0 1px 2px rgba(16,24,40,.06),0 4px 14px rgba(16,24,40,.05);--r:16px
}
@media (prefers-color-scheme:dark){:root{
  --bg:#0e1017;--surface:#171a24;--surface2:#1e2230;--fg:#e8eaf0;--muted:#9aa3b5;--line:#2a2f3f;
  --accent:#8b8dff;--accent-soft:#232648;--accent-fg:#0e1017;--ok:#34d399;--ok-soft:#14302a;--warn-soft:#2d2716;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 4px 14px rgba(0,0,0,.25)}}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html{scroll-behavior:smooth;scroll-padding-top:84px}
body{margin:0;background:var(--bg);color:var(--fg);
  font:16px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang TC","Noto Sans TC","Microsoft JhengHei",sans-serif}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.wrap{max-width:1080px;margin:0 auto;padding:0 16px 80px}
svg.i{width:1em;height:1em;fill:currentColor;vertical-align:-.125em}

/* header */
.top{display:flex;align-items:center;justify-content:space-between;padding:18px 0 6px;gap:12px}
.brand{font-weight:800;letter-spacing:-.01em;color:var(--fg)}
.brand small{display:block;font-weight:500;color:var(--muted);font-size:.78rem;letter-spacing:0}
.hero{padding:10px 0 4px}
.hero h1{font-size:clamp(1.7rem,5vw,2.3rem);line-height:1.2;margin:.2rem 0;letter-spacing:-.02em}
.hero .sub{color:var(--muted);margin:0}
.daynav{display:flex;gap:8px}
.pill{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);background:var(--surface);color:var(--fg);
  border-radius:999px;padding:6px 14px;font-size:.88rem;cursor:pointer;font-family:inherit;line-height:1.4}
.pill:hover{text-decoration:none;border-color:var(--accent)}
.pill[aria-disabled=true]{opacity:.4;pointer-events:none}

/* toolbar */
.bar{position:sticky;top:0;z-index:20;margin:14px -16px 0;padding:10px 16px;background:color-mix(in srgb,var(--bg) 88%,transparent);
  backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}
.bar-in{max-width:1080px;margin:0 auto;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.toggle{display:inline-flex;align-items:center;gap:8px;border:1px solid var(--line);background:var(--surface);border-radius:999px;
  padding:5px 12px 5px 8px;font-size:.88rem;cursor:pointer;user-select:none}
.toggle input{appearance:none;width:30px;height:18px;border-radius:99px;background:var(--line);position:relative;margin:0;cursor:pointer;transition:.2s}
.toggle input::after{content:"";position:absolute;left:2px;top:2px;width:14px;height:14px;border-radius:50%;background:#fff;transition:.2s}
.toggle input:checked{background:var(--accent)}.toggle input:checked::after{left:14px}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:999px;overflow:hidden;background:var(--surface)}
.seg button{border:0;background:none;color:var(--muted);padding:5px 11px;font-size:.84rem;cursor:pointer;font-family:inherit}
.seg button.on{background:var(--accent);color:var(--accent-fg)}
.spacer{flex:1}
.chips{display:flex;gap:8px;overflow-x:auto;padding:12px 0 2px;scrollbar-width:none}
.chips::-webkit-scrollbar{display:none}
.chip{flex:none;display:inline-flex;align-items:center;gap:8px;max-width:230px;border:1px solid var(--line);background:var(--surface);
  border-radius:12px;padding:6px 12px;font-size:.84rem;color:var(--fg)}
.chip b{display:inline-grid;place-items:center;width:20px;height:20px;border-radius:50%;background:var(--accent-soft);color:var(--accent);font-size:.75rem}
.chip span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

/* article card */
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--shadow);margin:18px 0;overflow:hidden}
.card-h{padding:20px 20px 4px;display:flex;gap:14px}
.num{flex:none;width:34px;height:34px;border-radius:10px;background:var(--accent);color:var(--accent-fg);display:grid;place-items:center;font-weight:800}
.card-h h2{font-size:1.22rem;line-height:1.35;margin:0;letter-spacing:-.01em}
.src{display:inline-flex;align-items:center;gap:6px;margin-top:8px;font-size:.8rem;color:var(--muted)}
.src a{background:var(--surface2);border-radius:6px;padding:1px 8px;color:var(--muted)}
.zh{color:var(--muted)}
.sec{padding:14px 20px}
.sec+.sec{border-top:1px dashed var(--line)}
.lbl{display:flex;align-items:center;gap:10px;font-size:.76rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0 0 8px}
.read{font-size:1.06rem;line-height:1.8}
.read-zh{margin:.4rem 0 0;font-size:.95rem}
.why{background:var(--warn-soft);border-radius:12px;padding:12px 14px}
.why p{margin:.15rem 0}

/* play buttons */
.play{flex:none;display:inline-grid;place-items:center;border:0;cursor:pointer;color:var(--accent);background:var(--accent-soft);
  width:34px;height:34px;border-radius:50%;font-size:15px;transition:transform .1s,background .2s}
.play:hover{transform:scale(1.07)}.play:active{transform:scale(.94)}
.play .pause{display:none}
.play.playing{background:var(--accent);color:var(--accent-fg)}
.play.playing .tri{display:none}.play.playing .pause{display:inline}
.play.sm{width:28px;height:28px;font-size:12px}
.playlbl{display:inline-flex;align-items:center;gap:8px;border:0;background:var(--accent-soft);color:var(--accent);font-weight:600;
  border-radius:999px;padding:5px 14px 5px 6px;cursor:pointer;font-size:.88rem;font-family:inherit;text-transform:none;letter-spacing:0}
.playlbl .play{width:26px;height:26px;font-size:11px;background:var(--accent);color:var(--accent-fg);pointer-events:none}
.playlbl.playing .play .tri{display:none}.playlbl.playing .play .pause{display:inline}

/* vocabulary */
.vgrid{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(min(100%,330px),1fr))}
.v{background:var(--surface2);border-radius:14px;padding:14px}
.v-top{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.word{font-size:1.25rem;font-weight:800;letter-spacing:-.01em}
.kk{color:var(--muted);font-size:.9rem}
.tag{font-size:.7rem;font-weight:700;border-radius:6px;padding:1px 7px;background:var(--surface);color:var(--muted);border:1px solid var(--line)}
.tag.toeic{background:var(--ok-soft);color:var(--ok);border-color:transparent}
.v-def{margin:6px 0 0}
.meaning{display:inline-block;margin-top:2px;font-weight:600}
.ex{margin-top:10px;padding:10px 12px;background:var(--surface);border-radius:10px;border-left:3px solid var(--accent);display:flex;gap:10px;align-items:flex-start}
.ex p{margin:0}.ex .en{font-size:.98rem}.ex .tr{font-size:.86rem;margin-top:2px}
.rel{margin-top:10px;display:flex;gap:6px;flex-wrap:wrap;font-size:.78rem;color:var(--muted);align-items:center}
.rel em{font-style:normal;background:var(--surface);border:1px solid var(--line);border-radius:6px;padding:0 7px;color:var(--fg)}

/* modes */
body.en-only .zh{display:none}
body.quiz .hide-q{filter:blur(7px);cursor:pointer;transition:filter .2s;user-select:none}
body.quiz .hide-q.reveal{filter:none}

/* index */
.days{display:grid;gap:14px;margin-top:18px}
.day{display:block;background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:18px 20px;box-shadow:var(--shadow);color:var(--fg)}
.day:hover{text-decoration:none;border-color:var(--accent)}
.day-h{display:flex;align-items:center;gap:4px 10px;margin-bottom:6px;flex-wrap:wrap}
.day-h>*{white-space:nowrap}
.day-h b{font-size:1.25rem;letter-spacing:-.01em}.day-h span{color:var(--muted);font-size:.88rem}
.badge{background:var(--accent);color:var(--accent-fg);border-radius:999px;font-size:.72rem;font-weight:700;padding:1px 9px}
.day ol{margin:0;padding-left:1.2rem;color:var(--muted);font-size:.92rem}
.day li{margin:2px 0;display:list-item}
.foot{margin-top:36px;text-align:center;color:var(--muted);font-size:.82rem}
@media (max-width:640px){.bar-in{flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none}.bar-in::-webkit-scrollbar{display:none}
  .bar-in>*{flex:none}.bar-in .spacer{display:none}.bar{padding:8px 16px}html{scroll-padding-top:64px}}
@media (max-width:520px){.card-h{padding:16px 16px 2px}.sec{padding:12px 16px}.chip{max-width:170px}}
"""

JS = """
const A=new Audio();let cur=null,speed=1,queue=[];
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
function setCur(b){if(cur)cur.classList.remove('playing');cur=b;if(b)b.classList.add('playing')}
function stopAll(){queue=[];A.pause();speechSynthesis.cancel();setCur(null)}
function done(b){if(cur===b)setCur(null);if(queue.length){const n=queue.shift();start(n)}}
function speak(b){const u=new SpeechSynthesisUtterance(b.dataset.text);u.lang='en-US';u.rate=speed;u.onend=()=>done(b);u.onerror=()=>done(b);speechSynthesis.speak(u)}
function start(b){A.pause();speechSynthesis.cancel();setCur(b);const s=b.dataset.src;
  if(s){A.src=s;A.playbackRate=speed;A.onended=()=>done(b);A.onerror=()=>speak(b);A.play().catch(()=>speak(b))}else speak(b)}
function play(b){if(cur===b){stopAll();return}queue=[];start(b)}
function playAll(){if(queue.length||cur){stopAll();return}
  const l=$$('.sumbtn');if(!l.length)return;queue=l.slice(1);start(l[0]);$('#all').classList.add('on')}
function setSpeed(v,btn){speed=v;A.playbackRate=v;$$('.seg button').forEach(x=>x.classList.toggle('on',x===btn));try{localStorage.sp=v}catch(e){}}
function mode(){const zh=$('#zh').checked,q=$('#quiz').checked;
  document.body.classList.toggle('en-only',!zh);document.body.classList.toggle('quiz',q);
  if(!q)$$('.reveal').forEach(x=>x.classList.remove('reveal'));
  try{localStorage.zh=zh?1:0;localStorage.quiz=q?1:0}catch(e){}}
document.addEventListener('click',e=>{const h=e.target.closest('.hide-q');if(h&&document.body.classList.contains('quiz'))h.classList.toggle('reveal')});
window.addEventListener('DOMContentLoaded',()=>{
  if($('#zh')){try{if(localStorage.zh==='0')$('#zh').checked=false;if(localStorage.quiz==='1')$('#quiz').checked=true;
    const sp=parseFloat(localStorage.sp||1);const b=$$('.seg button').find(x=>parseFloat(x.dataset.v)===sp);if(b)setSpeed(sp,b)}catch(e){}
    mode()}});
"""

ICON_PLAY = '<svg class="i tri" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg><svg class="i pause" viewBox="0 0 24 24"><path d="M6 5h4v14H6zm8 0h4v14h-4z"/></svg>'
ICON_SPK = '<svg class="i tri" viewBox="0 0 24 24"><path d="M3 10v4h4l5 4V6L7 10H3zm13.5 2A4.5 4.5 0 0 0 14 8v8a4.5 4.5 0 0 0 2.5-4zM14 3.2v2.1a7 7 0 0 1 0 13.4v2.1a9 9 0 0 0 0-17.6z"/></svg><svg class="i pause" viewBox="0 0 24 24"><path d="M6 5h4v14H6zm8 0h4v14h-4z"/></svg>'


def e(s: str) -> str:
    return html.escape(s or "", quote=True)


def pbtn(text: str, src: str | None, icon: str = ICON_PLAY, cls: str = "play", label: str = "play") -> str:
    return (f'<button class="{cls}" onclick="play(this)" data-text="{e(text)}" data-src="{e(src or "")}" '
            f'aria-label="{label}">{icon}</button>')


def page(title: str, body: str, desc: str = "") -> str:
    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light dark">
<meta name="description" content="{e(desc)}"><title>{e(title)}</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Crect width='100' height='100' rx='22' fill='%234f46e5'/%3E%3Ctext x='50' y='68' font-size='56' text-anchor='middle' fill='white' font-family='sans-serif' font-weight='700'%3EN%3C/text%3E%3C/svg%3E">
<style>{CSS}</style></head><body><div class="wrap">{body}</div><script>{JS}</script></body></html>"""


def date_label(d: str) -> tuple[str, str]:
    dt = datetime.strptime(d, "%Y-%m-%d")
    return f"{dt.month}月{dt.day}日", f"{dt.year} · 週{WEEK[dt.weekday()]}"


def render_day(data: dict, audio: dict, prev: str | None, nxt: str | None) -> str:
    d = data["date"]
    big, small = date_label(d)
    nav = (f'<a class="pill" href="{prev or "#"}{".html" if prev else ""}" aria-disabled="{"false" if prev else "true"}">← 前一天</a>'
           f'<a class="pill" href="{nxt or "#"}{".html" if nxt else ""}" aria-disabled="{"false" if nxt else "true"}">後一天 →</a>')
    p = [
        '<div class="top"><a class="brand" href="index.html">每日新聞 × 單字<small>Daily News &amp; Vocabulary</small></a>'
        f'<div class="daynav">{nav}</div></div>',
        f'<div class="hero"><h1>{e(big)}</h1><p class="sub">{e(small)} · {len(data["items"])} 則新聞 · '
        f'{sum(len(i["vocab"]) for i in data["items"])} 個單字</p></div>',
        '<div class="bar"><div class="bar-in">'
        '<button class="pill" id="all" onclick="playAll()">▶ 連播全部摘要</button>'
        '<label class="toggle"><input type="checkbox" id="zh" checked onchange="mode()">顯示中文</label>'
        '<label class="toggle"><input type="checkbox" id="quiz" onchange="mode()">單字自測</label>'
        '<span class="spacer"></span>'
        '<span class="seg" aria-label="speed"><button data-v="0.8" onclick="setSpeed(0.8,this)">0.8×</button>'
        '<button class="on" data-v="1" onclick="setSpeed(1,this)">1×</button>'
        '<button data-v="1.2" onclick="setSpeed(1.2,this)">1.2×</button></span>'
        '</div></div>',
        '<nav class="chips">' + "".join(
            f'<a class="chip" href="#n{i}"><b>{i}</b><span>{e(it["title_en"])}</span></a>'
            for i, it in enumerate(data["items"], 1)) + "</nav>",
    ]
    for i, it in enumerate(data["items"], 1):
        src = data["news"][i - 1] if i - 1 < len(data["news"]) else {}
        source = (f'<div class="src">來源 <a href="{e(src["link"])}" target="_blank" rel="noopener">{e(src["source"])} ↗</a></div>'
                  if src else "")
        s_audio = audio.get(f"n{i}-summary")
        p.append(f'<article class="card" id="n{i}"><div class="card-h"><div class="num">{i}</div><div>'
                 f'<h2>{e(it["title_en"])}</h2><div class="zh">{e(it["title_zh"])}</div>{source}</div></div>')
        p.append('<div class="sec"><div class="lbl">Summary '
                 f'<button class="playlbl sumbtn" onclick="play(this)" data-text="{e(it["summary_en"])}" data-src="{e(s_audio or "")}">'
                 f'<span class="play">{ICON_PLAY}</span>聽摘要</button></div>'
                 f'<div class="read">{e(it["summary_en"])}</div><div class="read-zh zh">{e(it["summary_zh"])}</div></div>')
        p.append('<div class="sec"><div class="why"><div class="lbl" style="margin:0">💡 Why it matters</div>'
                 f'<p>{e(it["why_important_en"])}</p><p class="zh">{e(it["why_important_zh"])}</p></div></div>')
        p.append('<div class="sec"><div class="lbl">Vocabulary</div><div class="vgrid">')
        for j, v in enumerate(it["vocab"], 1):
            toeic = '<span class="tag toeic">TOEIC</span>' if v["toeic_common"] else ""
            syn = "".join(f"<em>{e(x)}</em>" for x in v["synonyms"][:2])
            col = "".join(f"<em>{e(x)}</em>" for x in v["collocations"][:2])
            rel = ""
            if syn:
                rel += f"<span>同義</span>{syn}"
            if col:
                rel += f"<span style='margin-left:6px'>搭配</span>{col}"
            p.append(
                '<div class="v"><div class="v-top">'
                f'<span class="word">{e(v["word"])}</span><span class="kk">{e(v["kk"])}</span>'
                f'<span class="tag">{e(v["pos"])}</span>{toeic}<span class="spacer"></span>'
                f'{pbtn(v["word"], audio.get(f"n{i}-w{j}"), ICON_SPK, "play", "pronounce")}</div>'
                f'<p class="v-def">{e(v["definition_en"])}</p>'
                f'<div class="zh"><span class="meaning hide-q">{e(v["meaning_zh"])}</span></div>'
                f'<div class="ex">{pbtn(v["sentence_en"], audio.get(f"n{i}-w{j}-ex"), ICON_PLAY, "play sm", "play example")}'
                f'<div><p class="en">{e(v["sentence_en"])}</p><p class="tr zh hide-q">{e(v["sentence_zh"])}</p></div></div>'
                f'<div class="rel">{rel}</div></div>')
        p.append("</div></div></article>")
    p.append('<div class="foot">語音由 edge-tts 產生 · <a href="https://github.com/qsceszwdvrdx/en_news">GitHub</a></div>')
    return page(f"{big} 每日新聞 × 單字", "".join(p), "每日英文新聞摘要、語音與多益單字")


def render_index(days: list[tuple[str, list[str], int]]) -> str:
    cards = []
    for k, (d, titles, nvocab) in enumerate(days):
        big, small = date_label(d)
        badge = '<span class="badge">最新</span>' if k == 0 else ""
        lis = "".join(f"<li>{e(t)}</li>" for t in titles[:5])
        cards.append(f'<a class="day" href="{d}.html"><div class="day-h"><b>{e(big)}</b><span>{e(small)}</span>{badge}'
                     f'<span class="spacer"></span><span>{nvocab} 個單字</span></div><ol>{lis}</ol></a>')
    body = ('<div class="top"><span class="brand">每日新聞 × 單字<small>Daily News &amp; Vocabulary</small></span></div>'
            '<div class="hero"><h1>每天 5 則英文新聞<br>邊讀邊學多益單字</h1>'
            '<p class="sub">每天台灣時間 07:00 自動更新 · 英文語音 · 中英對照 · 單字自測</p></div>'
            f'<div class="days">{"".join(cards)}</div>'
            '<div class="foot"><a href="https://github.com/qsceszwdvrdx/en_news">GitHub</a></div>')
    return page("每日新聞 × 單字學習", body, "每天 5 則英文新聞、語音、多益單字")
