FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY seed.py .

RUN mkdir -p /app/data
VOLUME ["/app/data"]

# 初始化（建表 + 演示数据 + v1），随后以 gunicorn 启动
CMD ["sh", "-c", "python seed.py && gunicorn --bind 0.0.0.0:8000 --workers ${GUNICORN_WORKERS:-2} --threads 4 --access-logfile - 'app:app'"]
