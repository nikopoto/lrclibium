import asyncio
import subprocess
import re
import httpx
import urllib.parse
import datetime
from collections import OrderedDict
from typing import List, Tuple, Optional
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.align import Align

console = Console()
TIMESTAMP_RE = re.compile(r"\[(\d+):(\d+\.\d+)\]")
ERROR_LOG = "lyrics_errors.log"

def log_error(msg: str):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(ERROR_LOG, "a") as f:
        f.write(f"[{timestamp}] {msg}\n")

class LyricsManager:
    def __init__(self, cache_size: int = 50):
        self.cache = OrderedDict()
        self.cache_size = cache_size

    async def get_lyrics(self, artist: str, title: str) -> List[Tuple[float, str]]:
        key = f"{artist} - {title}"
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        try:
            lyrics = await self._fetch_lyrics(artist, title)
        except Exception as e:
            log_error(f"Failed to fetch lyrics for {artist} - {title}: {e}")
            return [(0, "❌ Lyrics not found")]
        self.cache[key] = lyrics
        if len(self.cache) > self.cache_size:
            self.cache.popitem(last=False)
        return lyrics

    async def _fetch_lyrics(self, artist: str, title: str) -> List[Tuple[float, str]]:
        query = f"{artist} {title}"
        url = f"https://lrclib.net/api/search?q={urllib.parse.quote_plus(query)}"
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            log_error(f"Error fetching lyrics for {artist} - {title}: {e}")
            return [(0, "❌ Lyrics not found")]
        if not data:
            return [(0, "❌ Lyrics not found")]
        track = data[0]
        lyrics_text = track.get("syncedLyrics") or track.get("plainLyrics") or "❌ Lyrics not found"
        if isinstance(lyrics_text, str) and lyrics_text.startswith("http"):
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    lyrics_text = await client.get(lyrics_text).text
            except Exception as e:
                log_error(f"Failed to download lyrics from URL for {artist} - {title}: {e}")
                lyrics_text = "❌ Lyrics not found"
        return self.parse_lrc(lyrics_text)

    @staticmethod
    def parse_lrc(text: str) -> List[Tuple[float, str]]:
        lines = []
        for line in text.splitlines():
            matches = list(TIMESTAMP_RE.finditer(line))
            if not matches:
                continue
            lyric = line[matches[-1].end():].strip()
            for m in matches:
                try:
                    mins = int(m.group(1))
                    secs = float(m.group(2))
                    lines.append((mins * 60 + secs, lyric))
                except Exception:
                    continue
        return sorted(lines, key=lambda x: x[0]) if lines else [(0, "❌ No parseable lyrics found")]

class MusicPlayer:
    def __init__(self, name: str):
        self.name = name

    async def get_track(self) -> Tuple[Optional[str], Optional[str]]:
        try:
            artist = await self._run_playerctl("metadata", "xesam:artist")
            title = await self._run_playerctl("metadata", "xesam:title")
            return artist, title
        except Exception as e:
            log_error(f"Player error getting track info: {e}")
            return None, None

    async def get_position(self) -> float:
        try:
            pos = await self._run_playerctl("position")
            return float(pos) if pos else 0.0
        except Exception as e:
            log_error(f"Player error getting position: {e}")
            return 0.0

    async def _run_playerctl(self, *args) -> Optional[str]:
        proc = await asyncio.create_subprocess_exec(
            "playerctl", "-p", self.name, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=2)
            return stdout.decode().strip()
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            log_error(f"Timeout running playerctl for {self.name} args {args}")
            return None

def choose_player(forced: Optional[str] = None) -> Optional[str]:
    if forced:
        return forced
    try:
        players = subprocess.check_output(["playerctl", "-l"], text=True).strip().splitlines()
    except Exception:
        return None
    for p in players:
        try:
            pos = subprocess.check_output(["playerctl", "position", "-p", p], text=True).strip()
            if pos and float(pos) >= 0:
                return p
        except Exception:
            continue
    return None

class WindowManager:
    def __init__(self, size: int):
        self.size = size

    def get_indices(self, current_index: int, total_lines: int) -> Tuple[int, int]:
        if total_lines <= self.size:
            return 0, total_lines
        half = self.size // 2
        top = max(0, current_index - half)
        bottom = min(top + self.size, total_lines)
        top = max(0, bottom - self.size)
        return top, bottom

def render_panel(lyrics: List[Tuple[float, str]], current_time: float,
                 artist: str, title: str, window_mgr: WindowManager) -> Panel:
    idx = 0
    for i in range(len(lyrics)-1):
        if lyrics[i][0] <= current_time < lyrics[i+1][0]:
            idx = i
            break
    else:
        idx = len(lyrics) - 1
    start, end = window_mgr.get_indices(idx, len(lyrics))
    content = []
    for i in range(start, end):
        _, line = lyrics[i]
        if i == idx:
            content.append(f"[black on cyan]{line}[/black on cyan]")
        elif abs(i - idx) == 1:
            content.append(f"[bright_white]{line}[/bright_white]")
        else:
            content.append(f"[dim]{line}[/dim]")
    panel_content = "\n".join(content)
    return Panel(Align.center(panel_content), title=f"[bold green]{artist} - {title}[/bold green]")

async def run_lyrics(player_name: str, window: int, cache_size: int):
    player = MusicPlayer(player_name)
    lyrics_mgr = LyricsManager(cache_size=cache_size)
    window_mgr = WindowManager(window)
    last_track = None
    lyrics_lines = [(0, "❌ Lyrics not found")]

    with Live(console=console, refresh_per_second=10) as live:
        try:
            while True:
                artist, title = await player.get_track()
                if not artist or not title:
                    await asyncio.sleep(0.5)
                    continue

                track_key = f"{artist} - {title}"
                if track_key != last_track:
                    try:
                        new_lyrics = await lyrics_mgr.get_lyrics(artist, title)
                        if new_lyrics:
                            lyrics_lines = new_lyrics
                    except Exception as e:
                        log_error(f"Error updating lyrics for {track_key}: {e}")
                    last_track = track_key

                pos = await player.get_position()
                panel = render_panel(lyrics_lines, pos, artist or "Unknown", title or "Unknown", window_mgr)
                live.update(panel)
                await asyncio.sleep(0.1)
        except KeyboardInterrupt:
            console.clear()
            console.print("[bold yellow]Exited lyrics display[/bold yellow]")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Centered Sliding Window Lyrics")
    parser.add_argument("-p", "--player", help="Force player name")
    parser.add_argument("--window", type=int, default=10, help="Lyrics window size")
    parser.add_argument("--cache-size", type=int, default=50, help="Lyrics cache size")
    args = parser.parse_args()

    player_name = choose_player(args.player)
    if not player_name:
        console.print("[bold red]❌ No active player found[/bold red]")
        return

    asyncio.run(run_lyrics(player_name, window=args.window, cache_size=args.cache_size))

if __name__ == "__main__":
    main()
