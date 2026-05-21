import os
import sys
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator


SCRIPTS_PATH = os.path.join(os.path.dirname(__file__), "scripts")
sys.path.insert(0, SCRIPTS_PATH)

from build_student_performance_mart import create_student_performance_mart


default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "start_date": datetime(2024, 1, 1),
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


with DAG(
    dag_id="create_student_performance_mart",
    default_args=default_args,
    description="Создание и обновление витрины dmr.analytics_student_performance",
    schedule_interval=None,
    catchup=False,
    tags=["mart", "student_performance"],
) as dag:

    create_student_performance_task = PythonOperator(
        task_id="create_student_performance_mart",
        python_callable=create_student_performance_mart,
    )

    create_student_performance_task