const fs = require("fs");
const os = require("os");
const path = require("path");
const net = require("net");
const tls = require("tls");
const https = require("https");
const { spawnSync } = require("child_process");

const PLATFORMS = [
  "toutiao",
  "baidu",
  "wallstreetcn-hot",
  "thepaper",
  "bilibili-hot-search",
  "cls-hot",
  "ifeng",
  "tieba",
  "weibo",
  "douyin",
  "zhihu",
];

const REQUEST_HEADERS = [
  "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
  "Accept: application/json,text/plain,*/*",
  "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8",
  "Accept-Encoding: identity",
  "Connection: close",
];

function hasFlag(name) {
  return process.argv.includes(name);
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: path.resolve(__dirname, ".."),
    stdio: "inherit",
    shell: false,
    ...options,
  });
  if (result.status !== 0) {
    throw new Error(`${command} ${args.join(" ")} failed with exit code ${result.status}`);
  }
}

function fetchDirect(url) {
  return new Promise((resolve, reject) => {
    https
      .get(
        url,
        {
          headers: {
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
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
          resolve(Buffer.concat(chunks));
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
      const rest = header.slice(marker + 4);
      const secure = tls.connect({ socket, servername: target.hostname });
      const chunks = [];
      let response = Buffer.alloc(0);
      secure.once("secureConnect", () => {
        secure.write(
          [
            `GET ${target.pathname}${target.search} HTTP/1.1`,
            `Host: ${target.hostname}`,
            ...REQUEST_HEADERS,
            "",
            "",
          ].join("\r\n"),
        );
        if (rest.length) secure.unshift(rest);
      });
      secure.on("data", (data) => chunks.push(data));
      secure.once("error", reject);
      secure.once("end", () => {
        response = Buffer.concat(chunks);
        const bodyMarker = response.indexOf("\r\n\r\n");
        const head = response.slice(0, bodyMarker).toString("utf8");
        const body = response.slice(bodyMarker + 4);
        const status = head.split("\r\n")[0];
        if (!/ 2\d\d /.test(status)) {
          reject(new Error(`HTTP failed: ${status}`));
          return;
        }
        resolve(body);
      });
    });
  });
}

function fetchApi(url) {
  const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY || "http://127.0.0.1:10808";
  if (proxy) return fetchViaHttpProxy(url, proxy);
  return fetchDirect(url);
}

async function fetchPlatform(id, rawDir) {
  const url = `https://newsnow.busiyi.world/api/s?id=${id}&latest`;
  const target = path.join(rawDir, `${id}.json`);
  const errorTarget = path.join(rawDir, `${id}.error.json`);
  try {
    const body = await fetchApi(url);
    fs.writeFileSync(target, body);
    console.log(`Fetched ${id} -> ${target}`);
  } catch (error) {
    fs.writeFileSync(
      errorTarget,
      `${JSON.stringify({ id, sourceUrl: url, error: error.message, fetchedAt: new Date().toISOString() }, null, 2)}\n`,
      "utf8",
    );
    console.warn(`Failed ${id}: ${error.message}`);
  }
}

async function main() {
  if (hasFlag("--validate-only")) {
    console.log("Daily report runner validated.");
    return;
  }

  const rawDir = fs.mkdtempSync(path.join(os.tmpdir(), "hotspot-miniapp-report-"));

  if (hasFlag("--fetch-test")) {
    await fetchPlatform("weibo", rawDir);
    const data = JSON.parse(fs.readFileSync(path.join(rawDir, "weibo.json"), "utf8"));
    console.log(`Fetch test ok: ${data.status}, first=${data.items?.[0]?.title || "-"}`);
    return;
  }

  for (const id of PLATFORMS) {
    await fetchPlatform(id, rawDir);
  }

  run("node", [".\\scripts\\build-report.js", "--raw", rawDir]);

  const status = spawnSync("git", ["status", "--short"], {
    cwd: path.resolve(__dirname, ".."),
    encoding: "utf8",
    shell: false,
  });
  if (!status.stdout.trim()) {
    console.log("No report changes to commit.");
    return;
  }

  run("git", ["add", "data/latest.json", "data/history.json", "reports"]);
  run("git", ["commit", "-m", `Run daily hotspot report ${new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Shanghai" })}`]);

  if (hasFlag("--no-push")) {
    console.log("No push requested.");
    return;
  }

  run("git", ["push"], {
    env: {
      ...process.env,
      HTTPS_PROXY: process.env.HTTPS_PROXY || "http://127.0.0.1:10808",
      HTTP_PROXY: process.env.HTTP_PROXY || "http://127.0.0.1:10808",
    },
  });
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
