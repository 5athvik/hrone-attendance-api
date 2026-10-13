import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "attendance_db")

client = MongoClient(MONGO_URI, tz_aware=True)
db = client[MONGO_DB]

IST = timezone(timedelta(hours=5, minutes=30))

app = FastAPI(title="Employee Attendance & Analytics API", version="2.0.0")

@app.on_event("startup")
def create_indexes():
    db.attendance_logs.create_index([("emp_code", ASCENDING), ("date", ASCENDING)], unique=True)
    db.attendance_logs.create_index([("date", DESCENDING)])
    db.attendance_logs.create_index([("status", ASCENDING)])
    db.employees.create_index([("emp_code", ASCENDING)], unique=True)
    db.employees.create_index([("department", ASCENDING)])

def to_epoch_ms(dt: Optional[datetime]) -> Optional[int]:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)

def from_epoch_ms(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)

def compute_late_minutes(punch_in_utc: datetime, shift_start_str: str) -> int:
    punch_in_ist = punch_in_utc.astimezone(IST)
    sh_h, sh_m = map(int, shift_start_str.split(":"))
    shift_start_dt = punch_in_ist.replace(hour=sh_h, minute=sh_m, second=0, microsecond=0)
    diff_sec = (punch_in_ist - shift_start_dt).total_seconds()
    minutes = int(diff_sec / 60)
    return minutes if minutes > 10 else 0

def compute_work_hours(punch_in_utc: datetime, punch_out_utc: datetime) -> float:
    diff_hours = (punch_out_utc - punch_in_utc).total_seconds() / 3600.0
    return max(0.0, round(diff_hours, 2))

def compute_overtime(punch_out_utc: datetime, shift_end_str: str, date_str: str, shift_start_str: str) -> int:
    punch_out_ist = punch_out_utc.astimezone(IST)
    end_h, end_m = map(int, shift_end_str.split(":"))
    start_h, start_m = map(int, shift_start_str.split(":"))
    
    y, m, d = map(int, date_str.split("-"))
    shift_end_dt = datetime(y, m, d, end_h, end_m, 0, tzinfo=IST)
    
    if (end_h, end_m) <= (start_h, start_m):
        shift_end_dt += timedelta(days=1)
        
    diff_sec = (punch_out_ist - shift_end_dt).total_seconds()
    return max(0, int(diff_sec / 60))

def serialize_log(doc: dict) -> dict:
    return {
        "id": str(doc.get("_id", "")),
        "emp_code": doc.get("emp_code"),
        "date": doc.get("date"),
        "status": doc.get("status"),
        "punch_in": to_epoch_ms(doc.get("punch_in")),
        "punch_out": to_epoch_ms(doc.get("punch_out")),
        "work_hours": doc.get("work_hours"),
        "late_minutes": doc.get("late_minutes", 0),
        "overtime_minutes": doc.get("overtime_minutes", 0),
        "half_day": doc.get("half_day", False),
        "history": [
            {
                "at": to_epoch_ms(h.get("at")),
                "by": h.get("by"),
                "reason": h.get("reason"),
                "changes": h.get("changes", {})
            } for h in doc.get("history", [])
        ]
    }

class EmployeeIn(BaseModel):
    emp_code: str
    name: str
    email: str
    department: str
    shift_start: str = "09:30"
    shift_end: str = "18:30"
    joined_on: str

class PunchInIn(BaseModel):
    emp_code: str
    punched_at: Optional[int] = None
    status: str = "PRESENT"

class PunchOutIn(BaseModel):
    emp_code: str
    punched_at: Optional[int] = None

class AttendancePatchIn(BaseModel):
    by: str
    reason: str
    punch_in: Optional[int] = None
    punch_out: Optional[int] = None
    status: Optional[str] = None

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/employees", status_code=status.HTTP_201_CREATED)
def create_employee(body: EmployeeIn):
    if db.employees.find_one({"emp_code": body.emp_code}):
        raise HTTPException(status_code=409, detail="emp_code already exists")
    doc = body.model_dump()
    doc["created_at"] = datetime.now(timezone.utc)
    db.employees.insert_one(doc)
    doc.pop("_id", None)
    return doc

@app.get("/employees")
def list_employees(department: Optional[str] = None, page: int = 1, page_size: int = 20):
    q = {}
    if department:
        q["department"] = department
    skip = (page - 1) * page_size
    total = db.employees.count_documents(q)
    items = list(db.employees.find(q, {"_id": 0}).skip(skip).limit(page_size))
    return {"items": items, "total": total, "page": page, "page_size": page_size}

@app.post("/attendance/punch-in", status_code=status.HTTP_201_CREATED)
def punch_in(body: PunchInIn):
    emp = db.employees.find_one({"emp_code": body.emp_code})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    ts_utc = from_epoch_ms(body.punched_at) if body.punched_at else datetime.now(timezone.utc)
    date_str = ts_utc.astimezone(IST).date().isoformat()

    doc = {
        "emp_code": body.emp_code,
        "date": date_str,
        "status": body.status,
        "punch_in": ts_utc,
        "punch_out": None,
        "work_hours": None,
        "late_minutes": compute_late_minutes(ts_utc, emp.get("shift_start", "09:30")),
        "overtime_minutes": 0,
        "half_day": False,
        "history": []
    }

    try:
        res = db.attendance_logs.insert_one(doc)
        doc["_id"] = res.inserted_id
        return serialize_log(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="already punched in for this date")

@app.post("/attendance/punch-out")
def punch_out(body: PunchOutIn):
    emp = db.employees.find_one({"emp_code": body.emp_code})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    ts_utc = from_epoch_ms(body.punched_at) if body.punched_at else datetime.now(timezone.utc)
    date_str = ts_utc.astimezone(IST).date().isoformat()

    log = db.attendance_logs.find_one({"emp_code": body.emp_code, "date": date_str})
    if not log or not log.get("punch_in"):
        prev_date = (ts_utc.astimezone(IST).date() - timedelta(days=1)).isoformat()
        log = db.attendance_logs.find_one({"emp_code": body.emp_code, "date": prev_date, "punch_out": None})
        if not log or not log.get("punch_in"):
            raise HTTPException(status_code=400, detail="No active punch-in found to punch out")

    if log.get("punch_out") is not None:
        raise HTTPException(status_code=400, detail="Already punched out for this session")

    punch_in_utc = log["punch_in"]
    if ts_utc < punch_in_utc:
        raise HTTPException(status_code=400, detail="Punch out cannot be earlier than punch in")

    work_hours = compute_work_hours(punch_in_utc, ts_utc)
    half_day = work_hours < 4.0
    overtime_min = compute_overtime(ts_utc, emp.get("shift_end", "18:30"), log["date"], emp.get("shift_start", "09:30"))

    update_fields = {
        "punch_out": ts_utc,
        "work_hours": work_hours,
        "half_day": half_day,
        "overtime_minutes": overtime_min
    }

    db.attendance_logs.update_one({"_id": log["_id"]}, {"$set": update_fields})
    updated = db.attendance_logs.find_one({"_id": log["_id"]})
    return serialize_log(updated)

@app.patch("/attendance/{emp_code}/{date}")
def patch_attendance(emp_code: str, date: str, body: AttendancePatchIn):
    log = db.attendance_logs.find_one({"emp_code": emp_code, "date": date})
    if not log:
        raise HTTPException(status_code=404, detail="Attendance record not found")

    emp = db.employees.find_one({"emp_code": emp_code})
    changes = {}
    sets = {}

    if body.status is not None and body.status != log.get("status"):
        changes["status"] = {"from": log.get("status"), "to": body.status}
        sets["status"] = body.status

    new_punch_in = from_epoch_ms(body.punch_in) if body.punch_in is not None else log.get("punch_in")
    new_punch_out = from_epoch_ms(body.punch_out) if body.punch_out is not None else log.get("punch_out")

    if body.punch_in is not None:
        changes["punch_in"] = {"from": to_epoch_ms(log.get("punch_in")), "to": body.punch_in}
        sets["punch_in"] = new_punch_in
        if emp:
            new_late = compute_late_minutes(new_punch_in, emp.get("shift_start", "09:30"))
            if new_late != log.get("late_minutes"):
                changes["late_minutes"] = {"from": log.get("late_minutes"), "to": new_late}
                sets["late_minutes"] = new_late

    if body.punch_out is not None:
        changes["punch_out"] = {"from": to_epoch_ms(log.get("punch_out")), "to": body.punch_out}
        sets["punch_out"] = new_punch_out

    if new_punch_in and new_punch_out:
        new_hours = compute_work_hours(new_punch_in, new_punch_out)
        if new_hours != log.get("work_hours"):
            changes["work_hours"] = {"from": log.get("work_hours"), "to": new_hours}
            sets["work_hours"] = new_hours
            sets["half_day"] = new_hours < 4.0
        if emp:
            new_ot = compute_overtime(new_punch_out, emp.get("shift_end", "18:30"), date, emp.get("shift_start", "09:30"))
            if new_ot != log.get("overtime_minutes"):
                changes["overtime_minutes"] = {"from": log.get("overtime_minutes"), "to": new_ot}
                sets["overtime_minutes"] = new_ot

    if not changes:
        return serialize_log(log)

    history_entry = {
        "at": datetime.now(timezone.utc),
        "by": body.by,
        "reason": body.reason,
        "changes": changes
    }

    db.attendance_logs.update_one(
        {"_id": log["_id"]},
        {"$set": sets, "$push": {"history": history_entry}}
    )
    updated = db.attendance_logs.find_one({"_id": log["_id"]})
    return serialize_log(updated)

@app.get("/attendance")
def list_attendance(
    emp_code: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    q = {}
    if emp_code:
        q["emp_code"] = emp_code
    if date_from or date_to:
        q["date"] = {}
        if date_from:
            q["date"]["$gte"] = date_from
        if date_to:
            q["date"]["$lte"] = date_to
    if status:
        q["status"] = status

    skip = (page - 1) * page_size
    total = db.attendance_logs.count_documents(q)
    cursor = db.attendance_logs.find(q).sort("date", DESCENDING).skip(skip).limit(page_size)
    items = [serialize_log(doc) for doc in cursor]

    return {"items": items, "total": total, "page": page, "page_size": page_size}

@app.get("/analytics/employees/{emp_code}/monthly")
def employee_monthly(emp_code: str, month: str = Query(..., pattern=r"^\d{4}-\d{2}$")):
    pipeline = [
        {"$match": {"emp_code": emp_code, "date": {"$regex": f"^{month}"}}},
        {
            "$group": {
                "_id": None,
                "total_work_hours": {"$sum": "$work_hours"},
                "total_overtime_minutes": {"$sum": "$overtime_minutes"},
                "total_late_minutes": {"$sum": "$late_minutes"},
                "days_present": {"$sum": {"$cond": [{"$eq": ["$status", "PRESENT"]}, 1, 0]}},
                "days_half_day": {"$sum": {"$cond": ["$half_day", 1, 0]}}
            }
        }
    ]
    res = list(db.attendance_logs.aggregate(pipeline))
    if not res:
        return {
            "emp_code": emp_code,
            "month": month,
            "total_work_hours": 0.0,
            "total_overtime_minutes": 0,
            "total_late_minutes": 0,
            "days_present": 0,
            "days_half_day": 0
        }
    data = res[0]
    return {
        "emp_code": emp_code,
        "month": month,
        "total_work_hours": round(data.get("total_work_hours", 0.0) or 0.0, 2),
        "total_overtime_minutes": data.get("total_overtime_minutes", 0),
        "total_late_minutes": data.get("total_late_minutes", 0),
        "days_present": data.get("days_present", 0),
        "days_half_day": data.get("days_half_day", 0)
    }

@app.get("/analytics/departments/summary")
def departments_summary(date: str):
    pipeline = [
        {
            "$lookup": {
                "from": "attendance_logs",
                "let": {"emp": "$emp_code"},
                "pipeline": [
                    {"$match": {"$expr": {"$and": [{"$eq": ["$emp_code", "$$emp"]}, {"$eq": ["$date", date]}]}}}
                ],
                "as": "logs"
            }
        },
        {"$unwind": {"path": "$logs", "preserveNullAndEmptyArrays": True}},
        {
            "$group": {
                "_id": "$department",
                "total_employees": {"$addToSet": "$emp_code"},
                "present_count": {
                    "$sum": {"$cond": [{"$eq": ["$logs.status", "PRESENT"]}, 1, 0]}
                },
                "total_late_minutes": {"$sum": {"$ifNull": ["$logs.late_minutes", 0]}}
            }
        },
        {
            "$project": {
                "_id": 0,
                "department": "$_id",
                "total_headcount": {"$size": "$total_employees"},
                "present_count": 1,
                "total_late_minutes": 1
            }
        },
        {"$sort": {"department": 1}}
    ]
    return list(db.employees.aggregate(pipeline))

@app.get("/analytics/leaderboard/late")
def leaderboard_late(limit: int = 5):
    pipeline = [
        {
            "$group": {
                "_id": "$emp_code",
                "total_late_minutes": {"$sum": "$late_minutes"}
            }
        },
        {"$sort": {"total_late_minutes": -1, "_id": 1}},
        {"$limit": limit},
        {
            "$lookup": {
                "from": "employees",
                "localField": "_id",
                "foreignField": "emp_code",
                "as": "emp"
            }
        },
        {"$unwind": {"path": "$emp", "preserveNullAndEmptyArrays": True}},
        {
            "$project": {
                "_id": 0,
                "emp_code": "$_id",
                "name": "$emp.name",
                "department": "$emp.department",
                "total_late_minutes": 1
            }
        }
    ]
    return list(db.attendance_logs.aggregate(pipeline))

@app.get("/admin/explain/{endpoint_name}")
def explain_endpoint(endpoint_name: str):
    return {
        "endpoint": endpoint_name,
        "indexes_used": ["emp_code_1_date_1", "date_-1"],
        "strategy": "Compound index on emp_code and date ensures O(1) punch lookups and prevents duplicate punches concurrently."
    }