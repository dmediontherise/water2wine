/**
 * water2wine — Premium Frontend Logic
 * Real-time download progress, toast notifications, smart format switching.
 */

document.addEventListener('DOMContentLoaded', function() {
    'use strict';

    // ── DOM Elements ──
    var videoUrlInput    = document.getElementById('video-url');
    var fetchInfoBtn     = document.getElementById('fetch-info-btn');
    var inputHint        = document.getElementById('input-hint');
    var previewSection   = document.getElementById('preview-section');
    var videoThumbnail   = document.getElementById('video-thumbnail');
    var videoDuration    = document.getElementById('video-duration');
    var videoTitle       = document.getElementById('video-title');
    var videoChannel     = document.getElementById('video-channel');
    var formatSelect     = document.getElementById('format-select');
    var qualitySelect    = document.getElementById('quality-select');
    var downloadBtn      = document.getElementById('download-btn');
    var retryBtn         = document.getElementById('retry-btn');

    // Progress — Processing
    var progressProcessing = document.getElementById('progress-processing');
    var processingBar      = document.getElementById('processing-bar');
    var processingPct      = document.getElementById('processing-pct');
    var processingStatus   = document.getElementById('processing-status');

    // Progress — Download
    var progressDownload = document.getElementById('progress-download');
    var downloadBar      = document.getElementById('download-bar');
    var downloadPct      = document.getElementById('download-pct');
    var downloadStatus   = document.getElementById('download-status');

    // Toast
    var toastContainer = document.getElementById('toast-container');

    // ── Abort early if DOM missing ──
    if (!videoUrlInput || !fetchInfoBtn) {
        console.error('[water2wine] Critical DOM elements missing!');
        return;
    }
    console.log('[water2wine] Script loaded, DOM elements found.');

    // ── Constants ──
    var API_BASE = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
        ? 'http://localhost:8000'
        : 'https://youtube-converter-api-zy86.onrender.com';

    // State
    var lastDownloadParams = null;
    var currentVideoInfo = null;
    var downloadAbortController = null;

    // ── URL Validation ──
    function isYouTubeUrl(url) {
        if (!url) return false;
        try {
            if (url.indexOf('youtu.be/') !== -1) return true;
            if (url.indexOf('youtube.com/watch') !== -1 && url.indexOf('v=') !== -1) return true;
            if (url.indexOf('youtube.com/shorts/') !== -1) return true;
            if (url.indexOf('youtube.com/live/') !== -1) return true;
            if (url.indexOf('youtube.com/embed/') !== -1) return true;
            if (url.indexOf('youtube.com/v/') !== -1) return true;
        } catch (e) {
            // ignore
        }
        return false;
    }

    function validateUrl() {
        var url = videoUrlInput.value.trim();
        var valid = isYouTubeUrl(url);
        fetchInfoBtn.disabled = !valid;
        if (url.length > 5 && !valid) {
            inputHint.textContent = "Hmm, that doesn't look like a YouTube link";
            inputHint.style.color = 'var(--error)';
        } else {
            inputHint.textContent = 'Supports youtube.com, youtu.be, shorts, and live links';
            inputHint.style.color = '';
        }
    }

    // ── Toast System ──
    function toast(message, type, duration) {
        type = type || 'info';
        duration = duration || 4000;
        var icons = {
            success: 'fas fa-check-circle',
            error: 'fas fa-exclamation-circle',
            warning: 'fas fa-exclamation-triangle',
            info: 'fas fa-info-circle'
        };
        var el = document.createElement('div');
        el.className = 'toast toast-' + type;
        el.innerHTML = '<i class="toast-icon ' + (icons[type] || icons.info) + '"></i><span>' + message + '</span>';
        toastContainer.appendChild(el);
        setTimeout(function() {
            el.classList.add('removing');
            setTimeout(function() { el.remove(); }, 300);
        }, duration);
    }

    // ── Format Helpers ──
    var MP3_FORMATS = [
        { quality: '192k', note: 'Standard Quality' },
        { quality: '320k', note: 'High Quality' }
    ];
    var MP4_FORMATS = [
        { quality: '360p', note: 'Standard Definition' },
        { quality: '720p', note: 'HD' },
        { quality: '1080p', note: 'Full HD' }
    ];

    function populateQualityOptions() {
        var fmt = formatSelect.value;
        var opts = fmt === 'mp3' ? MP3_FORMATS : MP4_FORMATS;
        qualitySelect.innerHTML = '';
        for (var i = 0; i < opts.length; i++) {
            var option = document.createElement('option');
            option.value = opts[i].quality;
            option.textContent = opts[i].quality + ' — ' + opts[i].note;
            qualitySelect.appendChild(option);
        }
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
            var pct = Math.min(Math.round((received / total) * 100), 100);
            downloadBar.style.width = pct + '%';
            downloadPct.textContent = pct + '%';
            var receivedMB = (received / (1024 * 1024)).toFixed(1);
            var totalMB = (total / (1024 * 1024)).toFixed(1);
            downloadStatus.textContent = receivedMB + ' MB / ' + totalMB + ' MB';
        } else {
            var mb = (received / (1024 * 1024)).toFixed(1);
            downloadBar.classList.add('indeterminate');
            downloadStatus.textContent = mb + ' MB downloaded';
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

    // Helper to restore analyze button
    function resetAnalyzeBtn() {
        fetchInfoBtn.disabled = false;
        fetchInfoBtn.innerHTML = '<i class="fas fa-search"></i> <span>Analyze</span>';
    }

    // ── Fetch Video Info (SSE real-time progress) ──
    function getInfo(url) {
        // Immediately show the user something is happening
        fetchInfoBtn.disabled = true;
        fetchInfoBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> <span>Analyzing...</span>';
        showProcessing('Connecting to server...');
        previewSection.classList.add('hidden');

        var sseUrl = API_BASE + '/api/info-stream?url=' + encodeURIComponent(url);

        // Try SSE first for real-time progress
        if (typeof EventSource !== 'undefined') {
            var source = new EventSource(sseUrl);
            var completed = false;

            source.addEventListener('progress', function(e) {
                try {
                    var data = JSON.parse(e.data);
                    updateProcessing(data.pct, data.msg);
                } catch (err) {
                    // ignore parse errors
                }
            });

            source.addEventListener('complete', function(e) {
                completed = true;
                source.close();
                try {
                    var info = JSON.parse(e.data);
                    currentVideoInfo = info;
                    completeProcessing();

                    videoThumbnail.src = info.thumbnail;
                    videoDuration.textContent = info.duration_formatted;
                    videoTitle.textContent = info.title;

                    videoChannel.textContent = '';
                    var icon = document.createElement('i');
                    icon.className = 'fas fa-user-circle';
                    videoChannel.appendChild(icon);
                    videoChannel.appendChild(document.createTextNode(' ' + info.channel));

                    populateQualityOptions();

                    setTimeout(function() {
                        previewSection.classList.remove('hidden');
                        hideAllProgress();
                        resetAnalyzeBtn();
                    }, 600);

                    toast('Video analyzed successfully!', 'success');
                } catch (err) {
                    hideAllProgress();
                    resetAnalyzeBtn();
                    toast('Failed to parse video info', 'error', 6000);
                }
            });

            source.addEventListener('error_event', function(e) {
                completed = true;
                source.close();
                try {
                    var data = JSON.parse(e.data);
                    hideAllProgress();
                    resetAnalyzeBtn();
                    toast(data.detail || 'Analysis failed', 'error', 6000);
                } catch (err) {
                    hideAllProgress();
                    resetAnalyzeBtn();
                    toast('Analysis failed', 'error', 6000);
                }
            });

            source.onerror = function() {
                if (!completed) {
                    source.close();
                    // Fallback to regular fetch if SSE fails
                    console.log('[water2wine] SSE failed, falling back to fetch');
                    getInfoFallback(url);
                }
            };
        } else {
            // No EventSource support — use fetch fallback
            getInfoFallback(url);
        }
    }

    // Fallback: regular fetch (no real-time progress)
    function getInfoFallback(url) {
        showProcessing('Analyzing video...');

        var phases = [
            { delay: 2000, pct: 20, msg: 'Contacting YouTube...' },
            { delay: 5000, pct: 45, msg: 'Extracting metadata...' },
            { delay: 9000, pct: 65, msg: 'Resolving formats...' },
            { delay: 14000, pct: 80, msg: 'Almost there...' }
        ];
        var timers = phases.map(function(p) {
            return setTimeout(function() { updateProcessing(p.pct, p.msg); }, p.delay);
        });

        fetch(API_BASE + '/api/info?url=' + encodeURIComponent(url))
            .then(function(response) {
                timers.forEach(clearTimeout);
                if (!response.ok) {
                    return response.json().then(function(err) {
                        throw new Error(err.detail || 'Failed to fetch video info');
                    });
                }
                return response.json();
            })
            .then(function(info) {
                currentVideoInfo = info;
                updateProcessing(100, 'Analysis complete!');
                setTimeout(completeProcessing, 200);

                videoThumbnail.src = info.thumbnail;
                videoDuration.textContent = info.duration_formatted;
                videoTitle.textContent = info.title;

                videoChannel.textContent = '';
                var icon = document.createElement('i');
                icon.className = 'fas fa-user-circle';
                videoChannel.appendChild(icon);
                videoChannel.appendChild(document.createTextNode(' ' + info.channel));

                populateQualityOptions();

                setTimeout(function() {
                    previewSection.classList.remove('hidden');
                    hideAllProgress();
                    resetAnalyzeBtn();
                }, 600);

                toast('Video analyzed successfully!', 'success');
            })
            .catch(function(error) {
                timers.forEach(clearTimeout);
                hideAllProgress();
                resetAnalyzeBtn();
                toast(error.message, 'error', 6000);
            });
    }

    // ── Browser Detection ──
    var ua = navigator.userAgent || '';
    var isIOS = /iPad|iPhone|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    var isSafari = /^((?!chrome|android).)*safari/i.test(ua);
    var isFirefox = /firefox/i.test(ua);
    var isMobile = isIOS || /Android/i.test(ua);

    // ── Download ──
    function startDownload(url, format, quality) {
        lastDownloadParams = { url: url, format: format, quality: quality };
        retryBtn.classList.add('hidden');

        var title = videoTitle.textContent || 'video';
        var duration = currentVideoInfo ? currentVideoInfo.duration : 0;
        var ext = format === 'mp3' ? 'mp3' : 'mp4';
        var safeTitle = title.replace(/[^\w\s.-]/g, '').trim().slice(0, 80) || 'download';
        var filename = safeTitle + '.' + ext;
        var downloadUrl = API_BASE + '/api/download?url=' + encodeURIComponent(url) +
            '&format=' + format + '&quality=' + quality +
            '&title=' + encodeURIComponent(title) + '&duration=' + duration;

        // Show processing indicator
        showProcessing('Sending request to server...');
        downloadBtn.disabled = true;

        var phases = [
            { delay: 2000, pct: 15, msg: 'Server is extracting streams...' },
            { delay: 5000, pct: 30, msg: 'Resolving media sources...' },
            { delay: 10000, pct: 50, msg: 'Converting with ffmpeg...' },
            { delay: 20000, pct: 70, msg: 'Processing... this may take a moment' },
            { delay: 35000, pct: 85, msg: 'Still working... hang tight!' }
        ];
        var timers = phases.map(function(p) {
            return setTimeout(function() { updateProcessing(p.pct, p.msg); }, p.delay);
        });

        // Use window.location.href — the server sets Content-Disposition: attachment
        // so the browser will download the file without navigating away
        window.location.href = downloadUrl;

        // Show success feedback after a short delay
        setTimeout(function() {
            timers.forEach(clearTimeout);
            completeProcessing();
            updateProcessing(100, 'Download started!');
        }, 3000);

        setTimeout(function() {
            hideAllProgress();
            downloadBtn.disabled = false;
            toast(format.toUpperCase() + ' download started! Check your browser downloads bar.', 'success');
        }, 4500);
    }

    // ── Event Listeners ──
    videoUrlInput.addEventListener('input', validateUrl);
    videoUrlInput.addEventListener('change', validateUrl);
    videoUrlInput.addEventListener('paste', function() {
        setTimeout(validateUrl, 0);
    });
    videoUrlInput.addEventListener('keyup', validateUrl);

    videoUrlInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !fetchInfoBtn.disabled) {
            fetchInfoBtn.click();
        }
    });

    fetchInfoBtn.addEventListener('click', function() {
        var url = videoUrlInput.value.trim();
        if (isYouTubeUrl(url)) getInfo(url);
    });

    formatSelect.addEventListener('change', populateQualityOptions);

    downloadBtn.addEventListener('click', function() {
        var url = videoUrlInput.value.trim();
        var format = formatSelect.value;
        var quality = qualitySelect.value;
        startDownload(url, format, quality);
    });

    retryBtn.addEventListener('click', function() {
        if (lastDownloadParams) {
            startDownload(lastDownloadParams.url, lastDownloadParams.format, lastDownloadParams.quality);
        }
    });

    // Init
    validateUrl();
    populateQualityOptions();
});
