"""Pre-registration lock + run-once guard (spec §10.1)."""
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess


def lock_hash(prereg_path: pathlib.Path) -> str:
    return hashlib.sha256(prereg_path.read_bytes()).hexdigest()


def current_commit(repo_root: pathlib.Path) -> str | None:
    r = subprocess.run(["git", "-C", str(repo_root), "rev-parse", "HEAD"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def tree_is_clean(repo_root: pathlib.Path) -> bool:
    r = subprocess.run(["git", "-C", str(repo_root), "status", "--porcelain"],
                       capture_output=True, text=True)
    return r.stdout.strip() == ""


def read_lock(lock_path: pathlib.Path) -> dict | None:
    if not lock_path.exists():
        return None
    return json.loads(lock_path.read_text())


def write_lock(lock_path: pathlib.Path, prereg_path: pathlib.Path, repo_root: pathlib.Path) -> dict:
    info = {
        "commit": current_commit(repo_root),
        "prereg_sha256": lock_hash(prereg_path),
    }
    lock_path.write_text(json.dumps(info, indent=2))
    return info


def verify_lock(lock_path: pathlib.Path, prereg_path: pathlib.Path,
                repo_root: pathlib.Path) -> tuple[bool, str]:
    """Returns (ok, reason). The gate run requires a matching lock + clean tree."""
    lock = read_lock(lock_path)
    if lock is None:
        return False, "PREREG.lock missing"
    if lock.get("prereg_sha256") != lock_hash(prereg_path):
        return False, "prereg.yaml hash does not match PREREG.lock"
    if lock.get("commit") is not None and lock["commit"] != current_commit(repo_root):
        return False, "working tree commit differs from locked commit"
    if not tree_is_clean(repo_root):
        return False, "working tree is not clean"
    return True, "ok"
