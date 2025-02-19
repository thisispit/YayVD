from flask import Flask, render_template, request, send_file, jsonify
import yt_dlp
import os

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        video_url = request.form['video_url']
        selected_format = request.form.get('format', '(bestvideo+bestaudio/best)[ext=mp4]')
        
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
                'merge_output_format': 'mp4',
                'format_sort': ['res', 'ext:mp4:m4a', 'tbr', 'id'],
                'format_sort_force': True,
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                }],
                # Updated FFmpeg options
                'keepvideo': True,
                'postprocessor_args': [
                    '-c:v', 'copy',
                    '-c:a', 'aac',
                    '-b:a', '192k'
                ],
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
            
            # Add best quality option at the top
            formats.append({
                'format_id': '(bestvideo+bestaudio/best)[ext=mp4]',
                'text': '🔥 Maximum Quality',
                'height': 9999
            })

            # Get video formats
            video_formats = []
            for f in info['formats']:
                if f.get('vcodec') != 'none' and f.get('height'):
                    video_formats.append(f)

            # Sort by height and add to formats list
            seen_heights = set()
            for fmt in sorted(video_formats, key=lambda x: (x.get('height', 0), x.get('tbr', 0)), reverse=True):
                height = fmt.get('height', 0)
                if height not in seen_heights:
                    seen_heights.add(height)
                    
                    # Create format string that ensures we get this exact height with best audio
                    format_id = f"(bestvideo[height={height}]+bestaudio/best[height={height}])[ext=mp4]"
                    
                    # Create quality label
                    quality_label = f"{height}p"
                    if height >= 2160:
                        quality_label += " 4K"
                    elif height >= 1440:
                        quality_label += " 2K"
                    elif height >= 1080:
                        quality_label += " FHD"
                    elif height >= 720:
                        quality_label += " HD"
                    
                    # Add bitrate if available
                    tbr = fmt.get('tbr', 0)
                    if tbr > 0:
                        quality_label += f" ({round(tbr/1000, 1)}Mbps)"
                    
                    formats.append({
                        'format_id': format_id,
                        'text': quality_label,
                        'height': height
                    })
            
            return jsonify({'formats': formats})
            
    except Exception as e:
        return jsonify({'error': str(e)}), 400

if __name__ == '__main__':
    app.run(debug=True)
