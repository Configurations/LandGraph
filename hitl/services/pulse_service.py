"""Pulse metrics service — status distribution, velocity, burndown."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog

from core.database import fetch_all, fetch_one
from schemas.pulse import (
    BurndownPoint,
    DependencyHealth,
    MetricValue,
    PulseResponse,
    TeamMemberActivity,
)

log = structlog.get_logger(__name__)


def _append_filters(
    query: str,
    args: list,
    idx: int,
    team_id: Optional[str],
    project_id: Optional[int],
    team_col: str = "team_id",
    proj_col: str = "project_id",
) -> tuple[str, list, int]:
    """Append optional team/project WHERE clauses. Returns (query, args, next_idx)."""
    if team_id is not None:
        query += f" AND {team_col} = ${idx}"
        args.append(team_id)
        idx += 1
    if project_id is not None:
        query += f" AND {proj_col} = ${idx}"
        args.append(project_id)
        idx += 1
    return query, args, idx


async def _status_distribution(
    team_id: Optional[str],
    project_id: Optional[int],
) -> dict[str, int]:
    """Count issues grouped by status."""
    query = "SELECT status, COUNT(*) AS cnt FROM project.pm_issues WHERE 1=1"
    query, args, _ = _append_filters(query, [], 1, team_id, project_id)
    query += " GROUP BY status"
    rows = await fetch_all(query, *args)
    return {r["status"]: r["cnt"] for r in rows}


async def _team_activity(
    team_id: Optional[str],
    project_id: Optional[int],
) -> list[TeamMemberActivity]:
    """Count total, completed, and active issues per assignee."""
    query = """
        SELECT assignee,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE status = 'done') AS completed,
               COUNT(*) FILTER (WHERE status IN ('in-progress', 'in-review')) AS active
        FROM project.pm_issues
        WHERE assignee IS NOT NULL
    """
    query, args, _ = _append_filters(query, [], 1, team_id, project_id)
    query += " GROUP BY assignee ORDER BY total DESC"
    rows = await fetch_all(query, *args)
    return [
        TeamMemberActivity(
            name=r["assignee"],
            total=r["total"],
            completed=r["completed"],
            active=r["active"],
        )
        for r in rows
    ]


async def _dependency_health(
    team_id: Optional[str],
    project_id: Optional[int],
) -> DependencyHealth:
    """Compute dependency health metrics."""
    base_filter = "1=1"
    args: list = []
    idx = 1

    if team_id is not None:
        base_filter += f" AND i.team_id = ${idx}"
        args.append(team_id)
        idx += 1
    if project_id is not None:
        base_filter += f" AND i.project_id = ${idx}"
        args.append(project_id)
        idx += 1

    # Blocked count
    blocked_q = f"""
        SELECT COUNT(DISTINCT r.target_issue_id) AS cnt
        FROM project.pm_issue_relations r
        JOIN project.pm_issues blocker ON r.source_issue_id = blocker.id
        JOIN project.pm_issues i ON r.target_issue_id = i.id
        WHERE r.type = 'blocks' AND blocker.status != 'done' AND {base_filter}
    """
    blocked_row = await fetch_one(blocked_q, *args)
    blocked = blocked_row["cnt"] if blocked_row else 0

    # Blocking count
    blocking_q = f"""
        SELECT COUNT(DISTINCT r.source_issue_id) AS cnt
        FROM project.pm_issue_relations r
        JOIN project.pm_issues i ON r.source_issue_id = i.id
        WHERE r.type = 'blocks' AND i.status != 'done' AND {base_filter}
    """
    blocking_row = await fetch_one(blocking_q, *args)
    blocking = blocking_row["cnt"] if blocking_row else 0

    # Chains: count relations of type blocks
    chains_q = f"""
        SELECT COUNT(*) AS cnt
        FROM project.pm_issue_relations r
        JOIN project.pm_issues i ON r.source_issue_id = i.id
        WHERE r.type = 'blocks' AND {base_filter}
    """
    chains_row = await fetch_one(chains_q, *args)
    chains = chains_row["cnt"] if chains_row else 0

    # Bottlenecks: issues blocking the most others
    bottleneck_q = f"""
        SELECT r.source_issue_id AS issue_id, i.title,
               COUNT(*) AS blocks_count
        FROM project.pm_issue_relations r
        JOIN project.pm_issues i ON r.source_issue_id = i.id
        WHERE r.type = 'blocks' AND i.status != 'done' AND {base_filter}
        GROUP BY r.source_issue_id, i.title
        ORDER BY blocks_count DESC
        LIMIT 5
    """
    bottleneck_rows = await fetch_all(bottleneck_q, *args)
    bottlenecks = [
        {"issue_id": r["issue_id"], "title": r["title"], "blocks": r["blocks_count"]}
        for r in bottleneck_rows
    ]

    return DependencyHealth(
        blocked=blocked,
        blocking=blocking,
        chains=chains,
        bottlenecks=bottlenecks,
    )


async def _velocity(
    team_id: Optional[str],
    project_id: Optional[int],
) -> MetricValue:
    """Issues completed in the last 7 days."""
    query = """
        SELECT COUNT(*) AS cnt FROM project.pm_issues
        WHERE status = 'done' AND updated_at >= NOW() - INTERVAL '7 days'
    """
    query, args, _ = _append_filters(query.rstrip(), [], 1, team_id, project_id)
    row = await fetch_one(query, *args)
    cnt = row["cnt"] if row else 0
    return MetricValue(value=str(cnt), sub="last 7 days")


async def _throughput(
    team_id: Optional[str],
    project_id: Optional[int],
) -> MetricValue:
    """Average issues completed per week over last 30 days."""
    query = """
        SELECT COUNT(*) AS cnt FROM project.pm_issues
        WHERE status = 'done' AND updated_at >= NOW() - INTERVAL '30 days'
    """
    query, args, _ = _append_filters(query.rstrip(), [], 1, team_id, project_id)
    row = await fetch_one(query, *args)
    cnt = row["cnt"] if row else 0
    avg_per_week = round(cnt / 4, 1)
    return MetricValue(value=str(avg_per_week), sub="per week (30d avg)")


async def _cycle_time(
    team_id: Optional[str],
    project_id: Optional[int],
) -> MetricValue:
    """Average time from creation to done in last 30 days."""
    query = """
        SELECT AVG(EXTRACT(EPOCH FROM (updated_at - created_at))) AS avg_secs
        FROM project.pm_issues
        WHERE status = 'done' AND updated_at >= NOW() - INTERVAL '30 days'
    """
    query, args, _ = _append_filters(query.rstrip(), [], 1, team_id, project_id)
    row = await fetch_one(query, *args)
    avg_secs = row["avg_secs"] if row and row["avg_secs"] else 0
    hours = round(float(avg_secs) / 3600, 1)
    return MetricValue(value=f"{hours}h", sub="avg (30d)")


async def _burndown(
    team_id: Optional[str],
    project_id: Optional[int],
    days: int = 14,
) -> list[BurndownPoint]:
    """Compute a burndown chart over the last N days."""
    now = datetime.now(timezone.utc)
    points: list[BurndownPoint] = []

    for offset in range(days, -1, -1):
        day = now - timedelta(days=offset)
        day_str = day.strftime("%Y-%m-%d")
        day_end = day.replace(hour=23, minute=59, second=59)

        rem_q = """
            SELECT COUNT(*) AS cnt FROM project.pm_issues
            WHERE created_at <= $1 AND (status != 'done' OR updated_at > $1)
        """
        done_q = """
            SELECT COUNT(*) AS cnt FROM project.pm_issues
            WHERE status = 'done' AND updated_at <= $1
        """
        rem_args: list = [day_end]
        done_args: list = [day_end]
        r_idx = 2
        d_idx = 2

        if team_id is not None:
            rem_q += f" AND team_id = ${r_idx}"
            rem_args.append(team_id)
            r_idx += 1
            done_q += f" AND team_id = ${d_idx}"
            done_args.append(team_id)
            d_idx += 1
        if project_id is not None:
            rem_q += f" AND project_id = ${r_idx}"
            rem_args.append(project_id)
            done_q += f" AND project_id = ${d_idx}"
            done_args.append(project_id)

        rem_row = await fetch_one(rem_q, *rem_args)
        done_row = await fetch_one(done_q, *done_args)

        points.append(BurndownPoint(
            date=day_str,
            remaining=rem_row["cnt"] if rem_row else 0,
            completed=done_row["cnt"] if done_row else 0,
        ))

    return points


async def get_pulse(
    team_id: Optional[str] = None,
    project_id: Optional[int] = None,
) -> PulseResponse:
    """Aggregate all pulse metrics."""
    dist = await _status_distribution(team_id, project_id)
    team = await _team_activity(team_id, project_id)
    deps = await _dependency_health(team_id, project_id)
    vel = await _velocity(team_id, project_id)
    thr = await _throughput(team_id, project_id)
    cyc = await _cycle_time(team_id, project_id)
    burn = await _burndown(team_id, project_id)

    return PulseResponse(
        status_distribution=dist,
        team_activity=team,
        dependency_health=deps,
        velocity=vel,
        throughput=thr,
        cycle_time=cyc,
        burndown=burn,
    )
