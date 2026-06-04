const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const repoRoot = path.resolve(__dirname, "..");
const bundledPython = "C:\\Users\\26960\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\python\\python.exe";

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

function runPythonCollector() {
  const candidates = [process.env.PYTHON, bundledPython, "python"].filter(Boolean);
  const script = path.join(repoRoot, "scripts", "macro-akshare.py");
  const errors = [];

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
      timeout: 300000,
    });
    if (result.status === 0 && result.stdout.trim()) {
      return JSON.parse(result.stdout);
    }
    errors.push(`${python}: ${result.stderr || result.stdout || `exit ${result.status}`}`);
  }

  throw new Error(`Macro collector failed: ${errors.join(" | ")}`);
}

function runRuntimeFallbackCollector() {
  const script = path.join(repoRoot, "scripts", "macro-runtime-fallback.py");
  const result = spawnSync(bundledPython, [script], {
    cwd: repoRoot,
    encoding: "utf8",
    shell: false,
    env: {
      ...process.env,
      PYTHONIOENCODING: "utf-8",
      HTTPS_PROXY: process.env.HTTPS_PROXY || "http://127.0.0.1:10808",
      HTTP_PROXY: process.env.HTTP_PROXY || "http://127.0.0.1:10808",
    },
    timeout: 300000,
  });
  if (result.status === 0 && result.stdout.trim()) {
    return JSON.parse(result.stdout);
  }
  throw new Error(`Runtime fallback collector failed: ${result.stderr || result.stdout || `exit ${result.status}`}`);
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

  let report;
  try {
    report = runPythonCollector();
  } catch (primaryError) {
    console.warn("Primary macro collector failed; using runtime fallback.");
    report = runRuntimeFallbackCollector();
  }
  const eventCount = Array.isArray(report.events) ? report.events.length : 0;
  const ratioCount = Array.isArray(report.ratios) ? report.ratios.length : 0;
  const cryptoCount = Array.isArray(report.cryptoMetrics) ? report.cryptoMetrics.length : 0;
  if (!eventCount && !ratioCount && !cryptoCount) {
    throw new Error("No macro data produced; refusing to publish an empty macro report.");
  }

  writeJson(path.join(repoRoot, "data", "macro-latest.json"), report);

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
