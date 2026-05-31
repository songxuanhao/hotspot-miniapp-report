# -*- coding: utf-8 -*-
import datetime as dt
import html
import json
import os
import re
import sys
import time
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET
import warnings

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.abspath(".python-deps"))

import akshare as ak
import pandas as pd
import requests
import yfinance as yf

TRANSLATION_FAILURES = 0


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


def generated_month_date():
    return dt.datetime.now().strftime("%Y-%m-01")


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

    try:
        pce = fred_csv("PCEPI")
        yoy = pce["value"].pct_change(12) * 100
        events.append(
            event(
                item_id="fred-pce-yoy",
                date=pce["date"].iloc[-1],
                country="美国",
                category="通胀",
                title="PCE 同比",
                actual=f"{yoy.iloc[-1]:.1f}%",
                previous=f"{yoy.iloc[-2]:.1f}%",
                surprise="较上月上升" if yoy.iloc[-1] > yoy.iloc[-2] else "较上月回落" if yoy.iloc[-1] < yoy.iloc[-2] else "与上月持平",
                source="FRED PCEPI",
                notes="FRED PCEPI 计算 12 个月同比；PCE 是美联储更关注的通胀口径。",
            )
        )
    except Exception as error:
        failures.append({"source": "FRED PCEPI", "error": str(error)})

    try:
        core_pce = fred_csv("PCEPILFE")
        yoy = core_pce["value"].pct_change(12) * 100
        events.append(
            event(
                item_id="fred-core-pce-yoy",
                date=core_pce["date"].iloc[-1],
                country="美国",
                category="通胀",
                title="核心 PCE 同比",
                actual=f"{yoy.iloc[-1]:.1f}%",
                previous=f"{yoy.iloc[-2]:.1f}%",
                surprise="较上月上升" if yoy.iloc[-1] > yoy.iloc[-2] else "较上月回落" if yoy.iloc[-1] < yoy.iloc[-2] else "与上月持平",
                source="FRED PCEPILFE",
                notes="FRED PCEPILFE 计算 12 个月同比；核心 PCE 是美联储偏好的通胀指标。",
            )
        )
    except Exception as error:
        failures.append({"source": "FRED PCEPILFE", "error": str(error)})

    try:
        claims = fred_csv("ICSA")
        latest = claims["value"].iloc[-1]
        previous = claims["value"].iloc[-2]
        events.append(
            event(
                item_id="fred-icsa",
                date=claims["date"].iloc[-1],
                country="美国",
                category="就业",
                title="初请失业金人数",
                actual=f"{latest / 1000:.0f} 千人",
                previous=f"{previous / 1000:.0f} 千人",
                surprise="较上周上升" if latest > previous else "较上周下降" if latest < previous else "与上周持平",
                source="FRED ICSA",
                notes="FRED ICSA，周度高频就业降温信号。",
            )
        )
    except Exception as error:
        failures.append({"source": "FRED ICSA", "error": str(error)})

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

    try:
        if hasattr(ak, "macro_china_shrzgm"):
            social = ak.macro_china_shrzgm()
            row = social.iloc[0].to_dict()
            date_text = row_text(row, ["月份", "日期", "统计时间"])
            value = row_text(row, ["社会融资规模增量", "社会融资规模", "今值", "数值"])
            if value:
                events.append(
                    event(
                        item_id="ak-china-social-financing",
                        date=date_text or generated_month_date(),
                        country="中国",
                        category="流动性",
                        title="社会融资规模",
                        actual=value,
                        previous="AkShare 源未统一提供前值",
                        surprise="官方源无预期",
                        source="AkShare macro_china_shrzgm",
                        notes="中国信用扩张和实体流动性的核心指标，best-effort。",
                        importance="medium",
                    )
                )
    except Exception:
        pass

    try:
        if hasattr(ak, "rate_interbank"):
            lpr = ak.rate_interbank(market="中国货币市场", symbol="LPR品种", indicator="贷款市场报价利率")
            row = lpr.iloc[0].to_dict()
            date_text = row_text(row, ["日期", "报告日"])
            value = row_text(row, ["利率", "最新值", "数值"])
            if value:
                events.append(
                    event(
                        item_id="ak-china-lpr",
                        date=date_text or generated_month_date(),
                        country="中国",
                        category="利率",
                        title="LPR",
                        actual=value,
                        previous="AkShare 源未统一提供前值",
                        surprise="官方源无预期",
                        source="AkShare rate_interbank",
                        notes="LPR 是中国信贷定价锚，best-effort。",
                        importance="medium",
                    )
                )
    except Exception:
        pass
    return events, failures


def latest_prices():
    tickers = [
        "GC=F",
        "SI=F",
        "CL=F",
        "BZ=F",
        "HG=F",
        "DX-Y.NYB",
        "^VIX",
        "^GSPC",
        "^IXIC",
        "USDJPY=X",
        "BTC-USD",
        "ETH-USD",
    ]
    data = yf.download(tickers, period="3mo", interval="1d", progress=False, auto_adjust=False)["Close"].ffill().dropna(how="all")
    last = data.iloc[-1]
    base = data.iloc[-23] if len(data) >= 23 else data.iloc[0]
    date = data.index[-1].strftime("%Y-%m-%d")
    latest = {ticker: float(last[ticker]) for ticker in tickers if ticker in last and not pd.isna(last[ticker])}
    previous = {ticker: float(base[ticker]) for ticker in tickers if ticker in base and not pd.isna(base[ticker])}
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
        brent = px.get("BZ=F")
        copper = px.get("HG=F")
        dxy = px.get("DX-Y.NYB")
        vix = px.get("^VIX")
        spx = px.get("^GSPC")
        nasdaq = px.get("^IXIC")
        usdjpy = px.get("USDJPY=X")
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
            {"name": "国际金价", "value": f"${gold:,.1f}", "notes": f"Yahoo Finance GC=F，作为伦敦金现货近似观察，{date}"},
            {"name": "白银", "value": f"${silver:,.2f}", "notes": f"Yahoo Finance，{date}"},
            {"name": "WTI 原油", "value": f"${oil:,.2f}", "notes": f"Yahoo Finance，{date}"},
            *([{"name": "Brent 原油", "value": f"${brent:,.2f}", "notes": f"Yahoo Finance BZ=F，{date}"}] if brent else []),
            *([{"name": "铜", "value": f"${copper:,.2f}", "notes": f"Yahoo Finance HG=F，增长晴雨表，{date}"}] if copper else []),
            *([{"name": "美元指数 DXY", "value": f"{dxy:,.2f}", "rawValue": dxy, "notes": f"Yahoo Finance DX-Y.NYB，金/币/新兴市场反向锚，{date}"}] if dxy else []),
            *([{"name": "VIX", "value": f"{vix:,.2f}", "rawValue": vix, "notes": f"Yahoo Finance ^VIX，股市波动率风险温度计，{date}"}] if vix else []),
            *([{"name": "标普500", "value": f"{spx:,.0f}", "notes": f"Yahoo Finance ^GSPC，{date}"}] if spx else []),
            *([{"name": "纳斯达克", "value": f"{nasdaq:,.0f}", "notes": f"Yahoo Finance ^IXIC，{date}"}] if nasdaq else []),
            *([{"name": "USD/JPY", "value": f"{usdjpy:,.2f}", "notes": f"Yahoo Finance USDJPY=X，日元套息/全球流动性观察，{date}"}] if usdjpy else []),
            {"name": "BTC", "value": f"${btc:,.0f}", "notes": f"Yahoo Finance，{date}"},
            {"name": "ETH", "value": f"${eth:,.0f}", "notes": f"Yahoo Finance，{date}"},
        ]
        try:
            if hasattr(ak, "spot_hist_sge"):
                sge = ak.spot_hist_sge(symbol="Au99.99")
                row = sge.iloc[-1].to_dict()
                raw_price = row_text(row, ["收盘价", "close", "Close", "最新价"])
                sge_price = first_number(raw_price)
                if sge_price:
                    prices.append({"name": "沪金 Au99.99", "value": f"{sge_price:,.2f} 元/克", "notes": "AkShare spot_hist_sge Au99.99，best-effort。"})
            if hasattr(ak, "futures_zh_spot"):
                sh_gold = ak.futures_zh_spot(symbol="AU0", market="CF", adjust="0")
                row = sh_gold.iloc[0].to_dict()
                raw_price = row_text(row, ["current_price", "最新价", "price", "现价"])
                sh_price = first_number(raw_price)
                if sh_price:
                    prices.append({"name": "沪金主连", "value": f"{sh_price:,.2f}", "notes": "AkShare futures_zh_spot AU0，best-effort。"})
        except Exception as error:
            failures.append({"source": "AkShare futures_zh_spot AU0", "error": str(error)})
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


def clean_text(value, limit=180):
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit].rstrip() + ("..." if len(text) > limit else "")


def has_cjk(value):
    return bool(re.search(r"[\u4e00-\u9fff]", str(value or "")))


def translate_to_zh(value, limit=260):
    global TRANSLATION_FAILURES
    text = clean_text(value, limit)
    if not text or has_cjk(text) or TRANSLATION_FAILURES >= 4:
        return text
    try:
        response = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={
                "client": "gtx",
                "sl": "auto",
                "tl": "zh-CN",
                "dt": "t",
                "q": text,
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
        translated = "".join(part[0] for part in data[0] if part and part[0])
        return clean_text(translated, limit) or text
    except Exception:
        TRANSLATION_FAILURES += 1
        return text


def fallback_news_zh(source, title, summary=""):
    body = f"{title} {summary}".lower()
    if any(word in body for word in ["bitcoin", "btc", "crypto", "ether", "eth", "xrp", "sec", "etf", "stablecoin"]):
        topic = "加密市场"
        meaning = "涉及比特币、以太坊、ETF、SEC 或链上风险，主要用来观察币圈资金流向和风险偏好。"
    elif any(word in body for word in ["federal reserve", "fed", "fomc", "powell", "rate", "yield", "inflation", "pce", "claims", "ism"]):
        topic = "美联储与利率"
        meaning = "涉及美联储、通胀、就业、PMI 或国债收益率，主要影响美元、实际利率和全球流动性。"
    elif any(word in body for word in ["trump", "tariff", "white house", "china", "trade"]):
        topic = "美国政策与贸易"
        meaning = "涉及特朗普、白宫、关税或中美贸易，可能传导到通胀、汇率和风险情绪。"
    elif any(word in body for word in ["war", "iran", "israel", "ukraine", "russia", "red sea", "sanction", "missile"]):
        topic = "战争与地缘"
        meaning = "涉及战争、制裁、航运或地区冲突，通常会影响油价、黄金和避险需求。"
    elif any(word in body for word in ["oil", "opec", "brent", "wti", "energy", "shipping"]):
        topic = "能源与供应链"
        meaning = "涉及原油、OPEC、能源供应或航运，主要影响通胀预期和商品价格。"
    elif any(word in body for word in ["stock", "market", "nasdaq", "s&p", "vix"]):
        topic = "市场风险情绪"
        meaning = "涉及股市、波动率或市场表现，用来确认当前是偏冒险还是偏避险。"
    else:
        topic = "全球宏观新闻"
        meaning = "这条新闻进入宏观日历，用来辅助解释当天资产价格和风险偏好的变化。"
    return f"{topic}：{source} 报道，{meaning}"


def make_news(source, title, url="", published="", summary=""):
    title = clean_text(title, 140)
    summary_text = clean_text(summary, 240)
    zh_blob = translate_to_zh(f"{title}\n摘要：{summary_text}" if summary_text else title, 420)
    title_zh = zh_blob
    summary_zh = summary_text
    if "摘要：" in zh_blob:
        title_zh, summary_zh = zh_blob.split("摘要：", 1)
    elif "摘要:" in zh_blob:
        title_zh, summary_zh = zh_blob.split("摘要:", 1)
    if not has_cjk(title_zh):
        fallback = fallback_news_zh(source, title, summary_text)
        title_zh = fallback
        summary_zh = fallback
    body = f"{title} {summary}".lower()
    buckets = []
    if any(keyword in body for keyword in ["fed", "federal reserve", "fomc", "powell", "rate cut", "rate hike", "inflation", "cpi", "payroll", "jobs", "unemployment", "treasury yield", "bond yield", "美联储", "鲍威尔", "降息", "加息", "通胀", "非农", "就业", "失业", "国债收益率"]):
        buckets.append("macro-tide")
    if any(keyword in body for keyword in ["gold", "oil", "tariff", "war", "iran", "israel", "russia", "ukraine", "red sea", "geopolitical", "safe haven", "sanction", "trump", "white house", "china trade", "黄金", "原油", "关税", "地缘", "战争", "伊朗", "以色列", "俄罗斯", "乌克兰", "制裁", "特朗普", "白宫", "中美", "贸易"]):
        buckets.append("risk-regime")
    if any(keyword in body for keyword in ["bitcoin", "btc", "ether", "eth", "crypto", "sec", "etf", "stablecoin", "比特币", "以太坊", "加密", "币圈"]):
        buckets.extend(["crypto-rotation", "sentiment-extreme"])
    return {
        "source": source,
        "title": title,
        "titleZh": clean_text(title_zh, 160),
        "url": str(url or ""),
        "published": clean_text(published, 80),
        "summary": summary_text,
        "summaryZh": clean_text(summary_zh, 240),
        "buckets": list(dict.fromkeys(buckets)),
    }


def rss_items(source, url, limit=10):
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=18)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    items = []
    for item in root.findall(".//item")[:limit]:
        title = item.findtext("title") or ""
        link = item.findtext("link") or ""
        published = item.findtext("pubDate") or item.findtext("date") or ""
        summary = item.findtext("description") or ""
        if title:
            items.append(make_news(source, title, link, published, summary))
    if not items:
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for item in root.findall(".//atom:entry", ns)[:limit]:
            title = item.findtext("atom:title", default="", namespaces=ns)
            link_node = item.find("atom:link", ns)
            link = link_node.attrib.get("href", "") if link_node is not None else ""
            published = item.findtext("atom:updated", default="", namespaces=ns)
            summary = item.findtext("atom:summary", default="", namespaces=ns)
            if title:
                items.append(make_news(source, title, link, published, summary))
    return items


def format_unix_time(value):
    try:
        return dt.datetime.fromtimestamp(int(value)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


def wallstreetcn_live_items(limit=12):
    url = "https://api-one-wscn.awtmt.com/apiv1/content/lives"
    response = requests.get(
        url,
        params={"channel": "global-channel", "client": "pc", "limit": limit},
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
        timeout=18,
    )
    response.raise_for_status()
    data = response.json().get("data", {}).get("items", [])
    items = []
    for entry in data[:limit]:
        summary = clean_text(
            f"{entry.get('content_text') or ''} {entry.get('content_more') or ''}",
            360,
        )
        title = clean_text(entry.get("title") or summary, 120)
        if not title:
            continue
        item = make_news(
            "华尔街见闻7x24",
            title,
            entry.get("uri", ""),
            format_unix_time(entry.get("display_time")),
            summary,
        )
        item["buckets"] = list(dict.fromkeys([*item.get("buckets", []), "macro-tide", "risk-regime"]))
        items.append(item)
    return items


def gdelt_items(topic, query, bucket, limit=6):
    url = "https://api.gdeltproject.org/api/v2/doc/doc"
    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": limit,
        "sort": "HybridRel",
        "timespan": "24h",
    }
    response = requests.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=18)
    response.raise_for_status()
    articles = response.json().get("articles", [])
    items = []
    for article in articles[:limit]:
        item = make_news(
            f"GDELT · {topic}",
            article.get("title", ""),
            article.get("url", ""),
            article.get("seendate", ""),
            article.get("domain", ""),
        )
        item["buckets"] = list(dict.fromkeys([*item.get("buckets", []), bucket]))
        items.append(item)
    return items


def google_news_url(query):
    return f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"


def google_news_zh_url(query):
    return f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"


def row_text(row, candidates):
    for key in candidates:
        if key in row and str(row[key]).strip() and str(row[key]).lower() != "nan":
            return str(row[key])
    for value in row.values():
        if str(value).strip() and str(value).lower() != "nan":
            return str(value)
    return ""


def akshare_realtime_news(limit=8):
    items = []
    failures = []
    candidates = [
        ("财联社电报", "stock_info_global_cls"),
        ("东方财富全球快讯", "stock_info_global_em"),
        ("新浪全球财经", "stock_info_global_sina"),
    ]
    for source, func_name in candidates:
        if not hasattr(ak, func_name):
            continue
        try:
            frame = getattr(ak, func_name)()
            for row in frame.head(limit).to_dict("records"):
                title = row_text(row, ["标题", "内容", "摘要", "title", "content"])
                published = row_text(row, ["时间", "发布时间", "date", "time"])
                url = row_text(row, ["链接", "url"])
                if title:
                    items.append(make_news(source, title, url, published))
        except Exception as error:
            failures.append({"source": source, "error": str(error)})
    return items[:limit], failures


def cctv_briefing():
    target_date = (dt.datetime.now() - dt.timedelta(days=1)).strftime("%Y%m%d")
    if not hasattr(ak, "news_cctv"):
        return {"date": target_date, "source": "新闻联播", "items": []}, [{"source": "news_cctv", "error": "AkShare 当前版本未暴露 news_cctv"}]
    try:
        frame = ak.news_cctv(date=target_date)
        items = []
        for row in frame.head(10).to_dict("records"):
            title = row_text(row, ["title", "标题", "新闻标题", "内容"])
            url = row_text(row, ["url", "链接"])
            if title:
                items.append({"title": clean_text(title, 120), "url": url})
        return {"date": target_date, "source": "新闻联播", "items": items}, []
    except Exception as error:
        return {"date": target_date, "source": "新闻联播", "items": []}, [{"source": "news_cctv", "error": str(error)}]


def get_market_news():
    news = []
    failures = []
    chinese_direct_sources = [
        ("华尔街见闻7x24", wallstreetcn_live_items),
    ]
    for source, fetcher in chinese_direct_sources:
        try:
            news.extend(fetcher())
        except Exception as error:
            failures.append({"source": source, "error": str(error)})

    feeds = {
        "Google新闻 · 财经头条": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "Google新闻 · 国际头条": "https://news.google.com/rss/headlines/section/topic/WORLD?hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "Google新闻 · 美国财经": google_news_zh_url("美国 经济 美股 美债 美元 黄金"),
        "Google新闻 · 全球央行": google_news_zh_url("美联储 欧洲央行 日本央行 降息 加息"),
        "Google新闻 · 大宗商品": google_news_zh_url("黄金 原油 铜价 OPEC 通胀 供应链"),
        "Google新闻 · 中国市场": google_news_zh_url("中国 宏观 人民币 国债 社融 LPR A股 港股"),
        "Google新闻 · 美联储利率": google_news_zh_url("美联储 降息 加息 通胀 PCE 非农 美债收益率 when:7d"),
        "Google新闻 · 特朗普关税": google_news_zh_url("特朗普 关税 中美贸易 美元 黄金 股市 when:7d"),
        "Google新闻 · 战争地缘": google_news_zh_url("俄乌 中东 伊朗 以色列 红海 战争 黄金 原油 when:7d"),
        "Google新闻 · 原油OPEC": google_news_zh_url("OPEC 原油 油价 红海 航运 通胀 when:7d"),
        "Google新闻 · 中国宏观": google_news_zh_url("中国 CPI PPI 社融 LPR 人民币 国债 收益率 when:7d"),
        "Google新闻 · 贵金属": google_news_zh_url("伦敦金 沪金 黄金 ETF 央行购金 美元 实际利率 when:7d"),
        "Google新闻 · 币圈宏观": google_news_zh_url("比特币 ETF 资金流入 稳定币 以太坊 SEC when:7d"),
        "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "MarketWatch": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
        "Federal Reserve": "https://www.federalreserve.gov/feeds/press_all.xml",
        "Fed Speeches": "https://www.federalreserve.gov/feeds/speeches.xml",
        "Google News · Trump/Tariff": google_news_url('Trump tariff China trade market when:3d'),
        "Google News · War/Geopolitics": google_news_url('Iran Israel Ukraine Russia war oil gold market when:7d'),
        "Google News · Fed/Rates": google_news_url('Federal Reserve Powell FOMC rate cut Treasury yields when:1d'),
        "Google News · PCE/ISM/Claims": google_news_url('PCE inflation ISM PMI jobless claims market when:7d'),
        "Google News · Oil/OPEC": google_news_url('OPEC oil prices supply sanctions Red Sea shipping when:3d'),
        "Google News · China Macro": google_news_url('China yuan bond stimulus tariff trade market when:7d'),
        "Google News · BTC ETF Flows": google_news_url('Bitcoin ETF inflows outflows spot ETF when:7d'),
    }
    for source, url in feeds.items():
        try:
            news.extend(rss_items(source, url, limit=8))
        except Exception as error:
            failures.append({"source": f"{source} RSS", "error": str(error)})
    # GDELT 可覆盖全球事件，但免费端点在当前网络下容易 429。
    # 先用 Google News RSS 承担特朗普/战争/能源/中美贸易等新闻维度，避免自动化报告被失败噪音污染。
    # AkShare 的中文实时快讯端点在部分网络环境会长时间卡住。
    # 这里暂不主动调用，避免每天自动化被单个新闻源拖死；RSS 和新闻联播已覆盖实时与历史层。
    briefing, cctv_failures = cctv_briefing()
    failures.extend(cctv_failures)
    deduped = []
    seen = set()
    for item in news:
        key = (item.get("source"), item.get("title"))
        if item.get("title") and key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped[:80], briefing, failures


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


def get_rate_metrics():
    metrics = []
    failures = []
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
            data = fred_csv(series_id)
            latest = data.iloc[-1]
            previous = data.iloc[-6] if len(data) >= 6 else data.iloc[0]
            current_value = float(latest["value"])
            previous_value = float(previous["value"])
            metrics.append(
                {
                    "name": name,
                    "value": f"{current_value:.2f}%",
                    "rawValue": current_value,
                    "changePct": None,
                    "notes": f"FRED {series_id}，{latest['date']}；近5个交易日 {current_value - previous_value:+.2f}pct。",
                }
            )
        except Exception as error:
            failures.append({"source": f"FRED {series_id}", "error": str(error)})

    try:
        if hasattr(ak, "bond_zh_us_rate"):
            frame = ak.bond_zh_us_rate()
            row = frame.iloc[-1].to_dict()
            date_text = row_text(row, ["日期", "date"])
            wanted = [
                ("中国2年国债收益率", "中国国债收益率2年"),
                ("中国10年国债收益率", "中国国债收益率10年"),
                ("中国30年国债收益率", "中国国债收益率30年"),
                ("中国10Y-2Y利差", "中国国债收益率10年-2年"),
            ]
            for name, column in wanted:
                value = first_number(row.get(column))
                if value is not None:
                    metrics.append(
                        {
                            "name": name,
                            "value": f"{value:.2f}%",
                            "rawValue": value,
                            "changePct": None,
                            "notes": f"AkShare bond_zh_us_rate，{date_text or 'latest'}。",
                        }
                    )
            china_10y = first_number(row.get("中国国债收益率10年"))
            us_10y = first_number(row.get("美国国债收益率10年"))
            if china_10y is not None and us_10y is not None:
                diff = us_10y - china_10y
                metrics.append(
                    {
                        "name": "中美10年利差",
                        "value": f"{diff:.2f}pct",
                        "rawValue": diff,
                        "changePct": None,
                        "notes": f"美国10Y - 中国10Y；AkShare bond_zh_us_rate，{date_text or 'latest'}。",
                    }
                )
    except Exception as error:
        failures.append({"source": "AkShare bond_zh_us_rate", "error": str(error)})
    return metrics, failures


def first_number(value):
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


def news_for_bucket(news, bucket, limit=3):
    return [
        {
            "source": item.get("source", ""),
            "title": item.get("title", ""),
            "titleZh": item.get("titleZh", item.get("title", "")),
            "url": item.get("url", ""),
            "published": item.get("published", ""),
            "summary": item.get("summary", ""),
            "summaryZh": item.get("summaryZh", item.get("summary", "")),
        }
        for item in news
        if bucket in item.get("buckets", [])
    ][:limit]


def build_questions(events, ratios, crypto_metrics, news, rate_metrics, prices):
    nonfarm = find_by_id(events, "fred-payems")
    cpi = find_by_id(events, "fred-cpi-yoy")
    pce = find_by_id(events, "fred-pce-yoy")
    core_pce = find_by_id(events, "fred-core-pce-yoy")
    claims = find_by_id(events, "fred-icsa")
    ism = find_by_id(events, "fred-ism-manufacturing")
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
    real_rate = find_by_name(rate_metrics, "实际利率")
    curve_2s10s = find_by_name(rate_metrics, "10Y-2Y")
    us10y = find_by_name(rate_metrics, "10年国债")
    dxy = find_by_name(prices, "DXY")
    vix = find_by_name(prices, "VIX")

    cpi_now = first_number(cpi.get("actual")) if cpi else None
    cpi_prev = first_number(cpi.get("previous")) if cpi else None
    pce_now = first_number(pce.get("actual")) if pce else None
    pce_prev = first_number(pce.get("previous")) if pce else None
    nonfarm_now = first_number(nonfarm.get("actual")) if nonfarm else None
    nonfarm_prev = first_number(nonfarm.get("previous")) if nonfarm else None
    real_rate_value = real_rate.get("rawValue") if real_rate else None
    curve_value = curve_2s10s.get("rawValue") if curve_2s10s else None
    dxy_value = dxy.get("rawValue") if dxy else None
    vix_value = vix.get("rawValue") if vix else None

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
    if curve_value is not None:
        tide_pressure += 1 if curve_value < 0 else 0
    if tide_pressure > tide_easing:
        tide = "实际利率、美元指数、通胀/曲线综合偏紧，宏观潮水偏退。"
        tide_tone = "defensive"
    elif tide_easing > tide_pressure:
        tide = "实际利率或美元压力缓和，叠加通胀/就业降温，宏观潮水有转松线索。"
        tide_tone = "risk"
    else:
        tide = "利率、美元、通胀和就业信号不完全一致，宏观潮水暂不清晰。"
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
    if vix_value is not None:
        safe_votes += 1 if vix_value >= 20 else 0
        risk_votes += 1 if vix_value < 16 else 0
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
                f"美国 PCE / 核心PCE：{pce.get('actual', '-') if pce else '-'} / {core_pce.get('actual', '-') if core_pce else '-'}",
                f"美国10年实际利率：{real_rate.get('value', '-') if real_rate else '-'}；DXY：{dxy.get('value', '-') if dxy else '-'}",
                f"美国10Y：{us10y.get('value', '-') if us10y else '-'}；10Y-2Y：{curve_2s10s.get('value', '-') if curve_2s10s else '-'}",
                f"美国失业率：{unemployment.get('actual', '-') if unemployment else '-'}；初请：{claims.get('actual', '-') if claims else '-'}；ISM：{ism.get('actual', '-') if ism else '-'}",
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
                f"金油比：{gold_oil.get('value', '-') if gold_oil else '-'}（{change_text(gold_oil)}，噪音较大）",
                f"金特比：{btc_gold.get('value', '-') if btc_gold else '-'}（{change_text(btc_gold)}）",
                f"VIX：{vix.get('value', '-') if vix else '-'}",
            ],
            "howToUse": "看趋势，不迷信绝对值。多个比值同向时才增强判断；如果互相打架，说明市场在转折或缺少共识。",
            "news": news_for_bucket(news, "risk-regime"),
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
            "news": news_for_bucket(news, "crypto-rotation"),
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
            "news": news_for_bucket(news, "sentiment-extreme"),
        },
    ]


def main():
    generated_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    us_events, us_failures = get_us_events()
    china_events, china_failures = get_china_events()
    ratios, prices, price_failures = get_ratios_and_prices()
    crypto_metrics, crypto_failures = get_crypto_metrics()
    rate_metrics, rate_failures = get_rate_metrics()
    news, daily_briefing, news_failures = get_market_news()
    questions = build_questions(us_events + china_events, ratios, crypto_metrics, news, rate_metrics, prices)
    sources = [
        {
            "name": "FRED CSV",
            "status": "已接入，无需 key",
            "usage": "美国非农、CPI/PCE/核心PCE、初请失业金、ISM、失业率；官方时间序列，直连 CSV。",
        },
        {
            "name": "AkShare 国家统计局源",
            "status": "已接入，本地依赖",
            "usage": "中国 CPI/PPI 官方统计源封装，替代停更的金十宏观函数。",
        },
        {
            "name": "yfinance",
            "status": "已接入，本地依赖",
            "usage": "伦敦金、黄金、白银、WTI/Brent、铜、DXY、VIX、股指、USD/JPY、BTC、ETH 价格与比值。",
        },
        {
            "name": "alternative.me / CoinGecko",
            "status": "已接入，无需 key",
            "usage": "恐慌贪婪指数、加密总市值、BTC 市占率。",
        },
        {
            "name": "FRED 利率曲线",
            "status": "已接入，无需 key",
            "usage": "美国 2Y/10Y/30Y 国债收益率和 10Y-2Y 利差；中国国债收益率为 AkShare best-effort。",
        },
        {
            "name": "RSS / Google News / AkShare 新闻",
            "status": "已接入，无需 key",
            "usage": "CoinDesk、MarketWatch、Federal Reserve、Fed Speeches、Google News 宏观主题 RSS；新闻标题/摘要自动转中文，新闻联播为 best-effort。",
        },
    ]
    payload = {
        "generatedAt": f"{generated_at} +08:00",
        "summary": (
            f"宏观快照：{len(us_events) + len(china_events)} 个官方宏观指标，"
            f"{len(ratios)} 个价格比值，{len(crypto_metrics)} 个币圈宏观指标；"
            f"{len(rate_metrics)} 个利率曲线指标，{len(news)} 条实时新闻；"
            "美国走 FRED CSV，中国走国家统计局源，价格和币圈指标走免费公开接口。"
        ),
        "events": us_events + china_events,
        "questions": questions,
        "news": news,
        "dailyBriefing": daily_briefing,
        "ratios": ratios,
        "prices": prices,
        "cryptoMetrics": crypto_metrics,
        "rateMetrics": rate_metrics,
        "sources": sources,
        "failures": us_failures + china_failures + price_failures + crypto_failures + rate_failures + news_failures,
    }
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
