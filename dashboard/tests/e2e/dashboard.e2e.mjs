import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const dashboardRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const port = Number(process.env.E2E_PORT || 3107);
const baseUrl = `http://127.0.0.1:${port}`;
const nextCli = path.join(dashboardRoot, "node_modules", "next", "dist", "bin", "next");
const serverOutput = [];
let serverExited = false;

const server = spawn(process.execPath, [nextCli, "start", "--hostname", "127.0.0.1", "--port", String(port)], {
  cwd: dashboardRoot,
  env: { ...process.env, NODE_ENV: "production" },
  shell: false,
  stdio: ["ignore", "pipe", "pipe"],
  windowsHide: true,
});

server.stdout.setEncoding("utf-8");
server.stderr.setEncoding("utf-8");
server.stdout.on("data", (chunk) => serverOutput.push(chunk));
server.stderr.on("data", (chunk) => serverOutput.push(chunk));
server.on("exit", () => {
  serverExited = true;
});

try {
  await waitForServer();
  await testDashboardShell();
  await testDefaultBacktest();
  await testDeterministicResult();
  await testHolidayDateMapping();
  await testValidationErrors();
  console.log("E2E PASS: 7 scenarios");
} catch (error) {
  console.error(serverOutput.join(""));
  throw error;
} finally {
  if (!serverExited) {
    const exitPromise = new Promise((resolve) => server.once("exit", resolve));
    server.kill();
    await Promise.race([exitPromise, new Promise((resolve) => setTimeout(resolve, 3_000))]);
  }
}

async function waitForServer() {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    if (serverExited) throw new Error("E2E server stopped before it became ready");
    try {
      const response = await fetch(baseUrl, { signal: AbortSignal.timeout(1_000) });
      if (response.ok) return;
    } catch {
      // The server is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error("E2E server did not become ready within 30 seconds");
}

async function testDashboardShell() {
  const response = await fetch(baseUrl);
  const html = await response.text();
  assert.equal(response.status, 200);
  assert.match(html, /순수 무한매수 V4 백테스트/);
  assert.match(html, /조건을 정해 보세요/);
  assert.match(html, /백테스트 실행/);
  assert.match(html, /과거의 백테스트 결과는 미래의 수익이나 성과를 보장하지 않습니다/);
}

async function testDefaultBacktest() {
  const result = await postBacktest({
    symbol: "TQQQ",
    division_count: 40,
    capital: 3_000,
    start_date: "2021-07-10",
    end_date: "2026-07-10",
  });
  assert.equal(result.response.status, 200);
  assert.equal(result.body.request.symbol, "TQQQ");
  assert.equal(result.body.request.division_count, 40);
  assert.equal(result.body.summary.trading_days, 1255);
  assert.equal(result.body.daily.length, result.body.summary.trading_days);
  assert.ok(result.body.events.length > 0);
  assert.ok(result.body.weather_daily.length > 0);
  assert.equal(result.body.weather_daily.at(-1).date, "2026-07-10");
  assert.equal(result.body.weather_daily.at(-1).signal_date, "2026-07-09");
  assert.equal(result.body.weather_daily.at(-1).weather_state, "green");
  assert.equal(result.body.assumptions.effective_dates.start, "2021-07-12");
  assert.equal(result.body.assumptions.effective_dates.end, "2026-07-10");
  assert.match(result.body.assumptions.digest, /^[0-9a-f]{64}$/);
  assert.equal(result.body.assumptions.price_basis, "액면분할과 배당을 반영한 수정 OHLC");
  assert.deepEqual(
    Object.keys(result.body.events[0]).sort(),
    ["cycle_id", "date", "fee", "price", "quantity", "reason_code", "role", "side"].sort(),
  );
}

async function testDeterministicResult() {
  const request = {
    symbol: "TQQQ",
    division_count: 20,
    capital: 3_000,
    start_date: "2025-01-02",
    end_date: "2025-06-30",
  };
  const first = await postBacktest(request);
  const second = await postBacktest(request);
  assert.equal(first.response.status, 200);
  assert.equal(second.response.status, 200);
  assert.equal(first.body.assumptions.digest, second.body.assumptions.digest);
  assert.deepEqual(first.body.summary, second.body.summary);
}

async function testHolidayDateMapping() {
  const result = await postBacktest({
    symbol: "TQQQ",
    division_count: 40,
    capital: 3_000,
    start_date: "2025-01-04",
    end_date: "2025-01-12",
  });
  assert.equal(result.response.status, 200);
  assert.deepEqual(result.body.assumptions.effective_dates, { start: "2025-01-06", end: "2025-01-10" });
}

async function testValidationErrors() {
  const base = {
    symbol: "TQQQ",
    division_count: 40,
    capital: 3_000,
    start_date: "2025-01-02",
    end_date: "2025-03-31",
  };
  const cases = [
    [{ ...base, capital: 0 }, "CAPITAL_TOO_LOW", "초기 자본은 $1 이상 입력해 주세요."],
    [{ ...base, capital: 3_001 }, "CAPITAL_TOO_HIGH", "초기 자본은 최대 $3,000까지 입력할 수 있습니다."],
    [{ ...base, start_date: "2025-04-01" }, "REVERSED_DATES", "시작일은 종료일보다 늦을 수 없습니다."],
    [{ ...base, symbol: "SOXL" }, "UNSUPPORTED_SYMBOL", "첫 버전에서는 TQQQ만 백테스트할 수 있습니다."],
  ];
  for (const [request, code, message] of cases) {
    const result = await postBacktest(request);
    assert.equal(result.response.status, 400);
    assert.equal(result.body.error.code, code);
    assert.equal(result.body.error.message, message);
  }
}

async function postBacktest(body) {
  const response = await fetch(`${baseUrl}/api/backtest`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(30_000),
  });
  return { response, body: await response.json() };
}
