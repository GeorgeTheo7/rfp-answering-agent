import asyncio
import os
import shutil
import tempfile
import base64
import pandas as pd
from typing import List, Dict

from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agent.graph import rfp_graph
from app.agent.nodes import is_fail_text
from app.agent.schemas import Answer, Status
from app.evaluation import run_info, run_llm_judge, categorical_eval
from app.excel_io import REVIEW_NOTE_COL, add_answer_status_column, with_run_info, detect_status_columns, create_formatted_excel_bytes, answer_statuses, build_answer_sheets, read_sheets, parse_question_id, find_id_column, find_question_column
from app.config import COST_DECIMALS, DEFAULT_AGENT_MODEL, EXCEL_EXTENSIONS
from app.store import get_vectorstore
from app.ingestion import ingest, IngestWriteError

router = APIRouter()

class FullRow(BaseModel):
    id: str
    category: str
    question: str
    answer: str
    sources: List[str]
    conflicts: str
    review_note: str = ""  # cleared by the frontend when a human edits the answer
    cost: float
    status_values: Dict[str, str] = {}
    status: Status = Status.answered  # the frontend sets "answered" when a human edits the answer

class ExportRequest(BaseModel):
    rows: List[FullRow]
    filename: str

def _reject_xls(filename: str):
    if os.path.splitext(filename)[1].lower() == ".xls":
        raise HTTPException(status_code=400, detail=f"'{filename}' is a legacy .xls file: please save as .xlsx and upload again.")

def _preview_row(ans: Answer) -> dict:
    return {
        "id": ans.question_id,
        "category": ans.category,
        "question": ans.question_text,
        "answer": ans.answer_text,
        "sources": ans.sources_used,
        "conflicts": ans.conflicts,
        "review_note": ans.review_note,
        "cost": round(ans.cost, COST_DECIMALS),
        "status_values": ans.status_values,
        "status": ans.status.value,
    }

@router.get("/api/health")
def health():
    return {"status": "ok"}

@router.get("/api/providers/status")
def get_providers_status():
    return {"openai": bool(os.environ.get("OPENAI_API_KEY"))}

@router.get("/api/documents")
def get_documents():
    try:
        results = get_vectorstore().get(include=["metadatas"])
        if not results or not results.get("metadatas"): return {"documents": []}
        sources = set(meta["source"] for meta in results["metadatas"] if meta and "source" in meta)
        return {"documents": sorted(list(sources))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/documents/upload")
async def upload_knowledge_documents(files: List[UploadFile] = File(...)):
    for file in files:
        _reject_xls(file.filename)  # before any write: no half-ingested batch
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_paths = []
        for file in files:
            temp_path = os.path.join(temp_dir, file.filename)
            with open(temp_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            temp_paths.append(temp_path)
        try:
            result = await ingest(temp_paths)
        except IngestWriteError as e:
            raise HTTPException(status_code=502, detail=f"{e}. Ingestion stopped; see server logs.")

    if not result.written and not result.skipped: raise HTTPException(status_code=400, detail="No data parsed.")
    return {"message": "Success"}

@router.delete("/api/documents/all")
def delete_all_documents():
    results = get_vectorstore().get()
    ids_to_delete = results.get("ids", [])
    if ids_to_delete:
        get_vectorstore().delete(ids_to_delete)
        return {"message": "Deleted"}
    return {"message": "Empty"}

@router.delete("/api/documents/{filename}")
def delete_document(filename: str):
    results = get_vectorstore().get(where={"source": filename})
    ids_to_delete = results.get("ids", [])
    if ids_to_delete:
        get_vectorstore().delete(ids_to_delete)
        return {"message": "Deleted"}
    return {"message": "Not found"}

def _analyze_file(temp_input_path: str, model: str, filename: str) -> dict:
    final_state = rfp_graph.invoke({"rfp_input_path": temp_input_path, "selected_model": model}, config={"max_concurrency": 5})
    answers = final_state["final_answers"]
    preview_data = [_preview_row(ans) for ans in answers]

    sheets = build_answer_sheets(temp_input_path, answers)
    excel_io = create_formatted_excel_bytes(sheets_dict=sheets, statuses=answer_statuses(temp_input_path, sheets, answers))
    excel_base64 = base64.b64encode(excel_io.getvalue()).decode('utf-8')
    export_name = f"Answered_{os.path.splitext(filename)[0]}.xlsx"

    return {"preview_data": preview_data, "excel_base64": excel_base64, "filename": export_name}


@router.post("/api/rfp/analyze")
async def analyze_rfp(file: UploadFile = File(...), model: str = Form(DEFAULT_AGENT_MODEL)):
    _reject_xls(file.filename)
    if not os.environ.get("OPENAI_API_KEY"): raise HTTPException(status_code=400, detail="Missing API Key")
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ('.pdf', *EXCEL_EXTENSIONS): raise HTTPException(status_code=400, detail="Unsupported file type")

    with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
        shutil.copyfileobj(file.file, tmp_file)
        temp_input_path = tmp_file.name

    try:
        # Worker thread: the graph and Excel work are sync and would block every other request.
        return await asyncio.to_thread(_analyze_file, temp_input_path, model, file.filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_input_path): os.remove(temp_input_path)

@router.post("/api/rfp/export_edits")
def export_edited_excel(req: ExportRequest):
    try:
        data = []
        has_notes = any(r.review_note for r in req.rows)
        for r in req.rows:
            d = {"ID": r.id, "Category": r.category, "Question": r.question, "Answer": r.answer,
                 "Sources": "\n".join(r.sources) if r.sources else "", "Conflicts": r.conflicts, "Cost ($)": r.cost}
            if has_notes:
                d[REVIEW_NOTE_COL] = r.review_note
            # Write EVERY chosen dropdown value into the column with its original header
            for col_name, col_val in (r.status_values or {}).items():
                if col_name and col_val:
                    d[col_name] = col_val
            data.append(d)
        df = pd.DataFrame(data)
        
        sheets_dict = {}
        statuses = {}
        for index, row in df.iterrows():
            sheet_name, clean_id = parse_question_id(row["ID"])

            if sheet_name not in sheets_dict: sheets_dict[sheet_name] = []

            clean_row = row.copy()
            clean_row["ID"] = clean_id
            sheets_dict[sheet_name].append(clean_row)
            statuses.setdefault(sheet_name, []).append(req.rows[index].status)

        # Status columns that appeared (may differ per sheet)
        status_cols = []
        for r in req.rows:
            for col_name, col_val in (r.status_values or {}).items():
                if col_name and col_val and col_name not in status_cols:
                    status_cols.append(col_name)

        def _order_columns(sheet_df):
            # Skip status columns that are completely empty in this sheet
            keep_status = []
            for sc in status_cols:
                if sc in sheet_df.columns:
                    is_empty = sheet_df[sc].fillna("").astype(str).str.strip().eq("").all()
                    if is_empty:
                        sheet_df = sheet_df.drop(columns=[sc])
                    else:
                        keep_status.append(sc)
            # Order: ID, Category, Question, Answer, [status...], Sources, Conflicts, [Review note], Cost ($)
            desired = ["ID", "Category", "Question", "Answer"] + keep_status + ["Sources", "Conflicts", REVIEW_NOTE_COL, "Cost ($)"]
            ordered = [c for c in desired if c in sheet_df.columns]
            leftover = [c for c in sheet_df.columns if c not in ordered]
            return sheet_df[ordered + leftover]

        final_sheets_dict = {sn: _order_columns(pd.DataFrame(rows)) for sn, rows in sheets_dict.items()}
        excel_io = create_formatted_excel_bytes(sheets_dict=final_sheets_dict, statuses=statuses)
        return StreamingResponse(excel_io, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={"Content-Disposition": f"attachment; filename={req.filename}", "Access-Control-Expose-Headers": "Content-Disposition"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# 7. ACCURACY EVALUATION ENDPOINT
# ==========================================
def _evaluate_file(temp_input_path: str, model: str, filename: str) -> dict:
    # 1. Run the normal RAG graph to get the Generated Answers
    final_state = rfp_graph.invoke({"rfp_input_path": temp_input_path, "selected_model": model}, config={"max_concurrency": 5})
    answers = final_state["final_answers"]
    by_row = {(ans.sheet, ans.row_index): ans for ans in answers}
    sheets = {name: sheet.fillna("") for name, sheet in build_answer_sheets(temp_input_path, answers).items()}

    # 2. Find the right columns (every sheet has the same columns, see build_answer_sheets)
    columns = next(iter(sheets.values())).columns
    cols = {str(c).lower(): c for c in columns}
    q_col = find_question_column(columns)
    # The RAG always writes the Generated Answer into the "Answer" column
    gen_a_col = "Answer" 
    exp_a_col = next((cols[k] for k in cols if "expected" in k or "truth" in k or "αναμεν" in k), None)
    id_col = find_id_column(columns)

    # --- [NEW] Detect constrained (dropdown / list-value) column ---
    status_map_eval = detect_status_columns(temp_input_path)
    allowed_by_col = {}
    for specs in status_map_eval.values():
        for s in specs:
            allowed_by_col.setdefault(str(s["column"]).strip().lower(), s["allowed_values"])

    # If there is no explicit "Expected" column but there is a dropdown, use it as ground truth
    if not exp_a_col:
        for k in cols:
            if k in allowed_by_col:
                exp_a_col = cols[k]
                break

    if not exp_a_col:
        raise HTTPException(status_code=400, detail="Column named 'Expected Answer' not found in Excel.")

    # Is the expected column categorical? (has fixed list values)
    expected_allowed = allowed_by_col.get(str(exp_a_col).strip().lower(), [])
    is_categorical = len(expected_allowed) > 0

    # In categorical mode the graph may have overwritten the expected column ->
    # read the REAL ground truth from the original file (row-aligned).
    gt_list = []
    if is_categorical:
        orig_sheets = read_sheets(temp_input_path)
        for _sn, odf in orig_sheets.items():
            match_col = next((c for c in odf.columns if str(c).strip().lower() == str(exp_a_col).strip().lower()), None)
            if match_col is not None:
                gt_list.extend(odf[match_col].fillna("").astype(str).tolist())
            else:
                gt_list.extend([""] * len(odf))

    results = []
    total_score = 0
    valid_rows = 0

    # 3. Evaluate each row
    pos = -1  # position across all sheets (row-aligned with gt_list)
    for sheet_name, df in sheets.items():
        # Add the new columns to the DataFrame
        df["LLM Score"] = 0
        df["LLM Reasoning"] = ""

        for index, row in df.iterrows():
            pos += 1
            q_text = str(row[q_col]) if q_col else ""
            generated_text = str(row[gen_a_col]) if gen_a_col in row else ""
            row_id = str(row[id_col]) if id_col else f"Q-{pos+1}"

            # In categorical mode the ground truth comes from the original file
            if is_categorical and pos < len(gt_list):
                expected_text = gt_list[pos]
            else:
                expected_text = str(row[exp_a_col]) if exp_a_col else ""

            if not q_text.strip() or not expected_text.strip(): 
                continue

            if is_categorical:
                # Take the ALREADY classified value of the generated answer from its Answer
                # (the graph already computed it — no extra LLM call here).
                gen_value = ""
                ans = by_row.get((sheet_name, index))
                for kk, vv in (ans.status_values if ans else {}).items():
                    if str(kk).strip().lower() == str(exp_a_col).strip().lower():
                        gen_value = vv
                        break
                eval_result = categorical_eval(gen_value, expected_text, expected_allowed)
                eval_cost = 0.0
                # Restore the ground truth in the expected column (the graph had overwritten it)
                df.at[index, exp_a_col] = expected_text
            else:
                # Semantic judge (as before)
                eval_result, eval_cost = run_llm_judge(q_text, generated_text, expected_text)
            
            df.at[index, "LLM Score"] = eval_result.score
            df.at[index, "LLM Reasoning"] = eval_result.reasoning

            # Take the previous cost and add the evaluation cost
            current_cost = df.at[index, "Cost ($)"] if "Cost ($)" in df.columns and pd.notna(df.at[index, "Cost ($)"]) else 0.0
            df.at[index, "Cost ($)"] = float(current_cost) + eval_cost

            results.append({
                "id": row_id,
                "question": q_text,
                "expected": expected_text,
                "generated": generated_text,
                "score": eval_result.score,
                "reasoning": eval_result.reasoning
            })
            
            # --- [EXCLUSION LOGIC] ---
            # Check whether the Expected Answer contains the fail message (old or new wording)
            # Only count it towards Accuracy if it does NOT
            if not is_fail_text(expected_text):
                total_score += eval_result.score
                valid_rows += 1

    overall_accuracy = round(total_score / valid_rows) if valid_rows > 0 else 0
    # needs_review answers are scored like any other; the count says how many a human should check
    needs_review_count = sum(ans.status == Status.needs_review for ans in answers)

    # 4. Export the final Excel with the scores
    statuses = answer_statuses(temp_input_path, sheets, answers)
    add_answer_status_column(sheets, statuses)
    excel_io = create_formatted_excel_bytes(sheets_dict=sheets, statuses=statuses)
    excel_bytes = with_run_info(excel_io.getvalue(), run_info(model))
    excel_base64 = base64.b64encode(excel_bytes).decode('utf-8')
    export_name = f"Evaluated_{os.path.splitext(filename)[0]}.xlsx"

    return {
        "results": results,
        "overall_accuracy": overall_accuracy,
        "needs_review_count": needs_review_count,
        "excel_base64": excel_base64,
        "filename": export_name
    }


@router.post("/api/rfp/evaluate")
async def evaluate_rfp_accuracy(file: UploadFile = File(...), model: str = Form(DEFAULT_AGENT_MODEL)):
    _reject_xls(file.filename)
    if not os.environ.get("OPENAI_API_KEY"): 
        raise HTTPException(status_code=400, detail="Missing API Key")
    
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in EXCEL_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only Excel files are supported for Evaluation.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
        shutil.copyfileobj(file.file, tmp_file)
        temp_input_path = tmp_file.name

    try:
        return await asyncio.to_thread(_evaluate_file, temp_input_path, model, file.filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_input_path): os.remove(temp_input_path)
