from flask import Flask, render_template, request, send_file, jsonify, Response
import yt_dlp
import os
import json
import shutil
from typing import Dict, Any
import logging
import sys

app = Flask(__name__, 
    template_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates')))

# Configuration
DOWNLOAD_PATH = os.path.join(os.getcwd(), "downloads")  # Update download path for Railway
ALLOWED_DOMAINS = ('youtube.com', 'youtu.be')
DEFAULT_FORMAT = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]'

# Global state
download_status = {'state': 'idle'}

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

class VideoDownloader:
    def __init__(self, url: str, format_id: str):
        self.url = url
        self.format_id = format_id
        self.filename = ""
        
    def get_formats(self) -> list:
        """Extract available video formats."""
        try:
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(self.url, download=False)
                formats = self._process_formats(info)
                return formats
        except Exception as e:
            raise ValueError(f"Error fetching video formats: {str(e)}")

    def _process_formats(self, info: Dict[str, Any]) -> list:
        """Process and filter video formats."""
        # Best quality option
        formats = [{
            'format_id': DEFAULT_FORMAT,
            'text': '🔥 Maximum Quality',
            'height': 9999,
            'filesize': self._get_format_size(info, DEFAULT_FORMAT)
        }]
        
        video_formats = [f for f in info['formats'] 
                        if f.get('vcodec') != 'none' and f.get('height')]
        
        seen_heights = set()
        for fmt in sorted(video_formats, 
                         key=lambda x: (x.get('height', 0), x.get('tbr', 0)), 
                         reverse=True):
            height = fmt.get('height', 0)
            if height not in seen_heights:
                seen_heights.add(height)
                formats.append(self._create_format_option(fmt, height, info))
        
        return formats

    def _create_format_option(self, fmt: Dict[str, Any], height: int, info: Dict[str, Any]) -> Dict[str, Any]:
        """Create a format option with appropriate label and size."""
        quality_label = f"{height}p"
        if height >= 2160:
            quality_label += " 4K"
        elif height >= 1440:
            quality_label += " 2K"
        elif height >= 1080:
            quality_label += " FHD"
        elif height >= 720:
            quality_label += " HD"

        if tbr := fmt.get('tbr', 0):
            quality_label += f" ({round(tbr/1000, 1)}Mbps)"

        format_id = f"bestvideo[height={height}]+bestaudio/best[height={height}]"
        filesize = self._get_format_size(info, format_id)
        
        if filesize:
            quality_label += f" - {filesize}"

        return {
            'format_id': format_id,
            'text': quality_label,
            'height': height,
            'filesize': filesize
        }

    def _get_format_size(self, info: Dict[str, Any], format_id: str) -> str:
        """Calculate and format the file size for a given format."""
        try:
            with yt_dlp.YoutubeDL({
                'format': format_id,
                'quiet': True,
                'no_warnings': True
            }) as ydl:
                format_info = ydl.extract_info(self.url, download=False)
                filesize = format_info.get('filesize', 0)
                if not filesize:
                    filesize = format_info.get('filesize_approx', 0)
                
                if filesize:
                    # Convert to appropriate unit
                    if filesize < 1024 * 1024:  # Less than 1MB
                        return f"{filesize / 1024:.1f}KB"
                    elif filesize < 1024 * 1024 * 1024:  # Less than 1GB
                        return f"{filesize / (1024 * 1024):.1f}MB"
                    else:  # GB or larger
                        return f"{filesize / (1024 * 1024 * 1024):.1f}GB"
                return ""
        except:
            return ""

    def download(self) -> str:
        """Download the video and return the filename."""
        try:
            logger.info(f"Starting download for URL: {self.url}")
            self._ensure_download_directory()
            
            ydl_opts = self._get_download_options()
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                logger.info("Extracting video info...")
                info = ydl.extract_info(self.url, download=True)
                self.filename = ydl.prepare_filename(info)
                
                if not self.filename.endswith('.mp4'):
                    self.filename = f"{os.path.splitext(self.filename)[0]}.mp4"
                
                if not os.path.exists(self.filename):
                    logger.error("Download failed - File not found")
                    raise ValueError("Download failed")
                
                logger.info(f"Download completed: {self.filename}")
                return self.filename
                
        except Exception as e:
            logger.error(f"Download error: {str(e)}")
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
        try:
            if os.path.exists(DOWNLOAD_PATH):
                shutil.rmtree(DOWNLOAD_PATH)
            os.makedirs(DOWNLOAD_PATH, exist_ok=True)
        except Exception:
            # Fallback to current directory if /tmp is not accessible
            global DOWNLOAD_PATH
            DOWNLOAD_PATH = "downloads"
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
def get_formats():
    try:
        url = request.form.get('video_url')
        if not is_valid_url(url):
            raise ValueError('Invalid YouTube URL')
            
        downloader = VideoDownloader(url, DEFAULT_FORMAT)
        formats = downloader.get_formats()
        return jsonify({'formats': formats})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/check-status')
def check_status():
    return jsonify(download_status)

@app.route('/health')
def health():
    return jsonify({"status": "healthy"}), 200

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

    return render_template('index.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
