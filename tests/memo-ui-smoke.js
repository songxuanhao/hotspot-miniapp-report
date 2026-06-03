const fs = require("fs");
const path = require("path");

const repoRoot = path.resolve(__dirname, "..");
const memoHtml = fs.readFileSync(path.join(repoRoot, "memo.html"), "utf8");
const indexHtml = fs.readFileSync(path.join(repoRoot, "index.html"), "utf8");
const macroHtml = fs.readFileSync(path.join(repoRoot, "macro.html"), "utf8");

function assert(condition, message) {
  if (!condition) {
    console.error(`FAIL: ${message}`);
    process.exitCode = 1;
  }
}

const script = [...memoHtml.matchAll(/<script>([\s\S]*?)<\/script>/g)]
  .map((match) => match[1])
  .join("\n");

try {
  new Function(script);
} catch (error) {
  console.error(error);
  assert(false, "memo.html inline JavaScript must parse");
}

[
  "<title>工作备忘录</title>",
  'href="./memo.html"',
  'id="projectName"',
  'id="requirement"',
  'id="launchTime"',
  'id="progress"',
  'id="todos"',
  'id="rawInput"',
  'id="aiEndpoint"',
  'id="saveAiEndpointButton"',
  'id="aiStatus"',
  'id="summarizeButton"',
  'id="confirmDraftButton"',
  'id="historyList"',
  'id="versionPreview"',
  "function summarizeText",
  "function buildAiPrompt",
  "function requestAiSummary",
  "function parseAiResponse",
  "function normalizeDraft",
  "function summarizeTextLocally",
  "function createDraft",
  "function confirmDraft",
  "function renderHistory",
  "function renderProjectList",
  "function saveStore",
  "memoStoreV1",
  "memoAiEndpointV1",
  "真正 AI 总结",
  "本地兜底整理",
].forEach((needle) => assert(memoHtml.includes(needle), `memo.html should include ${needle}`));

[
  indexHtml,
  macroHtml,
].forEach((html, index) => {
  assert(html.includes('href="./memo.html"'), `${index ? "macro" : "index"} page should link memo tab`);
});

if (!process.exitCode) {
  console.log("memo ui smoke ok");
}
