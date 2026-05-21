import os
import sys
import psycopg2


def get_database_connection():
    """Подключение к PostgreSQL через переменные окружения."""
    db_params = {
        "host": os.getenv("DB_HOST"),
        "port": os.getenv("DB_PORT"),
        "dbname": os.getenv("DB_NAME"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
    }

    try:
        connection = psycopg2.connect(**db_params)
        connection.autocommit = False
        return connection
    except Exception as err:
        print(f"Не удалось подключиться к базе: {err}")
        sys.exit(1)


def initialize_datamart_structure(cursor):
    """Создает схему и таблицу второй витрины."""
    sql_script = """
    CREATE SCHEMA IF NOT EXISTS dmr;

    CREATE TABLE IF NOT EXISTS dmr.analytics_student_performance (
        student_id         INTEGER NOT NULL,
        course_id          INTEGER NOT NULL,
        department_id      INTEGER,
        department_name    VARCHAR(255),
        education_level    VARCHAR(255),
        education_base     VARCHAR(255),
        semester           INTEGER,
        course_year        INTEGER,
        final_grade        INTEGER,
        total_events       INTEGER DEFAULT 0,
        avg_weekly_events  DECIMAL(10,2),
        total_course_views INTEGER DEFAULT 0,
        total_quiz_views   INTEGER DEFAULT 0,
        total_module_views INTEGER DEFAULT 0,
        total_submissions  INTEGER DEFAULT 0,
        peak_activity_week INTEGER,
        consistency_score  DECIMAL(5,2),
        activity_category  VARCHAR(50),
        last_update        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (student_id, course_id)
    );
    """
    cursor.execute(sql_script)


def extract_and_load_aggregates(cursor):
    """Загружает базовые поля и агрегированные суммы активности."""
    sql_script = """
    INSERT INTO dmr.analytics_student_performance (
        student_id,
        course_id,
        department_id,
        semester,
        course_year,
        final_grade,
        total_events,
        total_course_views,
        total_quiz_views,
        total_module_views,
        total_submissions
    )
    SELECT
        userid,
        courseid,
        MAX(depart) AS department_id,
        MAX(num_sem) AS semester,
        MAX(kurs) AS course_year,
        MAX(CAST(namer_level AS INTEGER)) AS final_grade,
        SUM(COALESCE(s_all, 0)) AS total_events,
        SUM(COALESCE(s_course_viewed, 0)) AS total_course_views,
        SUM(COALESCE(s_q_attempt_viewed, 0)) AS total_quiz_views,
        SUM(COALESCE(s_a_course_module_viewed, 0)) AS total_module_views,
        SUM(COALESCE(s_a_submission_status_viewed, 0)) AS total_submissions
    FROM public.user_logs
    WHERE namer_level IS NOT NULL
      AND namer_level IN ('2', '3', '4', '5')
    GROUP BY userid, courseid
    ON CONFLICT (student_id, course_id) DO UPDATE SET
        department_id = EXCLUDED.department_id,
        semester = EXCLUDED.semester,
        course_year = EXCLUDED.course_year,
        final_grade = EXCLUDED.final_grade,
        total_events = EXCLUDED.total_events,
        total_course_views = EXCLUDED.total_course_views,
        total_quiz_views = EXCLUDED.total_quiz_views,
        total_module_views = EXCLUDED.total_module_views,
        total_submissions = EXCLUDED.total_submissions,
        last_update = CURRENT_TIMESTAMP;
    """
    cursor.execute(sql_script)


def update_categorical_features(cursor):
    """Обновляет кафедру, уровень образования и основу обучения."""
    sql_script = """
    UPDATE dmr.analytics_student_performance AS t
    SET
        department_name = d.name,
        education_level = CASE CAST(s.leveled AS VARCHAR)
            WHEN '1' THEN 'бакалавриат'
            WHEN '2' THEN 'магистратура'
            ELSE 'иное'
        END,
        education_base = CASE CAST(s.name_osno AS VARCHAR)
            WHEN '1' THEN 'бюджет'
            WHEN '2' THEN 'контракт'
            ELSE 'иное'
        END,
        last_update = CURRENT_TIMESTAMP
    FROM (
        SELECT DISTINCT ON (userid, courseid)
            userid,
            courseid,
            leveled,
            name_osno,
            depart
        FROM public.user_logs
        ORDER BY userid, courseid, num_week DESC
    ) AS s
    LEFT JOIN public.departments d ON s.depart = d.id
    WHERE t.student_id = s.userid
      AND t.course_id = s.courseid;
    """
    cursor.execute(sql_script)


def compute_advanced_statistics(cursor):
    """Вычисляет среднее в неделю, стабильность и пиковую неделю."""
    sql_avg_consistency = """
    UPDATE dmr.analytics_student_performance AS t
    SET
        avg_weekly_events = ROUND(
            CAST(t.total_events AS NUMERIC) / NULLIF(s.total_weeks, 0),
            2
        ),
        consistency_score = ROUND(
            CAST(s.active_weeks AS NUMERIC) / NULLIF(s.total_weeks, 0),
            2
        ),
        last_update = CURRENT_TIMESTAMP
    FROM (
        SELECT
            userid,
            courseid,
            COUNT(DISTINCT num_week) AS total_weeks,
            COUNT(DISTINCT CASE WHEN COALESCE(s_all, 0) > 0 THEN num_week END) AS active_weeks
        FROM public.user_logs
        GROUP BY userid, courseid
    ) AS s
    WHERE t.student_id = s.userid
      AND t.course_id = s.courseid;
    """

    sql_peak_week = """
    WITH week_rankings AS (
        SELECT
            userid,
            courseid,
            num_week,
            ROW_NUMBER() OVER (
                PARTITION BY userid, courseid
                ORDER BY COALESCE(s_all, 0) DESC, num_week ASC
            ) AS week_rank
        FROM public.user_logs
    )
    UPDATE dmr.analytics_student_performance AS t
    SET
        peak_activity_week = wr.num_week,
        last_update = CURRENT_TIMESTAMP
    FROM week_rankings wr
    WHERE wr.week_rank = 1
      AND t.student_id = wr.userid
      AND t.course_id = wr.courseid;
    """

    cursor.execute(sql_avg_consistency)
    cursor.execute(sql_peak_week)


def set_engagement_levels(cursor):
    """Разбивает студентов на категории активности."""
    sql_script = """
    WITH quartiles AS (
        SELECT
            student_id,
            course_id,
            NTILE(4) OVER (ORDER BY COALESCE(total_events, 0) ASC) AS quartile
        FROM dmr.analytics_student_performance
    )
    UPDATE dmr.analytics_student_performance AS t
    SET
        activity_category = CASE
            WHEN q.quartile = 1 THEN 'низкая'
            WHEN q.quartile IN (2, 3) THEN 'средняя'
            WHEN q.quartile = 4 THEN 'высокая'
        END,
        last_update = CURRENT_TIMESTAMP
    FROM quartiles q
    WHERE t.student_id = q.student_id
      AND t.course_id = q.course_id;
    """
    cursor.execute(sql_script)


def create_student_performance_mart():
    """Основная функция сборки второй витрины."""
    db_conn = None

    try:
        print(
            f"Подключение к {os.getenv('DB_HOST')}:{os.getenv('DB_PORT')} "
            f"/ база {os.getenv('DB_NAME')} ..."
        )

        db_conn = get_database_connection()

        with db_conn.cursor() as cursor:
            initialize_datamart_structure(cursor)
            extract_and_load_aggregates(cursor)
            update_categorical_features(cursor)
            compute_advanced_statistics(cursor)
            set_engagement_levels(cursor)

        db_conn.commit()
        print("Витрина dmr.analytics_student_performance успешно создана/обновлена.")

    except Exception as err:
        print(f"[CRITICAL ERROR] Откат транзакции: {err}")

        if db_conn:
            db_conn.rollback()

        raise

    finally:
        if db_conn:
            db_conn.close()
            print("Соединение с БД закрыто.")


if __name__ == "__main__":
    create_student_performance_mart()