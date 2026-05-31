const fs = require("fs");
const path = require("path");

const repoRoot = path.resolve(__dirname, "..");
const htmlPath = path.join(repoRoot, "macro.html");
const html = fs.readFileSync(htmlPath, "utf8");

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
  assert(false, "macro.html inline JavaScript must parse");
}

[
  'id="headlineDecision"',
  'id="assetActions"',
  'id="evidenceCards"',
  'id="supportEvidence"',
  'id="counterEvidence"',
  'id="watchlist"',
  'id="riskSchedule"',
].forEach((needle) => assert(html.includes(needle), `macro.html should include ${needle}`));

[
  "为什么放入日历",
  "新闻按发布时间落到月历里",
  "用来解释宏观倾向",
].forEach((needle) => assert(!html.includes(needle), `remove system-facing copy: ${needle}`));

if (!process.exitCode) {
  console.log("macro cockpit smoke ok");
}
