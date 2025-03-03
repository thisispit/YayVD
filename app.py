from flask import Flask, render_template, request, redirect, url_for, send_file
import yt_dlp
import os
from datetime import datetime
import re
from threading import Thread, Lock
import time

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
    
    # Detect if running on Railway or other cloud platform
    is_cloud_env = os.environ.get('RAILWAY_STATIC_URL') is not None or os.environ.get('RAILWAY_SERVICE_ID') is not None
    
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
        # Only use browser cookies when running locally
        'cookiesfrombrowser': None if is_cloud_env else ('chrome',),
        # Use a more mobile-like user agent to avoid bot detection
        'user_agent': 'Mozilla/5.0 (Linux; Android 12; SM-S906N Build/QP1A.190711.020; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/120.0.6099.210 Mobile Safari/537.36',
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 12; SM-S906N Build/QP1A.190711.020; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/120.0.6099.210 Mobile Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://m.youtube.com/',  # Mobile YouTube referrer
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120"',
            'Sec-Ch-Ua-Mobile': '?1',  # Indicate mobile device
            'Sec-Ch-Ua-Platform': '"Android"',  # Indicate Android platform
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',  # Changed from same-origin to none
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'Connection': 'keep-alive',
            'Cache-Control': 'max-age=0',
            'X-Requested-With': 'com.google.android.youtube'  # Add YouTube Android app identifier
        },
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': False,
        'geo_bypass': True,
        'geo_bypass_country': 'US',
        'extractor_args': {
            'youtube': {
                'player_client': ['android'],  # Prioritize Android client
                'player_skip': ['webpage', 'configs', 'js'],
                'skip': ['hls', 'dash'],
                'compat_opts': ['no-youtube-unavailable-videos']
            }
        },
        'socket_timeout': 30,
        'retry_sleep_functions': {'http': lambda x: 5},
        'source_address': '0.0.0.0',
        'force_ipv4': True,
        'ap_mso': None,  # Disable authentication provider
        'ap_list': [],   # Empty authentication provider list
        'max_sleep_interval': 5,  # Limit sleep between retries
        'sleep_interval_function': lambda attempt: 1 + attempt * 2  # Progressive backoff
    }
    
    # Add proxy configuration if running in cloud environment and proxy is configured
    if is_cloud_env:
        # Check if proxy environment variables are set
        http_proxy = os.environ.get('HTTP_PROXY')
        https_proxy = os.environ.get('HTTPS_PROXY')
        if http_proxy or https_proxy:
            ydl_opts['proxy'] = https_proxy or http_proxy
    
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
