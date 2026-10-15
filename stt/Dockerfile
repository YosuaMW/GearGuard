FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir faster-whisper fastapi "uvicorn[standard]" python-multipart
WORKDIR /app
COPY app.py .
ENV HF_HOME=/models
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9000"]
