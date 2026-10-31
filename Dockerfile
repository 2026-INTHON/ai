FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY malo_ai ./malo_ai
RUN useradd --create-home malo && mkdir /data && chown malo:malo /data
ENV MALO_ENV=production MALO_AI_DATA_DIR=/data PYTHONUNBUFFERED=1
USER malo
EXPOSE 8000
CMD ["uvicorn", "malo_ai.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
