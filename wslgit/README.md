# wslgit

A tiny `git.exe` shim that runs the **Git installed inside WSL** instead of the
Windows build of Git.

It exists so that Windows GUI programs — Sublime Text and GitSavvy in
particular — can operate on repositories that live inside WSL, at WSL-native
speed, without path conversion bugs and without the WSL filesystem paying the
`/mnt/c` DrvFs penalty.

## Why

Point any Git-aware Windows program at this shim instead of `git.exe`:

- **Speed.** Git runs in the Linux filesystem. GitSavvy's status/diff/log calls
  stop crawling when the repo lives in `/home/you/...` rather than `/mnt/c/...`.
- **Correctness.** WSL paths (`\\wsl.localhost\Ubuntu\home\you\repo`) and
  Windows drive paths (`C:\src\repo`) are translated to their Linux form before
  Git sees them, and Git's exit code, stdout and stderr are passed through
  untouched.
- **No shell.** Arguments are forwarded verbatim as an argument vector, so
  paths with spaces or shell metacharacters are safe.

## Build

Requires Go 1.21+ (or any Go with `any` and `strings.Cut`). Build on the Windows
side or cross-compile from WSL:

```powershell
go test wslgit.go wslgit_test.go
go build -trimpath -ldflags="-s -w" -o wslgit.exe wslgit.go
```

Cross-compiling from WSL:

```bash
GOOS=windows GOARCH=amd64 go build -trimpath -ldflags="-s -w" -o wslgit.exe wslgit.go
```

Drop the resulting `wslgit.exe` somewhere durable, e.g.:

```
%APPDATA%\Sublime Text\Packages\User\GitSavvy-WSL\wslgit.exe
```

The binary is not committed to this repository; build it yourself so you know
what you are running.

## Use with GitSavvy

GitSavvy looks for Git in a few well-known places, so the cleanest way to
redirect it without touching the package is GitSavvy's own Git-path setting
(check GitSavvy's README for the exact key in your version), pointing at the
shim:

```json
{
    "git_path": "C:/Users/you/AppData/Roaming/Sublime Text/Packages/User/GitSavvy-WSL/wslgit.exe"
}
```

Then open a repository by its WSL path in Sublime:

```text
\\wsl.localhost\Ubuntu\home\you\repo
```

GitSavvy's status bar, commit log, branch view, diff and merge-request commands
all work against the WSL repository.

## Use with other tools

Anything that takes a path to a Git executable can use it, for example:

```json
{
    "git_binary": "C:/Users/you/AppData/Roaming/Sublime Text/Packages/User/GitSavvy-WSL/wslgit.exe"
}
```

This is exactly how [`GitWorktreeSwitcher`](../GitWorktreeSwitcher/) is
configured — see its README for how the two work together.

## How it works

1. Read the current working directory (the process that spawns Git decides this;
   GitSavvy sets it to the repository root).
2. Detect the WSL distribution and Linux path from `\\wsl.localhost\<distro>\...`
   or `\\wsl$\<distro>\...`, falling back to `/mnt/<drive>/...` for `C:\...`
   style paths.
3. Start `wsl.exe -d <distro> --cd <linux path> --exec ... /usr/bin/git <args>`,
   converting every argument to its Linux form the same way.
4. Mirror stdin/stdout/stderr straight through and exit with Git's own exit
   status.

Environment variables whose names start with `GIT_` are forwarded into WSL, and
values that are Windows paths are converted when the variable looks
path-shaped (`*_PATH`, `*_DIR`, `*_FILE`) — so things like `GIT_INDEX_FILE` and
`GIT_DIR` keep working.

The current directory's distro wins: an argument that points into a *different*
WSL distro is left alone rather than silently rewritten to a path that does not
exist in the active one.

## Configuration

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `WSLGIT_DISTRO` | auto-detected from the working directory | Force a specific WSL distribution. |
| `WSLGIT_GIT` | `/usr/bin/git` | Path to the Git executable **inside WSL**. |

`LC_ALL=C.UTF-8` is set inside WSL so Git's output parses consistently from a
Windows host with a non-UTF-8 code page.

## Limitations

- Windows-only (it is a Windows executable that shells into WSL).
- `wsl.exe` is invoked from `C:\Windows\System32\wsl.exe`; a non-standard
  Windows installation would need a code change.
- Interactive Git commands that expect a terminal, such as `git rebase -i` or
  credential prompts using a terminal, are better run from a real WSL shell.
  Git credential helpers that talk to Windows (Git Credential Manager) are not
  forwarded.
- Because it is a console application, a program that spawns it without
  suppressing console creation may flash a window. That is up to the caller: in
  Python, `subprocess` needs `creationflags=CREATE_NO_WINDOW` (0x08000000).

## Tests

`wslgit_test.go` covers path detection and argument conversion:

```bash
go test wslgit.go wslgit_test.go
```

## License

[MIT](../LICENSE)