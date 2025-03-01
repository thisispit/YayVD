from flask import Flask, render_template, request, redirect, url_for, send_file
import yt_dlp
import os
from datetime import datetime
import re
import tempfile

app = Flask(__name__)

# Use a temporary directory for downloads to work with Railway's ephemeral filesystem
DOWNLOAD_FOLDER = tempfile.mkdtemp()

def sanitize_filename(title):
    """Remove invalid characters from filename"""
    return re.sub(r'[\\/*?:"<>|]', "", title)

def get_available_formats(url):
    """Get all available video formats including highest quality options"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'writeinfojson': False,
        'youtube_include_dash_manifest': True,  # Include DASH formats
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        formats = []
        
        # Process all available formats
        for f in info['formats']:
            # Skip formats without resolution info
            if not f.get('height') and not f.get('width'):
                continue
                
            # Create format info dictionary
            format_info = {
                'format_id': f['format_id'],
                'ext': f['ext'],
                'resolution': f"{f.get('height', '?')}p",
                'filesize': f.get('filesize', f.get('filesize_approx', 0)),
                'vcodec': f.get('vcodec', 'none'),
                'acodec': f.get('acodec', 'none'),
                'fps': f.get('fps', '?'),
                'tbr': f.get('tbr', 0),  # Total bit rate
            }
            
            # Add format type label
            if format_info['vcodec'] != 'none' and format_info['acodec'] != 'none':
                format_info['type'] = 'Video + Audio'
            elif format_info['vcodec'] != 'none' and format_info['acodec'] == 'none':
                format_info['type'] = 'Video only'
            elif format_info['vcodec'] == 'none' and format_info['acodec'] != 'none':
                format_info['type'] = 'Audio only'
            else:
                continue  # Skip if neither video nor audio
                
            formats.append(format_info)
        
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
        
        # Sort formats by resolution (height) - highest first
        formats = sorted(formats, 
                        key=lambda x: (
                            0 if x['resolution'] in ['Best quality', 'Best MP4', 'Up to 1080p'] else 
                            int(x['resolution'].replace('p', '')) if x['resolution'] != '?p' else 0
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
    
    sanitized_title = sanitize_filename(video_title)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
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
        }] if 'ffmpeg' not in format_id else [],  # Only add metadata if it doesn't require ffmpeg
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=True)
            downloaded_file = ydl.prepare_filename(info)
            
            # Check if file exists (for merged formats, the extension might have changed)
            if not os.path.exists(downloaded_file):
                # Try to find the file with a different extension
                base_path = os.path.splitext(downloaded_file)[0]
                for ext in ['.mp4', '.webm', '.mkv', '.m4a', '.mp3']:
                    possible_file = base_path + ext
                    if os.path.exists(possible_file):
                        downloaded_file = possible_file
                        break
            
            # Send file as attachment
            response = send_file(downloaded_file, as_attachment=True, download_name=os.path.basename(downloaded_file))
            
            # Clean up after sending to avoid filling up Railway's storage
            @response.call_on_close
            def cleanup():
                if os.path.exists(downloaded_file):
                    try:
                        os.remove(downloaded_file)
                    except:
                        pass
            
            return response
    except Exception as e:
        error_message = str(e)
        # If error is related to ffmpeg, suggest another format
        if 'ffmpeg' in error_message.lower():
            error_message += " Please choose another format that doesn't require post-processing."
        return render_template('index.html', error=error_message)

# Fix for Railway port binding
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)