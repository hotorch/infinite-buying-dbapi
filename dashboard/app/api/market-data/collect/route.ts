import { spawn } from "node:child_process";
import path from "node:path";
import { NextResponse } from "next/server";
import { resolvePythonExecutable } from "@/lib/python-runtime";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST() {
  const repositoryRoot = path.resolve(process.cwd(), "..");
  const python = resolvePythonExecutable({ repositoryRoot });

  try {
    const result = await runCollector(python, repositoryRoot);
    const parsed = JSON.parse(result.stdout);
    if (result.exitCode === 2 && parsed.error) return NextResponse.json(parsed, { status: 400 });
    if (result.exitCode !== 0) throw new Error(result.stderr || "Market data collector failed");
    return NextResponse.json(parsed);
  } catch {
    return NextResponse.json(
      { error: { code: "MARKET_DATA_COLLECTION_FAILED", message: "캔들 수집에 실패했습니다. DB증권 인증 정보와 네트워크 상태를 확인해 주세요." } },
      { status: 500 },
    );
  }
}

function runCollector(python: string, cwd: string) {
  return new Promise<{ stdout: string; stderr: string; exitCode: number | null }>((resolve, reject) => {
    const child = spawn(python, ["-m", "infinite_buying_dbapi.market_data_collector_runner"], {
      cwd,
      shell: false,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    const timeout = setTimeout(() => child.kill(), 120_000);
    child.stdout.setEncoding("utf-8");
    child.stderr.setEncoding("utf-8");
    child.stdout.on("data", (chunk: string) => { stdout += chunk; });
    child.stderr.on("data", (chunk: string) => { stderr += chunk; });
    child.on("error", reject);
    child.on("close", (exitCode) => {
      clearTimeout(timeout);
      if (!stdout) return reject(new Error(stderr || "Collector returned no JSON"));
      resolve({ stdout, stderr, exitCode });
    });
  });
}
