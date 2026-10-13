import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "attendance_db")

client = MongoClient(MONGO_URI, tz_aware=True)
db = client[MONGO_DB]

employees = [
    {
        "emp_code": "EMP0001",
        "name": "Asha Rao",
        "email": "asha@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-01-05",
        "created_at": datetime(2026, 1, 5, 4, 30, tzinfo=timezone.utc),
    },
    {
        "emp_code": "EMP0002",
        "name": "Vikram Shah",
        "email": "vikram@example.com",
        "department": "Engineering",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-07-13",
        "created_at": datetime(2026, 7, 13, 4, 0, tzinfo=timezone.utc),
    },
    {
        "emp_code": "EMP0003",
        "name": "Neha Iyer",
        "email": "neha@example.com",
        "department": "Sales",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-02-01",
        "created_at": datetime(2026, 2, 1, 4, 30, tzinfo=timezone.utc),
    },
    {
        "emp_code": "EMP0004",
        "name": "Rohit Das",
        "email": "rohit@example.com",
        "department": "Sales",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-02-01",
        "created_at": datetime(2026, 2, 1, 4, 31, tzinfo=timezone.utc),
    },
    {
        "emp_code": "EMP0005",
        "name": "Meera Nair",
        "email": "meera@example.com",
        "department": "Support",
        "shift_start": "22:00",
        "shift_end": "06:00",
        "joined_on": "2026-03-10",
        "created_at": datetime(2026, 3, 10, 4, 30, tzinfo=timezone.utc),
    },
    {
        "emp_code": "EMP0006",
        "name": "Karan Bedi",
        "email": "karan@example.com",
        "department": "Support",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-03-10",
        "created_at": datetime(2026, 3, 10, 4, 31, tzinfo=timezone.utc),
    },
]

attendance_logs = [
    {
        "emp_code": "EMP0001",
        "date": "2026-07-06",
        "status": "PRESENT",
        "punch_in": datetime(2026, 7, 6, 3, 58, tzinfo=timezone.utc),
        "punch_out": datetime(2026, 7, 6, 13, 5, tzinfo=timezone.utc),
        "work_hours": 9.12,
        "late_minutes": 0,
        "overtime_minutes": 0,
        "half_day": False,
        "history": [],
    },
    {
        "emp_code": "EMP0003",
        "date": "2026-07-06",
        "status": "PRESENT",
        "punch_in": datetime(2026, 7, 6, 4, 35, tzinfo=timezone.utc),
        "punch_out": datetime(2026, 7, 6, 13, 40, tzinfo=timezone.utc),
        "work_hours": 9.08,
        "late_minutes": 35,
        "overtime_minutes": 40,
        "half_day": False,
        "history": [],
    },
    {
        "emp_code": "EMP0006",
        "date": "2026-07-07",
        "status": "PRESENT",
        "punch_in": datetime(2026, 7, 7, 4, 5, tzinfo=timezone.utc),
        "punch_out": None,
        "work_hours": None,
        "late_minutes": 0,
        "overtime_minutes": 0,
        "half_day": False,
        "history": [],
    },
    {
        "emp_code": "EMP0004",
        "date": "2026-07-07",
        "status": "WFH",
        "punch_in": datetime(2026, 7, 7, 4, 0, tzinfo=timezone.utc),
        "punch_out": datetime(2026, 7, 7, 7, 30, tzinfo=timezone.utc),
        "work_hours": 3.5,
        "late_minutes": 0,
        "overtime_minutes": 0,
        "half_day": True,
        "history": [],
    },
    {
        "emp_code": "EMP0005",
        "date": "2026-07-06",
        "status": "PRESENT",
        "punch_in": datetime(2026, 7, 6, 16, 25, tzinfo=timezone.utc),
        "punch_out": datetime(2026, 7, 7, 1, 10, tzinfo=timezone.utc),
        "work_hours": 8.75,
        "late_minutes": 0,
        "overtime_minutes": 40,
        "half_day": False,
        "history": [],
    },
]

db.employees.delete_many({})
db.employees.insert_many(employees)
print(f"Loaded {len(employees)} employees into '{db.name}.employees'")

db.attendance_logs.delete_many({})
db.attendance_logs.insert_many(attendance_logs)
print(f"Loaded {len(attendance_logs)} attendance logs into '{db.name}.attendance_logs'")