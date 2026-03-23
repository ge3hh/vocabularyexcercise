import csv
import os
import sqlite3
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "vocabulary_hs.db")

LIBRARY_TABLES = {
    "高中词库": "vocabulary_high_school",
    "大学四级词库": "vocabulary_cet4",
    "大学六级词库": "vocabulary_cet6",
}

TABLE_TO_LIBRARY = {table_name: library_name for library_name, table_name in LIBRARY_TABLES.items()}
DEFAULT_LIBRARY_NAME = "高中词库"
REVIEW_INTERVAL_DAYS = [1, 2, 4, 7, 15, 30, 60]


def get_connection():
    return sqlite3.connect(DB_PATH)


def ensure_library_table(cursor, table_name):
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            english TEXT NOT NULL UNIQUE,
            chinese TEXT DEFAULT '',
            practice_times INTEGER NOT NULL DEFAULT 0,
            first_test_date TEXT,
            last_practice_date TEXT,
            next_review_date TEXT,
            correct_times INTEGER NOT NULL DEFAULT 0,
            wrong_times INTEGER NOT NULL DEFAULT 0,
            mastery_level TEXT NOT NULL DEFAULT 'new'
        )
        """
    )

    cursor.execute(f"PRAGMA table_info({table_name})")
    existing_columns = {row[1] for row in cursor.fetchall()}

    if "first_test_date" not in existing_columns:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN first_test_date TEXT")


def ensure_wrong_notebook(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS wrong_notebook (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            library_name TEXT NOT NULL,
            english TEXT NOT NULL,
            chinese TEXT DEFAULT '',
            wrong_count INTEGER NOT NULL DEFAULT 1,
            last_wrong_date TEXT NOT NULL,
            UNIQUE (library_name, english)
        )
        """
    )


def ensure_library(table_name):
    with get_connection() as conn:
        cursor = conn.cursor()
        ensure_library_table(cursor, table_name)
        ensure_wrong_notebook(cursor)
        conn.commit()


def ensure_all_libraries():
    for table_name in LIBRARY_TABLES.values():
        ensure_library(table_name)


def format_datetime(value):
    if value is None:
        return ""
    return value.strftime("%Y-%m-%d %H:%M:%S")


def calculate_next_review(correct_times, is_known, current_time=None):
    current_time = current_time or datetime.now()

    if not is_known:
        return current_time + timedelta(minutes=10), "learning"

    interval_index = min(max(correct_times - 1, 0), len(REVIEW_INTERVAL_DAYS) - 1)
    next_review_time = current_time + timedelta(days=REVIEW_INTERVAL_DAYS[interval_index])

    if correct_times >= 5:
        mastery_level = "mastered"
    elif correct_times >= 2:
        mastery_level = "review"
    else:
        mastery_level = "learning"

    return next_review_time, mastery_level


def get_library_name(table_name):
    return TABLE_TO_LIBRARY.get(table_name, table_name)


def normalize_word_row(row):
    english = (row.get("english") or "").strip()
    chinese = (row.get("chinese") or "").strip()
    return english, chinese


def read_csv_rows(filename):
    last_error = None

    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            with open(filename, "r", newline="", encoding=encoding) as csvfile:
                return list(csv.DictReader(csvfile))
        except UnicodeDecodeError as exc:
            last_error = exc

    if last_error is not None:
        raise last_error

    return []


def import_new_words(filename, table_name):
    ensure_library(table_name)
    csv_rows = read_csv_rows(filename)
    rows_to_import = []

    for row in csv_rows:
        english, chinese = normalize_word_row(row)
        if english:
            rows_to_import.append((english, chinese))

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.executemany(
            f"""
            INSERT INTO {table_name} (
                english, chinese, practice_times, first_test_date, last_practice_date,
                next_review_date, correct_times, wrong_times, mastery_level
            )
            VALUES (?, ?, 0, NULL, NULL, NULL, 0, 0, 'new')
            ON CONFLICT(english) DO UPDATE SET
                chinese = CASE
                    WHEN excluded.chinese <> '' THEN excluded.chinese
                    ELSE {table_name}.chinese
                END
            """,
            rows_to_import,
        )
        conn.commit()

    return len(rows_to_import)


def get_library_word_count(table_name):
    ensure_library(table_name)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        return cursor.fetchone()[0]


def row_to_word(row):
    return {
        "english": row[0],
        "chinese": row[1] or "",
        "practice_times": row[2] or 0,
        "first_test_date": row[3] or "",
        "last_practice_date": row[4] or "",
        "next_review_date": row[5] or "",
        "correct_times": row[6] or 0,
        "wrong_times": row[7] or 0,
        "mastery_level": row[8] or "new",
    }


def get_words_for_test(table_name, test_quantity):
    ensure_library(table_name)
    now_text = format_datetime(datetime.now())

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
                 SELECT english, chinese, practice_times, first_test_date, last_practice_date,
                     next_review_date, correct_times, wrong_times, mastery_level
            FROM {table_name}
            WHERE next_review_date IS NULL OR next_review_date = '' OR next_review_date <= ?
            ORDER BY RANDOM()
            LIMIT ?
            """,
            (now_text, test_quantity),
        )
        selected_rows = cursor.fetchall()

        if len(selected_rows) < test_quantity:
            remaining = test_quantity - len(selected_rows)
            selected_words = {row[0] for row in selected_rows}

            if selected_words:
                placeholders = ", ".join("?" for _ in selected_words)
                cursor.execute(
                    f"""
                      SELECT english, chinese, practice_times, first_test_date, last_practice_date,
                          next_review_date, correct_times, wrong_times, mastery_level
                    FROM {table_name}
                    WHERE english NOT IN ({placeholders})
                    ORDER BY RANDOM()
                    LIMIT ?
                    """,
                    (*selected_words, remaining),
                )
            else:
                cursor.execute(
                    f"""
                      SELECT english, chinese, practice_times, first_test_date, last_practice_date,
                          next_review_date, correct_times, wrong_times, mastery_level
                    FROM {table_name}
                    ORDER BY RANDOM()
                    LIMIT ?
                    """,
                    (remaining,),
                )

            selected_rows.extend(cursor.fetchall())

    return [row_to_word(row) for row in selected_rows]


def update_wrong_notebook(cursor, table_name, english, chinese, current_time):
    library_name = get_library_name(table_name)
    cursor.execute(
        """
        INSERT INTO wrong_notebook (library_name, english, chinese, wrong_count, last_wrong_date)
        VALUES (?, ?, ?, 1, ?)
        ON CONFLICT(library_name, english) DO UPDATE SET
            chinese = excluded.chinese,
            wrong_count = wrong_notebook.wrong_count + 1,
            last_wrong_date = excluded.last_wrong_date
        """,
        (library_name, english, chinese or "", format_datetime(current_time)),
    )


def record_practice_result(table_name, english, is_known):
    ensure_library(table_name)
    current_time = datetime.now()

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT chinese, practice_times, first_test_date, correct_times, wrong_times
            FROM {table_name}
            WHERE english = ?
            """,
            (english,),
        )
        row = cursor.fetchone()

        if row is None:
            return None

        chinese, practice_times, first_test_date, correct_times, wrong_times = row
        practice_times += 1
        first_test_date = first_test_date or format_datetime(current_time)

        if is_known:
            correct_times += 1
            next_review_time, mastery_level = calculate_next_review(correct_times, True, current_time)
        else:
            wrong_times += 1
            correct_times = 0
            next_review_time, mastery_level = calculate_next_review(correct_times, False, current_time)
            update_wrong_notebook(cursor, table_name, english, chinese, current_time)

        cursor.execute(
            f"""
            UPDATE {table_name}
            SET practice_times = ?,
                first_test_date = ?,
                last_practice_date = ?,
                next_review_date = ?,
                correct_times = ?,
                wrong_times = ?,
                mastery_level = ?
            WHERE english = ?
            """,
            (
                practice_times,
                first_test_date,
                format_datetime(current_time),
                format_datetime(next_review_time),
                correct_times,
                wrong_times,
                mastery_level,
                english,
            ),
        )
        conn.commit()

    return {
        "english": english,
        "chinese": chinese or "",
        "practice_times": practice_times,
        "first_test_date": first_test_date,
        "correct_times": correct_times,
        "wrong_times": wrong_times,
        "next_review_date": format_datetime(next_review_time),
        "mastery_level": mastery_level,
    }


def clear_up_db(table_name):
    ensure_library(table_name)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM {table_name}")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name = ?", (table_name,))
        cursor.execute("DELETE FROM wrong_notebook WHERE library_name = ?", (get_library_name(table_name),))
        conn.commit()


def export_vocabulary_db(table_name, file_path):
    ensure_library(table_name)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
             SELECT english, chinese, practice_times, first_test_date, last_practice_date,
                 next_review_date, correct_times, wrong_times, mastery_level
            FROM {table_name}
            ORDER BY english ASC
            """
        )
        rows = cursor.fetchall()

    with open(file_path, mode="w", newline="", encoding="utf-8-sig") as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerow(
            [
                "english",
                "chinese",
                "practice_times",
                "first_test_date",
                "last_practice_date",
                "next_review_date",
                "correct_times",
                "wrong_times",
                "mastery_level",
            ]
        )
        csv_writer.writerows(rows)

    return len(rows)


def get_wrong_words(table_name=None, limit=50):
    ensure_all_libraries()

    with get_connection() as conn:
        cursor = conn.cursor()

        if table_name:
            cursor.execute(
                """
                SELECT library_name, english, chinese, wrong_count, last_wrong_date
                FROM wrong_notebook
                WHERE library_name = ?
                ORDER BY wrong_count DESC, last_wrong_date DESC
                LIMIT ?
                """,
                (get_library_name(table_name), limit),
            )
        else:
            cursor.execute(
                """
                SELECT library_name, english, chinese, wrong_count, last_wrong_date
                FROM wrong_notebook
                ORDER BY wrong_count DESC, last_wrong_date DESC
                LIMIT ?
                """,
                (limit,),
            )

        rows = cursor.fetchall()

    return [
        {
            "library_name": row[0],
            "english": row[1],
            "chinese": row[2] or "",
            "wrong_count": row[3] or 0,
            "last_wrong_date": row[4] or "",
        }
        for row in rows
    ]


def get_statistics(table_name):
    ensure_library(table_name)
    now_text = format_datetime(datetime.now())

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT
                COUNT(*),
                COALESCE(SUM(practice_times), 0),
                COALESCE(SUM(wrong_times), 0),
                COALESCE(SUM(CASE WHEN mastery_level = 'mastered' THEN 1 ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN mastery_level = 'learning' THEN 1 ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN mastery_level = 'review' THEN 1 ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN next_review_date IS NULL OR next_review_date = '' OR next_review_date <= ? THEN 1 ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN first_test_date IS NOT NULL AND first_test_date <> '' THEN 1 ELSE 0 END), 0)
            FROM {table_name}
            """,
            (now_text,),
        )
        row = cursor.fetchone()

        cursor.execute(
            "SELECT COUNT(*) FROM wrong_notebook WHERE library_name = ?",
            (get_library_name(table_name),),
        )
        wrong_notebook_count = cursor.fetchone()[0]

    return {
        "library_name": get_library_name(table_name),
        "total_words": row[0] or 0,
        "total_practice": row[1] or 0,
        "total_wrong": row[2] or 0,
        "mastered_words": row[3] or 0,
        "learning_words": row[4] or 0,
        "review_words": row[5] or 0,
        "due_words": row[6] or 0,
        "tested_words": row[7] or 0,
        "wrong_notebook_count": wrong_notebook_count,
    }


def get_recent_first_test_records(table_name, limit=10):
    ensure_library(table_name)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT english, chinese, first_test_date
            FROM {table_name}
            WHERE first_test_date IS NOT NULL AND first_test_date <> ''
            ORDER BY first_test_date DESC, english ASC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()

    return [
        {
            "english": row[0],
            "chinese": row[1] or "",
            "first_test_date": row[2] or "",
        }
        for row in rows
    ]


ensure_all_libraries()