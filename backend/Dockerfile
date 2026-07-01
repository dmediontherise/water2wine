FROM python:3.11-slim

# Install ffmpeg, curl, unzip, and Node.js (Node required by bgutil PO token provider)
RUN apt-get update && apt-get install -y ffmpeg curl unzip && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# Install Deno (recommended JS runtime for yt-dlp EJS challenge solver)
RUN curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh
ENV DENO_DIR=/tmp/deno

# Install bgutil globally — provides YouTube PO tokens to bypass bot detection
RUN npm install -g @ybd-project/yt-dlp-utils

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy main.py
COPY main.py .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
