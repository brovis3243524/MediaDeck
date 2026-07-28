#!/bin/bash
cd "$(dirname "$0")"

# Check if virtual environment exists, create if not
if [ ! -d "venv" ]; then
    echo "Setting up Python virtual environment for Bazzite..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install/update required dependencies quietly
echo "Checking dependencies..."
pip install --upgrade pip > /dev/null 2>&1
pip install PyQt6 yt-dlp imageio-ffmpeg > /dev/null 2>&1

# Launch the player
echo "Launching SoundCloud Turntable & HD Video Station..."
python3 soundcloud_player.py
