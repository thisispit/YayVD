from flask import Flask, render_template, request, send_file, jsonify
import yt_dlp
import os

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        video_url = request.form['video_url']
        selected_format = request.form.get('format', 'bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4] / bv*+ba/b')
        
        try:
            # Validate URL
            if not video_url.startswith(('https://www.youtube.com/', 'https://youtu.be/')):
                raise ValueError('Invalid YouTube URL')

            # Create download directory if it doesn't exist
            download_path = "temp_downloads"
            os.makedirs(download_path, exist_ok=True)

            # Configure yt-dlp options
            ydl_opts = {
                'format': selected_format,
                'outtmpl': os.path.join(download_path, '%(title)s.%(ext)s'),
                'quiet': True,
                'no_warnings': True,
                'merge_output_format': 'mp4'
            }

            # Download the video
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                filename = ydl.prepare_filename(info)
                
                # Ensure the filename ends with .mp4
                if not filename.endswith('.mp4'):
                    base = os.path.splitext(filename)[0]
                    filename = base + '.mp4'

            # Verify the file was downloaded
            if not os.path.exists(filename):
                raise ValueError("Download failed")

            # Send file and then clean up
            response = send_file(
                filename,
                as_attachment=True,
                download_name=os.path.basename(filename),
                mimetype='video/mp4'
            )
            
            @response.call_on_close
            def cleanup():
                try:
                    os.remove(filename)
                    if not os.listdir(download_path):
                        os.rmdir(download_path)
                except:
                    pass

            return response

        except ValueError as e:
            return render_template('index.html', error=str(e))
        except Exception as e:
            return render_template('index.html', error=f"An error occurred: {str(e)}")

    return render_template('index.html')

@app.route('/get-formats', methods=['POST'])
def get_formats():
    video_url = request.form.get('video_url')
    
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            formats = []
            
            # Get video formats
            for f in info['formats']:
                # Only include formats that have both video and audio, or are video only with specific qualities
                if f.get('height') and f.get('ext') in ['mp4', 'webm']:
                    format_id = f['format_id']
                    height = f.get('height')
                    ext = f.get('ext')
                    vcodec = f.get('vcodec', '')
                    acodec = f.get('acodec', '')
                    filesize = f.get('filesize', 0)
                    
                    # Skip formats without video
                    if vcodec == 'none':
                        continue
                        
                    # Convert filesize to MB
                    filesize_mb = round(filesize / (1024 * 1024), 1) if filesize else 0
                    
                    # Create format description
                    quality_label = f"{height}p"
                    if height >= 1080:
                        quality_label += " HD"
                    elif height >= 720:
                        quality_label += " HD"
                    
                    has_audio = acodec != 'none'
                    format_text = f"{quality_label} ({ext})"
                    if filesize_mb > 0:
                        format_text += f" - {filesize_mb}MB"
                    
                    formats.append({
                        'format_id': f"{format_id}+ba/b" if not has_audio else format_id,
                        'text': format_text,
                        'height': height,
                        'has_audio': has_audio
                    })
            
            # Remove duplicates and sort by height
            unique_formats = []
            seen_heights = set()
            
            # Add a "Best quality" option
            unique_formats.append({
                'format_id': 'bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]',
                'text': 'Best Quality (MP4)',
                'height': 9999  # This ensures it appears at the top
            })
            
            for f in sorted(formats, key=lambda x: x['height'], reverse=True):
                if f['height'] not in seen_heights:
                    unique_formats.append(f)
                    seen_heights.add(f['height'])
            
            return jsonify({'formats': unique_formats})
            
    except Exception as e:
        return jsonify({'error': str(e)}), 400

if __name__ == '__main__':
    app.run(debug=True)
