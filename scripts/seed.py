from __future__ import annotations

import random
from datetime import datetime, timedelta
from passlib.hash import bcrypt

from models import init_db, SessionLocal, User, Task, RecurringTemplate, Announcement


def main():
    init_db()
    db = SessionLocal()
    try:
        # Users
        admin = User(email="admin@example.com", name="Admin", role="ADMIN", password_hash=bcrypt.hash("admin123"))
        mgr1 = User(email="manager1@example.com", name="Fulfillment Lead", role="MANAGER", team="Fulfillment", password_hash=bcrypt.hash("manager123"))
        mgr2 = User(email="manager2@example.com", name="Support Lead", role="MANAGER", team="Support", password_hash=bcrypt.hash("manager123"))
        emps = [
            User(email=f"emp{i}@example.com", name=f"Employee {i}", role="EMPLOYEE", team=random.choice(["Fulfillment", "Support"]).strip(), password_hash=bcrypt.hash("emp12345"))
            for i in range(1, 6)
        ]
        users = [admin, mgr1, mgr2, *emps]
        db.add_all(users)
        db.commit()
        for u in users:
            db.refresh(u)

        # Tasks
        boards = ["DAILY", "OTHER"]
        statuses_daily = ["TODO", "IN_PROGRESS", "DONE"]
        statuses_other = ["BACKLOG", "IN_PROGRESS", "REVIEW", "DONE"]
        priorities = ["LOW", "MEDIUM", "HIGH", "URGENT"]
        for i in range(15):
            assignee = random.choice(emps)
            board = random.choice(boards)
            status = random.choice(statuses_daily if board == "DAILY" else statuses_other)
            t = Task(
                title=f"Sample Task {i+1}",
                description="Seeded task",
                board=board,
                status=status,
                priority=random.choice(priorities),
                created_by_id=admin.id,
                assigned_to_id=assignee.id,
                tags=["requireProof"] if random.random() < 0.2 else [],
            )
            db.add(t)
        db.commit()

        # Recurring templates
        db.add_all([
            RecurringTemplate(title="Daily Stock Check", description="Check inventory levels", board="DAILY", freq="DAILY", hour=8, minute=0, assigned_to_id=emps[0].id, created_by_id=admin.id, tags=["checklist"]),
            RecurringTemplate(title="Disputed Orders Review", description="Review disputes", board="OTHER", freq="DAILY", hour=11, minute=0, assigned_to_id=mgr1.id, created_by_id=admin.id, tags=["review"]) ,
        ])
        db.add(Announcement(title="Welcome", body="Task system enabled", created_by_id=admin.id))
        db.commit()
        print("Seed completed")
    finally:
        db.close()


if __name__ == "__main__":
    main()


