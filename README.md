# README.md

# YouTube Video Downloader

This is a Flask application that allows users to download videos from YouTube by providing a video URL. The application retrieves available video formats and enables users to select their preferred format for download.

## Project Structure

```
youtube-downloader
├── src
│   ├── static
│   │   └── style.css
│   ├── templates
│   │   ├── index.html
│   │   └── select_format.html
│   └── app.py
├── Procfile
├── requirements.txt
├── runtime.txt
└── README.md
```

## Requirements

- Python 3.x
- Flask
- yt-dlp

## Setup Instructions

1. Clone the repository:
   ```
   git clone <repository-url>
   cd youtube-downloader
   ```

2. Create a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. Install the required packages:
   ```
   pip install -r requirements.txt
   ```

## FFmpeg Setup for Windows Development

1. Download FFmpeg from https://github.com/BtbN/FFmpeg-Builds/releases
2. Extract the zip file
3. Copy the `ffmpeg.exe` from the `bin` folder to one of these locations:
   - `C:\ffmpeg\bin\ffmpeg.exe`
   - The project root directory
   - Add FFmpeg to your system PATH

## Running the Application

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python src/app.py
```

The application will automatically detect FFmpeg from the standard locations.

5. Open your browser and go to `http://127.0.0.1:5000` to access the application.

## Deployment

To deploy the application on Railway, ensure you have the following files configured:

- **Procfile**: Contains the command to run the application.
- **requirements.txt**: Lists all the dependencies.
- **runtime.txt**: Specifies the Python version.

## License

This project is licensed under the MIT License.