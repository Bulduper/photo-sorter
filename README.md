# Photo Sorter

A small, local photo categorizer. No account, database, or Python packages required.

## Run

```bash
python3 app.py /absolute/path/to/photos
```

Or run `python3 app.py` and enter a folder path in the app. It opens at **http://127.0.0.1:8765** (if your browser does not open automatically, visit that address). Stop with Ctrl+C. Use `--port 8766` if that port is occupied, or `--no-browser` to prevent opening a browser.

The folder can contain JPG, JPEG, PNG, GIF, WEBP, BMP and AVIF files. Browser support for some formats varies.

## Use

- **Focus** shows one photo. Use ← / → or the on-screen arrows to navigate. Number keys **1–9** toggle the corresponding category on the current photo. The ⛶ button enters actual browser fullscreen.
- **Grid** is a scrollable view of all photos. Click a photo to open it in Focus, or click its category chips to tag it directly.
- Click a **category** in the sidebar to show only its assigned photos in either view. Arrows move through the filtered results. Click **All photos** to clear the filter; empty categories show an empty-state message.
- Add categories in the sidebar, remove them with × (confirmation required), or import one or more `.txt` files with **Import category files**. Imports merge assignments with existing ones; filenames absent from the current folder are ignored.
- Each change is automatically written to `category-<category name>.txt` **in the photo folder**. Each line contains one exact photo filename; an empty category has an empty file. Only these prefixed files are automatically loaded when you reopen the folder. Imported files may be named either `category-Name.txt` or `Name.txt`.
- Your browser remembers the most recent folder, view, selected category filter, and photo position. The text files are the portable source of truth: reopen the folder in another browser or move those files with the photos to continue.

Run tests with `python3 -m unittest discover -s tests -v`.
