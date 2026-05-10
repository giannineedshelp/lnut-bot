FROM python:3.12-slim

WORKDIR /app

# Install system deps (cryptography needs build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot source
COPY . .

# Persistent volume path for config.json
ENV CONFIG_DIR=/app/data

# Create required dirs
RUN mkdir -p /app/data /app/logs

# Run the bot
CMD ["python", "main.py"]

