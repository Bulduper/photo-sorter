import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app import Collection, make_handler


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        for name in ("photo10.jpg", "photo2.jpg", "landscape.png"):
            (self.folder / name).write_bytes(b"example image")
        (self.folder / "notes.txt").write_text("not a category\n")
        self.collection = Collection()
        self.collection.open_folder(str(self.folder))

    def test_saves_and_restores_multiple_categories(self):
        self.assertEqual(self.collection.photos, ["landscape.png", "photo2.jpg", "photo10.jpg"])
        self.collection.add_category("Favorites")
        self.collection.add_category("Trips")
        self.collection.toggle("Favorites", "photo2.jpg")
        self.collection.toggle("Trips", "photo2.jpg")
        self.collection.toggle("Favorites", "photo10.jpg")
        self.assertEqual((self.folder / "category-Favorites.txt").read_text(), "photo2.jpg\nphoto10.jpg\n")
        restored = Collection()
        restored.open_folder(str(self.folder))
        self.assertEqual(restored.snapshot()["photos"][1]["categories"], ["Favorites", "Trips"])
        self.assertEqual(restored.snapshot()["categories"], ["Favorites", "Trips"])
        self.assertEqual((self.folder / "notes.txt").read_text(), "not a category\n")

    def test_import_merges_and_remove_deletes_only_category_file(self):
        self.collection.add_category("Favorites")
        self.collection.toggle("Favorites", "landscape.png")
        self.collection.import_files([
            {"name": "category-Favorites.txt", "content": "photo2.jpg\nmissing.jpg\n"},
            {"name": "Nature.txt", "content": "landscape.png\n"},
        ])
        self.assertEqual((self.folder / "category-Favorites.txt").read_text(), "landscape.png\nphoto2.jpg\n")
        self.assertEqual((self.folder / "category-Nature.txt").read_text(), "landscape.png\n")
        self.collection.remove_category("Nature")
        self.assertFalse((self.folder / "category-Nature.txt").exists())
        self.assertTrue((self.folder / "notes.txt").exists())

    def test_rejects_invalid_names(self):
        from app import BadRequest
        for name in ("../outside", "bad/name", "", "a\nb"):
            with self.subTest(name=name), self.assertRaises(BadRequest):
                self.collection.add_category(name)


class APITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        (self.folder / "example.jpg").write_bytes(b"example image")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(Collection()))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.thread.join, 2)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def post(self, path, payload):
        req = Request(self.base + path, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        with urlopen(req) as response:
            return json.load(response)

    def test_end_to_end_and_photo_route(self):
        state = self.post("/api/folder", {"path": str(self.folder)})
        self.assertEqual(state["photos"][0]["name"], "example.jpg")
        self.post("/api/categories/add", {"name": "Keep"})
        state = self.post("/api/toggle", {"filename": "example.jpg", "category": "Keep"})
        self.assertEqual(state["photos"][0]["categories"], ["Keep"])
        with urlopen(self.base + "/api/photo/0") as response:
            self.assertEqual(response.read(), b"example image")
        with self.assertRaises(HTTPError) as error:
            urlopen(self.base + "/api/photo/../app.py")
        self.assertEqual(error.exception.code, 404)
        error.exception.close()


if __name__ == "__main__":
    unittest.main()
