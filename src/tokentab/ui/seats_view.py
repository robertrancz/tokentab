from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Input, Select, Static

from tokentab.adapters.seats import PRESETS, add_seat, delete_seat, update_seat
from tokentab.models import Seat


class SeatsView(Vertical):
    def compose(self):
        yield Static("Subscription seats are line items. TokenTab does not scrape Cursor, Copilot, or Claude Desktop.")
        yield DataTable(id="seat-table", zebra_stripes=True)
        with Horizontal(classes="form-row"):
            yield Select(
                options=[(s.name, s.name) for s in PRESETS] + [("Custom", "Custom")],
                prompt="Preset",
                id="seat-preset",
            )
            yield Input(placeholder="Name", id="seat-name")
            yield Input(placeholder="Monthly USD", id="seat-usd", type="number")
            yield Input(placeholder="Billing day (1-28)", id="seat-day", value="1")
        yield Input(placeholder="Notes", id="seat-notes")
        with Horizontal(classes="form-row"):
            yield Button("Add", id="seat-add", variant="primary")
            yield Button("Update selected", id="seat-update")
            yield Button("Delete selected", id="seat-delete", variant="error")
        yield Static(id="seat-msg", classes="muted")

    def on_mount(self) -> None:
        table = self.query_one("#seat-table", DataTable)
        table.add_columns("ID", "Name", "Monthly", "Day", "MTD amortized", "Notes")
        table.cursor_type = "row"

    def update_from(self, data: dict) -> None:
        table = self.query_one("#seat-table", DataTable)
        table.clear()
        for seat in data["seats"]:
            table.add_row(
                str(seat["id"]),
                seat["name"],
                f"${seat['monthly_usd']:.2f}",
                str(seat["billing_day"]),
                f"${seat['amortized_mtd']:.2f}",
                seat["notes"],
                key=str(seat["id"]),
            )

    def _selected_id(self) -> int | None:
        table = self.query_one("#seat-table", DataTable)
        if table.cursor_row is None or not table.row_count:
            return None
        row = table.get_row_at(table.cursor_row)
        return int(row[0])

    def _form_seat(self, seat_id: int | None = None) -> Seat | None:
        name = self.query_one("#seat-name", Input).value.strip()
        usd = self.query_one("#seat-usd", Input).value.strip()
        day = self.query_one("#seat-day", Input).value.strip() or "1"
        notes = self.query_one("#seat-notes", Input).value.strip()
        if not name or not usd:
            self.query_one("#seat-msg", Static).update("Name and monthly USD are required.")
            return None
        try:
            monthly = float(usd)
            billing_day = max(1, min(28, int(day)))
        except ValueError:
            self.query_one("#seat-msg", Static).update("USD and billing day must be numbers.")
            return None
        return Seat(id=seat_id, name=name, monthly_usd=monthly, billing_day=billing_day, notes=notes)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "seat-preset":
            return
        if event.value in (Select.BLANK, "Custom"):
            return
        preset = next((s for s in PRESETS if s.name == event.value), None)
        if not preset:
            return
        self.query_one("#seat-name", Input).value = preset.name
        self.query_one("#seat-usd", Input).value = str(preset.monthly_usd)
        self.query_one("#seat-notes", Input).value = preset.notes

    def on_button_pressed(self, event: Button.Pressed) -> None:
        conn = self.app.conn
        if event.button.id == "seat-add":
            seat = self._form_seat()
            if not seat:
                return
            add_seat(conn, seat)
            self.query_one("#seat-msg", Static).update(f"Added {seat.name}.")
        elif event.button.id == "seat-update":
            sid = self._selected_id()
            if sid is None:
                self.query_one("#seat-msg", Static).update("Select a seat first.")
                return
            seat = self._form_seat(sid)
            if not seat:
                return
            update_seat(conn, seat)
            self.query_one("#seat-msg", Static).update(f"Updated {seat.name}.")
        elif event.button.id == "seat-delete":
            sid = self._selected_id()
            if sid is None:
                return
            delete_seat(conn, sid)
            self.query_one("#seat-msg", Static).update("Deleted seat.")
        self.app.refresh_dashboard()
