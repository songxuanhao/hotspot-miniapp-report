const fs = require("fs");
const path = require("path");

const repoRoot = path.resolve(__dirname, "..");
const collector = fs.readFileSync(path.join(repoRoot, "scripts", "macro-akshare.py"), "utf8");

function assert(condition, message) {
  if (!condition) {
    console.error(`FAIL: ${message}`);
    process.exitCode = 1;
  }
}

[
  "def fetch_article_content",
  "def enrich_news_with_fulltext",
  "articleContent",
  "contentQuality",
  "contentChars",
  "腾讯财经",
  "https://finance.qq.com",
  "def eastmoney_realtime_news",
  "东方财富全球快讯",
  "https://np-weblist.eastmoney.com/comm/web/getFastNewsList",
  "https://finance.eastmoney.com/a/",
].forEach((needle) => assert(collector.includes(needle), `macro collector should include ${needle}`));

if (!process.exitCode) {
  console.log("macro news fulltext test ok");
}
