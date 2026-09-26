#!/usr/bin/env python3

"""
BARKLY DOCS
One-file, dependency-free documentation generator.

Usage:

    python barkly_docs.py init

    python barkly_docs.py generate

    python barkly_docs.py generate --source .

    python barkly_docs.py generate --source . --output docs/index.html

The generator statically analyzes Python source with AST.
It does not import or execute the project.

It discovers:

- Python modules
- Functions
- Class methods
- Classes
- Parameters
- Return annotations
- Decorators
- FastAPI / Starlette endpoints
- Flask routes
- Imports
- Git branch
- Git commit
- Recent Git history
"""

from __future__ import annotations

import argparse
import ast
import html
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ============================================================
# DEFAULT PROJECT INFORMATION
# ============================================================

PROJECT = {
    "name": "CYN-X",
    "type": "Intelligent System",
    "status": "Active Development",

    "summary": (
        "BARKLY LABS' flagship intelligent system."
    ),

    "description": (
        "A human-centered intelligent system connecting "
        "local AI, interfaces, tools, software, vision, "
        "hardware, and future systems."
    ),

    "principles": [
        "Human First",
        "Understandable",
        "Private Where Practical",
        "Experimental",
    ],

    "technologies": [
        "Python",
        "FastAPI",
        "Ollama",
        "Astro",
        "TypeScript",
    ],

    "components": [
        "Local AI",
        "Memory",
        "Multimodal Interaction",
        "Computer Vision",
        "AI Interfaces",
        "Human-AI Collaboration",
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


# ============================================================
# DATA STRUCTURES
# ============================================================

@dataclass
class Parameter:
    name: str
    annotation: str = ""
    default: str = ""


@dataclass
class FunctionInfo:
    name: str
    file: str
    line: int

    docstring: str = ""

    parameters: list[Parameter] = field(
        default_factory=list
    )

    returns: str = ""

    decorators: list[str] = field(
        default_factory=list
    )

    async_function: bool = False

    class_name: str = ""


@dataclass
class ClassInfo:
    name: str
    file: str
    line: int

    docstring: str = ""

    bases: list[str] = field(
        default_factory=list
    )

    methods: list[FunctionInfo] = field(
        default_factory=list
    )


@dataclass
class EndpointInfo:
    method: str
    path: str
    function: str

    file: str
    line: int

    docstring: str = ""

    parameters: list[Parameter] = field(
        default_factory=list
    )

    response: str = ""

    framework: str = "API"


@dataclass
class ModuleInfo:
    name: str
    file: str
    lines: int

    docstring: str = ""

    imports: list[str] = field(
        default_factory=list
    )

    functions: list[FunctionInfo] = field(
        default_factory=list
    )

    classes: list[ClassInfo] = field(
        default_factory=list
    )

    endpoints: list[EndpointInfo] = field(
        default_factory=list
    )


# ============================================================
# GENERAL HELPERS
# ============================================================

def esc(value: object) -> str:
    return html.escape(str(value))


def compact_doc(
    doc: str,
    fallback: str = "No description documented yet.",
) -> str:

    text = " ".join(
        (doc or "").strip().split()
    )

    return text or fallback


def expression_text(
    node: Optional[ast.expr],
) -> str:

    if node is None:
        return ""

    try:
        return ast.unparse(node)

    except Exception:
        return ""


def annotation_text(
    node: Optional[ast.expr],
) -> str:

    return expression_text(node)


def relative_file(
    path: Path,
    root: Path,
) -> str:

    try:
        return path.relative_to(root).as_posix()

    except ValueError:
        return path.as_posix()


def chips(items: list[str]) -> str:

    return "".join(
        f'<span class="chip">{esc(item)}</span>'
        for item in items
    )


def cards(
    items: list[str],
    label: str,
) -> str:

    output = []

    for index, item in enumerate(items, 1):

        output.append(
            f"""
            <article class="card">

                <div class="index">
                    {index:02d}
                </div>

                <div>

                    <div class="eyebrow">
                        {esc(label)}
                    </div>

                    <h3>
                        {esc(item)}
                    </h3>

                </div>

            </article>
            """
        )

    return "".join(output)


def code_line(value: str) -> str:

    return f"<code>{esc(value)}</code>"


# ============================================================
# GIT
# ============================================================

def git_command(
    root: Path,
    *args: str,
) -> str:

    try:

        return subprocess.check_output(
            [
                "git",
                "-C",
                str(root),
                *args,
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()

    except Exception:

        return ""


def git_info(
    root: Path,
) -> tuple[str, str]:

    branch = (
        git_command(
            root,
            "branch",
            "--show-current",
        )
        or "unknown"
    )

    commit = (
        git_command(
            root,
            "rev-parse",
            "--short",
            "HEAD",
        )
        or "unknown"
    )

    return branch, commit


def git_history(
    root: Path,
    limit: int = 10,
) -> list[str]:

    result = git_command(
        root,
        "log",
        f"-{limit}",
        "--pretty=format:%h  %ad  %s",
        "--date=short",
    )

    if not result:
        return []

    return result.splitlines()


# ============================================================
# AST PARAMETER DISCOVERY
# ============================================================

def function_parameters(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[Parameter]:

    args = (
        list(node.args.posonlyargs)
        + list(node.args.args)
    )

    defaults = (
        [None] *
        (
            len(args)
            - len(node.args.defaults)
        )
        + list(node.args.defaults)
    )

    result = []

    for arg, default in zip(
        args,
        defaults,
    ):

        result.append(
            Parameter(
                name=arg.arg,
                annotation=annotation_text(
                    arg.annotation
                ),
                default=expression_text(
                    default
                ),
            )
        )

    if node.args.vararg:

        result.append(
            Parameter(
                name="*" + node.args.vararg.arg,
                annotation=annotation_text(
                    node.args.vararg.annotation
                ),
            )
        )

    for arg, default in zip(
        node.args.kwonlyargs,
        node.args.kw_defaults,
    ):

        result.append(
            Parameter(
                name=arg.arg,
                annotation=annotation_text(
                    arg.annotation
                ),
                default=expression_text(
                    default
                ),
            )
        )

    if node.args.kwarg:

        result.append(
            Parameter(
                name="**" + node.args.kwarg.arg,
                annotation=annotation_text(
                    node.args.kwarg.annotation
                ),
            )
        )

    return result


# ============================================================
# ENDPOINT DETECTION
# ============================================================

def detect_endpoints(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    decorators: list[str],
    file: str,
) -> list[EndpointInfo]:

    found = []

    methods = [
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "options",
        "head",
        "trace",
        "websocket",
    ]

    for decorator in decorators:

        for method in methods:

            marker = f".{method}("

            if marker not in decorator:
                continue

            path = "<path not resolved>"

            try:

                inside = decorator.split(
                    marker,
                    1,
                )[1]

                inside = inside.rsplit(
                    ")",
                    1,
                )[0]

                parsed = ast.parse(
                    inside,
                    mode="eval",
                ).body

                if isinstance(
                    parsed,
                    ast.Constant,
                ):

                    path = str(
                        parsed.value
                    )

                elif isinstance(
                    parsed,
                    ast.Tuple,
                ):

                    if parsed.elts:
                        path = expression_text(
                            parsed.elts[0]
                        )

                else:

                    path = expression_text(
                        parsed
                    )

            except Exception:
                pass

            found.append(
                EndpointInfo(
                    method=method.upper(),
                    path=path,
                    function=node.name,
                    file=file,
                    line=getattr(
                        node,
                        "lineno",
                        0,
                    ),
                    docstring=(
                        ast.get_docstring(node)
                        or ""
                    ),
                    parameters=function_parameters(
                        node
                    ),
                    response=annotation_text(
                        node.returns
                    ),
                    framework="FastAPI / Starlette",
                )
            )

    # --------------------------------------------------------
    # Flask @app.route()
    # --------------------------------------------------------

    for decorator in decorators:

        if ".route(" not in decorator:
            continue

        path = "<path not resolved>"

        try:

            inside = decorator.split(
                ".route(",
                1,
            )[1]

            inside = inside.rsplit(
                ")",
                1,
            )[0]

            parsed = ast.parse(
                inside,
                mode="eval",
            ).body

            if isinstance(
                parsed,
                ast.Constant,
            ):

                path = str(
                    parsed.value
                )

            elif isinstance(
                parsed,
                ast.Tuple,
            ):

                if parsed.elts:
                    path = expression_text(
                        parsed.elts[0]
                    )

        except Exception:
            pass

        found.append(
            EndpointInfo(
                method="ROUTE",
                path=path,
                function=node.name,
                file=file,
                line=getattr(
                    node,
                    "lineno",
                    0,
                ),
                docstring=(
                    ast.get_docstring(node)
                    or ""
                ),
                parameters=function_parameters(
                    node
                ),
                response=annotation_text(
                    node.returns
                ),
                framework="Flask",
            )
        )

    return found


# ============================================================
# PYTHON SCANNER
# ============================================================

class PythonScanner:

    def __init__(
        self,
        root: Path,
        file_path: Path,
    ):

        self.root = root

        self.file_path = file_path

        self.relative = relative_file(
            file_path,
            root,
        )

        self.functions = []

        self.classes = []

        self.endpoints = []

        self.imports = []

        self.module_docstring = ""

        self.current_class = None

    # --------------------------------------------------------
    # MODULE
    # --------------------------------------------------------

    def scan(
        self,
        tree: ast.Module,
    ):

        self.module_docstring = (
            ast.get_docstring(tree)
            or ""
        )

        for item in tree.body:

            if isinstance(
                item,
                (
                    ast.Import,
                    ast.ImportFrom,
                ),
            ):

                self.record_import(
                    item
                )

            elif isinstance(
                item,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            ):

                self.record_function(
                    item
                )

            elif isinstance(
                item,
                ast.ClassDef,
            ):

                self.record_class(
                    item
                )

    # --------------------------------------------------------
    # IMPORTS
    # --------------------------------------------------------

    def record_import(
        self,
        node,
    ):

        if isinstance(
            node,
            ast.Import,
        ):

            for alias in node.names:

                self.imports.append(
                    alias.name
                )

        else:

            module = node.module or ""

            for alias in node.names:

                if module:

                    self.imports.append(
                        f"{module}.{alias.name}"
                    )

                else:

                    self.imports.append(
                        alias.name
                    )

    # --------------------------------------------------------
    # FUNCTION
    # --------------------------------------------------------

    def record_function(
        self,
        node,
    ):

        decorators = [
            expression_text(
                decorator
            )
            for decorator
            in node.decorator_list
        ]

        info = FunctionInfo(

            name=node.name,

            file=self.relative,

            line=getattr(
                node,
                "lineno",
                0,
            ),

            docstring=(
                ast.get_docstring(node)
                or ""
            ),

            parameters=function_parameters(
                node
            ),

            returns=annotation_text(
                node.returns
            ),

            decorators=decorators,

            async_function=isinstance(
                node,
                ast.AsyncFunctionDef,
            ),

            class_name=(
                self.current_class.name
                if self.current_class
                else ""
            ),
        )

        if self.current_class:

            self.current_class.methods.append(
                info
            )

        else:

            self.functions.append(
                info
            )

        self.endpoints.extend(
            detect_endpoints(
                node,
                decorators,
                self.relative,
            )
        )

    # --------------------------------------------------------
    # CLASS
    # --------------------------------------------------------

    def record_class(
        self,
        node: ast.ClassDef,
    ):

        info = ClassInfo(

            name=node.name,

            file=self.relative,

            line=getattr(
                node,
                "lineno",
                0,
            ),

            docstring=(
                ast.get_docstring(node)
                or ""
            ),

            bases=[
                expression_text(base)
                for base in node.bases
            ],
        )

        self.classes.append(
            info
        )

        previous_class = (
            self.current_class
        )

        self.current_class = info

        for item in node.body:

            if isinstance(
                item,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            ):

                self.record_function(
                    item
                )

        self.current_class = (
            previous_class
        )


def scan_python(
    root: Path,
) -> list[ModuleInfo]:

    modules = []

    ignored = {
        ".git",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        "dist",
        "build",
    }

    for file_path in sorted(
        root.rglob("*.py")
    ):

        if any(
            part in ignored
            for part in file_path.parts
        ):
            continue

        try:

            source = file_path.read_text(
                encoding="utf-8"
            )

            tree = ast.parse(
                source,
                filename=str(file_path),
            )

        except (
            OSError,
            SyntaxError,
            UnicodeDecodeError,
        ):

            continue

        scanner = PythonScanner(
            root,
            file_path,
        )

        scanner.scan(tree)

        modules.append(
            ModuleInfo(

                name=file_path.stem,

                file=relative_file(
                    file_path,
                    root,
                ),

                lines=len(
                    source.splitlines()
                ),

                docstring=scanner.module_docstring,

                imports=sorted(
                    set(scanner.imports)
                ),

                functions=scanner.functions,

                classes=scanner.classes,

                endpoints=scanner.endpoints,
            )
        )

    return modules


# ============================================================
# HTML CARDS
# ============================================================

def parameter_text(
    parameters: list[Parameter],
) -> str:

    values = []

    for parameter in parameters:

        value = parameter.name

        if parameter.annotation:

            value += (
                ": "
                + parameter.annotation
            )

        if parameter.default:

            value += (
                " = "
                + parameter.default
            )

        values.append(value)

    return ", ".join(values)


def function_card(
    info: FunctionInfo,
) -> str:

    prefix = (
        "async "
        if info.async_function
        else ""
    )

    signature = (
        f"{prefix}"
        f"{info.name}"
        f"({parameter_text(info.parameters)})"
    )

    if info.returns:

        signature += (
            " -> "
            + info.returns
        )

    if info.class_name:

        title = (
            info.class_name
            + "."
            + info.name
        )

        label = "METHOD"

    else:

        title = info.name

        label = "FUNCTION"

    decorators = ""

    if info.decorators:

        decorators = (
            '<div class="decorators">'
            + "".join(
                code_line(x)
                for x in info.decorators
            )
            + "</div>"
        )

    return f"""
    <article class="api-card">

        <div class="api-top">

            <span class="api-kind">
                {label}
            </span>

            <span class="source">
                {esc(info.file)}:{info.line}
            </span>

        </div>

        <h3>
            {esc(title)}
        </h3>

        <div class="signature">
            {esc(signature)}
        </div>

        <p>
            {esc(
                compact_doc(
                    info.docstring
                )
            )}
        </p>

        {decorators}

    </article>
    """


def class_card(
    info: ClassInfo,
) -> str:

    bases = ", ".join(
        info.bases
    )

    base_text = (
        f"({bases})"
        if bases
        else ""
    )

    methods = ""

    for method in info.methods:

        methods += f"""
        <li>

            <code>
                {esc(method.name)}
                ({esc(
                    parameter_text(
                        method.parameters
                    )
                )})
            </code>

            <span>
                {esc(
                    compact_doc(
                        method.docstring,
                        "No method description."
                    )
                )}
            </span>

        </li>
        """

    if not methods:

        methods = """
        <li>
            <span>
                No methods discovered.
            </span>
        </li>
        """

    return f"""
    <article class="api-card">

        <div class="api-top">

            <span class="api-kind">
                CLASS
            </span>

            <span class="source">
                {esc(info.file)}:{info.line}
            </span>

        </div>

        <h3>
            {esc(info.name)}
            {esc(base_text)}
        </h3>

        <p>
            {esc(
                compact_doc(
                    info.docstring
                )
            )}
        </p>

        <div class="subhead">
            METHODS · {len(info.methods)}
        </div>

        <ul class="method-list">
            {methods}
        </ul>

    </article>
    """


def endpoint_card(
    info: EndpointInfo,
) -> str:

    params = parameter_text(
        info.parameters
    )

    response = ""

    if info.response:

        response = (
            " → "
            + info.response
        )

    return f"""
    <article class="endpoint">

        <div class="endpoint-route">

            <span class="method">
                {esc(info.method)}
            </span>

            <strong>
                {esc(info.path)}
            </strong>

        </div>

        <div class="endpoint-meta">

            <code>
                {esc(info.function)}
                ({esc(params)})
                {esc(response)}
            </code>

            <span>
                {esc(info.framework)}
                ·
                {esc(info.file)}:{info.line}
            </span>

        </div>

        <p>
            {esc(
                compact_doc(
                    info.docstring
                )
            )}
        </p>

    </article>
    """


def module_card(
    info: ModuleInfo,
) -> str:

    return f"""
    <article class="api-card">

        <div class="api-top">

            <span class="api-kind">
                MODULE
            </span>

            <span class="source">
                {esc(info.file)}
            </span>

        </div>

        <h3>
            {esc(info.name)}
        </h3>

        <p>
            {esc(
                compact_doc(
                    info.docstring
                )
            )}
        </p>

        <div class="module-stats">

            <span>
                {len(info.functions)}
                functions
            </span>

            <span>
                {len(info.classes)}
                classes
            </span>

            <span>
                {len(info.endpoints)}
                endpoints
            </span>

            <span>
                {info.lines}
                lines
            </span>

        </div>

    </article>
    """


# ============================================================
# PROJECT CONFIG
# ============================================================

def load_project() -> dict:

    config = Path(
        "project.json"
    )

    if not config.exists():

        return dict(PROJECT)

    try:

        data = json.loads(
            config.read_text(
                encoding="utf-8"
            )
        )

        merged = dict(PROJECT)

        merged.update(data)

        return merged

    except Exception as exc:

        print(
            "Warning: could not read "
            f"project.json: {exc}"
        )

        return dict(PROJECT)


def write_template():

    Path(
        "project.json"
    ).write_text(
        json.dumps(
            PROJECT,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        "Created project.json"
    )


# ============================================================
# HTML GENERATOR
# ============================================================

def generate(
    project: dict,
    root: Path,
    output: Path,
):

    modules = scan_python(
        root
    )

    all_functions = [
        function

        for module in modules

        for function in module.functions
    ]

    all_methods = [
        method

        for module in modules

        for cls in module.classes

        for method in cls.methods
    ]

    all_classes = [
        cls

        for module in modules

        for cls in module.classes
    ]

    all_endpoints = [
        endpoint

        for module in modules

        for endpoint in module.endpoints
    ]

    all_imports = sorted(
        {
            item.split(
                ".",
                1
            )[0]

            for module in modules

            for item in module.imports
        }
    )

    branch, commit = git_info(
        root
    )

    history = git_history(
        root
    )

    function_html = "".join(
        function_card(x)

        for x in (
            all_functions
            + all_methods
        )
    )

    class_html = "".join(
        class_card(x)

        for x in all_classes
    )

    endpoint_html = "".join(
        endpoint_card(x)

        for x in all_endpoints
    )

    module_html = "".join(
        module_card(x)

        for x in modules
    )

    if not function_html:

        function_html = """
        <div class="empty">
            No Python functions discovered.
        </div>
        """

    if not class_html:

        class_html = """
        <div class="empty">
            No Python classes discovered.
        </div>
        """

    if not endpoint_html:

        endpoint_html = """
        <div class="empty">
            No API endpoints detected.
        </div>
        """

    if not module_html:

        module_html = """
        <div class="empty">
            No Python modules discovered.
        </div>
        """

    history_html = "".join(
        f"""
        <li>
            <code>
                {esc(item)}
            </code>
        </li>
        """

        for item in history
    )

    if not history_html:

        history_html = """
        <li>
            No Git history available.
        </li>
        """

    import_html = chips(
        all_imports[:80]
    )

    lifecycle_html = ""

    for index, item in enumerate(
        project.get(
            "lifecycle",
            []
        ),
        1,
    ):

        lifecycle_html += f"""
        <div class="step">

            <span>
                {index:02d}
            </span>

            <strong>
                {esc(item)}
            </strong>

        </div>
        """

    technology_html = chips(
        project.get(
            "technologies",
            []
        )
    )

    # --------------------------------------------------------
    # COMPLETE DOCUMENT
    # --------------------------------------------------------

    page = f"""<!doctype html>

<html lang="en">

<head>

<meta charset="utf-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1"
>

<title>
    {esc(project["name"])}
    —
    BARKLY DOCS
</title>

<meta
    name="description"
    content="{esc(project["summary"])}"
>

<style>

:root {{

    --bg: #08090b;

    --panel: #101216;

    --panel2: #15171c;

    --line: #292d35;

    --text: #f3f4f6;

    --muted: #9da3ae;

    --soft: #cdd1d8;

    --radius: 18px;

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

    font:
        16px/1.6
        Inter,
        ui-sans-serif,
        system-ui,
        -apple-system,
        "Segoe UI",
        sans-serif;

}}

a {{
    color: inherit;
}}

.shell {{

    max-width: 1200px;

    margin: auto;

    padding:
        0 28px;

}}

header {{

    position: sticky;

    top: 0;

    z-index: 20;

    background:
        rgba(8, 9, 11, .90);

    backdrop-filter:
        blur(16px);

    border-bottom:
        1px solid var(--line);

}}

.nav {{

    height: 72px;

    display: flex;

    align-items: center;

    justify-content: space-between;

    gap: 20px;

}}

.brand {{

    display: flex;

    align-items: center;

    gap: 12px;

    font-weight: 800;

    letter-spacing: .08em;

}}

.paw {{

    width: 30px;

    height: 30px;

    fill: currentColor;

}}

.nav small {{

    color: var(--muted);

}}

.hero {{

    padding:
        110px 0 80px;

    border-bottom:
        1px solid var(--line);

}}

.eyebrow {{

    color: var(--muted);

    font:
        12px
        ui-monospace,
        SFMono-Regular,
        Menlo,
        monospace;

    font-weight: 700;

    letter-spacing: .16em;

    text-transform: uppercase;

}}

h1 {{

    margin:
        18px 0 12px;

    font-size:
        clamp(
            54px,
            9vw,
            112px
        );

    line-height: .9;

    letter-spacing: -.06em;

}}

.hero p {{

    max-width: 760px;

    color: var(--soft);

    font-size: 20px;

}}

.meta {{

    display: flex;

    flex-wrap: wrap;

    gap: 10px;

    margin-top: 28px;

}}

.chip {{

    border:
        1px solid var(--line);

    background:
        var(--panel);

    border-radius: 999px;

    padding:
        7px 12px;

    color: var(--soft);

    font:
        12px
        ui-monospace,
        SFMono-Regular,
        monospace;

}}

.status {{

    display: inline-flex;

    align-items: center;

    gap: 8px;

    color: var(--soft);

    font:
        12px
        ui-monospace,
        SFMono-Regular,
        monospace;

}}

.status::before {{

    content: "";

    width: 7px;

    height: 7px;

    border-radius: 50%;

    background:
        currentColor;

}}

section {{

    padding:
        72px 0;

    border-bottom:
        1px solid var(--line);

}}

.section-head {{

    display: grid;

    grid-template-columns:
        1fr 2fr;

    gap: 40px;

    margin-bottom: 34px;

}}

h2 {{

    margin:
        5px 0;

    font-size:
        clamp(
            30px,
            4vw,
            48px
        );

    letter-spacing:
        -.04em;

}}

.section-head p {{

    margin: 0;

    color: var(--muted);

    max-width: 700px;

}}

.grid {{

    display: grid;

    grid-template-columns:
        repeat(
            3,
            1fr
        );

    gap: 14px;

}}

.card,
.api-card,
.endpoint {{

    background:
        var(--panel);

    border:
        1px solid var(--line);

    border-radius:
        var(--radius);

}}

.card {{

    min-height: 150px;

    padding: 22px;

    display: flex;

    flex-direction: column;

    justify-content: space-between;

}}

.card:hover,
.api-card:hover,
.endpoint:hover {{

    border-color:
        #555b67;

}}

.index {{

    color:
        #666c77;

    font:
        12px
        ui-monospace,
        SFMono-Regular,
        Menlo,
        monospace;

}}

.card h3,
.api-card h3 {{

    margin:
        5px 0;

    font-size: 20px;

}}

.steps {{

    display: grid;

    grid-template-columns:
        repeat(
            5,
            1fr
        );

    gap: 10px;

}}

.step {{

    padding: 18px;

    min-height: 92px;

    background:
        var(--panel);

    border:
        1px solid var(--line);

    border-radius: 14px;

}}

.step span {{

    display: block;

    color:
        #666c77;

    font:
        11px
        ui-monospace,
        SFMono-Regular,
        Menlo,
        monospace;

    margin-bottom:
        18px;

}}

.api-grid {{

    display: grid;

    grid-template-columns:
        repeat(
            2,
            1fr
        );

    gap: 14px;

}}

.api-card {{

    padding: 22px;

}}

.api-top {{

    display: flex;

    justify-content:
        space-between;

    gap: 15px;

}}

.api-kind {{

    color:
        var(--muted);

    font:
        11px
        ui-monospace,
        SFMono-Regular,
        Menlo,
        monospace;

    letter-spacing:
        .12em;

}}

.source {{

    color:
        #666c77;

    font:
        11px
        ui-monospace,
        SFMono-Regular,
        Menlo,
        monospace;

    text-align: right;

}}

.api-card p,
.endpoint p {{

    color:
        var(--muted);

    margin-bottom:
        0;

}}

.signature {{

    padding:
        10px 12px;

    margin:
        12px 0;

    background:
        var(--panel2);

    border:
        1px solid var(--line);

    border-radius:
        9px;

    overflow:
        auto;

    font:
        13px
        ui-monospace,
        SFMono-Regular,
        Menlo,
        monospace;

    color:
        var(--soft);

}}

.decorators {{

    display: flex;

    flex-wrap: wrap;

    gap: 6px;

}}

code {{

    color:
        var(--soft);

    background:
        var(--panel2);

    border:
        1px solid var(--line);

    padding:
        2px 6px;

    border-radius:
        6px;

    font:
        12px
        ui-monospace,
        SFMono-Regular,
        Menlo,
        monospace;

}}

.endpoint {{

    padding:
        18px 20px;

}}

.endpoint-route {{

    display: flex;

    align-items: center;

    gap: 12px;

    flex-wrap: wrap;

}}

.method {{

    border:
        1px solid var(--line);

    padding:
        4px 8px;

    border-radius:
        6px;

    font:
        11px
        ui-monospace,
        SFMono-Regular,
        Menlo,
        monospace;

    font-weight: 800;

}}

.endpoint-route strong {{

    font:
        15px
        ui-monospace,
        SFMono-Regular,
        Menlo,
        monospace;

}}

.endpoint-meta {{

    display: flex;

    gap: 14px;

    flex-wrap: wrap;

    align-items: center;

    margin-top:
        12px;

    color:
        var(--muted);

    font-size:
        12px;

}}

.method-list {{

    margin:
        14px 0 0;

    padding-left:
        18px;

    color:
        var(--muted);

}}

.method-list li {{

    margin:
        8px 0;

    display: flex;

    gap: 10px;

    flex-wrap: wrap;

}}

.method-list span {{

    color:
        var(--muted);

}}

.subhead {{

    margin-top:
        20px;

    color:
        #666c77;

    font:
        11px
        ui-monospace,
        SFMono-Regular,
        Menlo,
        monospace;

    letter-spacing:
        .12em;

}}

.module-stats {{

    display: flex;

    flex-wrap: wrap;

    gap: 8px;

    margin-top:
        18px;

    color:
        #777d88;

    font:
        11px
        ui-monospace,
        SFMono-Regular,
        Menlo,
        monospace;

}}

.module-stats span {{

    border:
        1px solid var(--line);

    border-radius:
        999px;

    padding:
        4px 8px;

}}

.empty {{

    border:
        1px dashed var(--line);

    border-radius:
        var(--radius);

    padding:
        25px;

    color:
        var(--muted);

}}

.history {{

    margin: 0;

    padding-left:
        20px;

    color:
        var(--muted);

}}

.history li {{

    margin:
        8px 0;

}}

footer {{

    padding:
        34px 0 60px;

    color:
        var(--muted);

    font-size:
        13px;

}}

.footer-row {{

    display: flex;

    justify-content:
        space-between;

    gap: 20px;

    flex-wrap: wrap;

    align-items: center;

}}

@media (max-width: 900px) {{

    .section-head,
    .grid,
    .api-grid {{

        grid-template-columns:
            1fr;

    }}

    .steps {{

        grid-template-columns:
            repeat(
                2,
                1fr
            );

    }}

}}

@media (max-width: 520px) {{

    .shell {{

        padding:
            0 18px;

    }}

    .hero {{

        padding:
            76px 0 56px;

    }}

    .steps {{

        grid-template-columns:
            1fr;

    }}

    .nav small {{

        display: none;

    }}

}}

</style>

</head>

<body>

<header>

    <div class="shell nav">

        <div class="brand">

            <svg
                class="paw"
                viewBox="0 0 64 64"
                aria-hidden="true"
            >

                <circle
                    cx="20"
                    cy="20"
                    r="7"
                />

                <circle
                    cx="32"
                    cy="14"
                    r="7"
                />

                <circle
                    cx="44"
                    cy="20"
                    r="7"
                />

                <circle
                    cx="51"
                    cy="31"
                    r="6"
                />

                <path
                    d="
                        M32 28
                        c-9 0-17 8-17 17
                        c0 7 5 11 10 11
                        c3 0 5-2 7-4
                        c2 2 4 4 7 4
                        c5 0 10-4 10-11
                        c0-9-8-17-17-17z
                    "
                />

            </svg>

            <span>
                BARKLY DOCS
            </span>

        </div>

        <small>
            {esc(project["name"])}
            /
            {esc(project["type"])}
        </small>

    </div>

</header>


<main>

<div class="shell">


<section class="hero">

    <div class="eyebrow">
        01 / PROJECT
    </div>

    <h1>
        {esc(project["name"])}
    </h1>

    <div class="status">
        {esc(project["status"])}
    </div>

    <p>

        <strong>
            {esc(project["summary"])}
        </strong>

        <br>

        {esc(project["description"])}

    </p>

    <div class="meta">

        {technology_html}

    </div>

</section>


<section>

    <div class="section-head">

        <div>

            <div class="eyebrow">
                02 / PRINCIPLES
            </div>

            <h2>
                How it is built.
            </h2>

        </div>

        <p>
            Design principles that guide the
            project and make technical complexity
            easier for humans to approach.
        </p>

    </div>

    <div class="grid">

        {cards(
            project.get(
                "principles",
                []
            ),
            "PRINCIPLE"
        )}

    </div>

</section>


<section>

    <div class="section-head">

        <div>

            <div class="eyebrow">
                03 / COMPONENTS
            </div>

            <h2>
                System map.
            </h2>

        </div>

        <p>
            The major pieces currently identified
            as part of the project.
        </p>

    </div>

    <div class="grid">

        {cards(
            project.get(
                "components",
                []
            ),
            "COMPONENT"
        )}

    </div>

</section>


<section>

    <div class="section-head">

        <div>

            <div class="eyebrow">
                04 / API
            </div>

            <h2>
                Endpoints.
            </h2>

        </div>

        <p>
            Routes discovered directly from
            Python source. BARKLY DOCS reads
            decorators without running your
            application.
        </p>

    </div>

    <div class="api-grid">

        {endpoint_html}

    </div>

</section>


<section>

    <div class="section-head">

        <div>

            <div class="eyebrow">
                05 / CODE
            </div>

            <h2>
                Functions & methods.
            </h2>

        </div>

        <p>
            Functions and class methods discovered
            from source, including signatures,
            annotations, decorators, and
            documentation strings.
        </p>

    </div>

    <div class="api-grid">

        {function_html}

    </div>

</section>


<section>

    <div class="section-head">

        <div>

            <div class="eyebrow">
                06 / CLASSES
            </div>

            <h2>
                Objects.
            </h2>

        </div>

        <p>
            Classes discovered from Python source,
            including inheritance and their
            documented methods.
        </p>

    </div>

    <div class="api-grid">

        {class_html}

    </div>

</section>


<section>

    <div class="section-head">

        <div>

            <div class="eyebrow">
                07 / MODULES
            </div>

            <h2>
                Project map.
            </h2>

        </div>

        <p>
            Every scanned Python module with
            line counts and discovered structure.
        </p>

    </div>

    <div class="api-grid">

        {module_html}

    </div>

</section>


<section>

    <div class="section-head">

        <div>

            <div class="eyebrow">
                08 / IMPORTS
            </div>

            <h2>
                Dependencies in source.
            </h2>

        </div>

        <p>
            Top-level imports discovered statically
            from Python files. This does not replace
            requirements.txt or package locks.
        </p>

    </div>

    <div class="meta">

        {import_html or
        '<span class="empty">No imports discovered.</span>'}

    </div>

</section>


<section>

    <div class="section-head">

        <div>

            <div class="eyebrow">
                09 / LIFECYCLE
            </div>

            <h2>
                From idea to iteration.
            </h2>

        </div>

        <p>
            A repeatable path from experimentation
            through release and continued development.
        </p>

    </div>

    <div class="steps">

        {lifecycle_html}

    </div>

</section>


<section>

    <div class="section-head">

        <div>

            <div class="eyebrow">
                10 / GIT
            </div>

            <h2>
                Engineering record.
            </h2>

        </div>

        <p>
            Automatically captured project context
            so future-you does not have to remember
            everything.
        </p>

    </div>

    <div class="grid">

        <article class="card">

            <div class="eyebrow">
                PYTHON FILES
            </div>

            <h3>
                {len(modules)}
            </h3>

        </article>


        <article class="card">

            <div class="eyebrow">
                API ENDPOINTS
            </div>

            <h3>
                {len(all_endpoints)}
            </h3>

        </article>


        <article class="card">

            <div class="eyebrow">
                FUNCTIONS / METHODS
            </div>

            <h3>
                {len(all_functions) + len(all_methods)}
            </h3>

        </article>


        <article class="card">

            <div class="eyebrow">
                CLASSES
            </div>

            <h3>
                {len(all_classes)}
            </h3>

        </article>


        <article class="card">

            <div class="eyebrow">
                BRANCH
            </div>

            <h3>
                {esc(branch)}
            </h3>

        </article>


        <article class="card">

            <div class="eyebrow">
                COMMIT
            </div>

            <h3>
                {esc(commit)}
            </h3>

        </article>

    </div>

</section>


<section>

    <div class="section-head">

        <div>

            <div class="eyebrow">
                11 / CHANGELOG
            </div>

            <h2>
                Recent work.
            </h2>

        </div>

        <p>
            Recent Git commits are included
            automatically when the project is
            tracked by Git.
        </p>

    </div>

    <ul class="history">

        {history_html}

    </ul>

</section>


</div>

</main>


<footer>

    <div class="shell footer-row">

        <span>
            BARKLY LABS · BARKLY DOCS
        </span>

        <span>
            Technology should adapt to humans.
        </span>

    </div>

</footer>


</body>

</html>
"""

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_text(
        page,
        encoding="utf-8",
    )

    print(
        f"Generated: {output}"
    )

    print(
        "Scanned "
        f"{len(modules)} Python modules, "
        f"{len(all_endpoints)} endpoints, "
        f"{len(all_functions) + len(all_methods)} "
        "functions/methods, "
        f"{len(all_classes)} classes."
    )


# ============================================================
# COMMAND LINE
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "BARKLY DOCS — "
            "automatic project documentation"
        )
    )

    sub = parser.add_subparsers(
        dest="command"
    )

    sub.add_parser(
        "init",
        help=(
            "Create a project.json template."
        ),
    )

    generate_parser = sub.add_parser(
        "generate",
        help=(
            "Scan the project and "
            "generate HTML documentation."
        ),
    )

    generate_parser.add_argument(
        "--source",
        default=".",
        help=(
            "Project directory to scan."
        ),
    )

    generate_parser.add_argument(
        "--output",
        default="docs/index.html",
        help=(
            "Generated HTML path."
        ),
    )

    generate_parser.add_argument(
        "--name"
    )

    generate_parser.add_argument(
        "--type"
    )

    generate_parser.add_argument(
        "--status"
    )

    args = parser.parse_args()

    if args.command == "init":

        write_template()

        return

    if args.command == "generate":

        root = Path(
            args.source
        ).resolve()

        project = load_project()

        if args.name:
            project["name"] = args.name

        if args.type:
            project["type"] = args.type

        if args.status:
            project["status"] = args.status

        generate(
            project=project,
            root=root,
            output=Path(
                args.output
            ),
        )

        return

    parser.print_help()


if __name__ == "__main__":

    main()