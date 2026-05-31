import json
import math
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(".python-deps"))

import akshare as ak
import pandas as pd
import yfinance as yf


SERIES = [
    ("macro_usa_non_farm", "美国非农就业人数", "美国", "就业", "万人"),
    ("macro_usa_unemployment_rate", "美国失业率", "美国", "就业", "%"),
    ("macro_usa_cpi_monthly", "美国 CPI 月率", "美国", "通胀", "%"),
    ("macro_usa_core_cpi_monthly", "美国核心 CPI 月率", "美国", "通胀", "%"),
    ("macro_china_cpi_monthly", "中国 CPI 月率", "中国", "通胀", "%"),
    ("macro_china_cpi_yearly", "中国 CPI 年率", "中国", "通胀", "%"),
    ("macro_china_ppi_yearly", "中国 PPI 年率", "中国", "通胀", "%"),
]


def clean_value(value):
    if value is None:
        return ""
    try:
        if isinstance(value, float) and math.isnan(value):
            return ""
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value)


def fmt(value, unit=""):
    value = clean_value(value)
    if not value:
        return ""
    return f"{value}{unit}" if unit else value


def surprise(actual, expected):
    actual = clean_value(actual)
    expected = clean_value(expected)
    if not actual or not expected:
        return "暂无预期"
    try:
        a = float(actual)
        e = float(expected)
    except ValueError:
        return "暂无预期"
    if a > e:
        return "超出预期"
    if a < e:
        return "不及预期"
    return "符合预期"


def latest_rows_from_macro():
    events = []
    failures = []
    for func_name, title, country, category, unit in SERIES:
        try:
            data = getattr(ak, func_name)()
            if data.empty:
                raise RuntimeError("empty dataframe")
            data = data.dropna(subset=["今值"], how="all")
            row = data.iloc[-1]
            events.append(
                {
                    "id": f"akshare-{func_name}",
                    "date": clean_value(row.get("日期")),
                    "time": "已公布",
                    "period": clean_value(row.get("日期")),
                    "country": country,
                    "category": category,
                    "title": title,
                    "expected": fmt(row.get("预测值"), unit),
                    "actual": fmt(row.get("今值"), unit),
                    "previous": fmt(row.get("前值"), unit),
                    "surprise": surprise(row.get("今值"), row.get("预测值")),
                    "status": "released",
                    "importance": "high",
                    "source": f"AkShare {func_name}",
                    "notes": "AkShare 返回今值/预测值/前值；若预测值为空，则只展示实际与前值。",
                }
            )
        except Exception as error:
            failures.append({"source": func_name, "error": str(error)})
    return events, failures


def economic_calendar():
    events = []
    failures = []
    try:
        data = ak.news_economic_baidu()
        if data.empty:
            return events, failures
        keywords = ("非农", "失业率", "CPI", "PPI", "利率", "GDP", "PMI", "原油库存")
        data = data[data["事件"].astype(str).str.contains("|".join(keywords), case=False, na=False)]
        data = data.tail(30)
        for index, row in data.iterrows():
            actual = clean_value(row.get("公布"))
            expected = clean_value(row.get("预期"))
            events.append(
                {
                    "id": f"calendar-{index}",
                    "date": clean_value(row.get("日期")),
                    "time": clean_value(row.get("时间")),
                    "period": clean_value(row.get("日期")),
                    "country": clean_value(row.get("地区")),
                    "category": "经济日历",
                    "title": clean_value(row.get("事件")),
                    "expected": expected,
                    "actual": actual or "待公布",
                    "previous": clean_value(row.get("前值")),
                    "surprise": surprise(actual, expected) if actual else "待公布",
                    "status": "released" if actual else "watch",
                    "importance": "high" if str(row.get("重要性")) in ("2", "3") else "normal",
                    "source": "AkShare news_economic_baidu",
                    "notes": "百度股市通经济日历，适合作为预期/公布/前值来源；免费源可能偶发延迟或字段为空。",
                }
            )
    except Exception as error:
        failures.append({"source": "news_economic_baidu", "error": str(error)})
    return events, failures


def latest_close(symbol):
    data = yf.download(symbol, period="10d", interval="1d", progress=False, auto_adjust=False)
    if data.empty:
        raise RuntimeError(f"empty yfinance data for {symbol}")
    close = data["Close"]
    if hasattr(close, "columns"):
        close = close.iloc[:, 0]
    return float(close.dropna().iloc[-1])


def ratios():
    failures = []
    items = []
    try:
        gold = latest_close("GC=F")
        silver = latest_close("SI=F")
        oil = latest_close("CL=F")
        items.append(
            {
                "name": "金银比",
                "value": f"{gold / silver:.2f}",
                "notes": f"yfinance 期货收盘价计算：黄金 {gold:.2f} / 白银 {silver:.2f}。",
            }
        )
        items.append(
            {
                "name": "金油比",
                "value": f"{gold / oil:.2f}",
                "notes": f"yfinance 期货收盘价计算：黄金 {gold:.2f} / WTI 原油 {oil:.2f}。",
            }
        )
    except Exception as error:
        failures.append({"source": "yfinance-ratios", "error": str(error)})
        items.extend(
            [
                {"name": "金银比", "value": "获取失败", "notes": "yfinance 免费源暂不可用，保留上一份有效报告更安全。"},
                {"name": "金油比", "value": "获取失败", "notes": "yfinance 免费源暂不可用，保留上一份有效报告更安全。"},
            ]
        )
    return items, failures


def main():
    macro_events, macro_failures = latest_rows_from_macro()
    calendar_events, calendar_failures = economic_calendar()
    ratio_items, ratio_failures = ratios()
    payload = {
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "events": macro_events + calendar_events,
        "ratios": ratio_items,
        "failures": macro_failures + calendar_failures + ratio_failures,
    }
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
