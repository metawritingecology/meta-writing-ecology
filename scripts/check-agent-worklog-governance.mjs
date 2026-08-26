#!/usr/bin/env node
// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Meta-Writing Ecology
//
// Ported from metawritingecology/lineage-aware-agent-governance origin/main
// (commit 09ce4ef7cf7808e9d858d95cb98724c33ac701c2, scripts/ MIT). Adaptations:
// REPOSITORY points at this repository; the Active Log Notice checks are
// reported as evidence but are not errors, because this repository's
// AGENT_WORKLOG.md predates that notice and historical content is never
// rewritten to add one. Dependency-free: node:child_process and node:fs only.

import { execFileSync, spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";

const REVIEW_THRESHOLD_LINES = 4000;
const HARD_REVIEW_THRESHOLD_LINES = 5000;
const BOT_BRANCH_PREFIXES = ["dependabot/", "renovate/"];
const REPOSITORY = "metawritingecology/meta-writing-ecology";
const INTEGRATION_BRANCH = "main";

const args = process.argv.slice(2);
if (args.length > 1 || (args.length === 1 && args[0] !== "--json")) {
  console.error("Usage: node scripts/check-agent-worklog-governance.mjs [--json]");
  process.exit(2);
}

const jsonMode = args[0] === "--json";

function runGit(gitArgs) {
  try {
    return {
      ok: true,
      stdout: execFileSync("git", ["-c", "http.sslBackend=openssl", "-c", "core.longpaths=true", ...gitArgs], {
        encoding: "utf8",
        stdio: ["ignore", "pipe", "pipe"],
      }).trim(),
      stderr: "",
    };
  } catch (error) {
    return {
      ok: false,
      stdout: error.stdout?.toString().trim() ?? "",
      stderr: error.stderr?.toString().trim() || error.message,
    };
  }
}

function requireGit(gitArgs, message) {
  const result = runGit(gitArgs);
  if (!result.ok) throw new Error(`${message}: ${result.stderr}`);
  return result.stdout;
}

// Raw bytes of a path at a git revision (no encoding, no trim) for exact
// byte-prefix comparison. Returns { ok: false } if the revision/path is not
// available locally (e.g. the tracking ref is absent or predates the file).
function gitShowBytes(spec) {
  try {
    return {
      ok: true,
      buf: execFileSync("git", ["-c", "core.longpaths=true", "show", spec], {
        stdio: ["ignore", "pipe", "pipe"],
      }),
    };
  } catch {
    return { ok: false, buf: null };
  }
}

function gitObjectExists(spec) {
  return (
    spawnSync("git", ["-c", "core.longpaths=true", "cat-file", "-e", spec], {
      stdio: ["ignore", "pipe", "pipe"],
    }).status === 0
  );
}

// Bytes of AGENT_WORKLOG.md at a specific commit, fetching that commit
// read-only (objects only, no ref or working-tree change) if it is not present
// locally. Distinguishes:
//   found         - blob obtained (compare it as the append-only base)
//   path_absent   - commit present but the file did not exist there (bootstrap)
//   indeterminate - commit could not be resolved even after a read-only fetch
function worklogBaseAt(sha) {
  let blob = gitShowBytes(`${sha}:AGENT_WORKLOG.md`);
  if (blob.ok) return { state: "found", buf: blob.buf };
  if (gitObjectExists(`${sha}^{commit}`)) return { state: "path_absent" };
  const fetched =
    spawnSync("git", ["-c", "core.longpaths=true", "fetch", "--quiet", "--no-tags", "origin", sha], {
      stdio: ["ignore", "pipe", "pipe"],
    }).status === 0;
  if (fetched) {
    blob = gitShowBytes(`${sha}:AGENT_WORKLOG.md`);
    if (blob.ok) return { state: "found", buf: blob.buf };
    if (gitObjectExists(`${sha}^{commit}`)) return { state: "path_absent" };
  }
  return { state: "indeterminate" };
}

function splitLines(text) {
  if (text.length === 0) return [];
  return text.split(/\r\n|\n|\r/);
}

function rolloverLineStatus(lineCount) {
  if (lineCount >= HARD_REVIEW_THRESHOLD_LINES) return "hard_review_threshold_reached";
  if (lineCount >= REVIEW_THRESHOLD_LINES) return "review_threshold_reached";
  return "below_review_threshold";
}

function hasCommand(command) {
  return spawnSync(command, ["--version"], { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).status === 0;
}

function fetchPrMetadata() {
  if (!hasCommand("gh")) {
    return { available: false, reason: "gh_absent", detail: null, byHead: new Map() };
  }

  const result = spawnSync(
    "gh",
    [
      "pr",
      "list",
      "--repo",
      REPOSITORY,
      "--state",
      "all",
      "--limit",
      "200",
      "--json",
      "number,state,isDraft,headRefName,headRefOid,baseRefName,mergedAt,mergeCommit",
    ],
    { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
  );

  if (result.status !== 0) {
    return {
      available: false,
      reason: "gh_pr_access_failed",
      detail: result.stderr.trim() || result.stdout.trim(),
      byHead: new Map(),
    };
  }

  try {
    const byHead = new Map();
    for (const pr of JSON.parse(result.stdout)) {
      if (!pr.headRefName) continue;
      const entry = {
        number: pr.number,
        state: pr.state,
        draft: pr.isDraft,
        base: pr.baseRefName,
        headRefName: pr.headRefName,
        headSha: pr.headRefOid,
        mergedAt: pr.mergedAt || null,
        mergeCommitSha: pr.mergeCommit?.oid || null,
      };
      // Keep ALL PRs per head branch. A branch name can carry more than one PR
      // over time; overwriting would let a stale merged PR mask the current tip.
      const list = byHead.get(pr.headRefName) ?? [];
      list.push(entry);
      byHead.set(pr.headRefName, list);
    }
    return { available: true, reason: null, detail: null, byHead };
  } catch (error) {
    return { available: false, reason: "gh_json_parse_failed", detail: error.message, byHead: new Map() };
  }
}

function parseRemoteBranches(output) {
  return splitLines(output)
    .map((line) => line.match(/^([0-9a-f]{40})\s+refs\/heads\/(.+)$/i))
    .filter(Boolean)
    .map((match) => ({ tipSha: match[1], name: match[2] }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

function normalizeBranchName(branchName) {
  return branchName.replace(/^refs\/heads\//, "").replace(/^origin\//, "");
}

function isCurrentBranch(branchName, currentBranch) {
  return normalizeBranchName(branchName) === normalizeBranchName(currentBranch);
}

function containedInMainByAncestry(tipSha, originMainSha) {
  if (!originMainSha) return "unknown";
  // Read the exit CODE directly: `git merge-base --is-ancestor` exits 0 for
  // ancestor and 1 for "not an ancestor" (a normal result, not an error).
  // Routing exit 1 through a throwing execFileSync would collapse it to
  // "unknown"; spawnSync exposes the status so a real negative is reported.
  const res = spawnSync("git", ["-c", "core.longpaths=true", "merge-base", "--is-ancestor", tipSha, originMainSha], {
    stdio: ["ignore", "pipe", "pipe"],
  });
  if (res.status === 0) return true;
  if (res.status === 1) return false;
  return "unknown";
}

function buildBranchEvidence(branch, currentBranch, integrationBranch, originMainSha, prMetadata) {
  const contained = containedInMainByAncestry(branch.tipSha, originMainSha);
  const evidence = {
    branchName: branch.name,
    tipSha: branch.tipSha,
    contained_in_main_by_ancestry: contained,
    current_branch_excluded: branch.name === currentBranch,
  };

  const prs = prMetadata.byHead.get(branch.name) ?? [];
  if (prs.length > 0) {
    // A merged PR only clears THIS branch tip when it merged into the intended
    // integration branch AND its recorded head is exactly the current tip.
    // Anything weaker -- merged into some other base, or head advanced past the
    // merged commit -- must not read as "cleared". Weak evidence stays
    // ambiguous / needs review, matching the append-only governance stance.
    const prForTip = prs.find((p) => p.headSha === branch.tipSha) ?? null;
    const mergedIntoIntegration = prs.filter(
      (p) => (p.state === "MERGED" || !!p.mergedAt) && p.base === integrationBranch,
    );
    const mergedCoversTip =
      prForTip !== null &&
      (prForTip.state === "MERGED" || !!prForTip.mergedAt) &&
      prForTip.base === integrationBranch;
    return {
      ...evidence,
      prs,
      integration_branch: integrationBranch,
      pr_head_matches_tip: prForTip !== null,
      merged_into_integration_count: mergedIntoIntegration.length,
      merged_pr_covers_current_tip: mergedCoversTip,
      requires_author_or_pr_review: contained !== true && !mergedCoversTip,
    };
  }

  return {
    ...evidence,
    pr_state_unavailable: !prMetadata.available,
    pr_metadata_found: false,
    requires_author_or_pr_review: contained !== true,
  };
}

function collectEvidence() {
  const repositoryRoot = requireGit(["rev-parse", "--show-toplevel"], "repository root cannot be determined");
  const currentBranch = requireGit(["rev-parse", "--abbrev-ref", "HEAD"], "current branch cannot be determined");
  const currentHead = requireGit(["rev-parse", "HEAD"], "current HEAD cannot be determined");

  // Branch inventory and integration target must share ONE observation window.
  // Derive the integration-branch tip from the same ls-remote snapshot used for
  // the branch list, instead of a possibly-stale origin/<branch> tracking ref.
  const remoteResult = runGit(["ls-remote", "--heads", "origin"]);
  const remoteBranches = remoteResult.ok ? parseRemoteBranches(remoteResult.stdout) : [];
  const integrationRemote = remoteBranches.find((b) => b.name === INTEGRATION_BRANCH) ?? null;
  const originMainSha = integrationRemote ? integrationRemote.tipSha : null;
  // Ancestry needs the integration tip object locally; if it is absent,
  // containedInMainByAncestry returns "unknown" rather than a stale answer.

  const worklogPath = `${repositoryRoot}/AGENT_WORKLOG.md`;
  if (!existsSync(worklogPath)) throw new Error("AGENT_WORKLOG.md cannot be read");

  const worklogBuffer = readFileSync(worklogPath);
  const worklogText = worklogBuffer.toString("utf8");
  const activeNoticeCount = (worklogText.match(/^## Active Log Notice$/gm) ?? []).length;
  const activeNoticePointsToAgents = /## Active Log Notice[\s\S]*?`AGENTS\.md`/.test(worklogText);

  // Append-only invariant (HARD), fail-closed. Bind to the OBSERVED integration
  // tip from the same ls-remote window as the branch inventory -- not the local
  // origin/<branch> tracking ref, which can be stale and would let a rewrite of
  // history newer than the stale ref pass unseen. The worklog at that commit
  // must be an exact byte PREFIX of the working-tree file. If the commit cannot
  // be resolved even after a read-only fetch, the invariant is INDETERMINATE and
  // fails closed rather than passing green.
  let worklogAppendOnly;
  if (originMainSha === null) {
    worklogAppendOnly = {
      checked: false,
      preserved: null,
      indeterminate: false,
      reason: "no remote integration branch observed (bootstrap / pre-first-push)",
    };
  } else {
    const base = worklogBaseAt(originMainSha);
    if (base.state === "found") {
      const preserved =
        worklogBuffer.byteLength >= base.buf.byteLength &&
        worklogBuffer.subarray(0, base.buf.byteLength).equals(base.buf);
      worklogAppendOnly = {
        checked: true,
        preserved,
        indeterminate: false,
        baseSha: originMainSha,
        baseBytes: base.buf.byteLength,
        currentBytes: worklogBuffer.byteLength,
        reason: null,
      };
    } else if (base.state === "path_absent") {
      worklogAppendOnly = {
        checked: false,
        preserved: null,
        indeterminate: false,
        baseSha: originMainSha,
        reason: "AGENT_WORKLOG.md not present at the observed integration commit (bootstrap)",
      };
    } else {
      worklogAppendOnly = {
        checked: false,
        preserved: null,
        indeterminate: true,
        baseSha: originMainSha,
        reason: "observed integration commit unavailable locally and could not be fetched -- append-only unverifiable",
      };
    }
  }

  const agentsPath = `${repositoryRoot}/AGENTS.md`;
  const agentsText = existsSync(agentsPath) ? readFileSync(agentsPath, "utf8") : "";
  const agentsCanonicalPointerPresent = agentsText.includes("node scripts/check-agent-worklog-governance.mjs");

  const prMetadata = fetchPrMetadata();
  const dependencyBranches = [];
  const nonBotRemoteBranches = [];
  const excludedCurrentBranches = [];

  for (const branch of remoteBranches) {
    if (isCurrentBranch(branch.name, currentBranch)) {
      excludedCurrentBranches.push({
        branchName: branch.name,
        tipSha: branch.tipSha,
        reason: "current_branch",
      });
      continue;
    }

    const evidence = buildBranchEvidence(branch, currentBranch, INTEGRATION_BRANCH, originMainSha, prMetadata);
    if (BOT_BRANCH_PREFIXES.some((prefix) => branch.name.startsWith(prefix))) {
      dependencyBranches.push(evidence);
    } else {
      nonBotRemoteBranches.push(evidence);
    }
  }

  return {
    repositoryRoot,
    currentBranch,
    currentHead,
    integrationBranch: INTEGRATION_BRANCH,
    originMainSha,
    originMainObservation: originMainSha ? "ls-remote (same window as branch inventory)" : "unavailable",
    agentWorklog: {
      byteSize: worklogBuffer.byteLength,
      lineCount: splitLines(worklogText).length,
      datedEntryCount: (worklogText.match(/^### \d{4}-\d{2}-\d{2} /gm) ?? []).length,
      rolloverLineStatus: rolloverLineStatus(splitLines(worklogText).length),
      activeLogNoticeCount: activeNoticeCount,
      activeLogNoticeOccursExactlyOnce: activeNoticeCount === 1,
      activeLogNoticePointsToAgents: activeNoticePointsToAgents,
      appendOnly: worklogAppendOnly,
    },
    agentsCanonicalPointerPresent,
    remoteBranchEvidenceAvailable: remoteResult.ok,
    currentBranchExclusion: currentBranch,
    excludedCurrentBranches,
    botDependencyPrefixes: BOT_BRANCH_PREFIXES,
    prMetadata: {
      available: prMetadata.available,
      reason: prMetadata.reason,
      detail: prMetadata.detail,
    },
    dependencyBranches,
    nonBotRemoteBranches,
  };
}

function printHuman(evidence) {
  console.log("Agent worklog governance evidence");
  console.log("");
  console.log(`Repository root: ${evidence.repositoryRoot}`);
  console.log(`Current branch: ${evidence.currentBranch}`);
  console.log(`Current HEAD: ${evidence.currentHead}`);
  console.log(`Available origin/main SHA: ${evidence.originMainSha ?? "unknown"}`);
  console.log("");
  console.log("AGENT_WORKLOG.md:");
  console.log(`  Exact byte size: ${evidence.agentWorklog.byteSize}`);
  console.log(`  Exact line count: ${evidence.agentWorklog.lineCount}`);
  console.log(`  Dated-entry count: ${evidence.agentWorklog.datedEntryCount}`);
  console.log(`  Rollover line status: ${evidence.agentWorklog.rolloverLineStatus}`);
  console.log(`  Active Log Notice count: ${evidence.agentWorklog.activeLogNoticeCount}`);
  console.log(`  Active Log Notice points to AGENTS.md: ${evidence.agentWorklog.activeLogNoticePointsToAgents}`);
  const ao = evidence.agentWorklog.appendOnly;
  console.log(
    `  Append-only (byte prefix at observed integration commit${ao.baseSha ? " " + ao.baseSha.slice(0, 8) : ""}): ${
      ao.checked
        ? ao.preserved
        : ao.indeterminate
          ? `INDETERMINATE -- fail-closed (${ao.reason})`
          : `not-applicable (${ao.reason})`
    }`,
  );
  console.log(`  AGENTS.md script invocation pointer present: ${evidence.agentsCanonicalPointerPresent}`);
  console.log("");
  console.log(`Current branch exclusion: ${evidence.currentBranchExclusion}`);
  console.log("Excluded current branch refs:");
  for (const branch of evidence.excludedCurrentBranches) {
    console.log(`  - ${branch.branchName} ${branch.tipSha} reason=${branch.reason}`);
  }
  console.log(`Remote branch evidence available: ${evidence.remoteBranchEvidenceAvailable}`);
  const prState = evidence.prMetadata.available
    ? "available"
    : `pr_state_unavailable (${evidence.prMetadata.reason}${evidence.prMetadata.detail ? `: ${evidence.prMetadata.detail}` : ""})`;
  console.log(`PR metadata: ${prState}`);
  console.log("");
  console.log("Bot/dependency branches:");
  for (const branch of evidence.dependencyBranches) {
    console.log(
      `  - ${branch.branchName} ${branch.tipSha} contained_in_main_by_ancestry=${branch.contained_in_main_by_ancestry}`,
    );
  }
  console.log("");
  console.log("Non-bot remote branches:");
  for (const branch of evidence.nonBotRemoteBranches) {
    const prText =
      branch.prs && branch.prs.length > 0
        ? ` prs=${branch.prs.length} head_matches_tip=${branch.pr_head_matches_tip} merged_covers_tip=${branch.merged_pr_covers_current_tip}`
        : branch.pr_state_unavailable
          ? " pr_state_unavailable"
          : " pr_metadata_found=false";
    console.log(
      `  - ${branch.branchName} ${branch.tipSha} contained_in_main_by_ancestry=${branch.contained_in_main_by_ancestry}${prText} requires_author_or_pr_review=${branch.requires_author_or_pr_review}`,
    );
  }
}

try {
  const evidence = collectEvidence();
  const errors = [];
  // Active Log Notice: reported as evidence only (see header comment).
  if (!evidence.agentsCanonicalPointerPresent) {
    errors.push("AGENTS.md script invocation pointer is absent");
  }
  if (evidence.agentWorklog.appendOnly.preserved === false) {
    errors.push(
      "AGENT_WORKLOG.md is not append-only: the observed integration-commit worklog is not a byte prefix of the current file",
    );
  }
  if (evidence.agentWorklog.appendOnly.indeterminate) {
    errors.push(
      "AGENT_WORKLOG.md append-only invariant is unverifiable (observed integration commit unavailable) -- failing closed",
    );
  }

  if (jsonMode) {
    console.log(JSON.stringify(evidence, null, 2));
  } else {
    printHuman(evidence);
  }

  if (errors.length > 0) {
    for (const error of errors) console.error(`ERROR: ${error}`);
    process.exit(1);
  }
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  if (jsonMode) {
    console.log(JSON.stringify({ error: message }, null, 2));
  } else {
    console.error(message);
  }
  process.exit(1);
}
