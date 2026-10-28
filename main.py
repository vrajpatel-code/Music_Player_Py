"""
Music Player - main.py  (v1.0)
A feature-rich desktop music player built with Python, Tkinter (ttk) and python-vlc.

Features:
  - Dark neon-purple theme (Segoe UI font)
  - Playlist with title / artist / duration columns
  - Add Files, Add Folder, Remove Song, Clear Playlist
  - Play from Internet: YouTube search, YouTube URL, or direct MP3/stream URL
  - yt-dlp extracts best audio stream; runs in background thread (never freezes UI)
  - Play, Pause/Resume, Stop, Previous, Next controls
  - Volume slider & seek/progress bar (click or drag)
  - Shuffle and Repeat (off / one / all) modes
  - Double-click a song to play; auto-play next when track ends
  - "Now Playing" panel with album art (Pillow) or drawn music-note fallback
  - Live search / filter box
  - Save Playlist / Load Playlist (JSON) – online tracks included
  - Keyboard shortcuts: Space, Arrows, Ctrl+O, Ctrl+A (About)
  - Hover effects on all buttons
  - Status bar with live messages
  - Settings persistence: volume, shuffle, repeat, last playlist (settings.json)
  - About dialog
"""

import os
import sys
import json
import math
import time
import random
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ---------------------------------------------------------------------------
# Optional dependencies – import with friendly error messages
# ---------------------------------------------------------------------------
def _ensure_vlc_path():
    """
    python-vlc needs libvlc.dll on Windows.  It searches PATH and the
    working directory, but not the default VLC install folders.
    We add them to os.environ['PATH'] before importing vlc so the DLL
    is found automatically.
    """
    import ctypes.util
    candidates = [
        r"C:\Program Files\VideoLAN\VLC",
        r"C:\Program Files (x86)\VideoLAN\VLC",
    ]
    for folder in candidates:
        if os.path.isfile(os.path.join(folder, "libvlc.dll")):
            os.environ["PATH"] = folder + os.pathsep + os.environ.get("PATH", "")
            os.environ.setdefault("PYTHON_VLC_LIB",
                                  os.path.join(folder, "libvlc.dll"))
            os.environ.setdefault("PYTHON_VLC_MODULE_PATH",
                                  os.path.join(folder, "plugins"))
            return True
    return False

_vlc_found = _ensure_vlc_path()

try:
    import vlc
except (ImportError, OSError, FileNotFoundError) as _vlc_exc:
    _msg = (
        "VLC media player (64-bit) is required but was not found.\n\n"
        "Please install VLC from:\n"
        "  https://www.videolan.org/vlc/\n\n"
        "Use the same bit-width as Python (64-bit with 64-bit Python).\n"
        "After installing VLC, restart this application."
    )
    try:
        import tkinter.messagebox as _mb
        _mb.showerror("VLC Not Found", _msg)
    except Exception:
        print(_msg)
    sys.exit(1)

try:
    from mutagen import File as MutagenFile
    from mutagen.mp3 import MP3
    from mutagen.flac import FLAC
    from mutagen.id3 import ID3NoHeaderError
except ImportError:
    messagebox.showerror(
        "Missing library",
        "mutagen is not installed.\nRun:  pip install mutagen",
    )
    sys.exit(1)

# yt-dlp is optional at startup – we check at call-time and show a friendly error.
try:
    import yt_dlp  # noqa: F401  (just verify it's importable)
    _YTDLP_AVAILABLE = True
except ImportError:
    _YTDLP_AVAILABLE = False

# Pillow is optional – used for album art display.
try:
    from PIL import Image, ImageTk
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

# ---------------------------------------------------------------------------
# Colour palette & font constants
# ---------------------------------------------------------------------------
BG          = "#0D0D14"   # main canvas background
SURFACE     = "#171724"   # playlist / panel background
CARD_BG     = "#151522"   # center showcase card background
CARD_BORDER = "#28283E"   # subtle showcase border
SELECTED    = "#2B2844"   # selected / active row
ACCENT1     = "#7C5CFF"   # primary accent – neon purple
ACCENT2     = "#22D3EE"   # secondary accent – electric cyan
ACCENT3     = "#F43F5E"   # tertiary accent – coral pink
TEXT        = "#EDEDF5"   # primary text
MUTED       = "#9A9AB5"   # secondary / muted text
ERROR       = "#FF5C7A"   # error / remove colour
BORDER      = "#242436"   # subtle border / separator

FONT_TITLE   = ("Segoe UI", 16, "bold")
FONT_NORMAL  = ("Segoe UI", 11)
FONT_SMALL   = ("Segoe UI", 9)
FONT_BUTTON  = ("Segoe UI", 10, "bold")
FONT_MONO    = ("Consolas", 10)

# Path of the settings file (same folder as this script)
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")


# ---------------------------------------------------------------------------
# Helper – read metadata + album art from a local audio file with mutagen
# ---------------------------------------------------------------------------
def read_metadata(filepath: str) -> dict:
    """
    Return a dict with 'title', 'artist', 'duration' (float seconds) and
    'art_data' (raw bytes of cover art, or None).
    Falls back to filename-based title when tags are absent.
    """
    title    = os.path.splitext(os.path.basename(filepath))[0]
    artist   = "Unknown"
    duration = 0.0
    art_data = None

    try:
        audio = MutagenFile(filepath, easy=False)   # easy=False to access raw frames
        if audio is None:
            return {"title": title, "artist": artist,
                    "duration": duration, "art_data": art_data}

        # Read easy tags (ID3, Vorbis comment, etc.) via a second call
        easy = MutagenFile(filepath, easy=True)
        if easy:
            if easy.get("title"):
                title = easy["title"][0]
            if easy.get("artist"):
                artist = easy["artist"][0]

        # Duration
        if hasattr(audio, "info") and hasattr(audio.info, "length"):
            duration = audio.info.length

        # Album art – try ID3 APIC frames (MP3) and FLAC picture blocks
        try:
            from mutagen.id3 import ID3
            tags = ID3(filepath)
            apic = tags.getall("APIC")
            if apic:
                art_data = apic[0].data
        except Exception:
            pass

        if art_data is None:
            try:
                from mutagen.flac import FLAC as FlacFile
                flac = FlacFile(filepath)
                if flac.pictures:
                    art_data = flac.pictures[0].data
            except Exception:
                pass

        # MP4 / M4A cover art
        if art_data is None:
            try:
                from mutagen.mp4 import MP4
                mp4 = MP4(filepath)
                covr = mp4.tags.get("covr")
                if covr:
                    art_data = bytes(covr[0])
            except Exception:
                pass

    except Exception:
        pass  # use fallback values

    return {"title": title, "artist": artist,
            "duration": duration, "art_data": art_data}


def fmt_time(seconds: float) -> str:
    """Convert a float number of seconds to mm:ss string."""
    try:
        seconds = max(0, int(seconds))
        m, s = divmod(seconds, 60)
        return f"{m:02d}:{s:02d}"
    except Exception:
        return "00:00"


# ---------------------------------------------------------------------------
# Main application class
# ---------------------------------------------------------------------------
class MusicPlayer:
    """
    Full-featured music player using Tkinter (ttk) + python-vlc.
    All UI elements are contained in this class.
    """

    # Repeat mode constants
    REPEAT_OFF = "off"
    REPEAT_ONE = "one"
    REPEAT_ALL = "all"

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Music Player")
        self.root.geometry("980x640")
        self.root.minsize(840, 560)
        self.root.configure(bg=BG)

        # ── VLC ────────────────────────────────────────────────────────────
        self.vlc_instance = vlc.Instance("--no-xlib")   # suppress X11 on Linux
        self.media_player = self.vlc_instance.media_player_new()

        # ── Playlist state ─────────────────────────────────────────────────
        self.playlist: list[dict] = []
        self.filtered_indices: list[int] = []   # indices into self.playlist
        self.current_index: int = -1            # index in self.playlist
        self.is_playing: bool = False

        # ── Online loading flag (prevents concurrent fetches) ──────────────
        self._loading_online: bool = False

        # ── Playback mode ──────────────────────────────────────────────────
        self.shuffle: bool = False
        self.repeat_mode: str = self.REPEAT_OFF   # off | one | all

        # ── Seek dragging flag ─────────────────────────────────────────────
        self._seek_dragging: bool = False

        # ── Album art PhotoImage reference (must persist to prevent GC) ────
        self._art_photo: object = None

        # ── Spectrum Visualizer state ──────────────────────────────────────
        self._num_bars = 32
        self._bar_heights = [0.0] * self._num_bars
        self._bar_peaks = [0.0] * self._num_bars
        self._peak_decay = [0] * self._num_bars
        self._bar_colors = []
        for i in range(self._num_bars):
            t = i / max(1, self._num_bars - 1)
            # Gradient: Violet #7C5CFF -> Electric Cyan #22D3EE
            r = int(124 + (34 - 124) * t)
            g = int(92 + (211 - 92) * t)
            b = int(255 + (238 - 255) * t)
            self._bar_colors.append(f"#{r:02x}{g:02x}{b:02x}")

        # ── Volume & mute state ────────────────────────────────────────────
        self._is_muted = False
        self._prev_vol = 70

        # ── Build UI ───────────────────────────────────────────────────────
        self._apply_ttk_style()
        self._build_ui()

        # ── Restore settings (volume / shuffle / repeat / last playlist) ───
        self._load_settings()

        # ── Periodic update loops ──────────────────────────────────────────
        self._update_loop()
        self._anim_visualizer()

        # ── Keyboard shortcuts ─────────────────────────────────────────────
        self.root.bind("<space>",     lambda e: self.toggle_play_pause())
        self.root.bind("<Right>",     lambda e: self.play_next())
        self.root.bind("<Left>",      lambda e: self.play_prev())
        self.root.bind("<Up>",        lambda e: self._vol_up())
        self.root.bind("<Down>",      lambda e: self._vol_down())
        self.root.bind("<Control-o>", lambda e: self.add_files())
        self.root.bind("<Control-a>", lambda e: self.show_about())

        # ── Clean shutdown ─────────────────────────────────────────────────
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ======================================================================
    #  TTK Style (dark theme)
    # ======================================================================
    def _apply_ttk_style(self):
        """Apply the dark neon-purple theme to all ttk widgets."""
        style = ttk.Style(self.root)
        style.theme_use("clam")   # 'clam' allows the most overrides

        # ── General ────────────────────────────────────────────────────────
        style.configure(".",
            background=BG,
            foreground=TEXT,
            font=FONT_NORMAL,
            borderwidth=0,
            relief="flat",
        )

        # ── Treeview ───────────────────────────────────────────────────────
        style.configure("Playlist.Treeview",
            background=SURFACE,
            foreground=TEXT,
            fieldbackground=SURFACE,
            rowheight=28,
            borderwidth=0,
            font=FONT_NORMAL,
        )
        style.configure("Playlist.Treeview.Heading",
            background=BG,
            foreground=MUTED,
            relief="flat",
            font=FONT_SMALL,
        )
        style.map("Playlist.Treeview",
            background=[("selected", ACCENT1)],
            foreground=[("selected", TEXT)],
        )
        style.map("Playlist.Treeview.Heading",
            background=[("active", SURFACE)],
        )

        # ── Scrollbar ──────────────────────────────────────────────────────
        style.configure("Dark.Vertical.TScrollbar",
            background=SURFACE,
            troughcolor=BG,
            arrowcolor=MUTED,
            borderwidth=0,
            width=8,
        )
        style.map("Dark.Vertical.TScrollbar",
            background=[("active", SELECTED)],
        )

        # ── Standard button ────────────────────────────────────────────────
        style.configure("Dark.TButton",
            background=SURFACE,
            foreground=TEXT,
            padding=(10, 6),
            relief="flat",
            font=FONT_BUTTON,
            borderwidth=0,
        )
        style.map("Dark.TButton",
            background=[("active", SELECTED), ("pressed", ACCENT1)],
            foreground=[("active", TEXT)],
        )

        # ── Accent button (Play, etc.) ─────────────────────────────────────
        style.configure("Accent.TButton",
            background=ACCENT1,
            foreground=TEXT,
            padding=(14, 8),
            relief="flat",
            font=FONT_BUTTON,
            borderwidth=0,
        )
        style.map("Accent.TButton",
            background=[("active", "#9B7FFF"), ("pressed", "#5A40CC")],
        )

        # ── Toggle button (active state in accent2) ────────────────────────
        style.configure("Toggle.TButton",
            background=SURFACE,
            foreground=MUTED,
            padding=(10, 6),
            relief="flat",
            font=FONT_BUTTON,
            borderwidth=0,
        )
        style.map("Toggle.TButton",
            background=[("active", SELECTED)],
            foreground=[("active", ACCENT2)],
        )
        style.configure("ToggleOn.TButton",
            background=SELECTED,
            foreground=ACCENT2,
            padding=(10, 6),
            relief="flat",
            font=FONT_BUTTON,
        )

        # ── Scale (slider) ─────────────────────────────────────────────────
        style.configure("Dark.Horizontal.TScale",
            background=BG,
            troughcolor=SURFACE,
            sliderlength=14,
            sliderrelief="flat",
        )

        # ── Entry (search box) ─────────────────────────────────────────────
        style.configure("Dark.TEntry",
            fieldbackground=SURFACE,
            foreground=TEXT,
            insertcolor=TEXT,
            borderwidth=1,
            relief="flat",
            padding=(6, 4),
        )

        # ── Label ──────────────────────────────────────────────────────────
        style.configure("Dark.TLabel",
            background=BG,
            foreground=TEXT,
            font=FONT_NORMAL,
        )
        style.configure("Muted.TLabel",
            background=BG,
            foreground=MUTED,
            font=FONT_SMALL,
        )
        style.configure("Surface.TLabel",
            background=SURFACE,
            foreground=TEXT,
            font=FONT_NORMAL,
        )
        style.configure("SurfaceMuted.TLabel",
            background=SURFACE,
            foreground=MUTED,
            font=FONT_SMALL,
        )
        style.configure("Title.TLabel",
            background=SURFACE,
            foreground=TEXT,
            font=FONT_TITLE,
        )

        # ── Frame ──────────────────────────────────────────────────────────
        style.configure("Dark.TFrame",  background=BG)
        style.configure("Surface.TFrame", background=SURFACE)
        style.configure("Border.TFrame",
            background=BORDER,
        )

        # ── Separator ──────────────────────────────────────────────────────
        style.configure("TSeparator", background=BORDER)

        # ── Internet / Online accent button ───────────────────────────────
        style.configure("Internet.TButton",
            background="#163340",
            foreground=ACCENT2,
            padding=(10, 6),
            relief="flat",
            font=FONT_BUTTON,
            borderwidth=0,
        )
        style.map("Internet.TButton",
            background=[("active", "#1E4D5E"), ("pressed", "#0D2030")],
            foreground=[("active", ACCENT2)],
        )

        # ── Status bar label ──────────────────────────────────────────────
        style.configure("Status.TLabel",
            background="#13131C",
            foreground=MUTED,
            font=("Segoe UI", 9),
            padding=(8, 3),
        )

    # ======================================================================
    #  UI Construction
    # ======================================================================
    def _build_ui(self):
        """Build the complete UI layout."""
        # Root grid: two columns – playlist (left) | controls+player (right)
        # Row 0 = main content, Row 1 = status bar
        self.root.columnconfigure(0, weight=3, minsize=280)
        self.root.columnconfigure(1, weight=5)
        self.root.rowconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=0)

        self._build_left_panel()
        self._build_right_panel()
        self._build_status_bar()

    def _build_status_bar(self):
        """Thin status bar at the very bottom of the window (with colour support)."""
        self._status_var = tk.StringVar(value="Ready  •  No track loaded")
        self._status_lbl = ttk.Label(self.root, textvariable=self._status_var,
                                     style="Status.TLabel", anchor="w")
        self._status_lbl.grid(row=1, column=0, columnspan=2, sticky="ew")

    def _set_status(self, msg: str, error: bool = False):
        """Update the status bar. Error messages appear in the error colour."""
        self._status_var.set(msg)
        fg = ERROR if error else MUTED
        self._status_lbl.configure(foreground=fg)

    # ------------------------------------------------------------------
    #  LEFT PANEL – playlist + search + management buttons
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    #  LEFT PANEL – playlist + search + management buttons
    # ------------------------------------------------------------------
    def _build_left_panel(self):
        left = ttk.Frame(self.root, style="Surface.TFrame")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 1))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(2, weight=1)   # treeview expands

        # ── Header with Track Count Badge ──────────────────────────────
        hdr = ttk.Frame(left, style="Surface.TFrame")
        hdr.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        hdr.columnconfigure(0, weight=1)

        ttk.Label(hdr, text="🎵  Playlist", style="Title.TLabel",
                  font=("Segoe UI", 13, "bold")).grid(row=0, column=0, sticky="w")

        self.song_count_var = tk.StringVar(value="0 tracks")
        self.song_count_lbl = tk.Label(hdr, textvariable=self.song_count_var,
                                       bg="#222234", fg=MUTED,
                                       font=("Segoe UI", 8, "bold"),
                                       padx=8, pady=2)
        self.song_count_lbl.grid(row=0, column=1, sticky="e")

        # ── Search Box ────────────────────────────────────────────────
        search_frame = ttk.Frame(left, style="Surface.TFrame")
        search_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))
        search_frame.columnconfigure(1, weight=1)

        ttk.Label(search_frame, text="🔍", style="SurfaceMuted.TLabel",
                  font=("Segoe UI", 11)).grid(row=0, column=0, padx=(0, 4))

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_search_change)
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var,
                                 style="Dark.TEntry", font=FONT_NORMAL)
        search_entry.grid(row=0, column=1, sticky="ew")

        # ── Treeview ──────────────────────────────────────────────────
        tv_frame = ttk.Frame(left, style="Surface.TFrame")
        tv_frame.grid(row=2, column=0, sticky="nsew", padx=(10, 0), pady=(0, 6))
        tv_frame.columnconfigure(0, weight=1)
        tv_frame.rowconfigure(0, weight=1)

        cols = ("title", "artist", "duration")
        self.tree = ttk.Treeview(tv_frame, columns=cols, show="headings",
                                 style="Playlist.Treeview", selectmode="browse")
        self.tree.heading("title",    text="Title",    anchor="w")
        self.tree.heading("artist",   text="Artist",   anchor="w")
        self.tree.heading("duration", text="Time",     anchor="center")
        self.tree.column("title",    width=160, anchor="w",      stretch=True)
        self.tree.column("artist",   width=110, anchor="w",      stretch=True)
        self.tree.column("duration", width=55,  anchor="center", stretch=False)

        vsb = ttk.Scrollbar(tv_frame, orient="vertical",
                            command=self.tree.yview,
                            style="Dark.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        # Bindings
        self.tree.bind("<Double-1>", self._on_double_click)

        # Alternating row tags
        self.tree.tag_configure("odd",    background=SURFACE)
        self.tree.tag_configure("even",   background="#151520")
        self.tree.tag_configure("now",    background=SELECTED, foreground=ACCENT2)
        self.tree.tag_configure("online", foreground=ACCENT2)

        # ── Management buttons ────────────────────────────────────────
        mgmt = ttk.Frame(left, style="Surface.TFrame")
        mgmt.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 6))
        mgmt.columnconfigure((0, 1, 2, 3), weight=1)

        btn_cfg = [
            ("＋ Files",    self.add_files),
            ("📁 Folder",   self.add_folder),
            ("✕ Remove",   self.remove_song),
            ("🗑 Clear",   self.clear_playlist),
        ]
        for col, (label, cmd) in enumerate(btn_cfg):
            b = ttk.Button(mgmt, text=label, command=cmd, style="Dark.TButton")
            b.grid(row=0, column=col, padx=2, pady=2, sticky="ew")
            self._add_hover(b)

        # ── Play from Internet button (No Save/Load buttons below it!) ──
        inet_frame = ttk.Frame(left, style="Surface.TFrame")
        inet_frame.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 12))
        inet_frame.columnconfigure(0, weight=1)

        inet_btn = ttk.Button(inet_frame, text="🌐  Play from Internet",
                              command=self.play_from_internet,
                              style="Internet.TButton")
        inet_btn.grid(row=0, column=0, padx=2, pady=2, sticky="ew")
        self._add_hover(inet_btn)

    # ------------------------------------------------------------------
    #  RIGHT PANEL – Showcase + Animated Spectrum Visualizer + Controls
    # ------------------------------------------------------------------
    def _build_right_panel(self):
        right = ttk.Frame(self.root, style="Dark.TFrame")
        right.grid(row=0, column=1, sticky="nsew", padx=12, pady=10)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=0)   # Top Bar
        right.rowconfigure(1, weight=1)   # Hero Showcase Card
        right.rowconfigure(2, weight=0)   # Progress / Seek Bar
        right.rowconfigure(3, weight=0)   # Transport Controls
        right.rowconfigure(4, weight=0)   # Volume & Mode Toggles

        # ── Top Bar & Showcase Card ───────────────────────────────────
        self._build_now_playing(right)

        # ── Progress bar ──────────────────────────────────────────────
        self._build_progress(right)

        # ── Transport controls ────────────────────────────────────────
        self._build_transport(right)

        # ── Volume + mode toggles ─────────────────────────────────────
        self._build_volume_modes(right)

    def _build_now_playing(self, parent):
        # ── Top bar: Status indicator & About button ───────────────────
        top_bar = tk.Frame(parent, bg=BG)
        top_bar.grid(row=0, column=0, sticky="ew", padx=4, pady=(0, 6))
        top_bar.columnconfigure(0, weight=1)

        self.live_indicator_var = tk.StringVar(value="● PLAYER STANDBY")
        self.live_indicator_lbl = tk.Label(top_bar, textvariable=self.live_indicator_var,
                                           bg=BG, fg=MUTED, font=("Segoe UI", 9, "bold"))
        self.live_indicator_lbl.grid(row=0, column=0, sticky="w")

        about_btn = ttk.Button(top_bar, text="ℹ About",
                               command=self.show_about,
                               style="Dark.TButton")
        about_btn.grid(row=0, column=1, sticky="e")
        self._add_hover(about_btn)

        # ── Hero Center Showcase Card ─────────────────────────────────
        card = tk.Frame(parent, bg=CARD_BG,
                        highlightbackground=CARD_BORDER,
                        highlightthickness=1, bd=0)
        card.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 8))
        card.columnconfigure(0, weight=1)
        card.rowconfigure(0, weight=1)

        # Upper container: Album Art + Track Information
        top_info = tk.Frame(card, bg=CARD_BG, padx=20, pady=16)
        top_info.pack(fill="both", expand=True)
        top_info.columnconfigure(1, weight=1)

        # 150x150 Album Art / Vinyl Turntable Canvas
        self.art_canvas = tk.Canvas(top_info, width=150, height=150,
                                    bg=CARD_BG, highlightthickness=0)
        self.art_canvas.grid(row=0, column=0, rowspan=5, padx=(0, 20), pady=4, sticky="nw")
        self._draw_music_icon(self.art_canvas)

        # Track metadata container
        meta = tk.Frame(top_info, bg=CARD_BG)
        meta.grid(row=0, column=1, rowspan=5, sticky="nsew")
        meta.columnconfigure(0, weight=1)

        # Badges row: [ SOURCE BADGE ] [ TRACK COUNTER ]
        badges = tk.Frame(meta, bg=CARD_BG)
        badges.pack(anchor="w", pady=(2, 6))

        self.now_badge_var = tk.StringVar(value="READY")
        self.badge_lbl = tk.Label(badges, textvariable=self.now_badge_var,
                                  bg="#252538", fg=ACCENT2,
                                  font=("Segoe UI", 8, "bold"),
                                  padx=8, pady=3)
        self.badge_lbl.pack(side="left", padx=(0, 6))

        self.track_counter_var = tk.StringVar(value="0 / 0 tracks")
        self.counter_lbl = tk.Label(badges, textvariable=self.track_counter_var,
                                    bg="#1E1E2E", fg=MUTED,
                                    font=("Segoe UI", 8),
                                    padx=8, pady=3)
        self.counter_lbl.pack(side="left")

        # Track Title
        self.now_title_var = tk.StringVar(value="No track selected")
        self.title_lbl = tk.Label(meta, textvariable=self.now_title_var,
                                  bg=CARD_BG, fg=TEXT,
                                  font=("Segoe UI", 15, "bold"),
                                  wraplength=340, justify="left", anchor="w")
        self.title_lbl.pack(anchor="w", pady=(4, 2), fill="x")

        # Track Artist
        self.now_artist_var = tk.StringVar(value="Select or double-click a song to play")
        self.artist_lbl = tk.Label(meta, textvariable=self.now_artist_var,
                                   bg=CARD_BG, fg=MUTED,
                                   font=("Segoe UI", 11),
                                   wraplength=340, justify="left", anchor="w")
        self.artist_lbl.pack(anchor="w", pady=(0, 6), fill="x")

        # Audio Specification Tag
        self.now_spec_var = tk.StringVar(value="Hardware Accelerated Audio Engine")
        self.spec_lbl = tk.Label(meta, textvariable=self.now_spec_var,
                                 bg=CARD_BG, fg="#666680",
                                 font=("Segoe UI", 9),
                                 anchor="w")
        self.spec_lbl.pack(anchor="w", pady=(2, 0))

        # ── Lower Container: Animated Spectrum Visualizer ─────────────
        vis_container = tk.Frame(card, bg="#111119",
                                 highlightbackground="#222234",
                                 highlightthickness=1, bd=0, padx=12, pady=6)
        vis_container.pack(fill="x", side="bottom", padx=12, pady=(0, 12))

        vis_header = tk.Frame(vis_container, bg="#111119")
        vis_header.pack(fill="x", pady=(0, 2))

        tk.Label(vis_header, text="LIVE AUDIO SPECTRUM",
                 bg="#111119", fg="#686885",
                 font=("Segoe UI", 8, "bold")).pack(side="left")

        self.vis_bands_lbl = tk.Label(vis_header, text="32 BANDS",
                                      bg="#111119", fg="#484862",
                                      font=("Segoe UI", 7, "bold"))
        self.vis_bands_lbl.pack(side="right")

        self.vis_canvas = tk.Canvas(vis_container, height=52, bg="#111119",
                                    highlightthickness=0)
        self.vis_canvas.pack(fill="x", expand=True)

    def _draw_music_icon(self, canvas: tk.Canvas):
        """Draw a modern stylized vinyl turntable record on the canvas."""
        canvas.delete("all")
        cx, cy = 75, 75
        # Outer disc body
        canvas.create_oval(cx - 68, cy - 68, cx + 68, cy + 68,
                          fill="#13131C", outline="#252538", width=2)
        # Turntable grooves
        for r in (58, 48, 38):
            canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                              outline="#1C1C2A", width=1)
        # Center label disc in neon purple
        canvas.create_oval(cx - 24, cy - 24, cx + 24, cy + 24,
                          fill=ACCENT1, outline="#9B7FFF", width=2)
        # Center spindle hole
        canvas.create_oval(cx - 7, cy - 7, cx + 7, cy + 7,
                          fill=CARD_BG, outline="")
        # Minimal musical note symbol
        canvas.create_oval(cx - 3, cy + 1, cx + 3, cy + 6, fill="#FFFFFF", outline="")
        canvas.create_line(cx + 2, cy - 5, cx + 2, cy + 3, fill="#FFFFFF", width=2)
        canvas.create_line(cx + 2, cy - 5, cx + 7, cy - 3, fill="#FFFFFF", width=2)

    def _update_art_canvas(self, art_data: bytes | None):
        """
        Display album art on the Now Playing canvas with rounded corners.
        If art_data is None or Pillow is unavailable, fall back to the
        stylized vinyl turntable record.
        """
        if art_data and _PIL_AVAILABLE:
            try:
                from PIL import Image, ImageTk, ImageDraw
                import io
                img = Image.open(io.BytesIO(art_data)).convert("RGBA")
                size = 150
                img = img.resize((size, size), Image.LANCZOS)

                # Smooth rounded corners mask
                mask = Image.new("L", (size, size), 0)
                draw = ImageDraw.Draw(mask)
                draw.rounded_rectangle((0, 0, size, size), radius=14, fill=255)

                rounded = Image.new("RGBA", (size, size), (0, 0, 0, 0))
                rounded.paste(img, (0, 0), mask)

                self._art_photo = ImageTk.PhotoImage(rounded)
                self.art_canvas.delete("all")
                self.art_canvas.create_image(75, 75, image=self._art_photo)
                return
            except Exception:
                pass
        self._art_photo = None
        self._draw_music_icon(self.art_canvas)

    def _anim_visualizer(self):
        """Draw animated equalizer spectrum bars with falling peak caps."""
        if not hasattr(self, "vis_canvas") or not self.vis_canvas.winfo_exists():
            return

        c = self.vis_canvas
        w = c.winfo_width()
        h = c.winfo_height()

        if w > 20 and h > 10:
            c.delete("all")
            num = self._num_bars
            gap = 3
            bar_w = max(2, (w - (num - 1) * gap) / num)
            is_active = self.is_playing and (self.media_player.get_state() == vlc.State.Playing)
            t = time.time() * 7

            for i in range(num):
                if is_active:
                    # Simulated frequency dynamics (higher energy on bass, dynamic melody on mids/treble)
                    bass_factor = 1.0 - (i / num) * 0.45
                    wave = (math.sin(t * (0.85 + 0.08 * (i % 6)) + i * 0.38) + 1.0) * 0.5
                    noise = random.random() * 0.35
                    target = min(1.0, max(0.08, (wave * 0.65 + noise) * bass_factor))
                    self._bar_heights[i] += (target - self._bar_heights[i]) * 0.35
                else:
                    self._bar_heights[i] *= 0.82

                # Peak cap calculation
                val = self._bar_heights[i]
                if val > self._bar_peaks[i]:
                    self._bar_peaks[i] = val
                    self._peak_decay[i] = 8   # hold peak for 8 frames
                else:
                    if self._peak_decay[i] > 0:
                        self._peak_decay[i] -= 1
                    else:
                        self._bar_peaks[i] = max(0.0, self._bar_peaks[i] - 0.04)

                bar_h = max(2, int(val * (h - 8)))
                x0 = int(i * (bar_w + gap))
                x1 = int(x0 + bar_w)
                y1 = h - 2
                y0 = max(4, y1 - bar_h)

                color = self._bar_colors[i]
                c.create_rectangle(x0, y0, x1, y1, fill=color, outline="")

                # Peak hold indicator
                peak_y = max(2, int(h - 2 - (self._bar_peaks[i] * (h - 8))))
                c.create_line(x0, peak_y, x1, peak_y, fill="#FFFFFF", width=2)

        self.root.after(45, self._anim_visualizer)

    def _build_progress(self, parent):
        prog_frame = ttk.Frame(parent, style="Dark.TFrame")
        prog_frame.grid(row=2, column=0, sticky="ew", padx=4, pady=(4, 2))
        prog_frame.columnconfigure(1, weight=1)

        self.cur_time_var = tk.StringVar(value="00:00")
        self.tot_time_var = tk.StringVar(value="00:00")

        ttk.Label(prog_frame, textvariable=self.cur_time_var,
                  style="Muted.TLabel", font=FONT_MONO
                  ).grid(row=0, column=0, padx=(0, 8))

        # Canvas-based progress bar (supports click + drag)
        self.seek_canvas = tk.Canvas(prog_frame, height=18, bg=BG,
                                     highlightthickness=0, cursor="hand2")
        self.seek_canvas.grid(row=0, column=1, sticky="ew")
        self.seek_canvas.bind("<ButtonPress-1>",   self._seek_press)
        self.seek_canvas.bind("<B1-Motion>",        self._seek_drag)
        self.seek_canvas.bind("<ButtonRelease-1>",  self._seek_release)
        self.seek_canvas.bind("<Configure>",        lambda e: self._draw_seek_bar())

        ttk.Label(prog_frame, textvariable=self.tot_time_var,
                  style="Muted.TLabel", font=FONT_MONO
                  ).grid(row=0, column=2, padx=(8, 0))

        self._seek_ratio = 0.0   # 0.0–1.0, updated in loop

    def _draw_seek_bar(self, ratio: float = None):
        """Redraw the custom seek/progress bar canvas."""
        if ratio is None:
            ratio = self._seek_ratio
        c = self.seek_canvas
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 2:
            return
        c.delete("all")
        track_y = h // 2
        r = 3   # track radius
        # Background track
        self._rounded_rect(c, 0, track_y - r, w, track_y + r, r, fill="#232333", outline="")
        # Filled portion
        fill_w = max(0, min(w, int(w * ratio)))
        if fill_w > 0:
            self._rounded_rect(c, 0, track_y - r, fill_w, track_y + r, r,
                               fill=ACCENT1, outline="")
        # Thumb
        thumb_x = fill_w
        c.create_oval(thumb_x - 6, track_y - 6, thumb_x + 6, track_y + 6,
                      fill="#FFFFFF", outline=ACCENT1, width=2)

    @staticmethod
    def _rounded_rect(canvas, x1, y1, x2, y2, r, **kw):
        """Draw a rectangle with rounded corners on a canvas."""
        points = [
            x1 + r, y1,   x2 - r, y1,
            x2,     y1,   x2,     y1 + r,
            x2,     y2 - r, x2,   y2,
            x2 - r, y2,   x1 + r, y2,
            x1,     y2,   x1,     y2 - r,
            x1,     y1 + r, x1,   y1,
        ]
        return canvas.create_polygon(points, smooth=True, **kw)

    def _seek_press(self, event):
        self._seek_dragging = True
        self._do_seek(event.x)

    def _seek_drag(self, event):
        if self._seek_dragging:
            self._do_seek(event.x)

    def _seek_release(self, event):
        self._seek_dragging = False
        self._do_seek(event.x)

    def _do_seek(self, x: int):
        """Seek the media player to the position represented by pixel x."""
        w = self.seek_canvas.winfo_width()
        if w < 1:
            return
        ratio = max(0.0, min(1.0, x / w))
        self._seek_ratio = ratio
        self._draw_seek_bar(ratio)
        duration_ms = self.media_player.get_length()
        if duration_ms > 0:
            target_ms = int(duration_ms * ratio)
            self.media_player.set_time(target_ms)

    def _build_transport(self, parent):
        """Previous / Play / Pause / Stop / Next buttons."""
        ctrl = ttk.Frame(parent, style="Dark.TFrame")
        ctrl.grid(row=3, column=0, sticky="ew", padx=4, pady=8)
        ctrl.columnconfigure((0, 1, 2, 3, 4), weight=1)

        btns = [
            ("⏮",  self.play_prev,          "Dark.TButton"),
            ("▶",   self.play_current,       "Accent.TButton"),
            ("⏸",  self.toggle_play_pause,  "Dark.TButton"),
            ("⏹",  self.stop,               "Dark.TButton"),
            ("⏭",  self.play_next,          "Dark.TButton"),
        ]
        self.play_btn  = None
        self.pause_btn = None

        for col, (label, cmd, style) in enumerate(btns):
            b = ttk.Button(ctrl, text=label, command=cmd, style=style, width=4)
            b.grid(row=0, column=col, padx=4, pady=2)
            self._add_hover(b)
            if label == "▶":
                self.play_btn  = b
            elif label == "⏸":
                self.pause_btn = b

    def _build_volume_modes(self, parent):
        """Volume slider + mute toggle + shuffle + repeat toggles."""
        vm = ttk.Frame(parent, style="Dark.TFrame")
        vm.grid(row=4, column=0, sticky="ew", padx=4, pady=(2, 6))
        vm.columnconfigure(2, weight=1)

        # Clickable volume icon (toggles mute/unmute)
        self.vol_icon_lbl = tk.Label(vm, text="🔊", bg=BG, fg=TEXT,
                                     font=("Segoe UI", 12), cursor="hand2")
        self.vol_icon_lbl.grid(row=0, column=0, padx=(0, 4))
        self.vol_icon_lbl.bind("<Button-1>", lambda e: self._toggle_mute())

        self.vol_var = tk.IntVar(value=70)
        vol_scale = ttk.Scale(vm, from_=0, to=100,
                              orient="horizontal",
                              variable=self.vol_var,
                              command=self._on_volume_change,
                              style="Dark.Horizontal.TScale",
                              length=110)
        vol_scale.grid(row=0, column=1, sticky="w", padx=(0, 6))
        self.media_player.audio_set_volume(70)

        # Volume percentage readout
        self.vol_pct_var = tk.StringVar(value="70%")
        tk.Label(vm, textvariable=self.vol_pct_var, bg=BG, fg=MUTED,
                 font=("Consolas", 9)).grid(row=0, column=2, sticky="w", padx=(0, 16))

        # Shuffle button
        self.shuffle_btn = ttk.Button(vm, text="⇌ Shuffle",
                                      command=self._toggle_shuffle,
                                      style="Toggle.TButton")
        self.shuffle_btn.grid(row=0, column=3, padx=4)
        self._add_hover(self.shuffle_btn)

        # Repeat button
        self.repeat_btn = ttk.Button(vm, text="↺ Repeat",
                                     command=self._cycle_repeat,
                                     style="Toggle.TButton")
        self.repeat_btn.grid(row=0, column=4, padx=4)
        self._add_hover(self.repeat_btn)

    def _toggle_mute(self):
        """Toggle mute on/off."""
        if self._is_muted:
            self._is_muted = False
            self.vol_var.set(self._prev_vol)
            self._on_volume_change(self._prev_vol)
        else:
            self._prev_vol = max(5, self.vol_var.get())
            self._is_muted = True
            self.vol_var.set(0)
            self._on_volume_change(0)

    # ======================================================================
    #  Hover helpers
    # ======================================================================
    def _add_hover(self, widget: ttk.Button):
        """Bind enter/leave events to simulate hover glow on a button."""
        # We rely on the ttk.Style map's "active" state for most effects,
        # but we also store the original style to restore on leave.
        orig_style = widget.cget("style")

        def on_enter(e):
            widget.state(["active"])

        def on_leave(e):
            widget.state(["!active"])

        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)

    # ======================================================================
    #  Periodic update loop  (called every 500 ms via root.after)
    # ======================================================================
    def _update_loop(self):
        """Update progress bar, time labels and check for track end."""
        try:
            state  = self.media_player.get_state()
            length = self.media_player.get_length()   # ms
            pos_ms = self.media_player.get_time()     # ms

            if length > 0 and not self._seek_dragging:
                ratio = max(0.0, min(1.0, pos_ms / length))
                self._seek_ratio = ratio
                self._draw_seek_bar(ratio)
                self.cur_time_var.set(fmt_time(pos_ms / 1000))
                self.tot_time_var.set(fmt_time(length / 1000))

            # Check if track ended (vlc.State.Ended == 6)
            if state == vlc.State.Ended and self.is_playing:
                self._on_track_end()

        except Exception:
            pass

        self.root.after(500, self._update_loop)

    def _on_track_end(self):
        """Handle natural end of track according to repeat mode."""
        self.is_playing = False

        if self.repeat_mode == self.REPEAT_ONE:
            self.play_current()
        elif self.repeat_mode == self.REPEAT_ALL or self.shuffle:
            self.play_next()
        elif self.current_index < len(self.playlist) - 1:
            self.play_next()
        # else: last track, no repeat – stay stopped

    # ======================================================================
    #  Playback controls
    # ======================================================================
    def play_at_index(self, playlist_idx: int):
        """Load and play the track at *playlist_idx* (index in self.playlist)."""
        if not (0 <= playlist_idx < len(self.playlist)):
            return

        self.current_index = playlist_idx
        track = self.playlist[playlist_idx]
        path  = track["path"]

        try:
            media = self.vlc_instance.media_new(path)
            self.media_player.set_media(media)
            self.media_player.play()
            self.is_playing = True

            # Update Now Playing panel
            self.now_title_var.set(track["title"])
            artist_txt = track["artist"]
            self.now_artist_var.set(artist_txt)

            is_onl = track.get("is_online", False)
            if hasattr(self, "now_badge_var"):
                self.now_badge_var.set("🌐 YOUTUBE STREAM" if is_onl else "🎵 LOCAL AUDIO")
                self.badge_lbl.configure(fg=ACCENT2 if is_onl else ACCENT1)
            if hasattr(self, "live_indicator_var"):
                self.live_indicator_var.set("● NOW PLAYING")
                self.live_indicator_lbl.configure(fg=ACCENT1)
            if hasattr(self, "track_counter_var"):
                self.track_counter_var.set(f"Track {playlist_idx + 1} of {len(self.playlist)}")
            if hasattr(self, "now_spec_var"):
                ext = os.path.splitext(track.get("path", ""))[1].upper().replace(".", "") or "AUDIO"
                spec = "320 kbps Stream • Opus/AAC" if is_onl else f"{ext} • Hi-Fi Stereo Audio"
                self.now_spec_var.set(spec)

            # Update album art (local files carry art_data; online tracks use placeholder)
            self._update_art_canvas(track.get("art_data"))

            # Highlight row in treeview
            self._refresh_tree_highlight()

            # Reset progress
            self._seek_ratio = 0.0
            self.cur_time_var.set("00:00")
            self.tot_time_var.set(fmt_time(track["duration"]))

            # Update status bar
            src = "Online stream" if is_onl else "Local file"
            self._set_status(f"▶  Now playing: {track['title']}  [{src}]")

        except Exception as exc:
            self._set_status(f"Playback error: {exc}", error=True)
            messagebox.showerror("Playback Error", str(exc))

    def play_current(self):
        """Play/restart the currently selected track."""
        if self.current_index >= 0:
            self.play_at_index(self.current_index)
        elif self.playlist:
            self.play_at_index(0)

    def play_next(self):
        """Play the next track, respecting shuffle."""
        if not self.playlist:
            return

        if self.shuffle:
            idx = random.randint(0, len(self.playlist) - 1)
        else:
            idx = (self.current_index + 1) % len(self.playlist)

        self.play_at_index(idx)

    def play_prev(self):
        """Play the previous track, respecting shuffle."""
        if not self.playlist:
            return

        if self.shuffle:
            idx = random.randint(0, len(self.playlist) - 1)
        else:
            idx = (self.current_index - 1) % len(self.playlist)

        self.play_at_index(idx)

    def toggle_play_pause(self):
        """Toggle between play and pause."""
        state = self.media_player.get_state()
        if state == vlc.State.Playing:
            self.media_player.pause()
            self.is_playing = False
            if hasattr(self, "live_indicator_var"):
                self.live_indicator_var.set("⏸ PAUSED")
                self.live_indicator_lbl.configure(fg=MUTED)
            if hasattr(self, "now_badge_var"):
                self.now_badge_var.set("PAUSED")
        elif state in (vlc.State.Paused, vlc.State.Stopped):
            if self.current_index >= 0:
                self.media_player.play()
                self.is_playing = True
                if hasattr(self, "live_indicator_var"):
                    self.live_indicator_var.set("● NOW PLAYING")
                    self.live_indicator_lbl.configure(fg=ACCENT1)
                if hasattr(self, "now_badge_var"):
                    is_onl = self.playlist[self.current_index].get("is_online", False)
                    self.now_badge_var.set("🌐 YOUTUBE STREAM" if is_onl else "🎵 LOCAL AUDIO")
                    self.badge_lbl.configure(fg=ACCENT2 if is_onl else ACCENT1)
            else:
                self.play_current()

    def stop(self):
        """Stop playback completely."""
        self.media_player.stop()
        self.is_playing = False
        self._seek_ratio = 0.0
        self._draw_seek_bar(0.0)
        self.cur_time_var.set("00:00")
        if hasattr(self, "live_indicator_var"):
            self.live_indicator_var.set("⏹ STOPPED")
            self.live_indicator_lbl.configure(fg=MUTED)
        if hasattr(self, "now_badge_var"):
            self.now_badge_var.set("STOPPED")
            self.badge_lbl.configure(fg=MUTED)

    # ======================================================================
    #  Volume / Mode
    # ======================================================================
    def _on_volume_change(self, value):
        vol = int(float(value))
        self.media_player.audio_set_volume(vol)
        if hasattr(self, "vol_pct_var"):
            self.vol_pct_var.set(f"{vol}%")
        if hasattr(self, "vol_icon_lbl"):
            self.vol_icon_lbl.configure(text="🔇" if vol == 0 else ("🔉" if vol < 40 else "🔊"))
            self._is_muted = (vol == 0)

    def _vol_up(self):
        v = min(100, self.vol_var.get() + 5)
        self.vol_var.set(v)
        self._on_volume_change(v)

    def _vol_down(self):
        v = max(0, self.vol_var.get() - 5)
        self.vol_var.set(v)
        self._on_volume_change(v)

    def _toggle_shuffle(self):
        self.shuffle = not self.shuffle
        if self.shuffle:
            self.shuffle_btn.configure(style="ToggleOn.TButton")
        else:
            self.shuffle_btn.configure(style="Toggle.TButton")

    def _cycle_repeat(self):
        cycle = {
            self.REPEAT_OFF: self.REPEAT_ONE,
            self.REPEAT_ONE: self.REPEAT_ALL,
            self.REPEAT_ALL: self.REPEAT_OFF,
        }
        self.repeat_mode = cycle[self.repeat_mode]
        labels = {
            self.REPEAT_OFF: "↺ Repeat",
            self.REPEAT_ONE: "↺ One",
            self.REPEAT_ALL: "↺ All",
        }
        styles = {
            self.REPEAT_OFF: "Toggle.TButton",
            self.REPEAT_ONE: "ToggleOn.TButton",
            self.REPEAT_ALL: "ToggleOn.TButton",
        }
        self.repeat_btn.configure(text=labels[self.repeat_mode],
                                  style=styles[self.repeat_mode])

    # ======================================================================
    #  Playlist management
    # ======================================================================
    SUPPORTED_EXT = {".mp3", ".flac", ".wav", ".ogg", ".aac", ".m4a",
                     ".wma", ".opus", ".aiff", ".mp4"}

    def _add_track(self, filepath: str):
        """Add a single audio file to the internal playlist."""
        meta = read_metadata(filepath)
        self.playlist.append({
            "title":    meta["title"],
            "artist":   meta["artist"],
            "duration": meta["duration"],
            "path":     filepath,
            "art_data": meta["art_data"],   # raw bytes or None
            "is_online": False,
            "source":   "",
        })

    def add_files(self):
        """Open file dialog and add selected audio files."""
        exts = " ".join(f"*{e}" for e in self.SUPPORTED_EXT)
        paths = filedialog.askopenfilenames(
            title="Select Audio Files",
            filetypes=[("Audio Files", exts), ("All Files", "*.*")],
        )
        if not paths:
            return
        before = len(self.playlist)
        for p in paths:
            self._add_track(p)
        self._refresh_tree()
        added = len(self.playlist) - before
        self._set_status(f"➕  Added {added} file(s) — {len(self.playlist)} total")

    def add_folder(self):
        """Recursively add all audio files from a chosen folder."""
        folder = filedialog.askdirectory(title="Select Music Folder")
        if not folder:
            return
        count = 0
        for root_dir, _, files in os.walk(folder):
            for fname in sorted(files):
                if os.path.splitext(fname)[1].lower() in self.SUPPORTED_EXT:
                    self._add_track(os.path.join(root_dir, fname))
                    count += 1
        if count == 0:
            messagebox.showinfo("No Files Found",
                                "No supported audio files found in the selected folder.")
        self._refresh_tree()
        if count:
            self._set_status(f"📁  Loaded {count} file(s) from folder — {len(self.playlist)} total")

    def remove_song(self):
        """Remove the selected song from the playlist."""
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Remove Song", "Please select a song first.")
            return
        # Map treeview iid to playlist index via tag
        iid = sel[0]
        try:
            idx = int(self.tree.item(iid, "tags")[0])
        except (IndexError, ValueError):
            return

        # Adjust current_index
        if idx < self.current_index:
            self.current_index -= 1
        elif idx == self.current_index:
            self.stop()
            self.current_index = -1

        del self.playlist[idx]
        self._refresh_tree()

    def clear_playlist(self):
        """Clear all songs after user confirmation."""
        if not self.playlist:
            return
        if messagebox.askyesno("Clear Playlist",
                               "Remove all songs from the playlist?"):
            self.stop()
            self.playlist.clear()
            self.current_index = -1
            self.now_title_var.set("No track selected")
            self.now_artist_var.set("Select or double-click a song to play")
            if hasattr(self, "now_badge_var"):
                self.now_badge_var.set("EMPTY")
            if hasattr(self, "track_counter_var"):
                self.track_counter_var.set("0 / 0 tracks")
            if hasattr(self, "now_spec_var"):
                self.now_spec_var.set("Hardware Accelerated Audio Engine")
            self._update_art_canvas(None)
            self._refresh_tree()

    # ======================================================================
    #  Treeview refresh & filter
    # ======================================================================
    def _refresh_tree(self):
        """Repopulate the treeview according to current search filter."""
        query = self.search_var.get().lower().strip()

        if hasattr(self, "song_count_var"):
            self.song_count_var.set(f"{len(self.playlist)} tracks")

        for row in self.tree.get_children():
            self.tree.delete(row)

        self.filtered_indices = []
        for i, track in enumerate(self.playlist):
            # Filter
            if query and (query not in track["title"].lower()
                          and query not in track["artist"].lower()):
                continue
            self.filtered_indices.append(i)

            # Build tag tuple: playlist-index first, then visual style tags
            visual_tags: list[str] = []
            if i == self.current_index:
                visual_tags.append("now")
            elif track.get("is_online"):
                visual_tags.append("online")
            else:
                visual_tags.append(
                    "even" if len(self.filtered_indices) % 2 == 0 else "odd"
                )

            # Artist column: prefix online tracks with a globe icon
            artist_display = ("🌐 " + track["artist"]) if track.get("is_online") else track["artist"]
            # Duration: show ∞ for online streams where duration is unknown
            dur_display = fmt_time(track["duration"]) if track["duration"] > 0 else "∞"

            self.tree.insert(
                "", "end",
                iid=str(i),
                values=(
                    track["title"],
                    artist_display,
                    dur_display,
                ),
                tags=(str(i),) + tuple(visual_tags),   # first tag = playlist index
            )

    def _refresh_tree_highlight(self):
        """Update which row is highlighted as 'now playing'."""
        for row in self.tree.get_children():
            try:
                idx = int(self.tree.item(row, "tags")[0])
            except (IndexError, ValueError):
                continue
            tag = "now" if idx == self.current_index else (
                "even" if (list(self.tree.get_children()).index(row) % 2 == 0)
                else "odd"
            )
            self.tree.item(row, tags=(str(idx), tag))

    def _on_search_change(self, *_):
        self._refresh_tree()

    def _on_double_click(self, event):
        """Play a song when double-clicked in the treeview."""
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        try:
            idx = int(self.tree.item(iid, "tags")[0])
            self.play_at_index(idx)
        except (IndexError, ValueError):
            pass

    # ======================================================================
    #  Online Playback  (yt-dlp + threading)
    # ======================================================================
    def play_from_internet(self):
        """
        Open a themed dialog where the user can type:
          - A YouTube URL  (e.g. https://www.youtube.com/watch?v=...)
          - A direct audio URL  (e.g. https://example.com/song.mp3)
          - A plain song name  (searches YouTube for the best match)
        The network fetch runs in a background thread so the GUI never freezes.
        """
        if self._loading_online:
            messagebox.showinfo("Please Wait",
                                "Already loading an online track. Please wait.")
            return

        if not _YTDLP_AVAILABLE:
            messagebox.showerror(
                "yt-dlp Missing",
                "yt-dlp is not installed.\nRun:  pip install yt-dlp\nThen restart the player."
            )
            return

        query = self._internet_dialog()
        if not query:
            return

        # Update status immediately
        self._loading_online = True
        self._set_status(f"⏳  Loading online: {query} …")

        # Kick off background thread
        t = threading.Thread(
            target=self._fetch_online_thread,
            args=(query,),
            daemon=True,
        )
        t.start()

    def _internet_dialog(self) -> str:
        """
        Show a themed modal dialog asking for a URL or song name.
        Returns the entered string, or "" if cancelled.
        """
        dialog = tk.Toplevel(self.root)
        dialog.title("Play from Internet")
        dialog.configure(bg=SURFACE)
        dialog.resizable(False, False)
        dialog.grab_set()   # modal

        # Centre over main window
        self.root.update_idletasks()
        rx = self.root.winfo_x() + self.root.winfo_width()  // 2
        ry = self.root.winfo_y() + self.root.winfo_height() // 2
        dialog.geometry(f"480x190+{rx - 240}+{ry - 95}")

        # ── Content ──────────────────────────────────────────────────
        frm = tk.Frame(dialog, bg=SURFACE, padx=24, pady=20)
        frm.pack(fill="both", expand=True)

        tk.Label(frm, text="🌐  Play from Internet",
                 bg=SURFACE, fg=ACCENT2,
                 font=("Segoe UI", 13, "bold")).pack(anchor="w")

        tk.Label(frm,
                 text="Paste a YouTube URL, direct audio URL, or type a song name:",
                 bg=SURFACE, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 8))

        entry_var = tk.StringVar()
        entry = tk.Entry(frm, textvariable=entry_var,
                         bg=BG, fg=TEXT, insertbackground=TEXT,
                         font=("Segoe UI", 11), relief="flat",
                         highlightthickness=1, highlightcolor=ACCENT1,
                         highlightbackground=BORDER)
        entry.pack(fill="x", ipady=6)
        entry.focus_set()

        result: list[str] = [""]

        def on_play():
            result[0] = entry_var.get().strip()
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        # Enter key triggers play
        dialog.bind("<Return>", lambda e: on_play())
        dialog.bind("<Escape>", lambda e: on_cancel())

        btn_frame = tk.Frame(frm, bg=SURFACE)
        btn_frame.pack(fill="x", pady=(14, 0))

        tk.Button(btn_frame, text="▶  Play",
                  bg=ACCENT1, fg=TEXT, activebackground="#9B7FFF",
                  activeforeground=TEXT, relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=16, pady=6,
                  command=on_play).pack(side="right", padx=(6, 0))

        tk.Button(btn_frame, text="Cancel",
                  bg=SELECTED, fg=MUTED, activebackground=BORDER,
                  activeforeground=TEXT, relief="flat",
                  font=("Segoe UI", 10), padx=16, pady=6,
                  command=on_cancel).pack(side="right")

        self.root.wait_window(dialog)
        return result[0]

    def _fetch_online_thread(self, query: str):
        """
        Runs in a background thread.
        Uses yt-dlp to resolve `query` to a direct stream URL + metadata,
        then schedules a safe UI update back on the main thread.
        """
        try:
            import yt_dlp

            # Determine if query is a URL or a plain-text search
            is_url = query.startswith(("http://", "https://", "rtsp://", "rtmp://"))

            # ── Direct audio URL (not YouTube) ────────────────────────
            # e.g. an .mp3 hosted somewhere – VLC can handle it directly.
            # We still run it through yt-dlp to get the title if possible;
            # if yt-dlp can't extract info we fall back to using it raw.
            ydl_opts = {
                "quiet":          True,
                "no_warnings":    True,
                "format":         "bestaudio/best",   # best audio-only stream
                "noplaylist":     True,
                "default_search": "ytsearch1",        # song name → 1st YouTube result
                "socket_timeout": 15,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(query, download=False)

            # If the result is a playlist wrapper, grab the first entry
            if "entries" in info and info["entries"]:
                info = info["entries"][0]

            # Resolve the direct stream URL
            stream_url = info.get("url") or info.get("webpage_url") or query

            title    = info.get("title")    or query
            uploader = info.get("uploader") or info.get("channel") or "Online"
            duration = float(info.get("duration") or 0)

            track = {
                "title":     title,
                "artist":    uploader,
                "duration":  duration,
                "path":      stream_url,   # the resolved audio stream URL
                "source":    query,         # original user input – saved in JSON
                "is_online": True,
            }

            # Hand off to main thread
            self.root.after(0, self._on_online_ready, track)

        except Exception as exc:
            err_msg = str(exc)
            # Shorten very long yt-dlp error messages
            if len(err_msg) > 200:
                err_msg = err_msg[:200] + "…"
            self.root.after(0, self._on_online_error, err_msg)

    def _on_online_ready(self, track: dict):
        """Called on the main thread when the stream URL has been resolved."""
        self._loading_online = False
        self.playlist.append(track)
        self._refresh_tree()
        new_idx = len(self.playlist) - 1
        self._set_status(f"✅  Loaded online: {track['title']}  — playing now")
        self.play_at_index(new_idx)

    def _on_online_error(self, msg: str):
        """Called on the main thread when the online fetch fails."""
        self._loading_online = False
        self._set_status(f"❌  Online error: {msg}", error=True)
        messagebox.showerror("Online Playback Error",
                             f"Could not load the online track:\n\n{msg}")

    # ======================================================================
    #  Save / Load Playlist (JSON)  – online tracks fully round-trip
    # ======================================================================
    def save_playlist(self):
        """Save the current playlist to a JSON file."""
        if not self.playlist:
            messagebox.showinfo("Save Playlist", "Playlist is empty.")
            return
        path = filedialog.asksaveasfilename(
            title="Save Playlist",
            defaultextension=".json",
            filetypes=[("JSON Playlist", "*.json"), ("All Files", "*.*")],
        )
        if not path:
            return
        try:
            # For online tracks we save the original `source` query/URL
            # so they can be re-resolved on load (stream URLs expire).
            serialisable = []
            for t in self.playlist:
                entry = {
                    "title":     t["title"],
                    "artist":    t["artist"],
                    "duration":  t["duration"],
                    "path":      t.get("source", t["path"]) if t.get("is_online") else t["path"],
                    "is_online": t.get("is_online", False),
                    "source":    t.get("source", ""),
                }
                serialisable.append(entry)

            with open(path, "w", encoding="utf-8") as f:
                json.dump(serialisable, f, indent=2, ensure_ascii=False)
            self._set_status(f"💾  Playlist saved: {os.path.basename(path)}")
            messagebox.showinfo("Saved",
                                f"Playlist saved to:\n{os.path.basename(path)}")
        except Exception as exc:
            messagebox.showerror("Save Error", str(exc))

    def load_playlist(self):
        """Load a previously saved playlist JSON file."""
        path = filedialog.askopenfilename(
            title="Load Playlist",
            filetypes=[("JSON Playlist", "*.json"), ("All Files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise ValueError("Invalid playlist format.")

            self.stop()
            self.playlist.clear()
            self.current_index = -1

            skipped = 0
            for entry in data:
                # Validate required keys
                if not all(k in entry for k in ("title", "artist", "duration", "path")):
                    skipped += 1
                    continue

                is_online = entry.get("is_online", False)

                if is_online:
                    # Online entries: store the original source query.
                    # The `path` column holds source/query; it will be
                    # re-resolved when the user double-clicks or plays it.
                    # We mark it as online but keep the saved source.
                    source = entry.get("source") or entry["path"]
                    self.playlist.append({
                        "title":     entry["title"],
                        "artist":    entry["artist"],
                        "duration":  entry["duration"],
                        "path":      source,   # re-resolved at play time via yt-dlp
                        "source":    source,
                        "is_online": True,
                    })
                else:
                    # Local file – skip if no longer on disk
                    if not os.path.isfile(entry["path"]):
                        skipped += 1
                        continue
                    self.playlist.append({
                        "title":     entry["title"],
                        "artist":    entry["artist"],
                        "duration":  entry["duration"],
                        "path":      entry["path"],
                        "is_online": False,
                        "source":    "",
                    })

            self._refresh_tree()
            skip_note = f" ({skipped} skipped)" if skipped else ""
            count = len(self.playlist)
            self._set_status(f"📂  Loaded {count} track(s){skip_note}")
            messagebox.showinfo("Loaded",
                                f"Loaded {count} track(s).{skip_note}")
        except Exception as exc:
            messagebox.showerror("Load Error", str(exc))

    # ======================================================================
    #  Settings persistence  (settings.json)
    # ======================================================================
    def _load_settings(self):
        """
        Read settings.json and restore volume, shuffle, repeat mode and
        optionally the last playlist file path.
        """
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            return   # first run or corrupt file – silently ignore

        # Volume
        vol = int(cfg.get("volume", 70))
        self.vol_var.set(vol)
        self.media_player.audio_set_volume(vol)

        # Shuffle
        if cfg.get("shuffle", False):
            self.shuffle = True
            self.shuffle_btn.configure(style="ToggleOn.TButton")

        # Repeat mode
        rm = cfg.get("repeat_mode", self.REPEAT_OFF)
        if rm in (self.REPEAT_ONE, self.REPEAT_ALL):
            self.repeat_mode = rm
            labels = {self.REPEAT_ONE: "↺ One", self.REPEAT_ALL: "↺ All"}
            self.repeat_btn.configure(text=labels[rm], style="ToggleOn.TButton")

        # Last playlist – reload silently (no pop-up)
        last = cfg.get("last_playlist", "")
        if last and os.path.isfile(last):
            try:
                with open(last, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    for entry in data:
                        if not all(k in entry for k in ("title", "artist", "duration", "path")):
                            continue
                        is_online = entry.get("is_online", False)
                        if is_online:
                            source = entry.get("source") or entry["path"]
                            self.playlist.append({
                                "title": entry["title"], "artist": entry["artist"],
                                "duration": entry["duration"], "path": source,
                                "source": source, "is_online": True, "art_data": None,
                            })
                        elif os.path.isfile(entry["path"]):
                            self.playlist.append({
                                "title": entry["title"], "artist": entry["artist"],
                                "duration": entry["duration"], "path": entry["path"],
                                "is_online": False, "source": "",
                                "art_data": entry.get("art_data"),
                            })
                self._refresh_tree()
                self._set_status(f"📂  Restored {len(self.playlist)} track(s) from last session")
            except Exception:
                pass

    def _save_settings(self, last_playlist_path: str = ""):
        """
        Write current volume, shuffle, repeat and (optionally) a playlist
        file path to settings.json.
        """
        cfg = {
            "volume":         self.vol_var.get(),
            "shuffle":        self.shuffle,
            "repeat_mode":    self.repeat_mode,
            "last_playlist":  last_playlist_path,
        }
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass

    # ======================================================================
    #  About dialog
    # ======================================================================
    def show_about(self):
        """Show a themed 'About' window."""
        dlg = tk.Toplevel(self.root)
        dlg.title("About Music Player")
        dlg.configure(bg=SURFACE)
        dlg.resizable(False, False)
        dlg.grab_set()

        # Centre over main window
        self.root.update_idletasks()
        rx = self.root.winfo_x() + self.root.winfo_width()  // 2
        ry = self.root.winfo_y() + self.root.winfo_height() // 2
        dlg.geometry(f"420x320+{rx - 210}+{ry - 160}")

        frm = tk.Frame(dlg, bg=SURFACE, padx=30, pady=24)
        frm.pack(fill="both", expand=True)

        tk.Label(frm, text="🎵  Music Player",
                 bg=SURFACE, fg=ACCENT1,
                 font=("Segoe UI", 18, "bold")).pack(anchor="w")

        tk.Label(frm, text="Version 1.0  •  2026",
                 bg=SURFACE, fg=MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 16))

        info_lines = [
            ("Language",  "Python 3.10+"),
            ("GUI",        "Tkinter (ttk) — built-in"),
            ("Audio",      "python-vlc  (VLC media player backend)"),
            ("Metadata",   "mutagen  (tags, duration, album art)"),
            ("Online",     "yt-dlp  (YouTube & URL streaming)"),
            ("Art",        "Pillow  (album art rendering)"),
            ("Shortcuts",  "Space · ←/→ · ↑/↓ · Ctrl+O · Ctrl+A"),
        ]
        for label, value in info_lines:
            row = tk.Frame(frm, bg=SURFACE)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=f"{label}:",
                     bg=SURFACE, fg=MUTED,
                     font=("Segoe UI", 9), width=12, anchor="e").pack(side="left")
            tk.Label(row, text=value,
                     bg=SURFACE, fg=TEXT,
                     font=("Segoe UI", 9), anchor="w").pack(side="left", padx=(8, 0))

        tk.Button(frm, text="Close",
                  bg=ACCENT1, fg=TEXT, activebackground="#9B7FFF",
                  activeforeground=TEXT, relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=20, pady=6,
                  command=dlg.destroy).pack(pady=(20, 0))

        dlg.bind("<Escape>", lambda e: dlg.destroy())

    # ======================================================================
    #  Window close
    # ======================================================================
    def _on_close(self):
        """Save settings, stop VLC cleanly and destroy the window."""
        self._loading_online = False   # signal any running thread to abort (best-effort)

        # Auto-save the current playlist to a temp file so it can be
        # restored on next launch via settings.json
        auto_playlist = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_last_session.json"
        )
        try:
            serialisable = []
            for t in self.playlist:
                serialisable.append({
                    "title":     t["title"],
                    "artist":    t["artist"],
                    "duration":  t["duration"],
                    "path":      t.get("source", t["path"]) if t.get("is_online") else t["path"],
                    "is_online": t.get("is_online", False),
                    "source":    t.get("source", ""),
                })
            with open(auto_playlist, "w", encoding="utf-8") as f:
                json.dump(serialisable, f, indent=2, ensure_ascii=False)
        except Exception:
            auto_playlist = ""

        self._save_settings(last_playlist_path=auto_playlist)

        try:
            self.media_player.stop()
            self.vlc_instance.release()
        except Exception:
            pass
        self.root.destroy()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    root = tk.Tk()
    app  = MusicPlayer(root)
    root.mainloop()


if __name__ == "__main__":
    main()
