from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify, make_response
import yt_dlp
import os
import logging
import requests
import random
import time
import json
from pytube import YouTube
from io import BytesIO
from urllib.parse import urlparse, parse_qs

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

DOWNLOAD_FOLDER = 'downloads'
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

# List of public YouTube video proxies - these help circumvent restrictions
PROXIES = [
    "https://yt.lemnoslife.com/videos?part=id%2Csnippet&id=", 
    "https://yt.lemnoslife.com/nodetube?id=",
    "https://invidious.snopyta.org/vi/",
    "https://inv.riverside.rocks/vi/",
    "https://ytb.trom.tf/vi/"
]

# User agents to rotate
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 13; SM-S901B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
]

def get_random_proxy():
    return random.choice(PROXIES)

def get_random_user_agent():
    return random.choice(USER_AGENTS)

def extract_video_id(url):
    """Extract the video ID from a YouTube URL"""
    if 'youtu.be' in url:
        return url.split('/')[-1].split('?')[0]
    
    parsed_url = urlparse(url)
    if 'youtube.com' in parsed_url.netloc:
        if '/watch' in parsed_url.path:
            return parse_qs(parsed_url.query)['v'][0]
        elif '/embed/' in parsed_url.path:
            return parsed_url.path.split('/')[-1]
        elif '/v/' in parsed_url.path:
            return parsed_url.path.split('/')[-1]
    
    return None

def get_video_info_proxied(url):
    """Get video info using a proxy API"""
    video_id = extract_video_id(url)
    if not video_id:
        return None, None
    
    # Try several proxy endpoints with delay between requests
    for _ in range(3):
        try:
            # Add random delay to avoid rate limiting
            time.sleep(random.uniform(0.5, 2.0))
            
            # Choose a random proxy and user agent
            proxy_url = get_random_proxy() + video_id
            headers = {'User-Agent': get_random_user_agent()}
            
            response = requests.get(proxy_url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                
                # Format depends on which proxy we hit
                title = None
                formats = []
                
                # Extract title
                if 'snippet' in data:
                    title = data['snippet'].get('title')
                elif 'title' in data:
                    title = data.get('title')
                
                # Create a standard format response
                if title:
                    formats = [
                        {
                            'format_id': '720p',
                            'ext': 'mp4',
                            'resolution': '720p',
                            'filesize': 0,
                            'type': 'Video + Audio (MP4)',
                            'requires_ffmpeg': False,
                            'quality_label': 'HD'
                        },
                        {
                            'format_id': '480p',
                            'ext': 'mp4',
                            'resolution': '480p',
                            'filesize': 0,
                            'type': 'Video + Audio (MP4)',
                            'requires_ffmpeg': False,
                            'quality_label': 'Standard'
                        },
                        {
                            'format_id': '360p',
                            'ext': 'mp4',
                            'resolution': '360p',
                            'filesize': 0,
                            'type': 'Video + Audio (MP4)',
                            'requires_ffmpeg': False, 
                            'quality_label': 'Low'
                        }
                    ]
                    return formats, title
                    
        except Exception as e:
            logger.error(f"Proxy API error: {str(e)}")
            continue
    
    return None, None

def get_video_info_pytube(url):
    """Get video info using pytube with random user agent rotation"""
    try:
        # Add random delay to avoid being detected as bot
        time.sleep(random.uniform(0.5, 2))
        
        yt = YouTube(url)
        yt.bypass_age_gate()
        streams = yt.streams.filter(progressive=True).order_by('resolution').desc()
        formats = []
        
        # Add streams to formats list
        for stream in streams:
            format_info = {
                'format_id': f"{stream.itag}",
                'ext': stream.subtype,
                'resolution': stream.resolution or 'Auto',
                'filesize': stream.filesize,
                'type': f"Video + Audio ({stream.subtype.upper()})",
                'requires_ffmpeg': False,
                'quality_label': stream.resolution or 'Auto'
            }
            formats.append(format_info)
        
        return formats, yt.title
    except Exception as e:
        logger.error(f"Pytube error: {str(e)}")
        return None, None

def get_available_formats(url):
    """Try multiple methods to get video formats"""
    # First try with proxied API
    formats, title = get_video_info_proxied(url)
    if formats and title:
        return formats, title
    
    # If proxied API fails, try with yt-dlp
    try:
        headers = {'User-Agent': get_random_user_agent()}
        ydl_opts = {
            'quiet': True,
            'format': 'best',
            'extract_flat': True,
            'force_generic_extractor': False,
            'no_warnings': True,
            'http_headers': headers
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info and 'formats' in info:
                formats = []
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
                
                if formats:
                    formats.sort(key=lambda x: int(x['resolution'].replace('p', '')) if x['resolution'] != 'Auto' else 0, reverse=True)
                    return formats, info.get('title', 'Video')
    
    except Exception as e:
        logger.error(f"yt-dlp error: {str(e)}")
    
    # If yt-dlp fails, try pytube
    formats, title = get_video_info_pytube(url)
    if formats and title:
        return formats, title
    
    # If all methods fail, return basic format
    return [{
        'format_id': 'best',
        'ext': 'mp4',
        'resolution': 'Auto',
        'filesize': 0,
        'type': 'Auto Quality',
        'requires_ffmpeg': False,
        'quality_label': 'Auto'
    }], 'Video'

def download_with_proxy(url, quality='720p'):
    """Download a video using a proxy service"""
    video_id = extract_video_id(url)
    if not video_id:
        return None
    
    try:
        # Choose a proxy service that doesn't require youtube-dl-server
        headers = {'User-Agent': get_random_user_agent()}
        
        # Try using projectlounge proxy - this is public and doesn't require server dependency
        proxy_url = f"https://projectlounge.pw/ytdl/download?url=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3D{video_id}&format=mp4"
        
        response = requests.get(proxy_url, headers=headers, timeout=10, stream=True)
        
        if response.status_code == 200:
            # Save the content to a file
            file_path = os.path.join(DOWNLOAD_FOLDER, f"{video_id}_{quality}.mp4")
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            return file_path
    
    except Exception as e:
        logger.error(f"Proxy download error: {str(e)}")
    
    return None

def download_with_pytube(url, download_path, format_id=None):
    """Download video with pytube with additional options"""
    try:
        # Add random delay to avoid detection
        time.sleep(random.uniform(0.5, 2))
        
        yt = YouTube(url)
        yt.bypass_age_gate()
        
        # Try to get the specific format if requested
        if format_id and format_id != 'best':
            try:
                stream = yt.streams.get_by_itag(int(format_id))
                if stream:
                    return stream.download(output_path=download_path)
            except:
                pass  # Fall back to highest resolution if format not found
        
        # Get highest resolution stream
        stream = yt.streams.get_highest_resolution()
        if not stream:
            return None
        
        return stream.download(output_path=download_path)
    except Exception as e:
        logger.error(f"Pytube download error: {str(e)}")
        return None

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        try:
            url = request.form.get('url', '').strip()
            if not url:
                return render_template('index.html', error="Please enter a URL")
            
            formats, title = get_available_formats(url)
            return render_template('index.html', formats=formats, video_title=title, url=url)
        except Exception as e:
            logger.error(f"Error: {str(e)}")
            return render_template('index.html', error=str(e))
    
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    try:
        url = request.form.get('url')
        format_id = request.form.get('format', 'best')
        
        if not url:
            return render_template('index.html', error="Please provide a valid URL")
        
        # First try proxy download for reliability
        video_id = extract_video_id(url)
        if video_id:
            quality = '720p'
            if format_id != 'best':
                # Try to map format_id to quality
                format_map = {
                    '18': '360p',
                    '22': '720p',
                    '137': '1080p',
                    '248': '1080p',
                    '136': '720p'
                }
                quality = format_map.get(format_id, '720p')
                
            downloaded_file = download_with_proxy(url, quality)
            if downloaded_file and os.path.exists(downloaded_file):
                return send_file(
                    downloaded_file,
                    as_attachment=True,
                    download_name=os.path.basename(downloaded_file),
                    mimetype='video/mp4'
                )
        
        # If proxy fails, try yt-dlp
        try:
            ydl_opts = {
                'format': format_id,
                'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
                'quiet': False,
                'no_warnings': True,
                'http_headers': {
                    'User-Agent': get_random_user_agent()
                }
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info:
                    downloaded_file = ydl.prepare_filename(info)
                    if os.path.exists(downloaded_file):
                        return send_file(
                            downloaded_file,
                            as_attachment=True,
                            download_name=os.path.basename(downloaded_file),
                            mimetype='video/mp4'
                        )
        except Exception as e:
            logger.error(f"yt-dlp download error: {str(e)}")
        
        # If yt-dlp fails, try pytube
        downloaded_file = download_with_pytube(url, DOWNLOAD_FOLDER, format_id)
        if downloaded_file and os.path.exists(downloaded_file):
            return send_file(
                downloaded_file,
                as_attachment=True,
                download_name=os.path.basename(downloaded_file),
                mimetype='video/mp4'
            )
        
        return render_template('index.html', error="Failed to download video. Please try again with a different URL.")
        
    except Exception as e:
        logger.error(f"General error: {str(e)}")
        return render_template('index.html', error=f"An error occurred: {str(e)}")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
