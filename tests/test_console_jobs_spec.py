"""
The jobs-source OpenAPI document: well formed, internally consistent, and the pages'.

Interfaces: packages/thalamus-console/src/thalamus_console/jobs_source.openapi.json, the
console's forwarder (jobs_source._REST), and the paths jobs.js, board.js and surface.js
call through api() and apiPost().
Infrastructure: the files on disk and jsonschema, which the console never imports at run
time. It is not declared here because `mcp`, a core dependency, already requires it;
declaring it in the dev extra moves a pinned ledger ground (A0122) that only main can
re-read. No server.
Scope: the document is the only agreement between the console's pages, a jobs source
and qe's contract cases, so this holds it to what the other two rely on — every
example validates against its own schema (tests/js/spec-render.test.mjs renders the
same examples through the pages), every shape is closed, every operation answers its
errors in the one Error shape, every write that starts real work says so, and no path
parameter admits more than the console's forwarder would forward.
"""

import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from thalamus_console import jobs_source
from thalamus_console.server import STATIC_DIR

SPEC_PATH = Path(jobs_source.__file__).with_name("jobs_source.openapi.json")
SPEC = json.loads(SPEC_PATH.read_text())
SCHEMAS = SPEC["components"]["schemas"]
METHODS = ("get", "post")
OPERATIONS = [(p, m, op) for p, item in SPEC["paths"].items() for m, op in item.items() if m in METHODS]


def _validator(schema: dict) -> Draft202012Validator:
    """A validator whose `#/components/...` refs resolve inside the document."""
    return Draft202012Validator({**schema, "components": SPEC["components"]})


def _resolve(node: dict) -> dict:
    while "$ref" in node:
        kind, name = node["$ref"].split("/")[-2:]
        node = SPEC["components"][kind][name]
    return node


def test_it_is_an_openapi_3_1_document_for_the_v1_console_tree():
    assert SPEC["openapi"] == "3.1.0"
    assert SPEC["servers"] == [{"url": "/v1/console"}]
    assert SPEC["components"]["securitySchemes"]["bearer"] == {"type": "http", "scheme": "bearer"}
    assert SPEC["security"] == [{"bearer": []}]


@pytest.mark.parametrize("name", sorted(SCHEMAS))
def test_every_schema_is_valid_json_schema(name):
    Draft202012Validator.check_schema({**SCHEMAS[name], "components": SPEC["components"]})


def _closed(schema: dict, where: str, seen: set) -> list[str]:
    """Object shapes that leave additionalProperties open or omit a required list."""
    out = []
    if id(schema) in seen:
        return out
    seen.add(id(schema))
    if schema.get("type") == "object" and "properties" in schema:
        if schema.get("additionalProperties") is not False:
            out.append(f"{where}: additionalProperties is not false")
        if "required" not in schema:
            out.append(f"{where}: no required list")
    for key in ("properties",):
        for k, v in schema.get(key, {}).items():
            out += _closed(v, f"{where}.{k}", seen)
    for key in ("items",):
        if isinstance(schema.get(key), dict):
            out += _closed(schema[key], f"{where}[]", seen)
    for key in ("oneOf", "anyOf", "allOf"):
        for i, v in enumerate(schema.get(key, [])):
            out += _closed(v, f"{where}/{key}{i}", seen)
    return out


def test_every_shape_the_pages_read_is_closed():
    problems = []
    for name, schema in SCHEMAS.items():
        problems += _closed(schema, name, set())
    assert not problems, problems


def test_every_operation_has_an_id_an_example_and_the_shared_errors():
    ids = [op["operationId"] for _, _, op in OPERATIONS]
    assert len(ids) == len(set(ids))
    for path, method, op in OPERATIONS:
        responses = op["responses"]
        assert "200" in responses and "401" in responses and "502" in responses, (path, method)
        for status, resp in responses.items():
            if status.startswith("2"):
                continue
            body = _resolve(resp)["content"]["application/json"]
            assert body["schema"] == {"$ref": "#/components/schemas/Error"}, (path, status)
        ok = responses["200"]["content"]
        if path.endswith("/files/{path}"):
            continue
        media = ok["application/json"]
        assert "example" in media or "examples" in _resolve(media["schema"]), (path, method)


def test_every_post_has_a_closed_body():
    for path, method, op in OPERATIONS:
        if method != "post":
            continue
        body = op["requestBody"]["content"]["application/json"]
        schema = _resolve(body["schema"])
        assert "example" in body, path
        if "oneOf" not in schema:
            assert schema.get("additionalProperties") is False, path


SIDE_EFFECTS = {"labelFinding", "runJob", "replayRun", "setAutoApply", "revertChange", "setNotifications",
                "saveBoard", "writeApp"}


def test_every_write_that_starts_real_work_is_marked():
    marked = {op["operationId"] for _, _, op in OPERATIONS if op.get("x-side-effect") is True}
    assert marked == SIDE_EFFECTS
    for _, method, op in OPERATIONS:
        if method == "post" and op["operationId"] not in SIDE_EFFECTS:
            assert op.get("x-side-effect") is False, op["operationId"]


def _examples():
    for name, schema in SCHEMAS.items():
        for i, ex in enumerate(schema.get("examples", [])):
            yield f"schema {name}#{i}", {"$ref": f"#/components/schemas/{name}"}, ex
    for path, method, op in OPERATIONS:
        body = op.get("requestBody", {}).get("content", {}).get("application/json")
        if body and "example" in body:
            yield f"{method} {path} body", body["schema"], body["example"]
        for status, resp in op["responses"].items():
            media = _resolve(resp).get("content", {}).get("application/json")
            if media and "example" in media:
                yield f"{method} {path} {status}", media["schema"], media["example"]


@pytest.mark.parametrize("where,schema,example", list(_examples()), ids=lambda v: v if isinstance(v, str) else "")
def test_every_example_validates_against_its_schema(where, schema, example):
    errors = sorted(_validator(schema).iter_errors(example), key=str)
    assert not errors, f"{where}: {errors[0].message} at {list(errors[0].absolute_path)}"


HOSTILE = ["..", "a/../b", "a//b", "/a", "a b", "a%2fb", "a?b", "http://x"]


def test_no_path_parameter_admits_more_than_the_forwarder_forwards():
    for path, _, op in OPERATIONS:
        for p in op.get("parameters", []):
            if p["in"] != "path":
                continue
            pattern = re.compile(p["schema"]["pattern"])
            for s in HOSTILE:
                assert not pattern.search(s) or jobs_source._REST.match(s) and ".." not in s and "//" not in s, \
                    (path, p["name"], s)
            if not p.get("x-multi-segment"):
                assert not pattern.search("a/b"), (path, p["name"])


def test_the_tone_vocabulary_is_closed_and_runs_map_one_to_one():
    tones = SCHEMAS["Tone"]["enum"]
    assert tones == ["ok", "faint", "danger", "pending", "muted", "accent"]
    # A run's status reaches the page only when it is not the normal case (N5); the stored
    # words notable and silent never do.
    assert SCHEMAS["RunStatus"]["x-tones"] == {"failed": "danger", "running": "pending", "found nothing": "muted",
                                              "skipped": "faint"}


# The page calls each jobs-source path through api("<literal>" + ...) or apiPost(...).
CALL = re.compile(r"\bapi(?:Post)?\(\s*\"([^\"]+)\"")


def _templates() -> list[re.Pattern]:
    out = []
    for path in SPEC["paths"]:
        rx = re.sub(r"\{[^}]+\}", "[^/]+", path.lstrip("/"))
        out.append(re.compile(f"^{rx}"))
    return out


@pytest.mark.parametrize("page", ["jobs.js", "board.js", "surface.js"])
def test_every_path_a_page_calls_is_in_the_spec(page):
    src = (STATIC_DIR / page).read_text()
    literals = CALL.findall(src)
    templates = _templates()
    spec_prefixes = [p.lstrip("/").split("{")[0] for p in SPEC["paths"]]
    for lit in literals:
        lit = lit.split("?")[0]
        # A literal that ends at a slash is the fixed head of a path the page completes
        # with an id; it must be the head of some operation's path.
        assert any(t.match(lit) for t in templates) or any(p.startswith(lit) for p in spec_prefixes), (page, lit)
