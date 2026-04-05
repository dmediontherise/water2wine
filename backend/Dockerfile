FROM python:3.11-slim

# Install ffmpeg, curl, and unzip for Deno installation
RUN apt-get update && apt-get install -y ffmpeg curl unzip && rm -rf /var/lib/apt/lists/*

# Install Deno (recommended JS runtime for yt-dlp EJS challenge solver)
RUN curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh
ENV DENO_DIR=/tmp/deno

WORKDIR /app

# Copy requirements and install (yt-dlp[default] includes yt-dlp-ejs solver scripts)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy main.py
COPY main.py .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
