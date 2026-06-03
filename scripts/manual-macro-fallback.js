const fs = require("fs");
const path = require("path");

const repoRoot = path.resolve(__dirname, "..");
const macroPath = path.join(repoRoot, "data", "macro-latest.json");
const reportPath = path.join(repoRoot, "reports", "2026-06-03.json");

function normalize(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function loadJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function makeNews({ id, source, title, url, summary, buckets, published }) {
  return {
    id,
    source,
    title,
    titleZh: title,
    url,
    published,
    summary,
    summaryZh: summary,
    articleContent: summary,
    articleContentZh: summary,
    contentQuality: "summary",
    contentChars: summary.length,
    buckets,
  };
}

function findItem(items, matcher) {
  return items.find((item) => matcher(normalize(item.event)));
}

function pickRank(item, titleIncludes) {
  const ranks = Array.isArray(item?.platformRanks) ? item.platformRanks : [];
  if (titleIncludes) {
    const match = ranks.find((rank) => normalize(rank.title).includes(titleIncludes));
    if (match) return match;
  }
  return ranks[0] || { title: item?.event || "", url: "" };
}

function main() {
  const macro = loadJson(macroPath);
  const report = loadJson(reportPath);
  const published = "2026-06-03 08:06";

  const curated = [
    {
      item: findItem(report.items, (event) => event.includes("黄金替代美元")),
      source: "华尔街见闻热榜",
      summary: "欧央行与中文财经热榜同步聚焦黄金替代美元成为官方储备第一大资产，说明主权层面的避险偏好仍在抬升。",
      buckets: ["macro-tide", "risk-regime"],
    },
    {
      item: findItem(report.items, (event) => event.includes("特朗普操纵") && event.includes("美伊叙事")),
      source: "华尔街见闻热榜",
      summary: "特朗普对美伊谈判和以黎停火释放反复信号，地缘预期摇摆直接影响原油、黄金和全球风险偏好。",
      buckets: ["macro-tide", "risk-regime"],
    },
    {
      item: findItem(report.items, (event) => event.includes("美伊谈判反复背后")),
      source: "华尔街见闻热榜",
      summary: "美伊谈判反复与中东局势升温叠加，市场重新计入地缘风险溢价，避险交易重新活跃。",
      buckets: ["macro-tide", "risk-regime"],
    },
    {
      item: findItem(report.items, (event) => event.includes("伊朗相关油轮")),
      source: "凤凰网",
      summary: "美军打击伊朗相关油轮的消息强化了原油供应链与航运风险担忧，油价与黄金更容易获得地缘支撑。",
      buckets: ["risk-regime", "macro-tide"],
    },
    {
      item: findItem(report.items, (event) => event.includes("特朗普被曝同以总理通话爆粗口")),
      source: "澎湃新闻",
      summary: "特朗普与以色列总理通话风波说明美国在中东议题上的沟通仍不稳定，短线继续利好避险资产。",
      buckets: ["risk-regime", "macro-tide"],
    },
    {
      item: findItem(report.items, (event) => event.includes("AI与科技工具讨论")),
      titleIncludes: "AI热情力撑美股新高",
      source: "华尔街见闻热榜",
      summary: "美股再创新高、半导体大涨而比特币重挫，说明当前风险资产内部呈现“AI 股强、加密承压”的分化。",
      buckets: ["risk-regime", "crypto-rotation", "macro-tide"],
    },
    {
      item: findItem(report.items, (event) => event.includes("AI与科技工具讨论")),
      titleIncludes: "美股收盘 三大股指小幅收涨 标普首次突破7600点 AI狂热压倒中东忧虑",
      source: "财联社热门",
      summary: "标普首次突破 7600 点，说明权益市场仍在押注 AI 主线，但这种冒险情绪并没有同步扩散到币圈。",
      buckets: ["risk-regime", "crypto-rotation"],
    },
  ]
    .filter((entry) => entry.item)
    .map((entry, index) => {
      const rank = pickRank(entry.item, entry.titleIncludes);
      const title = rank.title || entry.item.event;
      return makeNews({
        id: `fallback-2026-06-03-${String(index + 1).padStart(2, "0")}`,
        source: entry.source,
        title,
        url: rank.url || "",
        summary: entry.summary,
        buckets: entry.buckets,
        published,
      });
    });

  if (!curated.length) {
    throw new Error("No fallback macro news could be derived from reports/2026-06-03.json");
  }

  const seen = new Set();
  const mergedNews = [...curated, ...(macro.news || [])].filter((item) => {
    const key = `${item.source}|${item.title}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  const bucketMap = new Map();
  for (const item of mergedNews) {
    for (const bucket of item.buckets || []) {
      const list = bucketMap.get(bucket) || [];
      if (list.length < 5) list.push(item);
      bucketMap.set(bucket, list);
    }
  }

  macro.generatedAt = "2026-06-03 08:06:54 +08:00";
  macro.summary =
    `宏观快照：${macro.events.length} 个官方宏观指标，${macro.ratios.length} 个价格比值，` +
    `${macro.cryptoMetrics.length} 个币圈宏观指标；${macro.rateMetrics.length} 个利率曲线指标，` +
    `${mergedNews.length} 条中文优先新闻。核心数据沿用上次成功采集结果，并补入 2026-06-03 中文宏观热榜。`;
  macro.news = mergedNews.slice(0, 80);
  macro.questions = (macro.questions || []).map((question) => ({
    ...question,
    news: bucketMap.get(question.id) || question.news || [],
  }));
  macro.failures = [
    ...((macro.failures || []).filter((entry) => !String(entry).includes("Python runtime fallback"))),
    "Python runtime fallback: 2026-06-03 本地 .python-deps 访问被拒绝，核心宏观/价格数据沿用 2026-06-02 最近一次成功采集结果；中文新闻已使用 2026-06-03 本地热榜报告补入。",
  ];

  fs.writeFileSync(macroPath, `${JSON.stringify(macro, null, 2)}\n`, "utf8");
  process.stdout.write(JSON.stringify({ curated: curated.length, titles: curated.map((item) => item.title) }, null, 2));
}

main();
