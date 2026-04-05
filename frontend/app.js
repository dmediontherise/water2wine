/**
 * water2wine — Premium Frontend Logic
 * Real-time download progress, toast notifications, smart format switching.
 */

document.addEventListener('DOMContentLoaded', () => {
    // ── DOM Elements ──
    const videoUrlInput    = document.getElementById('video-url');
    const fetchInfoBtn     = document.getElementById('fetch-info-btn');
    const inputHint        = document.getElementById('input-hint');
    const previewSection   = document.getElementById('preview-section');
    const videoThumbnail   = document.getElementById('video-thumbnail');
    const videoDuration    = document.getElementById('video-duration');
    const videoTitle       = document.getElementById('video-title');
    const videoChannel     = document.getElementById('video-channel');
    const formatSelect     = document.getElementById('format-select');
    const qualitySelect    = document.getElementById('quality-select');
    const downloadBtn      = document.getElementById('download-btn');
    const retryBtn         = document.getElementById('retry-btn');

    // Progress — Processing
    const progressProcessing = document.getElementById('progress-processing');
    const processingBar      = document.getElementById('processing-bar');
    const processingPct      = document.getElementById('processing-pct');
    const processingStatus   = document.getElementById('processing-status');

    // Progress — Download
    const progressDownload = document.getElementById('progress-download');
    const downloadBar      = document.getElementById('download-bar');
    const downloadPct      = document.getElementById('download-pct');
    const downloadStatus   = document.getElementById('download-status');

    // Toast
    const toastContainer = document.getElementById('toast-container');

    // ── Constants ──
    const YOUTUBE_REGEX = /^(https?:\/\/)?(www\.)?(youtube\.com\/(watch\?.*v=|shorts\/|live\/)|youtu\.be\/|m\.youtube\.com\/(watch\?.*v=))[\w-]+/;
    const API_BASE = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
        ? 'http://localhost:8000'
        : 'https://youtube-converter-api-zy86.onrender.com';

    // State
    let lastDownloadParams = null;
    let currentVideoInfo = null;
    let downloadAbortController = null;

    // ── Toast System ──
    function toast(message, type = 'info', duration = 4000) {
        const icons = {
            success: 'fas fa-check-circle',
            error: 'fas fa-exclamation-circle',
            warning: 'fas fa-exclamation-triangle',
            info: 'fas fa-info-circle'
        };
        const el = document.createElement('div');
        el.className = `toast toast-${type}`;
        el.innerHTML = `<i class="toast-icon ${icons[type] || icons.info}"></i><span>${message}</span>`;
        toastContainer.appendChild(el);

        setTimeout(() => {
            el.classList.add('removing');
            setTimeout(() => el.remove(), 300);
        }, duration);
    }

    // ── URL Validation ──
    function validateUrl() {
        const url = videoUrlInput.value.trim();
        const valid = YOUTUBE_REGEX.test(url);
        fetchInfoBtn.disabled = !valid;
        if (url.length > 5 && !valid) {
            inputHint.textContent = 'Hmm, that doesn\'t look like a YouTube link';
            inputHint.style.color = 'var(--error)';
        } else {
            inputHint.textContent = 'Supports youtube.com, youtu.be, shorts, and live links';
            inputHint.style.color = '';
        }
    }

    // ── Format Helpers ──
    const MP3_FORMATS = [
        { id: 'mp3-192', ext: 'mp3', quality: '192k', note: 'Standard Quality' },
        { id: 'mp3-320', ext: 'mp3', quality: '320k', note: 'High Quality' }
    ];
    const MP4_FORMATS = [
        { id: 'mp4-360',  ext: 'mp4', quality: '360p',  note: 'Standard Definition' },
        { id: 'mp4-720',  ext: 'mp4', quality: '720p',  note: 'HD' },
        { id: 'mp4-1080', ext: 'mp4', quality: '1080p', note: 'Full HD' }
    ];

    function populateQualityOptions() {
        const fmt = formatSelect.value;
        const opts = fmt === 'mp3' ? MP3_FORMATS : MP4_FORMATS;
        qualitySelect.innerHTML = '';
        opts.forEach(o => {
            const option = document.createElement('option');
            option.value = o.quality;
            option.textContent = `${o.quality} — ${o.note}`;
            qualitySelect.appendChild(option);
        });
        // Default to best
        qualitySelect.value = opts[opts.length - 1].quality;
    }

    // ── Progress Helpers ──
    function showProcessing(message) {
        progressProcessing.classList.remove('hidden');
        progressDownload.classList.add('hidden');
        retryBtn.classList.add('hidden');
        processingBar.classList.add('indeterminate');
        processingBar.classList.remove('complete');
        processingBar.style.width = '';
        processingPct.textContent = '—';
        processingStatus.textContent = message;
        downloadBtn.disabled = true;
    }

    function updateProcessing(pct, message) {
        processingBar.classList.remove('indeterminate');
        processingBar.style.width = pct + '%';
        processingPct.textContent = pct + '%';
        if (message) processingStatus.textContent = message;
    }

    function completeProcessing() {
        processingBar.classList.remove('indeterminate');
        processingBar.classList.add('complete');
        processingBar.style.width = '100%';
        processingPct.textContent = '100%';
        processingStatus.textContent = 'Processing complete!';
    }

    function showDownloadProgress() {
        progressDownload.classList.remove('hidden');
        downloadBar.style.width = '0%';
        downloadBar.classList.remove('complete');
        downloadPct.textContent = '0%';
        downloadStatus.textContent = 'Starting download...';
    }

    function updateDownloadProgress(received, total) {
        if (total > 0) {
            const pct = Math.min(Math.round((received / total) * 100), 100);
            downloadBar.style.width = pct + '%';
            downloadPct.textContent = pct + '%';
            const receivedMB = (received / (1024 * 1024)).toFixed(1);
            const totalMB = (total / (1024 * 1024)).toFixed(1);
            downloadStatus.textContent = `${receivedMB} MB / ${totalMB} MB`;
        } else {
            // No content-length — show received only
            const receivedMB = (received / (1024 * 1024)).toFixed(1);
            downloadBar.classList.add('indeterminate');
            downloadStatus.textContent = `${receivedMB} MB downloaded`;
        }
    }

    function completeDownload() {
        downloadBar.classList.remove('indeterminate');
        downloadBar.classList.add('complete');
        downloadBar.style.width = '100%';
        downloadPct.textContent = '100%';
        downloadStatus.textContent = 'Download complete!';
    }

    function hideAllProgress() {
        progressProcessing.classList.add('hidden');
        progressDownload.classList.add('hidden');
        downloadBtn.disabled = false;
    }

    // ── Fetch Video Info ──
    async function getInfo(url) {
        showProcessing('Analyzing video...');
        previewSection.classList.add('hidden');

        const phases = [
            { delay: 2000, pct: 20,  msg: 'Contacting YouTube...' },
            { delay: 4000, pct: 45,  msg: 'Extracting metadata...' },
            { delay: 7000, pct: 65,  msg: 'Resolving formats...' },
            { delay: 10000, pct: 80, msg: 'Almost there...' }
        ];
        const timers = phases.map(p =>
            setTimeout(() => updateProcessing(p.pct, p.msg), p.delay)
        );

        try {
            const response = await fetch(`${API_BASE}/api/info?url=${encodeURIComponent(url)}`);
            timers.forEach(clearTimeout);

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || 'Failed to fetch video info');
            }

            const info = await response.json();
            currentVideoInfo = info;

            // Animate to 100%
            updateProcessing(100, 'Analysis complete!');
            setTimeout(completeProcessing, 200);

            // Populate UI
            videoThumbnail.src = info.thumbnail;
            videoDuration.textContent = info.duration_formatted;
            videoTitle.textContent = info.title;

            videoChannel.textContent = '';
            const icon = document.createElement('i');
            icon.className = 'fas fa-user-circle';
            videoChannel.appendChild(icon);
            videoChannel.appendChild(document.createTextNode(` ${info.channel}`));

            populateQualityOptions();

            // Reveal card
            setTimeout(() => {
                previewSection.classList.remove('hidden');
                hideAllProgress();
            }, 600);

            toast('Video analyzed successfully!', 'success');
        } catch (error) {
            timers.forEach(clearTimeout);
            hideAllProgress();
            toast(error.message, 'error', 6000);
        }
    }

    // ── Browser Detection ──
    const ua = navigator.userAgent || '';
    const isIOS = /iPad|iPhone|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    const isSafari = /^((?!chrome|android).)*safari/i.test(ua);
    const isFirefox = /firefox/i.test(ua);
    const isMobile = isIOS || /Android/i.test(ua);
    const supportsReadableStream = typeof ReadableStream !== 'undefined'
        && typeof Response !== 'undefined'
        && typeof Response.prototype.body !== 'undefined'
        && typeof ReadableStream.prototype.getReader === 'function';

    /**
     * Determines the best download strategy for the current browser.
     * 'stream'  — fetch + ReadableStream reader + blob (Chrome/Edge desktop: full progress)
     * 'blob'    — fetch + response.blob() (Firefox, Android Chrome: no granular progress but reliable)
     * 'native'  — window.open / link click to let browser handle natively (Safari, iOS: most compatible)
     */
    function getDownloadStrategy() {
        if (isIOS) return 'native';           // iOS blob downloads are broken
        if (isSafari) return 'native';        // Safari blob downloads open in tab
        if (!supportsReadableStream) return 'blob';
        if (isFirefox && isMobile) return 'blob';
        return 'stream';
    }

    // ── Save Blob Cross-Browser ──
    function saveBlob(blob, filename) {
        // Try navigator.msSaveOrOpenBlob for old Edge (unlikely but safe)
        if (typeof navigator.msSaveOrOpenBlob === 'function') {
            navigator.msSaveOrOpenBlob(blob, filename);
            return;
        }

        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.style.display = 'none';
        document.body.appendChild(a);

        // Use click event dispatch for better compatibility
        const clickEvent = new MouseEvent('click', {
            bubbles: true,
            cancelable: true,
            view: window
        });
        a.dispatchEvent(clickEvent);

        // Delay revoke to give the browser time to initiate
        setTimeout(() => {
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }, 5000);
    }

    // ── Download with Progress ──
    async function startDownload(url, format, quality) {
        lastDownloadParams = { url, format, quality };
        retryBtn.classList.add('hidden');

        const title = videoTitle.textContent || 'video';
        const duration = currentVideoInfo ? currentVideoInfo.duration : 0;
        const ext = format === 'mp3' ? 'mp3' : 'mp4';
        const safeTitle = title.replace(/[^\w\s.-]/g, '').trim().slice(0, 80) || 'download';
        const filename = `${safeTitle}.${ext}`;
        const downloadUrl = `${API_BASE}/api/download?url=${encodeURIComponent(url)}&format=${format}&quality=${quality}&title=${encodeURIComponent(title)}&duration=${duration}`;

        const strategy = getDownloadStrategy();
        console.log(`[Download] Strategy: ${strategy}, iOS: ${isIOS}, Safari: ${isSafari}, Mobile: ${isMobile}`);

        // ─── Strategy: NATIVE (Safari / iOS) ───
        // Let the browser handle the download natively — most reliable on Safari/iOS
        if (strategy === 'native') {
            showProcessing(`Preparing ${format.toUpperCase()} download...`);

            const processingTimers = [
                setTimeout(() => updateProcessing(20, 'Connecting to server...'), 1500),
                setTimeout(() => updateProcessing(50, 'Server is processing...'), 4000),
                setTimeout(() => updateProcessing(75, 'Almost ready...'), 8000),
            ];

            // Open in same window — Safari will show its own download indicator
            // Using a hidden iframe avoids navigating away from the page
            const iframe = document.createElement('iframe');
            iframe.style.display = 'none';
            iframe.src = downloadUrl;
            document.body.appendChild(iframe);

            // Also try a direct link in case iframe doesn't trigger download
            setTimeout(() => {
                const a = document.createElement('a');
                a.href = downloadUrl;
                a.download = filename;
                a.style.display = 'none';
                document.body.appendChild(a);
                a.click();
                setTimeout(() => {
                    a.remove();
                    iframe.remove();
                }, 10000);
            }, 500);

            processingTimers.forEach(clearTimeout);
            completeProcessing();
            toast(`Download started! Check your browser's download bar.`, 'success');

            setTimeout(() => {
                hideAllProgress();
            }, 3000);
            return;
        }

        // ─── Phase 1: Processing indicator ───
        showProcessing(`Preparing ${format.toUpperCase()} stream...`);

        const processingPhases = [
            { delay: 1500, pct: 15, msg: 'Extracting stream URL...' },
            { delay: 3500, pct: 35, msg: 'Resolving media sources...' },
            { delay: 6000, pct: 55, msg: 'Starting conversion...' },
            { delay: 9000, pct: 75, msg: 'Buffering stream...' }
        ];
        const timers = processingPhases.map(p =>
            setTimeout(() => updateProcessing(p.pct, p.msg), p.delay)
        );

        try {
            downloadAbortController = new AbortController();

            const response = await fetch(downloadUrl, {
                signal: downloadAbortController.signal
            });

            timers.forEach(clearTimeout);

            if (!response.ok) {
                let errMsg = 'Download failed';
                try {
                    const err = await response.json();
                    errMsg = err.detail || errMsg;
                } catch {}
                throw new Error(errMsg);
            }

            completeProcessing();

            // ─── Strategy: STREAM (Chrome/Edge desktop) ───
            if (strategy === 'stream') {
                setTimeout(() => {
                    progressProcessing.classList.add('hidden');
                    showDownloadProgress();
                }, 400);

                const contentLength = parseInt(response.headers.get('Content-Length') || '0', 10);
                const reader = response.body.getReader();
                const chunks = [];
                let received = 0;

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    chunks.push(value);
                    received += value.length;
                    updateDownloadProgress(received, contentLength);
                }

                completeDownload();

                const mimeType = format === 'mp3' ? 'audio/mpeg' : 'video/mp4';
                const blob = new Blob(chunks, { type: mimeType });
                saveBlob(blob, filename);

            // ─── Strategy: BLOB (Firefox, Android) ───
            } else {
                setTimeout(() => {
                    progressProcessing.classList.add('hidden');
                    showDownloadProgress();
                    downloadStatus.textContent = 'Downloading file...';
                    downloadBar.classList.add('indeterminate');
                    downloadPct.textContent = '—';
                }, 400);

                const blob = await response.blob();
                completeDownload();
                saveBlob(blob, filename);
            }

            toast(`${format.toUpperCase()} downloaded successfully!`, 'success');

            setTimeout(() => {
                hideAllProgress();
            }, 2000);

        } catch (error) {
            timers.forEach(clearTimeout);

            if (error.name === 'AbortError') {
                toast('Download cancelled', 'warning');
                hideAllProgress();
                return;
            }

            // Fallback: if fetch-based download fails, try native
            console.warn('[Download] Fetch strategy failed, falling back to native:', error.message);
            progressProcessing.classList.add('hidden');
            progressDownload.classList.add('hidden');

            try {
                toast('Trying alternative download method...', 'warning', 3000);
                const a = document.createElement('a');
                a.href = downloadUrl;
                a.download = filename;
                a.style.display = 'none';
                document.body.appendChild(a);
                a.click();
                setTimeout(() => a.remove(), 5000);
                downloadBtn.disabled = false;
            } catch (fallbackError) {
                downloadBtn.disabled = false;
                retryBtn.classList.remove('hidden');
                toast(`Download failed: ${error.message}`, 'error', 6000);
            }
        }
    }

    // ── Event Listeners ──
    videoUrlInput.addEventListener('input', validateUrl);

    // Enter key to analyze
    videoUrlInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !fetchInfoBtn.disabled) {
            fetchInfoBtn.click();
        }
    });

    fetchInfoBtn.addEventListener('click', () => {
        const url = videoUrlInput.value.trim();
        if (YOUTUBE_REGEX.test(url)) getInfo(url);
    });

    formatSelect.addEventListener('change', populateQualityOptions);

    downloadBtn.addEventListener('click', () => {
        const url = videoUrlInput.value.trim();
        const format = formatSelect.value;
        const quality = qualitySelect.value;
        startDownload(url, format, quality);
    });

    retryBtn.addEventListener('click', () => {
        if (lastDownloadParams) {
            const { url, format, quality } = lastDownloadParams;
            startDownload(url, format, quality);
        }
    });

    // Init
    validateUrl();
    populateQualityOptions();
});
