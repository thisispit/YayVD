from flask import Flask, render_template, request, send_file
import yt_dlp
import os
from datetime import datetime, timedelta
import re
import threading
import time

app = Flask(__name__)

DOWNLOAD_FOLDER = '/home/YOUR_USERNAME/yay/downloads'
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

deletion_queue = {}
download_cache = {}

def sanitize_filename(title):
    return re.sub(r'[\\/*?:"<>|]', "", title)

def is_ffmpeg_available():
    try:
        import subprocess
        subprocess.run(['ffmpeg', '-version'], capture_output=True)
        return True
    except:
        return False

def get_available_formats(url):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        formats = []
        
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
        
        formats = sorted(formats, 
                        key=lambda x: int(x['resolution'].replace('p', '')) if x['resolution'].replace('p', '').isdigit() else 0, 
                        reverse=True)
        
        seen = set()
        unique_formats = []
        for fmt in formats:
            if fmt['resolution'] not in seen:
                seen.add(fmt['resolution'])
                unique_formats.append(fmt)
                
        return unique_formats, info['title']

def delayed_file_delete(filepath, delay_seconds=60):
    def delete_job():
        time.sleep(delay_seconds)
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                print(f"Successfully deleted: {filepath} after {delay_seconds} seconds")
            if filepath in deletion_queue:
                del deletion_queue[filepath]
            keys_to_delete = [key for key, value in download_cache.items() if value['file'] == filepath]
            for key in keys_to_delete:
                del download_cache[key]
        except Exception as e:
            print(f"Error deleting file {filepath}: {e}")
    t = threading.Thread(target=delete_job)
    t.daemon = True
    t.start()
    deletion_queue[filepath] = t
    return t

def cleanup_old_files(max_age_minutes=30):
    now = datetime.now()
    for filename in os.listdir(DOWNLOAD_FOLDER):
        path = os.path.join(DOWNLOAD_FOLDER, filename)
        try:
            if path in deletion_queue:
                continue
            file_time = datetime.fromtimestamp(os.path.getctime(path))
            if (now - file_time) > timedelta(minutes=max_age_minutes):
                os.remove(path)
                print(f"Cleaned up old file: {path}")
        except Exception as e:
            print(f"Error cleaning up file {filename}: {e}")

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
    
    cleanup_old_files()
    
    cache_key = (youtube_url, format_id)
    if cache_key in download_cache:
        cached = download_cache[cache_key]
        if os.path.exists(cached['file']) and (datetime.now() - cached['time']).total_seconds() < 60:
            print("Serving cached file")
            return send_file(cached['file'], as_attachment=True, download_name=os.path.basename(cached['file']))
    
    sanitized_title = sanitize_filename(video_title)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"{sanitized_title}_{timestamp}.%(ext)s"
    output_path = os.path.join(DOWNLOAD_FOLDER, output_filename)
    
    postprocessors = [{
        'key': 'FFmpegMetadata',
        'add_metadata': True,
    }]
    
    ydl_opts = {
        'format': format_id,
        'outtmpl': output_path,
        'noplaylist': True,
        'quiet': False,
        'no_warnings': False,
        'postprocessors': [postprocessors]
    }
    
    downloaded_file = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=True)
            downloaded_file = ydl.prepare_filename(info)
            
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
            delayed_file_delete(downloaded_file, delay_seconds=60)
            
            return send_file(downloaded_file, as_attachment=True, download_name=os.path.basename(downloaded_file))
    except Exception as e:
        if downloaded_file and os.path.exists(downloaded_file):
            try:
                os.remove(downloaded_file)
            except:
                pass
        return render_template('index.html', error=str(e))

def init_app():
    if not os.path.exists(DOWNLOAD_FOLDER):
        os.makedirs(DOWNLOAD_FOLDER)
    cleanup_old_files()

init_app()

if __name__ == '__main__':
    app.run(debug=True)