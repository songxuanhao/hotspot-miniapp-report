const fs = require("fs");
const path = require("path");
const net = require("net");
const tls = require("tls");
const https = require("https");
const { spawnSync } = require("child_process");

const repoRoot = path.resolve(__dirname, "..");
const bundledPython = "C:\\Users\\26960\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\python\\python.exe";

const BLS_SERIES = [
  {
    id: "CES0000000001",
    title: "美国非农就业人数",
    country: "美国",
    category: "就业",
    unit: "千人",
    notes: "BLS Current Employment Statistics，总非农就业，季调。",
  },
  {
    id: "CUSR0000SA0",
    title: "美国 CPI",
    country: "美国",
    category: "通胀",
    unit: "指数",
    notes: "BLS CPI-U All items，季调。",
  },
  {
    id: "WPUFD4",
    title: "美国 PPI 最终需求",
    country: "美国",
    category: "通胀",
    unit: "指数",
    notes: "BLS Producer Price Index，Final Demand。",
  },
];

const SOURCES = [
  {
    name: "AkShare",
    status: fs.existsSync(path.join(repoRoot, ".python-deps", "akshare")) ? "已接入，本地依赖" : "待安装本地依赖",
    usage: "美国/中国宏观数据，字段通常包含今值、预测值、前值；免费但属于第三方公开源封装。",
    url: "https://akshare.akfamily.xyz/",
  },
  {
    name: "yfinance",
    status: fs.existsSync(path.join(repoRoot, ".python-deps", "yfinance")) ? "已接入，本地依赖" : "待安装本地依赖",
    usage: "用 GC=F、SI=F、CL=F 收盘价计算金银比、金油比；免费源可能偶发限流。",
    url: "https://github.com/ranaroussi/yfinance",
  },
  {
    name: "BLS Public Data API",
    status: "保留兜底，无需 key",
    usage: "美国非农、CPI、PPI 实际值和前值；不提供市场预期，且不适合抢时效。",
    url: "https://api.bls.gov/publicAPI/v2/timeseries/data/",
  },
  {
    name: "Trading Economics Calendar API",
    status: process.env.TRADING_ECONOMICS_KEY ? "可接入，已检测到 key" : "待接 API key",
    usage: "最适合经济日历、预期值、实际值、前值、国家/重要性筛选；可覆盖中国 CPI/PPI。",
    url: "https://docs.tradingeconomics.com/economic_calendar/",
  },
  {
    name: "FRED API",
    status: process.env.FRED_API_KEY ? "可接入，已检测到 key" : "待接免费 API key",
    usage: "适合美国宏观时间序列、黄金、白银、WTI 等，用于金银比、金油比。",
    url: "https://fred.stlouisfed.org/docs/api/api_key.html",
  },
  {
    name: "中国国家统计局数据接口",
    status: "待确认指标码和稳定性",
    usage: "可作为中国 CPI/PPI 官方来源，但公开接口文档不完整，建议先用 Trading Economics 做日历。",
    url: "https://data.stats.gov.cn/",
  },
];

function hasFlag(name) {
  return process.argv.includes(name);
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: repoRoot,
    stdio: "inherit",
    shell: false,
    ...options,
  });
  if (result.status !== 0) throw new Error(`${command} ${args.join(" ")} failed`);
}

function loadAkshareData() {
  const candidates = [
    process.env.PYTHON,
    bundledPython,
    "python",
  ].filter(Boolean);
  const script = path.join(repoRoot, "scripts", "macro-akshare.py");
  for (const python of candidates) {
    const result = spawnSync(python, [script], {
      cwd: repoRoot,
      encoding: "utf8",
      shell: false,
      env: {
        ...process.env,
        PYTHONPATH: path.join(repoRoot, ".python-deps"),
        PYTHONIOENCODING: "utf-8",
        HTTPS_PROXY: process.env.HTTPS_PROXY || "http://127.0.0.1:10808",
        HTTP_PROXY: process.env.HTTP_PROXY || "http://127.0.0.1:10808",
      },
      timeout: 120000,
    });
    if (result.status === 0 && result.stdout.trim()) {
      return JSON.parse(result.stdout);
    }
  }
  return { events: [], ratios: [], failures: [{ source: "AkShare/yfinance", error: "Python macro source failed or dependencies missing" }] };
}

function fetchDirect(url) {
  return new Promise((resolve, reject) => {
    https
      .get(
        url,
        {
          headers: {
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            accept: "application/json,text/plain,*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "accept-encoding": "identity",
          },
        },
        (response) => {
          const chunks = [];
          response.on("data", (chunk) => chunks.push(chunk));
          response.on("end", () => {
            if (response.statusCode < 200 || response.statusCode >= 300) {
              reject(new Error(`HTTP ${response.statusCode}`));
              return;
            }
            resolve(Buffer.concat(chunks).toString("utf8"));
          });
        },
      )
      .on("error", reject);
  });
}

function fetchViaHttpProxy(url, proxyUrl) {
  const target = new URL(url);
  const proxy = new URL(proxyUrl);
  const port = Number(proxy.port || 80);

  return new Promise((resolve, reject) => {
    const socket = net.connect(port, proxy.hostname);
    socket.setTimeout(45000);
    socket.once("error", reject);
    socket.once("timeout", () => {
      socket.destroy();
      reject(new Error("Proxy connection timeout"));
    });
    socket.once("connect", () => {
      socket.write(
        [
          `CONNECT ${target.hostname}:443 HTTP/1.1`,
          `Host: ${target.hostname}:443`,
          "Proxy-Connection: keep-alive",
          "",
          "",
        ].join("\r\n"),
      );
    });

    let header = Buffer.alloc(0);
    socket.on("data", function onProxyData(chunk) {
      header = Buffer.concat([header, chunk]);
      const marker = header.indexOf("\r\n\r\n");
      if (marker === -1) return;
      socket.off("data", onProxyData);
      const statusLine = header.slice(0, marker).toString("utf8").split("\r\n")[0];
      if (!/ 200 /.test(statusLine)) {
        socket.destroy();
        reject(new Error(`Proxy CONNECT failed: ${statusLine}`));
        return;
      }
      const secure = tls.connect({ socket, servername: target.hostname });
      const chunks = [];
      secure.once("secureConnect", () => {
        secure.write(
          [
            `GET ${target.pathname}${target.search} HTTP/1.1`,
            `Host: ${target.hostname}`,
            "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept: application/json,text/plain,*/*",
            "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding: identity",
            "Connection: close",
            "",
            "",
          ].join("\r\n"),
        );
      });
      secure.on("data", (data) => chunks.push(data));
      secure.once("error", reject);
      secure.once("end", () => {
        const response = Buffer.concat(chunks);
        const bodyMarker = response.indexOf("\r\n\r\n");
        const head = response.slice(0, bodyMarker).toString("utf8");
        let body = response.slice(bodyMarker + 4);
        const status = head.split("\r\n")[0];
        if (!/ 2\d\d /.test(status)) {
          reject(new Error(`HTTP failed: ${status}`));
          return;
        }
        if (/transfer-encoding:\s*chunked/i.test(head)) body = decodeChunked(body);
        resolve(body.toString("utf8"));
      });
    });
  });
}

function decodeChunked(buffer) {
  const chunks = [];
  let offset = 0;
  while (offset < buffer.length) {
    const lineEnd = buffer.indexOf("\r\n", offset);
    if (lineEnd === -1) break;
    const sizeText = buffer.slice(offset, lineEnd).toString("ascii").split(";")[0].trim();
    const size = Number.parseInt(sizeText, 16);
    if (!size) break;
    const start = lineEnd + 2;
    chunks.push(buffer.slice(start, start + size));
    offset = start + size + 2;
  }
  return Buffer.concat(chunks);
}

function fetchText(url) {
  const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY || "http://127.0.0.1:10808";
  if (proxy) return fetchViaHttpProxy(url, proxy);
  return fetchDirect(url);
}

function latestTwo(series) {
  const data = Array.isArray(series.data) ? series.data : [];
  const cleaned = data
    .filter((item) => item.value && item.period && !item.period.includes("M13"))
    .sort((a, b) => `${b.year}${b.period}`.localeCompare(`${a.year}${a.period}`));
  return [cleaned[0], cleaned[1]];
}

function formatPeriod(row) {
  if (!row) return "-";
  return `${row.year} ${row.periodName || row.period}`;
}

function compareActual(actual, expected) {
  if (expected === "" || expected == null) return "暂无预期";
  const a = Number(actual);
  const e = Number(expected);
  if (Number.isNaN(a) || Number.isNaN(e)) return "暂无预期";
  if (a > e) return "超出预期";
  if (a < e) return "不及预期";
  return "符合预期";
}

async function fetchBlsEvents() {
  const events = [];
  for (const series of BLS_SERIES) {
    const url = `https://api.bls.gov/publicAPI/v2/timeseries/data/${series.id}`;
    const payload = JSON.parse(await fetchText(url));
    const item = payload.Results?.series?.[0];
    const [latest, previous] = latestTwo(item || {});
    if (!latest) continue;
    events.push({
      id: `bls-${series.id}`,
      date: formatPeriod(latest),
      time: "已公布",
      period: formatPeriod(latest),
      country: series.country,
      category: series.category,
      title: series.title,
      expected: "",
      actual: `${latest.value} ${series.unit}`,
      previous: previous ? `${previous.value} ${series.unit}` : "",
      surprise: compareActual(latest.value, ""),
      status: "released",
      importance: "high",
      source: "BLS Public Data API",
      notes: `${series.notes}；BLS 免费 API 只提供实际值，预期值需接经济日历 API。`,
    });
  }
  return events;
}

function watchEvents() {
  return [
    {
      id: "watch-china-cpi",
      date: "待接经济日历",
      time: "通常每月上旬",
      period: "-",
      country: "中国",
      category: "通胀",
      title: "中国 CPI",
      expected: "待接 API",
      actual: "待公布",
      previous: "待接 API",
      surprise: "待公布",
      status: "watch",
      importance: "high",
      source: "Trading Economics / 国家统计局",
      notes: "AkShare 中国宏观历史值已接入；若需要公布前精确日历和更稳预期，可再接 Trading Economics。",
    },
    {
      id: "watch-china-ppi",
      date: "待接经济日历",
      time: "通常每月上旬",
      period: "-",
      country: "中国",
      category: "通胀",
      title: "中国 PPI",
      expected: "待接 API",
      actual: "待公布",
      previous: "待接 API",
      surprise: "待公布",
      status: "watch",
      importance: "high",
      source: "Trading Economics / 国家统计局",
      notes: "AkShare 中国宏观历史值已接入；若需要公布前精确日历和更稳预期，可再接 Trading Economics。",
    },
    {
      id: "watch-us-nfp-calendar",
      date: "待接经济日历",
      time: "通常每月第一个周五 20:30/21:30 北京时间",
      period: "-",
      country: "美国",
      category: "就业",
      title: "美国非农就业公布日",
      expected: "待接 API",
      actual: "BLS 实际值已接",
      previous: "BLS 前值已接",
      surprise: "待接预期",
      status: "watch",
      importance: "high",
      source: "Trading Economics Calendar API",
      notes: "AkShare 已提供历史今值/预测值/前值；公布前提醒仍建议用经济日历源。",
    },
  ];
}

function ratios() {
  return [
    {
      name: "金银比",
      value: process.env.FRED_API_KEY ? "待启用 FRED 计算" : "待接 FRED_API_KEY",
      notes: "建议用 FRED 黄金、白银日度价格序列计算。无 key 时先展示为待接。",
    },
    {
      name: "金油比",
      value: process.env.FRED_API_KEY ? "待启用 FRED 计算" : "待接 FRED_API_KEY",
      notes: "建议用 FRED 黄金价格和 WTI 原油日度价格计算。",
    },
  ];
}

function writeJson(file, data) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, `${JSON.stringify(data, null, 2)}\n`, "utf8");
}

async function main() {
  if (hasFlag("--validate-only")) {
    console.log("Macro runner validated.");
    return;
  }

  const generatedAt = `${new Date().toLocaleString("zh-CN", { hour12: false, timeZone: "Asia/Shanghai" })} +08:00`;
  const failures = [];
  const akshare = loadAkshareData();
  let events = Array.isArray(akshare.events) ? akshare.events : [];
  let ratioItems = Array.isArray(akshare.ratios) ? akshare.ratios : [];
  failures.push(...(Array.isArray(akshare.failures) ? akshare.failures : []));

  if (!events.length) {
    try {
      events = await fetchBlsEvents();
    } catch (error) {
      failures.push({ source: "BLS Public Data API", error: error.message });
    }
  }

  if (!ratioItems.length) ratioItems = ratios();
  events = [...events, ...watchEvents()];
  if (!events.length) throw new Error("No macro events produced; refusing to publish an empty macro report.");

  const releasedCount = events.filter((event) => event.status === "released").length;
  const report = {
    generatedAt,
    summary: `金融宏观日历：${events.length} 个事件，${releasedCount} 个已公布数据；AkShare 提供今值/预测值/前值，yfinance 计算金银比/金油比，BLS 保留兜底。`,
    events,
    ratios: ratioItems,
    sources: SOURCES,
    failures,
  };

  writeJson(path.join(repoRoot, "data/macro-latest.json"), report);

  if (hasFlag("--no-commit")) {
    console.log(report.summary);
    return;
  }

  const status = spawnSync("git", ["status", "--short", "data/macro-latest.json"], {
    cwd: repoRoot,
    encoding: "utf8",
    shell: false,
  });
  if (!status.stdout.trim()) {
    console.log("No macro changes to commit.");
    return;
  }
  run("git", ["add", "data/macro-latest.json"]);
  run("git", ["commit", "-m", "Run macro calendar report"]);
  if (!hasFlag("--no-push")) {
    run("git", ["push"], {
      env: {
        ...process.env,
        HTTPS_PROXY: process.env.HTTPS_PROXY || "http://127.0.0.1:10808",
        HTTP_PROXY: process.env.HTTP_PROXY || "http://127.0.0.1:10808",
      },
    });
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
