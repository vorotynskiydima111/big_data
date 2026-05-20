# Используем официальный образ PostgreSQL
FROM postgres:13

# Копируем datasets внутрь контейнера, чтобы init.sh мог загрузить CSV в БД
COPY datasets /datasets/

# Копируем скрипт инициализации БД.
# Все файлы из /docker-entrypoint-initdb.d выполняются при первом создании volume.
COPY init.sh /docker-entrypoint-initdb.d/init.sh
RUN chmod +x /docker-entrypoint-initdb.d/init.sh
