#!/usr/bin/env python3
"""BARKLY DOCS - one-file, dependency-free project documentation generator."""

from __future__ import annotations
import argparse, html, json, subprocess
from datetime import datetime
from pathlib import Path

PROJECT = {
    "name": "CYN-X",
    "type": "Intelligent System",
    "status": "Active Development",
    "summary": "BARKLY LABS' flagship intelligent system.",
    "description": "A human-centered intelligent system connecting local AI, interfaces, tools, software, vision, hardware, and future systems.",
    "principles": ["Human First", "Understandable", "Private Where Practical", "Experimental"],
    "technologies": ["Python", "FastAPI", "Ollama", "Astro", "TypeScript"],
    "components": ["Local AI", "Memory", "Multimodal Interaction", "Computer Vision", "AI Interfaces", "Human-AI Collaboration"],
    "lifecycle": ["Idea", "Research", "Experiment", "Prototype", "Community Testing", "Engineering", "Productization", "Release", "Feedback", "Continued Development"],
}

PAW = """<svg class="paw" viewBox="0 0 64 64" aria-hidden="true">
<circle cx="20" cy="20" r="7"/><circle cx="32" cy="14" r="7"/><circle cx="44" cy="20" r="7"/><circle cx="51" cy="31" r="6"/>
<path d="M32 28c-9 0-17 8-17 17 0 7 5 11 10 11 3 0 5-2 7-4 2 2 4 4 7 4 5 0 10-4 10-11 0-9-8-17-17-17z"/>
</svg>"""

def esc(x): return html.escape(str(x))

def git_info():
    try:
        b = subprocess.check_output(["git","branch","--show-current"], stderr=subprocess.DEVNULL, text=True).strip() or "unknown"
        c = subprocess.check_output(["git","rev-parse","--short","HEAD"], stderr=subprocess.DEVNULL, text=True).strip() or "unknown"
        return b, c
    except Exception:
        return "not a git repository", "unknown"

def cards(items, label):
    return "".join(
        f'<article class="card"><div class="index">{i:02d}</div><div><div class="eyebrow">{esc(label)}</div><h3>{esc(x)}</h3></div></article>'
        for i, x in enumerate(items, 1)
    )

def generate(project, output):
    branch, commit = git_info()
    lifecycle = "".join(
        f'<div class="step"><span>{i:02d}</span><strong>{esc(x)}</strong></div>'
        for i, x in enumerate(project.get("lifecycle", []), 1)
    )
    chips = "".join(f'<span class="chip">{esc(x)}</span>' for x in project.get("technologies", []))

    page = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(project["name"])} — BARKLY DOCS</title>
<meta name="description" content="{esc(project["summary"])}">
<style>
:root{{--bg:#08090b;--panel:#101216;--line:#292d35;--text:#f3f4f6;--muted:#9da3ae;--soft:#cdd1d8}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--bg);color:var(--text);font:16px/1.6 Inter,system-ui,-apple-system,"Segoe UI",sans-serif}}
a{{color:inherit}}.shell{{max-width:1180px;margin:auto;padding:0 28px}}
header{{position:sticky;top:0;z-index:10;background:rgba(8,9,11,.9);backdrop-filter:blur(16px);border-bottom:1px solid var(--line)}}
.nav{{height:72px;display:flex;align-items:center;justify-content:space-between}}.brand{{display:flex;align-items:center;gap:12px;font-weight:800;letter-spacing:.08em}}
.paw{{width:30px;height:30px;fill:currentColor}}.nav small,.eyebrow,.status,.index,.step span{{font-family:ui-monospace,SFMono-Regular,monospace}}
.nav small{{color:var(--muted)}}.hero{{padding:110px 0 80px;border-bottom:1px solid var(--line)}}
.eyebrow{{color:var(--muted);font-size:12px;font-weight:700;letter-spacing:.16em;text-transform:uppercase}}
h1{{margin:18px 0 12px;font-size:clamp(54px,9vw,112px);line-height:.9;letter-spacing:-.06em}}
.hero p{{max-width:720px;color:var(--soft);font-size:20px}}.meta{{display:flex;flex-wrap:wrap;gap:10px;margin-top:28px}}
.chip{{border:1px solid var(--line);background:var(--panel);border-radius:999px;padding:7px 12px;color:var(--soft);font:12px ui-monospace,SFMono-Regular,monospace}}
.status{{display:inline-flex;align-items:center;gap:8px;color:var(--soft);font-size:12px}}.status:before{{content:"";width:7px;height:7px;border-radius:50%;background:currentColor}}
section{{padding:72px 0;border-bottom:1px solid var(--line)}}.section-head{{display:grid;grid-template-columns:1fr 2fr;gap:40px;margin-bottom:34px}}
h2{{margin:5px 0;font-size:clamp(30px,4vw,48px);letter-spacing:-.04em}}.section-head p{{margin:0;color:var(--muted);max-width:650px}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}.card{{min-height:150px;padding:22px;border:1px solid var(--line);background:var(--panel);border-radius:18px;display:flex;flex-direction:column;justify-content:space-between;transition:.2s}}
.card:hover{{transform:translateY(-3px);border-color:#555b67}}.index{{color:#666c77;font-size:12px}}.card h3{{margin:5px 0;font-size:20px}}
.steps{{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}}.step{{padding:18px;min-height:92px;background:var(--panel);border:1px solid var(--line);border-radius:14px}}
.step span{{display:block;color:#666c77;font-size:11px;margin-bottom:18px}}.step strong{{font-size:14px}}
footer{{padding:34px 0 60px;color:var(--muted);font-size:13px}}.footer-row{{display:flex;justify-content:space-between;gap:20px;flex-wrap:wrap}}
@media(max-width:850px){{.section-head,.grid{{grid-template-columns:1fr}}.steps{{grid-template-columns:repeat(2,1fr)}}}}
@media(max-width:520px){{.shell{{padding:0 18px}}.hero{{padding:76px 0 56px}}.steps{{grid-template-columns:1fr}}}}
</style></head>
<body>
<header><div class="shell nav"><div class="brand">{PAW}<span>BARKLY DOCS</span></div><small>{esc(project["name"])} / {esc(project["type"])}</small></div></header>
<main><div class="shell">
<section class="hero"><div class="eyebrow">01 / PROJECT</div><h1>{esc(project["name"])}</h1>
<div class="status">{esc(project["status"])}</div><p><strong>{esc(project["summary"])}</strong><br>{esc(project["description"])}</p>
<div class="meta">{chips}</div></section>
<section><div class="section-head"><div><div class="eyebrow">02 / PRINCIPLES</div><h2>How it is built.</h2></div><p>Design principles that guide the project and make technical complexity easier for humans to approach.</p></div>
<div class="grid">{cards(project.get("principles",[]),"PRINCIPLE")}</div></section>
<section><div class="section-head"><div><div class="eyebrow">03 / COMPONENTS</div><h2>System map.</h2></div><p>The major pieces currently identified as part of the project.</p></div>
<div class="grid">{cards(project.get("components",[]),"COMPONENT")}</div></section>
<section><div class="section-head"><div><div class="eyebrow">04 / LIFECYCLE</div><h2>From idea to iteration.</h2></div><p>A repeatable path from experimentation through release and continued development.</p></div>
<div class="steps">{lifecycle}</div></section>
<section><div class="section-head"><div><div class="eyebrow">05 / ENGINEERING</div><h2>Project record.</h2></div><p>Automatically captured context so future-you does not have to remember everything.</p></div>
<div class="grid"><article class="card"><div class="eyebrow">GENERATED</div><h3>{datetime.now().strftime("%Y-%m-%d %H:%M")}</h3></article>
<article class="card"><div class="eyebrow">GIT BRANCH</div><h3>{esc(branch)}</h3></article><article class="card"><div class="eyebrow">COMMIT</div><h3>{esc(commit)}</h3></article></div></section>
</div></main>
<footer><div class="shell footer-row"><span>{PAW} BARKLY LABS · BARKLY DOCS</span><span>Technology should adapt to humans.</span></div></footer>
</body></html>"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")
    print("Generated:", output)

def load_project():
    p = Path("project.json")
    if p.exists():
        try:
            x = dict(PROJECT); x.update(json.loads(p.read_text(encoding="utf-8"))); return x
        except Exception: pass
    return dict(PROJECT)

def main():
    parser = argparse.ArgumentParser(description="BARKLY DOCS")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("init")
    gen = sub.add_parser("generate")
    gen.add_argument("--name"); gen.add_argument("--type"); gen.add_argument("--status")
    gen.add_argument("--output", default="docs/index.html")
    a = parser.parse_args()
    if a.cmd == "init":
        Path("project.json").write_text(json.dumps(PROJECT, indent=2)+"\n", encoding="utf-8")
        print("Created project.json")
    elif a.cmd == "generate":
        p = load_project()
        if a.name: p["name"] = a.name
        if a.type: p["type"] = a.type
        if a.status: p["status"] = a.status
        generate(p, Path(a.output))
    else: parser.print_help()

if __name__ == "__main__":
    main()
