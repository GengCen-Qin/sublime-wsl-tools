package main

import "testing"

func TestSplitWSLPath(t *testing.T) {
	tests := []struct {
		input  string
		distro string
		path   string
		ok     bool
	}{
		{`\\wsl.localhost\Ubuntu\home\alice\repo`, "Ubuntu", "/home/alice/repo", true},
		{`\\wsl$\Debian\srv\app`, "Debian", "/srv/app", true},
		{`\\wsl.localhost\Ubuntu`, "Ubuntu", "/", true},
		{`C:\src\app`, "", "", false},
	}

	for _, test := range tests {
		distro, path, ok := splitWSLPath(test.input)
		if distro != test.distro || path != test.path || ok != test.ok {
			t.Errorf("splitWSLPath(%q) = (%q, %q, %v), want (%q, %q, %v)",
				test.input, distro, path, ok, test.distro, test.path, test.ok)
		}
	}
}

func TestWindowsPathToLinux(t *testing.T) {
	path, ok := windowsPathToLinux(`D:\work tree\repo`)
	if !ok || path != "/mnt/d/work tree/repo" {
		t.Fatalf("windowsPathToLinux returned (%q, %v)", path, ok)
	}
}

func TestConvertArgument(t *testing.T) {
	tests := map[string]string{
		`\\wsl.localhost\Ubuntu\home\alice\a.txt`:             "/home/alice/a.txt",
		`--git-dir=\\wsl$\Ubuntu\home\alice\repo\.git`:        "--git-dir=/home/alice/repo/.git",
		`C:\Users\Alice\message.txt`:                          "/mnt/c/Users/Alice/message.txt",
		`--pathspec-from-file=D:\temp\paths.txt`:              "--pathspec-from-file=/mnt/d/temp/paths.txt",
		`:(literal)src\keep-windows-style-pathspec-unchanged`: `:(literal)src\keep-windows-style-pathspec-unchanged`,
	}

	for input, expected := range tests {
		if actual := convertArgument(input, "Ubuntu"); actual != expected {
			t.Errorf("convertArgument(%q) = %q, want %q", input, actual, expected)
		}
	}
}
