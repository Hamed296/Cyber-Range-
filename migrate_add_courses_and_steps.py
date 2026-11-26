import sqlite3
from pathlib import Path

DB_PATH = Path("database.db")


def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def main():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        # -------------------------------------------------
        # 1) courses
        # -------------------------------------------------
        if not table_exists(conn, "courses"):
            conn.execute("""
                CREATE TABLE courses (
                    id INTEGER PRIMARY KEY,
                    code TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT ''
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS ix_courses_id ON courses (id)")
            conn.execute("CREATE INDEX IF NOT EXISTS ix_courses_code ON courses (code)")
            print("Created table: courses")
        else:
            print("Table already exists: courses")

        # -------------------------------------------------
        # 2) scenarios.description
        # -------------------------------------------------
        if not column_exists(conn, "scenarios", "description"):
            conn.execute("ALTER TABLE scenarios ADD COLUMN description TEXT NOT NULL DEFAULT ''")
            print("Added column: scenarios.description")
        else:
            print("Column already exists: scenarios.description")

        # -------------------------------------------------
        # 3) scenarios.course_id
        # -------------------------------------------------
        if not column_exists(conn, "scenarios", "course_id"):
            # SQLite يسمح بإضافة العمود، لكن FK constraint لن يُفرض بأثر رجعي هنا.
            conn.execute("ALTER TABLE scenarios ADD COLUMN course_id INTEGER NULL")
            print("Added column: scenarios.course_id")
        else:
            print("Column already exists: scenarios.course_id")

        # optional index
        conn.execute("CREATE INDEX IF NOT EXISTS ix_scenarios_course_id ON scenarios (course_id)")

        # -------------------------------------------------
        # 4) lab_steps
        # -------------------------------------------------
        if not table_exists(conn, "lab_steps"):
            conn.execute("""
                CREATE TABLE lab_steps (
                    id INTEGER PRIMARY KEY,
                    scenario_id INTEGER NOT NULL,
                    step_order INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    points INTEGER NOT NULL DEFAULT 0,
                    answer_type TEXT NOT NULL DEFAULT 'text',
                    correct_answer TEXT NOT NULL DEFAULT '',
                    placeholder TEXT NOT NULL DEFAULT '',
                    hint TEXT NOT NULL DEFAULT '',
                    is_required BOOLEAN NOT NULL DEFAULT 1,
                    FOREIGN KEY (scenario_id) REFERENCES scenarios(id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS ix_lab_steps_id ON lab_steps (id)")
            conn.execute("CREATE INDEX IF NOT EXISTS ix_lab_steps_scenario_id ON lab_steps (scenario_id)")
            print("Created table: lab_steps")
        else:
            print("Table already exists: lab_steps")

        # -------------------------------------------------
        # 5) student_lab_steps
        # -------------------------------------------------
        if not table_exists(conn, "student_lab_steps"):
            conn.execute("""
                CREATE TABLE student_lab_steps (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    session_id INTEGER NOT NULL,
                    step_id INTEGER NOT NULL,
                    submitted_answer TEXT NOT NULL DEFAULT '',
                    is_correct BOOLEAN NOT NULL DEFAULT 0,
                    awarded_points INTEGER NOT NULL DEFAULT 0,
                    submitted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (session_id) REFERENCES scenario_sessions(id),
                    FOREIGN KEY (step_id) REFERENCES lab_steps(id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS ix_student_lab_steps_id ON student_lab_steps (id)")
            conn.execute("CREATE INDEX IF NOT EXISTS ix_student_lab_steps_user_id ON student_lab_steps (user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS ix_student_lab_steps_session_id ON student_lab_steps (session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS ix_student_lab_steps_step_id ON student_lab_steps (step_id)")
            print("Created table: student_lab_steps")
        else:
            print("Table already exists: student_lab_steps")

        conn.commit()
        print("Migration completed successfully.")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()