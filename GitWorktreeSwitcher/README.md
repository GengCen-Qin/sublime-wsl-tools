# Git Worktree Switcher

A lightweight Sublime Text 4 package for browsing code in `git worktree`
checkouts. It lists every worktree of the current repository and lets you move
the current Sublime code context to another one.

It is a *worktree navigator* only. Creating, deleting, pruning, locking or
checking out anything is left to `git`, your worktree tool, and GitSavvy.

## Features

- `Git Worktree: Switch` — replace the project folder of the current repository
  with another worktree. The sidebar, index, *Goto Definition*, project search
  and LSP all follow, and GitSavvy picks up the correct Git context by itself.
  The file you were viewing is reopened at the same relative path and cursor
  position when it exists in the target worktree.
- `Git Worktree: Open Current File In...` — open the same logical file from
  another worktree in a new tab, without touching the current project. Handy for
  comparing a file across worktrees.
- `Git Worktree: Open In New Window` — open a worktree in its own window.

Worktrees are read with `git worktree list --porcelain -z`; `.git/worktrees` is
never parsed and no Git state is ever modified.

## Install During Development

Copy or symlink this directory into Sublime Text's `Packages` directory as
`GitWorktreeSwitcher` (`Preferences > Browse Packages...`).

## Usage

Open the command palette and type `worktree`:

```text
Git Worktree: Switch
Git Worktree: Open Current File In...
Git Worktree: Open In New Window
```

`Git Worktree: Switch` shows:

```text
feature/login                              current
/home/me/worktrees/login             ·  4c5d6e7
main
/home/me/code/my-project             ·  9f8e7d6
task-01928
/home/me/worktrees/task-01928        ·  a1b2c3d
```

The current worktree is always first, then `main`/`master`, then the remaining
branches by name. Detached worktrees show `(detached) <short-sha>` and locked
ones are marked `locked`, but are still selectable.

Only the folder that matches the current repository root is rewritten; other
folders in the project and their per-folder settings (`folder_exclude_patterns`,
`name`, ...) are preserved.

## Key Bindings

No keys are bound by default. Add your own, for example in
`Packages/User/Default (Windows).sublime-keymap`:

```json
[
    { "keys": ["ctrl+alt+w"], "command": "git_worktree_switch" },
    { "keys": ["ctrl+alt+shift+w"], "command": "git_worktree_open_new_window" }
]
```

On macOS use `["super+alt+w"]` instead.

## Settings

`GitWorktreeSwitcher.sublime-settings`:

```json
{
    "git_binary": "git",
    "wsl_bridge": "auto",
    "open_matching_file_on_switch": true,
    "preserve_cursor_position": true,
    "show_full_path": true,
    "sort_main_first": true,
    "main_branch_names": ["main", "master"],
    "debug_log": false
}
```

- `git_binary` — git executable. Use a list when git is reached through a
  wrapper, for example `["wsl.exe", "git"]` or a path to `wslgit.exe`.
- `wsl_bridge` — path translation for a git binary that runs git inside WSL.
  See below.
- `open_matching_file_on_switch` — reopen the previously active file in the
  target worktree when the same relative path exists there.
- `preserve_cursor_position` — restore the cursor row/column of that file.
- `show_full_path` — show absolute worktree paths in the quick panel; `false`
  shortens the home directory to `~`.
- `sort_main_first` / `main_branch_names` — ordering of the quick panel.
- `debug_log` — print each step (git command, repo root, worktree count, panel
  selection, target file) to Sublime's console (`View > Show Console`). Turn it
  on when reporting a problem.

Override any of these in `Packages/User/GitWorktreeSwitcher.sublime-settings`.

## Running git through WSL (wslgit.exe)

With a bridge such as `wslgit.exe`, Sublime runs on Windows while git runs
inside WSL. The bridge translates the paths given *to* it, but git's answers
still come back as Linux paths (`/home/me/project`), while Sublime names the
same directories as `/?wsl.localhost/Ubuntu/home/me/project` or `D:/project`.
This plugin therefore translates in both directions itself:

- the folder handed to `git -C` is converted to its Linux form,
- every worktree path git reports is converted back to Sublime's spelling.

The prefix pair is calibrated from one observed folder/repository-root pair, so
no distro name or path style is hardcoded and the spelling Sublime itself uses
is preserved. Translation turns on automatically for a `wslgit.exe`-style
binary (`wsl_bridge: "auto"`); set it to `false` to disable it, or `true` to
force it for another wrapper. With a normal Windows git nothing is translated.

```json
{
    "git_binary": "C:/Users/me/AppData/Roaming/Sublime Text/Packages/User/GitSavvy-WSL/wslgit.exe"
}
```


## Behaviour Notes

- Files are never closed automatically, so unsaved buffers are safe.
- If the previously active file does not exist in the target worktree, the
  switch still happens and the status bar says so. Files outside the repository
  are left untouched.
- After a switch, LSP may need a moment to shut down the old workspace and index
  the new one; the plugin does not manage language servers.
- All Git calls run on a worker thread with a list-form command (no shell), so
  paths containing spaces are safe.
