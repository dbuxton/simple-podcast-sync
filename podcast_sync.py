#!/usr/bin/env python3
"""
Simple Podcast Sync CLI for Aftershokz XTRAINERZ
Syncs podcasts from Apple Podcasts library to the device with a nice TUI interface.
"""

import os
import sys
import shutil
import subprocess
import sqlite3
import urllib.parse
import re
import logging
from pathlib import Path
import tempfile

# Set up logging to a file
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filename="podcast_sync.log",
    filemode="w",  # Overwrite the log file each time
)
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import (
    Header,
    Footer,
    Static,
    ListView,
    ListItem,
    Button,
    Checkbox,
    Label,
)
from textual.binding import Binding
from rich.text import Text
from rich.console import Console

console = Console()


def sanitize_filename(text: str) -> str:
    """Sanitize a string to be a valid filename."""
    # Replace spaces with underscores
    text = text.replace(" ", "_")
    # Remove invalid filename characters
    text = re.sub(r'[<>:"/\\|?*]', "", text)
    # Remove leading/trailing whitespace/dots
    text = text.strip(" .")
    # Limit length to avoid issues with filesystems
    return text[:200]


class PodcastEpisode:
    """Represents a podcast episode with metadata."""

    def __init__(self, title: str, podcast: str, file_path: str, date_added: datetime):
        self.title = title
        self.podcast = podcast
        self.file_path = file_path
        self.date_added = date_added
        self.selected = False

    def __str__(self):
        return f"{self.podcast}: {self.title}"

    @property
    def filename(self) -> str:
        """Return a sanitized filename based on the episode title, preserving extension."""
        original_path = Path(self.file_path)
        extension = original_path.suffix
        # Ensure extension is not empty, default to .mp3 if it is
        if not extension:
            extension = ".mp3"
        sanitized_title = sanitize_filename(self.title)
        return f"{sanitized_title}{extension}"


class DeviceFile:
    """Represents a file on the XTRAINERZ device."""

    def __init__(self, name: str, path: str):
        self.name = name
        self.path = path
        self.keep = False  # Default: remove

    @property
    def size_mb(self) -> float:
        """Return the file size in megabytes."""
        try:
            # Use the full path to get the file stats
            return Path(self.path).stat().st_size / (1024 * 1024)
        except (FileNotFoundError, Exception):
            # If file not found or other error, return 0
            return 0.0

    def __str__(self):
        return self.name


class PodcastLibrary:
    """Handles Apple Podcasts library parsing."""

    def __init__(self):
        self.db_path = self._find_podcasts_database()

    def _find_podcasts_database(self) -> Optional[Path]:
        """Find the Apple Podcasts database file."""
        # Apple Podcasts stores data in Group Containers
        group_containers = Path.home() / "Library" / "Group Containers"

        # Look for the Podcasts group container
        for container in group_containers.glob("*podcasts*"):
            db_path = container / "Documents" / "MTLibrary.sqlite"
            if db_path.exists():
                return db_path

        # Alternative location
        alt_path = (
            Path.home()
            / "Library"
            / "Containers"
            / "com.apple.podcasts"
            / "Data"
            / "Documents"
            / "MTLibrary.sqlite"
        )
        if alt_path.exists():
            return alt_path

        return None

    def get_recent_podcasts(self, limit: int = 10) -> List[PodcastEpisode]:
        """Get the most recently downloaded podcast episodes."""
        if not self.db_path:
            print("[red]Apple Podcasts database not found![/red]")
            return []

        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # Query for downloaded episodes with podcast info
            # Use ZDOWNLOADDATE instead of ZDATEDOWNLOADED and check for ZASSETURL
            query = """
            SELECT 
                e.ZTITLE as episode_title,
                p.ZTITLE as podcast_title,
                e.ZASSETURL as file_url,
                e.ZDOWNLOADDATE as download_date,
                e.ZLASTDATEPLAYED as last_played
            FROM ZMTEPISODE e
            JOIN ZMTPODCAST p ON e.ZPODCAST = p.Z_PK
            WHERE e.ZASSETURL IS NOT NULL 
            AND e.ZASSETURL != ''
            AND e.ZDOWNLOADDATE IS NOT NULL
            ORDER BY e.ZDOWNLOADDATE DESC
            LIMIT ?
            """

            cursor.execute(query, (limit,))
            rows = cursor.fetchall()

            print(f"Found {len(rows)} downloaded episodes")

            episodes = []
            for row in rows:
                episode_title, podcast_title, file_url, download_date, last_played = row

                if file_url and file_url.startswith("file://"):
                    # Decode URL and convert to path
                    file_path = urllib.parse.unquote(file_url.replace("file://", ""))

                    print(f"Checking file: {file_path}")

                    # Check if file exists
                    if Path(file_path).exists():
                        # Convert Core Data timestamp to datetime
                        # Core Data uses seconds since 2001-01-01
                        if download_date:
                            date_added = datetime(2001, 1, 1) + timedelta(
                                seconds=download_date
                            )
                        else:
                            date_added = datetime.now()

                        episode = PodcastEpisode(
                            title=episode_title or "Unknown Episode",
                            podcast=podcast_title or "Unknown Podcast",
                            file_path=file_path,
                            date_added=date_added,
                        )
                        episodes.append(episode)
                        print(f"Added episode: {episode}")
                    else:
                        print(f"File not found: {file_path}")

            conn.close()
            print(f"Returning {len(episodes)} episodes")
            return episodes

        except Exception as e:
            print(f"[red]Error reading Apple Podcasts database: {e}[/red]")
            import traceback

            traceback.print_exc()
            return []


class DeviceManager:
    """Handles XTRAINERZ device operations."""

    def __init__(self):
        self.device_path = Path("/Volumes/XTRAINERZ")

    def is_connected(self) -> bool:
        """Check if the XTRAINERZ device is connected."""
        return self.device_path.exists() and self.device_path.is_dir()

    def get_device_files(self) -> List[DeviceFile]:
        """Get audio files currently on the device, searching recursively."""
        if not self.is_connected():
            return []

        device_files = []
        audio_extensions = {".mp3", ".m4a", ".aac", ".wav", ".flac"}

        try:
            for file_path in self.device_path.glob("**/*"):
                # Ignore hidden files (dotfiles) created by the device/macOS
                if (
                    file_path.is_file()
                    and not file_path.name.startswith(".")
                    and file_path.suffix.lower() in audio_extensions
                ):
                    relative_path = file_path.relative_to(self.device_path)
                    device_files.append(
                        DeviceFile(name=str(relative_path), path=str(file_path))
                    )
        except Exception as e:
            console.print(f"[red]Error reading files from device: {e}[/red]")

        return device_files

    def copy_episode(self, episode: PodcastEpisode) -> bool:
        """Copy an episode to the device, creating a 'Podcasts' folder if needed."""
        if not self.is_connected():
            console.print("[red]Error: Device not connected.[/red]")
            return False

        try:
            source = Path(episode.file_path)
            destination_dir = self.device_path / "Podcasts"
            destination_dir.mkdir(parents=True, exist_ok=True)

            destination = destination_dir / episode.filename

            console.print(
                f"\nProcessing '{episode.title}' at 2x speed (pitch preserved)"
            )
            console.print(f"  Source:      {source}")
            console.print(f"  Destination: {destination}")

            # Pre-flight: ensure ffmpeg is available
            if shutil.which("ffmpeg") is None:
                err_msg = "ffmpeg executable not found in PATH. Install ffmpeg before running the sync."
                console.print(f"[bold red]  Error: {err_msg}[/bold red]")
                logging.error(err_msg)
                return False

            # If the processed file already exists and matches size > 0 we can skip re-encoding
            if destination.exists() and destination.stat().st_size > 0:
                console.print("[blue]  Skipped: File already exists on device.[/blue]")
                logging.info("Skipped processing; file already present on device.")
                return True

            if not source.exists():
                console.print(f"[red]  Error: Source file not found.[/red]")
                logging.error("Source file not found: %s", source)
                return False

            # If destination already exists, remove it to ensure fresh conversion
            if destination.exists():
                try:
                    destination.unlink()
                except Exception as e:
                    console.print(
                        f"[red]  Error removing existing destination file: {e}[/red]"
                    )
                    return False

            # Create a temporary file for the processed audio
            with tempfile.NamedTemporaryFile(
                suffix=destination.suffix, delete=False
            ) as tmp_file:
                tmp_path = Path(tmp_file.name)

            # Use ffmpeg to speed up audio by 2x while preserving pitch
            ffmpeg_cmd = [
                "ffmpeg",
                "-i",
                str(source),
                "-filter:a",
                "atempo=2.0",
                "-vn",
                "-y",  # overwrite without asking if tmp_path exists
                str(tmp_path),
            ]

            logging.info("Running ffmpeg command: %s", " ".join(ffmpeg_cmd))
            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)

            if result.returncode != 0:
                console.print(
                    f"[red]  Error processing audio with ffmpeg: {result.stderr.strip()}[/red]"
                )
                logging.error("ffmpeg error: %s", result.stderr.strip())
                # Clean up temp file if it exists
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass
                return False

            # Move the processed file to the destination on the device
            try:
                # Use shutil.move to handle cross-device situations (copy then remove temp file)
                shutil.move(str(tmp_path), str(destination))
            except Exception as e:
                console.print(
                    f"[red]  Error copying processed file to device: {e}[/red]"
                )
                logging.exception(
                    "Error moving processed file to destination (cross-device?)"
                )
                # Clean up temp file if move failed
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass
                return False

            # Simple verification that the destination file now exists and is non-zero size
            if destination.exists() and destination.stat().st_size > 0:
                console.print(
                    f"[green]  Success: Processed and copied to device.[/green]"
                )
                return True
            else:
                console.print(
                    f"[bold red]  Error: Verification failed after copying.[/bold red]"
                )
                logging.error("Verification failed for destination: %s", destination)
                return False
        except Exception as e:
            console.print(
                f"[red]  Error processing/copying '{episode.title}' to device: {e}[/red]"
            )
            logging.exception("Unhandled exception in copy_episode")
            import traceback

            traceback.print_exc()
            return False

    def delete_file(self, device_file: DeviceFile) -> bool:
        """Delete a file from the device."""
        try:
            Path(device_file.path).unlink()
            console.print(f"[yellow]Deleted: {device_file.name}[/yellow]")
            return True
        except Exception as e:
            console.print(f"[red]Error deleting {device_file.name}: {e}[/red]")
            return False

    def unmount(self) -> bool:
        """Unmount the device."""
        try:
            result = subprocess.run(
                ["diskutil", "unmount", str(self.device_path)],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                console.print("[green]Device unmounted successfully[/green]")
                return True
            else:
                console.print(f"[red]Error unmounting device: {result.stderr}[/red]")
                return False
        except Exception as e:
            console.print(f"[red]Error unmounting device: {e}[/red]")
            return False


class PodcastListItem(ListItem):
    """A list item for a podcast episode."""

    def __init__(self, episode: PodcastEpisode):
        super().__init__()
        self.episode = episode

    def compose(self) -> ComposeResult:
        yield Checkbox(self.episode.title, value=self.episode.selected)
        yield Label(
            f"  {self.episode.podcast} - {self.episode.date_added.strftime('%Y-%m-%d')}"
        )

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Called when the checkbox is toggled."""
        self.episode.selected = event.value
        logging.info(
            f"Episode '{self.episode.title}' selection changed to {event.value}"
        )

    def on_click(self) -> None:
        """Called when the list item is clicked to toggle the checkbox."""
        checkbox = self.query_one(Checkbox)
        checkbox.toggle()


class DeviceFileListItem(ListItem):
    """A list item for a file on the device."""

    def __init__(self, device_file: DeviceFile):
        super().__init__()
        self.device_file = device_file

    def compose(self) -> ComposeResult:
        yield Checkbox(self.device_file.name, value=self.device_file.keep)
        yield Label(f"  {self.device_file.size_mb:.2f} MB")

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Called when the checkbox is toggled."""
        self.device_file.keep = event.value
        logging.info(
            f"Device file '{self.device_file.name}' keep status changed to {event.value}"
        )

    def on_click(self) -> None:
        """Called when the list item is clicked to toggle the checkbox."""
        checkbox = self.query_one(Checkbox)
        checkbox.toggle()


class EpisodeSelectionScreen(Container):
    """Screen for selecting episodes to copy to device."""

    def __init__(self, episodes: List[PodcastEpisode]):
        super().__init__()
        self.episodes = episodes

    def compose(self) -> ComposeResult:
        yield Static(
            "Select podcasts to copy to device (Space to toggle, Enter to continue):",
            classes="header",
        )

        items = []
        for i, episode in enumerate(self.episodes):
            items.append(PodcastListItem(episode))

        yield ListView(*items, id="episode-list")
        yield Button("Continue", id="continue-btn", variant="primary")


class DeviceFilesScreen(Container):
    """Screen for managing files on device."""

    def __init__(self, device_files: List[DeviceFile]):
        super().__init__()
        self.device_files = device_files

    def compose(self) -> ComposeResult:
        yield Static(
            "Manage files on device (Space to keep, default is remove):",
            classes="header",
        )

        items = []
        for device_file in self.device_files:
            items.append(DeviceFileListItem(device_file))

        yield ListView(*items, id="device-list")
        yield Button("Apply Changes", id="apply-btn", variant="primary")


class UnmountScreen(Container):
    """Screen for asking to unmount the device."""

    def compose(self) -> ComposeResult:
        yield Static("Sync complete. Unmount the device?", classes="header")
        yield Horizontal(
            Button("Unmount", id="unmount-btn", variant="primary"),
            Button("Keep Mounted", id="keep-mounted-btn"),
        )


class PodcastSyncApp(App):
    """Main application for podcast syncing."""

    CSS = """
    .header {
        padding: 1;
        background: $primary;
        color: $text;
        text-align: center;
    }

    ListView {
        height: 1fr;
        border: solid $primary;
    }

    Button {
        margin: 1;
    }
    
    Horizontal {
        align: center middle;
        height: auto;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("space", "toggle_item", "Toggle"),
        Binding("enter", "continue_action", "Continue"),
    ]

    def __init__(self):
        super().__init__()
        self.library = PodcastLibrary()
        self.device = DeviceManager()
        self.episodes = []
        self.device_files = []
        self.current_screen = "episodes"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(id="main-content")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the app when mounted."""
        if not self.device.is_connected():
            self.exit(
                message="XTRAINERZ device not found. Please connect the device and try again."
            )
            return

        self.episodes = self.library.get_recent_podcasts()
        if not self.episodes:
            self.exit(message="No recent podcasts found in Apple Podcasts library.")
            return

        self.show_episode_selection()

    def show_episode_selection(self):
        """Show the episode selection screen."""
        self.current_screen = "episodes"
        main_content = self.query_one("#main-content")
        main_content.remove_children()
        main_content.mount(EpisodeSelectionScreen(self.episodes))

    def show_device_files(self):
        """Show the device files management screen."""
        self.current_screen = "device"
        self.device_files = self.device.get_device_files()
        main_content = self.query_one("#main-content")
        main_content.remove_children()
        main_content.mount(DeviceFilesScreen(self.device_files))

    def show_unmount_screen(self):
        """Show the unmount confirmation screen."""
        self.current_screen = "unmount"
        main_content = self.query_one("#main-content")
        main_content.remove_children()
        main_content.mount(UnmountScreen())

    def action_toggle_item(self):
        """Toggle the selected item by toggling the checkbox of the highlighted item."""
        if self.current_screen == "episodes":
            list_view = self.query_one("#episode-list")
            if list_view.highlighted_child:
                list_view.highlighted_child.query_one(Checkbox).toggle()

        elif self.current_screen == "device":
            list_view = self.query_one("#device-list")
            if list_view.highlighted_child:
                list_view.highlighted_child.query_one(Checkbox).toggle()

    def action_continue_action(self):
        """Continue to next screen or apply changes."""
        logging.info(
            f"action_continue_action triggered on screen: {self.current_screen}"
        )
        try:
            if self.current_screen == "episodes":
                self.show_device_files()
            elif self.current_screen == "device":
                self.apply_changes()
        except Exception as e:
            logging.exception("Error in action_continue_action")
            self.exit(f"An error occurred: {e}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        logging.info(f"Button pressed: {event.button.id}")
        try:
            if event.button.id == "continue-btn":
                self.show_device_files()
            elif event.button.id == "apply-btn":
                self.apply_changes()
            elif event.button.id == "unmount-btn":
                self.device.unmount()
                self.exit("Device unmounted. Bye!")
            elif event.button.id == "keep-mounted-btn":
                self.exit("Sync complete. Device remains mounted.")
        except Exception as e:
            logging.exception("Error in on_button_pressed")
            self.exit(f"An error occurred: {e}")

    def apply_changes(self):
        """Apply the selected changes and then ask to unmount."""
        logging.info("apply_changes called")
        console.print("\n[bold]Applying changes...[/bold]")

        selected_episodes = [e for e in self.episodes if e.selected]
        logging.info(f"Found {len(selected_episodes)} selected episodes.")
        console.print(
            f"Found {len(selected_episodes)} out of {len(self.episodes)} total episodes selected for copying."
        )

        copied_count = 0
        if selected_episodes:
            for episode in selected_episodes:
                if self.device.copy_episode(episode):
                    copied_count += 1
        else:
            logging.warning("No episodes were selected to copy.")
            console.print("No episodes were selected to copy.")

        console.print(f"\nCopied {copied_count} new episodes.")

        deleted_count = 0
        for device_file in self.device_files:
            if not device_file.keep:
                if self.device.delete_file(device_file):
                    deleted_count += 1
        console.print(f"Deleted {deleted_count} old episodes.")
        logging.info(f"Sync complete. Copied: {copied_count}, Deleted: {deleted_count}")

        self.show_unmount_screen()


def main():
    """Main entry point."""
    app = PodcastSyncApp()
    app.run()


if __name__ == "__main__":
    main()
