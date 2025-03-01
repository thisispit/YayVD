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
        'format': 'best',
        'geo_bypass': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'no_color': True,
        'extractor_retries': 5,
        'socket_timeout': 30,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web'],
                'skip': ['dash', 'hls'],
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Mobile Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
            'Sec-Fetch-Mode': 'navigate'
        }
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                # First try with default options
                info = ydl.extract_info(url, download=False)
                
                if info is None:
                    # If failed, try with alternative options
                    ydl_opts.update({
                        'extractor_args': {
                            'youtube': {
                                'player_client': ['web'],
                                'skip': [],
                            }
                        }
                    })
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl2:
                        info = ydl2.extract_info(url, download=False)
                
                if info is None:
                    return [], "Could not extract video information. Please check the URL and try again."
                
                formats = []
                # Add basic format as fallback
                formats.append({
                    'format_id': 'best',
                    'ext': 'mp4',
                    'resolution': 'Auto',
                    'filesize': 0,
                    'type': 'Auto Quality',
                    'requires_ffmpeg': False,
                    'quality_label': 'Auto'
                })
                
                # Add available formats from the video if present
                if 'formats' in info:
                    seen_qualities = set()
                    for f in info['formats']:
                        if f.get('height') and f.get('acodec') != 'none' and f.get('vcodec') != 'none':
                            quality = f"{f.get('height')}p"
                            if quality not in seen_qualities:
                                seen_qualities.add(quality)
                                format_info = {
                                    'format_id': f['format_id'],
                                    'ext': f.get('ext', 'mp4'),
                                    'resolution': quality,
                                    'filesize': f.get('filesize', 0),
                                    'type': f"Video + Audio ({f.get('ext', 'mp4').upper()})",
                                    'requires_ffmpeg': False,
                                    'quality_label': quality
                                }
                                formats.append(format_info)
                
                # Sort formats by resolution
                formats.sort(key=lambda x: int(x['resolution'].replace('p', '')) if x['resolution'] != 'Auto' else 0, reverse=True)
                
                return formats, info.get('title', 'Video')
            except Exception as e:
                logger.error(f"Error extracting formats: {str(e)}")
                # Return basic format as fallback
                return [{
                    'format_id': 'best',
                    'ext': 'mp4',
                    'resolution': 'Auto',
                    'filesize': 0,
                    'type': 'Auto Quality',
                    'requires_ffmpeg': False,
                    'quality_label': 'Auto'
                }], "Video"
    except Exception as e:
        logger.error(f"YoutubeDL error: {str(e)}")
        return [], f"Error initializing downloader: {str(e)}"

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
    try:
        url = request.form['url']
        format_id = request.form['format']
        
        ydl_opts = {
            'format': format_id,
            'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
            'geo_bypass': True,
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'no_color': True,
            'extractor_retries': 5,
            'socket_timeout': 30,
            'quiet': False,
            'no_warnings': False,
            'merge_output_format': 'mp4',
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web'],
                    'skip': ['dash', 'hls'],
                }
            },
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Mobile Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Sec-Fetch-Mode': 'navigate'
            }
        }
        
        if FFMPEG_PATH:
            ydl_opts['ffmpeg_location'] = FFMPEG_PATH
        
        try:
            # First try with default options
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    info = ydl.extract_info(url, download=True)
                    if info is None:
                        # If failed, try with alternative options
                        ydl_opts.update({
                            'format': 'best',  # Fallback to best format
                            'extractor_args': {
                                'youtube': {
                                    'player_client': ['web'],
                                    'skip': [],
                                }
                            }
                        })
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl2:
                            info = ydl2.extract_info(url, download=True)
                    
                    if info is None:
                        return render_template('index.html', error="Could not download video. Please check the URL and try again.")
                    
                    downloaded_file = ydl.prepare_filename(info)
                    
                    if not os.path.exists(downloaded_file):
                        # Try with different extension if file not found
                        base_path = os.path.splitext(downloaded_file)[0]
                        for ext in ['.mp4', '.mkv', '.webm']:
                            alt_file = base_path + ext
                            if os.path.exists(alt_file):
                                downloaded_file = alt_file
                                break
                    
                    if not os.path.exists(downloaded_file):
                        return render_template('index.html', error="Download completed but file not found. Please try again.")
                    
                    # Store in cache
                    downloaded_files[downloaded_file] = datetime.now()
                    
                    return send_file(
                        downloaded_file,
                        as_attachment=True,
                        download_name=os.path.basename(downloaded_file),
                        mimetype='video/mp4'
                    )
                except Exception as e:
                    logger.error(f"Error during download: {str(e)}")
                    return render_template('index.html', error=f"Download error: {str(e)}")
        except Exception as e:
            logger.error(f"YoutubeDL error: {str(e)}")
            return render_template('index.html', error=f"Downloader error: {str(e)}")
    except Exception as e:
        logger.error(f"General error: {str(e)}")
        return render_template('index.html', error=f"An error occurred: {str(e)}")

if __name__ == '__main__':
    # Use environment variable for port, defaulting to 10000
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
