# Use Debian slim (ML/scientific deps compile cleanly here)
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps for numpy/scikit-learn/matplotlib/cryptography/spaCy
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc g++ gfortran \
    libopenblas-dev liblapack-dev \
    libffi-dev libssl-dev \
    libglib2.0-0 libsm6 libxext6 libxrender1 \
    curl git \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (better layer caching)
COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir gunicorn

# Copy the rest
COPY . .

# Default port for local; Cloud Run injects $PORT
ENV PORT=8080

EXPOSE 8080

# app:app -> file app.py exposes Flask instance named "app"
CMD exec gunicorn -w 2 -k gthread --threads 4 --timeout 120 \
    -b 0.0.0.0:${PORT} app:app
