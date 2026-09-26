#!/usr/bin/env python3
"""
BARKLY DOCS
Human-friendly automatic project documentation generator.

One file.
Standard library only.
Static AST analysis — project code is never imported or executed.

Structure:
01 Project
02 Principles
03 Components
04 API Endpoints
05 Functions & Methods
06 Classes
07 Modules
08 Imports
09 Lifecycle
10 Git
11 Changelog

Design principle:
Show the shape first.
Reveal the details when the human asks for them.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import html
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ============================================================
# PROJECT DEFAULTS
# ============================================================

PROJECT = {
    "name": "CYN-X",
    "type": "AI / Software / Systems",
    "status": "Active",
    "description": (
        "Human-centered intelligent systems designed to adapt to people "
        "rather than forcing people to adapt to technology."
    ),
    "principles": [
        "Human First",
        "Understandable",
        "Private Where Practical",
        "Experimental",
    ],
    "components": [
        "CYN-X Core",
        "Local AI",
        "Multimodal Interaction",
        "Tools + Systems",
    ],
    "lifecycle": [
        "Idea",
        "Research",
        "Experiment",
        "Prototype",
        "Community Testing",
        "Engineering",
        "Productization",
        "Release",
        "Feedback",
        "Continued Development",
    ],
}


STATE_FILE = ".barkly-docs-state.json"


# ============================================================
# INLINE PAW LOGO
# ============================================================

PAW_SVG = """
<svg viewBox="0 0 100 100" aria-hidden="true">
  <path d="
    M30 43
    C19 43 12 35 14 25
    C16 16 24 12 31 16
    C38 20 40 31 37 37
    C35 41 33 43 30 43

    M70 43
    C81 43 88 35 86 25
    C84 16 76 12 69 16
    C62 20 60 31 63 37
    C65 41 67 43 70 43

    M50 36
    C42 36 37 29 39 22
    C41 15 47 12 52 15
    C58 18 59 26 56 32
    C55 35 53 36 50 36

    M50 52
    C35 52 24 62 24 75
    C24 87 34 92 45 88
    C49 87 52 87 56 88
    C67 92 76 87 76 75
    C76 62 65 52 50 52
  "/>
</svg>
"""


# ============================================================
# DATA MODELS
# ============================================================

@dataclass
class Parameter:
    name: str
    annotation: str = ""
    default: str = ""
    kind: str = ""


@dataclass
class FunctionInfo:
    name: str
    file: str
    line: int
    params: list[Parameter] = field(default_factory=list)
    returns: str = ""
    doc: str = ""
    decorators: list[str] = field(default_factory=list)
    class_name: str = ""
    is_method: bool = False
    is_new: bool = False
    is_changed: bool = False

    @property
    def qualified_name(self) -> str:
        if self.class_name:
            return f"{self.class_name}.{self.name}"
        return self.name

    @property
    def signature(self) -> str:
        parts = []

        for param in self.params:
            text = param.name

            if param.annotation:
                text += f": {param.annotation}"

            if param.default:
                text += f" = {param.default}"

            parts.append(text)

        result = f"{self.name}({', '.join(parts)})"

        if self.returns:
            result += f" -> {self.returns}"

        return result


@dataclass
class ClassInfo:
    name: str
    file: str
    line: int
    doc: str = ""
    decorators: list[str] = field(default_factory=list)
    methods: list[FunctionInfo] = field(default_factory=list)
    is_new: bool = False
    is_changed: bool = False


@dataclass
class EndpointInfo:
    methods: list[str]
    path: str
    file: str
    line: int
    function: str
    params: list[Parameter] = field(default_factory=list)
    returns: str = ""
    doc: str = ""
    framework: str = ""
    decorators: list[str] = field(default_factory=list)
    is_new: bool = False
    is_changed: bool = False

    @property
    def method_text(self) -> str:
        return " / ".join(self.methods)


@dataclass
class ModuleInfo:
    path: str
    functions: list[FunctionInfo] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)


# ============================================================
# BASIC HELPERS
# ============================================================

def esc(value: object) -> str:
    return html.escape(str(value or ""))


def compact_doc(doc: str, limit: int = 180) -> str:
    if not doc:
        return "No description documented yet."

    text = " ".join(doc.strip().split())

    if len(text) <= limit:
        return text

    return text[: limit - 1].rstrip() + "…"


def full_doc(doc: str) -> str:
    if not doc:
        return "No description documented yet."

    return doc.strip()


def expression_text(node: Optional[ast.AST]) -> str:
    if node is None:
        return ""

    try:
        return ast.unparse(node)
    except Exception:
        return "..."


def annotation_text(node: Optional[ast.AST]) -> str:
    return expression_text(node)


def relative_file(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def code_line(file: str, line: int) -> str:
    return f"{file}:{line}"


def short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def safe_call(command: list[str], cwd: Path) -> str:
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode != 0:
            return ""

        return result.stdout.strip()

    except Exception:
        return ""


def git_branch(root: Path) -> str:
    return safe_call(
        ["git", "branch", "--show-current"],
        root,
    )


def git_commit(root: Path) -> str:
    return safe_call(
        ["git", "rev-parse", "--short", "HEAD"],
        root,
    )


def git_log(root: Path, limit: int = 8) -> list[str]:
    output = safe_call(
        [
            "git",
            "log",
            f"-{limit}",
            "--pretty=format:%h|%ad|%s",
            "--date=short",
        ],
        root,
    )

    if not output:
        return []

    return output.splitlines()


# ============================================================
# AST HELPERS
# ============================================================

def node_doc(node: ast.AST) -> str:
    return ast.get_docstring(node, clean=True) or ""


def decorator_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id

    if isinstance(node, ast.Attribute):
        base = decorator_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr

    if isinstance(node, ast.Call):
        return decorator_name(node.func)

    return expression_text(node)


def decorator_text(node: ast.AST) -> str:
    return expression_text(node)


def decorators_for(node: ast.AST) -> list[str]:
    return [
        decorator_text(item)
        for item in getattr(node, "decorator_list", [])
    ]


def parameter_kind(
    name: str,
    default_node: Optional[ast.AST],
) -> str:
    if default_node is None:
        return ""

    text = expression_text(default_node)

    for kind in (
        "Query",
        "Path",
        "Body",
        "Header",
        "Cookie",
        "Form",
        "File",
        "Depends",
    ):
        if text.startswith(kind + "("):
            return kind

    return ""


def collect_parameters(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[Parameter]:
    args = node.args
    result: list[Parameter] = []

    positional = list(args.posonlyargs) + list(args.args)

    positional_defaults = [None] * (
        len(positional) - len(args.defaults)
    ) + list(args.defaults)

    for arg, default in zip(positional, positional_defaults):
        result.append(
            Parameter(
                name=arg.arg,
                annotation=annotation_text(arg.annotation),
                default=expression_text(default),
                kind=parameter_kind(arg.arg, default),
            )
        )

    if args.vararg:
        result.append(
            Parameter(
                name="*" + args.vararg.arg,
                annotation=annotation_text(args.vararg.annotation),
            )
        )

    for arg, default in zip(
        args.kwonlyargs,
        args.kw_defaults,
    ):
        result.append(
            Parameter(
                name=arg.arg,
                annotation=annotation_text(arg.annotation),
                default=expression_text(default),
                kind=parameter_kind(arg.arg, default),
            )
        )

    if args.kwarg:
        result.append(
            Parameter(
                name="**" + args.kwarg.arg,
                annotation=annotation_text(args.kwarg.annotation),
            )
        )

    return result


# ============================================================
# API ENDPOINT DETECTION
# ============================================================

HTTP_METHODS = {
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "options",
    "head",
    "trace",
}


def call_root_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Attribute):
        return node.func.attr.lower()

    if isinstance(node.func, ast.Name):
        return node.func.id.lower()

    return ""


def extract_string_argument(
    call: ast.Call,
    index: int = 0,
) -> str:
    if len(call.args) <= index:
        return ""

    node = call.args[index]

    if isinstance(node, ast.Constant):
        return str(node.value)

    return expression_text(node)


def extract_methods_keyword(call: ast.Call) -> list[str]:
    for keyword in call.keywords:
        if keyword.arg != "methods":
            continue

        value = keyword.value

        if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
            methods = []

            for item in value.elts:
                if isinstance(item, ast.Constant):
                    methods.append(str(item.value).upper())

            return methods

    return []


def endpoint_from_decorator(
    decorator: ast.AST,
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    file: str,
) -> Optional[EndpointInfo]:

    if not isinstance(decorator, ast.Call):
        return None

    if not isinstance(decorator.func, ast.Attribute):
        return None

    action = decorator.func.attr.lower()

    if action in HTTP_METHODS:
        path = extract_string_argument(decorator)

        return EndpointInfo(
            methods=[action.upper()],
            path=path or "/",
            file=file,
            line=function.lineno,
            function=function.name,
            params=collect_parameters(function),
            returns=annotation_text(function.returns),
            doc=node_doc(function),
            framework="FastAPI / Starlette / compatible",
            decorators=decorators_for(function),
        )

    if action == "api_route":
        path = extract_string_argument(decorator)
        methods = extract_methods_keyword(decorator)

        return EndpointInfo(
            methods=methods or ["ANY"],
            path=path or "/",
            file=file,
            line=function.lineno,
            function=function.name,
            params=collect_parameters(function),
            returns=annotation_text(function.returns),
            doc=node_doc(function),
            framework="FastAPI / Starlette / compatible",
            decorators=decorators_for(function),
        )

    if action == "route":
        path = extract_string_argument(decorator)
        methods = extract_methods_keyword(decorator)

        return EndpointInfo(
            methods=methods or ["GET"],
            path=path or "/",
            file=file,
            line=function.lineno,
            function=function.name,
            params=collect_parameters(function),
            returns=annotation_text(function.returns),
            doc=node_doc(function),
            framework="Flask / compatible",
            decorators=decorators_for(function),
        )

    if action == "websocket":
        path = extract_string_argument(decorator)

        return EndpointInfo(
            methods=["WS"],
            path=path or "/",
            file=file,
            line=function.lineno,
            function=function.name,
            params=collect_parameters(function),
            returns=annotation_text(function.returns),
            doc=node_doc(function),
            framework="WebSocket / compatible",
            decorators=decorators_for(function),
        )

    return None


# ============================================================
# PYTHON SCANNER
# ============================================================

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    ".astro",
}


class PythonScanner:
    def __init__(self, root: Path):
        self.root = root
        self.modules: list[ModuleInfo] = []
        self.functions: list[FunctionInfo] = []
        self.classes: list[ClassInfo] = []
        self.endpoints: list[EndpointInfo] = []
        self.imports: list[str] = []

    def scan(self) -> None:
        for path in sorted(self.root.rglob("*.py")):
            if any(part in SKIP_DIRS for part in path.parts):
                continue

            self.scan_file(path)

    def scan_file(self, path: Path) -> None:
        try:
            source = path.read_text(
                encoding="utf-8",
                errors="replace",
            )
            tree = ast.parse(source, filename=str(path))
        except Exception:
            return

        relative = relative_file(path, self.root)

        module = ModuleInfo(path=relative)

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function = self.make_function(
                    node,
                    relative,
                )

                module.functions.append(function)
                self.functions.append(function)

                self.find_endpoints(node, relative)

            elif isinstance(node, ast.ClassDef):
                class_info = self.make_class(
                    node,
                    relative,
                )

                module.classes.append(class_info)
                self.classes.append(class_info)

                for method in class_info.methods:
                    self.find_endpoints(
                        self.function_node_for_class_method(
                            node,
                            method.name,
                        ),
                        relative,
                    )

            elif isinstance(node, ast.Import):
                for alias in node.names:
                    module.imports.append(
                        alias.name
                    )

            elif isinstance(node, ast.ImportFrom):
                module.imports.append(
                    node.module or ""
                )

        self.modules.append(module)
        self.imports.extend(module.imports)

    def function_node_for_class_method(
        self,
        class_node: ast.ClassDef,
        method_name: str,
    ) -> Optional[ast.FunctionDef | ast.AsyncFunctionDef]:

        for node in class_node.body:
            if isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            ) and node.name == method_name:
                return node

        return None

    def make_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        file: str,
        class_name: str = "",
    ) -> FunctionInfo:

        return FunctionInfo(
            name=node.name,
            file=file,
            line=node.lineno,
            params=collect_parameters(node),
            returns=annotation_text(node.returns),
            doc=node_doc(node),
            decorators=decorators_for(node),
            class_name=class_name,
            is_method=bool(class_name),
        )

    def make_class(
        self,
        node: ast.ClassDef,
        file: str,
    ) -> ClassInfo:

        methods = []

        for child in node.body:
            if isinstance(
                child,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            ):
                methods.append(
                    self.make_function(
                        child,
                        file,
                        class_name=node.name,
                    )
                )

        return ClassInfo(
            name=node.name,
            file=file,
            line=node.lineno,
            doc=node_doc(node),
            decorators=decorators_for(node),
            methods=methods,
        )

    def find_endpoints(
        self,
        node: Optional[
            ast.FunctionDef |
            ast.AsyncFunctionDef
        ],
        file: str,
    ) -> None:

        if node is None:
            return

        for decorator in node.decorator_list:
            endpoint = endpoint_from_decorator(
                decorator,
                node,
                file,
            )

            if endpoint:
                self.endpoints.append(endpoint)


def scan_python(root: Path) -> PythonScanner:
    scanner = PythonScanner(root)
    scanner.scan()
    return scanner


# ============================================================
# DOCUMENTATION STATE
# ============================================================

def symbol_key(function: FunctionInfo) -> str:
    return f"function:{function.file}:{function.qualified_name}"


def class_key(item: ClassInfo) -> str:
    return f"class:{item.file}:{item.name}"


def endpoint_key(item: EndpointInfo) -> str:
    return (
        f"endpoint:{item.file}:"
        f"{item.function}:"
        f"{item.method_text}:"
        f"{item.path}"
    )


def function_fingerprint(item: FunctionInfo) -> str:
    raw = json.dumps(
        {
            "name": item.name,
            "signature": item.signature,
            "doc": item.doc,
            "decorators": item.decorators,
        },
        sort_keys=True,
    )

    return short_hash(raw)


def class_fingerprint(item: ClassInfo) -> str:
    raw = json.dumps(
        {
            "name": item.name,
            "doc": item.doc,
            "decorators": item.decorators,
            "methods": [
                function_fingerprint(method)
                for method in item.methods
            ],
        },
        sort_keys=True,
    )

    return short_hash(raw)


def endpoint_fingerprint(item: EndpointInfo) -> str:
    raw = json.dumps(
        {
            "methods": item.methods,
            "path": item.path,
            "function": item.function,
            "params": [
                {
                    "name": p.name,
                    "annotation": p.annotation,
                    "default": p.default,
                }
                for p in item.params
            ],
            "returns": item.returns,
            "doc": item.doc,
            "framework": item.framework,
            "decorators": item.decorators,
        },
        sort_keys=True,
    )

    return short_hash(raw)


def load_state(path: Path) -> dict:
    if not path.exists():
        return {
            "functions": {},
            "classes": {},
            "endpoints": {},
            "generation": 0,
            "initialized": False,
        }

    try:
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return {
            "functions": {},
            "classes": {},
            "endpoints": {},
            "generation": 0,
            "initialized": False,
        }


def apply_state(
    scanner: PythonScanner,
    previous: dict,
) -> dict:

    old_functions = previous.get("functions", {})
    old_classes = previous.get("classes", {})
    old_endpoints = previous.get("endpoints", {})

    for item in scanner.functions:
        key = symbol_key(item)
        fingerprint = function_fingerprint(item)

        if key not in old_functions:
            item.is_new = bool(previous.get("initialized"))
        elif old_functions[key] != fingerprint:
            item.is_changed = True

    for item in scanner.classes:
        key = class_key(item)
        fingerprint = class_fingerprint(item)

        if key not in old_classes:
            item.is_new = bool(previous.get("initialized"))
        elif old_classes[key] != fingerprint:
            item.is_changed = True

    for item in scanner.endpoints:
        key = endpoint_key(item)
        fingerprint = endpoint_fingerprint(item)

        if key not in old_endpoints:
            item.is_new = bool(previous.get("initialized"))
        elif old_endpoints[key] != fingerprint:
            item.is_changed = True

    return {
        "functions": {
            symbol_key(item): function_fingerprint(item)
            for item in scanner.functions
        },
        "classes": {
            class_key(item): class_fingerprint(item)
            for item in scanner.classes
        },
        "endpoints": {
            endpoint_key(item): endpoint_fingerprint(item)
            for item in scanner.endpoints
        },
        "generation": previous.get("generation", 0) + 1,
        "initialized": True,
    }


# ============================================================
# PROJECT CONFIG
# ============================================================

def load_project_config(root: Path) -> dict:
    path = root / "project.json"

    if not path.exists():
        return dict(PROJECT)

    try:
        data = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

        result = dict(PROJECT)
        result.update(data)

        return result

    except Exception:
        return dict(PROJECT)


def init_project(root: Path) -> None:
    path = root / "project.json"

    if path.exists():
        print("project.json already exists.")
        return

    path.write_text(
        json.dumps(
            PROJECT,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Created {path}")


# ============================================================
# SMALL HTML BUILDING BLOCKS
# ============================================================

def badge(
    text: str,
    kind: str = "",
) -> str:

    extra = f" badge-{kind}" if kind else ""

    return (
        f'<span class="badge{extra}">'
        f'{esc(text)}'
        f'</span>'
    )


def status_badges(
    is_new: bool,
    is_changed: bool,
) -> str:

    output = []

    if is_new:
        output.append(
            badge("NEW", "new")
        )

    if is_changed:
        output.append(
            badge("CHANGED", "changed")
        )

    return "".join(output)


def parameter_summary(
    params: list[Parameter],
) -> str:

    if not params:
        return "No parameters"

    return ", ".join(
        param.name
        for param in params
    )


def parameter_details(
    params: list[Parameter],
) -> str:

    if not params:
        return (
            '<div class="empty-detail">'
            'No parameters documented.'
            '</div>'
        )

    rows = []

    for param in params:
        kind = (
            badge(param.kind, "type")
            if param.kind
            else ""
        )

        annotation = (
            f"<code>{esc(param.annotation)}</code>"
            if param.annotation
            else ""
        )

        default = (
            f"<code>= {esc(param.default)}</code>"
            if param.default
            else ""
        )

        rows.append(
            f"""
            <div class="param-row">
              <div class="param-name">
                <code>{esc(param.name)}</code>
                {kind}
              </div>
              <div class="param-type">
                {annotation}
              </div>
              <div class="param-default">
                {default}
              </div>
            </div>
            """
        )

    return (
        '<div class="parameter-list">'
        + "".join(rows)
        + "</div>"
    )


# ============================================================
# COMPACT FUNCTION / METHOD ROWS
# ============================================================

def function_row(
    item: FunctionInfo,
    show_class: bool = False,
) -> str:

    search = " ".join(
        [
            item.name,
            item.qualified_name,
            item.file,
            item.doc,
            item.signature,
        ]
    ).lower()

    badges = status_badges(
        item.is_new,
        item.is_changed,
    )

    class_text = (
        f'<span class="symbol-parent">'
        f'{esc(item.class_name)}.'
        f'</span>'
        if show_class and item.class_name
        else ""
    )

    return f"""
    <details
      class="symbol-row method-row"
      data-search="{esc(search)}"
      data-new="{'true' if item.is_new else 'false'}"
    >
      <summary class="symbol-summary">
        <div class="symbol-main">
          {class_text}
          <span class="symbol-name">{esc(item.name)}</span>
        </div>

        <div class="symbol-description">
          {esc(compact_doc(item.doc, 130))}
        </div>

        <div class="symbol-badges">
          {badges}
        </div>

        <div class="symbol-line">
          {esc(item.file)}:{item.line}
        </div>
      </summary>

      <div class="symbol-details">

        <div class="detail-block">
          <div class="detail-label">WHAT IT DOES</div>
          <p>{esc(full_doc(item.doc))}</p>
        </div>

        <div class="detail-block">
          <div class="detail-label">SIGNATURE</div>
          <pre><code>{esc(item.signature)}</code></pre>
        </div>

        <div class="detail-block">
          <div class="detail-label">PARAMETERS</div>
          {parameter_details(item.params)}
        </div>

        <div class="detail-meta">

          <div>
            <span class="detail-label">RETURNS</span>
            <code>{esc(item.returns or "Not documented")}</code>
          </div>

          <div>
            <span class="detail-label">SOURCE</span>
            <code>{esc(code_line(item.file, item.line))}</code>
          </div>

        </div>

        {
            f'''
            <div class="detail-block">
              <div class="detail-label">DECORATORS</div>
              <div class="tag-list">
                {"".join(
                    f"<code>{esc(dec)}</code>"
                    for dec in item.decorators
                )}
              </div>
            </div>
            '''
            if item.decorators
            else ""
        }

      </div>
    </details>
    """


# ============================================================
# GROUPED METHOD DISPLAY
# ============================================================

def method_group(
    title: str,
    functions: list[FunctionInfo],
) -> str:

    if not functions:
        return ""

    new_count = sum(
        item.is_new
        for item in functions
    )

    changed_count = sum(
        item.is_changed
        for item in functions
    )

    status = ""

    if new_count:
        status += badge(
            f"{new_count} new",
            "new",
        )

    if changed_count:
        status += badge(
            f"{changed_count} changed",
            "changed",
        )

    return f"""
    <details class="symbol-group">
      <summary class="group-summary">

        <div class="group-title">
          {esc(title)}
        </div>

        <div class="group-count">
          {len(functions)} symbols
        </div>

        <div class="group-status">
          {status}
        </div>

      </summary>

      <div class="symbol-list">
        {"".join(
            function_row(item)
            for item in functions
        )}
      </div>

    </details>
    """


# ============================================================
# CLASS DISPLAY
# ============================================================

def class_group(
    item: ClassInfo,
) -> str:

    search = " ".join(
        [
            item.name,
            item.file,
            item.doc,
            *[
                method.name
                for method in item.methods
            ],
        ]
    ).lower()

    badges = status_badges(
        item.is_new,
        item.is_changed,
    )

    return f"""
    <details
      class="symbol-group class-group"
      data-search="{esc(search)}"
    >

      <summary class="group-summary">

        <div class="group-title">
          <span class="symbol-name">
            {esc(item.name)}
          </span>
        </div>

        <div class="group-description">
          {esc(compact_doc(item.doc, 120))}
        </div>

        <div class="group-count">
          {len(item.methods)} methods
        </div>

        <div class="group-status">
          {badges}
        </div>

      </summary>

      <div class="class-body">

        <div class="class-meta">
          <span>{esc(item.file)}:{item.line}</span>
        </div>

        <div class="class-description">
          {esc(full_doc(item.doc))}
        </div>

        <div class="class-methods">

          {
              "".join(
                  function_row(
                      method,
                      show_class=False,
                  )
                  for method in item.methods
              )
              if item.methods
              else
              '<div class="empty-detail">'
              'No methods discovered.'
              '</div>'
          }

        </div>

      </div>

    </details>
    """


# ============================================================
# ENDPOINT DISPLAY
# ============================================================

def endpoint_row(
    item: EndpointInfo,
) -> str:

    search = " ".join(
        [
            item.method_text,
            item.path,
            item.function,
            item.file,
            item.doc,
            item.framework,
        ]
    ).lower()

    badges = status_badges(
        item.is_new,
        item.is_changed,
    )

    method_badges = "".join(
        badge(method, "method")
        for method in item.methods
    )

    return f"""
    <details
      class="symbol-row endpoint-row"
      data-search="{esc(search)}"
      data-new="{'true' if item.is_new else 'false'}"
    >

      <summary class="symbol-summary endpoint-summary">

        <div class="endpoint-methods">
          {method_badges}
        </div>

        <div class="endpoint-path">
          <code>{esc(item.path)}</code>
        </div>

        <div class="symbol-description">
          {esc(item.function)}
          <span class="muted">
            — {esc(compact_doc(item.doc, 100))}
          </span>
        </div>

        <div class="symbol-badges">
          {badges}
        </div>

      </summary>

      <div class="symbol-details">

        <div class="detail-block">
          <div class="detail-label">WHAT IT DOES</div>
          <p>{esc(full_doc(item.doc))}</p>
        </div>

        <div class="detail-meta">

          <div>
            <span class="detail-label">HANDLER</span>
            <code>{esc(item.function)}</code>
          </div>

          <div>
            <span class="detail-label">FRAMEWORK</span>
            <code>{esc(item.framework)}</code>
          </div>

          <div>
            <span class="detail-label">SOURCE</span>
            <code>{esc(code_line(item.file, item.line))}</code>
          </div>

          <div>
            <span class="detail-label">RETURNS</span>
            <code>{esc(item.returns or "Not documented")}</code>
          </div>

        </div>

        <div class="detail-block">
          <div class="detail-label">PARAMETERS</div>
          {parameter_details(item.params)}
        </div>

        <div class="detail-block">
          <div class="detail-label">ROUTE DECORATORS</div>

          <div class="tag-list">
            {
                "".join(
                    f"<code>{esc(dec)}</code>"
                    for dec in item.decorators
                )
            }
          </div>

        </div>

      </div>

    </details>
    """


# ============================================================
# MODULE DISPLAY
# ============================================================

def module_row(
    module: ModuleInfo,
) -> str:

    total_symbols = (
        len(module.functions)
        + sum(
            len(item.methods)
            for item in module.classes
        )
        + len(module.classes)
    )

    return f"""
    <details class="module-row">

      <summary class="module-summary">

        <div class="module-name">
          {esc(module.path)}
        </div>

        <div class="module-count">
          {total_symbols} symbols
        </div>

        <div class="module-count">
          {len(module.imports)} imports
        </div>

      </summary>

      <div class="module-details">

        <div class="module-stats">

          <div>
            <span class="detail-label">FUNCTIONS</span>
            <strong>{len(module.functions)}</strong>
          </div>

          <div>
            <span class="detail-label">CLASSES</span>
            <strong>{len(module.classes)}</strong>
          </div>

          <div>
            <span class="detail-label">IMPORTS</span>
            <strong>{len(module.imports)}</strong>
          </div>

        </div>

        {
            f'''
            <div class="detail-block">
              <div class="detail-label">IMPORTS</div>
              <div class="tag-list">
                {"".join(
                    f"<code>{esc(item)}</code>"
                    for item in module.imports
                )}
              </div>
            </div>
            '''
            if module.imports
            else ""
        }

      </div>

    </details>
    """


# ============================================================
# SECTION HELPERS
# ============================================================

def section(
    number: str,
    title: str,
    description: str,
    body: str,
) -> str:

    return f"""
    <section class="section" id="section-{number}">

      <div class="section-head">

        <div class="section-number">
          {esc(number)}
        </div>

        <div>
          <div class="eyebrow">
            BARKLY DOCS
          </div>

          <h2 class="section-title">
            {esc(title)}
          </h2>

          <p class="section-copy">
            {esc(description)}
          </p>
        </div>

      </div>

      <div class="section-body">
        {body}
      </div>

    </section>
    """


def info_card(
    title: str,
    value: str,
    description: str = "",
) -> str:

    return f"""
    <article class="info-card">

      <div class="card-label">
        {esc(title)}
      </div>

      <div class="card-value">
        {esc(value)}
      </div>

      {
          f'<div class="card-description">{esc(description)}</div>'
          if description
          else ""
      }

    </article>
    """


def simple_card_grid(
    values: list[str],
) -> str:

    return (
        '<div class="card-grid">'
        + "".join(
            info_card(
                str(index + 1).zfill(2),
                value,
            )
            for index, value in enumerate(values)
        )
        + "</div>"
    )


def search_toolbar(
    input_id: str,
    count_id: str,
    new_id: str,
    placeholder: str,
) -> str:

    return f"""
    <div class="search-toolbar">

      <label class="search-box">

        <span>⌕</span>

        <input
          id="{esc(input_id)}"
          type="search"
          placeholder="{esc(placeholder)}"
          autocomplete="off"
        />

      </label>

      <label class="new-toggle">
        <input
          id="{esc(new_id)}"
          type="checkbox"
        />
        <span>NEW ONLY</span>
      </label>

      <div
        id="{esc(count_id)}"
        class="result-count"
      >
        0
      </div>

    </div>
    """


# ============================================================
# FULL HTML DOCUMENT
# ============================================================

def build_html(
    project: dict,
    scanner: PythonScanner,
    state: dict,
    root: Path,
) -> str:

    generation = state.get(
        "generation",
        1,
    )

    branch = git_branch(root)
    commit = git_commit(root)
    logs = git_log(root)

    new_functions = sum(
        item.is_new
        for item in scanner.functions
    )

    changed_functions = sum(
        item.is_changed
        for item in scanner.functions
    )

    new_classes = sum(
        item.is_new
        for item in scanner.classes
    )

    changed_classes = sum(
        item.is_changed
        for item in scanner.classes
    )

    new_endpoints = sum(
        item.is_new
        for item in scanner.endpoints
    )

    changed_endpoints = sum(
        item.is_changed
        for item in scanner.endpoints
    )

    # --------------------------------------------------------
    # 01 PROJECT
    # --------------------------------------------------------

    project_body = f"""
    <div class="hero-card">

      <div class="hero-kicker">
        PROJECT DOCUMENTATION
      </div>

      <h1>
        {esc(project.get("name", "Project"))}
      </h1>

      <p>
        {esc(project.get("description", ""))}
      </p>

    </div>

    <div class="card-grid">

      {info_card(
          "TYPE",
          project.get("type", ""),
      )}

      {info_card(
          "STATUS",
          project.get("status", ""),
      )}

      {info_card(
          "PYTHON FILES",
          str(len(scanner.modules)),
      )}

      {info_card(
          "GENERATION",
          f"#{generation}",
      )}

    </div>
    """

    # --------------------------------------------------------
    # 02 PRINCIPLES
    # --------------------------------------------------------

    principles_body = simple_card_grid(
        project.get(
            "principles",
            [],
        )
    )

    # --------------------------------------------------------
    # 03 COMPONENTS
    # --------------------------------------------------------

    components_body = simple_card_grid(
        project.get(
            "components",
            [],
        )
    )

    # --------------------------------------------------------
    # 04 API ENDPOINTS
    # --------------------------------------------------------

    endpoint_groups = {}

    for endpoint in scanner.endpoints:
        endpoint_groups.setdefault(
            endpoint.file,
            [],
        ).append(endpoint)

    endpoint_body = search_toolbar(
        "endpoint-search",
        "endpoint-count",
        "endpoint-new-only",
        "Find an endpoint, path, handler, or file…",
    )

    endpoint_body += (
        '<div id="endpoint-results" class="symbol-groups">'
    )

    for file, endpoints in endpoint_groups.items():
        endpoint_body += f"""
        <details class="symbol-group">

          <summary class="group-summary">

            <div class="group-title">
              {esc(file)}
            </div>

            <div class="group-count">
              {len(endpoints)} endpoints
            </div>

          </summary>

          <div class="symbol-list">
            {"".join(
                endpoint_row(item)
                for item in endpoints
            )}
          </div>

        </details>
        """

    if not scanner.endpoints:
        endpoint_body += """
        <div class="empty-state">
          No API endpoints were discovered.
        </div>
        """

    endpoint_body += "</div>"

    # --------------------------------------------------------
    # 05 FUNCTIONS & METHODS
    # --------------------------------------------------------

    function_groups = {}

    for function in scanner.functions:
        if function.is_method:
            continue

        function_groups.setdefault(
            function.file,
            [],
        ).append(function)

    method_groups = {}

    for class_info in scanner.classes:
        for method in class_info.methods:
            key = f"{class_info.file} · {class_info.name}"

            method_groups.setdefault(
                key,
                [],
            ).append(method)

    function_body = search_toolbar(
        "function-search",
        "function-count",
        "function-new-only",
        "Find a function, method, class, or file…",
    )

    function_body += (
        '<div id="function-results" class="symbol-groups">'
    )

    for file, functions in function_groups.items():
        function_body += method_group(
            file,
            functions,
        )

    for title, methods in method_groups.items():
        function_body += method_group(
            title,
            methods,
        )

    if not scanner.functions:
        function_body += """
        <div class="empty-state">
          No Python functions or methods were discovered.
        </div>
        """

    function_body += "</div>"

    # --------------------------------------------------------
    # 06 CLASSES
    # --------------------------------------------------------

    class_body = search_toolbar(
        "class-search",
        "class-count",
        "class-new-only",
        "Find a class, method, or file…",
    )

    class_body += (
        '<div id="class-results" class="symbol-groups">'
    )

    for item in scanner.classes:
        class_body += class_group(item)

    if not scanner.classes:
        class_body += """
        <div class="empty-state">
          No Python classes were discovered.
        </div>
        """

    class_body += "</div>"

    # --------------------------------------------------------
    # 07 MODULES
    # --------------------------------------------------------

    module_body = (
        '<div class="module-list">'
        + "".join(
            module_row(module)
            for module in scanner.modules
        )
        + "</div>"
    )

    # --------------------------------------------------------
    # 08 IMPORTS
    # --------------------------------------------------------

    unique_imports = sorted(
        set(
            item
            for item in scanner.imports
            if item
        )
    )

    imports_body = f"""
    <div class="import-summary">

      <div>
        <span class="detail-label">DISCOVERED</span>
        <strong>{len(unique_imports)}</strong>
      </div>

      <div>
        <span class="detail-label">SOURCE FILES</span>
        <strong>{len(scanner.modules)}</strong>
      </div>

    </div>

    <div class="tag-list import-list">

      {
          "".join(
              f"<code>{esc(item)}</code>"
              for item in unique_imports
          )
      }

    </div>
    """

    # --------------------------------------------------------
    # 09 LIFECYCLE
    # --------------------------------------------------------

    lifecycle_body = f"""
    <div class="lifecycle">

      {
          "".join(
              f'''
              <div class="lifecycle-step">

                <div class="lifecycle-number">
                  {str(index + 1).zfill(2)}
                </div>

                <div class="lifecycle-name">
                  {esc(item)}
                </div>

              </div>
              '''
              for index, item in enumerate(
                  project.get(
                      "lifecycle",
                      [],
                  )
              )
          )
      }

    </div>
    """

    # --------------------------------------------------------
    # 10 GIT
    # --------------------------------------------------------

    git_body = f"""
    <div class="card-grid">

      {info_card(
          "BRANCH",
          branch or "Unavailable",
      )}

      {info_card(
          "COMMIT",
          commit or "Unavailable",
      )}

      {info_card(
          "NEW FUNCTIONS",
          str(new_functions),
      )}

      {info_card(
          "CHANGED FUNCTIONS",
          str(changed_functions),
      )}

      {info_card(
          "NEW CLASSES",
          str(new_classes),
      )}

      {info_card(
          "CHANGED CLASSES",
          str(changed_classes),
      )}

      {info_card(
          "NEW ENDPOINTS",
          str(new_endpoints),
      )}

      {info_card(
          "CHANGED ENDPOINTS",
          str(changed_endpoints),
      )}

    </div>

    <div class="git-log">

      <div class="detail-label">
        RECENT COMMITS
      </div>

      {
          "".join(
              f'''
              <div class="git-row">
                <code>{esc(line)}</code>
              </div>
              '''
              for line in logs
          )
          if logs
          else
          '<div class="empty-state">'
          'No Git history available.'
          '</div>'
      }

    </div>
    """

    # --------------------------------------------------------
    # 11 CHANGELOG
    # --------------------------------------------------------

    changelog_body = f"""
    <div class="changelog-grid">

      {info_card(
          "DOCUMENTATION RUN",
          f"#{generation}",
          "Persistent documentation snapshot.",
      )}

      {info_card(
          "NEW FUNCTIONS",
          str(new_functions),
          "Detected since the previous documentation run.",
      )}

      {info_card(
          "CHANGED FUNCTIONS",
          str(changed_functions),
          "Signatures, decorators, or documentation changed.",
      )}

      {info_card(
          "NEW CLASSES",
          str(new_classes),
          "Detected since the previous documentation run.",
      )}

      {info_card(
          "NEW ENDPOINTS",
          str(new_endpoints),
          "Detected since the previous documentation run.",
      )}

    </div>

    <div class="note-card">

      <strong>
        How change detection works
      </strong>

      <p>
        BARKLY DOCS stores a small local snapshot of discovered
        symbols and compares the next scan against it. The scanner
        uses static Python AST analysis and never imports or executes
        the project.
      </p>

      <p>
        On the first generation, the existing project becomes the
        baseline. Later generations can identify newly discovered
        and changed functions, methods, classes, and API endpoints.
      </p>

    </div>
    """

    # --------------------------------------------------------
    # FINAL PAGE
    # --------------------------------------------------------

    return f"""<!DOCTYPE html>
<html lang="en">

<head>

  <meta charset="UTF-8" />

  <meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
  />

  <title>
    {esc(project.get("name", "Project"))}
    · BARKLY DOCS
  </title>

  <style>

    :root {{
      --bg: #080808;
      --panel: #101010;
      --panel-2: #151515;
      --line: #262626;
      --line-soft: #1d1d1d;
      --text: #f2f2f2;
      --muted: #9a9a9a;
      --dim: #666;
      --accent: #ff6b9d;
      --accent-soft: rgba(255, 107, 157, 0.12);
      --green: #7dffb2;
      --yellow: #ffd76b;
      --radius: 16px;
    }}

    * {{
      box-sizing: border-box;
    }}

    html {{
      scroll-behavior: smooth;
    }}

    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family:
        Inter,
        ui-sans-serif,
        system-ui,
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;
      line-height: 1.6;
    }}

    a {{
      color: inherit;
      text-decoration: none;
    }}

    code,
    pre,
    .eyebrow,
    .section-number,
    .symbol-name,
    .endpoint-path,
    .module-name {{
      font-family:
        "SFMono-Regular",
        Consolas,
        "Liberation Mono",
        monospace;
    }}

    code {{
      color: #e8e8e8;
      background: #0b0b0b;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 2px 6px;
      font-size: 0.88em;
    }}

    .topbar {{
      position: sticky;
      top: 0;
      z-index: 20;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
      min-height: 68px;
      padding: 0 28px;
      background: rgba(8, 8, 8, 0.92);
      border-bottom: 1px solid var(--line);
      backdrop-filter: blur(18px);
    }}

    .brand {{
      display: flex;
      align-items: center;
      gap: 12px;
      font-weight: 800;
      letter-spacing: -0.03em;
    }}

    .brand-paw {{
      width: 30px;
      height: 30px;
      display: grid;
      place-items: center;
      color: var(--accent);
    }}

    .brand-paw svg {{
      width: 100%;
      height: 100%;
      fill: currentColor;
    }}

    .brand small {{
      display: block;
      color: var(--muted);
      font-family: monospace;
      font-size: 10px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
    }}

    .nav {{
      display: flex;
      gap: 6px;
      overflow-x: auto;
    }}

    .nav a {{
      padding: 8px 10px;
      color: var(--muted);
      border-radius: 8px;
      font-family: monospace;
      font-size: 11px;
      white-space: nowrap;
    }}

    .nav a:hover {{
      color: var(--text);
      background: var(--panel-2);
    }}

    .page {{
      width: min(1320px, calc(100% - 36px));
      margin: 0 auto;
    }}

    .hero {{
      padding: 100px 0 70px;
    }}

    .hero-kicker,
    .eyebrow {{
      color: var(--accent);
      font-family: monospace;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.16em;
      text-transform: uppercase;
    }}

    .hero h1 {{
      max-width: 1000px;
      margin: 14px 0 18px;
      font-size: clamp(48px, 8vw, 104px);
      line-height: 0.92;
      letter-spacing: -0.07em;
    }}

    .hero p {{
      max-width: 760px;
      margin: 0;
      color: var(--muted);
      font-size: clamp(17px, 2vw, 22px);
    }}

    .hero-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 28px;
    }}

    .meta-pill {{
      padding: 7px 10px;
      border: 1px solid var(--line);
      border-radius: 999px;
      color: var(--muted);
      font-family: monospace;
      font-size: 11px;
    }}

    .section {{
      padding: 90px 0;
      border-top: 1px solid var(--line-soft);
    }}

    .section-head {{
      display: grid;
      grid-template-columns: 70px minmax(0, 1fr);
      gap: 20px;
      margin-bottom: 32px;
    }}

    .section-number {{
      color: var(--accent);
      font-size: 14px;
      font-weight: 700;
      padding-top: 5px;
    }}

    .section-title {{
      margin: 4px 0 8px;
      font-size: clamp(30px, 5vw, 54px);
      line-height: 1;
      letter-spacing: -0.05em;
    }}

    .section-copy {{
      max-width: 760px;
      margin: 0;
      color: var(--muted);
    }}

    .section-body {{
      min-width: 0;
    }}

    .hero-card {{
      padding: 32px;
      margin-bottom: 18px;
      background:
        linear-gradient(
          135deg,
          var(--accent-soft),
          transparent 55%
        ),
        var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
    }}

    .hero-card h1 {{
      margin: 10px 0;
      font-size: clamp(32px, 6vw, 68px);
      line-height: 0.95;
      letter-spacing: -0.06em;
    }}

    .hero-card p {{
      max-width: 760px;
      margin: 0;
      color: var(--muted);
    }}

    .card-grid {{
      display: grid;
      grid-template-columns:
        repeat(auto-fit, minmax(190px, 1fr));
      gap: 10px;
    }}

    .info-card {{
      min-width: 0;
      padding: 18px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
    }}

    .card-label,
    .detail-label {{
      margin-bottom: 6px;
      color: var(--dim);
      font-family: monospace;
      font-size: 9px;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }}

    .card-value {{
      color: var(--text);
      font-size: 18px;
      font-weight: 700;
    }}

    .card-description {{
      margin-top: 5px;
      color: var(--muted);
      font-size: 12px;
    }}

    /* ------------------------------------------------------
       SEARCH
    ------------------------------------------------------ */

    .search-toolbar {{
      position: sticky;
      top: 68px;
      z-index: 10;
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 12px;
      padding: 10px;
      background: rgba(8, 8, 8, 0.94);
      border: 1px solid var(--line);
      border-radius: 12px;
      backdrop-filter: blur(14px);
    }}

    .search-box {{
      flex: 1;
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 0;
      padding: 0 10px;
      color: var(--dim);
    }}

    .search-box input {{
      width: 100%;
      min-width: 0;
      padding: 9px 0;
      border: 0;
      outline: 0;
      background: transparent;
      color: var(--text);
      font: inherit;
    }}

    .search-box input::placeholder {{
      color: var(--dim);
    }}

    .new-toggle {{
      display: flex;
      align-items: center;
      gap: 7px;
      padding: 7px 10px;
      color: var(--muted);
      font-family: monospace;
      font-size: 10px;
      white-space: nowrap;
    }}

    .new-toggle input {{
      accent-color: var(--accent);
    }}

    .result-count {{
      min-width: 36px;
      padding: 6px 8px;
      color: var(--muted);
      background: var(--panel-2);
      border-radius: 7px;
      font-family: monospace;
      font-size: 10px;
      text-align: center;
    }}

    /* ------------------------------------------------------
       COLLAPSIBLE SYMBOL SYSTEM
    ------------------------------------------------------ */

    .symbol-groups {{
      display: grid;
      gap: 6px;
    }}

    .symbol-group,
    .module-row {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 11px;
      overflow: hidden;
    }}

    .group-summary,
    .module-summary {{
      display: grid;
      grid-template-columns:
        minmax(180px, 1.1fr)
        minmax(180px, 2fr)
        auto
        auto;
      align-items: center;
      gap: 16px;
      min-height: 58px;
      padding: 10px 14px;
      cursor: pointer;
      list-style: none;
    }}

    .group-summary::-webkit-details-marker,
    .module-summary::-webkit-details-marker,
    .symbol-summary::-webkit-details-marker {{
      display: none;
    }}

    .group-summary::before,
    .module-summary::before,
    .symbol-summary::before {{
      content: "›";
      display: inline-block;
      position: absolute;
      transform: translateX(-10px);
      color: var(--dim);
      transition: transform 0.15s ease;
    }}

    details[open] > .group-summary::before,
    details[open] > .module-summary::before,
    details[open] > .symbol-summary::before {{
      transform: translateX(-10px) rotate(90deg);
    }}

    .group-title {{
      min-width: 0;
      font-weight: 700;
    }}

    .group-description,
    .symbol-description {{
      min-width: 0;
      overflow: hidden;
      color: var(--muted);
      font-size: 12px;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}

    .group-count,
    .module-count,
    .symbol-line {{
      color: var(--dim);
      font-family: monospace;
      font-size: 10px;
      white-space: nowrap;
    }}

    .group-status,
    .symbol-badges {{
      display: flex;
      justify-content: flex-end;
      flex-wrap: wrap;
      gap: 4px;
    }}

    .symbol-list {{
      border-top: 1px solid var(--line-soft);
    }}

    .symbol-row {{
      border-bottom: 1px solid var(--line-soft);
    }}

    .symbol-row:last-child {{
      border-bottom: 0;
    }}

    .symbol-summary {{
      position: relative;
      display: grid;
      grid-template-columns:
        minmax(180px, 1fr)
        minmax(220px, 2fr)
        auto
        minmax(90px, auto);
      align-items: center;
      gap: 14px;
      padding: 10px 14px 10px 28px;
      cursor: pointer;
      list-style: none;
    }}

    .symbol-main {{
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}

    .symbol-name {{
      font-size: 12px;
      color: var(--text);
    }}

    .symbol-parent {{
      color: var(--dim);
      font-family: monospace;
      font-size: 11px;
    }}

    .symbol-details {{
      display: grid;
      gap: 18px;
      padding: 18px 22px 22px 30px;
      background: #0c0c0c;
      border-top: 1px solid var(--line-soft);
    }}

    .detail-block p {{
      margin: 0;
      max-width: 900px;
      color: var(--muted);
      font-size: 13px;
    }}

    .detail-block pre {{
      margin: 0;
      overflow-x: auto;
      padding: 12px;
      background: #070707;
      border: 1px solid var(--line);
      border-radius: 8px;
    }}

    .detail-block pre code {{
      padding: 0;
      border: 0;
      background: transparent;
    }}

    .detail-meta {{
      display: grid;
      grid-template-columns:
        repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
    }}

    .detail-meta > div {{
      min-width: 0;
    }}

    .detail-meta code {{
      display: block;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}

    .parameter-list {{
      display: grid;
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }}

    .param-row {{
      display: grid;
      grid-template-columns:
        minmax(120px, 1fr)
        minmax(120px, 1fr)
        minmax(100px, 1fr);
      gap: 10px;
      padding: 9px 10px;
      background: #0a0a0a;
      border-bottom: 1px solid var(--line-soft);
      font-size: 11px;
    }}

    .param-row:last-child {{
      border-bottom: 0;
    }}

    .param-name {{
      display: flex;
      align-items: center;
      gap: 5px;
    }}

    .param-type,
    .param-default {{
      min-width: 0;
      color: var(--muted);
      overflow: hidden;
      text-overflow: ellipsis;
    }}

    .tag-list {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }}

    .tag-list code {{
      font-size: 10px;
    }}

    .empty-detail,
    .empty-state {{
      padding: 18px;
      color: var(--dim);
      font-family: monospace;
      font-size: 11px;
    }}

    /* ------------------------------------------------------
       BADGES
    ------------------------------------------------------ */

    .badge {{
      display: inline-flex;
      align-items: center;
      width: fit-content;
      padding: 3px 6px;
      border: 1px solid var(--line);
      border-radius: 5px;
      color: var(--muted);
      font-family: monospace;
      font-size: 8px;
      font-weight: 700;
      letter-spacing: 0.04em;
      white-space: nowrap;
    }}

    .badge-new {{
      color: var(--green);
      border-color: rgba(125, 255, 178, 0.3);
      background: rgba(125, 255, 178, 0.06);
    }}

    .badge-changed {{
      color: var(--yellow);
      border-color: rgba(255, 215, 107, 0.3);
      background: rgba(255, 215, 107, 0.06);
    }}

    .badge-method {{
      color: var(--accent);
      border-color: rgba(255, 107, 157, 0.3);
      background: rgba(255, 107, 157, 0.05);
    }}

    .badge-type {{
      color: var(--muted);
      font-size: 7px;
    }}

    .muted {{
      color: var(--dim);
    }}

    /* ------------------------------------------------------
       CLASSES
    ------------------------------------------------------ */

    .class-body {{
      padding: 16px 20px 20px;
      border-top: 1px solid var(--line-soft);
    }}

    .class-meta {{
      margin-bottom: 10px;
      color: var(--dim);
      font-family: monospace;
      font-size: 10px;
    }}

    .class-description {{
      max-width: 850px;
      margin-bottom: 16px;
      color: var(--muted);
      font-size: 12px;
    }}

    .class-methods {{
      display: grid;
      gap: 4px;
    }}

    /* ------------------------------------------------------
       MODULES
    ------------------------------------------------------ */

    .module-list {{
      display: grid;
      gap: 6px;
    }}

    .module-summary {{
      grid-template-columns:
        minmax(0, 1fr)
        auto
        auto;
      padding-left: 28px;
      position: relative;
    }}

    .module-name {{
      overflow: hidden;
      color: var(--text);
      font-size: 12px;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}

    .module-details {{
      display: grid;
      gap: 18px;
      padding: 18px 22px;
      border-top: 1px solid var(--line-soft);
      background: #0c0c0c;
    }}

    .module-stats {{
      display: flex;
      flex-wrap: wrap;
      gap: 28px;
    }}

    .module-stats strong {{
      display: block;
      font-size: 18px;
    }}

    /* ------------------------------------------------------
       IMPORTS
    ------------------------------------------------------ */

    .import-summary {{
      display: flex;
      flex-wrap: wrap;
      gap: 40px;
      margin-bottom: 20px;
    }}

    .import-summary strong {{
      display: block;
      font-size: 24px;
    }}

    .import-list {{
      padding: 16px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
    }}

    /* ------------------------------------------------------
       LIFECYCLE
    ------------------------------------------------------ */

    .lifecycle {{
      display: grid;
      grid-template-columns:
        repeat(auto-fit, minmax(180px, 1fr));
      gap: 8px;
    }}

    .lifecycle-step {{
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 13px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 10px;
    }}

    .lifecycle-number {{
      color: var(--accent);
      font-family: monospace;
      font-size: 10px;
    }}

    .lifecycle-name {{
      font-size: 12px;
      font-weight: 600;
    }}

    /* ------------------------------------------------------
       GIT / CHANGELOG
    ------------------------------------------------------ */

    .git-log {{
      margin-top: 18px;
      padding: 18px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
    }}

    .git-row {{
      padding: 8px 0;
      border-bottom: 1px solid var(--line-soft);
      color: var(--muted);
      overflow-x: auto;
    }}

    .git-row:last-child {{
      border-bottom: 0;
    }}

    .changelog-grid {{
      display: grid;
      grid-template-columns:
        repeat(auto-fit, minmax(210px, 1fr));
      gap: 10px;
      margin-bottom: 18px;
    }}

    .note-card {{
      padding: 20px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
    }}

    .note-card p {{
      max-width: 800px;
      margin: 8px 0 0;
      color: var(--muted);
      font-size: 13px;
    }}

    /* ------------------------------------------------------
       FOOTER
    ------------------------------------------------------ */

    footer {{
      padding: 60px 0 80px;
      border-top: 1px solid var(--line);
      color: var(--dim);
      font-family: monospace;
      font-size: 10px;
    }}

    footer strong {{
      color: var(--text);
    }}

    /* ------------------------------------------------------
       RESPONSIVE
    ------------------------------------------------------ */

    @media (max-width: 900px) {{

      .topbar {{
        padding: 0 16px;
      }}

      .nav {{
        display: none;
      }}

      .page {{
        width: min(100% - 24px, 1320px);
      }}

      .hero {{
        padding-top: 70px;
      }}

      .section {{
        padding: 64px 0;
      }}

      .section-head {{
        grid-template-columns: 1fr;
        gap: 8px;
      }}

      .group-summary,
      .symbol-summary {{
        grid-template-columns: 1fr auto;
      }}

      .group-description,
      .symbol-description {{
        grid-column: 1 / -1;
        white-space: normal;
      }}

      .symbol-line {{
        display: none;
      }}

      .param-row {{
        grid-template-columns: 1fr;
      }}

      .search-toolbar {{
        top: 68px;
      }}

    }}

    @media (max-width: 560px) {{

      .search-toolbar {{
        align-items: stretch;
        flex-wrap: wrap;
      }}

      .search-box {{
        flex-basis: 100%;
      }}

      .hero-card {{
        padding: 22px;
      }}

      .group-summary,
      .module-summary,
      .symbol-summary {{
        padding-left: 24px;
      }}

      .symbol-details {{
        padding-left: 18px;
        padding-right: 18px;
      }}

    }}

  </style>

</head>

<body>

  <header class="topbar">

    <a class="brand" href="#top">

      <span class="brand-paw">
        {PAW_SVG}
      </span>

      <span>
        BARKLY DOCS
        <small>
          human-readable engineering reference
        </small>
      </span>

    </a>

    <nav class="nav">

      <a href="#section-01">01</a>
      <a href="#section-02">02</a>
      <a href="#section-03">03</a>
      <a href="#section-04">04</a>
      <a href="#section-05">05</a>
      <a href="#section-06">06</a>
      <a href="#section-07">07</a>
      <a href="#section-08">08</a>
      <a href="#section-09">09</a>
      <a href="#section-10">10</a>
      <a href="#section-11">11</a>

    </nav>

  </header>

  <main id="top" class="page">

    <div class="hero">

      <div class="hero-kicker">
        BARKLY LABS · AUTOMATED DOCUMENTATION
      </div>

      <h1>
        {esc(project.get("name", "Project"))}
      </h1>

      <p>
        {esc(project.get("description", ""))}
      </p>

      <div class="hero-meta">

        <span class="meta-pill">
          generation #{generation}
        </span>

        <span class="meta-pill">
          {len(scanner.modules)} python files
        </span>

        <span class="meta-pill">
          {len(scanner.functions)} functions
        </span>

        <span class="meta-pill">
          {len(scanner.classes)} classes
        </span>

        <span class="meta-pill">
          {len(scanner.endpoints)} endpoints
        </span>

      </div>

    </div>

    {section(
        "01",
        "Project",
        "The smallest useful picture of what this project is.",
        project_body,
    )}

    {section(
        "02",
        "Principles",
        "The rules and design principles the project is built around.",
        principles_body,
    )}

    {section(
        "03",
        "Components",
        "The major systems and pieces that make up the project.",
        components_body,
    )}

    {section(
        "04",
        "API Endpoints",
        "Every discovered route is compact by default and expandable when you need its technical details.",
        endpoint_body,
    )}

    {section(
        "05",
        "Functions & Methods",
        "Searchable, grouped symbols with details hidden until requested.",
        function_body,
    )}

    {section(
        "06",
        "Classes",
        "Classes stay collapsed so large projects remain readable.",
        class_body,
    )}

    {section(
        "07",
        "Modules",
        "A lightweight map of source files and their discovered contents.",
        module_body,
    )}

    {section(
        "08",
        "Imports",
        "Dependencies discovered from Python import statements.",
        imports_body,
    )}

    {section(
        "09",
        "Lifecycle",
        "The development path used by the project.",
        lifecycle_body,
    )}

    {section(
        "10",
        "Git",
        "Repository state and recent development history.",
        git_body,
    )}

    {section(
        "11",
        "Changelog",
        "What BARKLY DOCS noticed changed between documentation generations.",
        changelog_body,
    )}

    <footer>

      <strong>
        BARKLY DOCS
      </strong>

      · Generated automatically.

      <br />

      Built around a simple rule:
      <strong>
        don't make the human process information they didn't ask for yet.
      </strong>

    </footer>

  </main>


  <script>

    function bindSymbolFilter(
      inputId,
      resultsId,
      countId,
      newOnlyId
    ) {{

      const input =
        document.getElementById(inputId);

      const results =
        document.getElementById(resultsId);

      const count =
        document.getElementById(countId);

      const newOnly =
        document.getElementById(newOnlyId);

      if (
        !input ||
        !results ||
        !count ||
        !newOnly
      ) {{
        return;
      }}

      function update() {{

        const query =
          input.value
            .trim()
            .toLowerCase();

        const onlyNew =
          newOnly.checked;

        const rows =
          results.querySelectorAll(
            "[data-search]"
          );

        let visible = 0;

        rows.forEach((row) => {{

          const text =
            row
              .getAttribute("data-search")
              .toLowerCase();

          const isNew =
            row.getAttribute("data-new")
            === "true";

          const matchesText =
            !query ||
            text.includes(query);

          const matchesNew =
            !onlyNew ||
            isNew;

          const matches =
            matchesText &&
            matchesNew;

          row.style.display =
            matches
              ? ""
              : "none";

          if (matches) {{
            visible++;

            if (query) {{
              const parent =
                row.closest("details");

              if (parent) {{
                parent.open = true;
              }}
            }}
          }}

        }});

        count.textContent =
          String(visible);

      }}

      input.addEventListener(
        "input",
        update
      );

      newOnly.addEventListener(
        "change",
        update
      );

      update();
    }}


    bindSymbolFilter(
      "endpoint-search",
      "endpoint-results",
      "endpoint-count",
      "endpoint-new-only"
    );


    bindSymbolFilter(
      "function-search",
      "function-results",
      "function-count",
      "function-new-only"
    );


    bindSymbolFilter(
      "class-search",
      "class-results",
      "class-count",
      "class-new-only"
    );

  </script>

</body>

</html>
"""


# ============================================================
# GENERATE
# ============================================================

def generate(
    source: Path,
    output: Path,
    name: Optional[str] = None,
    project_type: Optional[str] = None,
    status: Optional[str] = None,
) -> None:

    source = source.resolve()
    output = output.resolve()

    project = load_project_config(source)

    if name:
        project["name"] = name

    if project_type:
        project["type"] = project_type

    if status:
        project["status"] = status

    scanner = scan_python(source)

    state_path = source / STATE_FILE
    previous_state = load_state(state_path)

    next_state = apply_state(
        scanner,
        previous_state,
    )

    output.mkdir(
        parents=True,
        exist_ok=True,
    )

    html_text = build_html(
        project,
        scanner,
        next_state,
        source,
    )

    output_file = output / "index.html"

    output_file.write_text(
        html_text,
        encoding="utf-8",
    )

    state_path.write_text(
        json.dumps(
            next_state,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    print()
    print("BARKLY DOCS")
    print("-----------")
    print(f"Project:    {project['name']}")
    print(f"Source:     {source}")
    print(f"Output:     {output_file}")
    print()
    print(f"Python files: {len(scanner.modules)}")
    print(f"Functions:    {len(scanner.functions)}")
    print(f"Classes:      {len(scanner.classes)}")
    print(f"Endpoints:    {len(scanner.endpoints)}")
    print()
    print(
        f"New:     "
        f"{sum(x.is_new for x in scanner.functions)} functions, "
        f"{sum(x.is_new for x in scanner.classes)} classes, "
        f"{sum(x.is_new for x in scanner.endpoints)} endpoints"
    )
    print(
        f"Changed: "
        f"{sum(x.is_changed for x in scanner.functions)} functions, "
        f"{sum(x.is_changed for x in scanner.classes)} classes, "
        f"{sum(x.is_changed for x in scanner.endpoints)} endpoints"
    )
    print()
    print("Documentation generated successfully.")


# ============================================================
# CLI
# ============================================================

def build_parser() -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(
        description=(
            "BARKLY DOCS — human-readable "
            "automatic project documentation."
        )
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    init_parser = subparsers.add_parser(
        "init",
        help="Create project.json.",
    )

    init_parser.add_argument(
        "--source",
        default=".",
        help="Project directory.",
    )

    generate_parser = subparsers.add_parser(
        "generate",
        help="Generate documentation.",
    )

    generate_parser.add_argument(
        "--source",
        default=".",
        help="Project source directory.",
    )

    generate_parser.add_argument(
        "--output",
        default="docs",
        help="Documentation output directory.",
    )

    generate_parser.add_argument(
        "--name",
        default=None,
        help="Override project name.",
    )

    generate_parser.add_argument(
        "--type",
        dest="project_type",
        default=None,
        help="Override project type.",
    )

    generate_parser.add_argument(
        "--status",
        default=None,
        help="Override project status.",
    )

    return parser


def main() -> None:

    parser = build_parser()
    args = parser.parse_args()

    if args.command == "init":

        root = Path(
            args.source
        ).resolve()

        init_project(root)
        return

    if args.command == "generate":

        source = Path(
            args.source
        )

        output = Path(
            args.output
        )

        generate(
            source=source,
            output=output,
            name=args.name,
            project_type=args.project_type,
            status=args.status,
        )

        return


if __name__ == "__main__":
    main()