
import os
import sys
import psycopg2
from dotenv import load_dotenv

# Инициализация переменных окружения
load_dotenv()

def get_database_connection():
    """Подключение к PostgreSQL через параметры из .env."""
    db_params = {
        'host': os.getenv('DB_HOST'),
        'port': os.getenv('DB_PORT'),
        'dbname': os.getenv('DB_NAME'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD')
    }
    
    try:
        connection = psycopg2.connect(**db_params)
        connection.autocommit = False
        return connection
    except Exception as err:
        print(f" Не удалось подключиться к базе: {err}")
        sys.exit(1)

def initialize_datamart_structure(cursor):
    """Создает схему и пустую таблицу витрины."""
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
    """Загружает идентификаторы и агрегированные суммы событий за семестр."""
    sql_script = """
    INSERT INTO dmr.analytics_student_performance (
        student_id, course_id, department_id, semester, course_year, final_grade,
        total_events, total_course_views, total_quiz_views, total_module_views, total_submissions
    )
    SELECT 
        userid, 
        courseid, 
        MAX(Depart), 
        MAX(Num_Sem), 
        MAX(Kurs), 
        MAX(CAST(NameR_Level AS INTEGER)),
        SUM(COALESCE(s_all, 0)),
        SUM(COALESCE(s_course_viewed, 0)),
        SUM(COALESCE(s_q_attempt_viewed, 0)),
        SUM(COALESCE(s_a_course_module_viewed, 0)),
        SUM(COALESCE(s_a_submission_status_viewed, 0))
    FROM public.user_logs
    WHERE NameR_Level IS NOT NULL AND NameR_Level ~ '^[0-9]+$'
    GROUP BY userid, courseid
    ON CONFLICT (student_id, course_id) DO UPDATE SET
        total_events = EXCLUDED.total_events,
        total_course_views = EXCLUDED.total_course_views,
        total_quiz_views = EXCLUDED.total_quiz_views,
        total_module_views = EXCLUDED.total_module_views,
        total_submissions = EXCLUDED.total_submissions,
        last_update = CURRENT_TIMESTAMP;
    """
    cursor.execute(sql_script)
   

def update_categorical_features(cursor):
    """Обновляет строковые поля (названия кафедр и формы обучения)."""
    sql_script = """
    UPDATE dmr.analytics_student_performance AS t
    SET 
        department_name = d.name,
        education_level = CASE CAST(s.LevelEd AS VARCHAR)
            WHEN '1' THEN 'бакалавриат' 
            WHEN '2' THEN 'магистратура' 
            ELSE 'иное' 
        END,
        education_base = CASE CAST(s.Name_OsnO AS VARCHAR)
            WHEN '1' THEN 'бюджет' 
            WHEN '2' THEN 'контракт' 
            ELSE 'иное' 
        END
    FROM (
        -- Добавили поле Depart сюда, чтобы использовать его для JOIN
        SELECT DISTINCT ON (userid, courseid) 
            userid, courseid, LevelEd, Name_OsnO, Depart 
        FROM public.user_logs
    ) AS s
    -- Теперь мы джоиним справочник со временной таблицей s, а не с t
    LEFT JOIN public.departments d ON s.Depart = d.id
    WHERE t.student_id = s.userid AND t.course_id = s.courseid;
    """
    cursor.execute(sql_script)
    
def compute_advanced_statistics(cursor):
    """Вычисляет производные метрики: стабильность, среднее в неделю и пик активности."""
    
    # Расчет средних показателей и коэффициента стабильности
    sql_avg_consistency = """
    UPDATE dmr.analytics_student_performance AS t
    SET 
        avg_weekly_events = ROUND(CAST(t.total_events AS NUMERIC) / NULLIF(s.total_weeks, 0), 2),
        consistency_score = ROUND(CAST(s.active_weeks AS NUMERIC) / NULLIF(s.total_weeks, 0), 2)
    FROM (
        SELECT 
            userid, 
            courseid, 
            COUNT(DISTINCT num_week) AS total_weeks, 
            COUNT(DISTINCT CASE WHEN s_all > 0 THEN num_week END) AS active_weeks 
        FROM public.user_logs 
        GROUP BY userid, courseid
    ) AS s
    WHERE t.student_id = s.userid AND t.course_id = s.courseid;
    """

    # Определение пиковой недели
    sql_peak_week = """
    WITH WeekRankings AS (
        SELECT 
            userid, 
            courseid, 
            num_week,
            ROW_NUMBER() OVER (PARTITION BY userid, courseid ORDER BY s_all DESC) AS rank
        FROM public.user_logs
    )
    UPDATE dmr.analytics_student_performance AS t
    SET peak_activity_week = wr.num_week
    FROM WeekRankings wr
    WHERE wr.rank = 1 
      AND t.student_id = wr.userid 
      AND t.course_id = wr.courseid;
    """
    cursor.execute(sql_avg_consistency)
    cursor.execute(sql_peak_week)
    

def set_engagement_levels(cursor):
    """Разбивает студентов на группы активности через квартили """
    # Использование NTILE(4) делит выборку на 4 равные части,
    # что является красивой альтернативой PERCENT_RANK()
    sql_script = """
    WITH Quartiles AS (
        SELECT 
            student_id, 
            course_id, 
            NTILE(4) OVER (ORDER BY total_events ASC) AS quartile
        FROM dmr.analytics_student_performance
    )
    UPDATE dmr.analytics_student_performance AS t
    SET activity_category = CASE 
            WHEN q.quartile = 1 THEN 'низкая'
            WHEN q.quartile IN (2, 3) THEN 'средняя'
            WHEN q.quartile = 4 THEN 'высокая'
        END
    FROM Quartiles q
    WHERE t.student_id = q.student_id AND t.course_id = q.course_id;
    """
    cursor.execute(sql_script)
    
def execute_etl_pipeline():
    """Точка входа и оркестрация процесса."""
    db_conn = None
    try:
        
        db_conn = get_database_connection()
        
        with db_conn.cursor() as cursor:
            initialize_datamart_structure(cursor)
            extract_and_load_aggregates(cursor)
            update_categorical_features(cursor)
            compute_advanced_statistics(cursor)
            set_engagement_levels(cursor)
            
        db_conn.commit()
        
        
    except Exception as err:
        print(f"\n[CRITICAL ERROR] Откат транзакции: {err}")
        if db_conn:
            db_conn.rollback()
    finally:
        if db_conn:
            db_conn.close()

if __name__ == "__main__":
    execute_etl_pipeline()