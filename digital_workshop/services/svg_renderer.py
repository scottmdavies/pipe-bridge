"""Render drawing objects to a self-contained SVG string."""

from __future__ import annotations

from collections.abc import Sequence
from html import escape

from digital_workshop.domain.models import BoundingBox, DrawingObject

STYLE = (
    ".obj{stroke:#6b7785;fill:none;stroke-width:1.2px;cursor:pointer}"
    ".obj text{fill:#6b7785;stroke:none}"
    ".obj:hover{stroke:#1c7ed6}.obj:hover text{fill:#1c7ed6}"
    ".obj.sel{stroke:#e8590c;stroke-width:2.6px}.obj.sel text{fill:#e8590c}"
    ".obj.hidden{display:none}"
    ".obj *{vector-effect:non-scaling-stroke}"
)
PADDING_RATIO = 0.05


class SvgRenderer:
    """Turns :class:`DrawingObject` primitives into SVG markup.

    Each object becomes ``<g class="obj" data-id=... data-layer=...>`` so that the
    browser can toggle ``sel`` / ``hidden`` classes without re-rendering. The drawing
    is y-flipped (DXF is y-up, SVG is y-down) and the viewBox is exposed on the root.
    """

    def render(
        self,
        objects: Sequence[DrawingObject],
        bbox: BoundingBox | None,
        selected_ids: frozenset[int] = frozenset(),
        hidden_layers: frozenset[str] = frozenset(),
    ) -> str:
        """Render objects to an SVG document string."""
        view = bbox or BoundingBox(0, 0, 100, 100)
        pad = max(view.width, view.height, 1.0) * PADDING_RATIO
        min_x, min_y = view.min_x - pad, -(view.max_y + pad)
        width, height = view.width + 2 * pad, view.height + 2 * pad
        view_box = f"{min_x:.4f} {min_y:.4f} {width:.4f} {height:.4f}"
        body = "".join(self._render_object(o, selected_ids, hidden_layers) for o in objects)
        return (
            f'<svg id="dxf-svg" xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="{view_box}" data-home="{view_box}" '
            f'style="width:100%;height:100%;background:#fff" '
            f'preserveAspectRatio="xMidYMid meet">'
            f"<style>{STYLE}</style>"
            f'<g transform="scale(1,-1)">{body}</g></svg>'
        )

    def _render_object(
        self,
        obj: DrawingObject,
        selected_ids: frozenset[int],
        hidden_layers: frozenset[str],
    ) -> str:
        classes = ["obj"]
        if obj.id in selected_ids:
            classes.append("sel")
        if obj.layer in hidden_layers:
            classes.append("hidden")
        shapes = "".join(self._render_primitive(p) for p in obj.primitives)
        return (
            f'<g class="{" ".join(classes)}" data-id="{obj.id}" '
            f'data-layer="{escape(obj.layer, quote=True)}">{shapes}</g>'
        )

    @staticmethod
    def _render_primitive(primitive: dict) -> str:
        if primitive["t"] == "text":
            x, y = primitive["p"]
            return (
                f'<text transform="translate({x} {y}) scale(1 -1)" '
                f'font-size="{primitive["h"]}">{escape(primitive["s"])}</text>'
            )
        points = " ".join(f"{x},{y}" for x, y in primitive["pts"])
        tag = "polygon" if primitive.get("closed") else "polyline"
        return f'<{tag} points="{points}"/>'
