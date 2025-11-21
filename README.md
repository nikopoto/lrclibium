# LRCLib Terminal Lyrics Viewer

**A real time in-terminal lyrics viewer powered by LRCLib.**

---

## Features
- Supports any music player that exposes itself to mpris with metadata
- Logs errors to `lyrics_errors.log` without interrupting display


---

## How to use

```bash
git clone https://github.com/nikopoto/lrclibium.git
cd lrclibium
python3 -m venv lrclibium-venv
source ./lrclibium-venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

**Requires:**

- Python 3.11+ (tested on 3.14)
- `httpx`
- `rich`
- `playerctl` installed

---

## Usage

```bash
python lrclibium.py
```

**Optional arguments:**

- `-p / --player` : Force a specific music player, useful if you have many music apps open at the same time
- `--window` : Number of lyrics lines to display at once (default: 8)
- `--cache-size` : Maximum number of lyrics to cache (default: 100)

**Example:**

```bash
python lrclibium.py -p spotify --window 10 --cache-size 50
```

---

## Logging

All runtime errors and API issues are logged to `lyrics_errors.log`.

---

## Contributing

Contributions are welcome. Make sure to maintain the GPLv3 license when distributing modified versions.

---

## License

This project is licensed under **GPLv3**. See the `LICENSE` file for full details.
