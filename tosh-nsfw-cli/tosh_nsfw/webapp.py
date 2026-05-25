"""
Web-based NSFW photo review interface.
Fast loading with skeleton UI and image prefetch.
"""

import json
import logging
import webbrowser
from pathlib import Path
from threading import Timer

from flask import Flask, jsonify, render_template_string, send_file, request

from .tagger import get_tagged_photos, mark_lockboxed
from .scanner import get_thumbnail_path, generate_thumbnail, delete_thumbnail, THUMBNAIL_CACHE
from .reviewer import mark_reviewed, local_lockbox_photo, delete_from_ios
from .utils.photos import get_photo_by_uuid

logger = logging.getLogger(__name__)

app = Flask(__name__)

# HTML template with skeleton loading
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Photo Library Maintenance</title>
    <style>
        /* Boss key decoy screen */
        .decoy {
            position: fixed;
            inset: 0;
            background: #f5f5f5;
            z-index: 1000;
            display: flex;
            flex-direction: column;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            color: #333;
        }

        .decoy-header {
            background: #fff;
            padding: 1rem 2rem;
            border-bottom: 1px solid #ddd;
            display: flex;
            align-items: center;
            gap: 1rem;
        }

        .decoy-header h1 {
            font-size: 1.2rem;
            font-weight: 500;
            color: #666;
        }

        .decoy-icon {
            width: 32px;
            height: 32px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 6px;
        }

        .decoy-content {
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-direction: column;
            gap: 1rem;
            color: #888;
        }

        .decoy-spinner {
            width: 40px;
            height: 40px;
            border: 3px solid #ddd;
            border-top-color: #667eea;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .decoy-footer {
            padding: 1rem;
            text-align: center;
            color: #aaa;
            font-size: 0.8rem;
        }

        /* Hidden unlock button - bottom right corner, subtle */
        .unlock-btn {
            position: fixed;
            bottom: 8px;
            right: 8px;
            width: 40px;
            height: 40px;
            background: transparent;
            border: 1px solid rgba(102, 126, 234, 0.1);
            border-radius: 4px;
            cursor: pointer;
            z-index: 1001;
            opacity: 0.3;
            transition: opacity 0.2s;
        }

        .unlock-btn:hover {
            opacity: 0.6;
            background: rgba(102, 126, 234, 0.1);
        }

        .decoy.hidden { display: none; }

        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }

        .header {
            padding: 1rem 2rem;
            background: #16213e;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #0f3460;
        }

        .progress {
            font-size: 1.2rem;
            font-weight: 600;
        }

        .score {
            font-size: 2rem;
            font-weight: 700;
            color: #e94560;
        }

        .score.safe { color: #4ade80; }
        .score.borderline { color: #fbbf24; }
        .score.suggestive { color: #f97316; }
        .score.nsfw { color: #e94560; }

        .container {
            flex: 1;
            display: flex;
            overflow: hidden;
        }

        .main {
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 2rem;
            gap: 1.5rem;
        }

        .sidebar {
            width: 280px;
            background: #16213e;
            border-left: 1px solid #0f3460;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        .sidebar-header {
            padding: 1rem;
            border-bottom: 1px solid #0f3460;
            font-weight: 600;
            display: flex;
            justify-content: space-between;
        }

        .sidebar-list {
            flex: 1;
            overflow-y: auto;
            padding: 0.5rem;
        }

        .sidebar-item {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.5rem;
            border-radius: 6px;
            margin-bottom: 0.25rem;
            font-size: 0.85rem;
        }

        .sidebar-item.approve { background: rgba(34, 197, 94, 0.2); }
        .sidebar-item.remove { background: rgba(239, 68, 68, 0.2); }
        .sidebar-item.lockbox { background: rgba(139, 92, 246, 0.2); }
        .sidebar-item.skip { background: rgba(107, 114, 128, 0.2); }

        .sidebar-item .icon { font-size: 1rem; }
        .sidebar-item .name {
            flex: 1;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            color: #ccc;
        }

        .sidebar-item .status {
            font-size: 0.7rem;
            padding: 0.15rem 0.4rem;
            border-radius: 3px;
            background: rgba(0,0,0,0.3);
        }

        .image-container {
            position: relative;
            width: 100%;
            max-width: 800px;
            aspect-ratio: 4/3;
            background: #16213e;
            border-radius: 12px;
            overflow: hidden;
        }

        .skeleton {
            position: absolute;
            inset: 0;
            background: linear-gradient(90deg, #16213e 25%, #1a2744 50%, #16213e 75%);
            background-size: 200% 100%;
            animation: shimmer 1.5s infinite;
        }

        @keyframes shimmer {
            0% { background-position: 200% 0; }
            100% { background-position: -200% 0; }
        }

        .image-container img {
            position: absolute;
            inset: 0;
            width: 100%;
            height: 100%;
            object-fit: contain;
            opacity: 0;
            transition: opacity 0.3s ease;
        }

        .image-container img.loaded {
            opacity: 1;
        }

        .info {
            text-align: center;
            color: #888;
            font-size: 0.9rem;
        }

        .info .filename {
            color: #ccc;
            font-size: 1rem;
            margin-bottom: 0.25rem;
        }

        .buttons {
            display: flex;
            gap: 1rem;
            flex-wrap: wrap;
            justify-content: center;
        }

        button {
            padding: 1rem 2rem;
            font-size: 1.1rem;
            font-weight: 600;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            transition: transform 0.1s, box-shadow 0.2s;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }

        button:active {
            transform: translateY(0);
        }

        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }

        .btn-approve { background: #22c55e; color: white; }
        .btn-remove { background: #ef4444; color: white; }
        .btn-lockbox { background: #8b5cf6; color: white; }
        .btn-skip { background: #6b7280; color: white; }

        .kbd {
            background: rgba(0,0,0,0.2);
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            font-size: 0.8rem;
            margin-left: 0.5rem;
        }

        .complete {
            text-align: center;
            padding: 4rem;
        }

        .complete h1 {
            font-size: 2.5rem;
            margin-bottom: 1rem;
            color: #4ade80;
        }

        .complete .stats {
            font-size: 1.2rem;
            line-height: 2;
        }

        .toast {
            position: fixed;
            bottom: 2rem;
            left: 50%;
            transform: translateX(-50%) translateY(100px);
            background: #16213e;
            padding: 1rem 2rem;
            border-radius: 8px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.4);
            opacity: 0;
            transition: all 0.3s ease;
        }

        .toast.show {
            transform: translateX(-50%) translateY(0);
            opacity: 1;
        }

        /* Prefetch hidden image */
        .prefetch {
            position: absolute;
            width: 1px;
            height: 1px;
            opacity: 0;
            pointer-events: none;
        }
    </style>
</head>
<body>
    <!-- Decoy/Boss Key Screen -->
    <div class="decoy" id="decoy">
        <div class="decoy-header">
            <div class="decoy-icon"></div>
            <h1>Photo Library Maintenance</h1>
        </div>
        <div class="decoy-content">
            <div class="decoy-spinner"></div>
            <p>Analyzing photo library metadata...</p>
            <p style="font-size: 0.85rem;">This may take several minutes</p>
        </div>
        <div class="decoy-footer">
            macOS Photo Library Tools v2.1.4
        </div>
    </div>

    <!-- Tiny unlock button (hover bottom-right corner) -->
    <button class="unlock-btn" id="unlock-btn" title=" "></button>

    <div class="header">
        <div class="progress" id="progress">Loading...</div>
        <div class="score" id="score"></div>
    </div>

    <div class="container">
        <div class="main" id="main">
            <div class="image-container">
                <div class="skeleton" id="skeleton"></div>
                <img id="photo" alt="Photo for review">
            </div>

            <div class="info">
                <div class="filename" id="filename"></div>
                <div id="uuid"></div>
            </div>

            <div class="buttons">
                <button class="btn-approve" onclick="action('approve')" id="btn-approve">
                    👍 Keep <span class="kbd">K</span>
                </button>
                <button class="btn-remove" onclick="action('remove')" id="btn-remove">
                    👎 Remove <span class="kbd">R</span>
                </button>
                <button class="btn-lockbox" onclick="action('lockbox')" id="btn-lockbox">
                    📦 Lockbox <span class="kbd">L</span>
                </button>
                <button class="btn-skip" onclick="action('skip')" id="btn-skip">
                    Skip <span class="kbd">S</span>
                </button>
            </div>
        </div>

        <div class="sidebar">
            <div class="sidebar-header">
                <span>Decisions</span>
                <span id="sidebar-count">0</span>
            </div>
            <div class="sidebar-list" id="sidebar-list"></div>
        </div>
    </div>

    <div class="toast" id="toast"></div>

    <!-- Hidden prefetch image -->
    <img class="prefetch" id="prefetch" alt="">

    <script>
        console.log('BOOT: script starting v20260119');
        let photos = [];
        let currentIndex = 0;
        let stats = { approved: 0, removed: 0, lockboxed: 0, skipped: 0 };

        async function loadPhotos() {
            console.log('loadPhotos called');
            try {
                const res = await fetch('/api/photos');
                photos = await res.json();
                console.log('Loaded photos:', photos.length);

                if (photos.length === 0) {
                    showComplete();
                } else {
                    showPhoto(0);
                }
            } catch (err) {
                console.error('loadPhotos error:', err);
            }
        }

        function showPhoto(index) {
            if (index >= photos.length) {
                showComplete();
                return;
            }

            currentIndex = index;
            const photo = photos[index];

            // Update UI
            document.getElementById('progress').textContent =
                `Photo ${index + 1} of ${photos.length}`;

            const scoreEl = document.getElementById('score');
            const score = Math.round(photo.nsfw_score * 100);
            scoreEl.textContent = score + '%';
            scoreEl.className = 'score ' + (photo.classification || 'nsfw');

            document.getElementById('filename').textContent = photo.filename || 'Unknown';
            document.getElementById('uuid').textContent = photo.uuid;

            // Show skeleton, hide image
            document.getElementById('skeleton').style.display = 'block';
            const img = document.getElementById('photo');
            img.classList.remove('loaded');

            // Load image
            img.onload = () => {
                document.getElementById('skeleton').style.display = 'none';
                img.classList.add('loaded');
            };
            img.src = '/thumbnail/' + photo.uuid;

            // Prefetch next image
            if (index + 1 < photos.length) {
                document.getElementById('prefetch').src =
                    '/thumbnail/' + photos[index + 1].uuid;
            }

            enableButtons(true);
        }

        function enableButtons(enabled) {
            document.querySelectorAll('button').forEach(b => b.disabled = !enabled);
        }

        let decisions = [];

        async function action(type) {
            enableButtons(false);
            const photo = photos[currentIndex];

            try {
                const res = await fetch('/api/action/' + photo.uuid, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: type })
                });

                const result = await res.json();

                if (result.success) {
                    stats[type]++;
                    addToSidebar(photo, type);
                    showPhoto(currentIndex + 1);
                } else {
                    showToast('Error: ' + result.error, true);
                    enableButtons(true);
                }
            } catch (e) {
                showToast('Network error', true);
                enableButtons(true);
            }
        }

        function addToSidebar(photo, type) {
            decisions.push({ photo, type });

            const icons = { approve: '👍', remove: '👎', lockbox: '📦', skip: '⏭️' };
            const list = document.getElementById('sidebar-list');

            const item = document.createElement('div');
            item.className = 'sidebar-item ' + type;
            item.innerHTML = `
                <span class="icon">${icons[type]}</span>
                <span class="name">${photo.filename || photo.uuid.slice(0,8)}</span>
                <span class="status">${Math.round(photo.nsfw_score * 100)}%</span>
            `;

            list.insertBefore(item, list.firstChild);
            document.getElementById('sidebar-count').textContent = decisions.length;
        }

        function getActionMessage(type) {
            switch(type) {
                case 'approve': return '👍 Kept';
                case 'remove': return '👎 Removed from iOS';
                case 'lockbox': return '📦 Moved to lockbox';
                case 'skip': return '⏭️ Skipped';
            }
        }

        function showToast(message, isError = false) {
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.style.background = isError ? '#ef4444' : '#16213e';
            toast.classList.add('show');
            setTimeout(() => toast.classList.remove('show'), 2000);
        }

        async function showComplete() {
            document.getElementById('main').innerHTML = `
                <div class="complete">
                    <h1>⏳ Processing...</h1>
                    <div class="stats" id="live-stats">
                        Waiting for background tasks to complete...
                    </div>
                    <div id="failed-section" style="display:none; margin-top:2rem; padding:1rem; background:#2d1f1f; border-radius:8px; max-width:500px;">
                        <h3 style="color:#ef4444; margin-bottom:0.5rem;">⚠️ Failed Deletions</h3>
                        <p style="font-size:0.9rem; color:#888; margin-bottom:1rem;">
                            These photos couldn't be deleted automatically. Open Photos app and search for these UUIDs to delete manually.
                        </p>
                        <div id="failed-list" style="font-family:monospace; font-size:0.8rem; background:#1a1a1a; padding:0.5rem; border-radius:4px; max-height:150px; overflow-y:auto;"></div>
                        <button onclick="copyFailed()" style="margin-top:0.5rem; padding:0.5rem 1rem; font-size:0.9rem;">📋 Copy UUIDs</button>
                    </div>
                </div>
            `;
            document.getElementById('progress').textContent = 'Processing';
            document.getElementById('score').textContent = '';

            // Poll for completion
            while (true) {
                const res = await fetch('/api/stats');
                const s = await res.json();

                document.getElementById('live-stats').innerHTML = `
                    👍 Approved: ${s.approved}<br>
                    👎 Removed: ${s.removed}<br>
                    📦 Lockboxed: ${s.lockboxed}<br>
                    ⏭️ Skipped: ${s.skipped}<br>
                    ${s.errors.length > 0 ? `❌ Failed: ${s.errors.length}<br>` : ''}
                    <br>
                    ${s.pending > 0 ? `⏳ ${s.pending} remaining...` : ''}
                `;

                // Show failed section if there are errors
                if (s.errors.length > 0) {
                    document.getElementById('failed-section').style.display = 'block';
                    failedUUIDs = [];  // Reset for fresh list
                    document.getElementById('failed-list').innerHTML = s.errors.map(e => {
                        // New format: {uuid, date, album} object
                        // Old format: string
                        let uuid, date, album;
                        if (typeof e === 'object' && e.uuid) {
                            uuid = e.uuid;
                            date = e.date || '';
                            album = e.album || '';
                        } else {
                            // Legacy string format
                            uuid = String(e).replace('Failed to remove ', '').trim();
                            date = '';
                            album = '';
                        }
                        failedUUIDs.push(uuid);  // Track for copy button
                        // Build metadata line - hide if no info
                        let metaHtml = '';
                        if (date || album) {
                            metaHtml = '<div style="color:#888; font-size:0.8rem; margin-top:0.25rem;">';
                            if (date) metaHtml += `📅 ${date}`;
                            if (date && album) metaHtml += ' &nbsp;';
                            if (album) metaHtml += `📁 ${album}`;
                            metaHtml += '</div>';
                        }
                        return `<div style="margin-bottom:0.5rem; padding:0.5rem; background:#222; border-radius:4px;">
                            <div style="color:#ef4444; font-family:monospace;">${uuid}</div>
                            ${metaHtml}
                        </div>`;
                    }).join('');
                }

                if (s.pending === 0 && !s.processing) {
                    document.querySelector('.complete h1').textContent = '✅ Review Complete!';
                    document.getElementById('progress').textContent = 'Complete';
                    break;
                }

                await new Promise(r => setTimeout(r, 500));
            }
        }

        let failedUUIDs = [];

        function copyFailed() {
            navigator.clipboard.writeText(failedUUIDs.join('\\n'));
            showToast('UUIDs copied to clipboard');
        }

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.target.tagName === 'INPUT') return;
            switch(e.key.toLowerCase()) {
                case 'k': action('approve'); break;
                case 'r': action('remove'); break;
                case 'l': action('lockbox'); break;
                case 's': case 'arrowright': action('skip'); break;
            }
        });

        // Boss key / unlock
        let unlocked = false;
        let sessionId = null;
        try {
            sessionId = localStorage.getItem('nsfw_session_id');
        } catch (e) {
            console.warn('localStorage unavailable:', e);
        }
        console.log('BOOT: script loaded, sessionId=', sessionId);

        async function initSession() {
            const res = await fetch('/api/session', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId })
            });
            const data = await res.json();

            sessionId = data.session_id;
            localStorage.setItem('nsfw_session_id', sessionId);

            if (data.resumed && data.stats) {
                // Restore stats from previous session
                stats = {
                    approved: data.stats.approved || 0,
                    removed: data.stats.removed || 0,
                    lockboxed: data.stats.lockboxed || 0,
                    skipped: data.stats.skipped || 0
                };
                console.log('Resumed session:', sessionId, stats);
            }

            loadPhotos();
        }

        document.getElementById('unlock-btn').addEventListener('click', () => {
            console.log('Unlock clicked, unlocked=', unlocked);
            if (!unlocked) {
                console.log('Hiding decoy and starting session...');
                document.getElementById('decoy').classList.add('hidden');
                unlocked = true;
                initSession().catch(err => console.error('initSession error:', err));
            }
        });

        // Double-tap Escape to re-lock (boss key)
        let escapeCount = 0;
        let escapeTimer = null;
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && unlocked) {
                escapeCount++;
                if (escapeCount === 2) {
                    // Re-lock: show decoy and clear sidebar
                    document.getElementById('decoy').classList.remove('hidden');
                    document.getElementById('sidebar-list').innerHTML = '';
                    document.getElementById('sidebar-count').textContent = '0';
                    decisions = [];
                    unlocked = false;
                    escapeCount = 0;
                }
                clearTimeout(escapeTimer);
                escapeTimer = setTimeout(() => escapeCount = 0, 500);
            }
        });

        // Auto-unlock on load for now (bypass decoy)
        document.getElementById('decoy').classList.add('hidden');
        unlocked = true;
        initSession();
    </script>
</body>
</html>
'''


@app.route('/')
def index():
    """Serve the review UI."""
    response = app.make_response(render_template_string(HTML_TEMPLATE))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/api/photos')
def api_photos():
    """Get list of photos pending review from scan_log."""
    from .utils.db import get_cursor

    pending = []
    try:
        with get_cursor() as cur:
            # Get flagged, unreviewed photos from scan_log
            cur.execute("""
                SELECT uuid, filename, max_score, classification
                FROM bronze.nsfw_scan_log
                WHERE flagged = TRUE AND review_action IS NULL
                ORDER BY max_score DESC
            """)
            rows = cur.fetchall()

            for row in rows:
                uuid, filename, score, classification = row

                # Ensure thumbnail exists
                photo_info = get_photo_by_uuid(uuid)
                if photo_info and photo_info.path:
                    thumb = get_thumbnail_path(uuid)
                    if not thumb:
                        generate_thumbnail(uuid, photo_info.path)

                pending.append({
                    'uuid': uuid,
                    'filename': filename,
                    'nsfw_score': score,
                    'classification': classification or _classify_score(score),
                })
    except Exception as e:
        logger.error(f"Failed to get pending photos: {e}")

    return jsonify(pending)


def _classify_score(score: float) -> str:
    """Classify score into category."""
    if score > 0.7:
        return 'nsfw'
    elif score > 0.4:
        return 'suggestive'
    elif score > 0.2:
        return 'borderline'
    return 'safe'


@app.route('/thumbnail/<uuid>')
def serve_thumbnail(uuid: str):
    """Serve a cached thumbnail."""
    thumb_path = get_thumbnail_path(uuid)

    if thumb_path and thumb_path.exists():
        return send_file(thumb_path, mimetype='image/jpeg')

    # Try to generate on the fly
    photo_info = get_photo_by_uuid(uuid)
    if photo_info and photo_info.path:
        thumb_path = generate_thumbnail(uuid, photo_info.path)
        if thumb_path:
            return send_file(thumb_path, mimetype='image/jpeg')

    # Return placeholder
    return jsonify({'error': 'Thumbnail not found'}), 404


# Background processing
from queue import Queue
from threading import Thread
from datetime import datetime
import time
import uuid as uuid_lib

from .utils.db import get_cursor, DatabaseError

action_queue = Queue()
processing_stats = {'approved': 0, 'removed': 0, 'lockboxed': 0, 'skipped': 0, 'errors': [], 'processing': False}
current_session_id = None

# Decision log file
DECISION_LOG = Path.home() / ".tosh" / "nsfw_decisions.log"


# --- Session Management ---

def create_session() -> str:
    """Create a new review session in database."""
    global current_session_id, processing_stats
    session_id = str(uuid_lib.uuid4())[:8]

    try:
        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO bronze.nsfw_review_sessions (session_id)
                VALUES (%s)
            """, (session_id,))
        current_session_id = session_id
        # Reset in-memory stats
        processing_stats = {'approved': 0, 'removed': 0, 'lockboxed': 0, 'skipped': 0, 'errors': [], 'processing': False}
        logger.info(f"Created session: {session_id}")
    except DatabaseError as e:
        logger.error(f"Failed to create session: {e}")

    return session_id


def load_session(session_id: str) -> dict | None:
    """Load session stats from database."""
    global current_session_id, processing_stats

    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT approved, removed, lockboxed, skipped, errors
                FROM bronze.nsfw_review_sessions
                WHERE session_id = %s AND ended_at IS NULL
            """, (session_id,))
            row = cur.fetchone()
            if row:
                current_session_id = session_id
                processing_stats = {
                    'approved': row[0] or 0,
                    'removed': row[1] or 0,
                    'lockboxed': row[2] or 0,
                    'skipped': row[3] or 0,
                    'errors': row[4] or [],
                    'processing': False
                }
                logger.info(f"Loaded session: {session_id}")
                return processing_stats
    except DatabaseError as e:
        logger.error(f"Failed to load session: {e}")
    return None


def save_session_stats():
    """Save current stats to database."""
    if not current_session_id:
        return

    try:
        with get_cursor() as cur:
            cur.execute("""
                UPDATE bronze.nsfw_review_sessions
                SET approved = %s, removed = %s, lockboxed = %s, skipped = %s, errors = %s
                WHERE session_id = %s
            """, (
                processing_stats['approved'],
                processing_stats['removed'],
                processing_stats['lockboxed'],
                processing_stats['skipped'],
                json.dumps(processing_stats['errors']),
                current_session_id
            ))
    except DatabaseError as e:
        logger.error(f"Failed to save session: {e}")


def get_photo_metadata(uuid: str) -> tuple[str, str]:
    """Get helpful metadata for finding photo in Photos app.

    Returns (date_str, album_str) tuple.
    """
    try:
        import osxphotos
        db = osxphotos.PhotosDB()
        photos = db.photos(uuid=[uuid])
        if photos:
            p = photos[0]
            date_str = p.date.strftime("%Y-%m-%d") if p.date else ""
            albums = [a.title for a in p.album_info] if p.album_info else []
            album_str = albums[0] if albums else ""
            return (date_str, album_str)
    except Exception as e:
        logger.warning(f"Could not get metadata for {uuid}: {e}")
    return ("", "")


def log_decision(uuid: str, action: str, success: bool, details: str = ""):
    """Append decision to persistent log file."""
    DECISION_LOG.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "✅" if success else "❌"
    line = f"{timestamp} | {status} {action.upper():10} | {uuid[:12]} | {details}\n"
    with open(DECISION_LOG, "a") as f:
        f.write(line)


def background_processor():
    """Process actions in background thread."""
    while True:
        item = action_queue.get()
        if item is None:
            break

        uuid, action = item
        processing_stats['processing'] = True

        try:
            if action == 'approve':
                mark_reviewed(uuid, 'approved')
                delete_thumbnail(uuid)
                processing_stats['approved'] += 1
                log_decision(uuid, 'approve', True, 'marked as safe')
                logger.info(f"✅ APPROVED {uuid[:8]}")

            elif action == 'remove':
                if delete_from_ios(uuid):
                    processing_stats['removed'] += 1
                    log_decision(uuid, 'remove', True, 'deleted from iOS')
                    logger.info(f"✅ REMOVED {uuid[:8]} from iOS")
                else:
                    # Get extra info for manual deletion
                    date_str, album_str = get_photo_metadata(uuid)
                    error_obj = {'uuid': uuid, 'date': date_str, 'album': album_str}
                    processing_stats['errors'].append(error_obj)
                    log_decision(uuid, 'remove', False, f'deletion failed - {date_str} {album_str}')
                    logger.error(f"❌ FAILED to remove {uuid[:8]} from iOS")

            elif action == 'lockbox':
                photo_info = get_photo_by_uuid(uuid)
                if photo_info and photo_info.path:
                    if local_lockbox_photo(uuid, photo_info.path):
                        processing_stats['lockboxed'] += 1
                        log_decision(uuid, 'lockbox', True, f'moved to ~/.tosh/nsfw_lockbox/')
                        logger.info(f"✅ LOCKBOXED {uuid[:8]} -> ~/.tosh/nsfw_lockbox/")
                    else:
                        processing_stats['errors'].append(f"Failed to lockbox {uuid[:8]}")
                        log_decision(uuid, 'lockbox', False, 'copy failed')
                        logger.error(f"❌ FAILED to lockbox {uuid[:8]}")
                else:
                    processing_stats['errors'].append(f"Photo {uuid[:8]} not found locally")
                    log_decision(uuid, 'lockbox', False, 'photo not found locally')
                    logger.error(f"❌ FAILED to lockbox {uuid[:8]} - not found locally")

            elif action == 'skip':
                processing_stats['skipped'] += 1
                log_decision(uuid, 'skip', True, 'skipped for later')
                logger.info(f"⏭️ SKIPPED {uuid[:8]}")

        except Exception as e:
            logger.error(f"❌ PROCESS ERROR {uuid[:8]}: {e}")
            log_decision(uuid, action, False, str(e))
            processing_stats['errors'].append(f"{uuid[:8]}: {str(e)}")

        action_queue.task_done()
        processing_stats['processing'] = action_queue.qsize() > 0
        save_session_stats()  # Persist to database after each action


def log_session_summary():
    """Log final session summary."""
    logger.info("=" * 50)
    logger.info("REVIEW SESSION COMPLETE")
    logger.info(f"  👍 Approved:  {processing_stats['approved']}")
    logger.info(f"  👎 Removed:   {processing_stats['removed']}")
    logger.info(f"  📦 Lockboxed: {processing_stats['lockboxed']}")
    logger.info(f"  ⏭️ Skipped:   {processing_stats['skipped']}")
    if processing_stats['errors']:
        logger.info(f"  ⚠️ Errors:    {len(processing_stats['errors'])}")
        for err in processing_stats['errors']:
            logger.info(f"     - {err}")
    logger.info("=" * 50)


# Start background thread
processor_thread = Thread(target=background_processor, daemon=True)
processor_thread.start()


@app.route('/api/action/<uuid>', methods=['POST'])
def api_action(uuid: str):
    """Queue review action for background processing."""
    data = request.get_json()
    action = data.get('action')

    if action in ('approve', 'remove', 'lockbox', 'skip'):
        action_queue.put((uuid, action))
        return jsonify({'success': True, 'queued': True, 'queue_size': action_queue.qsize()})
    else:
        return jsonify({'success': False, 'error': 'Unknown action'})


@app.route('/api/stats')
def api_stats():
    """Get processing stats."""
    return jsonify({
        **processing_stats,
        'pending': action_queue.qsize(),
        'session_id': current_session_id
    })


@app.route('/api/session', methods=['POST'])
def api_session():
    """Create or resume a session."""
    data = request.get_json() or {}
    session_id = data.get('session_id')

    if session_id:
        # Try to resume existing session
        stats = load_session(session_id)
        if stats:
            return jsonify({'resumed': True, 'session_id': session_id, 'stats': stats})

    # Create new session
    new_session_id = create_session()
    return jsonify({'resumed': False, 'session_id': new_session_id, 'stats': processing_stats})


@app.route('/api/failed')
def api_failed():
    """Get list of failed deletions for manual handling."""
    return jsonify({
        'errors': processing_stats['errors'],
        'count': len(processing_stats['errors'])
    })


def open_browser(port: int):
    """Open browser after short delay."""
    webbrowser.open(f'http://localhost:{port}')


def run_webapp(port: int = 5050, open_browser_flag: bool = True):
    """Run the web app."""
    print(f"Starting NSFW review webapp on http://localhost:{port}")

    if open_browser_flag:
        Timer(1.0, open_browser, args=[port]).start()

    app.run(host='127.0.0.1', port=port, debug=False)
