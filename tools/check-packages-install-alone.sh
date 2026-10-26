#!/usr/bin/env bash
# Install each distribution the workspace builds into a clean environment of its own,
# outside the checkout, and run what it adds.
#
# The gap this closes: in the uv workspace every package installs into one
# environment, so a plugin that imports something its own pyproject.toml does not
# declare passes the whole suite and every arch gate, and fails only when a user
# installs it alone. Here the core goes in by itself, then each plugin goes in with the
# core and nothing else, so an undeclared import is an ImportError.
#
# Usage: tools/check-packages-install-alone.sh <dist-dir>   (from `uv build --all-packages`)
set -euo pipefail

dist=$(cd "${1:?usage: $0 <dist-dir>}" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$work"

core_wheel=$(ls "$dist"/thalamus_memory-*.whl)

# The core alone: every command it owns answers, no plugin is loaded, and nothing
# reports a plugin failure.
uv venv -q "$work/core"
uv pip install -q --python "$work/core/bin/python" "$core_wheel"
"$work/core/bin/thalamus" --help >/dev/null 2>"$work/core.err"
if [ -s "$work/core.err" ]; then
  echo "core alone wrote to stderr:" >&2; cat "$work/core.err" >&2; exit 1
fi
if "$work/core/bin/thalamus" ingest --help >/dev/null 2>&1; then
  echo "core alone answers \`thalamus ingest\`, which belongs to thalamus-ingest" >&2
  exit 1
fi
if "$work/core/bin/thalamus" reflex --help >/dev/null 2>&1; then
  echo "core alone answers \`thalamus reflex\`, which belongs to thalamus-reflex" >&2
  exit 1
fi
if "$work/core/bin/thalamus" pulse --help >/dev/null 2>&1; then
  echo "core alone answers \`thalamus pulse\`, which belongs to thalamus-measure" >&2
  exit 1
fi
for cmd in console spawn room dispatch ceremony; do
  if "$work/core/bin/thalamus" "$cmd" --help >/dev/null 2>&1; then
    echo "core alone answers \`thalamus $cmd\`, which belongs to thalamus-console" >&2
    exit 1
  fi
done
if "$work/core/bin/thalamus" pin --help | grep -q -- --room; then
  echo "core alone offers \`pin --room\`, which belongs to thalamus-console" >&2
  exit 1
fi
# The SessionEnd hooks run `eval sync --write` after every distillation, so the core has
# to answer it with no plugin installed.
"$work/core/bin/thalamus" eval sync --help >/dev/null
echo "ok  thalamus-memory alone"

# Each plugin with the core and its own declared dependencies, nothing more.
for wheel in "$dist"/thalamus_*.whl; do
  name=$(basename "$wheel" | cut -d- -f1)
  [ "$name" = thalamus_memory ] && continue
  env="$work/$name"
  uv venv -q "$env"
  uv pip install -q --python "$env/bin/python" "$core_wheel" "$wheel"
  # Every module the plugin ships, imported in isolated mode so nothing from the
  # current directory can satisfy an import the package should have declared.
  "$env/bin/python" -I - "$name" <<'EOF'
import importlib, pkgutil, sys
package = importlib.import_module(sys.argv[1])
for module in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
    importlib.import_module(module.name)
EOF
  # The commands it registers, through the installed entry-point table.
  "$env/bin/thalamus" --help >"$work/$name.help" 2>"$work/$name.err"
  if [ -s "$work/$name.err" ]; then
    echo "$name: \`thalamus --help\` wrote to stderr:" >&2; cat "$work/$name.err" >&2; exit 1
  fi
  echo "ok  $name with thalamus-memory"
done

# The ingest plugin's commands, named: a plugin that loads and registers nothing would
# pass the loop above.
"$work/thalamus_ingest/bin/thalamus" ingest --help >/dev/null
"$work/thalamus_ingest/bin/thalamus" backfill-chunks --help >/dev/null
echo "ok  thalamus ingest, thalamus backfill-chunks"

# The reflex plugin's commands, including the two under core's `eval`, and its hook
# scripts: shipped in the wheel, accepted by core, and executable once installed.
"$work/thalamus_reflex/bin/thalamus" reflex --help >/dev/null
"$work/thalamus_reflex/bin/thalamus" eval reflex --help >/dev/null
"$work/thalamus_reflex/bin/thalamus" eval vocabulary --help >/dev/null
"$work/thalamus_reflex/bin/python" -I - <<'EOF'
import os
from thalamus import plugins
loaded = plugins.load()
hooks = loaded.hooks()
assert not loaded.failures, loaded.failures
assert {h.script.name for h in hooks} == {"reflex.sh", "reflex-pointer-tap.sh"}, hooks
assert all(os.access(h.script, os.X_OK) for h in hooks), hooks
EOF
echo "ok  thalamus reflex, thalamus eval reflex|vocabulary, and its two hook scripts"

# The measure plugin's commands under core's `eval`, the dashboard, and the page it
# serves, which ships in the wheel beside the module that reads it.
for cmd in report uses pins withholding gremlin recipes profile; do
  "$work/thalamus_measure/bin/thalamus" eval "$cmd" --help >/dev/null
done
"$work/thalamus_measure/bin/thalamus" pulse --help >/dev/null
"$work/thalamus_measure/bin/python" -I - <<'EOF'
from thalamus_measure.pulse.web import STATIC_DIR
assert (STATIC_DIR / "index.html").is_file(), STATIC_DIR
EOF
echo "ok  thalamus eval report|uses|pins|withholding|gremlin|recipes|profile, thalamus pulse and its page"

# The console plugin's commands, the options it adds to core's, and the client it serves,
# which ships in the wheel beside the server that reads it.
for cmd in console spawn room dispatch ceremony; do
  "$work/thalamus_console/bin/thalamus" "$cmd" --help >/dev/null
done
"$work/thalamus_console/bin/thalamus" pin --help | grep -q -- --room
"$work/thalamus_console/bin/thalamus" eval cost --help | grep -q -- --by-occasion
"$work/thalamus_console/bin/python" -I - <<'EOF'
from thalamus_console.server import STATIC_DIR
for name in ("index.html", "app.js", "sw.js", "style.css"):
    assert (STATIC_DIR / name).is_file(), STATIC_DIR / name
EOF
echo "ok  thalamus console|spawn|room|dispatch|ceremony, pin --room, eval cost --by-occasion, and its client"
