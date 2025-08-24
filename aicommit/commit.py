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

def _sanitize_commit_message(raw: str) -> str:
    """Sanitize model output to a single-line Conventional Commit header.

    - Removes prefaces like "Here's..." and code fences.
    - Returns the first valid header if found; otherwise a safe fallback.
    """
    if not raw:
        return "chore: update"

    text = raw.strip()
    # Strip code fences
    text = re.sub(r"^```[\w-]*\n|\n```$", "", text, flags=re.IGNORECASE)
    text = text.replace("\r", "")
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
                        "Return ONLY the commit message without any preface, commentary, code fences, or quotes. "
                        "Prefer a single-line header like 'type(scope): subject'. "
                        "Use 'fix' for bug patches, 'feat' for new user-facing functionality, and add '!' for breaking changes."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Create a Conventional Commit message summarizing these changes. "
                        "Output must be exactly the final commit header line with no extra text.\n\n"
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
    parser.add_argument("command", nargs="?", help="Optional command: version")
    parser.add_argument("--version", "-V", action="store_true", help="Show version and exit")

    args = parser.parse_args(argv)

    if args.version or (args.command and args.command.lower() == "version"):
        print(get_app_version())
        return

    files = get_diffed_files()
    if files:
        commit_changes(files)
    else:
        print("No changes to commit.")

if __name__ == "__main__":
    main()
