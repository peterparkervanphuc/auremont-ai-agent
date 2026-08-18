from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.core.deps import require_role
from backend.core.enums import UserRole
from backend.core.mysql_client import get_db
from backend.models.chat_session import ChatSession
from backend.models.conflict_flag import ConflictFlag
from backend.models.document import Document
from backend.models.feedback import Feedback
from backend.models.hitl_log import HitlLog
from backend.models.message import Message
from backend.models.project import Project
from backend.models.user import User

router = APIRouter(prefix="/admin/stats", tags=["Admin Stats"], dependencies=[Depends(require_role(UserRole.ADMIN))])

TREND_DAYS = 14


def _cumulative_counts(created_dates: list[date], days: int) -> list[int]:
    """Total rows that existed by the end of each day, used to render growth trend charts."""
    start = date.today() - timedelta(days=days - 1)
    per_day: dict[date, int] = {}
    for d in created_dates:
        per_day[d] = per_day.get(d, 0) + 1

    running = sum(count for d, count in per_day.items() if d < start)
    result = []
    for i in range(days):
        day = start + timedelta(days=i)
        running += per_day.get(day, 0)
        result.append(running)
    return result


def _open_conflicts_trend(rows: list[tuple[date, date | None]], days: int) -> list[int]:
    """Number of flags still open as of the end of each day (created, not yet resolved by that point)."""
    start = date.today() - timedelta(days=days - 1)
    result = []
    for i in range(days):
        day = start + timedelta(days=i)
        open_count = sum(1 for created, resolved in rows if created <= day and (resolved is None or resolved > day))
        result.append(open_count)
    return result


@router.get("/trends")
async def get_admin_trends(db: Session = Depends(get_db)) -> dict:
    """Sparkline data for AdminHome — computed only from fields that actually exist
    (created_at/resolved_at); does not fabricate numbers for faithfulness/relevancy
    since the real eval pipeline is not wired up yet."""
    doc_dates = [row[0].date() for row in db.query(Document.created_at).all()]
    conflict_rows = [
        (row[0].date(), row[1].date() if row[1] else None)
        for row in db.query(ConflictFlag.created_at, ConflictFlag.resolved_at).all()
    ]

    return {
        "documents": _cumulative_counts(doc_dates, TREND_DAYS),
        "open_conflicts": _open_conflicts_trend(conflict_rows, TREND_DAYS),
    }


@router.get("/business")
async def get_business_dashboard(
    days: int = Query(default=14, ge=7, le=90),
    project_id: str | None = None,
    sale_id: int | None = None,
    db: Session = Depends(get_db),
) -> dict:
    """Business overview computed only from data already captured by SalesMate.

    A consultation session is the closest current proxy for a customer interaction;
    revenue, contracts and conversion rate are intentionally omitted because the
    product does not store those facts yet.
    """
    today = date.today()
    start_day = today - timedelta(days=days - 1)
    start_at = datetime.combine(start_day, time.min)

    # Use the same official-team scope for every business metric. Otherwise the
    # headline session/question totals include Admin and E2E traffic while the
    # active-Sale card excludes it, producing an internally inconsistent dashboard.
    official_sales = (
        db.query(User).filter(User.role == "sale", User.is_active.is_(True), ~User.username.like("e2e_sale_%")).all()
    )
    sale_names = {row.id: row.username for row in official_sales}
    official_sale_ids = set(sale_names)
    session_query = db.query(ChatSession).filter(
        ChatSession.created_at >= start_at,
        ChatSession.sale_id.in_(official_sale_ids),
    )
    if project_id:
        session_query = session_query.filter(ChatSession.project_id == project_id)
    if sale_id:
        session_query = session_query.filter(ChatSession.sale_id == sale_id)
    sessions = session_query.all() if official_sale_ids else []
    session_ids = [row.id for row in sessions]
    messages = db.query(Message).filter(Message.session_id.in_(session_ids)).all() if session_ids else []
    agent_messages = [row for row in messages if row.sender == "agent"]
    sale_messages = [row for row in messages if row.sender == "sale"]

    feedback_rows = (
        db.query(Feedback).filter(Feedback.message_id.in_([row.id for row in agent_messages])).all()
        if agent_messages
        else []
    )
    helpful_count = sum(1 for row in feedback_rows if row.type == "helpful")
    helpful_rate = helpful_count / len(feedback_rows) if feedback_rows else None

    verified_scores = [row.verifier_score for row in agent_messages if row.verifier_score is not None]
    verifier_avg = sum(verified_scores) / len(verified_scores) if verified_scores else None
    hitl_required = [row for row in agent_messages if row.requires_hitl]
    hitl_message_ids = [row.id for row in hitl_required]
    hitl_confirmed = (
        db.query(func.count(HitlLog.id))
        .filter(HitlLog.message_id.in_(hitl_message_ids), HitlLog.confirmed_at.isnot(None))
        .scalar()
        if hitl_message_ids
        else 0
    )

    activity = []
    for offset in range(days):
        day = start_day + timedelta(days=offset)
        day_sessions = [row for row in sessions if row.created_at.date() == day]
        day_session_ids = {row.id for row in day_sessions}
        activity.append(
            {
                "date": day.isoformat(),
                "sessions": len(day_sessions),
                "questions": sum(1 for row in sale_messages if row.session_id in day_session_ids),
            }
        )

    projects = db.query(Project).all()
    project_names = {row.id: row.name for row in projects}
    project_counts: dict[str, int] = {}
    unknown_project_count = 0
    for row in sessions:
        if not row.project_id:
            unknown_project_count += 1
            continue
        project_counts[row.project_id] = project_counts.get(row.project_id, 0) + 1
    top_projects = [
        {"project_id": project_id, "name": project_names.get(project_id, project_id), "sessions": count}
        for project_id, count in sorted(project_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
    ]
    if unknown_project_count:
        top_projects.append({"project_id": None, "name": "Chưa xác định dự án", "sessions": unknown_project_count})
        top_projects.sort(key=lambda item: (-item["sessions"], item["name"]))
        top_projects = top_projects[:6]

    sale_counts: dict[int, dict[str, int]] = {}
    for row in sessions:
        if row.sale_id not in official_sale_ids:
            continue
        sale_counts.setdefault(row.sale_id, {"sessions": 0, "customers": 0})
        sale_counts[row.sale_id]["sessions"] += 1
        if row.customer_name and row.customer_name.strip():
            sale_counts[row.sale_id]["customers"] += 1
    session_sale = {row.id: row.sale_id for row in sessions}
    for row in sale_messages:
        sale_id = session_sale.get(row.session_id)
        if sale_id in sale_counts:
            sale_counts[sale_id].setdefault("questions", 0)
            sale_counts[sale_id]["questions"] += 1
    top_sales = [
        {
            "sale_id": sale_id,
            "username": sale_names.get(sale_id, f"Sale #{sale_id}"),
            "sessions": counts["sessions"],
            "customers": counts["customers"],
            "questions": counts.get("questions", 0),
        }
        for sale_id, counts in sorted(sale_counts.items(), key=lambda item: (-item[1]["sessions"], item[0]))[:5]
    ]

    feedback_distribution = {"helpful": 0, "wrong": 0, "incomplete": 0, "unrated": 0}
    rated_message_ids: set[int] = set()
    for row in feedback_rows:
        if row.type in feedback_distribution:
            feedback_distribution[row.type] += 1
        rated_message_ids.add(row.message_id)
    feedback_distribution["unrated"] = sum(1 for row in agent_messages if row.id not in rated_message_ids)

    quality_trend = []
    for offset in range(days):
        day = start_day + timedelta(days=offset)
        day_answers = [row for row in agent_messages if row.created_at.date() == day]
        faithfulness = [row.faithfulness for row in day_answers if row.faithfulness is not None]
        relevancy = [row.answer_relevancy for row in day_answers if row.answer_relevancy is not None]
        quality_trend.append(
            {
                "date": day.isoformat(),
                "faithfulness": sum(faithfulness) / len(faithfulness) if faithfulness else None,
                "relevancy": sum(relevancy) / len(relevancy) if relevancy else None,
            }
        )

    coverage_categories = ["sales_policy", "price_list", "floor_plan", "legal_document", "payment_schedule"]
    documents = db.query(Document).filter(Document.project_id.isnot(None)).all()
    document_coverage = []
    for project in projects:
        project_documents = [row for row in documents if row.project_id == project.id and row.is_current]
        categories = {}
        for category in coverage_categories:
            matching = [row for row in project_documents if row.category == category]
            if any(row.status == "completed" and row.review_status == "approved" for row in matching):
                state = "ready"
            elif any(row.status == "completed" for row in matching):
                state = "pending_review"
            elif matching:
                state = "unavailable"
            else:
                state = "missing"
            categories[category] = state
        document_coverage.append(
            {
                "project_id": project.id,
                "name": project.name,
                "categories": categories,
                "ready_count": sum(1 for state in categories.values() if state == "ready"),
            }
        )
    document_coverage.sort(key=lambda item: (-item["ready_count"], item["name"]))

    return {
        "period_days": days,
        "applied_filters": {"project_id": project_id, "sale_id": sale_id},
        "filter_options": {
            "projects": [{"id": row.id, "name": row.name} for row in projects],
            "sales": [{"id": row.id, "username": row.username} for row in official_sales],
        },
        "verifier_threshold": get_settings().verifier_threshold_sale,
        "summary": {
            "sessions": len(sessions),
            "customers": sum(1 for row in sessions if row.customer_name and row.customer_name.strip()),
            "questions": len(sale_messages),
            "active_sales": len(sale_counts),
            "helpful_rate": helpful_rate,
            "verifier_avg": verifier_avg,
            "hitl_required": len(hitl_required),
            "hitl_confirmed": hitl_confirmed,
        },
        "activity": activity,
        "top_projects": top_projects,
        "top_sales": top_sales,
        "feedback_distribution": feedback_distribution,
        "quality_trend": quality_trend,
        "hitl_funnel": {
            "answers": len(agent_messages),
            "required": len(hitl_required),
            "confirmed": hitl_confirmed,
        },
        "document_coverage": document_coverage[:8],
    }
