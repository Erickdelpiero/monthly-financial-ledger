"""Render the monthly report to a PNG (PHASE-2.8 §5-6, PHASE-2.5 §20).

Python owns image generation; n8n only delivers the bytes. The concrete
library was left to implementation (PHASE-2.8 §16) -- matplotlib's Agg backend
needs no display and is already a common dependency. The layout is deliberately
plain: a header block, then a table that grows downward with the number of
movements. No charts, categories, or technical identifiers (PHASE-2.8 §5.3).
"""

from __future__ import annotations

import io
from datetime import timezone
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")  # headless: no display, before pyplot is imported

import matplotlib.pyplot as plt  # noqa: E402

from money_ledger.reports.service import MonthlyReport, debt_line, fmt_amount  # noqa: E402

_LIMA = ZoneInfo("America/Lima")
_COLS = ("Fecha", "Hora", "Persona", "Movimiento", "Monto", "Descripción")
_COL_WIDTHS = (0.11, 0.07, 0.11, 0.21, 0.10, 0.40)
_DESC_MAX = 46          # descriptions longer than this are truncated with an ellipsis
_FIG_W_IN = 10.5
_HEADER_IN = 2.1        # vertical space for the summary block
_ROW_IN = 0.34          # per table row (incl. the header row)
_MARGIN_IN = 0.35


def _local_time(recorded_at) -> str:
    dt = recorded_at
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_LIMA).strftime("%H:%M")


def _clip(text: str, limit: int = _DESC_MAX) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _summary_lines(report: MonthlyReport) -> list[str]:
    if report.balance.direction.value == "no_debt":
        saldo = "No hay deuda pendiente — S/ 0.00"
    else:
        saldo = debt_line(report.balance)
    return ["RESUMEN DEL MES", report.period_label, "", "Saldo actual:", saldo]


def render_monthly_png(report: MonthlyReport) -> bytes:
    rows = report.rows
    n = len(rows)
    table_in = _ROW_IN * (n + 1) if n else 0.5
    total_in = _HEADER_IN + table_in + _MARGIN_IN

    fig = plt.figure(figsize=(_FIG_W_IN, total_in))
    ax = fig.add_axes([0.02, 0.0, 0.96, 1.0])
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    header_frac = _HEADER_IN / total_in
    line_step = 0.30 / total_in
    for i, line in enumerate(_summary_lines(report)):
        ax.text(
            0.0,
            1.0 - 0.24 / total_in - i * line_step,
            line,
            transform=ax.transAxes,
            va="top",
            fontsize=17 if i == 0 else (12 if i in (1, 3) else 13),
            fontweight="bold" if i in (0, 4) else "normal",
        )

    table_top = 1.0 - header_frac
    if n == 0:
        ax.text(0.0, table_top - 0.06, "No hubo movimientos este mes.",
                transform=ax.transAxes, va="top", fontsize=11)
    else:
        cells = [
            [
                r.event_date.strftime("%d/%m/%Y"),
                _local_time(r.recorded_at),
                r.person_name,
                _clip(r.movement_label, 24),
                f"S/ {fmt_amount(r.amount)}",
                _clip(r.description),
            ]
            for r in rows
        ]
        table = ax.table(
            cellText=cells,
            colLabels=list(_COLS),
            colWidths=list(_COL_WIDTHS),
            cellLoc="left",
            bbox=[0.0, 0.02, 1.0, table_top - 0.05],
        )
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        for (row, _col), cell in table.get_celld().items():
            cell.set_edgecolor("#d0d0d0")
            cell.set_linewidth(0.5)
            cell.set_text_props(ha="left")
            cell.get_text().set_clip_on(True)  # keep long text inside its cell
            if row == 0:
                cell.set_text_props(fontweight="bold", ha="left")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()
