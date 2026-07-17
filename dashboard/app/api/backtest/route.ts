import { spawn } from "node:child_process";
import path from "node:path";
import { NextResponse } from "next/server";
import { resolvePythonExecutable } from "@/lib/python-runtime";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: { code: "INVALID_JSON", message: "입력 내용을 읽을 수 없습니다." } }, { status: 400 });
  }

  const repositoryRoot = path.resolve(process.cwd(), "..");
  const python = resolvePythonExecutable({ repositoryRoot });

  try {
    const result = await runPython(python, repositoryRoot, payload);
    const parsed = JSON.parse(result.stdout);
    if (result.exitCode === 2 && parsed.error) {
      return NextResponse.json(parsed, { status: 400 });
    }
    if (result.exitCode !== 0) {
      throw new Error("Python runner failed");
    }
    return NextResponse.json(parsed);
  } catch {
    return NextResponse.json(
      { error: { code: "BACKTEST_FAILED", message: "백테스트를 완료하지 못했습니다. Python 환경과 데이터 파일을 확인해 주세요." } },
      { status: 500 },
    );
  }
}

function runPython(python: string, cwd: string, payload: unknown) {
  return new Promise<{ stdout: string; exitCode: number | null }>((resolve, reject) => {
    const child = spawn(python, ["-m", "infinite_buying_dbapi.backtest_runner"], {
      cwd,
      shell: false,
      windowsHide: true,
      stdio: ["pipe", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    const timeout = setTimeout(() => child.kill(), 30_000);
    child.stdout.setEncoding("utf-8");
    child.stderr.setEncoding("utf-8");
    child.stdout.on("data", (chunk: string) => {
      stdout += chunk;
      if (stdout.length > 10_000_000) child.kill();
    });
    child.stderr.on("data", (chunk: string) => {
      stderr += chunk;
    });
    child.on("error", reject);
    child.on("close", (exitCode) => {
      clearTimeout(timeout);
      if (!stdout && stderr) return reject(new Error("Python runner returned no JSON"));
      resolve({ stdout, exitCode });
    });
    child.stdin.end(JSON.stringify(payload), "utf-8");
  });
}
