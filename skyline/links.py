"""GitHub links to a line in the commit under review."""
from __future__ import annotations

from typing import Optional


def github_base(remote: str) -> Optional[str]:
    """https://github.com/owner/repo from an origin URL. None for other hosts."""
    remote = (remote or "").strip()
    if remote.endswith(".git"):
        remote = remote[:-4]
    if remote.startswith("git@github.com:"):
        return "https://github.com/" + remote[len("git@github.com:"):]
    if remote.startswith("ssh://git@github.com/"):
        return "https://github.com/" + remote[len("ssh://git@github.com/"):]
    if remote.startswith("https://github.com/"):
        return remote
    return None


def finding_href(remote: str, finding, base_sha: str, head_sha: str) -> Optional[str]:
    sha = base_sha if getattr(finding, "side", "head") == "base" else head_sha
    return code_url(
        remote, sha, getattr(finding, "path", ""),
        getattr(finding, "line", None), getattr(finding, "end_line", None),
    )


def code_url(remote: str, sha: str, path: str, line: Optional[int] = None,
             end_line: Optional[int] = None) -> Optional[str]:
    base = github_base(remote)
    if not base or not sha or not path:
        return None
    url = f"{base}/blob/{sha}/{path}"
    if line:
        if end_line and end_line != line:
            url += f"#L{line}-L{end_line}"
        else:
            url += f"#L{line}"
    return url
