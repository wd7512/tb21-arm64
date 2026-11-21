# git-multibranch

- **Class:** port (container engines whose `exec` processes run with umask 0000).
- **Change:** the Dockerfile creates `/run/sshd` as `root:root` with mode `0755`, so the solution's `mkdir -p /run/sshd` does nothing.
- **Why:** `dockerd` sets its own umask to 0. When `dockerd` runs its own `containerd`, as a rootless engine usually does, processes started by `docker exec` inherit umask 0000. Harbor runs the oracle and the agent through `exec`, so `mkdir -p /run/sshd` creates a mode-0777 folder, and `sshd` exits with `/run/sshd must be owned by root and not group or world-writable`. Engines with a separate `containerd` service (the usual rootful install, and the CI runner) give `exec` umask 0022, so the task passed there unchanged.
- **Evidence:** on a rootless engine with a host-managed containerd, the upstream image `alexgshaw/git-multibranch:20251031` started `sshd` via `docker run` (umask 0022, `/run/sshd` mode 755). Via `docker exec` the umask was 0000, `/run/sshd` was mode 777, and `sshd` refused to start. The `dockerd` and `containerd` processes had umask 0000; RootlessKit had 0022.
- **Effect on the task:** none for the agent. The folder is sshd's own runtime directory, and the instruction and tests do not mention it.
