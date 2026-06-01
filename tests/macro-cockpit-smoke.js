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
  'id="assetSpotlight"',
  'id="evidenceCards"',
  'id="supportEvidence"',
  'id="counterEvidence"',
  'id="watchlist"',
  'id="riskSchedule"',
  'id="assetDrawer"',
  'id="drawerChart"',
].forEach((needle) => assert(html.includes(needle), `macro.html should include ${needle}`));

[
  "function summarizeItem",
  "function summarizeNewsConclusion",
  "function articleTypeFor",
  "function renderAccordionItems",
  "function renderAssetSpotlight",
  "function openAssetDrawer",
  "function drawAssetChart",
  "function niceAxisTicks",
  "function drawHoverCrosshair",
  "function handleChartPointer",
  "data-accordion-id",
  "data-asset-key",
  'id="chartTooltip"',
].forEach((needle) => assert(html.includes(needle), `macro.html should include ${needle}`));

const dataPath = path.join(repoRoot, "data", "macro-latest.json");
const data = JSON.parse(fs.readFileSync(dataPath, "utf8"));
assert(Array.isArray(data.assetHistory), "macro-latest.json should include assetHistory");
if (Array.isArray(data.assetHistory)) {
  assert(data.assetHistory.length >= 3, "assetHistory should include at least three tracked assets");
  assert(
    data.assetHistory.some((asset) => Array.isArray(asset.points) && asset.points.length >= 20),
    "assetHistory should include chartable price points"
  );
}

[
  "为什么放入日历",
  "新闻按发布时间落到月历里",
  "用来解释宏观倾向",
].forEach((needle) => assert(!html.includes(needle), `remove system-facing copy: ${needle}`));

if (!process.exitCode) {
  console.log("macro cockpit smoke ok");
}
