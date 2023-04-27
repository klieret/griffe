"""This module contains the code allowing to load modules from specific git commits.

```python
from griffe.git import load_git

# where `repo` is the folder *containing* `.git`
old_api = load_git("my_module", commit="v0.1.0", repo="path/to/repo")
```
"""

from __future__ import annotations

import os
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Any, Iterator, Sequence

from griffe import loader

if TYPE_CHECKING:
    from griffe.collections import LinesCollection, ModulesCollection
    from griffe.dataclasses import Module
    from griffe.docstrings.parsers import Parser
    from griffe.extensions import Extensions


def _assert_git_repo(repo: str) -> None:
    if not shutil.which("git"):
        raise RuntimeError("Could not find git executable. Please install git.")

    try:
        subprocess.run(
            ["git", "-C", repo, "rev-parse", "--is-inside-work-tree"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as err:
        raise OSError(f"Not a git repository: {repo!r}") from err


def _get_latest_tag(path: str | Path) -> str:
    if isinstance(path, str):
        path = Path(path)
    if not path.is_dir():
        path = path.parent
    output = subprocess.check_output(
        ["git", "describe", "--tags", "--abbrev=0"],
        cwd=path,
    )
    return output.decode().strip()


def _get_repo_root(path: str | Path) -> str:
    if isinstance(path, str):
        path = Path(path)
    if not path.is_dir():
        path = path.parent
    output = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=path,
    )
    return output.decode().strip()


@contextmanager
def tmp_worktree(repo: str | Path = ".", ref: str = "HEAD") -> Iterator[Path]:
    """Context manager that checks out the given reference in the given repository to a temporary worktree.

    Parameters:
        repo: Path to the repository (i.e. the directory *containing* the `.git` directory)
        ref: A Git reference such as a commit, tag or branch.

    Yields:
        The path to the temporary worktree.

    Raises:
        OSError: If `repo` is not a valid `.git` repository
        RuntimeError: If the `git` executable is unavailable, or if it cannot create a worktree
    """
    repo = str(repo)
    _assert_git_repo(repo)
    with TemporaryDirectory(prefix="griffe-worktree-") as td:
        uid = f"griffe_{ref}"
        target = os.path.join(td, uid)
        retval = subprocess.run(
            ["git", "-C", repo, "worktree", "add", "-b", uid, target, ref],
            capture_output=True,
        )
        if retval.returncode:
            raise RuntimeError(f"Could not create git worktree: {retval.stderr.decode()}")

        try:
            yield Path(target)
        finally:
            subprocess.run(["git", "-C", repo, "worktree", "remove", uid], stdout=subprocess.DEVNULL)
            subprocess.run(["git", "-C", repo, "worktree", "prune"], stdout=subprocess.DEVNULL)
            subprocess.run(["git", "-C", repo, "branch", "-d", uid], stdout=subprocess.DEVNULL)


def load_git(
    module: str | Path,
    *,
    ref: str = "HEAD",
    repo: str | Path = ".",
    submodules: bool = True,
    extensions: Extensions | None = None,
    search_paths: Sequence[str | Path] | None = None,
    docstring_parser: Parser | None = None,
    docstring_options: dict[str, Any] | None = None,
    lines_collection: LinesCollection | None = None,
    modules_collection: ModulesCollection | None = None,
    allow_inspection: bool = True,
) -> Module:
    """Load and return a module from a specific Git reference.

    This function will create a temporary
    [git worktree](https://git-scm.com/docs/git-worktree) at the requested reference
    before loading `module` with [`griffe.load`][griffe.loader.load].

    This function requires that the `git` executable is installed.

    Parameters:
        module: The module path, relative to the repository root.
        ref: A Git reference such as a commit, tag or branch.
        repo: Path to the repository (i.e. the directory *containing* the `.git` directory)
        submodules: Whether to recurse on the submodules.
        extensions: The extensions to use.
        search_paths: The paths to search into (relative to the repository root).
        docstring_parser: The docstring parser to use. By default, no parsing is done.
        docstring_options: Additional docstring parsing options.
        lines_collection: A collection of source code lines.
        modules_collection: A collection of modules.
        allow_inspection: Whether to allow inspecting modules when visiting them is not possible.

    Returns:
        A loaded module.
    """
    with tmp_worktree(repo, ref) as worktree:
        search_paths = [worktree / path for path in search_paths or ["."]]
        if isinstance(module, Path):
            module = worktree / module
        return loader.load(
            module=module,
            submodules=submodules,
            try_relative_path=False,
            extensions=extensions,
            search_paths=search_paths,
            docstring_parser=docstring_parser,
            docstring_options=docstring_options,
            lines_collection=lines_collection,
            modules_collection=modules_collection,
            allow_inspection=allow_inspection,
        )
