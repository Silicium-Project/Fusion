#!/usr/bin/env node
import fs from "node:fs";

const token = process.env.GITHUB_TOKEN || process.env.GH_TOKEN || process.env.GITHUB_APP_TOKEN;
if (!token) {
  console.error("Missing GITHUB_TOKEN/GH_TOKEN/GITHUB_APP_TOKEN.");
  process.exit(1);
}

function usage() {
  console.error([
    "Usage:",
    "  node .github/scripts/check-submodule-ci.mjs --all",
    "  node .github/scripts/check-submodule-ci.mjs --repo owner/repo --ref main",
    "  node .github/scripts/check-submodule-ci.mjs --repo owner/repo --sha <commit-sha>",
    "  node .github/scripts/check-submodule-ci.mjs --repo owner/repo --latest-green",
    "",
    "Environment:",
    "  GITHUB_TOKEN, GH_TOKEN or GITHUB_APP_TOKEN",
  ].join("\n"));
}

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--all") {
      out.all = true;
    } else if (arg === "--repo") {
      out.repo = argv[++i];
    } else if (arg === "--ref") {
      out.ref = argv[++i];
    } else if (arg === "--sha") {
      out.sha = argv[++i];
    } else if (arg === "--label") {
      out.label = argv[++i];
    } else if (arg === "--latest-green") {
      out.latestGreen = true;
    } else if (arg === "--help" || arg === "-h") {
      out.help = true;
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  return out;
}

function normalizeRepoUrl(url) {
  const https = url.match(/^https:\/\/github\.com\/([^/]+)\/([^/]+?)(?:\.git)?$/i);
  if (https) {
    return `${https[1]}/${https[2]}`;
  }

  const ssh = url.match(/^git@github\.com:([^/]+)\/([^/]+?)(?:\.git)?$/i);
  if (ssh) {
    return `${ssh[1]}/${ssh[2]}`;
  }

  throw new Error(`Unsupported GitHub repository URL: ${url}`);
}

function parseGitmodules(text) {
  const entries = [];
  let current = null;

  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) {
      continue;
    }

    const section = line.match(/^\[submodule\s+"(.+)"\]$/);
    if (section) {
      current = { name: section[1] };
      entries.push(current);
      continue;
    }

    const kv = line.match(/^([A-Za-z0-9._-]+)\s*=\s*(.+)$/);
    if (kv && current) {
      current[kv[1]] = kv[2];
    }
  }

  return entries;
}

async function api(path) {
  const response = await fetch(`https://api.github.com${path}`, {
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "silicium-submodule-ci-gate",
    },
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`GitHub API ${path} failed with ${response.status}: ${body}`);
  }

  return response.json();
}

async function resolveCommitSha(repo, refOrSha) {
  if (/^[0-9a-f]{40}$/i.test(refOrSha)) {
    return refOrSha.toLowerCase();
  }

  const branch = await api(`/repos/${repo}/branches/${encodeURIComponent(refOrSha)}`);
  if (!branch?.commit?.sha) {
    throw new Error(`Cannot resolve ${repo}@${refOrSha}`);
  }
  return branch.commit.sha;
}

async function checkRepo(repo, refOrSha, label) {
  const sha = await resolveCommitSha(repo, refOrSha);
  const display = label || repo;

  const runs = await api(`/repos/${repo}/actions/runs?head_sha=${sha}&per_page=100`);
  const workflowRuns = runs.workflow_runs || [];
  if (workflowRuns.length === 0) {
    throw new Error(`${display}@${sha.slice(0, 12)} has no visible Actions workflow runs.`);
  }

  // Multiple dispatches for one SHA are common while recovering a runner.
  // Evaluate only the newest attempt of each workflow; an older cancelled
  // attempt must not mask a newer successful attempt.
  const latestByWorkflow = new Map();
  for (const run of workflowRuns) {
    const key = String(run.workflow_id || run.name || run.path || "workflow");
    const previous = latestByWorkflow.get(key);
    if (!previous || Number(run.run_number || 0) > Number(previous.run_number || 0)) {
      latestByWorkflow.set(key, run);
    }
  }

  const broken = [...latestByWorkflow.values()].filter((run) => {
    return run.status !== "completed" || run.conclusion !== "success";
  });

  if (broken.length > 0) {
    const details = broken
      .map((run) => `${run.name || run.workflow_id || "workflow"}:${run.status}/${run.conclusion || "unknown"}`)
      .join(", ");
    throw new Error(`${display}@${sha.slice(0, 12)} has non-green workflow runs: ${details}`);
  }

  console.log(`${display}@${sha.slice(0, 12)} is green.`);
  return sha;
}

async function resolveLatestGreen(repo, branch = "main", label = repo) {
  const branchData = await api(`/repos/${repo}/branches/${encodeURIComponent(branch)}`);
  const branchSha = branchData?.commit?.sha;
  if (!branchSha) {
    throw new Error(`Cannot resolve ${repo}@${branch}`);
  }

  const runs = await api(
    `/repos/${repo}/actions/runs?branch=${encodeURIComponent(branch)}&per_page=100`,
  );
  const candidates = [];
  const seen = new Set();
  for (const run of runs.workflow_runs || []) {
    const sha = String(run.head_sha || "").toLowerCase();
    if (/^[0-9a-f]{40}$/.test(sha) && !seen.has(sha)) {
      seen.add(sha);
      candidates.push(sha);
    }
  }
  if (!seen.has(branchSha.toLowerCase())) {
    candidates.unshift(branchSha.toLowerCase());
  }

  for (const candidate of candidates) {
    try {
      await checkRepo(repo, candidate, label);
      console.log(`LATEST_GREEN_SHA=${candidate}`);
      return candidate;
    } catch (error) {
      console.log(`${label}@${candidate.slice(0, 12)} is not the latest green candidate: ${error.message}`);
    }
  }

  throw new Error(`${label} has no green commit candidate on ${branch}.`);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    usage();
    process.exit(0);
  }

  if (args.all) {
    const text = fs.readFileSync(".gitmodules", "utf8");
    const entries = parseGitmodules(text);
    for (const entry of entries) {
      const branch = entry.branch || "main";
      if (branch !== "main") {
        throw new Error(`${entry.name} is configured on '${branch}', expected 'main'.`);
      }
      const repo = normalizeRepoUrl(entry.url);
      await checkRepo(repo, branch, entry.name);
    }
    return;
  }

  if (args.latestGreen) {
    if (!args.repo) {
      usage();
      process.exit(1);
    }
    await resolveLatestGreen(args.repo, args.ref || "main", args.label || args.repo);
    return;
  }

  if (!args.repo || (!args.ref && !args.sha)) {
    usage();
    process.exit(1);
  }

  await checkRepo(args.repo, args.sha || args.ref, args.label || args.repo);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exit(1);
});
