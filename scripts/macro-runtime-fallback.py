import csv
import datetime as dt
import io
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MACRO_PATH = os.path.join(REPO_ROOT, "data", "macro-latest.json")
REPORTS_DIR = os.path.join(REPO_ROOT, "reports")
HTTP_PROXY = os.environ.get("HTTP_PROXY") or "http://127.0.0.1:10808"
HTTPS_PROXY = os.environ.get("HTTPS_PROXY") or "http://127.0.0.1:10808"
PROXY = urllib.request.ProxyHandler({"http": HTTP_PROXY, "https": HTTPS_PROXY})
OPENER = urllib.request.build_opener(PROXY)

MONTHLY_START = "2020-01-01"
HIGH_FREQ_START = "2025-01-01"
YAHOO_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json,text/plain,*/*",
}

ASSET_DEFINITIONS = [
    {"key": "gold", "name": "国际金价", "symbol": "GC=F", "unit": "美元/盎司"},
    {"key": "silver", "name": "白银", "symbol": "SI=F", "unit": "美元/盎司"},
    {"key": "wti", "name": "WTI 原油", "symbol": "CL=F", "unit": "美元/桶"},
    {"key": "brent", "name": "Brent 原油", "symbol": "BZ=F", "unit": "美元/桶"},
    {"key": "copper", "name": "铜", "symbol": "HG=F", "unit": "美元/磅"},
    {"key": "dxy", "name": "美元指数 DXY", "symbol": "DX-Y.NYB", "unit": "点"},
    {"key": "vix", "name": "VIX", "symbol": "^VIX", "unit": "点"},
    {"key": "spx", "name": "标普500", "symbol": "^GSPC", "unit": "点"},
    {"key": "nasdaq", "name": "纳斯达克", "symbol": "^IXIC", "unit": "点"},
    {"key": "usdjpy", "name": "USD/JPY", "symbol": "USDJPY=X", "unit": "汇率"},
    {"key": "btc", "name": "BTC", "symbol": "BTC-USD", "unit": "美元"},
    {"key": "eth", "name": "ETH", "symbol": "ETH-USD", "unit": "美元"},
]

PRICE_NOTES = {
    "国际金价": "Yahoo Finance GC=F，作为伦敦金现货近似观察，{date}",
    "白银": "Yahoo Finance，{date}",
    "WTI 原油": "Yahoo Finance，{date}",
    "Brent 原油": "Yahoo Finance BZ=F，{date}",
    "铜": "Yahoo Finance HG=F，增长晴雨表，{date}",
    "美元指数 DXY": "Yahoo Finance DX-Y.NYB，金/币/新兴市场反向锚，{date}",
    "VIX": "Yahoo Finance ^VIX，股市波动率风险温度计，{date}",
    "标普500": "Yahoo Finance ^GSPC，{date}",
    "纳斯达克": "Yahoo Finance ^IXIC，{date}",
    "USD/JPY": "Yahoo Finance USDJPY=X，日元套利/全球流动性观察，{date}",
    "BTC": "Yahoo Finance，{date}",
    "ETH": "Yahoo Finance，{date}",
}


def load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def request_text(url, timeout=30, headers=None, retries=3, pause=1.0):
    last_error = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers=headers or {})
            with OPENER.open(request, timeout=timeout) as response:
                return response.read().decode("utf-8")
        except Exception as error:
            last_error = error
            if attempt + 1 < retries:
                time.sleep(pause * (attempt + 1))
    raise last_error


def request_json(url, timeout=30, headers=None, retries=3, pause=1.0):
    return json.loads(request_text(url, timeout=timeout, headers=headers, retries=retries, pause=pause))


def read_report_for_today():
    today = dt.datetime.now().strftime("%Y-%m-%d")
    report_path = os.path.join(REPORTS_DIR, f"{today}.json")
    if not os.path.exists(report_path):
        return None
    return load_json(report_path)


def fred_csv(series_id, start_date):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start_date}"
    text = request_text(url, timeout=25, retries=3, pause=1.5)
    rows = []
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        value_text = row.get(series_id, ".")
        if value_text in (".", "", None):
            continue
        rows.append({"date": row["observation_date"], "value": float(value_text)})
    if not rows:
        raise ValueError(f"FRED {series_id} returned no usable rows")
    return rows


def pct_change(current, previous):
    if previous in (None, 0):
        return None
    return (current / previous - 1) * 100


def first_number(value):
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value or ""))
    return float(match.group(0)) if match else None


def find_event(events, item_id):
    return next((item for item in events if item.get("id") == item_id), None)


def find_metric(metrics, name):
    return next((item for item in metrics if item.get("name") == name), None)


def update_metric(metrics, name, payload):
    for index, item in enumerate(metrics):
        if item.get("name") == name:
            merged = dict(item)
            merged.update(payload)
            metrics[index] = merged
            return
    metrics.append(payload)


def update_event(events, item_id, payload):
    for index, item in enumerate(events):
        if item.get("id") == item_id:
            merged = dict(item)
            merged.update(payload)
            events[index] = merged
            return
    events.append(payload)


def compare_text(current, previous, higher_text, lower_text, same_text):
    if current > previous:
        return higher_text
    if current < previous:
        return lower_text
    return same_text


def format_signed(value, digits=0, unit=""):
    return f"{value:+.{digits}f}{unit}"


def build_us_events(base_events, failures):
    try:
        rows = fred_csv("PAYEMS", MONTHLY_START)
        current = rows[-1]["value"] - rows[-2]["value"]
        previous = rows[-2]["value"] - rows[-3]["value"]
        update_event(
            base_events,
            "fred-payems",
            {
                "date": rows[-1]["date"],
                "period": rows[-1]["date"],
                "actual": f"{current:+.0f} 千人",
                "previous": f"{previous:+.0f} 千人",
                "expected": "官方源无预期",
                "surprise": compare_text(current, previous, "较上月多增", "较上月少增", "与上月持平"),
                "source": "FRED PAYEMS",
                "notes": "FRED 官方 CSV，无需 API key；PAYEMS 为非农就业总人数，脚本用环比差值计算新增就业。",
            },
        )
    except Exception as error:
        failures.append(f"FRED PAYEMS fallback failed: {error}")

    for series_id, item_id, title, notes in [
        ("CPIAUCSL", "fred-cpi-yoy", "CPI 同比", "FRED 官方 CSV，无需 API key；用 CPI 指数计算 12 个月同比。"),
        ("PCEPI", "fred-pce-yoy", "PCE 同比", "FRED PCEPI 计算 12 个月同比；PCE 是美联储更关注的通胀口径。"),
        ("PCEPILFE", "fred-core-pce-yoy", "核心 PCE 同比", "FRED PCEPILFE 计算 12 个月同比；核心 PCE 是美联储偏好的通胀指标。"),
    ]:
        try:
            rows = fred_csv(series_id, MONTHLY_START)
            current = (rows[-1]["value"] / rows[-13]["value"] - 1) * 100
            previous = (rows[-2]["value"] / rows[-14]["value"] - 1) * 100
            update_event(
                base_events,
                item_id,
                {
                    "date": rows[-1]["date"],
                    "period": rows[-1]["date"],
                    "title": title,
                    "actual": f"{current:.1f}%",
                    "previous": f"{previous:.1f}%",
                    "expected": "官方源无预期",
                    "surprise": compare_text(current, previous, "较上月升温", "较上月回落", "与上月持平"),
                    "source": f"FRED {series_id}",
                    "notes": notes,
                },
            )
        except Exception as error:
            failures.append(f"FRED {series_id} fallback failed: {error}")

    try:
        rows = fred_csv("UNRATE", MONTHLY_START)
        current = rows[-1]["value"]
        previous = rows[-2]["value"]
        update_event(
            base_events,
            "fred-unrate",
            {
                "date": rows[-1]["date"],
                "period": rows[-1]["date"],
                "actual": f"{current:.1f}%",
                "previous": f"{previous:.1f}%",
                "expected": "官方源无预期",
                "surprise": compare_text(current, previous, "较上月上升", "较上月下降", "与上月持平"),
                "source": "FRED UNRATE",
                "notes": "FRED 官方 CSV，无需 API key；月度失业率。",
            },
        )
    except Exception as error:
        failures.append(f"FRED UNRATE fallback failed: {error}")

    try:
        rows = fred_csv("ICSA", HIGH_FREQ_START)
        current = rows[-1]["value"]
        previous = rows[-2]["value"]
        update_event(
            base_events,
            "fred-icsa",
            {
                "date": rows[-1]["date"],
                "period": rows[-1]["date"],
                "actual": f"{current / 1000:.0f} 千人",
                "previous": f"{previous / 1000:.0f} 千人",
                "expected": "官方源无预期",
                "surprise": compare_text(current, previous, "较上周上升", "较上周下降", "与上周持平"),
                "source": "FRED ICSA",
                "notes": "FRED ICSA，周度高频就业降温信号。",
            },
        )
    except Exception as error:
        failures.append(f"FRED ICSA fallback failed: {error}")


def fetch_yahoo_chart(symbol):
    encoded = urllib.parse.quote(symbol, safe="")
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{encoded}?range=1y&interval=1d&includePrePost=false&events=div%2Csplits"
    payload = request_json(url, timeout=30, headers=YAHOO_HEADERS, retries=4, pause=1.2)
    result = payload["chart"]["result"][0]
    timestamps = result.get("timestamp") or []
    closes = result["indicators"]["quote"][0]["close"]
    points = []
    for stamp, close in zip(timestamps, closes):
        if close is None:
            continue
        day = dt.datetime.utcfromtimestamp(stamp).strftime("%Y-%m-%d")
        points.append({"date": day, "value": round(float(close), 4)})
    if not points:
        raise ValueError(f"Yahoo {symbol} returned no points")
    return points


def format_price(name, value):
    if name == "国际金价":
        return f"${value:,.1f}"
    if name in ("白银", "WTI 原油", "Brent 原油", "铜"):
        return f"${value:,.2f}"
    if name in ("美元指数 DXY", "VIX", "USD/JPY"):
        return f"{value:,.2f}"
    if name in ("标普500", "纳斯达克"):
        return f"{value:,.0f}"
    return f"${value:,.0f}"


def update_prices_and_ratios(payload, failures):
    histories = []
    latest = {}
    previous = {}
    for asset in ASSET_DEFINITIONS:
        try:
            points = fetch_yahoo_chart(asset["symbol"])
            latest[asset["symbol"]] = points[-1]["value"]
            previous[asset["symbol"]] = points[-23]["value"] if len(points) >= 23 else points[0]["value"]
            histories.append(
                {
                    "key": asset["key"],
                    "name": asset["name"],
                    "symbol": asset["symbol"],
                    "unit": asset["unit"],
                    "source": "Yahoo Finance",
                    "updatedAt": points[-1]["date"],
                    "points": points,
                }
            )
            time.sleep(0.2)
        except Exception as error:
            failures.append(f"Yahoo {asset['symbol']} fallback failed: {error}")

    if len(histories) < 8:
        raise RuntimeError("Yahoo fallback fetched too few assets to trust the report")

    asset_history = {item["key"]: item for item in payload.get("assetHistory", [])}
    for item in histories:
        asset_history[item["key"]] = item
    payload["assetHistory"] = list(asset_history.values())

    latest_date = histories[0]["updatedAt"]
    prices = []
    for asset in ASSET_DEFINITIONS:
        value = latest.get(asset["symbol"])
        if value is None:
            continue
        entry = {
            "name": asset["name"],
            "value": format_price(asset["name"], value),
            "notes": PRICE_NOTES[asset["name"]].format(date=latest_date),
        }
        if asset["name"] in ("美元指数 DXY", "VIX"):
            entry["rawValue"] = value
        prices.append(entry)

    for legacy_name in ("沪金 Au99.99", "沪金主连"):
        legacy = find_metric(payload.get("prices", []), legacy_name)
        if legacy:
            prices.append(legacy)
    payload["prices"] = prices

    gold = latest.get("GC=F")
    silver = latest.get("SI=F")
    oil = latest.get("CL=F")
    btc = latest.get("BTC-USD")
    eth = latest.get("ETH-USD")
    old_gold = previous.get("GC=F")
    old_silver = previous.get("SI=F")
    old_oil = previous.get("CL=F")
    old_btc = previous.get("BTC-USD")
    old_eth = previous.get("ETH-USD")
    if None in (gold, silver, oil, btc, eth, old_gold, old_silver, old_oil, old_btc, old_eth):
        raise RuntimeError("Yahoo fallback missing core symbols for ratio calculation")

    ratio_values = {
        "金银比": gold / silver,
        "金油比": gold / oil,
        "金特比": btc / gold,
        "ETH/BTC": eth / btc,
    }
    old_ratio_values = {
        "金银比": old_gold / old_silver,
        "金油比": old_gold / old_oil,
        "金特比": old_btc / old_gold,
        "ETH/BTC": old_eth / old_btc,
    }
    ratio_notes = {
        "金银比": "黄金价格 / 白银价格；上行偏避险，下行偏工业和风险偏好修复。",
        "金油比": "黄金价格 / WTI 原油价格；噪音较大，但上行常提示增长担忧或原油走弱。",
        "金特比": "BTC 价格 / 黄金价格；上行代表 BTC 相对黄金更强，偏风险偏好。",
        "ETH/BTC": "ETH 价格 / BTC 价格；上行说明币圈内部风险偏好改善。",
    }
    payload["ratios"] = [
        {
            "name": name,
            "value": f"{value:.4f}" if name == "ETH/BTC" else (f"1 BTC ≈ {value:.1f} 盎司黄金" if name == "金特比" else f"{value:.1f}"),
            "rawValue": value,
            "changePct": pct_change(value, old_ratio_values[name]),
            "notes": ratio_notes[name],
        }
        for name, value in ratio_values.items()
    ]


def update_crypto_metrics(payload, failures):
    metrics = []
    try:
        fng = request_json("https://api.alternative.me/fng/?limit=1", timeout=20)["data"][0]
        label = {
            "Extreme Fear": "极度恐慌",
            "Fear": "恐慌",
            "Neutral": "中性",
            "Greed": "贪婪",
            "Extreme Greed": "极度贪婪",
        }.get(fng["value_classification"], fng["value_classification"])
        metrics.append(
            {
                "name": "恐慌贪婪指数",
                "value": f"{fng['value']}/100",
                "rawValue": int(fng["value"]),
                "classification": label,
                "notes": f"{label}；来源 alternative.me。",
            }
        )
    except Exception as error:
        failures.append(f"alternative.me fallback failed: {error}")

    try:
        global_data = request_json("https://api.coingecko.com/api/v3/global", timeout=20)["data"]
        market_cap = float(global_data["total_market_cap"]["usd"])
        dominance = float(global_data["market_cap_percentage"]["btc"])
        change = float(global_data.get("market_cap_change_percentage_24h_usd", 0))
        metrics.extend(
            [
                {
                    "name": "加密总市值",
                    "value": f"${market_cap / 1e12:.2f} 万亿",
                    "rawValue": market_cap,
                    "changePct": change,
                    "notes": f"24h {change:+.1f}%；来源 CoinGecko。",
                },
                {
                    "name": "BTC 市占率",
                    "value": f"{dominance:.1f}%",
                    "rawValue": dominance,
                    "notes": "BTC 市值占全市场比例；来源 CoinGecko。",
                },
            ]
        )
    except Exception as error:
        failures.append(f"CoinGecko fallback failed: {error}")

    if metrics:
        payload["cryptoMetrics"] = metrics


def update_rate_metrics(payload, failures):
    metrics = list(payload.get("rateMetrics", []))
    series = [
        ("美国2年国债收益率", "DGS2"),
        ("美国10年国债收益率", "DGS10"),
        ("美国30年国债收益率", "DGS30"),
        ("美国10Y-2Y利差", "T10Y2Y"),
        ("美国10年实际利率", "DFII10"),
        ("美国10年盈亏平衡通胀率", "T10YIE"),
    ]
    for name, series_id in series:
        try:
            rows = fred_csv(series_id, HIGH_FREQ_START)
            latest = rows[-1]
            previous = rows[-6] if len(rows) >= 6 else rows[0]
            current_value = float(latest["value"])
            previous_value = float(previous["value"])
            update_metric(
                metrics,
                name,
                {
                    "name": name,
                    "value": f"{current_value:.2f}%",
                    "rawValue": current_value,
                    "changePct": None,
                    "notes": f"FRED {series_id}，{latest['date']}；近5个交易日 {current_value - previous_value:+.2f}pct。",
                },
            )
        except Exception as error:
            failures.append(f"FRED {series_id} fallback failed: {error}")
    payload["rateMetrics"] = metrics


def infer_source(rank):
    platform = rank.get("platform") or ""
    url = rank.get("url") or ""
    if "wallstreetcn.com" in url:
        return "华尔街见闻"
    if "thepaper.cn" in url:
        return "澎湃新闻"
    if "ifeng.com" in url:
        return "凤凰网"
    if platform:
        return platform
    return "中文热榜"


def classify_buckets(text):
    lower = text.lower()
    buckets = set()
    if any(keyword in text for keyword in ["美联储", "降息", "通胀", "非农", "失业", "特朗普", "关税", "中国宏观", "社融", "LPR", "CPI", "PPI", "美元", "美债"]):
        buckets.add("macro-tide")
    if any(keyword in text for keyword in ["黄金", "原油", "战争", "地缘", "伊朗", "以色列", "VIX", "油价", "避险", "A股"]):
        buckets.add("risk-regime")
    if any(keyword in lower for keyword in ["btc", "eth", "比特币", "以太坊", "稳定币", "加密", "币圈", "etf"]):
        buckets.add("crypto-rotation")
    if any(keyword in text for keyword in ["恐慌", "贪婪", "情绪", "狂热", "暴跌", "新高", "回撤"]):
        buckets.add("sentiment-extreme")
    if not buckets:
        buckets.add("macro-tide")
    return sorted(buckets)


def summarize_news(event_text, title):
    text = f"{event_text}；{title}".strip("；")
    if any(keyword in text for keyword in ["伊朗", "以色列", "战争", "原油", "油价"]):
        return "地缘与原油风险仍在抬头，短线继续影响黄金、原油和全球风险偏好。"
    if any(keyword in text for keyword in ["特朗普", "关税", "谈判"]):
        return "特朗普与贸易/谈判叙事反复，会直接影响美元、风险资产与避险资产的切换。"
    if any(keyword in text for keyword in ["A股", "创业板", "科技", "AI"]):
        return "权益市场和科技主题的强弱，能帮助判断当前资金是在追逐风险还是回到防守。"
    if any(keyword in text.lower() for keyword in ["btc", "eth", "比特币", "加密", "币圈", "etf"]):
        return "币圈相关主题有助于判断资金是在回流 BTC 防守，还是继续向高弹性资产扩散。"
    return "这条中文宏观新闻用于补充解释当天的流动性、风险偏好或情绪变化。"


def build_today_news(payload, failures):
    report = read_report_for_today()
    if not report:
        failures.append("今日 reports 文件缺失；沿用上一版新闻主列表。")
        return payload.get("news", [])

    candidates = []
    for item in report.get("items", []):
        ranks = item.get("platformRanks") or []
        if not ranks:
            continue
        rank = ranks[0]
        text = f"{item.get('event', '')} {rank.get('title', '')}"
        if not any(keyword in text.lower() for keyword in ["美联储", "降息", "关税", "特朗普", "原油", "opec", "黄金", "伊朗", "以色列", "战争", "btc", "eth", "比特币", "加密", "cpi", "ppi", "非农", "失业", "a股", "美元", "美债", "科技", "ai"]):
            continue
        candidates.append((item, rank))

    published = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    curated = []
    seen = set()
    for index, (item, rank) in enumerate(candidates[:18], start=1):
        title = (rank.get("title") or item.get("event") or "").strip()
        if not title or title in seen:
            continue
        seen.add(title)
        summary = summarize_news(item.get("event", ""), title)
        curated.append(
            {
                "id": f"fallback-{dt.datetime.now().strftime('%Y-%m-%d')}-{index:02d}",
                "source": infer_source(rank),
                "title": title,
                "titleZh": title,
                "url": rank.get("url") or "",
                "published": published,
                "summary": summary,
                "summaryZh": summary,
                "articleContent": summary,
                "articleContentZh": summary,
                "contentQuality": "summary",
                "contentChars": len(summary),
                "buckets": classify_buckets(f"{item.get('event', '')} {title}"),
            }
        )

    if not curated:
        failures.append("今日中文热榜未筛出宏观候选；沿用上一版新闻主列表。")
        return payload.get("news", [])

    merged = []
    seen_keys = set()
    for item in curated + list(payload.get("news", [])):
        key = f"{item.get('source')}|{item.get('titleZh') or item.get('title')}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        merged.append(item)
    return merged[:80]


def news_for_bucket(news, bucket, limit=5):
    return [item for item in news if bucket in item.get("buckets", [])][:limit]


def change_text(item):
    change = item.get("changePct") if item else None
    if change is None:
        return "近月变化暂缺"
    return f"近月 {change:+.1f}%"


def rebuild_questions(payload):
    events = payload.get("events", [])
    ratios = payload.get("ratios", [])
    crypto = payload.get("cryptoMetrics", [])
    news = payload.get("news", [])
    rates = payload.get("rateMetrics", [])
    prices = payload.get("prices", [])

    nonfarm = find_event(events, "fred-payems")
    cpi = find_event(events, "fred-cpi-yoy")
    pce = find_event(events, "fred-pce-yoy")
    core_pce = find_event(events, "fred-core-pce-yoy")
    claims = find_event(events, "fred-icsa")
    unemployment = find_event(events, "fred-unrate")
    china_cpi = find_event(events, "nbs-china-cpi")
    china_ppi = find_event(events, "nbs-china-ppi")
    gold_silver = find_metric(ratios, "金银比")
    gold_oil = find_metric(ratios, "金油比")
    btc_gold = find_metric(ratios, "金特比")
    eth_btc = find_metric(ratios, "ETH/BTC")
    fng = find_metric(crypto, "恐慌贪婪指数")
    market_cap = find_metric(crypto, "加密总市值")
    btc_dominance = find_metric(crypto, "BTC 市占率")
    real_rate = find_metric(rates, "美国10年实际利率")
    curve = find_metric(rates, "美国10Y-2Y利差")
    us10y = find_metric(rates, "美国10年国债收益率")
    dxy = find_metric(prices, "美元指数 DXY")
    vix = find_metric(prices, "VIX")

    cpi_now = first_number(cpi.get("actual")) if cpi else None
    cpi_prev = first_number(cpi.get("previous")) if cpi else None
    pce_now = first_number(pce.get("actual")) if pce else None
    pce_prev = first_number(pce.get("previous")) if pce else None
    real_rate_value = real_rate.get("rawValue") if real_rate else None
    curve_value = curve.get("rawValue") if curve else None
    dxy_value = dxy.get("rawValue") if dxy else None
    vix_value = vix.get("rawValue") if vix else None
    fng_value = fng.get("rawValue") if fng else None
    eth_change = eth_btc.get("changePct") if eth_btc else None

    tide_pressure = 0
    tide_easing = 0
    if real_rate_value is not None:
        tide_pressure += 1 if real_rate_value >= 1.8 else 0
        tide_easing += 1 if real_rate_value < 1.2 else 0
    if dxy_value is not None:
        tide_pressure += 1 if dxy_value >= 100 else 0
        tide_easing += 1 if dxy_value < 98 else 0
    if cpi_now is not None and cpi_prev is not None:
        tide_pressure += 1 if cpi_now > 2 and cpi_now >= cpi_prev else 0
        tide_easing += 1 if cpi_now <= cpi_prev else 0
    if pce_now is not None and pce_prev is not None:
        tide_pressure += 1 if pce_now > 2 and pce_now >= pce_prev else 0
        tide_easing += 1 if pce_now <= pce_prev else 0
    if curve_value is not None and curve_value < 0:
        tide_pressure += 1
    if tide_pressure > tide_easing:
        tide_tone = "defensive"
        tide_text = "实际利率、美元指数、通胀/曲线综合偏紧，宏观潮水偏退。"
    elif tide_easing > tide_pressure:
        tide_tone = "risk"
        tide_text = "实际利率或美元压力缓和，叠加通胀/就业降温，宏观潮水有转松线索。"
    else:
        tide_tone = "neutral"
        tide_text = "利率、美元、通胀与就业信号互相拉扯，宏观潮水暂未形成单边结论。"

    safe_votes = 0
    risk_votes = 0
    if gold_silver and gold_silver.get("changePct") is not None:
        safe_votes += 1 if gold_silver["changePct"] > 0 else 0
        risk_votes += 1 if gold_silver["changePct"] <= 0 else 0
    if gold_oil and gold_oil.get("changePct") is not None:
        safe_votes += 1 if gold_oil["changePct"] > 0 else 0
        risk_votes += 1 if gold_oil["changePct"] <= 0 else 0
    if btc_gold and btc_gold.get("changePct") is not None:
        safe_votes += 1 if btc_gold["changePct"] < 0 else 0
        risk_votes += 1 if btc_gold["changePct"] >= 0 else 0
    if vix_value is not None:
        safe_votes += 1 if vix_value >= 20 else 0
        risk_votes += 1 if vix_value < 16 else 0
    risk_tone = "defensive" if safe_votes > risk_votes else "risk" if risk_votes > safe_votes else "neutral"
    risk_text = f"避险票 {safe_votes} : 冒险票 {risk_votes}。"
    if safe_votes > risk_votes:
        risk_text += " 当前更偏避险。"
    elif risk_votes > safe_votes:
        risk_text += " 当前更偏冒险。"
    else:
        risk_text += " 当前市场分歧较大。"

    if eth_change is None:
        rotation_tone = "neutral"
        rotation_text = "ETH/BTC 近月变化暂缺，币圈内部轮动信号不足。"
    elif eth_change > 0:
        rotation_tone = "risk"
        rotation_text = "ETH/BTC 走强，资金从 BTC 防守向更高弹性的资产扩散。"
    else:
        rotation_tone = "defensive"
        rotation_text = "ETH/BTC 走弱，资金更偏回流 BTC 防守，高弹性资产承压。"

    if fng_value is None:
        timing_tone = "neutral"
        timing_text = "恐慌贪婪指数暂缺，不给择时结论。"
    elif fng_value <= 20:
        timing_tone = "risk"
        timing_text = "情绪进入极度恐慌区，具备逆向观察价值，但仍需价格确认。"
    elif fng_value >= 80:
        timing_tone = "defensive"
        timing_text = "情绪进入极度贪婪区，追高性价比下降，注意回撤风险。"
    else:
        timing_tone = "neutral"
        timing_text = "情绪尚未到极端区间，更多用于确认市场温度。"

    payload["questions"] = [
        {
            "id": "macro-tide",
            "title": "① 宏观潮水在涨还是退？",
            "subtitle": "流动性 / 政策",
            "tone": tide_tone,
            "inclination": tide_text,
            "bullets": [
                f"美国非农新增：{nonfarm.get('actual', '-') if nonfarm else '-'}（前值 {nonfarm.get('previous', '-') if nonfarm else '-'}）",
                f"美国 CPI 同比：{cpi.get('actual', '-') if cpi else '-'}（前值 {cpi.get('previous', '-') if cpi else '-'}）",
                f"美国 PCE / 核心PCE：{pce.get('actual', '-') if pce else '-'} / {core_pce.get('actual', '-') if core_pce else '-'}",
                f"美国10年实际利率：{real_rate.get('value', '-') if real_rate else '-'}；DXY：{dxy.get('value', '-') if dxy else '-'}",
                f"美国10Y：{us10y.get('value', '-') if us10y else '-'}；10Y-2Y：{curve.get('value', '-') if curve else '-'}",
                f"美国失业率：{unemployment.get('actual', '-') if unemployment else '-'}；初请：{claims.get('actual', '-') if claims else '-'}",
                f"中国背景：CPI {china_cpi.get('actual', '-') if china_cpi else '-'}；PPI {china_ppi.get('actual', '-') if china_ppi else '-'}",
            ],
            "howToUse": "这块决定大方向：实际利率和 DXY 上行时，黄金/币/新兴市场通常承压；曲线倒挂加深说明衰退或紧缩压力仍在。",
            "news": news_for_bucket(news, "macro-tide"),
        },
        {
            "id": "risk-regime",
            "title": "② 该避险还是冒险？",
            "subtitle": "风险体制",
            "tone": risk_tone,
            "inclination": risk_text,
            "bullets": [
                f"金银比：{gold_silver.get('value', '-') if gold_silver else '-'}（{change_text(gold_silver)}）",
                f"金油比：{gold_oil.get('value', '-') if gold_oil else '-'}（{change_text(gold_oil)}）",
                f"金特比：{btc_gold.get('value', '-') if btc_gold else '-'}（{change_text(btc_gold)}）",
                f"VIX：{vix.get('value', '-') if vix else '-'}",
            ],
            "howToUse": "看趋势，不迷信绝对值。多个比价同向时才增强判断；如果互相打架，说明市场在转折或缺少共识。",
            "news": news_for_bucket(news, "risk-regime"),
        },
        {
            "id": "crypto-rotation",
            "title": "③ 币圈的钱往哪流？",
            "subtitle": "内部轮动",
            "tone": rotation_tone,
            "inclination": rotation_text,
            "bullets": [
                f"ETH/BTC：{eth_btc.get('value', '-') if eth_btc else '-'}（{change_text(eth_btc)}）",
                f"BTC 市占率：{btc_dominance.get('value', '-') if btc_dominance else '-'}",
            ],
            "howToUse": "BTC 强、ETH/BTC 弱时，币圈偏防守；ETH/BTC 连续走强时，才说明资金愿意去更高风险资产里找弹性。",
            "news": news_for_bucket(news, "crypto-rotation"),
        },
        {
            "id": "sentiment-extreme",
            "title": "④ 情绪到极端了吗？",
            "subtitle": "择时",
            "tone": timing_tone,
            "inclination": timing_text,
            "bullets": [
                f"恐慌贪婪指数：{fng.get('value', '-') if fng else '-'}（{fng.get('classification', '-') if fng else '-'}）",
                f"加密总市值：{market_cap.get('value', '-') if market_cap else '-'}（{change_text(market_cap).replace('近月', '24h')}）",
            ],
            "howToUse": "情绪指标只在极端区间最有价值。中间区间不要硬解读，主要用来辅助判断市场是否已经过热或过冷。",
            "news": news_for_bucket(news, "sentiment-extreme"),
        },
    ]


def main():
    payload = load_json(MACRO_PATH)
    failures = [item for item in payload.get("failures", []) if "runtime fallback" not in str(item).lower()]

    build_us_events(payload["events"], failures)
    update_rate_metrics(payload, failures)
    update_prices_and_ratios(payload, failures)
    update_crypto_metrics(payload, failures)
    payload["news"] = build_today_news(payload, failures)
    rebuild_questions(payload)

    now = dt.datetime.now()
    payload["generatedAt"] = now.strftime("%Y-%m-%d %H:%M:%S +08:00")
    payload["summary"] = (
        f"宏观快照：{len(payload.get('events', []))} 个宏观指标，"
        f"{len(payload.get('ratios', []))} 个价格比值，{len(payload.get('cryptoMetrics', []))} 个币圈宏观指标；"
        f"{len(payload.get('rateMetrics', []))} 个利率曲线指标，{len(payload.get('news', []))} 条中文优先新闻。"
        "当前运行走 runtime fallback：美国 FRED、Yahoo Finance、alternative.me、CoinGecko 已刷新；"
        "中国 AkShare 依赖因本地 .python-deps 权限异常，暂沿用上一版成功快照。"
    )
    failures.append("Runtime fallback active: refreshed FRED/Yahoo/CoinGecko/news; retained prior China AkShare snapshot because .python-deps is unreadable.")
    payload["failures"] = failures
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
