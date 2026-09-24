# Sublime WSL Tools

Two small, independent Sublime Text 4 utilities that make it comfortable to work
on Git repositories kept in WSL (Windows Subsystem for Linux) from the Windows
build of Sublime Text.

| Package | What it does |
| ------- | ------------ |
| [`wslgit`](wslgit/) | A `git.exe` shim that runs Git installed inside WSL. Speeds up GitSavvy and any Git-powered package on Windows. |
| [`GitWorktreeSwitcher`](GitWorktreeSwitcher/) | Navigate `git worktree` checkouts right from the command palette. |

They are deliberately independent and both live here as separate folders, so you
can use one without the other — but they are built to pair well: the switcher
understands wslgit-style path translation and turns it on automatically.

## Why these tools

You edit in the Windows build of Sublime Text, but your repos live in WSL
(`/home/you/...`, or on a Windows drive under `/mnt/c/...`). Two problems follow:

1. **Git is slow or broken.** `git.exe` is the Windows build and doesn't
   understand WSL paths or WSL files-permissions, so GitSavvy and friends are
   unreliable. `wslgit` fixes this by shimming the real WSL Git.
2. **Worktrees are tedious.** Repositories that grow many worktrees (workflow
   tools that spawn one worktree per task, mono-repos with several feature
   branches) have no built-in way to jump between them. `GitWorktreeSwitcher`
   lists them and switches your code context in one action.

## Requirements

- Sublime Text 4 (build 4022+) for the GitWorktreeSwitcher package (it uses
  `QuickPanelItem`).
- Windows 10/11 with WSL for `wslgit`.
- Git in WSL (`/usr/bin/git`).

## Install

Each folder is a ready-to-use Sublime Text package — copy or symlink it into your
`Packages` directory (`Preferences > Browse Packages...`). See the per-tool
README for details:

- [`wslgit` → install & build](wslgit/README.md)
- [`GitWorktreeSwitcher` → install & settings](GitWorktreeSwitcher/README.md)

## License

[MIT](LICENSE)