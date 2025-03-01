from flask import Flask, render_template, request, send_file, after_this_request
import yt_dlp
import os
from datetime import datetime, timedelta
import re
import threading
import time
import subprocess

app = Flask(__name__)

# Use absolute path for downloads folder within the container
DOWNLOAD_FOLDER = '/app/downloads'
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# Store cache for downloaded files
download_cache = {}

def sanitize_filename(title):
    """Remove invalid characters from filename."""
    return re.sub(r'[\\/*?:"<>|]', "", title)

def is_ffmpeg_installed(ffmpeg_location=None):
    """Check if ffmpeg is installed and accessible."""
    try:
        # Check system-specific paths
        if os.name == 'nt':  # Windows
            possible_paths = [
                r'C:\ffmpeg\bin\ffmpeg.exe',
                'ffmpeg.exe',
                os.path.join(os.getcwd(), 'ffmpeg.exe'),
                os.environ.get('FFMPEG_PATH', '')
            ]
        else:  # Linux/Unix
            possible_paths = [
                '/usr/bin/ffmpeg',
                'ffmpeg',
                '/app/.apt/usr/bin/ffmpeg',
                os.environ.get('FFMPEG_PATH', '')
            ]
        possible_paths = [p for p in possible_paths if p]
        for path in possible_paths:
            try:
                result = subprocess.run([path, '-version'],
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE,
                                     timeout=5)
                if result.returncode == 0:
                    print(f"FFmpeg found at: {path}")
                    return path
            except Exception as e:
                print(f"Failed to run FFmpeg at {path}: {e}")
                continue
        print("No FFmpeg installation found")
        return False
    except Exception as e:
        print(f"FFmpeg check error: {e}")
        return False

def get_available_formats(url):
    """Retrieve available formats from the video."""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'no_check_certificate': True,
        'extract_flat': False,  # Changed to False to get full info
        'format': 'best',  # Default format for initial check
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
            'Sec-Fetch-Mode': 'navigate',
        },
        'socket_timeout': 30,
        'extractor_args': {
            'youtube': {
                'skip': ['hls', 'dash'],  # Skip live formats
                'player_skip': ['js', 'configs', 'webpage']  # Skip additional data
            }
        }
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        formats = []
        
        # Add muxed formats (combined audio and video)
        for f in info['formats']:
            if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                if not f.get('height') and not f.get('width'):
                    continue
                format_info = {
                    'format_id': f['format_id'],
                    'ext': f['ext'],
                    'resolution': f"{f.get('height', '?')}p",
                    'filesize': f.get('filesize', f.get('filesize_approx', 0)),
                    'vcodec': f.get('vcodec', 'none'),
                    'acodec': f.get('acodec', 'none'),
                    'fps': f.get('fps', '?'),
                    'tbr': f.get('tbr', 0),
                    'type': 'Muxed'
                }
                formats.append(format_info)
        
        # Add merging options (which require ffmpeg)
        merged_options = [
            {
                'format_id': 'bestvideo+bestaudio/best',
                'ext': 'mp4',
                'resolution': 'Best quality',
                'filesize': 0,
                'type': 'Merged'
            },
            {
                'format_id': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]',
                'ext': 'mp4',
                'resolution': 'Best MP4',
                'filesize': 0,
                'type': 'Merged'
            },
            {
                'format_id': 'best[height<=1080]',
                'ext': 'mp4',
                'resolution': 'Up to 1080p',
                'filesize': 0,
                'type': 'Merged'
            }
        ]
        formats.extend(merged_options)
        
        # Custom sort: prioritize merged options with high artificial quality scores.
        def sort_key(fmt):
            if fmt['type'] == 'Merged':
                mapping = {'Best quality': 10000, 'Best MP4': 10000, 'Up to 1080p': 1080}
                return mapping.get(fmt['resolution'], 10000)
            else:
                try:
                    return int(fmt['resolution'].replace('p', ''))
                except:
                    return 0
        
        formats = sorted(formats, key=sort_key, reverse=True)
        
        # Remove duplicate resolutions (keeping first occurrence)
        seen = set()
        unique_formats = []
        for fmt in formats:
            if fmt['resolution'] not in seen:
                seen.add(fmt['resolution'])
                unique_formats.append(fmt)
                
        return unique_formats, info['title']

def delayed_file_delete(filepath, delay_seconds=60):
    """Delete file after a delay (and remove it from cache)."""
    def delete_job():
        time.sleep(delay_seconds)
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                print(f"Successfully deleted: {filepath} after {delay_seconds} seconds")
            keys_to_delete = [key for key, value in download_cache.items() if value['file'] == filepath]
            for key in keys_to_delete:
                del download_cache[key]
        except Exception as e:
            print(f"Error deleting file {filepath}: {e}")
    t = threading.Thread(target=delete_job)
    t.daemon = True
    t.start()
    return t

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        youtube_url = request.form['youtube_url']
        try:
            formats, video_title = get_available_formats(youtube_url)
            return render_template('select_format.html', 
                                   formats=formats, 
                                   youtube_url=youtube_url, 
                                   video_title=video_title)
        except Exception as e:
            return render_template('index.html', error=str(e))
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    youtube_url = request.form['youtube_url']
    format_id = request.form['format_id']
    video_title = request.form['video_title']
    
    # Check cache for a recent download
    cache_key = (youtube_url, format_id)
    if cache_key in download_cache:
        cached = download_cache[cache_key]
        if os.path.exists(cached['file']):
            print("Serving cached file")
            return send_file(
                cached['file'],
                as_attachment=True,
                download_name=os.path.basename(cached['file']),
                conditional=True
            )
    
    sanitized_title = sanitize_filename(video_title)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"{sanitized_title}_{timestamp}.%(ext)s"
    output_path = os.path.join(DOWNLOAD_FOLDER, output_filename)
    
    # Build postprocessors. For merged formats, check for FFmpeg.
    postprocessors = [{
        'key': 'FFmpegMetadata',
        'add_metadata': True,
    }]
    if ('+' in format_id) or ('bestvideo' in format_id and 'bestaudio' in format_id):
        if not is_ffmpeg_installed():
            return render_template('index.html', error="FFmpeg is not installed. Please select a muxed format or install FFmpeg.")
        postprocessors.insert(0, {'key': 'FFmpegMerger'})
    
    ffmpeg_path = is_ffmpeg_installed()
    if not ffmpeg_path:
        return render_template('index.html', error="FFmpeg is not accessible")
    
    ydl_opts = {
        'format': format_id,
        'outtmpl': output_path,
        'noplaylist': True,
        'quiet': False,
        'no_warnings': False,
        'ffmpeg_location': ffmpeg_path,
        'postprocessors': postprocessors,
        'no_check_certificate': True,
        'socket_timeout': 30,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
            'Sec-Fetch-Mode': 'navigate',
        },
        'extractor_args': {
            'youtube': {
                'skip': ['hls', 'dash'],
                'player_skip': ['js', 'configs', 'webpage']
            }
        }
    }
    
    downloaded_file = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=True)
            downloaded_file = ydl.prepare_filename(info)
            
            # For merged formats, the final file may have a different extension.
            if not os.path.exists(downloaded_file):
                base = os.path.splitext(downloaded_file)[0]
                for ext in ['.mp4', '.webm', '.mkv', '.m4a', '.mp3']:
                    candidate = base + ext
                    if os.path.exists(candidate):
                        downloaded_file = candidate
                        break
            
            if not downloaded_file or not os.path.exists(downloaded_file):
                raise FileNotFoundError("Downloaded file not found")
            
            download_cache[cache_key] = {'file': downloaded_file, 'time': datetime.now()}
            
            # Create the response and schedule deletion after the response is sent.
            response = send_file(
                downloaded_file,
                as_attachment=True,
                download_name=os.path.basename(downloaded_file),
                conditional=True
            )
            @after_this_request
            def remove_file(response):
                # Schedule deletion after 60 seconds
                delayed_file_delete(downloaded_file, delay_seconds=60)
                return response
            return response
            
    except Exception as e:
        if downloaded_file and os.path.exists(downloaded_file):
            try:
                os.remove(downloaded_file)
            except:
                pass
        return render_template('index.html', error=str(e))

def init_app():
    """Initialize the application and verify dependencies."""
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
    os.chmod(DOWNLOAD_FOLDER, 0o777)
    print(f"Download directory: {os.path.abspath(DOWNLOAD_FOLDER)}")
    print(f"Current working directory: {os.getcwd()}")
    
    ffmpeg_path = is_ffmpeg_installed()
    if not ffmpeg_path:
        print("WARNING: FFmpeg not found. Only non-merged formats will be available.")
    else:
        print(f"FFmpeg found at: {ffmpeg_path}")

init_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
