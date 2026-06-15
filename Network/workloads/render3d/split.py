from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from .render3d_workload import load_scene, write_json
except ImportError:  # pragma: no cover - direct script execution
    from render3d_workload import load_scene, write_json


@dataclass
class SplitNode:
    fragment_index: int
    y_start: int
    y_end: int
    depth: int
    complexity_score: int
    parent_index: int | None = None
    children: list["SplitNode"] = field(default_factory=list)

    @property
    def is_leaf(self) -> bool:
        return not self.children


def image_size(scene: dict[str, Any]) -> tuple[int, int]:
    image = scene.get("image") if isinstance(scene.get("image"), dict) else {}
    width = max(16, min(2048, int(image.get("width", 320))))
    height = max(16, min(2048, int(image.get("height", 200))))
    return width, height


def estimate_complexity(scene: dict[str, Any], width: int, y_start: int, y_end: int) -> int:
    objects = scene.get("objects") if isinstance(scene.get("objects"), list) else []
    sphere_count = sum(1 for obj in objects if isinstance(obj, dict) and obj.get("type") == "sphere")
    return max(1, width * max(1, y_end - y_start) * max(1, sphere_count))


def build_split_tree(
    scene: dict[str, Any],
    width: int,
    y_start: int,
    y_end: int,
    threshold: int,
    max_depth: int,
    next_index: list[int],
    parent_index: int | None = None,
    depth: int = 0,
) -> SplitNode:
    fragment_index = next_index[0]
    next_index[0] += 1
    complexity = estimate_complexity(scene, width, y_start, y_end)
    node = SplitNode(fragment_index, y_start, y_end, depth, complexity, parent_index)
    if complexity > threshold and depth < max_depth and (y_end - y_start) >= 2:
        mid = (y_start + y_end) // 2
        node.children = [
            build_split_tree(scene, width, y_start, mid, threshold, max_depth, next_index, fragment_index, depth + 1),
            build_split_tree(scene, width, mid, y_end, threshold, max_depth, next_index, fragment_index, depth + 1),
        ]
    return node


def flatten_tree(root: SplitNode) -> list[SplitNode]:
    nodes = [root]
    for child in root.children:
        nodes.extend(flatten_tree(child))
    return nodes


def leaf_nodes(root: SplitNode) -> list[SplitNode]:
    return [node for node in flatten_tree(root) if node.is_leaf]


def tree_to_dict(node: SplitNode) -> dict[str, Any]:
    return {
        "fragment_index": node.fragment_index,
        "parent_index": node.parent_index,
        "y_start": node.y_start,
        "y_end": node.y_end,
        "depth": node.depth,
        "complexity_score": node.complexity_score,
        "is_leaf": node.is_leaf,
        "children": [tree_to_dict(child) for child in node.children],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Split a render3d scene into recursive horizontal fragments.")
    parser.add_argument("scene")
    parser.add_argument("--output", required=True)
    parser.add_argument("--complexity-threshold", type=int, default=60_000)
    parser.add_argument("--max-depth", type=int, default=4)
    args = parser.parse_args()

    scene_path = Path(args.scene).resolve()
    scene = load_scene(scene_path)
    width, height = image_size(scene)
    root = build_split_tree(scene, width, 0, height, args.complexity_threshold, args.max_depth, [0])
    leaves = leaf_nodes(root)
    payload = {
        "schema_version": 1,
        "workload": "render3d",
        "scene": str(scene_path),
        "image": {"width": width, "height": height},
        "complexity_threshold": args.complexity_threshold,
        "max_depth": args.max_depth,
        "split_tree": tree_to_dict(root),
        "fragments": [tree_to_dict(node) for node in leaves],
    }
    write_json(Path(args.output).resolve(), payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
