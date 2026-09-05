#!/usr/bin/env python
"""Claude Code statusLine: model/dir/git branch/PR on line 1; context-window
usage, cost, duration, and lines-changed on line 2; rate-limit and
prompt-cache health on an optional line 3. Line 2's context-window percentage
flags >=75% as a "consider a checkpoint" warning -- see your rules doc's
token-budget guidance, if it has one; the rate-limit segment below is a
separate account-wide 5h/7d budget that a context-window percentage does not
cover.

Payload schema per the official statusLine doc
(code.claude.com/docs/en/statusline.md) -- rate_limits/prompt_cache/pr require
a sufficiently recent Claude Code version and are absent until populated;
every field below is read defensively and simply omitted when missing, never
guessed. git branch/dirty-state has no payload field at all -- read directly
via `git`, cached to a temp file keyed by session_id (session_id is stable
per session and unique across concurrent sessions in different repos, unlike
a bare PID, since Claude Code re-invokes this script as a fresh process every
refresh) so a git status/branch pair only actually runs once per 5s even
though refreshInterval re-fires this script every 30s and after every
assistant turn.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

RESET = "\033[0m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[1;31m"
CYAN = "\033[36m"

GIT_CACHE_MAX_AGE = 5  # seconds

try:
    data = json.load(sys.stdin)
except Exception:
    print("ctx: n/a")
    sys.exit(0)

cwd = data.get("cwd") or (data.get("workspace") or {}).get("current_dir") or ""
model_name = (data.get("model") or {}).get("display_name") or "?"
dir_label = Path(cwd).name if cwd else "?"
session_id = data.get("session_id") or "nosession"


def git_segment(cwd, session_id):
    """"branch" or "branch*" (uncommitted changes) or None (not a repo /
    git unavailable -- degrade by omitting the segment, never guess).
    Cached to a temp file for GIT_CACHE_MAX_AGE seconds, keyed by session_id
    so concurrent sessions in different repos never read each other's state.
    """
    if not cwd:
        return None
    cache_file = Path(tempfile.gettempdir()) / f"statusline-git-cache-{session_id}"
    try:
        if cache_file.exists() and (time.time() - cache_file.stat().st_mtime) <= GIT_CACHE_MAX_AGE:
            cached = cache_file.read_text(encoding="utf-8").strip()
            return cached or None
    except Exception:
        pass

    label = None
    try:
        branch = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=3,
        )
        if branch.returncode == 0:
            branch_name = branch.stdout.strip()
            status = subprocess.run(
                ["git", "-C", cwd, "status", "--porcelain"],
                capture_output=True, text=True, timeout=3,
            )
            dirty = bool(status.stdout.strip()) if status.returncode == 0 else False
            label = f"{branch_name}*" if dirty else branch_name
    except Exception:
        label = None

    try:
        cache_file.write_text(label or "", encoding="utf-8")
    except Exception:
        pass
    return label


git_label = git_segment(cwd, session_id)

pr = data.get("pr") or {}
pr_label = None
if pr.get("number"):
    state = pr.get("review_state")
    kind = "MR" if pr.get("kind") == "mr" else "PR"
    pr_label = f"{kind}#{pr['number']}" + (f" {state}" if state else "")

prefix_parts = [model_name, dir_label]
if git_label:
    prefix_parts.append(git_label)
if pr_label:
    prefix_parts.append(pr_label)
line1 = f"{DIM}{' · '.join(prefix_parts)}{RESET}"

ctx = data.get("context_window") or {}
pct = ctx.get("used_percentage")

if pct is None:
    line2_parts = ["ctx: n/a"]
else:
    pct = round(pct)
    if pct >= 75:
        line2_parts = [f"{RED}⚠ Context {pct}% — approaching budget, consider a checkpoint{RESET}"]
    elif pct >= 50:
        line2_parts = [f"{YELLOW}Context {pct}%{RESET}"]
    else:
        line2_parts = [f"{GREEN}Context {pct}%{RESET}"]

cost = data.get("cost") or {}
cost_usd = cost.get("total_cost_usd")
if cost_usd is not None:
    line2_parts.append(f"💰${cost_usd:.2f}")

duration_ms = cost.get("total_duration_ms")
if duration_ms:
    mins, secs = divmod(int(duration_ms) // 1000, 60)
    line2_parts.append(f"⏱ {mins}m{secs}s")

added = cost.get("total_lines_added") or 0
removed = cost.get("total_lines_removed") or 0
if added or removed:
    line2_parts.append(f"{GREEN}+{added}{RESET}/{RED}-{removed}{RESET}")

print(f"{line1} · {' · '.join(line2_parts)}")

line3_parts = []

rate_limits = data.get("rate_limits") or {}
five_h = (rate_limits.get("five_hour") or {}).get("used_percentage")
seven_d = (rate_limits.get("seven_day") or {}).get("used_percentage")
if five_h is not None or seven_d is not None:
    bits = []
    if five_h is not None:
        color = RED if five_h >= 90 else YELLOW if five_h >= 75 else CYAN
        bits.append(f"{color}5h:{five_h:.0f}%{RESET}")
    if seven_d is not None:
        color = RED if seven_d >= 90 else YELLOW if seven_d >= 75 else CYAN
        bits.append(f"{color}7d:{seven_d:.0f}%{RESET}")
    line3_parts.append(" ".join(bits))

prompt_cache = data.get("prompt_cache") or {}
hit_ratio = prompt_cache.get("hit_ratio")
if hit_ratio is not None:
    warm = "warm" if prompt_cache.get("warm") else "cold"
    line3_parts.append(f"{DIM}cache {hit_ratio * 100:.0f}% {warm}{RESET}")

if line3_parts:
    print(" · ".join(line3_parts))
