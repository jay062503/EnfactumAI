"""A tiny stand-in for Enfactum OS, used only for local demos (MOCK_OS_ENABLED=true).

It behaves like a Laravel API protected by Sanctum + permissions: it authenticates the bearer token, enforces
permissions and row-level visibility itself, and returns {"data": [...]} payloads. All records are fictional.
"""
from datetime import date, timedelta

from fastapi import APIRouter, Body, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from .auth import load_demo_users
from .config import Settings

EMPLOYEES = [
    {"id": 101, "name": "Aisha Khan", "email": "aisha.khan@enfactum.example", "department": "Leadership",
     "designation": "Chief Operating Officer", "manager": None, "location": "Singapore", "salary": 310000},
    {"id": 102, "name": "Rohan Mehta", "email": "rohan.mehta@enfactum.example", "department": "People & Culture",
     "designation": "HR Manager", "manager": "Aisha Khan", "location": "Mumbai", "salary": 145000},
    {"id": 103, "name": "Priya Nair", "email": "priya.nair@enfactum.example", "department": "Delivery",
     "designation": "Senior Project Manager", "manager": "Aisha Khan", "location": "Bengaluru", "salary": 128000},
    {"id": 104, "name": "Daniel Lim", "email": "daniel.lim@enfactum.example", "department": "Design",
     "designation": "UX Lead", "manager": "Priya Nair", "location": "Singapore", "salary": 118000},
    {"id": 105, "name": "Sara Iyer", "email": "sara.iyer@enfactum.example", "department": "Engineering",
     "designation": "Full-stack Engineer", "manager": "Priya Nair", "location": "Bengaluru", "salary": 92000},
    {"id": 106, "name": "Marcus Tan", "email": "marcus.tan@enfactum.example", "department": "Finance",
     "designation": "Finance Controller", "manager": "Aisha Khan", "location": "Singapore", "salary": 150000},
]

CLIENTS = [
    {"id": 201, "name": "Northwind Retail", "industry": "Retail", "account_manager": "Priya Nair", "status": "active"},
    {"id": 202, "name": "Helios Energy", "industry": "Energy", "account_manager": "Aisha Khan", "status": "active"},
    {"id": 203, "name": "BlueHarbor Bank", "industry": "Financial Services", "account_manager": "Priya Nair",
     "status": "prospect"},
]

PROJECTS = [
    {"id": 301, "name": "Northwind Omnichannel App", "client": "Northwind Retail", "status": "in_progress",
     "manager": "Priya Nair", "start_date": "2026-03-02", "end_date": "2026-11-30", "budget": 420000,
     "team": ["Priya Nair", "Daniel Lim", "Sara Iyer"]},
    {"id": 302, "name": "Helios Customer Portal", "client": "Helios Energy", "status": "planning",
     "manager": "Aisha Khan", "start_date": "2026-10-15", "end_date": "2027-04-30", "budget": 610000,
     "team": ["Aisha Khan", "Marcus Tan"]},
    {"id": 303, "name": "BlueHarbor Discovery Sprint", "client": "BlueHarbor Bank", "status": "proposal",
     "manager": "Priya Nair", "start_date": None, "end_date": None, "budget": 55000, "team": ["Priya Nair"]},
]

LEAVE_REQUESTS = [
    {"id": 401, "employee_id": 103, "leave_type": "annual", "start_date": "2026-08-10", "end_date": "2026-08-14",
     "days": 5, "reason": "Family trip", "status": "approved"},
]

TASKS = [
    {"id": 501, "project_id": 301, "project": "Northwind Omnichannel App", "title": "Sign off checkout UX",
     "assignee": "Priya Nair", "due_date": "2026-10-09", "priority": "high", "status": "in_progress",
     "created_by": "Daniel Lim"},
    {"id": 502, "project_id": 301, "project": "Northwind Omnichannel App", "title": "Payment gateway integration",
     "assignee": "Sara Iyer", "due_date": "2026-10-20", "priority": "high", "status": "todo",
     "created_by": "Priya Nair"},
]


def build_router(settings: Settings) -> APIRouter:
    users = {u["os_token"]: u for u in load_demo_users(settings).values() if u.get("os_token")}
    router = APIRouter(prefix="/mock-os/api", tags=["mock-os"], include_in_schema=False)

    def auth(authorization: str | None) -> dict:
        token = (authorization or "").removeprefix("Bearer ").strip()
        user = users.get(token)
        if not user:
            raise HTTPException(401, "Unauthenticated.")
        return user

    def can(user: dict, perm: str) -> bool:
        return "super_admin" in user.get("roles", []) or perm in user.get("permissions", [])

    def require(user: dict, perm: str) -> None:
        if not can(user, perm):
            raise HTTPException(403, "This action is unauthorized.")

    def match(record: dict, q: str | None, *keys: str) -> bool:
        return not q or any(q.lower() in str(record.get(k) or "").lower() for k in keys)

    @router.get("/user")
    def me(authorization: str | None = Header(None)):
        u = auth(authorization)
        return {"id": u["id"], "name": u["name"], "email": u.get("email"), "user_type": u.get("user_type", "employee"),
                "roles": u.get("roles", []), "permissions": u.get("permissions", [])}

    @router.get("/employees")
    def employees(search: str | None = Query(None), department: str | None = Query(None),
                  authorization: str | None = Header(None)):
        u = auth(authorization)
        require(u, "employees.view")
        rows = [e for e in EMPLOYEES if match(e, search, "name", "email", "designation")
                and match(e, department, "department")]
        if not can(u, "employees.view_salary"):
            rows = [{k: v for k, v in e.items() if k != "salary"} for e in rows]
        return {"data": rows, "meta": {"total": len(rows)}}

    @router.get("/employees/{employee_id}")
    def employee(employee_id: int, authorization: str | None = Header(None)):
        u = auth(authorization)
        require(u, "employees.view")
        for e in EMPLOYEES:
            if e["id"] == employee_id:
                return {"data": e if can(u, "employees.view_salary") else {k: v for k, v in e.items() if k != "salary"}}
        raise HTTPException(404, "Not found.")

    @router.get("/projects")
    def projects(search: str | None = Query(None), status: str | None = Query(None),
                 authorization: str | None = Header(None)):
        u = auth(authorization)
        require(u, "projects.view")
        rows = [p for p in PROJECTS if match(p, search, "name", "client") and (not status or p["status"] == status)]
        if not can(u, "projects.view_all"):
            rows = [p for p in rows if u["name"] in p["team"]]
        if not can(u, "finance.view"):
            rows = [{k: v for k, v in p.items() if k != "budget"} for p in rows]
        return {"data": rows, "meta": {"total": len(rows)}}

    @router.get("/clients")
    def clients(search: str | None = Query(None), authorization: str | None = Header(None)):
        u = auth(authorization)
        require(u, "clients.view")
        rows = [c for c in CLIENTS if match(c, search, "name", "industry")]
        return {"data": rows, "meta": {"total": len(rows)}}

    @router.get("/leave-requests")
    def leave_list(authorization: str | None = Header(None)):
        u = auth(authorization)
        require(u, "leave.view")
        rows = [r for r in LEAVE_REQUESTS if r["employee_id"] == int(u["id"])]
        return {"data": rows, "meta": {"total": len(rows)}}

    @router.post("/leave-requests", status_code=201)
    def leave_create(body: dict = Body(...), authorization: str | None = Header(None)):
        u = auth(authorization)
        require(u, "leave.create")
        errors: dict[str, list[str]] = {}
        start, end = _date(body.get("start_date")), _date(body.get("end_date"))
        if body.get("leave_type") not in ("annual", "sick", "casual", "unpaid", "parental"):
            errors["leave_type"] = ["The selected leave type is invalid."]
        if not start:
            errors["start_date"] = ["The start date must be a valid date."]
        if not end:
            errors["end_date"] = ["The end date must be a valid date."]
        if start and end and end < start:
            errors["end_date"] = ["The end date must be a date after or equal to start date."]
        if errors:
            return _invalid(errors)
        days = sum(1 for i in range((end - start).days + 1) if (start + timedelta(i)).weekday() < 5)
        row = {"id": 400 + len(LEAVE_REQUESTS) + 1, "employee_id": int(u["id"]), "leave_type": body["leave_type"],
               "start_date": start.isoformat(), "end_date": end.isoformat(), "days": days,
               "reason": str(body.get("reason") or "")[:500], "status": "pending_approval"}
        LEAVE_REQUESTS.append(row)
        return {"data": row}

    @router.get("/tasks")
    def task_list(project_id: int | None = Query(None), status: str | None = Query(None),
                  authorization: str | None = Header(None)):
        u = auth(authorization)
        require(u, "tasks.view")
        rows = [t for t in TASKS if t["assignee"] == u["name"] or t["created_by"] == u["name"]]
        rows = [t for t in rows if (not project_id or t["project_id"] == project_id)
                and (not status or t["status"] == status)]
        return {"data": rows, "meta": {"total": len(rows)}}

    @router.post("/tasks", status_code=201)
    def task_create(body: dict = Body(...), authorization: str | None = Header(None)):
        u = auth(authorization)
        require(u, "tasks.create")
        project = next((p for p in PROJECTS if p["id"] == body.get("project_id")), None)
        if not project or u["name"] not in project["team"]:
            raise HTTPException(403, "You are not a member of this project.")
        title = str(body.get("title") or "").strip()
        if not title:
            return _invalid({"title": ["The title field is required."]})
        assignee = body.get("assignee") or u["name"]
        if assignee not in project["team"]:
            return _invalid({"assignee": [f"{assignee} is not on this project."]})
        row = {"id": 500 + len(TASKS) + 1, "project_id": project["id"], "project": project["name"], "title": title,
               "assignee": assignee, "due_date": body.get("due_date"), "priority": body.get("priority") or "medium",
               "status": "todo", "created_by": u["name"]}
        TASKS.append(row)
        return {"data": row}

    return router


def _invalid(errors: dict) -> JSONResponse:
    """Laravel-style validation error payload."""
    return JSONResponse({"message": "The given data was invalid.", "errors": errors}, status_code=422)


def _date(value) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
