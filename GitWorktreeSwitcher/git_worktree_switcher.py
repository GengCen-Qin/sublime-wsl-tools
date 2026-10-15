"""Git Worktree Switcher for Sublime Text 4.

Switch the current Sublime project folder to another ``git worktree`` of the
same repository. Git is the single source of truth: worktrees are read with
``git worktree list --porcelain`` and nothing is inferred from
``.git/worktrees``.

The plugin never modifies the repository: it does not create, delete, prune or
lock worktrees, does not checkout branches, and does not talk to GitSavvy.
Switching happens by rewriting the matching ``folders`` entry of the current
Sublime project, so the sidebar, index, Goto Definition, project search and LSP
all move to the selected worktree.
"""

from __future__ import annotations

import os
import posixpath
import re
import subprocess

import sublime
import sublime_plugin


SETTINGS_FILE = "GitWorktreeSwitcher.sublime-settings"

ERR_NO_REPO = "Git Worktree: current folder is not inside a Git repository."
ERR_NO_WORKTREES = "Git Worktree: unable to read Git worktrees."


def _setting(name, default):
    settings = sublime.load_settings(SETTINGS_FILE)
    return settings.get(name, default)


_DEBUG = True


def _log(message):
    """Write one line to Sublime's console (View > Show Console)."""
    if _DEBUG:
        print("[GitWorktreeSwitcher] {0}".format(message))


_git_prefix = None
_bridge = None


def refresh_git_prefix():
    """Cache ``git_binary`` on the UI thread.

    ``sublime.load_settings`` is a main-thread API, so the executable is
    resolved once before any Git command runs on a worker thread.
    """
    global _git_prefix, _bridge, _DEBUG
    _DEBUG = bool(_setting("debug_log", True))
    binary = _setting("git_binary", "git")
    if isinstance(binary, (list, tuple)):
        _git_prefix = [str(part) for part in binary]
    else:
        _git_prefix = [str(binary)]
    _bridge = PathBridge(_git_prefix, _setting("wsl_bridge", "auto"))
    _log("git command : {0}".format(" ".join(_git_prefix)))
    _log("wsl bridge  : enabled={0} mode={1}".format(
        _bridge.enabled, _setting("wsl_bridge", "auto")))


def _git_argv():
    """Return the git command prefix.

    ``git_binary`` accepts a string (``"git"``) or a list for wrappers such as
    a WSL bridge: ``["wsl.exe", "git"]``.
    """
    if _git_prefix is None:
        refresh_git_prefix()
    return list(_git_prefix)


def bridge():
    if _bridge is None:
        refresh_git_prefix()
    return _bridge


# ---------------------------------------------------------------------------
# WSL path bridge
#
# A git wrapper such as wslgit.exe runs git inside WSL. It translates the paths
# passed *to* it, but git's *output* still comes back as Linux paths
# (/home/me/project, /mnt/c/project), while Sublime names the same directories
# with its own spelling (/?wsl.localhost/Ubuntu/home/me/project, D:/project).
# GitSavvy gets away without this mapping because it runs git with the repo as
# the process working directory and only ever consumes relative paths; this
# plugin needs absolute worktree paths, so both directions are translated here.
#
# The prefix pair is calibrated from one observed folder/repository-root pair,
# so the plugin never has to guess a distro name or a path style.
# ---------------------------------------------------------------------------

_WSL_PREFIX_RE = re.compile(r"^//(?:wsl\.localhost|wsl\$)/([^/]+)(/.*)?$", re.IGNORECASE)
_POSIX_MOUNT_RE = re.compile(r"^/mnt/([a-zA-Z])/(.*)$")
_DRIVE_RE = re.compile(r"^([a-zA-Z]):[\\/](.*)$")
_SLASH_DRIVE_RE = re.compile(r"^/([a-zA-Z])/(.*)$")


def _forward_slashes(path):
    return path.replace("\\", "/")


def split_wsl_path(path):
    """Return ``(linux_path, distro)`` for a Windows-side WSL path, else None.

    Handles the spellings Sublime and Windows produce for a WSL location:
    ``\\\\wsl.localhost\\Ubuntu\\home\\me``, ``\\\\wsl$\\Ubuntu\\home\\me``,
    ``\\\\?\\UNC\\wsl.localhost\\Ubuntu\\home\\me`` and Sublime's own
    ``/?wsl.localhost/Ubuntu/home/me``.
    """
    fwd = path.replace("\\", "/")
    stripped = False
    for head in ("//?/UNC/", "/?/UNC/", "//?/", "/?/"):
        if fwd.startswith(head):
            fwd = "//" + fwd[len(head):]
            stripped = True
            break
    if not stripped:
        for head in ("//?", "/?"):
            if fwd.startswith(head):
                fwd = "//" + fwd[len(head):]
                break
    match = _WSL_PREFIX_RE.match(fwd)
    if not match:
        return None
    return match.group(2) or "/", match.group(1)


class PathBridge:

    """Translate between Sublime's path spelling and the git side spelling."""

    def __init__(self, git_argv, mode="auto"):
        self.sublime_prefix = ""
        self.git_prefix = ""
        self.distro = ""
        self.enabled = self._detect(git_argv, mode)

    @staticmethod
    def _detect(git_argv, mode):
        if mode is True:
            return True
        if mode is False:
            return False
        # "auto": translation is only correct for a binary that runs git through
        # WSL, which is the only configuration where git answers with Linux
        # paths while Sublime names the same files differently.
        names = [os.path.basename(str(part)).lower() for part in git_argv]
        return any("wslgit" in name or name.startswith("wsl") for name in names)

    def to_git(self, path):
        """Sublime path -> path the git side understands."""
        if not self.enabled:
            return path
        if not self.sublime_prefix:
            # Learn the prefix pair from the first path of a known style; a
            # Linux path teaches nothing and leaves the bridge untouched.
            self.learn(path)
        if self.sublime_prefix and path.startswith(self.sublime_prefix):
            rest = path[len(self.sublime_prefix):]
            return self.git_prefix + _forward_slashes(rest)
        wsl = split_wsl_path(path)
        if wsl:
            self.distro = self.distro or wsl[1]
            return wsl[0]
        match = _DRIVE_RE.match(path)
        if match:
            return "/mnt/{0}/{1}".format(
                match.group(1).lower(), _forward_slashes(match.group(2)))
        match = _SLASH_DRIVE_RE.match(path)
        if match:
            return "/mnt/{0}/{1}".format(match.group(1).lower(), match.group(2))
        return path

    def to_sublime(self, path):
        """git output path -> path Sublime can open."""
        if not self.enabled or not path.startswith("/"):
            return path
        if self.sublime_prefix and path.startswith(self.git_prefix):
            rest = path[len(self.git_prefix):]
            if "\\" in self.sublime_prefix:
                rest = rest.replace("/", "\\")
            return self.sublime_prefix + rest
        match = _POSIX_MOUNT_RE.match(path)
        if match:
            return "{0}:/{1}".format(match.group(1).upper(), match.group(2))
        if self.distro:
            return "\\\\wsl.localhost\\{0}{1}".format(
                self.distro, path.replace("/", "\\"))
        return path

    def learn(self, path):
        """Derive the prefix pair from any path of this style.

        A WSL path describes its own prefix (everything before the Linux part),
        so this works whether the path is the repository root, a subdirectory of
        it, or a parent of it - no observation of a matching pair is needed.
        """
        if not self.enabled:
            return False
        wsl = split_wsl_path(path)
        if wsl:
            linux, distro = wsl
            self.distro = distro
            original = path.rstrip("\\/")
            self.sublime_prefix = original[:len(original) - len(linux)].rstrip("\\/")
            self.git_prefix = ""
            return True
        match = _DRIVE_RE.match(path)
        if match:
            self.sublime_prefix = match.group(1) + ":"
            self.git_prefix = "/mnt/" + match.group(1).lower()
            return True
        match = _SLASH_DRIVE_RE.match(path)
        if match:
            self.sublime_prefix = "/" + match.group(1)
            self.git_prefix = "/mnt/" + match.group(1).lower()
            return True
        return False


# ---------------------------------------------------------------------------
# Git helpers. These run on a worker thread and never raise.
# ---------------------------------------------------------------------------

def run_git(args, cwd=None):
    """Run a git command without a shell. Returns an (ok, stdout) tuple.

    ``cwd`` is a Sublime-side path; it is translated to the git side before the
    command runs. The output is left in git-side spelling (the caller decides
    whether and how to translate it back).
    """
    command = _git_argv()
    if cwd is not None:
        command += ["-C", bridge().to_git(cwd)]
    command += list(args)
    kwargs = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
    }
    # The git binary is often a console app (e.g. wslgit.exe); without this flag
    # every call flashes a console window on Windows.
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    try:
        proc = subprocess.run(command, **kwargs)
    except (FileNotFoundError, OSError) as exc:
        _log("git failed  : {0} ({1})".format(" ".join(command), exc))
        return False, ""
    if proc.returncode != 0:
        _log("git exit {0}: {1}".format(proc.returncode, " ".join(command)))
        return False, ""
    return True, proc.stdout


def git_root(path):
    """Return the worktree root containing ``path`` (Sublime spelling), or None."""
    ok, out = run_git(["rev-parse", "--show-toplevel"], cwd=path)
    root = out.strip() if ok else ""
    if not root:
        return None
    # `path` may be the repository root, a subdirectory or a parent of it; the
    # bridge learns its prefix from the path style, then the root is expressed
    # in that same spelling.
    bridge().learn(path)
    return bridge().to_sublime(root)


class Worktree:

    __slots__ = ("path", "head", "branch", "detached", "locked", "is_main")

    def __init__(self, path):
        self.path = path
        self.head = None
        self.branch = None
        self.detached = False
        self.locked = False
        # The main (primary) checkout, e.g. the directory where the repo was
        # first cloned, as opposed to the linked worktrees. Set by the parser:
        # ``git worktree list`` guarantees the main worktree comes first.
        self.is_main = False

    def label(self):
        """Branch name, or a ``(detached) <short-sha>`` label."""
        if self.detached:
            return "(detached) {0}".format(self.head[:7]) if self.head else "(detached)"
        return self.branch or "(unknown)"

    def sort_label(self):
        # Detached worktrees have no branch name to sort by; push them after
        # the named branches instead of letting "(" sort before letters.
        if self.detached or not self.branch:
            return "\uffff" + (self.branch or self.path).lower()
        return self.branch.lower()


def _parse_porcelain(text, nul_separated):
    """Parse ``worktree list --porcelain`` output into Worktree objects.

    ``-z`` terminates every attribute with NUL and finishes each record with an
    extra NUL, while the default form separates attributes with newlines and
    records with an empty line. Both are flattened to attribute lines here; a
    record starts whenever a ``worktree <path>`` line appears, which keeps the
    parse independent of the record separator.
    """
    lines = []
    if nul_separated:
        for token in text.split("\x00"):
            lines.extend(token.splitlines())
    else:
        lines = text.splitlines()

    worktrees = []
    entry = None
    for line in lines:
        if line.startswith("worktree "):
            entry = Worktree(line[len("worktree "):])
            # The first record is the main worktree ("git worktree list"
            # always lists it first, before every linked worktree).
            if not worktrees:
                entry.is_main = True
            worktrees.append(entry)
        elif entry is None:
            continue
        elif line.startswith("HEAD "):
            entry.head = line[len("HEAD "):].strip()
        elif line.startswith("branch "):
            ref = line[len("branch "):].strip()
            entry.branch = ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref
        elif line == "detached":
            entry.detached = True
        elif line.startswith("locked"):
            entry.locked = True
    return [wt for wt in worktrees if wt.path]


def list_worktrees(repo_root):
    """Return every worktree of the repository, or None on failure.

    Paths are returned in Sublime's spelling. ``-z`` is preferred because it
    cannot be confused by spaces or newlines in a path; older git versions that
    do not support it fall back to the plain porcelain output.
    """
    worktrees = None
    ok, out = run_git(["worktree", "list", "--porcelain", "-z"], cwd=repo_root)
    if ok:
        worktrees = _parse_porcelain(out, True)
    else:
        ok, out = run_git(["worktree", "list", "--porcelain"], cwd=repo_root)
        if ok:
            worktrees = _parse_porcelain(out, False)
    if worktrees is None:
        return None

    bridge_ = bridge()
    for wt in worktrees:
        wt.path = bridge_.to_sublime(wt.path)
    return worktrees


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _real(path):
    """Real path used for worktree identity comparisons.

    WSL spellings (``/?wsl.localhost/...``, ``\\\\wsl.localhost\\...``) are only
    case/separator normalized: ``realpath`` would resolve them against the
    current drive on Windows and destroy the prefix the comparison relies on.
    Both sides of every comparison pass through here, so a consistent
    normalization is all that is required.
    """
    try:
        if split_wsl_path(path):
            return os.path.normcase(path.replace("/", os.sep))
        return os.path.normcase(os.path.realpath(path))
    except (OSError, ValueError):
        return os.path.normcase(path)


def _display_path(path):
    if _setting("show_full_path", True):
        return path
    home = os.path.expanduser("~")
    if home and path.startswith(home):
        return "~" + path[len(home):]
    return path


def relative_path_inside(file_path, root):
    """Path of ``file_path`` relative to ``root``, or None if it is outside.

    Both inputs are in Sublime's spelling. When a WSL bridge is active the
    comparison is done on the git side, so Windows path quirks (mixed
    separators, a prefix that is not a real drive path) cannot corrupt it.
    """
    if not file_path or not root:
        return None
    bridge_ = bridge()
    if bridge_.enabled:
        a = bridge_.to_git(file_path).replace("\\", "/")
        b = bridge_.to_git(root).replace("\\", "/")
        if not (a.startswith("/") and b.startswith("/")):
            return None
        try:
            rel = posixpath.relpath(a, b)
        except ValueError:
            return None
        if rel == "." or rel == ".." or rel.startswith("../"):
            return None
        return rel

    try:
        rel = os.path.relpath(file_path, root)
    except ValueError:
        return None
    if rel == os.curdir or rel.startswith(os.pardir + os.sep) or rel == os.pardir:
        return None
    if os.path.isabs(rel):
        return None
    return rel


def file_in_worktree(worktree_path, relative):
    """Absolute Subble path of ``relative`` inside ``worktree_path``.

    The join happens on the git side and is translated back, so the result is
    spelled exactly like ``worktree_path`` itself.
    """
    bridge_ = bridge()
    if bridge_.enabled:
        base = bridge_.to_git(worktree_path).replace("\\", "/")
        if base.startswith("/"):
            joined = posixpath.join(base, relative.replace("\\", "/"))
            return bridge_.to_sublime(joined)
    return os.path.join(worktree_path, relative)


def file_exists(file_path, worktree_root, relative):
    """True when ``relative`` exists inside ``worktree_root``.

    A WSL spelling may be unreadable by the local filesystem API, so when that
    check fails the file is looked up in the worktree through git instead.
    """
    if os.path.isfile(file_path):
        return True
    if not bridge().enabled:
        return False
    ok, out = run_git(
        ["ls-files", "--error-unmatch", "--", relative.replace("\\", "/")],
        cwd=worktree_root,
    )
    return ok and bool(out.strip())


def same_path(a, b):
    """True when two paths name the same directory, whatever their spelling."""
    return _real(a) == _real(b)


def sort_worktrees(worktrees, current_root):
    """Current worktree first, then the main one, then branches by name."""
    main_names = set(_setting("main_branch_names", ["main", "master"]))
    sort_main_first = _setting("sort_main_first", True)

    def key(wt):
        is_current = 0 if same_path(wt.path, current_root) else 1
        is_main = 1
        # The main worktree is a fixed location the user returns to often, so it
        # is kept near the top whether or not it happens to sit on main/master
        # (it is frequently on a feature branch).
        if sort_main_first and (wt.is_main or (wt.branch or "") in main_names):
            is_main = 0
        return (is_current, is_main, wt.sort_label())

    return sorted(worktrees, key=key)


def build_panel_items(worktrees, current_root):
    """Quick panel entries: branch as trigger, details as the worktree path.

    The main worktree is prefixed with ``*`` so the primary checkout can be told
    apart at a glance from the linked worktrees, which usually live under a
    tool-managed directory.
    """
    mark_main = _setting("mark_main_worktree", True)
    items = []
    for wt in worktrees:
        notes = []
        if same_path(wt.path, current_root):
            notes.append("current")
        if wt.locked:
            notes.append("locked")
        if wt.is_main:
            notes.append("main")
        details = _display_path(wt.path)
        if wt.head and not wt.detached:
            details = "{0}  ·  {1}".format(details, wt.head[:7])
        trigger = wt.label()
        if wt.is_main and mark_main:
            trigger = "* {0}".format(trigger)
        # annotation must be "" when empty: Sublime compares it against "",
        # and a None would be forwarded to the API as a non-string.
        items.append(sublime.QuickPanelItem(
            trigger=trigger,
            details=details,
            annotation=" ".join(notes),
        ))
    return items


# ---------------------------------------------------------------------------
# Sublime project folder handling (UI thread only)
# ---------------------------------------------------------------------------

def candidate_paths(window):
    """Paths to probe for a repository, most specific first."""
    candidates = []
    view = window.active_view()
    if view and view.file_name():
        candidates.append(os.path.dirname(view.file_name()))
    for folder in window.folders():
        if folder not in candidates:
            candidates.append(folder)
    return candidates


def replace_repo_folder(window, repo_root, new_root):
    """Point the project folders belonging to ``repo_root`` at ``new_root``.

    A project often opens a subdirectory of the repository rather than its root
    (for example ``<repo>/sub/dir``); that folder is mapped to the same
    relative subdirectory of the target worktree. Every other folder and every
    per-folder setting (``folder_exclude_patterns``, ``name``, ...) is
    preserved: only ``path`` changes.
    """
    project_data = window.project_data() or {}
    folders = project_data.get("folders") or []

    replaced = False
    for folder in folders:
        path = folder.get("path")
        if not path:
            continue
        expanded = os.path.expanduser(path)
        if same_path(expanded, repo_root):
            folder["path"] = new_root
            replaced = True
            continue
        # A folder below the repository root keeps its position inside the
        # worktree it is switched to.
        inside = relative_path_inside(expanded, repo_root)
        if inside:
            folder["path"] = file_in_worktree(new_root, inside)
            replaced = True

    if not replaced:
        # The repo is not itself a project folder (for instance the project
        # opens a parent directory). Keep what is there and add the worktree.
        folders.append({"path": new_root})

    project_data["folders"] = folders
    window.set_project_data(project_data)
    return True


def cursor_position(view):
    """First selection as a 1-based ``(row, column)`` tuple, or None."""
    if not view:
        return None
    selection = view.sel()
    if not selection:
        return None
    row, col = view.rowcol(selection[0].a)
    return row + 1, col + 1


def encoded_position(path, position):
    """Build a ``path:row:col`` reference for ``open_file`` when requested."""
    if not position or not _setting("preserve_cursor_position", True):
        return path
    return "{0}:{1}:{2}".format(path, position[0], position[1])


# ---------------------------------------------------------------------------
# Shared command flow: probe git off the UI thread, then show the panel
# ---------------------------------------------------------------------------

class WorktreeCommand(sublime_plugin.WindowCommand):

    """Base class: resolves the repository, lists worktrees, shows a picker."""

    def run(self, **kwargs):
        # window.folders() / active_view() / load_settings are UI-thread APIs,
        # so snapshot everything the worker thread needs before leaving it.
        self._candidates = candidate_paths(self.window)
        self._context = None
        refresh_git_prefix()
        sublime.set_timeout_async(self._resolve, 0)

    def _resolve(self):
        try:
            self._resolve_inner()
        except Exception as exc:  # surface failures instead of silently doing nothing
            import traceback
            details = traceback.format_exc()
            sublime.set_timeout(
                lambda: sublime.error_message(
                    "Git Worktree: {0}\n\n{1}".format(exc, details)), 0)

    def _resolve_inner(self):
        root = None
        for candidate in self._candidates:
            # No local isdir() gate: through a WSL bridge git can resolve paths
            # that Windows itself cannot stat, and git fails fast otherwise.
            _log("probing root: {0}".format(candidate))
            root = git_root(candidate)
            if root:
                _log("repo root   : {0}".format(root))
                break

        if not root:
            _log("no repository found")
            sublime.set_timeout(lambda: sublime.status_message(ERR_NO_REPO), 0)
            return

        worktrees = list_worktrees(root)
        _log("worktrees   : {0}".format(
            "None" if worktrees is None else len(worktrees)))
        if worktrees is None:
            sublime.set_timeout(lambda: sublime.error_message(ERR_NO_WORKTREES), 0)
            return

        sublime.set_timeout(lambda: self._show(root, worktrees), 0)

    def _show(self, root, worktrees):
        # `root` stays in Sublime's own spelling: it is what gets written back
        # into the project and what relative paths are computed against.
        self._context = (root, sort_worktrees(worktrees, root))
        if not self._context[1]:
            sublime.status_message("Git Worktree: no worktrees found.")
            return
        items = build_panel_items(self._context[1], root)
        _log("panel items : {0}".format(len(items)))
        self.window.show_quick_panel(items, self._selected)

    def _selected(self, index):
        _log("panel index : {0}".format(index))
        if index < 0 or not self._context:
            return
        current_root, worktrees = self._context
        try:
            self.selected(worktrees[index], current_root)
        except Exception as exc:
            import traceback
            details = traceback.format_exc()
            _log(details)
            sublime.error_message(
                "Git Worktree: {0}\n\n{1}".format(exc, details))

    def selected(self, worktree, current_root):
        raise NotImplementedError


class GitWorktreeSwitchCommand(WorktreeCommand):

    """Replace the current repository folder with another worktree."""

    def selected(self, worktree, current_root):
        _log("selected {0} -> {1}".format(worktree.label(), worktree.path))
        if same_path(worktree.path, current_root):
            sublime.status_message(
                "Git Worktree: already on {0}".format(worktree.label()))
            return

        target_root = worktree.path
        view = self.window.active_view()
        current_file = view.file_name() if view else None
        # The active file only maps onto the target worktree when it sits inside
        # this repository; a scratch buffer or unrelated folder is left alone.
        rel = relative_path_inside(current_file, current_root)
        position = cursor_position(view)
        _log("active file : {0}".format(current_file))
        _log("relative    : {0}".format(rel))
        _log("target root : {0}".format(target_root))

        replace_repo_folder(self.window, current_root, target_root)

        if not rel or not _setting("open_matching_file_on_switch", True):
            sublime.status_message(
                "Git Worktree: switched to {0}".format(worktree.label()))
            return

        target_file = file_in_worktree(target_root, rel)
        exists = file_exists(target_file, target_root, rel)
        _log("target file : {0}".format(target_file))
        _log("target exists: {0}".format(exists))
        if exists:
            self.window.open_file(
                encoded_position(target_file, position), sublime.ENCODED_POSITION)
            sublime.status_message(
                "Git Worktree: switched to {0}".format(worktree.label()))
        else:
            sublime.status_message(
                "Git Worktree: switched. Current file does not exist in target worktree.")


class GitWorktreeOpenCurrentFileCommand(WorktreeCommand):

    """Open the active file from another worktree, without switching project."""

    def selected(self, worktree, current_root):
        view = self.window.active_view()
        current_file = view.file_name() if view else None
        rel = relative_path_inside(current_file, current_root)
        if not rel:
            sublime.status_message(
                "Git Worktree: the current file is not inside this repository.")
            return

        target_file = file_in_worktree(worktree.path, rel)
        if not file_exists(target_file, worktree.path, rel):
            sublime.status_message(
                "Git Worktree: file does not exist in {0}.".format(worktree.label()))
            return

        self.window.open_file(
            encoded_position(target_file, cursor_position(view)),
            sublime.ENCODED_POSITION,
        )


class GitWorktreeOpenNewWindowCommand(WorktreeCommand):

    """Open a worktree in a new window, leaving the current window untouched."""

    def selected(self, worktree, current_root):
        target_root = worktree.path
        previous_id = self.window.id()
        self.window.run_command("new_window")
        self._await_new_window(previous_id, target_root, 0)

    def _await_new_window(self, previous_id, target_root, attempts):
        window = sublime.active_window()
        if window and window.id() != previous_id:
            window.set_project_data({"folders": [{"path": target_root}]})
            sublime.status_message(
                "Git Worktree: opened {0} in a new window.".format(target_root))
            return
        # A new window can take a moment to appear; retry briefly, then fall
        # back to the command line client if the API never yields one.
        if attempts < 20:
            sublime.set_timeout(
                lambda: self._await_new_window(previous_id, target_root, attempts + 1),
                50,
            )
            return
        self._open_with_cli(target_root)

    def _open_with_cli(self, target_root):
        try:
            subprocess.Popen(["subl", "-n", target_root])
            sublime.status_message(
                "Git Worktree: opened {0} via subl.".format(target_root))
        except OSError:
            sublime.error_message(
                "Git Worktree: could not open a new window for {0}.".format(target_root))
