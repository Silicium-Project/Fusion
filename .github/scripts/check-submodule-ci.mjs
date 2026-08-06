#!/usr/bin/env node
import fs from "node:fs";

const token = process.env.GITHUB_TOKEN || process.env.GH_TOKEN || process.env.GITHUB_APP_TOKEN;
if (!token) {
  console.error("Missing GITHUB_TOKEN/GH_TOKEN/GITHUB_APP_TOKEN.");
  process.exit(1);
}

const badConclusions = new Set([
  "failure",
  "cancelled",
  "timed_out",
  "action_required",
  "startup_failure",
  "stale",
  "neutralized",
]);

function usage() {
  console.error([
    "Usage:",
    "  node .github/scripts/check-submodule-ci.mjs --all",
    "  node .github/scripts/check-submodule-ci.mjs --repo owner/repo --ref main",
    "  node .github/scripts/check-submodule-ci.mjs --repo owner/repo --sha <commit-sha>",
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

  const combined = await api(`/repos/${repo}/commits/${sha}/status`);
  if (combined.state !== "success") {
    throw new Error(`${display}@${sha.slice(0, 12)} has combined status '${combined.state}', expected 'success'.`);
  }

  const runs = await api(`/repos/${repo}/commits/${sha}/check-runs?per_page=100`);
  const broken = (runs.check_runs || []).filter((run) => {
    const conclusion = (run.conclusion || "").toLowerCase();
    return run.status !== "completed" || badConclusions.has(conclusion);
  });

  if (broken.length > 0) {
    const details = broken
      .map((run) => `${run.name || run.app?.slug || "check"}:${run.status}/${run.conclusion || "unknown"}`)
      .join(", ");
    throw new Error(`${display}@${sha.slice(0, 12)} has failing check runs: ${details}`);
  }

  console.log(`${display}@${sha.slice(0, 12)} is green.`);
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
