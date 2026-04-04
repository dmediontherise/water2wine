/**
 * water2wine - Frontend Logic
 * Handles YouTube URL validation, video info fetching, and download triggering.
 */

document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const videoUrlInput = document.getElementById('video-url');
    const fetchInfoBtn = document.getElementById('fetch-info-btn');
    const previewSection = document.getElementById('preview-section');
    const videoThumbnail = document.getElementById('video-thumbnail');
    const videoDuration = document.getElementById('video-duration');
    const videoTitle = document.getElementById('video-title');
    const videoChannel = document.getElementById('video-channel');
    const formatSelect = document.getElementById('format-select');
    const qualitySelect = document.getElementById('quality-select');
    const downloadBtn = document.getElementById('download-btn');
    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.getElementById('progress-bar');
    const progressStatus = document.getElementById('progress-status');

    // Constants
    const YOUTUBE_REGEX = /^(https?:\/\/)?(www\.)?(youtube\.com\/(watch\?v=|shorts\/|live\/)|youtu\.be\/)[\w-]+/;
    const API_BASE = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
        ? 'http://localhost:8000'
        : 'https://water2wine.onrender.com';
    const INFO_TIMEOUT_MS = 5000;

    /**
     * Validates the YouTube URL and enables/disables the analyze button.
     */
    const validateUrl = () => {
        const url = videoUrlInput.value.trim();
        fetchInfoBtn.disabled = !YOUTUBE_REGEX.test(url);
    };

    /**
     * Shows the indeterminate progress bar with a specific status message.
     * @param {string} message - The status message to display.
     */
    const showLoading = (message) => {
        progressStatus.textContent = message;
        progressContainer.classList.remove('hidden');
        progressBar.classList.add('indeterminate');
    };

    /**
     * Hides the progress bar.
     */
    const hideLoading = () => {
        progressContainer.classList.add('hidden');
        progressBar.classList.remove('indeterminate');
    };

    /**
     * Fetches video information from the backend.
     * @param {string} url - The YouTube video URL.
     */
    const getInfo = async (url) => {
        showLoading('Analyzing video...');
        previewSection.classList.add('hidden');

        let timeoutReached = false;
        const timeoutId = setTimeout(() => {
            timeoutReached = true;
            progressStatus.textContent = 'Still analyzing... this might take a moment.';
        }, INFO_TIMEOUT_MS);

        try {
            const response = await fetch(`${API_BASE}/api/info?url=${encodeURIComponent(url)}`);
            clearTimeout(timeoutId);

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to fetch video info');
            }

            const info = await response.json();
            
            // Update UI with video info
            videoThumbnail.src = info.thumbnail;
            videoDuration.textContent = info.duration_formatted;
            videoTitle.textContent = info.title;
            
            // Fix XSS: Use textContent for channel name
            videoChannel.textContent = '';
            const channelIcon = document.createElement('i');
            channelIcon.className = 'fas fa-user';
            videoChannel.appendChild(channelIcon);
            videoChannel.appendChild(document.createTextNode(` ${info.channel}`));
            
            // Logic Mismatch: Dynamically populate quality-select
            qualitySelect.innerHTML = '';
            info.formats.forEach(fmt => {
                const option = document.createElement('option');
                option.value = fmt.quality;
                option.textContent = `${fmt.quality} (${fmt.ext}) - ${fmt.note}`;
                qualitySelect.appendChild(option);
            });
            
            previewSection.classList.remove('hidden');
            hideLoading();
        } catch (error) {
            clearTimeout(timeoutId);
            hideLoading();
            alert(`Error: ${error.message}`);
        }
    };

    /**
     * Triggers the video download process.
     * @param {string} url - The YouTube video URL.
     * @param {string} format - The desired format (mp3/mp4).
     * @param {string} quality - The desired quality.
     */
    const download = (url, format, quality) => {
        showLoading(`Preparing ${format.toUpperCase()} download...`);
        downloadBtn.disabled = true;

        try {
            const title = videoTitle.textContent || "video";
            const downloadUrl = `${API_BASE}/api/download?url=${encodeURIComponent(url)}&format=${format}&quality=${quality}&title=${encodeURIComponent(title)}`;
            
            // We can't easily track progress with window.location.href, 
            // but it's safer for large files.
            window.location.href = downloadUrl;
            
            // Hide loading after a short delay since we can't know when it starts
            setTimeout(() => {
                hideLoading();
                downloadBtn.disabled = false;
            }, 2000);
        } catch (error) {
            hideLoading();
            alert(`Download Error: ${error.message}`);
            downloadBtn.disabled = false;
        }
    };

    // Event Listeners
    videoUrlInput.addEventListener('input', validateUrl);

    fetchInfoBtn.addEventListener('click', () => {
        const url = videoUrlInput.value.trim();
        if (YOUTUBE_REGEX.test(url)) {
            getInfo(url);
        }
    });

    downloadBtn.addEventListener('click', () => {
        const url = videoUrlInput.value.trim();
        const format = formatSelect.value;
        const quality = qualitySelect.value;
        download(url, format, quality);
    });

    // Initial validation
    validateUrl();
});
