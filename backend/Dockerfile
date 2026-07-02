FROM python:3.11-slim

# Install ffmpeg, curl, and unzip
RUN apt-get update && apt-get install -y ffmpeg curl unzip && rm -rf /var/lib/apt/lists/*

# Install Deno (JS runtime for yt-dlp EJS challenge solver / remote-components)
RUN curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh
ENV DENO_DIR=/tmp/deno

# PO Token provider (bgutil-ytdlp-pot-provider, script mode) - required since
# YouTube now rejects most player requests without a valid PO token, even
# with cookies. Reuse the maintainer's own prebuilt Deno-flavored image
# instead of building the canvas native dependency ourselves.
COPY --from=brainicism/bgutil-ytdlp-pot-provider:1.3.1-deno /app /root/bgutil-ytdlp-pot-provider/server

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy main.py
COPY main.py .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
