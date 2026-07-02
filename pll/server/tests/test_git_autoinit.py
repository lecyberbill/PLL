"""Tests for git auto-init feature (standalone, no sqlalchemy dependency)."""
import os, subprocess, tempfile

def _git(*args, cwd):
    r = subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True, text=True, timeout=30)
    return {"ok": r.returncode == 0, "out": r.stdout.strip(), "err": r.stderr.strip()}

def _ensure_repo(git_dir):
    if not os.path.isdir(os.path.join(git_dir, ".git")):
        _git("init", cwd=git_dir)
        _git("config", "user.name", "test", cwd=git_dir)
        _git("config", "user.email", "test@test", cwd=git_dir)

def _parse_status(out: str):
    staged, modified, untracked, deleted = [], [], [], []
    for line in out.split("\n"):
        if not line.strip(): continue
        code = line[:2]
        path = line[3:].strip()
        index = code[0]
        worktree = code[1] if len(code) > 1 else " "
        if code == "??": untracked.append(path)
        elif index == "M" or worktree == "M": modified.append(path)
        elif index == "A": staged.append(path)
        elif index == "D" or worktree == "D": deleted.append(path)
    return staged, modified, untracked, deleted

def test_git_init_creates_git_dir():
    with tempfile.TemporaryDirectory() as tmp:
        git_dir = os.path.join(tmp, "proj")
        os.makedirs(git_dir)
        assert not os.path.isdir(os.path.join(git_dir, ".git"))
        _ensure_repo(git_dir)
        assert os.path.isdir(os.path.join(git_dir, ".git"))

def test_git_branch_after_init():
    with tempfile.TemporaryDirectory() as tmp:
        git_dir = os.path.join(tmp, "proj")
        os.makedirs(git_dir)
        _ensure_repo(git_dir)
        # Before first commit, rev-parse HEAD fails — default to "main"
        r = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=git_dir)
        assert not r["ok"]  # no commits yet, so HEAD is unborn

def test_git_untracked_file():
    with tempfile.TemporaryDirectory() as tmp:
        git_dir = os.path.join(tmp, "proj")
        os.makedirs(git_dir)
        _ensure_repo(git_dir)
        with open(os.path.join(git_dir, "hello.py"), "w") as f:
            f.write("print('hello')")
        r = _git("status", "--porcelain", cwd=git_dir)
        _, _, untracked, _ = _parse_status(r.get("out", ""))
        assert "hello.py" in untracked

def test_git_parse_status_empty():
    staged, modified, untracked, deleted = _parse_status("")
    assert staged == [] and modified == [] and untracked == [] and deleted == []

def test_git_parse_status_various():
    out = " M mod.py\nA  add.py\n?? new.py\n D del.py"
    staged, modified, untracked, deleted = _parse_status(out)
    assert modified == ["mod.py"], f"got {modified}"
    assert staged == ["add.py"], f"got {staged}"
    assert untracked == ["new.py"], f"got {untracked}"
    assert deleted == ["del.py"], f"got {deleted}"
