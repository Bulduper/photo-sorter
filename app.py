#!/usr/bin/env python3
"""Local photo categorizer. Run with: python3 app.py [photo-folder]"""

import argparse
import json
import mimetypes
import os
import re
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".avif"}
PREFIX = "category-"
STATIC = Path(__file__).resolve().parent / "static"
MAX_REQUEST = 8 * 1024 * 1024


class BadRequest(Exception):
    pass


def category_name(value):
    if not isinstance(value, str):
        raise BadRequest("Enter a category name.")
    name = value.strip()
    if (not name or len(name) > 60 or name in {".", ".."}
            or name.endswith(".") or re.search(r'[\x00-\x1f/\\<>:"|?*]', name)):
        raise BadRequest("Category names must be 1–60 characters and cannot contain / \\ < > : \" | ? * or control characters.")
    return name


def natural_key(name):
    return [(0, int(piece)) if piece.isdigit() else (1, piece.casefold())
            for piece in re.split(r"(\d+)", name)]


class Collection:
    def __init__(self):
        self.lock = threading.RLock()
        self.folder = None
        self.photos = []
        self.categories = {}  # name -> set of photo filenames

    def snapshot(self):
        with self.lock:
            names = sorted(self.categories, key=str.casefold)
            return {
                "folder": str(self.folder) if self.folder else None,
                "photos": [{"name": name, "index": i,
                            "categories": [cat for cat in names if name in self.categories[cat]]}
                           for i, name in enumerate(self.photos)],
                "categories": names,
            }

    def require_folder(self):
        if self.folder is None:
            raise BadRequest("Open a photo folder first.")

    def find_category(self, name):
        name = category_name(name)
        return next((existing for existing in self.categories if existing.casefold() == name.casefold()), None)

    def category_path(self, name):
        return self.folder / f"{PREFIX}{name}.txt"

    def save_category(self, name, filenames):
        path = self.category_path(name)
        # An atomic replacement prevents a partially written list after interruption.
        temp = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n",
                                             dir=self.folder, prefix=".photo-sorter-",
                                             delete=False) as output:
                temp = output.name
                for filename in sorted(filenames, key=natural_key):
                    output.write(filename + "\n")
            os.replace(temp, path)
        finally:
            if temp and os.path.exists(temp):
                os.unlink(temp)

    def open_folder(self, location):
        if not isinstance(location, str) or not location.strip():
            raise BadRequest("Enter a folder path.")
        folder = Path(location.strip()).expanduser().resolve()
        if not folder.is_dir():
            raise BadRequest("That folder does not exist or cannot be opened.")
        with self.lock:
            try:
                entries = list(folder.iterdir())
                photos = sorted((p.name for p in entries if p.is_file()
                                 and p.suffix.lower() in PHOTO_EXTENSIONS
                                 and "\n" not in p.name and "\r" not in p.name), key=natural_key)
                photo_set = set(photos)
                categories = {}
                for path in sorted(entries, key=lambda p: p.name.casefold()):
                    if not path.is_file() or not path.name.startswith(PREFIX) or path.suffix.lower() != ".txt":
                        continue
                    name = path.name[len(PREFIX):-4]
                    try:
                        category_name(name)
                        if any(existing.casefold() == name.casefold() for existing in categories):
                            continue
                        categories[name] = set(path.read_text(encoding="utf-8-sig").splitlines()) & photo_set
                    except (BadRequest, UnicodeError):
                        continue
            except OSError as error:
                raise BadRequest(f"Could not read folder: {error}") from error
            self.folder, self.photos, self.categories = folder, photos, categories
            return self.snapshot()

    def add_category(self, name):
        with self.lock:
            self.require_folder()
            name = category_name(name)
            if self.find_category(name):
                raise BadRequest("That category already exists.")
            self.save_category(name, set())
            self.categories[name] = set()
            return self.snapshot()

    def remove_category(self, name):
        with self.lock:
            self.require_folder()
            name = self.find_category(name)
            if name is None:
                raise BadRequest("Category not found.")
            self.category_path(name).unlink(missing_ok=True)
            del self.categories[name]
            return self.snapshot()

    def toggle(self, name, filename):
        with self.lock:
            self.require_folder()
            name = self.find_category(name)
            if name is None or filename not in self.photos:
                raise BadRequest("Photo or category not found.")
            updated = self.categories[name].copy()
            if filename in updated:
                updated.remove(filename)
            else:
                updated.add(filename)
            self.save_category(name, updated)
            self.categories[name] = updated
            return self.snapshot()

    def import_files(self, files):
        with self.lock:
            self.require_folder()
            if not isinstance(files, list) or not files:
                raise BadRequest("Select one or more .txt category files.")
            updates = {}
            photo_set = set(self.photos)
            for item in files:
                if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not isinstance(item.get("content"), str):
                    raise BadRequest("Invalid category file.")
                source = Path(item["name"]).name
                if not source.lower().endswith(".txt"):
                    raise BadRequest("Only .txt category files are supported.")
                stem = source[:-4]
                if stem.startswith(PREFIX):
                    stem = stem[len(PREFIX):]
                name = category_name(stem)
                name = (self.find_category(name)
                        or next((existing for existing in updates if existing.casefold() == name.casefold()), name))
                if name not in updates:
                    updates[name] = self.categories.get(name, set()).copy()
                updates[name].update(set(item["content"].lstrip("\ufeff").splitlines()) & photo_set)
            for name, filenames in updates.items():
                self.save_category(name, filenames)
                self.categories[name] = filenames
            return self.snapshot()


def make_handler(collection):
    class Handler(BaseHTTPRequestHandler):
        def send_bytes(self, status, data, content_type):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def send_json(self, status, value):
            self.send_bytes(status, json.dumps(value, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self):
            path = unquote(urlsplit(self.path).path)
            if path == "/api/state":
                return self.send_json(200, collection.snapshot())
            if path.startswith("/api/photo/"):
                try:
                    index = int(path[len("/api/photo/"):])
                    with collection.lock:
                        filename = collection.photos[index] if index >= 0 else None
                        photo = collection.folder / filename if filename else None
                    if photo is None or not photo.is_file():
                        raise ValueError
                    self.send_bytes(200, photo.read_bytes(), mimetypes.guess_type(photo.name)[0] or "application/octet-stream")
                except (ValueError, IndexError, OSError):
                    self.send_json(404, {"error": "Photo not found."})
                return
            assets = {"/": ("index.html", "text/html; charset=utf-8"),
                      "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                      "/style.css": ("style.css", "text/css; charset=utf-8")}
            if path not in assets:
                return self.send_json(404, {"error": "Not found."})
            filename, content_type = assets[path]
            self.send_bytes(200, (STATIC / filename).read_bytes(), content_type)

        def do_POST(self):
            if self.headers.get("Origin") not in (None, f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"):
                return self.send_json(403, {"error": "Invalid origin."})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0 or length > MAX_REQUEST:
                    raise BadRequest("Request is too large.")
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise BadRequest("Invalid request.")
                path = urlsplit(self.path).path
                if path == "/api/folder":
                    result = collection.open_folder(data.get("path"))
                elif path == "/api/categories/add":
                    result = collection.add_category(data.get("name"))
                elif path == "/api/categories/remove":
                    result = collection.remove_category(data.get("name"))
                elif path == "/api/toggle":
                    result = collection.toggle(data.get("category"), data.get("filename"))
                elif path == "/api/import":
                    result = collection.import_files(data.get("files"))
                else:
                    return self.send_json(404, {"error": "Not found."})
                self.send_json(200, result)
            except (BadRequest, ValueError, json.JSONDecodeError) as error:
                self.send_json(400, {"error": str(error)})
            except OSError as error:
                self.send_json(500, {"error": f"Could not save files: {error}"})

    return Handler


def main():
    parser = argparse.ArgumentParser(description="Sort photos into categories using a local browser app.")
    parser.add_argument("folder", nargs="?", help="Photo folder to open at startup")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    collection = Collection()
    if args.folder:
        try:
            collection.open_folder(args.folder)
        except BadRequest as error:
            parser.error(str(error))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(collection))
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"Photo Sorter running at {url} (Ctrl+C to stop)", flush=True)
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
