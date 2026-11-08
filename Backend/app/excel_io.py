import io
import re
from typing import List

import openpyxl
import pandas as pd
from openpyxl.utils import range_boundaries
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont
from openpyxl.styles import Font, PatternFill, Alignment

from app.agent.schemas import Status
from app.config import COST_DECIMALS, EXCEL_EXTENSIONS

REVIEW_NOTE_COL = "Review note"  # only added when some answer has a note
# Evaluated files only; not "Status", which RFP sheets often use for a dropdown.
ANSWER_STATUS_COL = "Answer status"
RUN_INFO_SHEET = "Run info"  # evaluated files: Field/Value rows (models, settings, time, commit)
STATUS_FILLS = {Status.not_found: "FFC7CE", Status.error: "FFC7CE", Status.needs_review: "FFEB9C"}

# Normalized header names of an ID column, highest priority first.
ID_HEADERS = (
    "id", "question id", "question_id", "qid", "q id", "requirement id", "req id", "control id",
    "ref", "ref no", "reference no", "question no", "question number", "q no", "item no",
    "s/n", "sr no", "#", "α/α", "no", "nr", "number",
)

def _normalize_header(header) -> str:
    return " ".join(str(header).split()).lower().rstrip(".:")

def find_id_column(columns):
    """Returns the ID column, matching whole header names (never substrings), or None.
    A bare "No" next to a "Yes" column is a tick-box answer, not an ID."""
    normalized = {}
    for col in columns:
        normalized.setdefault(_normalize_header(col), col)
    for header in ID_HEADERS:
        if header == "no" and "yes" in normalized:
            continue
        if header in normalized:
            return normalized[header]
    return None

def is_id_header(header) -> bool:
    return _normalize_header(header) in ID_HEADERS

def find_question_column(columns):
    """First column whose header mentions a question, skipping ID headers like "Question ID"."""
    for col in columns:
        name = str(col).lower()
        if ("question" in name or "ερώτηση" in name) and not is_id_header(col):
            return col
    return None

def read_sheets(input_path: str) -> dict:
    """{sheet_name: DataFrame}. The only read of an RFP workbook: Question.row_index is this
    DataFrame's index, so extraction and write-back must see the same rows."""
    return pd.read_excel(input_path, sheet_name=None)

def resolve_id_column(df: pd.DataFrame, sheet_name: str):
    """find_id_column for a sheet, or None (row IDs Q1, Q2...) if its IDs would collide:
    the preview and export_edits need one ID per question."""
    id_col = find_id_column(df.columns)
    if id_col is None:
        return None
    ids = [str(v) if pd.notna(v) else f"Q{i+1}" for i, v in enumerate(df[id_col])]
    if len(set(ids)) < len(ids):
        print(f"[WARNING] Sheet '{sheet_name}': column '{id_col}' has duplicate IDs -> using row IDs (Q1, Q2...).")
        return None
    return id_col

# ==========================================
# 1c. EXCEL DROPDOWN (DATA-VALIDATION) DETECTION
# ==========================================
def _parse_dv_values(dv, wb, ws) -> List[str]:
    """Extracts the allowed values of a data-validation 'list'.
    Covers: inline list ("a,b,c"), named range, and range reference (Sheet!$A$1:$A$5)."""
    f = (dv.formula1 or "").strip()
    if not f:
        return []
    # 1) Inline list:  "a,b,c"
    if f.startswith('"') and f.endswith('"'):
        return [v.strip() for v in f[1:-1].split(",") if v.strip()]
    # 2) Named range
    try:
        names = getattr(wb, "defined_names", {})
        dn = names[f] if f in names else None
        if dn is not None:
            vals = []
            for title, coord in dn.destinations:
                tws = wb[title]
                for r in tws[coord]:
                    cells = r if isinstance(r, tuple) else (r,)
                    for c in cells:
                        if c.value is not None and str(c.value).strip():
                            vals.append(str(c.value).strip())
            if vals:
                return vals
    except Exception:
        pass
    # 3) Range reference:  Sheet!$A$1:$A$5  or  $A$1:$A$5
    try:
        ref = f.lstrip("=")
        if "!" in ref:
            sheet_part, coord = ref.split("!", 1)
            tws = wb[sheet_part.strip().strip("'")]
        else:
            tws, coord = ws, ref
        coord = coord.replace("$", "")
        vals = []
        for r in tws[coord]:
            cells = r if isinstance(r, tuple) else (r,)
            for c in cells:
                if c.value is not None and str(c.value).strip():
                    vals.append(str(c.value).strip())
        return vals
    except Exception:
        return []

def detect_status_columns(input_path: str) -> dict:
    """Returns {sheet_name: [ {"column": <header>, "allowed_values": [...]}, ... ]}
    reading ALL dropdowns (data-validation type='list') of every sheet.
    For anything but EXCEL_EXTENSIONS returns {}."""
    result = {}
    if not input_path.lower().endswith(EXCEL_EXTENSIONS):
        return result
    try:
        wb = openpyxl.load_workbook(input_path)
    except Exception as e:
        print(f"[WARNING] detect_status_columns could not open workbook: {e}")
        return result
    for ws in wb.worksheets:
        if ws.sheet_state != "visible":
            continue
        # header text per column index (row 1)
        headers = {}
        for cell in ws[1]:
            if cell.value is not None and str(cell.value).strip():
                headers[cell.column] = str(cell.value).strip()
        sheet_specs = []
        seen_cols = set()
        for dv in ws.data_validations.dataValidation:
            if dv.type != "list":
                continue
            allowed = _parse_dv_values(dv, wb, ws)
            if not allowed:
                # Dropdown exists but its values can't be read (e.g. external reference)
                for rng in str(dv.sqref).split():
                    try:
                        mc, _, _, _ = range_boundaries(rng)
                    except Exception:
                        continue
                    h = headers.get(mc)
                    if h:
                        print(f"[WARNING] Sheet '{ws.title}': dropdown found in column '{h}', "
                              f"but its values can NOT be read (likely external reference) -> skipped.")
                continue
            for rng in str(dv.sqref).split():
                try:
                    min_col, _, _, _ = range_boundaries(rng)
                except Exception:
                    continue
                header = headers.get(min_col)
                # Keep EVERY dropdown column of the sheet (each once).
                if header and header not in seen_cols:
                    seen_cols.add(header)
                    sheet_specs.append({"column": header, "allowed_values": allowed})
        if sheet_specs:
            result[ws.title] = sheet_specs
    wb.close()
    return result

def _write_to_sheet(writer, sheet_name, df, row_statuses=()):
    safe_sheet_name = str(sheet_name)[:31].replace(":", "").replace("/", "").replace("\\", "").replace("?", "").replace("*", "").replace("[", "").replace("]", "")
    if not safe_sheet_name: safe_sheet_name = "Sheet"

    if "Cost ($)" in df.columns:
        # to_numeric first: round() silently skips object-dtype columns (export_edits builds those).
        df = df.assign(**{"Cost ($)": pd.to_numeric(df["Cost ($)"], errors="coerce").round(COST_DECIMALS)})
    df.to_excel(writer, index=False, sheet_name=safe_sheet_name)
    worksheet = writer.sheets[safe_sheet_name]

    id_col = find_id_column(df.columns)
    for idx, col_name in enumerate(df.columns):
        col_letter = openpyxl.utils.get_column_letter(idx + 1)
        name_lower = str(col_name).lower()
        if col_name == id_col: width = 15
        elif "category" in name_lower: width = 25
        elif "question" in name_lower or "ερώτηση" in name_lower: width = 50
        elif "answer" in name_lower or "απάντηση" in name_lower: width = 80
        elif "source" in name_lower or "πηγές" in name_lower: width = 35
        elif "conflict" in name_lower or "συγκρούσεις" in name_lower: width = 45 
        elif col_name == REVIEW_NOTE_COL: width = 45
        elif "cost" in name_lower: width = 15
        elif "score" in name_lower: width = 15
        elif "reasoning" in name_lower: width = 50
        else: width = 20
        worksheet.column_dimensions[col_letter].width = width

    header_colors = ['DDEBF7', 'E2EFDA', 'FFF2CC', 'FCE4D6', 'EDEDED', 'E1D5E7', 'FFCCCC']
    for col_num in range(1, len(df.columns) + 1):
        cell = worksheet.cell(row=1, column=col_num)
        cell.font = Font(bold=True, size=12)
        color = header_colors[(col_num - 1) % len(header_colors)]
        cell.fill = PatternFill(start_color=color, end_color=color, fill_type='solid')
        cell.alignment = Alignment(horizontal='center', vertical='center')

    ans_col_idx = list(df.columns).index("Answer") + 1 if "Answer" in df.columns else None

    for row_pos, row in enumerate(worksheet.iter_rows(min_row=2, max_row=worksheet.max_row)):
        status = row_statuses[row_pos] if row_pos < len(row_statuses) else None
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical='top')
            if cell.column == ans_col_idx and status in STATUS_FILLS:
                color = STATUS_FILLS[status]
                cell.fill = PatternFill(start_color=color, end_color=color, fill_type='solid')
            if isinstance(cell.value, str) and '**' in cell.value:
                parts = cell.value.split('**')
                rich_string = CellRichText()
                bold_font = InlineFont(b=True)
                for idx, part in enumerate(parts):
                    if not part: continue
                    if idx % 2 == 1: rich_string.append(TextBlock(font=bold_font, text=part))
                    else: rich_string.append(part)
                cell.value = rich_string

def create_formatted_excel_bytes(df: pd.DataFrame = None, sheets_dict: dict = None, statuses: dict = None) -> io.BytesIO:
    """statuses: {sheet_name: [Status or None per row]} colours the Answer column."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        if sheets_dict is not None:
            for sheet_name, sheet_df in sheets_dict.items():
                _write_to_sheet(writer, sheet_name, sheet_df, (statuses or {}).get(sheet_name, ()))
        elif df is not None:
            _write_to_sheet(writer, 'RFP Responses', df)
    output.seek(0)
    return output

def _write_answer_to_row(df: pd.DataFrame, index, ans):
    df.at[index, "Answer"] = ans.answer_text
    df.at[index, "Sources"] = "\n".join(ans.sources_used) if ans.sources_used else ""
    df.at[index, "Conflicts"] = ans.conflicts
    if REVIEW_NOTE_COL in df.columns:
        df.at[index, REVIEW_NOTE_COL] = ans.review_note
    df.at[index, "Cost ($)"] = ans.cost
    # Write each chosen value into its ORIGINAL dropdown column
    for col_name, col_val in ans.status_values.items():
        if not col_val:
            continue
        target_col = col_name
        if target_col not in df.columns:
            for c in df.columns:
                if str(c).strip().lower() == str(col_name).strip().lower():
                    target_col = c
                    break
        if target_col in df.columns:
            if df[target_col].dtype != object:
                df[target_col] = df[target_col].astype(object)
            df.at[index, target_col] = col_val

def _excel_answer_sheets(input_path: str, answers: list) -> dict:
    by_row = {(ans.sheet, ans.row_index): ans for ans in answers}
    has_notes = any(ans.review_note for ans in answers)
    frames = {}
    for sheet_name, df in read_sheets(input_path).items():
        if "Answer" not in df.columns: df["Answer"] = ""
        if "Sources" not in df.columns: df["Sources"] = ""
        if "Conflicts" not in df.columns: df["Conflicts"] = ""
        if "Cost ($)" not in df.columns: df["Cost ($)"] = 0.0

        df["Answer"] = df["Answer"].astype(object)
        df["Sources"] = df["Sources"].astype(object)
        df["Conflicts"] = df["Conflicts"].astype(object)
        df["Cost ($)"] = df["Cost ($)"].astype(float)
        if has_notes and REVIEW_NOTE_COL not in df.columns:
            df.insert(df.columns.get_loc("Conflicts") + 1, REVIEW_NOTE_COL, "")

        for index in df.index:
            ans = by_row.get((sheet_name, index))
            if ans is not None:
                _write_answer_to_row(df, index, ans)
        frames[sheet_name] = df

    # concat + split kept on purpose (docs/SPEC.md Later): every sheet gets the columns of all
    # sheets, int IDs can become floats, sheets without rows are dropped. Row index is preserved.
    combined = pd.concat(frames)
    return {name: group.droplevel(0) for name, group in combined.groupby(level=0, sort=False)}

def _pdf_answer_sheets(answers: list) -> dict:
    has_notes = any(ans.review_note for ans in answers)
    return {"RFP Responses": pd.DataFrame([{
        "Question ID": ans.question_id,
        "Category": ans.assigned_analyst,
        "Question": ans.question_text,
        "Answer": ans.answer_text,
        "Sources": "\n".join(ans.sources_used) if ans.sources_used else "",
        "Conflicts": ans.conflicts,
        **({REVIEW_NOTE_COL: ans.review_note} if has_notes else {}),
        "Cost ($)": ans.cost,
    } for ans in answers])}

def build_answer_sheets(input_path: str, answers: list) -> dict:
    """{sheet_name: DataFrame} ready for create_formatted_excel_bytes. Excel: the original
    sheets with each Answer written to its own row. PDF: one sheet, one row per Answer."""
    if input_path.lower().endswith(EXCEL_EXTENSIONS):
        return _excel_answer_sheets(input_path, answers)
    return _pdf_answer_sheets(answers)

def answer_statuses(input_path: str, sheets: dict, answers: list) -> dict:
    """{sheet_name: [Status or None per row]} for build_answer_sheets output; None = no Answer."""
    if input_path.lower().endswith(EXCEL_EXTENSIONS):
        by_row = {(ans.sheet, ans.row_index): ans.status for ans in answers}
        return {name: [by_row.get((name, index)) for index in df.index] for name, df in sheets.items()}
    return {"RFP Responses": [ans.status for ans in answers]}

def parse_question_id(raw_id):
    """"[<sheet>] <id>" -> (sheet, id). Without brackets -> ("RFP Responses", raw_id)."""
    match = re.match(r'^\[(.*?)\]\s*(.*)', str(raw_id))
    if match:
        return match.group(1), match.group(2)
    return "RFP Responses", raw_id


def write_run_info(wb, info: dict):
    """Replaces the Run info sheet (last sheet) with one Field/Value row per item."""
    if RUN_INFO_SHEET in wb.sheetnames:
        del wb[RUN_INFO_SHEET]
    ws = wb.create_sheet(RUN_INFO_SHEET)
    ws.append(["Field", "Value"])
    for field, value in info.items():
        ws.append([field, value])
    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 45

def read_run_info(wb) -> dict:
    """{field: value} from the Run info sheet, {} if the workbook has none (older files)."""
    if RUN_INFO_SHEET not in wb.sheetnames:
        return {}
    rows = wb[RUN_INFO_SHEET].iter_rows(min_row=2, values_only=True)
    return {str(r[0]): "" if r[1] is None else str(r[1]) for r in rows if r and r[0] is not None}

def with_run_info(xlsx: bytes, info: dict) -> bytes:
    wb = openpyxl.load_workbook(io.BytesIO(xlsx))
    write_run_info(wb, info)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def add_answer_status_column(sheets: dict, statuses: dict):
    """Inserts ANSWER_STATUS_COL right after "Answer" (statuses as from answer_statuses; "" = no Answer)."""
    for name, df in sheets.items():
        values = [s.value if s else "" for s in statuses.get(name, [None] * len(df))]
        if ANSWER_STATUS_COL in df.columns:
            df[ANSWER_STATUS_COL] = values
        else:
            df.insert(df.columns.get_loc("Answer") + 1, ANSWER_STATUS_COL, values)
