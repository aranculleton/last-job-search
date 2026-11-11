"""A GitHub Actions run played out here, for a test of which jobs a workflow starts.

GitHub's runners cannot be started from a test, and a mistake in an `if:` or a `needs:` shows
only on GitHub, after the push: a job that never runs looks the same as one that passed. So
this reads the workflow files and evaluates their own expressions, the way the Actions docs
describe them (docs.github.com, "Evaluate expressions in workflows and actions"): `&&` and
`||` give one of their sides, strings compare ignoring case, a missing property is null,
`labels.*.name` picks a field from every element, and a job `if:` with no status function is
read as `success() && (...)`, so a job whose need was skipped or failed is skipped too.

    run(workflow, github={...}, outputs={"plan": {...}}, fails={"suite"})
        -> {"plan": "success", "suite": "failure", "page": "skipped", ...}

A matrix job is one job here, as a later job's `needs` sees it. Only what this repo's
workflows use is understood; anything else raises, so a new kind of expression fails a test
here rather than being guessed at.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"

_TOKEN = re.compile(r"\s*(?:(?P<str>'(?:[^']|'')*')|(?P<num>\d+(?:\.\d+)?)"
                    r"|(?P<op>==|!=|<=|>=|&&|\|\||[!<>()\[\],.*])|(?P<name>[A-Za-z_][\w-]*))")


def load(name: str) -> dict:
    import yaml
    wf = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    if True in wf:                       # YAML 1.1 reads the key `on` as True
        wf["on"] = wf.pop(True)
    return wf


def _tokens(text: str) -> list[tuple[str, str]]:
    out, i = [], 0
    while i < len(text):
        m = _TOKEN.match(text, i)
        if not m or m.end() == i:
            if text[i:].strip() == "":
                break
            raise ValueError(f"cannot read expression at {text[i:]!r}")
        kind = m.lastgroup
        out.append((kind, m.group(kind)))
        i = m.end()
    return out


class _Picked(list):
    """The elements an object filter (`*`) picked: a property read from it is read from each."""


def _str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, (list, dict)):
        return json.dumps(v)
    return str(v)


def _num(v) -> float:
    if v is None:
        return 0.0
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip()) if v.strip() else 0.0
        except ValueError:
            return math.nan
    return math.nan


def _eq(a, b) -> bool:
    if isinstance(a, str) and isinstance(b, str):
        return a.casefold() == b.casefold()
    if type(a) is type(b) and not isinstance(a, (int, float)):
        return a == b
    x, y = _num(a), _num(b)
    return not (math.isnan(x) or math.isnan(y)) and x == y


def truthy(v) -> bool:
    if v is None or v is False or v == "":
        return False
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return not (v == 0 or math.isnan(v))
    return True


def _prop(obj, name: str):
    if isinstance(obj, _Picked):
        return _Picked(_prop(o, name) for o in obj)
    if isinstance(obj, dict):
        if name in obj:
            return obj[name]
        for k, v in obj.items():
            if isinstance(k, str) and k.casefold() == name.casefold():
                return v
    return None


class _Parser:
    def __init__(self, text: str, ctx: dict, status: dict):
        self.toks, self.i, self.ctx, self.status = _tokens(text), 0, ctx, status

    def peek(self, value=None):
        if self.i >= len(self.toks):
            return None
        tok = self.toks[self.i]
        return tok if value is None or tok[1] == value else None

    def take(self, value=None):
        tok = self.peek(value)
        if tok is None:
            raise ValueError(f"expected {value!r} at token {self.i}")
        self.i += 1
        return tok

    def parse(self):
        v = self.or_()
        if self.i != len(self.toks):
            raise ValueError(f"unread tokens {self.toks[self.i:]}")
        return v

    def or_(self):
        v = self.and_()
        while self.peek("||"):
            self.take()
            right = self.and_()
            v = v if truthy(v) else right
        return v

    def and_(self):
        v = self.eq()
        while self.peek("&&"):
            self.take()
            right = self.eq()
            v = right if truthy(v) else v
        return v

    def eq(self):
        v = self.cmp()
        while self.peek("==") or self.peek("!="):
            op = self.take()[1]
            right = self.cmp()
            v = _eq(v, right) if op == "==" else not _eq(v, right)
        return v

    def cmp(self):
        v = self.unary()
        while any(self.peek(o) for o in ("<", ">", "<=", ">=")):
            op = self.take()[1]
            x, y = _num(v), _num(self.unary())
            v = {"<": x < y, ">": x > y, "<=": x <= y, ">=": x >= y}[op]
        return v

    def unary(self):
        if self.peek("!"):
            self.take()
            return not truthy(self.unary())
        return self.postfix()

    def postfix(self):
        v = self.primary()
        while True:
            if self.peek("."):
                self.take()
                if self.peek("*"):
                    self.take()
                    v = _Picked(v.values() if isinstance(v, dict) else (v or []))
                else:
                    v = _prop(v, self.take()[1])
            elif self.peek("["):
                self.take()
                key = self.or_()
                self.take("]")
                v = v[int(_num(key))] if isinstance(v, list) and not isinstance(key, str) \
                    else _prop(v, _str(key))
            else:
                return v

    def primary(self):
        kind, value = self.take()
        if kind == "str":
            return value[1:-1].replace("''", "'")
        if kind == "num":
            return float(value)
        if value == "(":
            v = self.or_()
            self.take(")")
            return v
        if kind != "name":
            raise ValueError(f"unexpected {value!r}")
        if value in ("true", "false"):
            return value == "true"
        if value == "null":
            return None
        if self.peek("("):
            self.take()
            args = []
            while not self.peek(")"):
                args.append(self.or_())
                if self.peek(","):
                    self.take()
            self.take(")")
            return self.call(value, args)
        return self.ctx.get(value)

    def call(self, name: str, args: list):
        low = name.casefold()
        if low in self.status:
            return self.status[low]
        if low == "contains":
            hay, needle = args
            if isinstance(hay, list):
                return any(_eq(x, needle) for x in hay)
            return _str(needle).casefold() in _str(hay).casefold()
        if low == "startswith":
            return _str(args[0]).casefold().startswith(_str(args[1]).casefold())
        if low == "endswith":
            return _str(args[0]).casefold().endswith(_str(args[1]).casefold())
        if low == "fromjson":
            return json.loads(_str(args[0]))
        if low == "tojson":
            return json.dumps(args[0])
        if low == "format":
            return re.sub(r"\{(\d+)\}", lambda m: _str(args[1 + int(m.group(1))]), _str(args[0]))
        if low == "hashfiles":
            return self.ctx.get("__hashfiles__", "")
        raise ValueError(f"function {name} is not understood here")


def strip(expr) -> str:
    text = str(expr).strip()
    m = re.fullmatch(r"\$\{\{(.*)\}\}", text, re.S)
    return m.group(1).strip() if m else text


def evaluate(expr, ctx: dict, status: dict | None = None):
    """The value of one expression (`${{ }}` optional) in `ctx`: github, inputs, needs..."""
    status = status or {"always": True, "success": True, "failure": False, "cancelled": False}
    return _Parser(strip(expr), ctx, status).parse()


def _needs(job: dict) -> list[str]:
    n = job.get("needs") or []
    return [n] if isinstance(n, str) else list(n)


def run(workflow: str | dict, github: dict, inputs: dict | None = None,
        outputs: dict | None = None, fails=(), hashfiles: str = "") -> dict:
    """Each job's result for one run: "success", "failure" (a job in `fails`, as if one of its
    steps had failed) or "skipped" (its `if:` false, or a need not met). `outputs` are the
    outputs a job hands on when it succeeds."""
    wf = load(workflow) if isinstance(workflow, str) else workflow
    jobs, outputs = wf["jobs"], outputs or {}
    results: dict[str, str] = {}
    ancestors: dict[str, set] = {}
    pending = list(jobs)
    while pending:
        for name in pending:
            if all(n in results for n in _needs(jobs[name])):
                break
        else:
            raise ValueError(f"needs that never finish: {pending}")
        pending.remove(name)
        job, needs = jobs[name], _needs(jobs[name])
        ancestors[name] = set(needs).union(*(ancestors[n] for n in needs)) if needs else set()
        ctx = {"github": github, "inputs": inputs or {}, "__hashfiles__": hashfiles,
               "needs": {n: {"result": results[n],
                             "outputs": outputs.get(n, {}) if results[n] == "success" else {}}
                         for n in needs}}
        status = {"always": True, "cancelled": False,
                  "failure": any(results[a] == "failure" for a in ancestors[name]),
                  "success": all(results[n] == "success" for n in needs)
                  and not any(results[a] in ("failure", "cancelled") for a in ancestors[name])}
        cond = strip(job["if"]) if "if" in job else "true"
        if not re.search(r"\b(?:always|success|failure|cancelled)\s*\(", cond):
            cond = f"success() && ({cond})"
        ok = truthy(evaluate(cond, ctx, status))
        results[name] = "skipped" if not ok else ("failure" if name in fails else "success")
    return results


def needs_json(workflow: str | dict, job: str, results: dict, outputs: dict | None = None) -> dict:
    """`toJSON(needs)` as the job `job` would see it after `run`."""
    wf = load(workflow) if isinstance(workflow, str) else workflow
    outputs = outputs or {}
    return {n: {"result": results[n],
                "outputs": outputs.get(n, {}) if results[n] == "success" else {}}
            for n in _needs(wf["jobs"][job])}


def pull_request(action: str = "synchronize", labels=(), label: str = "",
                 private: bool = False, title: str = "A change") -> dict:
    """The github context of a pull request event."""
    g = {"event_name": "pull_request", "action": action,
         "repository": {"private": private},
         "event": {"action": action, "repository": {"private": private},
                   "pull_request": {"title": title, "labels": [{"name": n} for n in labels],
                                    "base": {"sha": "b" * 40}}}}
    if label:
        g["event"]["label"] = {"name": label}
    return g


def event(name: str, private: bool = False) -> dict:
    """The github context of a push, a schedule or a run by hand."""
    return {"event_name": name, "repository": {"private": private},
            "event": {"repository": {"private": private}, "before": "a" * 40}}
