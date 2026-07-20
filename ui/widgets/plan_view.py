"""Execution Plan View - Side-by-side plan comparison (rebuilt for AnalysisSession)"""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QSplitter,
    QFrame,
    QHeaderView,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush

from core.models import AnalysisSession, PlanComparison, PlanNode


COST_WARN_RATIO = 2.0  # Flag if cost >= 2x baseline
COST_CRIT_RATIO = 10.0  # Critical if cost >= 10x baseline

OPERATION_ICONS = {
    "TABLE ACCESS FULL": "⚠ TABLE ACCESS FULL",
    "TABLE ACCESS BY INDEX ROWID": "✓ TABLE ACCESS (INDEX)",
    "INDEX RANGE SCAN": "✓ INDEX RANGE SCAN",
    "INDEX UNIQUE SCAN": "✓ INDEX UNIQUE SCAN",
    "INDEX FULL SCAN": "~ INDEX FULL SCAN",
    "INDEX SKIP SCAN": "~ INDEX SKIP SCAN",
    "HASH JOIN": "⟗ HASH JOIN",
    "NESTED LOOPS": "⟗ NESTED LOOPS",
    "MERGE JOIN": "⟗ MERGE JOIN",
    "SORT": "↕ SORT",
    "SORT AGGREGATE": "↕ SORT AGGREGATE",
    "SORT ORDER BY": "↕ SORT ORDER BY",
    "SORT GROUP BY": "↕ SORT GROUP BY",
    "HASH GROUP BY": "# HASH GROUP BY",
    "FILTER": "⊃ FILTER",
    "VIEW": "⊡ VIEW",
    "UNION-ALL": "∪ UNION-ALL",
    "SELECT STATEMENT": "► SELECT STATEMENT",
}


def _color_operation(item: QTreeWidgetItem, op: str) -> None:
    """Color the operation column by operation family."""
    if "FULL" in op and "INDEX" not in op:
        item.setForeground(0, QBrush(QColor("#f85149")))
    elif "INDEX" in op:
        item.setForeground(0, QBrush(QColor("#2ea043")))
    elif "SORT" in op:
        item.setForeground(0, QBrush(QColor("#e3b341")))
    elif "HASH JOIN" in op or "MERGE JOIN" in op:
        item.setForeground(0, QBrush(QColor("#79c0ff")))


def _highlight_cost(
    item: QTreeWidgetItem, cost: int | None, baseline_node: PlanNode
) -> None:
    """Highlight the cost cell when it grew past the warn/crit ratios."""
    base_cost = baseline_node.get("cost", 0) or 0
    curr_cost = cost if cost is not None else 0
    try:
        ratio = float(curr_cost) / float(base_cost) if float(base_cost) > 0 else 1
        if ratio >= COST_CRIT_RATIO:
            item.setBackground(1, QBrush(QColor("#3a1a1a")))
            item.setForeground(1, QBrush(QColor("#f85149")))
        elif ratio >= COST_WARN_RATIO:
            item.setBackground(1, QBrush(QColor("#2a2a1a")))
            item.setForeground(1, QBrush(QColor("#e3b341")))
    except (ValueError, TypeError):
        pass


class PlanTree(QTreeWidget):
    def __init__(self, title: str, title_color: str) -> None:
        super().__init__()
        self.setColumnCount(4)
        self.setHeaderLabels(["Operation", "Cost", "Rows", "Bytes"])
        header = self.header()
        assert header is not None  # QTreeWidget always has a header
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.setAlternatingRowColors(True)
        self.setStyleSheet("""
            QTreeWidget {
                background-color: #161616;
                alternate-background-color: #1A1A1A;
                border: 1px solid #2A2A2A;
                border-radius: 4px;
                font-family: 'Consolas', monospace;
                font-size: 11px;
            }
            QTreeWidget::item { padding: 3px 4px; }
            QTreeWidget::item:selected { background-color: #C41200; }
            QHeaderView::section {
                background-color: #1C1C1C;
                color: #888888;
                border: none;
                border-right: 1px solid #2A2A2A;
                padding: 4px 8px;
                font-size: 10px;
                font-weight: bold;
                letter-spacing: 1px;
            }
        """)
        self._title_color = title_color

    def load_plan(
        self,
        plan_nodes: list[PlanNode],
        compare_nodes: list[PlanNode] | None = None,
    ) -> None:
        """
        plan_nodes: list of dicts with keys: operation, cost, rows, bytes, depth, id
        compare_nodes: baseline nodes to compare cost against (optional)
        """
        self.clear()
        if not plan_nodes:
            item = QTreeWidgetItem(["No execution plan data available", "", "", ""])
            item.setForeground(0, QBrush(QColor("#555555")))
            self.addTopLevelItem(item)
            return

        compare_map: dict[str, PlanNode] = {}
        if compare_nodes:
            for n in compare_nodes:
                compare_map[n.get("id", "")] = n

        stack: list[QTreeWidgetItem] = []
        for node in plan_nodes:
            depth = node.get("depth", 0)
            op = node.get("operation", "")
            cost = node.get("cost")
            rows = node.get("rows")
            nbytes = node.get("bytes")

            display_op = OPERATION_ICONS.get(op, op)

            # "cost" is always present in parsed nodes; the "-" branch guards
            # only malformed legacy data. None renders as "None" (unchanged).
            cost_str = str(cost) if "cost" in node else "-"
            rows_str = self._fmt_number(rows)
            bytes_str = self._fmt_bytes(nbytes)

            item = QTreeWidgetItem([display_op, cost_str, rows_str, bytes_str])

            _color_operation(item, op)
            if compare_nodes and node.get("id") in compare_map:
                _highlight_cost(item, cost, compare_map[node["id"]])

            # Build tree hierarchy
            while len(stack) > depth:
                stack.pop()

            if stack:
                stack[-1].addChild(item)
            else:
                self.addTopLevelItem(item)

            stack.append(item)

        self.expandAll()

    def _fmt_number(self, val: int | str | None) -> str:
        if val == "" or val is None:
            return "-"
        try:
            n = int(val)
            if n >= 1_000_000:
                return f"{n / 1_000_000:.1f}M"
            elif n >= 1_000:
                return f"{n / 1_000:.1f}K"
            return str(n)
        except (ValueError, TypeError):
            return str(val)

    def _fmt_bytes(self, val: int | str | None) -> str:
        if val == "" or val is None:
            return "-"
        try:
            n = int(val)
            if n >= 1_048_576:
                return f"{n / 1_048_576:.1f}MB"
            elif n >= 1_024:
                return f"{n / 1_024:.1f}KB"
            return f"{n}B"
        except (ValueError, TypeError):
            return str(val)


class PlanView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self._stats_labels: dict[str, QLabel] = {}
        self.stats_bar = self._build_stats_bar()
        layout.addLayout(self.stats_bar)

        # Plan trees
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left_frame = QFrame()
        ll = QVBoxLayout(left_frame)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(4)
        lt = QLabel("BASELINE PLAN")
        lt.setStyleSheet(
            "color: #2ea043; font-size: 11px; font-weight: bold; letter-spacing: 2px; background: transparent;"
        )
        ll.addWidget(lt)
        self.left_tree = PlanTree("BASELINE", "#2ea043")
        ll.addWidget(self.left_tree)

        right_frame = QFrame()
        rl = QVBoxLayout(right_frame)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(4)
        rt = QLabel("CURRENT PLAN  (cost increases highlighted)")
        rt.setStyleSheet(
            "color: #f85149; font-size: 11px; font-weight: bold; letter-spacing: 2px; background: transparent;"
        )
        rl.addWidget(rt)
        self.right_tree = PlanTree("CURRENT", "#f85149")
        rl.addWidget(self.right_tree)

        splitter.addWidget(left_frame)
        splitter.addWidget(right_frame)
        splitter.setSizes([600, 600])
        layout.addWidget(splitter)

        self._placeholder()

    def _build_stats_bar(self) -> QHBoxLayout:
        """Four stat tiles: baseline/current cost, delta, plan-changed flag."""
        stats_bar = QHBoxLayout()
        for key, label, color in [
            ("baseline_cost", "Baseline Cost", "#2ea043"),
            ("current_cost", "Current Cost", "#f85149"),
            ("cost_delta", "Cost Delta", "#e3b341"),
            ("plan_changed", "Plan Changed", "#79c0ff"),
        ]:
            frame = QFrame()
            frame.setStyleSheet(
                f"background-color: #161616; border: 1px solid #2A2A2A; border-left: 3px solid {color}; border-radius: 4px;"
            )
            fl = QVBoxLayout(frame)
            fl.setContentsMargins(10, 6, 10, 6)
            fl.setSpacing(2)
            title_lbl = QLabel(label.upper())
            title_lbl.setStyleSheet(
                "color: #888888; font-size: 9px; letter-spacing: 1px; background: transparent;"
            )
            val_lbl = QLabel("—")
            val_lbl.setStyleSheet(
                f"color: {color}; font-size: 16px; font-weight: bold; background: transparent;"
            )
            fl.addWidget(title_lbl)
            fl.addWidget(val_lbl)
            self._stats_labels[key] = val_lbl
            stats_bar.addWidget(frame)
        return stats_bar

    def _placeholder(self) -> None:
        self.left_tree.load_plan([])
        self.right_tree.load_plan([])

    def load_results(self, session: AnalysisSession) -> None:
        """Load plan comparison from an AnalysisSession."""
        self.clear()
        if session.plan_comparison:
            self._render_comparison(session.plan_comparison)

    def _render_comparison(self, plan: PlanComparison) -> None:
        """Render a PlanComparison dataclass into the two trees and stats bar."""
        self.left_tree.load_plan(plan.baseline_nodes)
        self.right_tree.load_plan(plan.current_nodes, compare_nodes=plan.baseline_nodes)

        stats = plan.stats
        self._stats_labels["baseline_cost"].setText(
            str(stats.get("baseline_total_cost", "—"))
        )
        self._stats_labels["current_cost"].setText(
            str(stats.get("current_total_cost", "—"))
        )

        delta = stats.get("cost_delta_pct")
        if delta is not None:
            sign = "+" if delta > 0 else ""
            self._stats_labels["cost_delta"].setText(f"{sign}{delta:.0f}%")
            if delta > 100:
                self._stats_labels["cost_delta"].setStyleSheet(
                    "color: #f85149; font-size: 16px; font-weight: bold; background: transparent;"
                )
        else:
            self._stats_labels["cost_delta"].setText("—")

        plan_changed = plan.plan_shape_changed
        self._stats_labels["plan_changed"].setText("YES" if plan_changed else "NO")
        color = "#f85149" if plan_changed else "#2ea043"
        self._stats_labels["plan_changed"].setStyleSheet(
            f"color: {color}; font-size: 16px; font-weight: bold; background: transparent;"
        )

    def clear(self) -> None:
        self._placeholder()
        for lbl in self._stats_labels.values():
            lbl.setText("—")
