FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY infer.py .
COPY models ./models

RUN pip install --no-cache-dir \
    ultralytics \
    torch torchvision \
    fastapi \
    uvicorn \
    pillow \
    python-multipart \
    opencv-python-headless

CMD ["uvicorn", "infer:app", "--host", "0.0.0.0", "--port", "5000"]
