"""Memory routes — browse, delete, and export approved drafts."""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.agents.memory_agent import delete_memory_record, list_all_memory_records

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("")
async def list_memory() -> list[dict]:
    """List all approved memory records (most recent first)."""
    records = list_all_memory_records()
    return [
        {
            "record_id": r.record_id,
            "company_name": r.company_name,
            "persona_title": r.persona_title,
            "draft_subject": r.draft_subject,
            "approved_at": r.approved_at,
            "used_as_example": r.used_as_example,
        }
        for r in records
    ]


@router.delete("/{record_id}", status_code=200)
async def delete_memory(record_id: str) -> dict:
    """Delete a specific memory record."""
    deleted = delete_memory_record(record_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory record not found")
    return {"message": "Memory record deleted", "record_id": record_id}


@router.get("/export")
async def export_memory() -> StreamingResponse:
    """Export all memory records as CSV.

    Returns a CSV file with columns:
    record_id, company_name, persona_title, signal_summary, technical_context,
    draft_subject, draft_body, approved_at, used_as_example
    """
    records = list_all_memory_records()

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "record_id",
            "company_name",
            "persona_title",
            "signal_summary",
            "technical_context",
            "draft_subject",
            "draft_body",
            "approved_at",
            "used_as_example",
        ],
    )
    writer.writeheader()
    for r in records:
        writer.writerow({
            "record_id": r.record_id,
            "company_name": r.company_name,
            "persona_title": r.persona_title,
            "signal_summary": r.signal_summary,
            "technical_context": r.technical_context,
            "draft_subject": r.draft_subject,
            "draft_body": r.draft_body,
            "approved_at": r.approved_at,
            "used_as_example": r.used_as_example,
        })

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=signalforge_memory.csv"},
    )
