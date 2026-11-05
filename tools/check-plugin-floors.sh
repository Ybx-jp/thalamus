#!/usr/bin/env bash
# Install each plugin with the core at exactly the version its floor names, from PyPI,
# and run what it ships.
#
# The gap this closes: a plugin declares `thalamus-memory>=X`, and a user who already
# has core X installed keeps it, because X satisfies the floor. Every other check here
# misses that user. The workspace installs every member from the checkout, the
# installs-alone check pairs a plugin with the workspace's own core wheel, and the
# release proof resolves the newest core on PyPI. So a plugin that starts importing a
# core name newer than its floor passes all of them and breaks only on that user's
# machine. Here the core is pinned to the floor itself, so the same import is an
# ImportError in the change that introduced it.
#
# A floor naming a pre-release (`0.1.2.dev0`) is the documented state of a plugin
# waiting on an unreleased core (CONTRIBUTING.md "Releasing"), and PyPI has no such
# core to install. By default that is reported and passes. With --release it fails,
# because a plugin cannot be published before the core it needs.
#
# Usage: tools/check-plugin-floors.sh [--release] <artifact>...
#   artifacts are plugin wheels or sdists (from `uv build`); the core's own artifacts,
#   and any package that does not depend on the core, are skipped and say so.
set -euo pipefail

release=0
if [ "${1:-}" = "--release" ]; then
  release=1
  shift
fi
[ "$#" -gt 0 ] || { echo "usage: $0 [--release] <artifact>..." >&2; exit 2; }

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
failed=0

# The artifact's own metadata: a wheel's METADATA, an sdist's PKG-INFO.
metadata() {
  case "$1" in
    *.whl) unzip -p "$1" '*.dist-info/METADATA' ;;
    *.tar.gz) tar -xOzf "$1" "$(tar -tzf "$1" | grep -E '^[^/]+/PKG-INFO$' | head -n1)" ;;
    *) echo "not a wheel or an sdist: $1" >&2; return 1 ;;
  esac
}

for artifact in "$@"; do
  artifact=$(cd "$(dirname "$artifact")" && pwd)/$(basename "$artifact")
  meta=$(metadata "$artifact")
  name=$(awk '/^Name:/ {print $2; exit}' <<< "$meta")
  label="$name ($(basename "$artifact"))"
  if [ "$name" = thalamus-memory ]; then
    echo "skip $label: the core itself"
    continue
  fi
  requirement=$(awk '/^Requires-Dist: thalamus-memory/ {sub(/^Requires-Dist: /, ""); print; exit}' <<< "$meta")
  if [ -z "$requirement" ]; then
    echo "skip $label: does not depend on thalamus-memory"
    continue
  fi
  # The lower bound of a `>=` specifier, whatever else the specifier carries.
  floor=$(sed -nE 's/.*>=[[:space:]]*([0-9][0-9A-Za-z.+!-]*).*/\1/p' <<< "$requirement")
  if [ -z "$floor" ]; then
    echo "FAIL $label: \`$requirement\` names no \`>=\` floor, so there is no version to prove it against" >&2
    failed=1
    continue
  fi
  if grep -qE '(a|b|rc|\.dev)[0-9]*$' <<< "$floor"; then
    if [ "$release" = 1 ]; then
      echo "FAIL $label: floors thalamus-memory at $floor, a pre-release. Release the core, raise the floor to that release, then release this package." >&2
      failed=1
    else
      echo "wait $label: floors thalamus-memory at $floor, which is not released; proven here once the floor names a release"
    fi
    continue
  fi

  env="$work/$(basename "$artifact")"
  uv venv -q "$env"
  if ! uv pip install -q --python "$env/bin/python" "$artifact" "thalamus-memory==$floor" 2>"$env.install"; then
    echo "FAIL $label: does not install beside thalamus-memory==$floor from PyPI:" >&2
    cat "$env.install" >&2
    failed=1
    continue
  fi
  module=$(tr - _ <<< "$name")
  # Isolated mode, from a directory that is not the checkout, so nothing on disk can
  # stand in for the installed core.
  if ! (cd "$work" && "$env/bin/python" -I - "$module" <<'EOF'
import importlib, pkgutil, sys
package = importlib.import_module(sys.argv[1])
for found in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
    importlib.import_module(found.name)
EOF
  ) 2>"$env.import"; then
    echo "FAIL $label: a module does not import against thalamus-memory==$floor, the floor it declares. Raise the floor to a core that has what it imports (CONTRIBUTING.md \"Releasing\"):" >&2
    tail -n 5 "$env.import" >&2
    failed=1
    continue
  fi
  if ! (cd "$work" && "$env/bin/thalamus" --help >/dev/null 2>"$env.help") || [ -s "$env.help" ]; then
    echo "FAIL $label: \`thalamus --help\` against thalamus-memory==$floor reported:" >&2
    cat "$env.help" >&2
    failed=1
    continue
  fi
  echo "ok   $label at thalamus-memory==$floor"
done

exit "$failed"
