const fs = require("fs");
const path = require("path");

const repoRoot = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(repoRoot, "index.html"), "utf8");

function assert(condition, message) {
  if (!condition) {
    console.error(`FAIL: ${message}`);
    process.exitCode = 1;
  }
}

const script = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)]
  .map((match) => match[1])
  .join("\n");

try {
  new Function(script);
} catch (error) {
  console.error(error);
  assert(false, "index.html inline JavaScript must parse");
}

[
  "function decisionKind",
  "function decisionTone",
  "function renderDecisionBadge",
  "function renderUseCaseStrip",
  "function renderOpportunitySummary",
  "function renderDecisionMetrics",
  "decision-metrics",
  "class=\"opportunity-summary\"",
  "class=\"usecase-strip\"",
  "class=\"decision-badge",
  "用户为什么会用",
  "研发边界",
  "微信搜索词",
  "可做机会",
  "谨慎机会",
  "放弃热点",
].forEach((needle) => assert(html.includes(needle), `index.html should include ${needle}`));

[
  "收藏保存在当前浏览器；复制按钮会把单个小程序机会整理成可直接发给自己或团队的文本。",
  "可评估机会",
  "高优先级",
].forEach((needle) => assert(!html.includes(needle), `remove low-value UI copy: ${needle}`));

if (!process.exitCode) {
  console.log("hotspot ui smoke ok");
}
