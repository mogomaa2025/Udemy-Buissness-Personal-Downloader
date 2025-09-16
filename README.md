
# Udemy Course Downloader GUI

A modern GUI application for downloading Udemy courses with support for encrypted videos, captions, and course materials.
This project is for eduictional purpose, don't download or share courses.

<img width="1015" height="820" alt="image" src="https://github.com/user-attachments/assets/8dbf2a63-84d0-4cc2-8c44-1c77ac4370ee" />


# IMPORTANT
1- install python : https://www.python.org/ftp/python/3.13.7/python-3.13.7-amd64.exe
2- use firefox extention : https://addons.mozilla.org/en-US/firefox/addon/widevine-l3-decrypter/?utm_source=addons.mozilla.org&utm_medium=referral&utm_content=search

## Quick Start

1. **Install Python 3** from [python.org](https://python.org/)
2. **Install dependencies:**

   **Windows:**
   ```bash
   @First-Tine-Library.cmd
   ```

   **Linux/macOS:**
   ```bash
   chmod +x setup.sh
   ./setup.sh
   ```
3. **Run the GUI:**

   **Windows:**
   ```bash
   @START.CMD
   ```

   **Linux/macOS:**
   ```bash
   chmod +x start.sh
   ./start.sh
   ```

## Optional External Tools

The following tools are **optional** but recommended for full functionality:

> [!NOTE]  
> These tools are not installed with pip and must be installed manually if you want full functionality.

-   [ffmpeg](https://www.ffmpeg.org/) - Required for video processing and combining
-   [aria2/aria2c](https://github.com/aria2/aria2/) - Recommended for faster downloads
-   [shaka-packager](https://github.com/shaka-project/shaka-packager/releases/latest) - Required for DRM video decryption
-   [yt-dlp](https://github.com/yt-dlp/yt-dlp/) - Can be installed via pip: `pip install yt-dlp`

**Note:** The application will show warnings if these tools are missing but will still run with limited functionality.

## Features

- Modern GUI interface with dark theme
- Support for encrypted Udemy videos
- Automatic video/audio combining
- Subtitle download and conversion
- Course material downloads (PDFs, presentations, etc.)
- Selective video download with preview
- Progress tracking and logging
