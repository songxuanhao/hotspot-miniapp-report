# -*- coding: utf-8 -*-
import datetime as dt
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.abspath(".python-deps"))

import akshare as ak
import pandas as pd
import requests
import yfinance as yf


def value_text(value, unit="", signed=False, digits=1):
    if value is None or pd.isna(value):
        return ""
    number = float(value)
    if signed:
        return f"{number:+.{digits}f}{unit}"
    return f"{number:.{digits}f}{unit}"


def event(
    *,
    item_id,
    date,
    country,
    category,
    title,
    actual,
    previous="",
    expected="官方源无预期",
    surprise="",
    source,
    notes,
    status="released",
    importance="high",
):
    return {
        "id": item_id,
        "date": str(date),
        "time": "已公布" if status == "released" else "待公布",
        "period": str(date),
        "country": country,
        "category": category,
        "title": title,
        "expected": expected,
        "actual": actual,
        "previous": previous,
        "surprise": surprise or "官方源无预期",
        "status": status,
        "importance": importance,
        "source": source,
        "notes": notes,
    }


def fred_csv(series_id):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    data = pd.read_csv(url)
    data.columns = ["date", "value"]
    data["value"] = pd.to_numeric(data["value"], errors="coerce")
    return data.dropna()


def get_us_events():
    events = []
    failures = []
    try:
        payrolls = fred_csv("PAYEMS")
        change = payrolls["value"].diff()
        latest_date = payrolls["date"].iloc[-1]
        current = change.iloc[-1]
        previous = change.iloc[-2]
        surprise = "较上月多增" if current > previous else "较上月少增" if current < previous else "与上月持平"
        events.append(
            event(
                item_id="fred-payems",
                date=latest_date,
                country="美国",
                category="就业",
                title="非农新增就业",
                actual=f"{current:+.0f} 千人",
                previous=f"{previous:+.0f} 千人",
                surprise=surprise,
                source="FRED PAYEMS",
                notes="FRED 官方 CSV，无需 API key；PAYEMS 为非农就业总人数，脚本用环比差值计算新增就业。",
            )
        )
    except Exception as error:
        failures.append({"source": "FRED PAYEMS", "error": str(error)})

    try:
        cpi = fred_csv("CPIAUCSL")
        yoy = cpi["value"].pct_change(12) * 100
        events.append(
            event(
                item_id="fred-cpi-yoy",
                date=cpi["date"].iloc[-1],
                country="美国",
                category="通胀",
                title="CPI 同比",
                actual=f"{yoy.iloc[-1]:.1f}%",
                previous=f"{yoy.iloc[-2]:.1f}%",
                surprise="较上月上升" if yoy.iloc[-1] > yoy.iloc[-2] else "较上月回落" if yoy.iloc[-1] < yoy.iloc[-2] else "与上月持平",
                source="FRED CPIAUCSL",
                notes="FRED 官方 CSV，无需 API key；用 CPI 指数计算 12 个月同比。",
            )
        )
    except Exception as error:
        failures.append({"source": "FRED CPIAUCSL", "error": str(error)})

    try:
        unemployment = fred_csv("UNRATE")
        latest = unemployment["value"].iloc[-1]
        previous = unemployment["value"].iloc[-2]
        events.append(
            event(
                item_id="fred-unrate",
                date=unemployment["date"].iloc[-1],
                country="美国",
                category="就业",
                title="失业率",
                actual=f"{latest:.1f}%",
                previous=f"{previous:.1f}%",
                surprise="较上月上升" if latest > previous else "较上月下降" if latest < previous else "与上月持平",
                source="FRED UNRATE",
                notes="FRED 官方 CSV，无需 API key；月度失业率。",
            )
        )
    except Exception as error:
        failures.append({"source": "FRED UNRATE", "error": str(error)})
    return events, failures


def get_china_events():
    events = []
    failures = []
    try:
        cpi = ak.macro_china_cpi()
        row = cpi.iloc[0]
        events.append(
            event(
                item_id="nbs-china-cpi",
                date=row["月份"],
                country="中国",
                category="通胀",
                title="CPI",
                actual=f"同比 {float(row['全国-同比增长']):+.1f}% / 环比 {float(row['全国-环比增长']):+.1f}%",
                previous="国家统计局源未给上月对比列",
                surprise="官方源无预期",
                source="AkShare macro_china_cpi（国家统计局源）",
                notes="AkShare 国家统计局源，当前比金十宏观函数更新；使用全国同比和环比。",
            )
        )
    except Exception as error:
        failures.append({"source": "macro_china_cpi", "error": str(error)})

    try:
        ppi = ak.macro_china_ppi()
        row = ppi.iloc[0]
        events.append(
            event(
                item_id="nbs-china-ppi",
                date=row["月份"],
                country="中国",
                category="通胀",
                title="PPI",
                actual=f"同比 {float(row['当月同比增长']):+.1f}%",
                previous="国家统计局源未给上月对比列",
                surprise="官方源无预期",
                source="AkShare macro_china_ppi（国家统计局源）",
                notes="AkShare 国家统计局源，当前比金十宏观函数更新；使用当月同比增长。",
            )
        )
    except Exception as error:
        failures.append({"source": "macro_china_ppi", "error": str(error)})
    return events, failures


def latest_prices():
    tickers = ["GC=F", "SI=F", "CL=F", "BTC-USD", "ETH-USD"]
    data = yf.download(tickers, period="3mo", interval="1d", progress=False, auto_adjust=False)["Close"].dropna()
    last = data.iloc[-1]
    base = data.iloc[-23] if len(data) >= 23 else data.iloc[0]
    date = data.index[-1].strftime("%Y-%m-%d")
    latest = {ticker: float(last[ticker]) for ticker in tickers}
    previous = {ticker: float(base[ticker]) for ticker in tickers}
    return date, latest, previous


def pct_change(current, previous):
    if previous in (None, 0):
        return None
    return (current / previous - 1) * 100


def get_ratios_and_prices():
    failures = []
    ratios = []
    prices = []
    try:
        date, px, prev = latest_prices()
        gold = px["GC=F"]
        silver = px["SI=F"]
        oil = px["CL=F"]
        btc = px["BTC-USD"]
        eth = px["ETH-USD"]
        old_gold = prev["GC=F"]
        old_silver = prev["SI=F"]
        old_oil = prev["CL=F"]
        old_btc = prev["BTC-USD"]
        old_eth = prev["ETH-USD"]
        ratio_values = {
            "gold_silver": gold / silver,
            "gold_oil": gold / oil,
            "btc_gold": btc / gold,
            "eth_btc": eth / btc,
        }
        old_ratio_values = {
            "gold_silver": old_gold / old_silver,
            "gold_oil": old_gold / old_oil,
            "btc_gold": old_btc / old_gold,
            "eth_btc": old_eth / old_btc,
        }
        prices = [
            {"name": "黄金", "value": f"${gold:,.1f}", "notes": f"Yahoo Finance，{date}"},
            {"name": "白银", "value": f"${silver:,.2f}", "notes": f"Yahoo Finance，{date}"},
            {"name": "WTI 原油", "value": f"${oil:,.2f}", "notes": f"Yahoo Finance，{date}"},
            {"name": "BTC", "value": f"${btc:,.0f}", "notes": f"Yahoo Finance，{date}"},
            {"name": "ETH", "value": f"${eth:,.0f}", "notes": f"Yahoo Finance，{date}"},
        ]
        ratios = [
            {
                "name": "金银比",
                "value": f"{ratio_values['gold_silver']:.1f}",
                "rawValue": ratio_values["gold_silver"],
                "changePct": pct_change(ratio_values["gold_silver"], old_ratio_values["gold_silver"]),
                "notes": "黄金价格 / 白银价格；上行偏避险，下行偏工业和风险偏好修复。",
            },
            {
                "name": "金油比",
                "value": f"{ratio_values['gold_oil']:.1f}",
                "rawValue": ratio_values["gold_oil"],
                "changePct": pct_change(ratio_values["gold_oil"], old_ratio_values["gold_oil"]),
                "notes": "黄金价格 / WTI 原油价格；噪音较大，但上行常提示增长担忧或原油走弱。",
            },
            {
                "name": "金特比",
                "value": f"1 BTC ≈ {ratio_values['btc_gold']:.1f} 盎司黄金",
                "rawValue": ratio_values["btc_gold"],
                "changePct": pct_change(ratio_values["btc_gold"], old_ratio_values["btc_gold"]),
                "notes": "BTC 价格 / 黄金价格；上行代表 BTC 相对黄金更强，偏风险偏好。",
            },
            {
                "name": "ETH/BTC",
                "value": f"{ratio_values['eth_btc']:.4f}",
                "rawValue": ratio_values["eth_btc"],
                "changePct": pct_change(ratio_values["eth_btc"], old_ratio_values["eth_btc"]),
                "notes": "ETH 相对 BTC 强弱；上行通常代表币圈内部风险偏好更强。",
            },
        ]
    except Exception as error:
        failures.append({"source": "yfinance", "error": str(error)})
    return ratios, prices, failures


def get_json(url):
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    response.raise_for_status()
    return response.json()


def get_crypto_metrics():
    metrics = []
    failures = []
    try:
        fng = get_json("https://api.alternative.me/fng/?limit=1")["data"][0]
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
        failures.append({"source": "alternative.me fng", "error": str(error)})

    try:
        global_data = get_json("https://api.coingecko.com/api/v3/global")["data"]
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
        failures.append({"source": "CoinGecko global", "error": str(error)})
    return metrics, failures


def first_number(value):
    import re

    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value or ""))
    return float(match.group(0)) if match else None


def find_by_id(items, item_id):
    return next((item for item in items if item.get("id") == item_id), None)


def find_by_name(items, keyword):
    return next((item for item in items if keyword in item.get("name", "")), None)


def change_text(item):
    change = item.get("changePct") if item else None
    if change is None:
        return "近1月变化暂缺"
    return f"近1月 {change:+.1f}%"


def build_questions(events, ratios, crypto_metrics):
    nonfarm = find_by_id(events, "fred-payems")
    cpi = find_by_id(events, "fred-cpi-yoy")
    unemployment = find_by_id(events, "fred-unrate")
    china_cpi = find_by_id(events, "nbs-china-cpi")
    china_ppi = find_by_id(events, "nbs-china-ppi")
    gold_silver = find_by_name(ratios, "金银比")
    gold_oil = find_by_name(ratios, "金油比")
    btc_gold = find_by_name(ratios, "金特比")
    eth_btc = find_by_name(ratios, "ETH/BTC")
    fng = find_by_name(crypto_metrics, "恐慌贪婪")
    market_cap = find_by_name(crypto_metrics, "加密总市值")
    btc_dominance = find_by_name(crypto_metrics, "BTC 市占率")

    cpi_now = first_number(cpi.get("actual")) if cpi else None
    cpi_prev = first_number(cpi.get("previous")) if cpi else None
    nonfarm_now = first_number(nonfarm.get("actual")) if nonfarm else None
    nonfarm_prev = first_number(nonfarm.get("previous")) if nonfarm else None

    if cpi_now is not None and cpi_prev is not None and cpi_now > 2 and cpi_now >= cpi_prev:
        tide = "通胀高于 2% 且回升，美联储偏紧，宏观潮水偏退。"
        tide_tone = "defensive"
    elif nonfarm_now is not None and nonfarm_prev is not None and nonfarm_now < nonfarm_prev and cpi_now is not None and cpi_now <= cpi_prev:
        tide = "就业降温且通胀回落，后续更容易交易宽松，宏观潮水有转松线索。"
        tide_tone = "risk"
    else:
        tide = "通胀、就业信号不完全一致，宏观潮水暂不清晰，适合降低单边判断。"
        tide_tone = "neutral"

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
    risk_tone = "defensive" if safe_votes > risk_votes else "risk" if risk_votes > safe_votes else "neutral"
    risk_text = (
        f"避险票 {safe_votes} : 冒险票 {risk_votes}。"
        + (" 当前更偏避险。" if safe_votes > risk_votes else " 当前更偏冒险。" if risk_votes > safe_votes else " 当前分歧较大。")
    )

    eth_change = eth_btc.get("changePct") if eth_btc else None
    if eth_change is None:
        rotation = "ETH/BTC 近1月变化暂缺，币圈内部轮动信号不足。"
        rotation_tone = "neutral"
    elif eth_change > 0:
        rotation = "ETH/BTC 走强，资金从 BTC 防守向更高弹性的资产扩散。"
        rotation_tone = "risk"
    else:
        rotation = "ETH/BTC 走弱，资金更偏回流 BTC 防守，山寨与高弹性资产偏弱。"
        rotation_tone = "defensive"

    fng_value = fng.get("rawValue") if fng else None
    if fng_value is None:
        timing = "恐慌贪婪指数暂缺，不给择时结论。"
        timing_tone = "neutral"
    elif fng_value <= 20:
        timing = "情绪进入极度恐慌区，出现反向观察价值，但仍要等价格确认。"
        timing_tone = "risk"
    elif fng_value >= 80:
        timing = "情绪进入极度贪婪区，追高性价比下降，注意回撤风险。"
        timing_tone = "defensive"
    else:
        timing = "未到情绪极值，暂无明确择时信号，更多用于确认市场温度。"
        timing_tone = "neutral"

    return [
        {
            "id": "macro-tide",
            "title": "① 宏观潮水在涨还是退？",
            "subtitle": "流动性 / 政策",
            "tone": tide_tone,
            "inclination": tide,
            "bullets": [
                f"美国非农新增：{nonfarm.get('actual', '-') if nonfarm else '-'}（前值 {nonfarm.get('previous', '-') if nonfarm else '-'}）",
                f"美国 CPI 同比：{cpi.get('actual', '-') if cpi else '-'}（前值 {cpi.get('previous', '-') if cpi else '-'}）",
                f"美国失业率：{unemployment.get('actual', '-') if unemployment else '-'}",
                f"中国背景：CPI {china_cpi.get('actual', '-') if china_cpi else '-'}；PPI {china_ppi.get('actual', '-') if china_ppi else '-'}",
            ],
            "howToUse": "这块决定大方向：潮水退时，黄金、现金流、BTC 防守更值得看；潮水涨时，成长股、山寨、周期资产才更容易顺风。",
        },
        {
            "id": "risk-regime",
            "title": "② 该避险还是冒险？",
            "subtitle": "风险体制",
            "tone": risk_tone,
            "inclination": risk_text,
            "bullets": [
                f"金银比：{gold_silver.get('value', '-') if gold_silver else '-'}（{change_text(gold_silver)}）",
                f"金油比：{gold_oil.get('value', '-') if gold_oil else '-'}（{change_text(gold_oil)}，噪音较大）",
                f"金特比：{btc_gold.get('value', '-') if btc_gold else '-'}（{change_text(btc_gold)}）",
            ],
            "howToUse": "看趋势，不迷信绝对值。多个比值同向时才增强判断；如果互相打架，说明市场在转折或缺少共识。",
        },
        {
            "id": "crypto-rotation",
            "title": "③ 币圈的钱往哪流？",
            "subtitle": "内部轮动",
            "tone": rotation_tone,
            "inclination": rotation,
            "bullets": [
                f"ETH/BTC：{eth_btc.get('value', '-') if eth_btc else '-'}（{change_text(eth_btc)}）",
                f"BTC 市占率：{btc_dominance.get('value', '-') if btc_dominance else '-'}",
            ],
            "howToUse": "BTC 强、ETH/BTC 弱时，币圈偏防守；ETH/BTC 连续走强时，才说明资金愿意去更高风险资产里找弹性。",
        },
        {
            "id": "sentiment-extreme",
            "title": "④ 情绪到极端了吗？",
            "subtitle": "择时",
            "tone": timing_tone,
            "inclination": timing,
            "bullets": [
                f"恐慌贪婪指数：{fng.get('value', '-') if fng else '-'}（{fng.get('classification', '-') if fng else '-'}）",
                f"加密总市值：{market_cap.get('value', '-') if market_cap else '-'}（{change_text(market_cap).replace('近1月', '24h')}）",
            ],
            "howToUse": "情绪指标只在极端区间最有价值。中间区域不要硬解读，主要用来辅助判断市场是否已经过热或过冷。",
        },
    ]


def main():
    generated_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    us_events, us_failures = get_us_events()
    china_events, china_failures = get_china_events()
    ratios, prices, price_failures = get_ratios_and_prices()
    crypto_metrics, crypto_failures = get_crypto_metrics()
    questions = build_questions(us_events + china_events, ratios, crypto_metrics)
    sources = [
        {
            "name": "FRED CSV",
            "status": "已接入，无需 key",
            "usage": "美国非农、CPI、失业率；官方时间序列，直连 CSV。",
        },
        {
            "name": "AkShare 国家统计局源",
            "status": "已接入，本地依赖",
            "usage": "中国 CPI/PPI 官方统计源封装，替代停更的金十宏观函数。",
        },
        {
            "name": "yfinance",
            "status": "已接入，本地依赖",
            "usage": "黄金、白银、WTI、BTC、ETH 价格与比值。",
        },
        {
            "name": "alternative.me / CoinGecko",
            "status": "已接入，无需 key",
            "usage": "恐慌贪婪指数、加密总市值、BTC 市占率。",
        },
    ]
    payload = {
        "generatedAt": f"{generated_at} +08:00",
        "summary": (
            f"宏观快照：{len(us_events) + len(china_events)} 个官方宏观指标，"
            f"{len(ratios)} 个价格比值，{len(crypto_metrics)} 个币圈宏观指标；"
            "美国走 FRED CSV，中国走国家统计局源，价格和币圈指标走免费公开接口。"
        ),
        "events": us_events + china_events,
        "questions": questions,
        "ratios": ratios,
        "prices": prices,
        "cryptoMetrics": crypto_metrics,
        "sources": sources,
        "failures": us_failures + china_failures + price_failures + crypto_failures,
    }
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
