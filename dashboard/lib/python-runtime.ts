import { existsSync } from "node:fs";
import path from "node:path";

type PythonPlatform = "win32" | "darwin" | "linux";

type ResolvePythonExecutableOptions = {
  repositoryRoot: string;
  override?: string;
  platform?: PythonPlatform;
  pathExists?: (candidate: string) => boolean;
};

export function resolvePythonExecutable({
  repositoryRoot,
  override = process.env.BACKTEST_PYTHON,
  platform = process.platform as PythonPlatform,
  pathExists,
}: ResolvePythonExecutableOptions): string {
  if (override) return override;

  const isWindows = platform === "win32";
  const pathApi = isWindows ? path.win32 : path.posix;
  const bundledPython = isWindows
    ? pathApi.join(repositoryRoot, ".venv", "Scripts", "python.exe")
    : pathApi.join(repositoryRoot, ".venv", "bin", "python");

  if ((pathExists ?? existsSync)(bundledPython)) return bundledPython;
  return isWindows ? "python" : "python3";
}
