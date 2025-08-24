import subprocess
import os
import re
import argparse
from typing import Optional, List
try:
    from importlib.metadata import version as pkg_version, PackageNotFoundError
except Exception:  # pragma: no cover
    pkg_version = None
    PackageNotFoundError = Exception

_openai_client = None

def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        # Lazy import to allow --version to work without OpenAI present
        from openai import OpenAI
        _openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    return _openai_client

def get_app_version() -> str:
    """Return installed aicommit version or a local fallback."""
    # 1) Prefer installed package version
    if pkg_version:
        try:
            return pkg_version("aicommit")
        except PackageNotFoundError:
            pass
        except Exception:
            pass
    # 2) Fallback to package constant if available
    try:
        from . import __version__  # type: ignore
        if __version__:
            return str(__version__)
    except Exception:
        pass
    # 3) Last resort
    return "0.0.0-dev"

def _git_status_porcelain():
    """Return parsed entries from `git status --porcelain`.

    Each entry: (X, Y, path, orig_path)
    - X: staged status, Y: worktree status
    - For renames/copies, orig_path is set; otherwise None.
    """
    result = subprocess.run(
        ['git', 'status', '--porcelain'], capture_output=True, text=True
    )
    if result.returncode != 0:
        print("Error getting status:", result.stderr)
        return []
    entries = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        # Format: XY␠PATH or XY␠OLD -> NEW for renames
        prefix = line[:2]
        rest = line[3:] if len(line) > 3 else ''
        X, Y = prefix[0], prefix[1]
        orig_path = None
        path = rest
        if ' -> ' in rest:
            orig_path, path = rest.split(' -> ', 1)
        entries.append((X, Y, path.strip(), orig_path.strip() if orig_path else None))
    return entries


def get_diffed_files():
    """Get the list of files with changes (staged, unstaged, or untracked)."""
    entries = _git_status_porcelain()
    files = []
    for X, Y, path, _ in entries:
        if X != ' ' or Y != ' ' or (X == '?' and Y == '?'):
            files.append(path)
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for f in files:
        if f not in seen:
            seen.add(f)
            unique.append(f)
    return unique

def get_file_diff(file_path, status_map=None):
    """Get the diff of a specific file, preferring staged diff when present."""
    staged = False
    if status_map and file_path in status_map:
        X, Y = status_map[file_path]
        staged = X != ' '
    # Prefer staged diff if available
    if staged:
        result = subprocess.run(['git', 'diff', '--cached', '--', file_path], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout:
            return result.stdout
    # Fallback to working tree diff
    result = subprocess.run(['git', 'diff', '--', file_path], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error getting diff for {file_path}:", result.stderr)
        return ""
    return result.stdout

def _strip_code_fences(text: str) -> str:
    """Remove Markdown code fences while preserving inner content.

    Handles variations like ````, ```text, and uneven fencing gracefully.
    """
    if not text:
        return text
    # Normalize and strip typical fence lines like ``` or ```markdown
    t = text.replace("\r", "")
    t = re.sub(r"^\s*```[\w-]*\s*$", "", t, flags=re.MULTILINE)
    # Handle same-line fenced content and any remaining backticks
    t = t.replace("```", "")
    return t.strip()


def _sanitize_commit_message(raw: str) -> str:
    """Sanitize model output to a single-line Conventional Commit header.

    - Removes prefaces like "Here's..." and code fences.
    - Returns the first valid header if found; otherwise a safe fallback.
    """
    if not raw:
        return "chore: update"

    text = _strip_code_fences(raw.strip())
    # Remove common leading phrases
    text = re.sub(r"^\s*here('s| is)\b.*?:\s*\n?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*(commit message|conventional commit)\s*:?-?\s*\n?", "", text, flags=re.IGNORECASE)
    text = text.strip().strip('"').strip("'")

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        return "chore: update"

    header_regex = re.compile(
        r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([\w\-\/\.\s]+\))?!?:\s+.+$",
        re.IGNORECASE,
    )
    for line in lines:
        cleaned = re.sub(r"^[-*]\s+", "", line)
        if header_regex.match(cleaned):
            return cleaned

    # Fallback: use first non-empty line, trimmed
    fallback = re.sub(r"^[-*]\s+", "", lines[0])
    fallback = fallback.split("\n")[0].strip()
    if not header_regex.match(fallback):
        if ":" in fallback.split(" ")[0]:
            return fallback
        return f"chore: {fallback}"
    return fallback


def generate_commit_message(diff):
    """Generate a commit message using OpenAI API and sanitize it."""
    try:
        response = _get_openai_client().chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You write Conventional Commit messages. "
                        "Output must be plain text only: no Markdown, no backticks, no code fences, no quotes, no extra commentary. "
                        "Return exactly one line in the format 'type(scope): subject' (scope optional). "
                        "Use 'fix' for bug patches, 'feat' for new user-facing functionality, and add '!' for breaking changes."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Create a Conventional Commit message summarizing these changes. "
                        "Return only the final commit header line. Do not use Markdown or code fences.\n\n"
                        f"{diff}"
                    ),
                },
            ],
            max_tokens=120,
        )
        raw = response.choices[0].message.content or ""
        return _sanitize_commit_message(raw)
    except Exception as e:
        print(f"Error generating commit message: {e}")
        return "chore: update"


# -----------------------------
# Release utilities
# -----------------------------

_CC_RE = re.compile(r"^(?P<type>feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([^)]+\))?(?P<breaking>!)?:\s+(?P<subject>.+)$", re.IGNORECASE)


def _read_current_version_from_file() -> str:
    try:
        from . import __version__  # type: ignore
        if __version__:
            return str(__version__)
    except Exception:
        pass
    # Fallback parse from file
    try:
        with open(os.path.join(os.path.dirname(__file__), "__init__.py"), "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("__version__"):
                    return line.split("=")[-1].strip().strip('"').strip("'")
    except Exception:
        pass
    return "0.0.0"


def _semver_bump(version: str, bump: str) -> str:
    major, minor, patch = (int(x) for x in version.split("."))
    if bump == "major":
        return f"{major+1}.0.0"
    if bump == "minor":
        return f"{major}.{minor+1}.0"
    # patch/default
    return f"{major}.{minor}.{patch+1}"


def _git_last_tag() -> Optional[str]:
    r = subprocess.run(["git", "describe", "--tags", "--abbrev=0"], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return r.stdout.strip() or None


def _git_commits_since(tag: Optional[str]) -> List[dict]:
    range_spec = f"{tag}..HEAD" if tag else "HEAD"
    r = subprocess.run(["git", "log", "--format=%H%x1f%B%x1e", range_spec], capture_output=True, text=True)
    if r.returncode != 0:
        return []
    commits = []
    for entry in r.stdout.split("\x1e"):
        if not entry.strip():
            continue
        try:
            sha, body = entry.split("\x1f", 1)
        except ValueError:
            continue
        commits.append({"sha": sha.strip(), "body": body.strip()})
    return commits


def _analyze_commits(commits: List[dict]) -> dict:
    res = {
        "breaking": [],
        "feat": [],
        "fix": [],
        "other": [],
    }
    for c in commits:
        body = c["body"]
        lines = [l for l in body.splitlines() if l.strip()]
        subject = lines[0] if lines else ""
        m = _CC_RE.match(subject)
        is_breaking = False
        if m:
            ctype = m.group("type").lower()
            if m.group("breaking"):
                is_breaking = True
            if any("BREAKING CHANGE" in l.upper() for l in lines[1:]):
                is_breaking = True
            item = {"sha": c["sha"], "subject": subject}
            if is_breaking:
                res["breaking"].append(item)
            if ctype == "feat":
                res["feat"].append(item)
            elif ctype == "fix":
                res["fix"].append(item)
            else:
                res["other"].append(item)
        else:
            res["other"].append({"sha": c["sha"], "subject": subject or body.splitlines()[0] if body else c["sha"]})
    return res


def _decide_bump(analysis: dict) -> str:
    if analysis["breaking"]:
        return "major"
    if analysis["feat"]:
        return "minor"
    return "patch"


def _update_version_file(new_version: str) -> None:
    init_path = os.path.join(os.path.dirname(__file__), "__init__.py")
    lines = []
    with open(init_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip().startswith("__version__"):
                lines.append(f"__version__ = \"{new_version}\"\n")
            else:
                lines.append(line)
    with open(init_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


def _prepend_changelog(new_version: str, analysis: dict) -> None:
    from datetime import date
    today = date.today().isoformat()
    header = [
        f"## v{new_version} - {today}\n",
        "\n",
    ]
    sections = []
    if analysis["breaking"]:
        sections.append(("Breaking Changes", analysis["breaking"]))
    if analysis["feat"]:
        sections.append(("Features", analysis["feat"]))
    if analysis["fix"]:
        sections.append(("Bug Fixes", analysis["fix"]))
    if analysis["other"]:
        sections.append(("Other Changes", analysis["other"]))

    for title, items in sections:
        header.append(f"### {title}\n")
        for it in items:
            short = it["sha"][:7]
            header.append(f"- {it['subject']} ({short})\n")
        header.append("\n")

    changelog_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "CHANGELOG.md")
    existing = ""
    if os.path.exists(changelog_path):
        with open(changelog_path, "r", encoding="utf-8") as f:
            existing = f.read()
    with open(changelog_path, "w", encoding="utf-8") as f:
        f.writelines(header)
        if existing:
            f.write(existing if existing.startswith("# ") else existing)


def _git_commit_and_tag(new_version: str, dry_run: bool = False) -> None:
    if dry_run:
        return
    subprocess.run(["git", "add", "CHANGELOG.md", "aicommit/__init__.py"], check=True)
    subprocess.run(["git", "commit", "-m", f"chore(release): v{new_version}"], check=True)
    subprocess.run(["git", "tag", f"v{new_version}"], check=True)


def run_release(dry_run: bool = False, bump_override: Optional[str] = None) -> str:
    # Ensure clean working tree (ignore untracked)
    r = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    dirty = [ln for ln in r.stdout.splitlines() if ln and not ln.startswith("?? ")]
    if dirty:
        raise SystemExit("Working tree must be clean (no staged/unstaged changes) before release.")

    current = _read_current_version_from_file()
    last_tag = _git_last_tag()
    commits = _git_commits_since(last_tag)
    analysis = _analyze_commits(commits)
    bump = bump_override or _decide_bump(analysis)
    new_version = _semver_bump(current, bump)

    _update_version_file(new_version)
    _prepend_changelog(new_version, analysis)
    _git_commit_and_tag(new_version, dry_run=dry_run)
    return new_version

def commit_changes(files):
    """Commit changes with generated commit messages per path.

    - Includes staged files as-is.
    - Stages unstaged modifications, additions, and deletions per file.
    - Commits each pathspec individually so staged unrelated files remain staged.
    """
    # Build a quick status map: path -> (X, Y)
    status_map = {}
    details_map = {}
    for X, Y, path, orig in _git_status_porcelain():
        status_map[path] = (X, Y)
        details_map[path] = (X, Y, orig)

    processed = set()
    for file in files:
        if file in processed:
            continue
        X, Y, orig = details_map.get(file, (' ', ' ', None))

        # Stage as needed if not already staged
        if X == ' ':
            try:
                if orig:
                    # Likely a rename detected in worktree; stage both sides
                    old, new = orig, file
                    subprocess.run(['git', 'add', '-A', '--', old, new], check=True)
                    # mark both as processed as a pair
                    processed.add(old)
                    processed.add(new)
                    # Refresh local variables
                    X, Y = 'R', ' '
                elif Y == 'D':
                    # Deleted in worktree; stage deletion
                    subprocess.run(['git', 'rm', '--quiet', '--', file], check=True)
                else:
                    # New/modified/untracked
                    subprocess.run(['git', 'add', '-f', '--', file], check=True)
                # Refresh status after staging
                X, Y = status_map[file] = (X if X != ' ' else 'M', ' ')
            except subprocess.CalledProcessError as e:
                print(f"Error staging {file}: {e}")
                continue

        # Prepare diff preferring staged (handle rename pair specially)
        if orig:
            old, new = orig, file
            # Get staged diff for both paths
            result = subprocess.run(['git', 'diff', '--cached', '--', old, new], capture_output=True, text=True)
            diff = result.stdout if result.returncode == 0 else ''
            if not diff.strip():
                result = subprocess.run(['git', 'diff', '--', old, new], capture_output=True, text=True)
                diff = result.stdout if result.returncode == 0 else ''
        else:
            diff = get_file_diff(file, status_map)
        if not diff.strip():
            # No diff to describe; skip committing
            continue

        commit_message = generate_commit_message(diff)
        try:
            if orig:
                # Commit both old and new paths to record rename atomically
                subprocess.run(['git', 'commit', '-m', commit_message, '--', orig, file], check=True)
                processed.add(file)
                print(f"Committed rename {orig} -> {file} with message: {commit_message}")
            else:
                # Commit only this pathspec (respects deletions too)
                subprocess.run(['git', 'commit', '-m', commit_message, '--', file], check=True)
                print(f"Committed {file} with message: {commit_message}")
        except subprocess.CalledProcessError as e:
            print(f"Error committing {file}: {e}")

def main(argv: Optional[List[str]] = None):
    parser = argparse.ArgumentParser(prog="aicommit", add_help=True)
    parser.add_argument("command", nargs="?", help="Optional command: version|release")
    parser.add_argument("--version", "-V", action="store_true", help="Show version and exit")
    # release options
    parser.add_argument("--dry-run", action="store_true", help="Run release without committing/tagging")
    parser.add_argument("--release-type", choices=["major", "minor", "patch"], help="Force bump type")

    args = parser.parse_args(argv)

    if args.version or (args.command and args.command.lower() == "version"):
        print(get_app_version())
        return

    if args.command and args.command.lower() == "release":
        newv = run_release(dry_run=args.dry_run, bump_override=args.release_type)
        print(f"Prepared release v{newv}. To push: git push && git push --tags")
        return

    files = get_diffed_files()
    if files:
        commit_changes(files)
    else:
        print("No changes to commit.")

if __name__ == "__main__":
    main()
