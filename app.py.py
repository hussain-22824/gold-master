from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import html
import math
import re
from urllib.parse import quote

import feedparser
import numpy as np
import pandas as pd
import yfinance as yf
from flask import Flask, jsonify, render_template_string, request
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

app = Flask(__name__)

# Yahoo symbols are convenient proxies. Replace them with your licensed broker/data adapter.
WATCHLIST = {
    "XAUUSD": {"ticker": "GC=F", "name": "Gold", "asset": "Metal"},
    "XAGUSD": {"ticker": "SI=F", "name": "Silver", "asset": "Metal"},
    "EURUSD": {"ticker": "EURUSD=X", "name": "Euro / US Dollar", "asset": "Forex"},
    "GBPUSD": {"ticker": "GBPUSD=X", "name": "Pound / US Dollar", "asset": "Forex"},
    "USDJPY": {"ticker": "JPY=X", "name": "US Dollar / Yen", "asset": "Forex"},
    "SPX": {"ticker": "^GSPC", "name": "S&P 500", "asset": "Index"},
    "NDX": {"ticker": "^NDX", "name": "Nasdaq 100", "asset": "Index"},
    "USOIL": {"ticker": "CL=F", "name": "WTI Crude Oil", "asset": "Energy"},
}

RSS_FEEDS = [
    ("Google News · geopolitics markets", "https://news.google.com/rss/search?q=geopolitics+markets+war+sanctions+tariffs+central+bank&hl=en-US&gl=US&ceid=US:en"),
    ("Google News · metals forex stocks", "https://news.google.com/rss/search?q=gold+silver+forex+stocks+market+breaking+news&hl=en-US&gl=US&ceid=US:en"),
    ("Google News · macroeconomics", "https://news.google.com/rss/search?q=Federal+Reserve+ECB+BOJ+inflation+interest+rates+markets&hl=en-US&gl=US&ceid=US:en"),
]

analyzer = SentimentIntensityAnalyzer()

PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Macro Signal Desk</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<style>
:root{--bg:#0c1016;--panel:#151b24;--line:#2b3544;--text:#f4f0e7;--muted:#97a3b3;--gold:#d9ad58;--green:#54d29a;--red:#ff7474;--blue:#80aaff;--amber:#e7b45f}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 90% 0,#302719 0,#0c1016 38%);color:var(--text);font:14px Arial,sans-serif}.wrap{max-width:1400px;margin:auto;padding:28px 18px}.top{display:flex;justify-content:space-between;gap:18px;align-items:end}.eyebrow{color:var(--gold);font-size:11px;font-weight:bold;letter-spacing:2px}.top h1{font-size:42px;letter-spacing:-2px;margin:9px 0}.top p{color:var(--muted);margin:0}.controls{display:flex;gap:10px;align-items:center}.controls select,.controls button{background:var(--panel);color:var(--text);border:1px solid var(--line);padding:11px 13px;border-radius:9px}.controls button{cursor:pointer;color:var(--gold)}.layout{display:grid;grid-template-columns:1.4fr .8fr;gap:16px;margin-top:32px}.card{background:rgba(21,27,36,.94);border:1px solid var(--line);border-radius:15px;padding:18px}.full{grid-column:1/-1}.head{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}.head h2,.head h3{margin:0;font-size:16px}.head span,.meta{color:var(--muted);font-size:11px}.table-wrap{overflow:auto}.signals{width:100%;border-collapse:collapse}.signals th{color:var(--muted);font-size:10px;text-transform:uppercase;text-align:left;letter-spacing:1px}.signals td,.signals th{padding:13px 9px;border-bottom:1px solid var(--line);white-space:nowrap}.signals tr{cursor:pointer}.signals tr:hover{background:#ffffff08}.badge{display:inline-block;padding:5px 8px;border-radius:99px;font:700 11px monospace}.BUY{background:#163d2f;color:var(--green)}.SELL{background:#4b2229;color:var(--red)}.WAIT{background:#40341e;color:var(--amber)}.score{font-family:monospace;color:var(--blue)}.chartbox{height:355px}.news{max-height:390px;overflow:auto}.news article{padding:13px 0;border-bottom:1px solid var(--line)}.news a{color:var(--text);text-decoration:none;line-height:1.45}.news a:hover{color:var(--gold)}.news small{display:block;color:var(--muted);margin-top:6px}.risk{display:inline-block;font:11px monospace;margin-left:8px}.risk-high{color:var(--red)}.risk-mid{color:var(--amber)}.risk-low{color:var(--green)}.reason{color:var(--muted);line-height:1.6;margin:0;padding-left:18px}.notice{border-top:1px solid var(--line);color:var(--muted);font-size:11px;line-height:1.7;margin-top:18px;padding-top:17px}.notice strong{color:var(--gold)}.error{color:var(--red)}@media(max-width:900px){.layout{grid-template-columns:1fr}.full{grid-column:auto}.top{display:block}.controls{margin-top:18px;justify-content:space-between}}
</style></head><body><main class="wrap">
<header class="top"><div><div class="eyebrow">CAPSTONIC · MACRO CONFIRMATION DESK</div><h1>Markets under pressure.</h1><p>Technical alignment plus geopolitical headline risk across metals, forex, indices and energy.</p></div><div class="controls"><select id="asset"><option value="ALL">All markets</option><option value="Metal">Metals</option><option value="Forex">Forex</option><option value="Index">Indices</option><option value="Energy">Energy</option></select><button onclick="loadAll()">Refresh data</button></div></header>
<section class="layout"><article class="card full"><div class="head"><h2>Confirmed signal board</h2><span id="updated">Loading…</span></div><div class="table-wrap"><table class="signals"><thead><tr><th>Market</th><th>Signal</th><th>Confidence</th><th>Price</th><th>15m</th><th>1h</th><th>News risk</th><th>Reason</th></tr></thead><tbody id="rows"><tr><td colspan="8">Fetching market data…</td></tr></tbody></table></div></article>
<article class="card"><div class="head"><h3>Selected market chart</h3><span id="selected">XAUUSD</span></div><div class="chartbox"><canvas id="chart"></canvas></div></article>
<article class="card"><div class="head"><h3>Geopolitical & macro news</h3><span id="newsStatus">Loading…</span></div><div class="news" id="news"><p class="meta">Fetching headlines…</p></div></article>
<article class="card full"><div class="head"><h3>How confirmation works</h3><span>Rule transparency</span></div><ul class="reason"><li>Trend: EMA 20 versus EMA 50.</li><li>Momentum: RSI 14 and MACD direction.</li><li>Confirmation: 15-minute and 1-hour signals must agree.</li><li>News filter: recent headline sentiment and risk keywords can downgrade BUY/SELL to WAIT.</li><li>Risk map: ATR-based stop and 2R target are estimates, not promises.</li></ul><div class="notice"><strong>Important:</strong> This dashboard cannot see every event, verify every headline, or guarantee market direction. RSS headlines may be delayed, duplicated, incomplete, or wrong. Use a licensed real-time data/news provider, test in a demo account, and add risk limits before any real-money use. This app does not place trades.</div></article></section></main>
<script>
let allData=[], selected='XAUUSD', chart=null; const $=id=>document.getElementById(id); const f=x=>Number(x).toFixed(2);
function renderRows(){const filter=$('asset').value;const rows=allData.filter(x=>filter==='ALL'||x.asset===filter);$('rows').innerHTML=rows.map(x=>`<tr onclick="selectMarket('${x.symbol}')"><td><b>${x.symbol}</b><br><span class="meta">${x.name}</span></td><td><span class="badge ${x.action}">${x.action}</span></td><td>${x.confidence}%</td><td>${f(x.price)}</td><td>${x.tf15m.action}</td><td>${x.tf1h.action}</td><td><span class="risk risk-${x.news_risk.level}">${x.news_risk.label}</span></td><td>${x.reason}</td></tr>`).join('')||'<tr><td colspan="8">No markets available.</td></tr>'}
function draw(c){const x=c.find(v=>v.symbol===selected)||c[0];if(!x)return;$('selected').textContent=x.symbol;if(chart)chart.destroy();chart=new Chart($('chart'),{type:'line',data:{labels:x.chart.map(v=>new Date(v.time).toLocaleTimeString()),datasets:[{data:x.chart.map(v=>v.close),borderColor:'#d9ad58',backgroundColor:'#d9ad5830',fill:true,tension:.2,pointRadius:0}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{display:false},y:{grid:{color:'#2b3544'},ticks:{color:'#97a3b3'}}}}})}
function selectMarket(s){selected=s;draw(allData)}
async function loadAll(){try{const [s,n]=await Promise.all([fetch('/api/signals'),fetch('/api/news')]);allData=await s.json();renderRows();draw(allData);const news=await n.json();$('newsStatus').textContent=(`${news.items.length} headlines`);$('news').innerHTML=news.items.map(x=>`<article><a href="${x.link}" target="_blank" rel="noopener">${x.title}</a><small>${x.source} · ${new Date(x.published).toLocaleString()} <span class="risk risk-${x.risk_level}">${x.risk_label}</span></small></article>`).join('')||'<p class="meta">No headlines returned.</p>';$('updated').textContent='Updated '+new Date().toLocaleTimeString()}catch(e){$('rows').innerHTML='<tr><td colspan="8" class="error">Could not load data: '+e.message+'</td></tr>';$('news').innerHTML='<p class="error">Could not load news.</p>'}}
$('asset').onchange=renderRows;loadAll();setInterval(loadAll,300000);
</script></body></html>'''


def clean_title(value: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", value or "")).strip()


def news_items() -> list[dict]:
    items = []
    seen = set()
    for source, url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:20]:
                title = clean_title(entry.get("title", ""))
                link = entry.get("link", "")
                if not title or link in seen:
                    continue
                seen.add(link)
                raw = f"{title} {entry.get('summary','')}".lower()
                score = analyzer.polarity_scores(title)["compound"]
                high_risk = any(k in raw for k in ["war", "invasion", "missile", "sanction", "tariff", "attack", "crisis", "default", "coup", "nuclear", "blockade"])
                level = "high" if high_risk else ("mid" if abs(score) >= .25 else "low")
                label = "HIGH RISK" if level == "high" else ("MIXED" if level == "mid" else "LOW RISK")
                published = entry.get("published", datetime.now(timezone.utc).isoformat())
                try:
                    published = parsedate_to_datetime(published).isoformat()
                except Exception:
                    pass
                items.append({"title":title,"link":link,"source":source,"published":published,"score":score,"risk_level":level,"risk_label":label})
        except Exception:
            continue
    return sorted(items, key=lambda x: x["published"], reverse=True)[:35]


def candles(ticker: str, interval: str) -> pd.DataFrame:
    period = "5d" if interval == "15m" else "1mo"
    frame = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=False, threads=False)
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    frame.columns = [str(c).lower() for c in frame.columns]
    frame = frame.dropna(subset=["open", "high", "low", "close"])
    if len(frame) < 60:
        raise RuntimeError(f"Insufficient candles for {ticker} {interval}")
    return frame


def technical(frame: pd.DataFrame) -> dict:
    d = frame.copy(); close = d["close"].astype(float)
    d["ema20"] = close.ewm(span=20, adjust=False).mean(); d["ema50"] = close.ewm(span=50, adjust=False).mean()
    delta = close.diff(); gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean(); loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    d["rsi"] = (100 - 100/(1 + gain/loss.replace(0, np.nan))).fillna(50)
    fast = close.ewm(span=12, adjust=False).mean(); slow = close.ewm(span=26, adjust=False).mean(); d["macd"] = fast-slow
    score = 0; reasons=[]
    if d.iloc[-1].ema20 > d.iloc[-1].ema50: score += 1; reasons.append("EMA trend up")
    else: score -= 1; reasons.append("EMA trend down")
    if 52 <= d.iloc[-1].rsi <= 68: score += 1; reasons.append("RSI bullish")
    elif 32 <= d.iloc[-1].rsi <= 48: score -= 1; reasons.append("RSI bearish")
    else: reasons.append("RSI not confirming")
    if d.iloc[-1].macd > 0: score += 1; reasons.append("MACD positive")
    else: score -= 1; reasons.append("MACD negative")
    action = "BUY" if score >= 2 else ("SELL" if score <= -2 else "WAIT")
    return {"action":action,"score":score,"price":float(d.iloc[-1].close),"rsi":float(d.iloc[-1].rsi),"atr":float((d.high-d.low).ewm(alpha=1/14,adjust=False).mean().iloc[-1]),"reasons":reasons,"chart":[{"time":i.isoformat(),"close":float(v)} for i,v in d.tail(100)["close"].items()]}


def market_signal(symbol: str, spec: dict) -> dict:
    short = technical(candles(spec["ticker"], "15m")); long = technical(candles(spec["ticker"], "1h"))
    aligned = short["action"] == long["action"] and short["action"] in ("BUY", "SELL")
    action = short["action"] if aligned else "WAIT"
    reasons = ["15m and 1h agree: confirmation passed"] if aligned else ["15m and 1h do not agree: confirmation failed"]
    reasons += short["reasons"][:2]
    price = short["price"]; atr = max(short["atr"], price * .001)
    stop = price - 1.5*atr if action == "BUY" else price + 1.5*atr if action == "SELL" else price
    target = price + 3*atr if action == "BUY" else price - 3*atr if action == "SELL" else price
    return {"symbol":symbol,"name":spec["name"],"asset":spec["asset"],"action":action,"confidence":80 if aligned else 45,"price":price,"entry":price,"stop_loss":stop,"take_profit":target,"tf15m":{"action":short["action"],"score":short["score"]},"tf1h":{"action":long["action"],"score":long["score"]},"reason":reasons[0],"chart":short["chart"]}


@app.get("/")
def home(): return render_template_string(PAGE)

@app.get("/health")
def health(): return jsonify({"status":"ok","service":"macro-signal-desk"})

@app.get("/api/news")
def news(): return jsonify({"items":news_items(),"generated_at":datetime.now(timezone.utc).isoformat()})

@app.get("/api/signals")
def signals():
    output=[]
    for symbol,spec in WATCHLIST.items():
        try:
            item=market_signal(symbol,spec)
            headlines=news_items()
            high=sum(1 for x in headlines[:12] if x["risk_level"]=="high")
            item["news_risk"]={"level":"high" if high>=3 else "mid" if high else "low","label":"HIGH RISK" if high>=3 else "WATCH" if high else "LOW"}
            if item["action"] in ("BUY","SELL") and item["news_risk"]["level"]=="high": item["action"]="WAIT"; item["confidence"]=40; item["reason"]="News risk filter downgraded the technical signal"
            output.append(item)
        except Exception as exc:
            output.append({"symbol":symbol,"name":spec["name"],"asset":spec["asset"],"action":"WAIT","confidence":0,"price":0,"tf15m":{"action":"ERROR"},"tf1h":{"action":"ERROR"},"news_risk":{"level":"mid","label":"DATA ERROR"},"reason":str(exc),"chart":[]})
    return jsonify(output)

if __name__ == "__main__": app.run(host="0.0.0.0", port=5000, debug=False)
