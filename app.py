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
from pytube import YouTube
import json

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

DOWNLOAD_FOLDER = 'downloads'
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

def get_video_info_pytube(url):
    try:
        yt = YouTube(url)
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
    # First try with yt-dlp
    try:
        ydl_opts = {
            'quiet': True,
            'format': 'best',
            'extract_flat': True,
            'force_generic_extractor': False,
            'no_warnings': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
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
    if formats:
        return formats, title
    
    # If both fail, return basic format
    return [{
        'format_id': 'best',
        'ext': 'mp4',
        'resolution': 'Auto',
        'filesize': 0,
        'type': 'Auto Quality',
        'requires_ffmpeg': False,
        'quality_label': 'Auto'
    }], 'Video'

def download_with_pytube(url, download_path):
    try:
        yt = YouTube(url)
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
        
        # First try yt-dlp
        try:
            ydl_opts = {
                'format': format_id,
                'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
                'quiet': False,
                'no_warnings': True,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
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
        downloaded_file = download_with_pytube(url, DOWNLOAD_FOLDER)
        if downloaded_file and os.path.exists(downloaded_file):
            return send_file(
                downloaded_file,
                as_attachment=True,
                download_name=os.path.basename(downloaded_file),
                mimetype='video/mp4'
            )
        
        return render_template('index.html', error="Failed to download video. Please try again.")
        
    except Exception as e:
        logger.error(f"General error: {str(e)}")
        return render_template('index.html', error=f"An error occurred: {str(e)}")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
