# 🎵 Modern Python Music Player (Desktop & Online)

A sleek, modern dark-themed desktop music player written in Python using **Tkinter (ttk)**, **python-vlc**, **mutagen**, **yt-dlp**, and **Pillow (PIL)**. Supports local audio files (MP3, WAV, FLAC, OGG, M4A) and real-time online streaming (YouTube search, direct audio URLs) with unified playback controls.

---

## ✨ Features

- **🎧 Unified Playback**: Seamless playback for both local audio files and internet streams using LibVLC.
- **🎨 Sleek Dark Neon UI**: Custom dark glassmorphic palette (`#0F0F14` background, `#1B1B25` cards, `#7C5CFF` purple neon accent).
- **🌐 Online Streaming**: Search by track name or paste direct YouTube/audio stream links via `yt-dlp` in non-blocking background threads.
- **📂 Playlist Management**:
  - Add individual files or entire folders.
  - Live search / filter tracks.
  - Automatic session restore on startup (remembers your previous tracks).
  - Reorder, remove, or clear playlist with instant updates.
- **🎛️ Full Audio Controls**:
  - Play, Pause, Stop, Previous, Next.
  - Smooth interactive Seek / Scrub bar (drag or click to jump).
  - Clickable volume icon with mute/unmute toggle and live percentage.
  - Shuffle and Repeat modes (Off, Repeat One, Repeat All).
  - Automatic playback of next song upon track finish.
- **📊 Live Audio Spectrum Visualizer**:
  - 32-band dynamic animated equalizer with falling peak caps on canvas.
  - Animated frequency response with neon violet to electric cyan gradient.
- **🖼️ Album Art & Turntable Vinyl Display**:
  - Extracts embedded ID3 / FLAC album artwork with Pillow (smooth rounded corners).
  - Procedural vinyl turntable record fallback with grooves and neon spindle label.
- **⚡ Keyboard Shortcuts**:
  - `Space`: Play / Pause toggle
  - `Left` / `Right`: Previous / Next track
  - `Up` / `Down`: Volume Up / Down
  - `Ctrl + O`: Add audio files dialog
  - `Ctrl + A`: About dialog
- **💾 State Persistence**: Automatically preserves volume, shuffle, repeat mode, and last playlist in `settings.json`.

---

## 🛠️ Prerequisites & Installation

### 1. Install VLC Media Player (Required)
The audio engine depends on the **VLC Media Player (LibVLC 64-bit)** library:
- Download and install 64-bit VLC from the official website: [https://www.videolan.org/vlc/](https://www.videolan.org/vlc/)
- *Note:* The bitness of VLC (64-bit) must match your Python architecture (64-bit).

### 2. Clone or Download Project
```bash
cd "d:\B.Tech\B.TECH_SEM 7\Project\Music_Player_Py"
```

### 3. Install Python Dependencies
```bash
pip install -r requirements.txt
```
*(Dependencies: `python-vlc`, `mutagen`, `yt-dlp`, `Pillow`)*

---

## 🚀 Running the Application

Launch the music player with:
```bash
python main.py
```

---

## 📦 Building Standalone Windows Executable (.exe)

You can package the application into a standalone Windows `.exe` using **PyInstaller**:

1. Install PyInstaller:
   ```bash
   pip install pyinstaller
   ```
2. Build executable:
   ```bash
   pyinstaller --noconsole --onefile --name "MusicPlayer" main.py
   ```
3. The executable will be generated inside the `dist/` directory.

---

## 🏗️ Project Architecture

```
Music_Player_Py/
├── main.py                          # Complete application code (GUI + Audio Engine + Threading)
├── requirements.txt                 # Project dependencies
├── settings.json                    # User preferences & cached playlist state
├── README.md                        # Documentation & setup guide
└── Music_Player_Project_Guide.md    # Viva & presentation preparation notes
```

---

## 📜 License
Developed for Academic Project / Engineering Demonstration. Free to use and modify.
