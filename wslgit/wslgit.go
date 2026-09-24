// wslgit adapts Windows GUI programs that expect a git.exe-style executable
// to Git installed inside WSL.
package main

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"regexp"
	"strings"
)

const (
	defaultGit = "/usr/bin/git"
	wslExe     = `C:\Windows\System32\wsl.exe`
)

var drivePath = regexp.MustCompile(`^([A-Za-z]):[\\/](.*)$`)

func main() {
	wd, err := os.Getwd()
	if err != nil {
		fatalf("cannot determine the current directory: %v", err)
	}

	distro, linuxWD, isWSLPath := splitWSLPath(wd)
	if configured := os.Getenv("WSLGIT_DISTRO"); configured != "" {
		distro = configured
	}

	gitPath := os.Getenv("WSLGIT_GIT")
	if gitPath == "" {
		gitPath = defaultGit
	}

	args := make([]string, 0, len(os.Args)+8)
	if distro != "" {
		args = append(args, "-d", distro)
	}
	if isWSLPath {
		args = append(args, "--cd", linuxWD)
	} else if linuxPath, ok := windowsPathToLinux(wd); ok {
		args = append(args, "--cd", linuxPath)
	}
	args = append(args, "--exec", "/usr/bin/env", "LC_ALL=C.UTF-8")
	args = append(args, forwardedGitEnvironment()...)
	args = append(args, gitPath)

	for _, arg := range os.Args[1:] {
		args = append(args, convertArgument(arg, distro))
	}

	cmd := exec.Command(wslExe, args...)
	cmd.Stdin = os.Stdin
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.Env = os.Environ()

	err = cmd.Run()
	if err == nil {
		return
	}

	var exitErr *exec.ExitError
	if errors.As(err, &exitErr) {
		os.Exit(exitErr.ExitCode())
	}
	fatalf("cannot start WSL Git: %v", err)
}

func fatalf(format string, args ...any) {
	fmt.Fprintf(os.Stderr, "wslgit: "+format+"\n", args...)
	os.Exit(127)
}

func splitWSLPath(path string) (distro, linuxPath string, ok bool) {
	normalized := strings.ReplaceAll(path, "/", `\`)
	lower := strings.ToLower(normalized)

	var rest string
	for _, prefix := range []string{`\\wsl.localhost\`, `\\wsl$\`} {
		if strings.HasPrefix(lower, prefix) {
			rest = normalized[len(prefix):]
			break
		}
	}
	if rest == "" {
		return "", "", false
	}

	parts := strings.SplitN(rest, `\`, 2)
	distro = parts[0]
	if distro == "" {
		return "", "", false
	}
	if len(parts) == 1 || parts[1] == "" {
		return distro, "/", true
	}
	return distro, "/" + strings.ReplaceAll(parts[1], `\`, "/"), true
}

func windowsPathToLinux(path string) (string, bool) {
	match := drivePath.FindStringSubmatch(path)
	if match == nil {
		return "", false
	}
	return "/mnt/" + strings.ToLower(match[1]) + "/" +
		strings.ReplaceAll(match[2], `\`, "/"), true
}

func convertArgument(arg, currentDistro string) string {
	if distro, linuxPath, ok := splitWSLPath(arg); ok {
		if currentDistro == "" || strings.EqualFold(distro, currentDistro) {
			return linuxPath
		}
		return arg
	}
	if linuxPath, ok := windowsPathToLinux(arg); ok {
		return linuxPath
	}

	if key, value, found := strings.Cut(arg, "="); found {
		if distro, linuxPath, ok := splitWSLPath(value); ok {
			if currentDistro == "" || strings.EqualFold(distro, currentDistro) {
				return key + "=" + linuxPath
			}
		}
		if linuxPath, ok := windowsPathToLinux(value); ok {
			return key + "=" + linuxPath
		}
	}
	return arg
}

func forwardedGitEnvironment() []string {
	var forwarded []string
	for _, item := range os.Environ() {
		key, value, found := strings.Cut(item, "=")
		if !found || !strings.HasPrefix(strings.ToUpper(key), "GIT_") {
			continue
		}
		if converted, ok := windowsPathToLinux(value); ok &&
			(strings.HasSuffix(strings.ToUpper(key), "_PATH") ||
				strings.HasSuffix(strings.ToUpper(key), "_DIR") ||
				strings.HasSuffix(strings.ToUpper(key), "_FILE")) {
			value = converted
		}
		forwarded = append(forwarded, key+"="+value)
	}
	return forwarded
}
