FROM python:3.13-slim-bookworm

WORKDIR /app


COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование проекта
COPY . .

CMD ["python", "scheduler.py"]
