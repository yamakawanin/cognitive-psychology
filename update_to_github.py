#!/usr/bin/env python3
"""
Update current project to your fork:
https://github.com/xSuan-47/cognitive-psychology.git

Usage:
  python3 update_to_github.py
  python3 update_to_github.py -m "feat: update experiment"
  python3 update_to_github.py --remote-name origin --branch main
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_REMOTE_URL = "git@github.com:xSuan-47/cognitive-psychology.git"
DEFAULT_REMOTE_NAME = "origin"
DEFAULT_BRANCH = "main"


def run_git(
    args: list[str],
    cwd: Path,
    check: bool = True,
    non_interactive: bool = False,
) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    if non_interactive:
        # Fail fast instead of hanging on username/password prompts.
        env["GIT_TERMINAL_PROMPT"] = "0"

    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=check,
        text=True,
        capture_output=True,
        env=env,
    )


def ensure_git_available() -> None:
    if shutil.which("git") is None:
        print("[Error] git command not found. Please install Git first.", file=sys.stderr)
        sys.exit(1)


def ensure_repo(cwd: Path) -> None:
    try:
        run_git(["rev-parse", "--is-inside-work-tree"], cwd)
        top = run_git(["rev-parse", "--show-toplevel"], cwd).stdout.strip()
        if Path(top).resolve() != cwd.resolve():
            print(f"[Info] Detected parent repository at: {top}")
            print(f"[Info] Initializing standalone repository in: {cwd}")
            run_git(["init"], cwd)
    except subprocess.CalledProcessError:
        print("[Info] Not a git repository. Running git init...")
        run_git(["init"], cwd)


def has_changes(cwd: Path) -> bool:
    # Includes tracked, untracked, and staged changes.
    result = run_git(["status", "--porcelain"], cwd)
    return bool(result.stdout.strip())


def branch_exists(cwd: Path, branch: str) -> bool:
    result = run_git(["show-ref", "--verify", f"refs/heads/{branch}"], cwd, check=False)
    return result.returncode == 0


def ensure_branch(cwd: Path, branch: str) -> None:
    print(f"[Step] Checking branch state (target: {branch})...")
    has_head = run_git(["rev-parse", "--verify", "HEAD"], cwd, check=False).returncode == 0
    if not has_head:
        if branch_exists(cwd, branch):
            run_git(["switch", branch], cwd)
        else:
            run_git(["switch", "-c", branch], cwd)
        return

    current = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd).stdout.strip()
    if current == "HEAD":
        # Detached HEAD: create/switch branch
        if branch_exists(cwd, branch):
            run_git(["switch", branch], cwd)
        else:
            run_git(["switch", "-c", branch], cwd)
        return

    if current != branch:
        # Keep user's branch if needed; we push HEAD to target branch later.
        print(f"[Info] Current branch is '{current}'. Will push HEAD to '{branch}'.")


def ensure_remote(cwd: Path, remote_name: str, remote_url: str) -> None:
    print(f"[Step] Ensuring remote '{remote_name}' is set...")
    result = run_git(["remote", "get-url", remote_name], cwd, check=False)
    if result.returncode != 0:
        print(f"[Info] Adding remote '{remote_name}' -> {remote_url}")
        run_git(["remote", "add", remote_name, remote_url], cwd)
        return

    current_url = result.stdout.strip()
    if current_url != remote_url:
        print(f"[Info] Updating remote '{remote_name}' from {current_url} to {remote_url}")
        run_git(["remote", "set-url", remote_name, remote_url], cwd)


def stage_and_commit(cwd: Path, message: str) -> bool:
    print("[Step] Staging and committing changes...")
    run_git(["add", "-A"], cwd)
    if not has_changes(cwd):
        print("[Info] No changes to commit.")
        return False

    run_git(["commit", "-m", message], cwd)
    print(f"[OK] Commit created: {message}")
    return True


def push(cwd: Path, remote_name: str, branch: str) -> None:
    # Push current HEAD to target branch; create/update upstream in one go.
    print(f"[Step] Pushing to {remote_name}/{branch}...")
    run_git(
        ["push", "-u", remote_name, f"HEAD:{branch}"],
        cwd,
        non_interactive=True,
    )
    print(f"[OK] Pushed to {remote_name}/{branch}")


def remote_branch_exists(cwd: Path, remote_name: str, branch: str) -> bool:
    result = run_git(["ls-remote", "--heads", remote_name, branch], cwd, check=False)
    return bool(result.stdout.strip())


def is_branch_ahead_of_remote(cwd: Path, remote_name: str, branch: str) -> bool:
    if not remote_branch_exists(cwd, remote_name, branch):
        return True

    result = run_git(["rev-list", "--left-right", "--count", f"HEAD...{remote_name}/{branch}"], cwd, check=False)
    if result.returncode != 0:
        return True

    parts = result.stdout.strip().split()
    if len(parts) != 2:
        return True

    ahead = int(parts[0])
    return ahead > 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Commit and push this project to GitHub.")
    parser.add_argument("-m", "--message", help="Commit message")
    parser.add_argument("--repo-url", default=DEFAULT_REMOTE_URL, help="Target GitHub repo URL")
    parser.add_argument("--remote-name", default=DEFAULT_REMOTE_NAME, help="Git remote name to use")
    parser.add_argument("--branch", default=DEFAULT_BRANCH, help="Target branch name")
    return parser.parse_args()


def main() -> None:
    ensure_git_available()
    args = parse_args()

    # Always target the repository folder where this script lives.
    cwd = Path(__file__).resolve().parent
    commit_message = args.message or f"chore: update project ({dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})"

    try:
        print("[Step] Starting update workflow...")
        ensure_repo(cwd)
        ensure_branch(cwd, args.branch)
        ensure_remote(cwd, args.remote_name, args.repo_url)
        committed = stage_and_commit(cwd, commit_message)
        if committed or is_branch_ahead_of_remote(cwd, args.remote_name, args.branch):
            push(cwd, args.remote_name, args.branch)
        else:
            print("[Info] Skipped push because there is no new commit and local branch is not ahead of remote.")
    except subprocess.CalledProcessError as e:
        print("[Error] Git command failed:", "git", " ".join(e.cmd[1:]), file=sys.stderr)
        err = (e.stderr or "").strip()
        if err:
            print(err, file=sys.stderr)
        auth_markers = ["Authentication failed", "could not read Username", "Permission denied (publickey)"]
        if e.returncode == 128 and any(m in err for m in auth_markers):
            print(
                "[Hint] 这通常是远程认证/权限问题。\n"
                "- HTTPS 仓库请使用 Personal Access Token (PAT)\n"
                "- 或把 --repo-url 改成 SSH 地址并确保 SSH Key 已配置",
                file=sys.stderr,
            )
        sys.exit(e.returncode)


if __name__ == "__main__":
    main()
