"""Team service — list teams, members, invite."""

from __future__ import annotations

from uuid import UUID

import structlog

from core.config import load_teams
from core.database import execute, fetch_all, fetch_one
from core.security import hash_password
from schemas.common import SuccessResponse
from schemas.team import TeamMemberResponse, TeamResponse

log = structlog.get_logger(__name__)


async def list_teams(user_id: UUID, user_role: str) -> list[TeamResponse]:
    """List teams visible to the user. Admins see all teams."""
    config_teams = load_teams()

    if user_role == "admin":
        team_ids = [t["id"] for t in config_teams]
    else:
        rows = await fetch_all(
            "SELECT team_id FROM project.hitl_team_members WHERE user_id = $1",
            user_id,
        )
        team_ids = [r["team_id"] for r in rows]

    result: list[TeamResponse] = []
    for t in config_teams:
        if t["id"] not in team_ids:
            continue
        count_row = await fetch_one(
            "SELECT COUNT(*) as cnt FROM project.hitl_team_members WHERE team_id = $1",
            t["id"],
        )
        member_count = count_row["cnt"] if count_row else 0
        result.append(TeamResponse(
            id=t["id"],
            name=t.get("name", t["id"]),
            directory=t.get("directory", t["id"]),
            member_count=member_count,
        ))

    return result


async def list_members(team_id: str) -> list[TeamMemberResponse]:
    """List all members of a team with their global + team roles."""
    rows = await fetch_all(
        """SELECT u.id, u.email, u.display_name, u.role as role_global,
                  tm.role as role_team, u.is_active,
                  u.last_login
           FROM project.hitl_team_members tm
           JOIN project.hitl_users u ON u.id = tm.user_id
           WHERE tm.team_id = $1
           ORDER BY u.email""",
        team_id,
    )
    return [
        TeamMemberResponse(
            user_id=r["id"],
            email=r["email"],
            display_name=r["display_name"] or "",
            role_global=r["role_global"],
            role_team=r["role_team"],
            is_active=r["is_active"],
            last_login=r["last_login"],
        )
        for r in rows
    ]


async def invite_member(
    team_id: str,
    email: str,
    display_name: str = "",
    role: str = "member",
) -> SuccessResponse:
    """Invite a user to a team. Creates the user if needed."""
    # Find or create user
    row = await fetch_one(
        "SELECT id FROM project.hitl_users WHERE email = $1", email,
    )

    if row:
        user_id = row["id"]
    else:
        # Create a new user with a temp password
        import secrets
        import string
        alphabet = string.ascii_letters + string.digits
        temp_pw = "".join(secrets.choice(alphabet) for _ in range(12))
        hashed = hash_password(temp_pw)
        name = display_name or email.split("@")[0]
        new_row = await fetch_one(
            """INSERT INTO project.hitl_users
               (email, password_hash, display_name, role, auth_type)
               VALUES ($1, $2, $3, 'member', 'local')
               RETURNING id""",
            email, hashed, name,
        )
        if not new_row:
            from fastapi import HTTPException
            raise HTTPException(500, detail="common.server_error")
        user_id = new_row["id"]
        log.info("user_created_via_invite", email=email, team_id=team_id)

    # Check if already a member
    existing = await fetch_one(
        """SELECT 1 FROM project.hitl_team_members
           WHERE user_id = $1 AND team_id = $2""",
        user_id, team_id,
    )
    if existing:
        from fastapi import HTTPException
        raise HTTPException(409, detail="team.member_exists")

    await execute(
        """INSERT INTO project.hitl_team_members (user_id, team_id, role)
           VALUES ($1, $2, $3)""",
        user_id, team_id, role,
    )
    log.info("member_invited", email=email, team_id=team_id, role=role)
    return SuccessResponse(ok=True)
