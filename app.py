from flask import Flask, render_template, request, redirect, url_for, send_file
import yt_dlp
import os
from datetime import datetime
import re
from threading import Thread, Lock
import time
import random

app = Flask(__name__)

DOWNLOAD_FOLDER = 'downloads'
CACHE_DURATION = 300  # 5 minutes cache

# Cache dictionary to store recent downloads and lock for thread safety
download_cache = {}
cache_lock = Lock()

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

def sanitize_filename(title):
    """Remove invalid characters from filename"""
    return re.sub(r'[\\/*?:"<>|]', "", title)

# List of mobile user agents to rotate
MOBILE_USER_AGENTS = [
    'Mozilla/5.0 (Linux; Android 12; SM-S906N Build/QP1A.190711.020; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/120.0.6099.210 Mobile Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (Linux; Android 13; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36',
    'Mozilla/5.0 (iPad; CPU OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/101.0.4951.44 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (Linux; Android 11; Redmi Note 9 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Mobile Safari/537.36'
]

def get_random_user_agent():
    """Return a random mobile user agent"""
    return random.choice(MOBILE_USER_AGENTS)

def get_available_formats(url):
    user_agent = get_random_user_agent()
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'writeinfojson': False,
        'youtube_include_dash_manifest': False,  # Reduce complexity of request
        'format': 'bestvideo+bestaudio/best',
        'user_agent': user_agent,
        'http_headers': {
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://www.youtube.com/',
            'X-Forwarded-For': f"192.168.{random.randint(1, 254)}.{random.randint(1, 254)}"
        },
        'nocheckcertificate': True,
        'geo_bypass': True,
        'geo_bypass_country': 'US',  # Try using US as location
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web'],  # Try both clients
                'compat_opts': ['no-youtube-unavailable-videos']
            }
        }
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = []
            
            # Process all available formats
            for f in info.get('formats', []):
                # Include formats with either height or width
                if not (f.get('height') or f.get('width')):
                    continue
                    
                format_info = {
                    'format_id': f['format_id'],
                    'ext': f['ext'],
                    'resolution': f"{f.get('height', '?')}p",
                    'filesize': f.get('filesize', f.get('filesize_approx', 0)),
                    'vcodec': f.get('vcodec', 'none'),
                    'acodec': f.get('acodec', 'none'),
                    'fps': f.get('fps', '?'),
                    'tbr': f.get('tbr', 0)
                }
                
                # Modified format type labeling
                if format_info['vcodec'] != 'none':
                    if format_info['acodec'] != 'none':
                        format_info['type'] = 'Video + Audio'
                    else:
                        format_info['type'] = 'Video only'
                    formats.append(format_info)
                elif format_info['acodec'] != 'none':
                    format_info['type'] = 'Audio only'
                    formats.append(format_info)

            # Add preset format options
            additional_formats = [
                {
                    'format_id': 'bestvideo+bestaudio/best',
                    'ext': 'mp4',
                    'resolution': 'Best quality',
                    'filesize': 0,
                    'type': 'Best quality (Merged)'
                },
                {
                    'format_id': 'bestvideo[height<=1080]+bestaudio/best',
                    'ext': 'mp4',
                    'resolution': 'Best up to 1080p',
                    'filesize': 0,
                    'type': 'Merged 1080p'
                },
                {
                    'format_id': 'bestvideo[height<=720]+bestaudio/best',
                    'ext': 'mp4',
                    'resolution': 'Best up to 720p',
                    'filesize': 0,
                    'type': 'Merged 720p'
                },
                {
                    'format_id': 'bestaudio/best',
                    'ext': 'm4a',
                    'resolution': 'Audio only',
                    'filesize': 0,
                    'type': 'Best audio'
                }
            ]
            formats.extend(additional_formats)
            
            # Sort formats
            formats = sorted(formats, 
                            key=lambda x: (
                                0 if x['resolution'] in ['Best quality', 'Best up to 1080p', 'Best up to 720p'] else
                                1 if x['type'] == 'Video + Audio' else
                                2 if x['type'] == 'Video only' else 3,
                                # Try to parse resolution as number for sorting
                                int(x['resolution'].replace('p', '')) if x['resolution'].replace('p', '').isdigit() else 0
                            ), 
                            reverse=True)
            
            return formats, info.get('title', 'Untitled Video')
    except Exception as e:
        raise Exception(f"Error extracting video information: {str(e)}")

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        youtube_url = request.form['youtube_url']
        try:
            formats, video_title = get_available_formats(youtube_url)
            return render_template('select_format.html', formats=formats, youtube_url=youtube_url, video_title=video_title)
        except Exception as e:
            return render_template('index.html', error=str(e))
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    youtube_url = request.form['youtube_url']
    format_id = request.form['format_id']
    video_title = request.form['video_title']
    
    # Check cache for recent downloads with thread safety
    cache_key = f"{youtube_url}_{format_id}"
    current_time = datetime.now()
    
    with cache_lock:
        if cache_key in download_cache:
            cached_file, cache_time = download_cache[cache_key]
            if (current_time - cache_time).total_seconds() < CACHE_DURATION and os.path.exists(cached_file):
                return send_file(cached_file, as_attachment=True, download_name=os.path.basename(cached_file))
    
    sanitized_title = sanitize_filename(video_title)
    timestamp = current_time.strftime("%Y%m%d_%H%M%S")
    output_filename = f"{sanitized_title}_{timestamp}.%(ext)s"
    output_path = os.path.join(DOWNLOAD_FOLDER, output_filename)
    
    user_agent = get_random_user_agent()
    
    ydl_opts = {
        'format': format_id,
        'outtmpl': output_path,
        'noplaylist': True,
        'quiet': False,
        'no_warnings': False,
        'postprocessors': [{
            'key': 'FFmpegMetadata',
            'add_metadata': True,
        }],
        'user_agent': user_agent,
        'http_headers': {
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://www.youtube.com/',
            'X-Forwarded-For': f"192.168.{random.randint(1, 254)}.{random.randint(1, 254)}"
        },
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': True,  # Log to stderr for debugging
        'geo_bypass': True,
        'geo_bypass_country': 'US',
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web'],  # Try both clients
                'compat_opts': ['no-youtube-unavailable-videos']
            }
        },
        'socket_timeout': 30,
        'retries': 10,  # Increase retry attempts
        'retry_sleep_functions': {'http': lambda x: 5 + x * 2},  # Progressive backoff
        'max_sleep_interval': 15,
        'force_ipv4': True
    }
    
    # Add a proxy if configured
    if os.environ.get('HTTP_PROXY') or os.environ.get('HTTPS_PROXY'):
        ydl_opts['proxy'] = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=True)
            downloaded_file = ydl.prepare_filename(info)
            
            if not os.path.exists(downloaded_file):
                base_path = os.path.splitext(downloaded_file)[0]
                for ext in ['.mp4', '.webm', '.mkv', '.m4a', '.mp3']:
                    possible_file = base_path + ext
                    if os.path.exists(possible_file):
                        downloaded_file = possible_file
                        break
            
            # Update cache with thread safety
            with cache_lock:
                download_cache[cache_key] = (downloaded_file, current_time)
                # Clean old cache entries
                current_time = datetime.now()
                expired_keys = [k for k, v in download_cache.items()
                               if (current_time - v[1]).total_seconds() > CACHE_DURATION]
                for k in expired_keys:
                    del download_cache[k]
            
            response = send_file(downloaded_file, as_attachment=True, download_name=os.path.basename(downloaded_file))
            
            def delayed_delete():
                time.sleep(120)  # 2 minutes delay
                try:
                    if os.path.exists(downloaded_file):
                        os.remove(downloaded_file)
                        with cache_lock:
                            if cache_key in download_cache and download_cache[cache_key][0] == downloaded_file:
                                del download_cache[cache_key]
                except Exception as e:
                    print(f"Error deleting file: {str(e)}")
            
            delete_thread = Thread(target=delayed_delete)
            delete_thread.daemon = True
            delete_thread.start()
            
            return response
    except Exception as e:
        error_message = str(e)
        if 'Sign in to confirm' in error_message or 'bot' in error_message.lower():
            error_message = "YouTube has detected this as automated activity. Try a different format or video, or try using a proxy."
        return render_template('index.html', error=error_message)

# Add a route to check if Railway environment variables are available
@app.route('/check_env', methods=['GET'])
def check_env():
    is_railway = os.environ.get('RAILWAY_STATIC_URL') is not None or os.environ.get('RAILWAY_SERVICE_ID') is not None
    proxy_configured = os.environ.get('HTTP_PROXY') is not None or os.environ.get('HTTPS_PROXY') is not None
    env_info = {
        "running_on_railway": is_railway,
        "proxy_configured": proxy_configured,
        "download_folder_exists": os.path.exists(DOWNLOAD_FOLDER),
        "python_version": os.environ.get('PYTHON_VERSION', 'Unknown')
    }
    return str(env_info)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)