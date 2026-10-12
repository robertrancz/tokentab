from __future__ import annotations

from textual.widgets import DataTable, Static
from textual.containers import Vertical


def _usd(value: float) -> str:
    return f"${value:,.4f}" if value < 1 else f"${value:,.2f}"


class ModelsView(Vertical):
    def compose(self):
        yield Static("Billed models this cycle (vendor cost when known, else catalog).")
        yield DataTable(id="model-table", zebra_stripes=True)

    def on_mount(self) -> None:
        table = self.query_one("#model-table", DataTable)
        table.add_columns("Model", "Input", "Output", "Total tokens", "Cost", "$ / 1M")
        table.cursor_type = "row"

    def update_from(self, data: dict) -> None:
        table = self.query_one("#model-table", DataTable)
        table.clear()
        for row in data["by_model"]:
            table.add_row(
                row["model"],
                f"{row['input_tokens']:,}",
                f"{row['output_tokens']:,}",
                f"{row['total_tokens']:,}",
                _usd(row["cost"]),
                f"{row['usd_per_m']:.2f}",
            )
