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

# Cache dictionary and lock for thread safety
download_cache = {}
cache_lock = Lock()

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

def sanitize_filename(title):
    """Remove invalid characters from filename"""
    return re.sub(r'[\\/*?:"<>|]', "", title)

# List of desktop user agents to rotate
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
]

def get_random_user_agent():
    """Return a random desktop user agent"""
    return random.choice(USER_AGENTS)

def get_available_formats(url):
    user_agent = get_random_user_agent()
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'writeinfojson': False,
        'format': 'bestvideo+bestaudio/best',
        'user_agent': user_agent,
        'http_headers': {
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://www.youtube.com/'
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
                
                # Improved format type labeling - more accurate audio detection
                has_video = format_info['vcodec'] != 'none' and format_info['vcodec'] != 'anull'
                has_audio = format_info['acodec'] != 'none' and format_info['acodec'] != 'anull'
                
                if has_video:
                    if has_audio:
                        format_info['type'] = 'Video + Audio'
                    else:
                        format_info['type'] = 'Video only'
                    formats.append(format_info)
                elif has_audio:
                    format_info['type'] = 'Audio only'
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
                    'format_id': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
                    'ext': 'mp4',
                    'resolution': 'Best up to 1080p',
                    'filesize': 0,
                    'type': 'Merged 1080p'
                },
                {
                    'format_id': 'bestvideo[height<=720]+bestaudio/best[height<=720]',
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
            
            # Create merged audio+video options from video-only formats
            video_only_formats = [f for f in formats if f['type'] == 'Video only']
            best_audio = next((f for f in formats if f['type'] == 'Audio only' and f.get('tbr', 0) > 0), None)
            
            if best_audio and video_only_formats:
                merged_formats = []
                # Get unique resolutions from video-only formats
                unique_resolutions = set()
                for vf in video_only_formats:
                    resolution = vf.get('resolution', '')
                    if resolution and resolution not in unique_resolutions and resolution.replace('p', '').isdigit():
                        unique_resolutions.add(resolution)
                        # Create a merged format option
                        merged_format = {
                            'format_id': f"{vf['format_id']}+{best_audio['format_id']}",
                            'ext': 'mp4',
                            'resolution': f"{resolution} (Merged)",
                            'filesize': vf.get('filesize', 0) + best_audio.get('filesize', 0),
                            'type': 'Video + Audio (FFmpeg)',
                            'fps': vf.get('fps', '?')
                        }
                        merged_formats.append(merged_format)
                
                # Add the merged formats to the list
                formats.extend(merged_formats)
            
            # Filter formats to include video+audio, audio-only, or merged sources
            formats = [f for f in formats if 
                      'Video + Audio' in f['type'] or 
                      'Merged' in f['type'] or 
                      'Audio only' in f['type'] or
                      'Best quality' in f['resolution'] or
                      'FFmpeg' in f.get('type', '')]
            
            # Sort formats - prioritize 1080p, then other formats, move Best quality to bottom
            formats = sorted(formats, 
                            key=lambda x: (
                                # Prioritize 1080p formats
                                9 if x['resolution'] == '1080p' or '1080p (Merged)' in x['resolution'] else
                                # Put Best quality at the bottom
                                0 if x['resolution'] == 'Best quality' else
                                # Regular sorting for other formats
                                1 if x['type'] == 'Video + Audio' else
                                2 if 'Merged' in x['type'] and 'Best up to' not in x['resolution'] else
                                3 if 'Audio only' in x['type'] else
                                4 if 'Best up to' in x['resolution'] else 5,
                                # Try to parse resolution as number for sorting
                                int(x['resolution'].replace('p', '')) if x['resolution'].replace('p', '').isdigit() else 0
                            ), 
                            reverse=True)
            
            # Add 'recommended' flag to 1080p formats
            for format in formats:
                if format['resolution'] == '1080p' or '1080p (Merged)' in format['resolution']:
                    format['recommended'] = True
            
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
    
    # Check cache for recent downloads
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
    
    # FIX: Improved format selection logic
    format_selection = format_id
    is_custom_merge = False
    
    # For preset formats, refine the format selection to ensure proper quality
    if 'bestvideo[height<=1080]+bestaudio' in format_id:
        # Force 1080p or highest available below that
        format_selection = 'bestvideo[height<=1080][height>=720]+bestaudio/best[height<=1080]'
    elif 'bestvideo[height<=720]+bestaudio' in format_id:
        # Force 720p or highest available below that
        format_selection = 'bestvideo[height<=720][height>=480]+bestaudio/best[height<=720]'
    elif 'bestvideo+bestaudio' in format_id:
        # Ensure we get the best quality with proper merging
        format_selection = 'bestvideo+bestaudio/best'
    # Handle custom video+audio merges created from video-only formats
    elif '+' in format_id and '(Merged)' in request.form.get('resolution', ''):
        # This is a custom format that needs to be merged with FFmpeg
        video_format, audio_format = format_id.split('+')
        format_selection = f"{video_format}+{audio_format}"
        is_custom_merge = True
        
    ydl_opts = {
        'format': format_selection,
        'outtmpl': output_path,
        'noplaylist': True,
        'quiet': False,
        # Always use FFmpeg for merging to ensure audio is included when available
        'postprocessors': [
            {
                'key': 'FFmpegMetadata',
                'add_metadata': True,
            },
            # Add FFmpeg video remuxer to ensure proper merging
            {
                'key': 'FFmpegVideoRemuxer',
                'preferedformat': 'mp4',
            }
        ],
        # Ensure FFmpeg is used for merging separate audio and video
        'merge_output_format': 'mp4',
        'user_agent': user_agent,
        'cookiesfrombrowser': ['chrome'],  # Use cookies from Chrome browser
        'http_headers': {
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://www.youtube.com/'
        },
        'retries': 5
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
            
            # Update cache
            with cache_lock:
                download_cache[cache_key] = (downloaded_file, current_time)
                
                # Clean old cache entries
                expired_keys = [k for k, v in download_cache.items()
                               if (current_time - v[1]).total_seconds() > CACHE_DURATION]
                for k in expired_keys:
                    del download_cache[k]
            
            response = send_file(downloaded_file, as_attachment=True, download_name=os.path.basename(downloaded_file))
            
            # Schedule file cleanup
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

@app.route('/check_env', methods=['GET'])
def check_env():
    is_railway = os.environ.get('RAILWAY_STATIC_URL') is not None or os.environ.get('RAILWAY_SERVICE_ID') is not None
    proxy_configured = os.environ.get('HTTP_PROXY') is not None or os.environ.get('HTTPS_PROXY') is not None
    env_info = {
        "running_on_railway": is_railway,
        "proxy_configured": proxy_configured,
        "download_folder_exists": os.path.exists(DOWNLOAD_FOLDER)
    }
    return str(env_info)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)