FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv/mhd

# 先装依赖，利用层缓存
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码（科学计算只用标准库，无额外系统依赖）
COPY app ./app
COPY wsgi.py ./

EXPOSE 8000

# 容器内只有这一个服务，直接用 Flask 内置服务器即可
CMD ["python", "-m", "flask", "--app", "wsgi:app", "run", "--host", "0.0.0.0", "--port", "8000"]
