#!/usr/bin/env python3
"""Generate a single combined Mermaid diagram for all LangGraph workflows.

This script produces one mega-diagram with:
- A subgraph per workflow
- All nodes/edges from each workflow
- Optional cross-workflow orchestration links

Run from repo root:
    backend\\venv\\Scripts\\python scripts\\visualize_langgraphs_combined.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from langchain_core.runnables.graph import MermaidDrawMethod
from langchain_core.runnables.graph_mermaid import draw_mermaid_png


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.agents.constructor.coordinator.agent import build_coordinator_graph
from app.agents.constructor.ingestion.agent import build_ingestion_graph
from app.agents.constructor.quiz_gen.agent import build_quiz_gen_graph
from app.agents.constructor.structure.agent import build_structure_graph
from app.agents.constructor.validation.agent import build_validation_graph
from app.agents.tutor.graph import build_tutor_graph


@dataclass(frozen=True)
class WorkflowSpec:
    key: str
    title: str
    builder: Callable[[], object]


def _build_constructor_coordinator():
    return build_coordinator_graph("viz_constructor").graph


def _build_constructor_ingestion():
    return build_ingestion_graph().graph


def _build_constructor_structure():
    return build_structure_graph().graph


def _build_constructor_quiz_gen():
    return build_quiz_gen_graph().graph


def _build_constructor_validation():
    return build_validation_graph().graph


def _build_tutor():
    return build_tutor_graph("viz_tutor").graph


WORKFLOWS: list[WorkflowSpec] = [
    WorkflowSpec("constructor_coordinator", "Constructor Coordinator", _build_constructor_coordinator),
    WorkflowSpec("constructor_ingestion", "Constructor Ingestion Sub-Agent", _build_constructor_ingestion),
    WorkflowSpec("constructor_structure", "Constructor Structure Sub-Agent", _build_constructor_structure),
    WorkflowSpec("constructor_quiz_gen", "Constructor Quiz Generation Sub-Agent", _build_constructor_quiz_gen),
    WorkflowSpec("constructor_validation", "Constructor Validation Sub-Agent", _build_constructor_validation),
    WorkflowSpec("tutor_coordinator", "Tutor Coordinator", _build_tutor),
]


def _build_fallback_composite_png(target_png: Path) -> str | None:
    """Compose a single image from per-workflow PNGs as a local fallback."""
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return "Pillow not available for fallback composite PNG."

    source_files: list[tuple[str, Path]] = []
    for spec in WORKFLOWS:
        p = ROOT_DIR / "artifacts" / "langgraph_viz" / spec.key / f"{spec.key}.png"
        if p.exists():
            source_files.append((spec.title, p))

    if not source_files:
        return "No per-workflow PNG files found for fallback composite."

    images = []
    for title, path in source_files:
        img = Image.open(path).convert("RGB")
        images.append((title, img))

    cols = 2
    rows = (len(images) + cols - 1) // cols
    tile_w = max(img.width for _, img in images)
    tile_h = max(img.height for _, img in images)
    header_h = 44
    pad = 24

    canvas_w = cols * tile_w + (cols + 1) * pad
    canvas_h = rows * (tile_h + header_h) + (rows + 1) * pad
    canvas = Image.new("RGB", (canvas_w, canvas_h), color=(245, 247, 250))
    draw = ImageDraw.Draw(canvas)

    for i, (title, img) in enumerate(images):
        r, c = divmod(i, cols)
        x = pad + c * (tile_w + pad)
        y = pad + r * (tile_h + header_h + pad)
        draw.rectangle((x, y, x + tile_w, y + header_h), fill=(230, 236, 245))
        draw.text((x + 10, y + 12), title, fill=(33, 37, 41))
        canvas.paste(img, (x, y + header_h))

    target_png.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(target_png, format="PNG")
    return None


def _safe_id(raw: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", str(raw))
    if not cleaned:
        cleaned = "node"
    if cleaned[0].isdigit():
        cleaned = f"n_{cleaned}"
    return cleaned


def _full_node_id(workflow_key: str, node_id: str) -> str:
    return f"{_safe_id(workflow_key)}__{_safe_id(node_id)}"


def _edge_label(value: object) -> str:
    text = str(value or "").strip()
    text = text.replace("|", "/").replace('"', "'")
    return text


def _node_label(node: dict) -> str:
    node_id = str(node.get("id", ""))
    if node_id == "__start__":
        return "START"
    if node_id == "__end__":
        return "END"
    data = node.get("data") or {}
    name = str(data.get("name") or node_id)
    return name.replace('"', "'")


def _render_subgraph(spec: WorkflowSpec, graph_json: dict) -> tuple[list[str], dict[str, str]]:
    node_map: dict[str, str] = {}
    lines: list[str] = []

    subgraph_id = _safe_id(spec.key)
    lines.append(f'subgraph {subgraph_id}["{spec.title}"]')
    lines.append("direction TB")

    for node in graph_json.get("nodes", []):
        raw_id = str(node.get("id", ""))
        full_id = _full_node_id(spec.key, raw_id)
        node_map[raw_id] = full_id
        label = _node_label(node)
        if raw_id in {"__start__", "__end__"}:
            lines.append(f'{full_id}(("{label}"))')
        else:
            lines.append(f'{full_id}["{label}"]')

    for edge in graph_json.get("edges", []):
        src_raw = str(edge.get("source", ""))
        dst_raw = str(edge.get("target", ""))
        if src_raw not in node_map or dst_raw not in node_map:
            continue
        src = node_map[src_raw]
        dst = node_map[dst_raw]
        label = _edge_label(edge.get("data"))
        conditional = bool(edge.get("conditional", False))
        arrow = "-.->" if conditional else "-->"
        if label:
            lines.append(f'{src} -- "{label}" {arrow} {dst}')
        else:
            lines.append(f"{src} {arrow} {dst}")

    lines.append("end")
    return lines, node_map


def _cross_workflow_edges(node_maps: dict[str, dict[str, str]]) -> list[str]:
    lines: list[str] = []

    coord = node_maps.get("constructor_coordinator", {})
    ing = node_maps.get("constructor_ingestion", {})
    struct = node_maps.get("constructor_structure", {})
    quiz = node_maps.get("constructor_quiz_gen", {})
    valid = node_maps.get("constructor_validation", {})

    def get(workflow: dict[str, str], key: str) -> str | None:
        return workflow.get(key)

    orchestration_pairs = [
        (get(coord, "ingestion"), get(ing, "__start__"), "invokes"),
        (get(coord, "structure"), get(struct, "__start__"), "invokes"),
        (get(coord, "quiz"), get(quiz, "__start__"), "invokes"),
        (get(coord, "validation"), get(valid, "__start__"), "invokes"),
        (get(ing, "__end__"), get(coord, "respond"), "returns"),
        (get(struct, "__end__"), get(coord, "respond"), "returns"),
        (get(quiz, "__end__"), get(coord, "respond"), "returns"),
        (get(valid, "__end__"), get(coord, "respond"), "returns"),
    ]

    for src, dst, label in orchestration_pairs:
        if src and dst:
            lines.append(f'{src} -. "{label}" .-> {dst}')
    return lines


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-file",
        default="artifacts/langgraph_viz/combined/all_workflows.mmd",
        help="Output Mermaid file path (repo-relative or absolute).",
    )
    parser.add_argument(
        "--direction",
        default="TB",
        choices=["TB", "BT", "LR", "RL"],
        help="Top-level Mermaid flow direction. Default: TB",
    )
    parser.add_argument(
        "--no-cross-links",
        action="store_true",
        help="Disable conceptual orchestration links between workflows.",
    )
    parser.add_argument(
        "--png",
        action="store_true",
        help="Also render combined PNG next to the Mermaid file.",
    )
    parser.add_argument(
        "--png-method",
        choices=[m.value for m in MermaidDrawMethod],
        default=MermaidDrawMethod.API.value,
        help="PNG render backend. Default: api",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    output_file = Path(args.output_file)
    if not output_file.is_absolute():
        output_file = ROOT_DIR / output_file
    output_file.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = [f"flowchart {args.direction}"]
    node_maps: dict[str, dict[str, str]] = {}
    summary: dict[str, object] = {"workflows": []}

    for spec in WORKFLOWS:
        compiled = spec.builder()
        graph_json = compiled.get_graph().to_json()
        sub_lines, node_map = _render_subgraph(spec, graph_json)
        lines.extend(["", *sub_lines])
        node_maps[spec.key] = node_map
        summary["workflows"].append(
            {
                "key": spec.key,
                "title": spec.title,
                "nodes": len(graph_json.get("nodes", [])),
                "edges": len(graph_json.get("edges", [])),
            }
        )

    if not args.no_cross_links:
        cross = _cross_workflow_edges(node_maps)
        if cross:
            lines.extend(["", "%% Cross-workflow orchestration links", *cross])

    lines.extend(
        [
            "",
            "classDef normal fill:#e5e7eb,stroke:#374151,stroke-width:1px,color:#111827;",
            "classDef terminal fill:#d1fae5,stroke:#047857,stroke-width:1.5px,color:#064e3b;",
        ]
    )

    for spec in WORKFLOWS:
        for raw_id, full_id in node_maps.get(spec.key, {}).items():
            if raw_id in {"__start__", "__end__"}:
                lines.append(f"class {full_id} terminal;")
            else:
                lines.append(f"class {full_id} normal;")

    mermaid_text = "\n".join(lines).rstrip() + "\n"
    output_file.write_text(mermaid_text, encoding="utf-8")

    summary_path = output_file.with_suffix(".json")
    png_path = output_file.with_suffix(".png")
    png_warning = None
    if args.png:
        try:
            png_bytes = draw_mermaid_png(
                mermaid_syntax=mermaid_text,
                draw_method=MermaidDrawMethod(args.png_method),
            )
            png_path.write_bytes(png_bytes)
        except Exception as exc:
            png_warning = str(exc)
            fallback_warning = _build_fallback_composite_png(png_path)
            if fallback_warning:
                png_warning = f"{png_warning} | Fallback failed: {fallback_warning}"
            else:
                png_warning = (
                    f"{png_warning} | Created fallback composite PNG from per-workflow images."
                )

    summary["paths"] = {
        "mermaid": str(output_file.relative_to(ROOT_DIR)),
        "json": str(summary_path.relative_to(ROOT_DIR)),
        "png": str(png_path.relative_to(ROOT_DIR)) if png_path.exists() else None,
    }
    if png_warning:
        summary["png_warning"] = png_warning

    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Wrote combined mermaid: {output_file}")
    print(f"Wrote combined summary: {summary_path}")
    if png_path.exists():
        print(f"Wrote combined PNG:    {png_path}")
    elif args.png and png_warning:
        print(f"PNG render warning:    {png_warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
