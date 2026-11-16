"""Writes the return workbook: the form, the variance sheet and the check results."""

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .lines import RETURN_LINES

BOLD = Font(bold=True)
HEADER_FILL = PatternFill("solid", fgColor="DDE3EA")
SECTION_FILL = PatternFill("solid", fgColor="F2F4F7")
WARN_FILL = PatternFill("solid", fgColor="FCE8B2")
MONEY = "#,##0.00"
COUNT = "#,##0"
PERCENT = "+0.0%;-0.0%;0.0%"


def _header(ws, row, titles):
    for col, title in enumerate(titles, start=1):
        cell = ws.cell(row=row, column=col, value=title)
        cell.font = BOLD
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="center")


def _widths(ws, widths):
    for col, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col)].width = width


def write_workbook(path, period, run_id, generated_at, lines, variance_rows, checks, threshold):
    wb = Workbook()

    # ---- the form --------------------------------------------------------
    ws = wb.active
    ws.title = "PS-M1"
    ws["A1"] = "Form PS-M1: Monthly Payment Systems Return"
    ws["A1"].font = Font(bold=True, size=14)
    meta = [
        ("Reporting institution", "Zaffre Wallet (fictional)"),
        ("Regulator", "Central Bank of Meridia (fictional)"),
        ("Reporting period", period.label),
        ("Currency", "MRD"),
        ("Generated (UTC)", generated_at),
        ("Run ID", run_id),
    ]
    for offset, (key, value) in enumerate(meta):
        ws.cell(row=3 + offset, column=1, value=key).font = BOLD
        ws.cell(row=3 + offset, column=2, value=value)

    row = 3 + len(meta) + 1
    _header(ws, row, ["Line", "Description", "Count", "Value (MRD)"])
    current_section = None
    for code, (section, label, has_value) in RETURN_LINES.items():
        if section != current_section:
            row += 1
            cell = ws.cell(row=row, column=1, value=section)
            cell.font = BOLD
            for col in range(1, 5):
                ws.cell(row=row, column=col).fill = SECTION_FILL
            current_section = section
        row += 1
        count, value_minor = lines.get(code, (0, 0 if has_value else None))
        ws.cell(row=row, column=1, value=code)
        ws.cell(row=row, column=2, value=label)
        ws.cell(row=row, column=3, value=count).number_format = COUNT
        if has_value:
            ws.cell(row=row, column=4, value=value_minor / 100).number_format = MONEY
        if code == "B9":
            for col in range(1, 5):
                ws.cell(row=row, column=col).font = BOLD
    _widths(ws, [24, 40, 14, 18])

    # ---- variance against the prior period -------------------------------
    vs = wb.create_sheet("Variance")
    _header(vs, 1, ["Line", "Description", "Measure", "This period", "Prior period", "Change"])
    for i, (code, measure, current, prior, change) in enumerate(variance_rows, start=2):
        is_value = measure == "value"
        fmt = MONEY if is_value else COUNT
        vs.cell(row=i, column=1, value=code)
        vs.cell(row=i, column=2, value=RETURN_LINES[code][1])
        vs.cell(row=i, column=3, value=measure)
        vs.cell(row=i, column=4, value=current / 100 if is_value else current).number_format = fmt
        if prior is not None:
            vs.cell(row=i, column=5, value=prior / 100 if is_value else prior).number_format = fmt
        if change is not None:
            cell = vs.cell(row=i, column=6, value=change)
            cell.number_format = PERCENT
            if abs(change) > threshold:
                for col in range(1, 7):
                    vs.cell(row=i, column=col).fill = WARN_FILL
    _widths(vs, [8, 40, 10, 18, 18, 12])

    # ---- what was checked before release ---------------------------------
    cs = wb.create_sheet("Checks")
    _header(cs, 1, ["Check", "Severity", "Result", "Detail"])
    for i, check in enumerate(checks, start=2):
        result = "PASS" if check.passed else ("REVIEW" if check.severity == "warn" else "FAIL")
        cs.cell(row=i, column=1, value=check.name)
        cs.cell(row=i, column=2, value=check.severity)
        cs.cell(row=i, column=3, value=result)
        cs.cell(row=i, column=4, value=check.detail)
        if not check.passed:
            for col in range(1, 5):
                cs.cell(row=i, column=col).fill = WARN_FILL
    _widths(cs, [30, 10, 10, 90])

    wb.save(str(path))
