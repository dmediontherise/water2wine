FROM python:3.11-slim

# Install ffmpeg and nodejs for bot bypassing
RUN apt-get update && apt-get install -y ffmpeg nodejs npm && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy main.py
COPY main.py .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
