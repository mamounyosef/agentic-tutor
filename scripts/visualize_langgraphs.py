#!/usr/bin/env python3
"""Export LangGraph workflow diagrams for all project graphs.

Outputs, per workflow:
- Mermaid source (.mmd)
- Graph JSON (.json)
- ASCII graph (.txt, when supported by dependencies)
- Optional PNG (.png)

Run from repo root (recommended):
    backend\\venv\\Scripts\\python scripts\\visualize_langgraphs.py
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Import after adjusting sys.path.
from langchain_core.runnables.graph import MermaidDrawMethod

from app.agents.constructor.coordinator.agent import build_coordinator_graph
from app.agents.constructor.ingestion.agent import build_ingestion_graph
from app.agents.constructor.quiz_gen.agent import build_quiz_gen_graph
from app.agents.constructor.structure.agent import build_structure_graph
from app.agents.constructor.validation.agent import build_validation_graph
from app.agents.tutor.graph import build_tutor_graph


@dataclass(frozen=True)
class WorkflowSpec:
    name: str
    description: str
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
    WorkflowSpec(
        name="constructor_coordinator",
        description="Top-level constructor coordinator graph",
        builder=_build_constructor_coordinator,
    ),
    WorkflowSpec(
        name="constructor_ingestion",
        description="Constructor ingestion sub-agent graph",
        builder=_build_constructor_ingestion,
    ),
    WorkflowSpec(
        name="constructor_structure",
        description="Constructor structure sub-agent graph",
        builder=_build_constructor_structure,
    ),
    WorkflowSpec(
        name="constructor_quiz_gen",
        description="Constructor quiz-generation sub-agent graph",
        builder=_build_constructor_quiz_gen,
    ),
    WorkflowSpec(
        name="constructor_validation",
        description="Constructor validation sub-agent graph",
        builder=_build_constructor_validation,
    ),
    WorkflowSpec(
        name="tutor_coordinator",
        description="Tutor coordinator graph",
        builder=_build_tutor,
    ),
]


def _write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _write_json(path: Path, content: object) -> None:
    path.write_text(json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8")


def export_workflow(
    spec: WorkflowSpec,
    output_dir: Path,
    include_png: bool,
    png_method: MermaidDrawMethod,
) -> dict:
    compiled = spec.builder()
    visual_graph = compiled.get_graph()

    mermaid = visual_graph.draw_mermaid()
    graph_json = visual_graph.to_json()

    workflow_dir = output_dir / spec.name
    workflow_dir.mkdir(parents=True, exist_ok=True)

    mermaid_path = workflow_dir / f"{spec.name}.mmd"
    json_path = workflow_dir / f"{spec.name}.json"
    ascii_path = workflow_dir / f"{spec.name}.txt"
    png_path = workflow_dir / f"{spec.name}.png"

    _write_text(mermaid_path, mermaid)
    _write_json(json_path, graph_json)

    ascii_error = None
    try:
        ascii_graph = visual_graph.draw_ascii()
        _write_text(ascii_path, ascii_graph)
    except Exception as exc:  # pragma: no cover - optional dependency path
        ascii_error = str(exc)

    png_error = None
    if include_png:
        try:
            png_bytes = visual_graph.draw_mermaid_png(draw_method=png_method)
            png_path.write_bytes(png_bytes)
        except Exception as exc:  # pragma: no cover - depends on runtime/network
            png_error = str(exc)

    nodes = graph_json.get("nodes", []) if isinstance(graph_json, dict) else []
    edges = graph_json.get("edges", []) if isinstance(graph_json, dict) else []

    return {
        "name": spec.name,
        "description": spec.description,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "paths": {
            "mermaid": str(mermaid_path.relative_to(ROOT_DIR)),
            "json": str(json_path.relative_to(ROOT_DIR)),
            "ascii": str(ascii_path.relative_to(ROOT_DIR)) if ascii_path.exists() else None,
            "png": str(png_path.relative_to(ROOT_DIR)) if png_path.exists() else None,
        },
        "warnings": {
            "ascii": ascii_error,
            "png": png_error,
        },
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default="artifacts/langgraph_viz",
        help="Output directory (repo-relative or absolute). Default: artifacts/langgraph_viz",
    )
    parser.add_argument(
        "--png",
        action="store_true",
        help="Also render PNG for each workflow graph.",
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

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT_DIR / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    png_method = MermaidDrawMethod(args.png_method)

    summary = {
        "output_dir": str(output_dir.relative_to(ROOT_DIR)),
        "workflows": [],
    }

    for spec in WORKFLOWS:
        info = export_workflow(
            spec=spec,
            output_dir=output_dir,
            include_png=bool(args.png),
            png_method=png_method,
        )
        summary["workflows"].append(info)
        print(f"[ok] {spec.name}: {info['node_count']} nodes, {info['edge_count']} edges")

    summary_path = output_dir / "summary.json"
    _write_json(summary_path, summary)

    index_lines = [
        "# LangGraph Workflow Exports",
        "",
        f"Output directory: `{summary['output_dir']}`",
        "",
    ]
    for wf in summary["workflows"]:
        index_lines.append(f"## {wf['name']}")
        index_lines.append(wf["description"])
        index_lines.append("")
        index_lines.append(f"- Nodes: {wf['node_count']}")
        index_lines.append(f"- Edges: {wf['edge_count']}")
        index_lines.append(f"- Mermaid: `{wf['paths']['mermaid']}`")
        index_lines.append(f"- JSON: `{wf['paths']['json']}`")
        if wf["paths"]["ascii"]:
            index_lines.append(f"- ASCII: `{wf['paths']['ascii']}`")
        if wf["paths"]["png"]:
            index_lines.append(f"- PNG: `{wf['paths']['png']}`")
        if wf["warnings"]["ascii"]:
            index_lines.append(f"- ASCII warning: `{wf['warnings']['ascii']}`")
        if wf["warnings"]["png"]:
            index_lines.append(f"- PNG warning: `{wf['warnings']['png']}`")
        index_lines.append("")

    index_path = output_dir / "README.md"
    _write_text(index_path, "\n".join(index_lines).rstrip() + "\n")

    print(f"\nWrote summary: {summary_path}")
    print(f"Wrote index:   {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

