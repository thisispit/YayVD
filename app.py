from flask import Flask, render_template, request, redirect, url_for, send_file
import yt_dlp
import os
from datetime import datetime, timedelta
import re
import shutil
import logging
import threading
import time
from functools import lru_cache

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

DOWNLOAD_FOLDER = 'downloads'
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

# Try multiple possible FFmpeg locations
POSSIBLE_FFMPEG_PATHS = [
    os.path.join(os.getcwd(), 'ffmpeg', 'bin', 'ffmpeg.exe'),  # Local ffmpeg folder
    os.path.join(os.getcwd(), 'ffmpeg.exe'),                   # Root folder
    shutil.which('ffmpeg'),                                    # System PATH
    r"C:\ffmpeg\bin\ffmpeg.exe",                              # Common install location
]

def find_ffmpeg():
    for path in POSSIBLE_FFMPEG_PATHS:
        if path and os.path.exists(path):
            logger.info(f"Found FFmpeg at: {path}")
            return path
    logger.warning("FFmpeg not found in any standard location!")
    return None

FFMPEG_PATH = find_ffmpeg()
FFMPEG_AVAILABLE = FFMPEG_PATH is not None

logger.info(f"FFmpeg available: {FFMPEG_AVAILABLE}")
if FFMPEG_AVAILABLE:
    logger.info(f"Using FFmpeg from: {FFMPEG_PATH}")

def sanitize_filename(title):
    """Remove invalid characters from filename"""
    return re.sub(r'[\\/*?:"<>|]', "", title)

def get_resolution_value(resolution_str):
    """Convert resolution string to numeric value for sorting"""
    try:
        if 'Best' in resolution_str:
            return float('inf')
        # Extract numbers from the resolution string
        numbers = re.findall(r'\d+', resolution_str)
        if numbers:
            # Use the first number found (height)
            return int(numbers[0])
        return 0
    except Exception:
        return 0

def get_format_priority(format_info):
    """Calculate priority score for format sorting"""
    # Base priority for complete vs video-only formats
    base_priority = 1000 if not format_info.get('is_video_only', False) else 0
    
    # Add resolution-based priority
    if 'Best quality' in format_info.get('resolution', ''):
        resolution_priority = 500
    elif '4K' in format_info.get('resolution', ''):
        resolution_priority = 400
    elif '2K' in format_info.get('resolution', ''):
        resolution_priority = 300
    elif 'Full HD' in format_info.get('resolution', ''):
        resolution_priority = 200
    elif 'HD' in format_info.get('resolution', ''):
        resolution_priority = 100
    else:
        resolution_priority = get_resolution_value(format_info.get('resolution', '0')) // 10
    
    return base_priority + resolution_priority

def get_available_formats(url):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'writeinfojson': False,
        'youtube_include_dash_manifest': True,
        'cookiesfrombrowser': ('chrome',),  # Try to use Chrome cookies
        'no_check_certificates': True,
    }
    
    if FFMPEG_PATH:
        ydl_opts['ffmpeg_location'] = FFMPEG_PATH

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        formats = []
        
        # Add best quality options first if FFmpeg is available
        if FFMPEG_AVAILABLE:
            best_formats = [
                {
                    'format_id': 'bestvideo*+bestaudio/best',
                    'ext': 'mp4',
                    'resolution': 'Best quality',
                    'filesize': 0,
                    'type': 'Best quality (video+audio)',
                    'requires_ffmpeg': True
                },
                {
                    'format_id': 'bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best',
                    'ext': 'mp4',
                    'resolution': 'Best MP4',
                    'filesize': 0,
                    'type': 'Best MP4 quality',
                    'requires_ffmpeg': True
                },
                {
                    'format_id': 'bv*[height=2160]+ba/b[height=2160]',
                    'ext': 'mp4',
                    'resolution': '4K (2160p)',
                    'filesize': 0,
                    'type': '4K quality',
                    'requires_ffmpeg': True
                },
                {
                    'format_id': 'bv*[height=1440]+ba/b[height=1440]',
                    'ext': 'mp4',
                    'resolution': '2K (1440p)',
                    'filesize': 0,
                    'type': '2K quality',
                    'requires_ffmpeg': True
                },
                {
                    'format_id': 'bv*[height=1080]+ba/b[height=1080]',
                    'ext': 'mp4',
                    'resolution': 'Full HD (1080p)',
                    'filesize': 0,
                    'type': 'Full HD quality',
                    'requires_ffmpeg': True
                }
            ]
            formats.extend(best_formats)

        # Add all complete formats
        seen_resolutions = set()
        for f in info['formats']:
            if not f.get('height'):
                continue
                
            # Only process formats that have both video and audio
            if f.get('vcodec', 'none') != 'none' and f.get('acodec', 'none') != 'none':
                height = f.get('height', 0)
                format_info = {
                    'format_id': f['format_id'],
                    'ext': f['ext'],
                    'resolution': f"{height}p",
                    'filesize': f.get('filesize', f.get('filesize_approx', 0)),
                    'vcodec': f.get('vcodec', 'none'),
                    'acodec': f.get('acodec', 'none'),
                    'fps': f.get('fps', '?'),
                    'tbr': f.get('tbr', 0),
                    'requires_ffmpeg': False,
                    'type': f"Video + Audio ({f['ext'].upper()})"
                }
                
                # Add format if we haven't seen this resolution or if it's better quality
                resolution_key = f"{height}_{f['ext']}"
                if resolution_key not in seen_resolutions:
                    seen_resolutions.add(resolution_key)
                    formats.append(format_info)

        # Sort formats by resolution and quality
        formats.sort(
            key=lambda x: (
                float('inf') if 'Best' in x['resolution'] else 
                get_resolution_value(x['resolution']),
                x.get('tbr', 0) or 0,
                x['ext'] == 'mp4'  # Prefer MP4 format
            ),
            reverse=True
        )

        # Add quality labels with more detail
        for fmt in formats:
            try:
                height = get_resolution_value(fmt['resolution'])
                fps = fmt.get('fps', '?')
                ext = fmt['ext'].upper()
                if 'Best' in fmt['resolution']:
                    fmt['quality_label'] = f'Best ({ext})'
                else:
                    fmt['quality_label'] = f"{height}p {fps}fps ({ext})"
            except Exception:
                fmt['quality_label'] = 'Auto'

        return formats, info['title']

# Add cache and file tracking
CACHE_TIMEOUT = 120  # 2 minutes
downloaded_files = {}  # Track files with their download times

def cleanup_old_files():
    """Background thread to clean up old downloaded files"""
    while True:
        current_time = datetime.now()
        files_to_remove = []
        
        # Check all tracked files
        for filepath, download_time in downloaded_files.items():
            if current_time - download_time > timedelta(seconds=CACHE_TIMEOUT):
                try:
                    if os.path.exists(filepath):
                        os.remove(filepath)
                        logger.info(f"Cleaned up expired file: {filepath}")
                except Exception as e:
                    logger.error(f"Error cleaning up file {filepath}: {str(e)}")
                files_to_remove.append(filepath)
        
        # Remove cleaned up files from tracking
        for filepath in files_to_remove:
            downloaded_files.pop(filepath, None)
        
        time.sleep(30)  # Check every 30 seconds

# Start cleanup thread
cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
cleanup_thread.start()

@lru_cache(maxsize=32)
def get_video_info(url):
    """Cache video format information"""
    formats, title = get_available_formats(url)
    return formats, title

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        youtube_url = request.form['youtube_url']
        try:
            formats, video_title = get_video_info(youtube_url)  # Use cached function
            return render_template('select_format.html', 
                                formats=formats, 
                                youtube_url=youtube_url, 
                                video_title=video_title,
                                ffmpeg_available=FFMPEG_AVAILABLE,  # Pass as direct variable
                                ffmpeg_path=FFMPEG_PATH)  # Pass FFmpeg path for debugging
        except Exception as e:
            return render_template('index.html', error=str(e))
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    youtube_url = request.form['youtube_url']
    format_id = request.form['format_id']
    video_title = request.form['video_title']
    
    # Generate unique filename
    sanitized_title = sanitize_filename(video_title)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"{sanitized_title}_{timestamp}.%(ext)s"
    output_path = os.path.join(DOWNLOAD_FOLDER, output_filename)
    
    # Check if a recent download exists
    existing_file = None
    for filepath, download_time in downloaded_files.items():
        if (sanitized_title in filepath and 
            datetime.now() - download_time < timedelta(seconds=CACHE_TIMEOUT)):
            existing_file = filepath
            break
    
    if existing_file and os.path.exists(existing_file):
        logger.info(f"Using cached file: {existing_file}")
        response = send_file(
            existing_file,
            as_attachment=True,
            download_name=os.path.basename(existing_file),
            mimetype='application/octet-stream'
        )
        return response
    
    requires_ffmpeg = '+' in format_id or 'bestvideo' in format_id
    
    if requires_ffmpeg and not FFMPEG_AVAILABLE:
        return render_template('index.html', 
                             error="This format requires FFmpeg. Please choose a format that doesn't require merging video and audio.")
    
    ydl_opts = {
        'format': format_id,
        'outtmpl': output_path,
        'noplaylist': True,
        'quiet': False,
        'no_warnings': False,
        'merge_output_format': 'mp4',  # Force MP4 output
        'cookiesfrombrowser': ('chrome',),  # Try to use Chrome cookies
        'no_check_certificates': True,
    }
    
    # Add FFmpeg location if available
    if FFMPEG_PATH:
        ydl_opts['ffmpeg_location'] = FFMPEG_PATH
    
    if FFMPEG_AVAILABLE:
        ydl_opts['postprocessors'] = [
            {
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            },
            {
                'key': 'FFmpegMetadata',
                'add_metadata': True,
            }
        ]
    
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
            
            if not os.path.exists(downloaded_file):
                raise FileNotFoundError("Downloaded file not found")

            # Track the new download
            downloaded_files[downloaded_file] = datetime.now()
            
            # Set up the response with the file
            try:
                response = send_file(
                    downloaded_file,
                    as_attachment=True,
                    download_name=os.path.basename(downloaded_file),
                    mimetype='application/octet-stream'
                )
                
                # Add cache control headers
                response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                response.headers['Pragma'] = 'no-cache'
                response.headers['Expires'] = '0'
                
                return response
                
            except Exception as e:
                # If send_file fails, clean up and re-raise
                if os.path.exists(downloaded_file):
                    os.remove(downloaded_file)
                raise e
                
    except Exception as e:
        error_message = str(e)
        if 'ffmpeg' in error_message.lower():
            error_message += " Please choose another format that doesn't require post-processing."
        return render_template('index.html', error=error_message)

if __name__ == '__main__':
    # Use environment variable for port, defaulting to 10000
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
