from flask import Flask, render_template, request, send_file, jsonify, Response
import yt_dlp
import os
import json
import shutil
from typing import Dict, Any
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
import asyncio
import tempfile
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)

# Configuration
DOWNLOAD_PATH = os.path.join(tempfile.gettempdir(), "yayvd_downloads")
ALLOWED_DOMAINS = ('youtube.com', 'youtu.be')
DEFAULT_FORMAT = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]'

# Global state
download_status = {'state': 'idle'}

class VideoDownloader:
    def __init__(self, url: str, format_id: str):
        self.url = url
        self.format_id = format_id
        self.filename = ""
        self._executor = ThreadPoolExecutor(max_workers=2)
        
    @lru_cache(maxsize=32)
    def get_formats(self) -> list:
        """Extract available video formats with caching."""
        try:
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(self.url, download=False)
                return self._process_formats(info)
        except Exception as e:
            raise ValueError(f"Error fetching video formats: {str(e)}")

    def _process_formats(self, info: Dict[str, Any]) -> list:
        """Process and filter video formats with improved efficiency."""
        formats = [{
            'format_id': DEFAULT_FORMAT,
            'text': '🔥 Maximum Quality',
            'height': 9999,
            'filesize': self._get_format_size(info, DEFAULT_FORMAT)
        }]
        
        # Filter and sort formats in one pass
        video_formats = sorted(
            (f for f in info['formats'] 
             if f.get('vcodec') != 'none' and f.get('height')),
            key=lambda x: (x.get('height', 0), x.get('tbr', 0)),
            reverse=True
        )
        
        seen_heights = set()
        return formats + [
            self._create_format_option(fmt, fmt['height'], info)
            for fmt in video_formats
            if fmt['height'] not in seen_heights 
            and not seen_heights.add(fmt['height'])
        ]

    @lru_cache(maxsize=64)
    def _get_format_size(self, info: Dict[str, Any], format_id: str) -> str:
        """Calculate and format the file size with caching."""
        try:
            with yt_dlp.YoutubeDL({
                'format': format_id,
                'quiet': True,
                'no_warnings': True
            }) as ydl:
                format_info = ydl.extract_info(self.url, download=False)
                filesize = format_info.get('filesize') or format_info.get('filesize_approx', 0)
                
                if not filesize:
                    return ""
                    
                # Use integer division for faster computation
                if filesize < 1048576:  # 1024 * 1024
                    return f"{filesize // 1024:.1f}KB"
                elif filesize < 1073741824:  # 1024 * 1024 * 1024
                    return f"{filesize // 1048576:.1f}MB"
                return f"{filesize // 1073741824:.1f}GB"
        except:
            return ""

    def download(self) -> str:
        """Download the video and return the filename."""
        try:
            self._ensure_download_directory()
            
            ydl_opts = self._get_download_options()
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
                self.filename = ydl.prepare_filename(info)
                
                if not self.filename.endswith('.mp4'):
                    self.filename = f"{os.path.splitext(self.filename)[0]}.mp4"
                
                if not os.path.exists(self.filename):
                    raise ValueError("Download failed")
                
                return self.filename
                
        except Exception as e:
            self._cleanup()
            raise ValueError(f"Download error: {str(e)}")

    def _get_download_options(self) -> Dict[str, Any]:
        """Get yt-dlp download options."""
        return {
            'format': self.format_id,
            'outtmpl': os.path.join(DOWNLOAD_PATH, '%(title)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'merge_output_format': 'mp4',
            'progress_hooks': [self._progress_hook],
            'format_sort': ['res', 'ext:mp4:m4a', 'tbr', 'id'],
            'format_sort_force': True,
        }

    def _progress_hook(self, d: Dict[str, Any]) -> None:
        """Update download status."""
        global download_status
        if d['status'] == 'downloading':
            download_status['state'] = 'downloading'
        elif d['status'] == 'finished':
            download_status['state'] = 'processing'

    @staticmethod
    def _ensure_download_directory() -> None:
        """Ensure clean download directory exists."""
        if os.path.exists(DOWNLOAD_PATH):
            shutil.rmtree(DOWNLOAD_PATH)
        os.makedirs(DOWNLOAD_PATH)

    @staticmethod
    def _cleanup() -> None:
        """Clean up download directory."""
        if os.path.exists(DOWNLOAD_PATH):
            shutil.rmtree(DOWNLOAD_PATH)

def is_valid_url(url: str) -> bool:
    """Validate YouTube URL."""
    return any(domain in url for domain in ALLOWED_DOMAINS)

@app.route('/get-formats', methods=['POST'])
async def get_formats():
    try:
        url = request.form.get('video_url')
        if not is_valid_url(url):
            raise ValueError('Invalid YouTube URL')
            
        downloader = VideoDownloader(url, DEFAULT_FORMAT)
        formats = await asyncio.to_thread(downloader.get_formats)
        return jsonify({'formats': formats})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/check-status')
def check_status():
    return jsonify(download_status)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        try:
            url = request.form['video_url']
            format_id = request.form.get('format', DEFAULT_FORMAT)
            
            if not is_valid_url(url):
                raise ValueError('Invalid YouTube URL')

            downloader = VideoDownloader(url, format_id)
            filename = downloader.download()
            
            response = send_file(
                filename,
                as_attachment=True,
                download_name=os.path.basename(filename),
                mimetype='video/mp4'
            )
            
            @response.call_on_close
            def cleanup():
                try:
                    if os.path.exists(filename):
                        os.remove(filename)
                    if os.path.exists(DOWNLOAD_PATH):
                        shutil.rmtree(DOWNLOAD_PATH)
                except Exception:
                    pass

            download_status['state'] = 'done'
            return response

        except ValueError as e:
            return render_template('index.html', error=str(e))
        except Exception as e:
            return render_template('index.html', error=f"An error occurred: {str(e)}")

    try:
        # Example request
        response = requests.get('https://www.youtube.com')
        # Your existing code to handle the response
        ...
    except ValueError as e:
        return render_template('index.html', error=str(e))
    except Exception as e:
        return render_template('index.html', error=f"An error occurred: {str(e)}")

    return render_template('index.html')

app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
