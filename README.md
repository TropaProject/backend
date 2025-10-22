# Руководство по запуску Django проекта

### Предварительные требования
- Python 3.8 или выше
- PostgreSQL 12+
- pip (менеджер пакетов Python)
- pgAdmin
### 1. Создание и активация виртуального окружения
Windows
```
# Создание виртуального окружения
python -m venv venv

# Активация виртуального окружения
venv\Scripts\activate
```
macOS/Linux
```
# Создание виртуального окружения
python3 -m venv venv
# Активация виртуального окружения
source venv/bin/activate
```
Примечание: После активации виртуального окружения в командной строке должен отображаться префикс (venv)

### 2. Установка зависимостей
```
pip install -r requirements.txt
```
### 3. Создание базы данных
1. Откройте pgAdmin → подключитесь к серверу

2. Правой кнопкой на Databases → Create → Database

### 4. Настройка переменных окружения
Создайте файл .env в корне проекта:
```
SECRET_KEY=key
DEBUG=True
ALLOWED_HOSTS=*

DB_NAME=your_database_name
DB_USER=your_database_user
DB_PASSWORD=your_database_password
DB_HOST=localhost
DB_PORT=5432

CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
GEOAPIFY_API_KEY=your_geoapify_api_key_here #Пока оставить пустые
OPENAI_API_KEY=your_openai_api_key_here #Пока оставить пустые
```
### 5. Миграции базы данных
```
#Создание миграций
python manage.py makemigrations
# Применение миграций
python manage.py migrate
```
### 6. Создание суперпользователя
```
python manage.py createsuperuser
```
Следуйте инструкциям для ввода данных.

### 7. Запуск сервера разработки
bash
python manage.py runserver
Сервер будет доступен по адресу: http://localhost:8000
