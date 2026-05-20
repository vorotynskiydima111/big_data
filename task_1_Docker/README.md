# Big Data — task1

## Описание проекта

В проекте запускается контейнер PostgreSQL через Docker Compose.

При первом запуске автоматически создаётся база данных `user_logs_db` и загружаются данные из CSV-файлов.

В скрипте `init.sh` выполняется:

1. Создание таблицы `departments` со справочником кафедр.
2. Создание таблицы `user_logs` с логами пользователей.
3. Загрузка данных из файла `datasets/departments.csv`.
4. Загрузка данных из файла `datasets/aggrigation_logs_per_week.csv`.
5. Поле `Depart` в таблице `user_logs` используется как `INTEGER`.
6. Таблица `user_logs` связывается с таблицей `departments` по полю `Depart`.

В базе данных создаются 2 таблицы:

- `departments`
- `user_logs`

Количество записей в таблице `user_logs`: `414528`.

## Переменные окружения

В файле `.env` указаны параметры подключения к базе данных:

```env
DB_USER=user
DB_PASSWORD=password
DB_NAME=user_logs_db
DB_PORT=5432
VOLUME_NAME=user_logs_pgdata
```

## Запуск проекта

Перейти в папку задания:

```bash
cd big_data/task1
```

Удалить старый контейнер и volume, если проект уже запускался:

```bash
docker compose down -v
```

Запустить сборку и контейнер:

```bash
docker compose up --build
```

## Подключение к контейнеру

Получить ID контейнера:

```bash
docker ps
```

Войти внутрь контейнера:

```bash
docker exec -it CONTAINER_ID bash
```

Также можно войти по имени контейнера:

```bash
docker exec -it postgres_logs_db bash
```

## Подключение к базе данных

Подключиться к базе данных внутри контейнера:

```bash
psql -U user -d user_logs_db
```

## Проверка таблиц

Вывести список таблиц:

```sql
\dt
```

В базе данных должно быть 2 таблицы:

- `departments`
- `user_logs`

## Вывод первых 10 строк таблицы user_logs

```sql
SELECT * FROM user_logs LIMIT 10;
```

## Количество записей в таблице user_logs

```sql
SELECT COUNT(*) FROM user_logs;
```

Результат:

```text
414528
```

## Вывод первых 10 записей с названием кафедры

Вывести `userid`, `courseid` и название кафедры из таблицы `departments`:

```sql
SELECT
    ul.userid,
    ul.courseid,
    d.name AS department_name
FROM user_logs ul
JOIN departments d ON ul.Depart = d.id
LIMIT 10;
```

Пример результата:

```text
 userid | courseid | department_name
--------+----------+-----------------
 34527  | 71262    | ПМиИ
 34527  | 71262    | ПМиИ
 34527  | 71262    | ПМиИ
```

## Выход

Выйти из psql:

```sql
\q
```

Выйти из контейнера:

```bash
exit
```
