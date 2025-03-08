# Yet Another YouTube Video Downloader (YAYVD)

A modern, user-friendly web application for downloading YouTube videos in various formats and qualities. Built with Flask and yt-dlp.

## Features

- 🎥 Download YouTube videos in multiple quality options (up to Best Quality)
- 🎵 Extract audio from videos
- 📱 Mobile-friendly interface
- 🔄 Smart format selection with recommended options
- 🎯 Preset quality options (1080p, 720p)
- 🚀 Fast downloads with caching
- 🛡️ Proxy support for enhanced reliability

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/yayvd.git
cd yayvd
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
python app.py
```

The application will be available at `http://localhost:8000`

## Environment Variables

- `PORT`: Server port (default: 8000)
- `HTTP_PROXY` / `HTTPS_PROXY`: Proxy configuration for enhanced reliability

## Deployment

### Railway Deployment

This application is compatible with Railway deployment. The application automatically detects Railway environment and configures itself accordingly.

To deploy on Railway:
1. Fork this repository
2. Create a new Railway project
3. Connect your GitHub repository
4. Deploy!

## Usage

1. Open the application in your web browser
2. Paste a YouTube video URL
3. Select your preferred format and quality
4. Click download and wait for the process to complete

## Features in Detail

### Quality Selection
- Best Quality: Highest available resolution with audio
- 1080p (Recommended): Full HD quality
- 720p: HD quality
- Custom qualities available based on source video

### Audio Downloads
- Extract audio in best quality
- Multiple audio format support

### Smart Caching
- Recently downloaded files are cached for 5 minutes
- Improves download speed for repeated requests

### Mobile Support
- Responsive design
- Optimized for mobile browsers
- Rotating user agents for better compatibility

## Technical Details

- Built with Flask (Python web framework)
- Uses yt-dlp for video extraction
- Implements thread-safe caching
- Automatic file cleanup
- Proxy support for enhanced reliability

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is open source and available under the MIT License.

## Disclaimer

This tool is for educational purposes only. Please respect YouTube's terms of service and content creators' rights when using this application.
