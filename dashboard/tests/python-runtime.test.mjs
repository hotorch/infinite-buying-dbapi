import assert from "node:assert/strict";
import test from "node:test";

import { resolvePythonExecutable } from "../lib/python-runtime.ts";

test("BACKTEST_PYTHON wins and is returned unchanged", () => {
  let checkedPath = false;
  const python = resolvePythonExecutable({
    repositoryRoot: "/repo",
    override: "  /custom/python  ",
    platform: "darwin",
    pathExists: () => {
      checkedPath = true;
      return true;
    },
  });

  assert.equal(python, "  /custom/python  ");
  assert.equal(checkedPath, false);
});

test("win32 uses the virtualenv interpreter when it exists", () => {
  const expected = String.raw`C:\repo\.venv\Scripts\python.exe`;
  const python = resolvePythonExecutable({
    repositoryRoot: String.raw`C:\repo`,
    override: "",
    platform: "win32",
    pathExists: (candidate) => candidate === expected,
  });

  assert.equal(python, expected);
});

test("win32 falls back to python when the virtualenv interpreter is missing", () => {
  const python = resolvePythonExecutable({
    repositoryRoot: String.raw`C:\repo`,
    override: "",
    platform: "win32",
    pathExists: () => false,
  });

  assert.equal(python, "python");
});

for (const platform of ["darwin", "linux"]) {
  test(`${platform} uses the virtualenv interpreter when it exists`, () => {
    const expected = "/repo/.venv/bin/python";
    const python = resolvePythonExecutable({
      repositoryRoot: "/repo",
      override: "",
      platform,
      pathExists: (candidate) => candidate === expected,
    });

    assert.equal(python, expected);
  });

  test(`${platform} falls back to python3 when the virtualenv interpreter is missing`, () => {
    const python = resolvePythonExecutable({
      repositoryRoot: "/repo",
      override: "",
      platform,
      pathExists: () => false,
    });

    assert.equal(python, "python3");
  });
}
