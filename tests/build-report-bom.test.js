const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync } = require("child_process");

const repoRoot = path.resolve(__dirname, "..");
const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "hotspot-bom-test-"));
const tempScripts = path.join(tempRoot, "scripts");
const rawDir = path.join(tempRoot, "raw");

fs.mkdirSync(tempScripts, { recursive: true });
fs.mkdirSync(rawDir, { recursive: true });
fs.copyFileSync(path.join(repoRoot, "scripts", "build-report.js"), path.join(tempScripts, "build-report.js"));

const bomJson = Buffer.concat([
  Buffer.from([0xef, 0xbb, 0xbf]),
  Buffer.from(
    JSON.stringify({
      id: "toutiao",
      sourceUrl: "https://newsnow.busiyi.world/api/s?id=toutiao&latest",
      error: "network unreachable",
      fetchedAt: "2026-05-31 00:00:00 +08:00",
    }),
    "utf8"
  ),
]);

fs.writeFileSync(path.join(rawDir, "toutiao.error.json"), bomJson);

const output = execFileSync("node", ["scripts/build-report.js", "--raw", rawDir], {
  cwd: tempRoot,
  encoding: "utf8",
});

assert.match(output, /调用 11 个平台/);

const latest = JSON.parse(fs.readFileSync(path.join(tempRoot, "data", "latest.json"), "utf8"));
assert.ok(Array.isArray(latest.failures), "expected failures array");
assert.strictEqual(latest.failures[0].platform, "今日头条");
assert.strictEqual(latest.failures[0].error, "network unreachable");

console.log("build-report BOM test passed");
