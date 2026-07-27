# The confinement boundary for a counterfactual arm (docs/04 layer 2, lab/022).
#
# An arm runs `--dangerously-skip-permissions`, and measurement showed it using
# that freedom: 3 of 24 arms read the operator's checkout by absolute path, and
# 9 of 88 reached past their pinned ref through the shared git object store.
# `prepare_worktree` closes the second by giving the arm a one-commit repo; this
# image closes the first by giving it a filesystem the operator's checkout is not
# in.
#
# bubblewrap would be lighter and does not work here: Ubuntu's
# `kernel.apparmor_restrict_unprivileged_userns=1` denies the uid map, so bwrap
# and plain `unshare` both fail on this box. Docker needs no kernel knob.
#
# The toolchain is deliberately *mounted*, not installed: the `claude` binary and
# `uv` come from the host at run time, so the arm runs the same versions the
# operator does and the image never drifts from them. Only the OS layer is baked.
FROM ubuntu:24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates curl ripgrep less \
    && rm -rf /var/lib/apt/lists/*

# Match the host uid/gid so files the arm writes into its mounted checkout are
# owned by the operator, not by root.
ARG UID=1000
ARG GID=1000
RUN if ! getent group "${GID}" >/dev/null; then groupadd -g "${GID}" arm; fi \
 && if ! getent passwd "${UID}" >/dev/null; then \
        useradd -m -u "${UID}" -g "${GID}" arm; \
    fi

# git refuses to operate on a checkout owned by a different uid than the caller;
# the arm's repo is bind-mounted from the host, so mark it safe unconditionally.
RUN git config --system --add safe.directory '*'

USER ${UID}:${GID}
WORKDIR /arm
