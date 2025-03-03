<<<<<<< HEAD
from flask import Flask, render_template, request, redirect, url_for, send_file
import yt_dlp
import os
from datetime import datetime
import re
from threading import Thread, Lock
import time
=======
from flask import Flask, render_template, request, send_file
import yt_dlp
import os
import logging
import requests
import random
import time
from urllib.parse import urlparse, parse_qs
import shutil

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
>>>>>>> 2c961646bbb07d254cc13261c49a725688538268

app = Flask(__name__)

DOWNLOAD_FOLDER = 'downloads'
<<<<<<< HEAD
CACHE_DURATION = 300  # 5 minutes cache

# Cache dictionary to store recent downloads and lock for thread safety
download_cache = {}
cache_lock = Lock()

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

def sanitize_filename(title):
    """Remove invalid characters from filename"""
    return re.sub(r'[\\/*?:"<>|]', "", title)

def get_available_formats(url):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'writeinfojson': False,
        'youtube_include_dash_manifest': True,
        'format': 'bestvideo+bestaudio/best'
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        formats = []
        
        # Process all available formats
        for f in info['formats']:
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

        # Get best video and audio streams
        video_formats = [f for f in info['formats'] if f.get('vcodec') != 'none' and f.get('acodec') == 'none']
        audio_formats = [f for f in info['formats'] if f.get('acodec') != 'none' and f.get('vcodec') == 'none']
        
        # Add merged format options
        for video in video_formats:
            if not video.get('height'):
                continue
            
            for audio in audio_formats:
                format_info = {
                    'format_id': f'{video["format_id"]}+{audio["format_id"]}',
                    'ext': 'mp4',
                    'resolution': f'{video.get("height", "?")}p',
                    'filesize': (video.get('filesize', 0) or 0) + (audio.get('filesize', 0) or 0),
                    'type': 'Merged (Video + Audio)',
                    'vcodec': video.get('vcodec', 'unknown'),
                    'acodec': audio.get('acodec', 'unknown'),
                    'fps': video.get('fps', '?'),
                    'tbr': (video.get('tbr', 0) or 0) + (audio.get('tbr', 0) or 0)
                }
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
                'format_id': 'bestvideo[height<=2160]+bestaudio/best',
                'ext': 'mp4',
                'resolution': 'Best up to 4K',
                'filesize': 0,
                'type': 'Merged 4K'
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
            }
        ]
        formats.extend(additional_formats)
        
        # Add special format options for best quality
        formats.append({
            'format_id': 'bestvideo+bestaudio/best',
            'ext': 'mp4',  # Will use best available container
            'resolution': 'Best quality',
            'filesize': 0,
            'type': 'Best quality (video+audio)'
        })
        
        formats.append({
            'format_id': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]',
            'ext': 'mp4',
            'resolution': 'Best MP4',
            'filesize': 0,
            'type': 'Best MP4 quality'
        })
        
        formats.append({
            'format_id': 'best[height<=1080]',
            'ext': 'mp4',
            'resolution': 'Up to 1080p',
            'filesize': 0,
            'type': 'Best quality up to 1080p'
        })
        
        # Sort formats by type (video+audio first) and then by resolution
        def parse_resolution(res):
            if res in ['Best quality', 'Best MP4', 'Up to 1080p', 'Best up to 4K', 'Best up to 1080p', 'Best up to 720p']:
                return 10000  # Give high priority to special formats
            try:
                return int(res.replace('p', ''))
            except (ValueError, AttributeError):
                return 0

        formats = sorted(formats, 
                        key=lambda x: (
                            # Priority order: Best quality options first, then video+audio, then video only, then audio only
                            0 if x['resolution'] in ['Best quality', 'Best MP4', 'Up to 1080p'] else
                            1 if x['type'] == 'Video + Audio' else
                            2 if x['type'] == 'Video only' else
                            3,
                            # Secondary sort by resolution using the new parse_resolution function
                            parse_resolution(x['resolution'])
                        ), 
                        reverse=True)
        
        # Remove duplicate resolutions (keep highest bitrate)
        seen_resolutions = set()
        unique_formats = []
        
        for fmt in formats:
            res_key = fmt['resolution']
            if res_key not in seen_resolutions:
                seen_resolutions.add(res_key)
                unique_formats.append(fmt)
        
        return unique_formats, info['title']
=======
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

# User agents to rotate
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Android 13; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
]

def get_random_user_agent():
    return random.choice(USER_AGENTS)

def extract_video_id(url):
    """Extract the video ID from a YouTube URL"""
    if 'youtu.be' in url:
        return url.split('/')[-1].split('?')[0]
    
    parsed_url = urlparse(url)
    if 'youtube.com' in parsed_url.netloc:
        if '/watch' in parsed_url.path:
            return parse_qs(parsed_url.query).get('v', [''])[0]
        elif '/embed/' in parsed_url.path:
            return parsed_url.path.split('/')[-1]
        elif '/v/' in parsed_url.path:
            return parsed_url.path.split('/')[-1]
    
    return None

def get_available_formats(url):
    """Get available formats using yt-dlp with anti-blocking measures"""
    formats = []
    title = "YouTube Video"
    video_id = extract_video_id(url)
    
    if not video_id:
        return formats, title
        
    # Add standard formats as fallback
    formats = [
        {
            'format_id': 'best',
            'ext': 'mp4',
            'resolution': 'Highest Quality',
            'filesize': 0,
            'type': 'Video + Audio (MP4)',
            'requires_ffmpeg': False,
            'quality_label': 'Auto'
        },
        {
            'format_id': '22',
            'ext': 'mp4',
            'resolution': '720p',
            'filesize': 0,
            'type': 'Video + Audio (MP4)',
            'requires_ffmpeg': False,
            'quality_label': 'HD'
        },
        {
            'format_id': '18',
            'ext': 'mp4',
            'resolution': '360p',
            'filesize': 0,
            'type': 'Video + Audio (MP4)',
            'requires_ffmpeg': False,
            'quality_label': 'SD'
        }
    ]
    
    # Try to get real title
    try:
        # Use a public API to get title without triggering YouTube blocks
        api_url = f"https://noembed.com/embed?url=https://www.youtube.com/watch?v={video_id}"
        response = requests.get(api_url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if 'title' in data:
                title = data['title']
    except Exception as e:
        logger.error(f"Error getting title: {str(e)}")
    
    # Try with yt-dlp as a backup for format info
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'youtube_include_dash_manifest': False,
            'extract_flat': True,
            'skip_download': True,
            'http_headers': {
                'User-Agent': get_random_user_agent(),
                'Referer': 'https://www.google.com/'
            }
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info and 'title' in info:
                title = info['title']
    except Exception as e:
        logger.error(f"Error with yt-dlp format extraction: {str(e)}")
    
    return formats, title

def download_video(url, format_id='best'):
    """Download video with multiple fallback mechanisms"""
    video_id = extract_video_id(url)
    if not video_id:
        return None
    
    # Try direct proxy download first
    try:
        # Use external service that downloads directly
        proxy_url = f"https://projectlounge.pw/ytdl/download?url=https://www.youtube.com/watch?v={video_id}&format={format_id if format_id != 'best' else 'mp4'}"
        headers = {'User-Agent': get_random_user_agent()}
        
        logger.info(f"Trying proxy download from {proxy_url}")
        response = requests.get(proxy_url, headers=headers, timeout=15, stream=True)
        
        if response.status_code == 200 and int(response.headers.get('Content-Length', 0)) > 10000:
            file_path = os.path.join(DOWNLOAD_FOLDER, f"{video_id}_{format_id}.mp4")
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            if os.path.exists(file_path) and os.path.getsize(file_path) > 10000:
                logger.info(f"Successfully downloaded via proxy to {file_path}")
                return file_path
    except Exception as e:
        logger.error(f"Proxy download error: {str(e)}")
    
    # Fallback to yt-dlp
    try:
        logger.info("Falling back to yt-dlp for download")
        ydl_opts = {
            'format': format_id,
            'outtmpl': os.path.join(DOWNLOAD_FOLDER, f'{video_id}_{format_id}.%(ext)s'),
            'http_headers': {
                'User-Agent': get_random_user_agent(),
                'Referer': 'https://www.google.com/'
            }
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info:
                downloaded_file = ydl.prepare_filename(info)
                if os.path.exists(downloaded_file):
                    logger.info(f"Successfully downloaded via yt-dlp to {downloaded_file}")
                    return downloaded_file
    except Exception as e:
        logger.error(f"yt-dlp download error: {str(e)}")
    
    return None

# Clean up old downloads periodically
@app.before_request
def cleanup_old_downloads():
    """Clean up old downloaded files to prevent disk space issues"""
    try:
        # Only run this cleanup occasionally (1 in 10 requests)
        if random.random() < 0.1 and os.path.exists(DOWNLOAD_FOLDER):
            current_time = time.time()
            # Clean files older than 1 hour
            for filename in os.listdir(DOWNLOAD_FOLDER):
                file_path = os.path.join(DOWNLOAD_FOLDER, filename)
                # If file is older than 1 hour, remove it
                if os.path.isfile(file_path) and (current_time - os.path.getmtime(file_path)) > 3600:
                    try:
                        os.remove(file_path)
                        logger.info(f"Cleaned up old file: {file_path}")
                    except:
                        pass
    except Exception as e:
        logger.error(f"Error in cleanup: {str(e)}")

@app.route('/health')
def health_check():
    """Health check endpoint for monitoring"""
    return {"status": "healthy"}, 200
>>>>>>> 2c961646bbb07d254cc13261c49a725688538268

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
<<<<<<< HEAD
        youtube_url = request.form['youtube_url']
        try:
            formats, video_title = get_available_formats(youtube_url)
            return render_template('select_format.html', formats=formats, youtube_url=youtube_url, video_title=video_title)
        except Exception as e:
            return render_template('index.html', error=str(e))
=======
        try:
            url = request.form.get('url', '').strip()
            if not url:
                return render_template('index.html', error="Please enter a URL")
            
            formats, title = get_available_formats(url)
            return render_template('index.html', formats=formats, video_title=title, url=url)
        except Exception as e:
            logger.error(f"Error: {str(e)}")
            return render_template('index.html', error=str(e))
    
>>>>>>> 2c961646bbb07d254cc13261c49a725688538268
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
<<<<<<< HEAD
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
    
    ydl_opts = {
        'format': format_id,
        'outtmpl': output_path,
        'noplaylist': True,
        'quiet': False,
        'no_warnings': False,
        'postprocessors': [{
            'key': 'FFmpegMetadata',
            'add_metadata': True,
        }] if 'ffmpeg' not in format_id else [],
    }
    
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
                # Initial delay to ensure file transfer is complete
                time.sleep(120)  # Increased initial delay to 2 minutes
                max_retries = 10  # Increased max retries
                retry_delay = 60  # Increased retry delay to 60 seconds
                
                for attempt in range(max_retries):
                    try:
                        if os.path.exists(downloaded_file):
                            # Try to open the file to check if it's still in use
                            try:
                                with open(downloaded_file, 'ab') as f:
                                    pass
                                # If we can open the file, it's safe to delete
                                os.remove(downloaded_file)
                                with cache_lock:
                                    if cache_key in download_cache and download_cache[cache_key][0] == downloaded_file:
                                        del download_cache[cache_key]
                                print(f"Successfully deleted {downloaded_file}")
                                break
                            except PermissionError:
                                print(f"File {downloaded_file} is still in use, retrying in {retry_delay} seconds...")
                                time.sleep(retry_delay)
                                continue
                    except Exception as e:
                        print(f"Attempt {attempt + 1} to delete file {downloaded_file} failed: {str(e)}")
                        if attempt < max_retries - 1:  # Don't sleep on the last attempt
                            time.sleep(retry_delay)
            
            delete_thread = Thread(target=delayed_delete)
            delete_thread.daemon = True
            delete_thread.start()
            
            return response
    except Exception as e:
        error_message = str(e)
        if 'ffmpeg' in error_message.lower():
            error_message += " Please choose another format that doesn't require post-processing."
        return render_template('index.html', error=error_message)

if __name__ == '__main__':
    app.run(debug=True)
=======
    try:
        url = request.form.get('url')
        format_id = request.form.get('format', 'best')
        
        if not url:
            return render_template('index.html', error="Please provide a valid URL")
        
        downloaded_file = download_video(url, format_id)
        
        if downloaded_file and os.path.exists(downloaded_file):
            return send_file(
                downloaded_file,
                as_attachment=True,
                download_name=os.path.basename(downloaded_file),
                mimetype='video/mp4'
            )
        
        return render_template('index.html', error="Failed to download video. YouTube may be blocking this request. Please try again with a different URL.")
        
    except Exception as e:
        logger.error(f"General error: {str(e)}")
        return render_template('index.html', error=f"An error occurred: {str(e)}")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
>>>>>>> 2c961646bbb07d254cc13261c49a725688538268
