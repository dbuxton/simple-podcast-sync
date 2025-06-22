# Simple Podcast Sync for Aftershokz XTRAINERZ

A CLI tool to sync podcasts from your Apple Podcasts library to your Aftershokz XTRAINERZ device with a nice text-based user interface.

## Features

- 📱 Automatically detects connected XTRAINERZ device
- 🎧 Reads your Apple Podcasts library from SQLite database
- 📋 Shows last 10 downloaded podcasts for selection
- 🗂️ Manages existing files on device (keep/remove)
- 🔄 Copies selected episodes and removes unwanted files
- 💾 Safely unmounts device after completion
- ✨ Beautiful TUI interface with minimal typing required

## Requirements

- macOS (tested on modern versions)
- Python 3.7+
- Aftershokz XTRAINERZ device connected and mounted as "XTRAINERZ"
- Apple Podcasts app with downloaded episodes

## Installation

1. Clone or download this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Connect your Aftershokz XTRAINERZ device to your Mac
2. Ensure it's mounted (should appear as "XTRAINERZ" in Finder)
3. Test database access first:
   ```bash
   python test_podcasts.py
   ```
4. Run the sync tool:
   ```bash
   python podcast_sync.py
   ```

## How it works

1. **Episode Selection**: Browse your 10 most recent podcast downloads and select which ones to copy
2. **Device Management**: Review files currently on your device and choose which to keep or remove
3. **Sync**: The tool copies new episodes and removes unwanted files
4. **Cleanup**: Safely unmounts the device

## Controls

- **Arrow keys**: Navigate lists
- **Space**: Toggle selection (select/deselect episodes, keep/remove files)
- **Enter**: Continue to next screen or apply changes
- **Q**: Quit application

## Supported Audio Formats

- MP3 (.mp3)
- M4A (.m4a)
- AAC (.aac)
- WAV (.wav)

## Troubleshooting

- **Device not found**: Ensure XTRAINERZ is connected and mounted as "XTRAINERZ"
- **No podcasts found**: Check that Apple Podcasts has downloaded episodes
- **Database not found**: Run `python test_podcasts.py` to verify database access
- **Permission errors**: Ensure you have read access to Apple Podcasts database and write access to device

## Database Location

Apple Podcasts stores data in:
- `~/Library/Group Containers/[podcasts-container]/Documents/MTLibrary.sqlite`
- Or: `~/Library/Containers/com.apple.podcasts/Data/Documents/MTLibrary.sqlite`

The tool automatically searches for the correct location.

## Notes

- The tool reads from Apple Podcasts SQLite database
- Files are copied, not moved (originals remain in Apple Podcasts)
- Device is safely unmounted after sync completion
- Default behavior is to remove existing files unless explicitly kept
