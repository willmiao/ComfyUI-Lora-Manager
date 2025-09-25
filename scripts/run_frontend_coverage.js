#!/usr/bin/env node
import { spawnSync } from 'node:child_process';
import { mkdirSync, rmSync, readdirSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '..');
const coverageRoot = path.join(repoRoot, 'coverage');
const v8OutputDir = path.join(coverageRoot, '.v8');
const frontendCoverageDir = path.join(coverageRoot, 'frontend');

rmSync(v8OutputDir, { recursive: true, force: true });
rmSync(frontendCoverageDir, { recursive: true, force: true });
mkdirSync(v8OutputDir, { recursive: true });
mkdirSync(frontendCoverageDir, { recursive: true });

const vitestCli = path.join(repoRoot, 'node_modules', 'vitest', 'vitest.mjs');

if (!existsSync(vitestCli)) {
  console.error('Failed to locate Vitest CLI at', vitestCli);
  console.error('Try reinstalling frontend dependencies with `npm install`.');
  process.exit(1);
}

const env = { ...process.env, NODE_V8_COVERAGE: v8OutputDir };

const spawnOptions = { stdio: 'inherit', env };
const result = spawnSync(process.execPath, [vitestCli, 'run'], spawnOptions);

if (result.error) {
  console.error('Failed to execute Vitest:', result.error.message);
  process.exit(result.status ?? 1);
}

if (result.status !== 0) {
  process.exit(result.status ?? 1);
}

const fileCoverage = collectCoverageFromV8(v8OutputDir, repoRoot);
writeCoverageOutputs(fileCoverage, frontendCoverageDir, repoRoot);
printSummary(fileCoverage);
rmSync(v8OutputDir, { recursive: true, force: true });

function collectCoverageFromV8(v8Dir, rootDir) {
  const coverageMap = new Map();
  const files = readdirSync(v8Dir).filter((file) => file.endsWith('.json'));

  for (const file of files) {
    const reportPath = path.join(v8Dir, file);
    const report = JSON.parse(readFileSync(reportPath, 'utf8'));
    if (!Array.isArray(report.result)) {
      continue;
    }

    for (const script of report.result) {
      const filePath = normalizeFilePath(script.url, rootDir);
      if (!filePath) {
        continue;
      }

      if (!filePath.startsWith('static/')) {
        continue;
      }

      if (!filePath.endsWith('.js')) {
        continue;
      }

      const absolutePath = path.join(rootDir, filePath);
      let lineMap = coverageMap.get(filePath);
      if (!lineMap) {
        lineMap = new Map();
        coverageMap.set(filePath, lineMap);
      }

      const source = readFileSync(absolutePath, 'utf8');
      const lineOffsets = calculateLineOffsets(source);

      for (const fn of script.functions ?? []) {
        for (const range of fn.ranges ?? []) {
          if (range.startOffset === range.endOffset) {
            continue;
          }
          const count = typeof range.count === 'number' ? range.count : 0;
          const startLine = findLineNumber(range.startOffset, lineOffsets);
          const endLine = findLineNumber(Math.max(range.endOffset - 1, range.startOffset), lineOffsets);
          for (let line = startLine; line <= endLine; line += 1) {
            const current = lineMap.get(line);
            if (current === undefined || count > current) {
              lineMap.set(line, count);
            }
          }
        }
      }
    }
  }

  return coverageMap;
}

function normalizeFilePath(url, rootDir) {
  if (!url) {
    return null;
  }
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== 'file:') {
      return null;
    }
    const absolute = fileURLToPath(parsed);
    const relative = path.relative(rootDir, absolute);
    if (relative.startsWith('..') || path.isAbsolute(relative)) {
      return null;
    }
    return relative.replace(/\\/g, '/');
  } catch {
    if (url.startsWith(rootDir)) {
      return url.slice(rootDir.length + 1).replace(/\\/g, '/');
    }
    return null;
  }
}

function calculateLineOffsets(content) {
  const offsets = [0];
  for (let index = 0; index < content.length; index += 1) {
    if (content.charCodeAt(index) === 10) {
      offsets.push(index + 1);
    }
  }
  offsets.push(content.length);
  return offsets;
}

function findLineNumber(offset, lineOffsets) {
  let low = 0;
  let high = lineOffsets.length - 1;
  while (low < high) {
    const mid = Math.floor((low + high + 1) / 2);
    if (lineOffsets[mid] <= offset) {
      low = mid;
    } else {
      high = mid - 1;
    }
  }
  return low + 1;
}

function writeCoverageOutputs(coverageMap, outputDir, rootDir) {
  const summary = {
    total: { lines: { total: 0, covered: 0, pct: 100 } },
    files: {},
  };

  let lcovContent = '';

  for (const [relativePath, lineMap] of [...coverageMap.entries()].sort()) {
    const lines = [...lineMap.entries()].sort((a, b) => a[0] - b[0]);
    const total = lines.length;
    const covered = lines.filter(([, count]) => count > 0).length;
    const pct = total === 0 ? 100 : (covered / total) * 100;

    summary.files[relativePath] = {
      lines: {
        total,
        covered,
        pct,
      },
    };

    summary.total.lines.total += total;
    summary.total.lines.covered += covered;

    const absolute = path.join(rootDir, relativePath);
    lcovContent += 'TN:\n';
    lcovContent += `SF:${absolute.replace(/\\/g, '/')}\n`;
    for (const [line, count] of lines) {
      lcovContent += `DA:${line},${count}\n`;
    }
    lcovContent += `LF:${total}\n`;
    lcovContent += `LH:${covered}\n`;
    lcovContent += 'end_of_record\n';
  }

  summary.total.lines.pct = summary.total.lines.total === 0
    ? 100
    : (summary.total.lines.covered / summary.total.lines.total) * 100;

  writeFileSync(path.join(outputDir, 'coverage-summary.json'), JSON.stringify(summary, null, 2));
  writeFileSync(path.join(outputDir, 'lcov.info'), lcovContent, 'utf8');
}

function printSummary(coverageMap) {
  let totalLines = 0;
  let totalCovered = 0;
  for (const lineMap of coverageMap.values()) {
    const lines = lineMap.size;
    const covered = [...lineMap.values()].filter((count) => count > 0).length;
    totalLines += lines;
    totalCovered += covered;
  }
  const pct = totalLines === 0 ? 100 : (totalCovered / totalLines) * 100;
  console.log(`\nFrontend coverage: ${totalCovered}/${totalLines} lines (${pct.toFixed(2)}%)`);
}
