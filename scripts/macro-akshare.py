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
    data = yf.download(tickers, period="5d", interval="1d", progress=False, auto_adjust=False)["Close"].dropna()
    last = data.iloc[-1]
    date = data.index[-1].strftime("%Y-%m-%d")
    return date, {ticker: float(last[ticker]) for ticker in tickers}


def get_ratios_and_prices():
    failures = []
    ratios = []
    prices = []
    try:
        date, px = latest_prices()
        gold = px["GC=F"]
        silver = px["SI=F"]
        oil = px["CL=F"]
        btc = px["BTC-USD"]
        eth = px["ETH-USD"]
        prices = [
            {"name": "黄金", "value": f"${gold:,.1f}", "notes": f"Yahoo Finance，{date}"},
            {"name": "白银", "value": f"${silver:,.2f}", "notes": f"Yahoo Finance，{date}"},
            {"name": "WTI 原油", "value": f"${oil:,.2f}", "notes": f"Yahoo Finance，{date}"},
            {"name": "BTC", "value": f"${btc:,.0f}", "notes": f"Yahoo Finance，{date}"},
            {"name": "ETH", "value": f"${eth:,.0f}", "notes": f"Yahoo Finance，{date}"},
        ]
        ratios = [
            {"name": "金银比", "value": f"{gold / silver:.1f}", "notes": "黄金价格 / 白银价格。"},
            {"name": "金油比", "value": f"{gold / oil:.1f}", "notes": "黄金价格 / WTI 原油价格。"},
            {"name": "金特比", "value": f"1 BTC ≈ {btc / gold:.1f} 盎司黄金", "notes": "BTC 价格 / 黄金价格。"},
            {"name": "ETH/BTC", "value": f"{eth / btc:.4f}", "notes": "ETH 相对 BTC 强弱。"},
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
                    "notes": f"24h {change:+.1f}%；来源 CoinGecko。",
                },
                {
                    "name": "BTC 市占率",
                    "value": f"{dominance:.1f}%",
                    "notes": "BTC 市值占全市场比例；来源 CoinGecko。",
                },
            ]
        )
    except Exception as error:
        failures.append({"source": "CoinGecko global", "error": str(error)})
    return metrics, failures


def main():
    generated_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    us_events, us_failures = get_us_events()
    china_events, china_failures = get_china_events()
    ratios, prices, price_failures = get_ratios_and_prices()
    crypto_metrics, crypto_failures = get_crypto_metrics()
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
        "ratios": ratios,
        "prices": prices,
        "cryptoMetrics": crypto_metrics,
        "sources": sources,
        "failures": us_failures + china_failures + price_failures + crypto_failures,
    }
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
