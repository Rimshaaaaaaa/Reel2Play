"""Custom mechanics (feature 24, Later): the director writes a small script for a new
mechanic, and code decides whether it may run.

The script is parsed, never run, here. It may use only plain arithmetic, its own functions
and variables, ``Math``, and the ``api`` object the custom template hands it. Anything that
could reach the page or the network is refused: no globals (``window``, ``document``,
``fetch`` ...), no ``this`` or ``new``, no classes, imports, ``eval``, regular expressions,
``try``, generators or async code, and no property names like ``constructor`` or
``__proto__``. The game page's Content-Security-Policy also forbids eval and every network
call but the anonymous event counter, and the page removes the Function constructor before
the script runs, so even a name built at run time could not reach further.

A script that passes still runs only after the play-tester has played it in the sandbox
(a Modal Sandbox with no network in production) and every gate has passed.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import esprima

MAX_CHARS = 6000
REQUIRED = ("setup", "update", "draw")
OPTIONAL = ("tap", "drag", "hint")
FREE_NAMES = frozenset({"Math", "Infinity", "NaN", "undefined"})
ALLOWED_NODES = frozenset(
    {
        "Program",
        "VariableDeclaration",
        "VariableDeclarator",
        "FunctionDeclaration",
        "FunctionExpression",
        "ArrowFunctionExpression",
        "BlockStatement",
        "ExpressionStatement",
        "ReturnStatement",
        "IfStatement",
        "ForStatement",
        "ForOfStatement",
        "WhileStatement",
        "DoWhileStatement",
        "BreakStatement",
        "ContinueStatement",
        "EmptyStatement",
        "SwitchStatement",
        "SwitchCase",
        "BinaryExpression",
        "LogicalExpression",
        "UnaryExpression",
        "UpdateExpression",
        "AssignmentExpression",
        "ConditionalExpression",
        "CallExpression",
        "MemberExpression",
        "StaticMemberExpression",
        "ComputedMemberExpression",
        "ObjectExpression",
        "Property",
        "ArrayExpression",
        "Literal",
        "Identifier",
        "TemplateLiteral",
        "TemplateElement",
        "SequenceExpression",
        "SpreadElement",
    }
)
FORBIDDEN_WORDS = (
    "constructor",
    "prototype",
    "__proto__",
    "caller",
    "callee",
    "arguments",
    "__define",
    "__lookup",
)
FORBIDDEN_TEXT = ("</", "<!--", "<script")


class MechanicRejectedError(ValueError):
    """The script may not run; ``problems`` says why, in plain words."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def _children(node: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    for key, value in node.items():
        if isinstance(value, dict) and "type" in value:
            yield key, value
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and "type" in item:
                    yield key, item


def _declared(tree: dict[str, Any]) -> set[str]:
    """Every name the script declares: functions, parameters and variables."""
    names: set[str] = set()

    def visit(node: dict[str, Any]) -> None:
        kind = node["type"]
        if kind in ("FunctionDeclaration", "FunctionExpression") and node.get("id"):
            names.add(node["id"]["name"])
        if kind in ("FunctionDeclaration", "FunctionExpression", "ArrowFunctionExpression"):
            for param in node.get("params", []):
                if param.get("type") == "Identifier":
                    names.add(param["name"])
        if kind == "VariableDeclarator" and node["id"].get("type") == "Identifier":
            names.add(node["id"]["name"])
        for _, child in _children(node):
            visit(child)

    visit(tree)
    return names


def _bad_word(text: str) -> str | None:
    lowered = text.lower()
    return next((w for w in FORBIDDEN_WORDS if w.lower() in lowered), None)


def check_script(script: str) -> list[str]:
    """Why the script may not run; empty when it may."""
    problems: list[str] = []
    if not script.strip():
        return ["the script is empty"]
    if len(script) > MAX_CHARS:
        problems.append(f"the script is longer than {MAX_CHARS} characters")
    lowered = script.lower()
    for text in FORBIDDEN_TEXT:
        if text in lowered:
            problems.append(f"the script contains {text!r}")
    try:
        tree: dict[str, Any] = esprima.parseScript(script).toDict()
    except esprima.Error as exc:
        return [*problems, f"the script does not parse: {exc}"]

    declared = _declared(tree)
    seen: set[str] = set()

    def note(problem: str) -> None:
        if problem not in seen:
            seen.add(problem)
            problems.append(problem)

    def visit(node: dict[str, Any], parent: dict[str, Any] | None, key: str) -> None:
        kind = node["type"]
        if kind not in ALLOWED_NODES:
            note(f"{kind} is not allowed")
            return
        if kind in ("FunctionDeclaration", "FunctionExpression", "ArrowFunctionExpression"):
            if node.get("generator") or node.get("async"):
                note("generators and async functions are not allowed")
            if any(p.get("type") != "Identifier" for p in node.get("params", [])):
                note("parameters must be plain names")
        if kind == "VariableDeclarator" and node["id"].get("type") != "Identifier":
            note("variables must be plain names")
        if kind == "Literal":
            if node.get("regex"):
                note("regular expressions are not allowed")
            if isinstance(node.get("value"), str) and (word := _bad_word(node["value"])):
                note(f"the text {word!r} is not allowed")
        if kind == "TemplateElement":
            raw = str((node.get("value") or {}).get("raw", ""))
            if word := _bad_word(raw):
                note(f"the text {word!r} is not allowed")
        if kind == "BinaryExpression" and node.get("operator") == "+":
            joined = _static_text(node)
            if joined and (word := _bad_word(joined)):
                note(f"the text {word!r} is not allowed")
        if kind == "UnaryExpression" and node.get("operator") == "delete":
            note("delete is not allowed")
        if kind in ("MemberExpression", "StaticMemberExpression") and not node.get("computed"):
            name = str(node["property"].get("name", ""))
            if _bad_word(name) or name.startswith("__"):
                note(f"the property {name!r} is not allowed")
        if kind == "Identifier":
            name = node["name"]
            is_key = (
                parent is not None
                and key == "property"
                and parent["type"] in ("MemberExpression", "StaticMemberExpression")
                and not parent.get("computed")
            ) or (
                parent is not None
                and key == "key"
                and parent["type"] == "Property"
                and not parent.get("computed")
            )
            if is_key:
                if _bad_word(name) or name.startswith("__"):
                    note(f"the property {name!r} is not allowed")
            elif name not in declared and name not in FREE_NAMES:
                note(f"{name!r} is not available to a mechanic")
        for child_key, child in _children(node):
            visit(child, node, child_key)

    visit(tree, None, "")

    top = tree.get("body", [])
    functions = {n["id"]["name"] for n in top if n["type"] == "FunctionDeclaration" and n.get("id")}
    for name in REQUIRED:
        if name not in functions:
            problems.append(f"the script must define function {name}")
    for node in top:
        if node["type"] == "VariableDeclaration":
            for declarator in node.get("declarations", []):
                if _has_call(declarator.get("init")):
                    note("top-level values must be plain numbers, text, lists or objects")
        elif node["type"] != "FunctionDeclaration":
            note("only functions and constants may be written at the top level")
    return problems


def _static_text(node: dict[str, Any]) -> str | None:
    """Text that ``+`` builds from literals alone ("con" + "structor"), else None."""
    kind = node["type"]
    if kind == "Literal" and isinstance(node.get("value"), str):
        return str(node["value"])
    if kind == "TemplateLiteral" and not node.get("expressions"):
        return "".join(str((q.get("value") or {}).get("cooked", "")) for q in node["quasis"])
    if kind == "BinaryExpression" and node.get("operator") == "+":
        left, right = _static_text(node["left"]), _static_text(node["right"])
        if left is not None and right is not None:
            return left + right
    return None


def _has_call(node: dict[str, Any] | None) -> bool:
    if node is None:
        return False
    if node["type"] in ("CallExpression", "FunctionExpression", "ArrowFunctionExpression"):
        return True
    return any(_has_call(child) for _, child in _children(node))


def mechanic_head(script: str) -> str:
    """The <script> block that defines window.__r2pMechanic, for a script that passed."""
    problems = check_script(script)
    if problems:
        raise MechanicRejectedError(problems)
    hooks = ", ".join(
        f'{name}: typeof {name} === "function" ? {name} : undefined'
        for name in (*REQUIRED, *OPTIONAL)
    )
    # Belt and braces: even a property name built at run time cannot reach the Function
    # constructor (the page's CSP already forbids running text as code).
    guard = 'Object.defineProperty(Function.prototype, "constructor", { value: undefined });'
    return (
        f'<script>{guard}\nwindow.__r2pMechanic = (function () {{\n"use strict";\n'
        f"{script}\nreturn {{{hooks}}};\n}})();</script>"
    )
