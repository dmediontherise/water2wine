# water2wine

A simple, lightweight downloader that converts videos to MP3 or MP4 formats directly in your browser.

## Features

- **MP3 Conversion**: High-quality 192kbps audio extraction.
- **MP4 Downloads**: Support for multiple resolutions (1080p, 720p, 360p).
- **Real-time Streaming**: Downloads start immediately without waiting for server-side processing.
- **Clean UI**: Modern, responsive interface with dark mode support.
- **Rate Limiting**: Built-in protection to ensure service stability.

## Tech Stack

- **Backend**: FastAPI (Python)
- **Frontend**: Vanilla JavaScript, HTML5, CSS3
- **Tools**: `yt-dlp`, `ffmpeg`

## Local Setup

### Prerequisites

- Python 3.9+
- `ffmpeg` installed and available in your PATH.
- `yt-dlp` (installed via pip).

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yourusername/water2wine.git
   cd water2wine
   ```

2. **Set up the Backend**:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

3. **Run the Backend**:
   ```bash
   uvicorn main:app --reload
   ```
   The API will be available at `http://localhost:8000`.

4. **Set up the Frontend**:
   Since the frontend is static, you can serve it using any web server. For example, using Python's built-in server:
   ```bash
   cd ../frontend
   python -m http.server 3000
   ```
   Open `http://localhost:3000` in your browser.

## Deployment

### Backend (Render)

The backend is configured for deployment on [Render](https://render.com/).
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Environment Variables**:
  - `ALLOWED_ORIGIN`: Set this to your frontend URL (e.g., `https://yourname.github.io`).

### Frontend (GitHub Pages)

The frontend is configured for deployment on GitHub Pages via GitHub Actions.
- Push your changes to the `main` branch.
- The workflow in `.github/workflows/pages.yml` will automatically deploy the `frontend/` directory.

## License

MIT License
