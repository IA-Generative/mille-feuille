"""The image of a page handed to the OCR pods through S3 (app/ocr/pages.py, RustFsStorage.delete_objects)."""

from app.config import settings
from app.ocr import pages
from app.storage import RustFsStorage


class FakeStorage:
    def __init__(self, objects: dict[str, bytes] | None = None):
        self.objects = dict(objects or {})
        self.content_types: dict[str, str] = {}

    def put_object(self, key, data, content_type="application/octet-stream"):
        self.objects[key] = data
        self.content_types[key] = content_type

    def delete_objects(self, keys):
        for key in keys:
            self.objects.pop(key, None)


def test_the_image_of_a_page_has_a_key_apart_from_the_screenshots():
    key = pages.page_image_key("doc-1", 7)
    assert key == "ocr-pages/doc-1/page-7.png"
    assert not key.startswith("screenshots/")


def test_an_image_goes_in_and_comes_out_by_its_key():
    storage = FakeStorage()
    key = pages.put_page_image(storage, "doc-1", 3, b"png-bytes")
    assert key == pages.page_image_key("doc-1", 3)
    assert storage.content_types[key] == "image/png"
    assert storage.objects[key] == b"png-bytes"


def test_the_images_of_some_pages_are_dropped_and_no_other():
    storage = FakeStorage(
        {
            pages.page_image_key("doc-1", 1): b"a",
            pages.page_image_key("doc-1", 2): b"b",
            pages.page_image_key("doc-1", 3): b"c",
            pages.page_image_key("doc-10", 1): b"not ours: same start, other document",
            "screenshots/doc-1/page-1.png": b"stays",
        }
    )
    pages.delete_pages_images(storage, "doc-1", [1, 3])
    assert set(storage.objects) == {
        pages.page_image_key("doc-1", 2),
        pages.page_image_key("doc-10", 1),
        "screenshots/doc-1/page-1.png",
    }


def test_delete_objects_goes_by_batches_of_a_thousand():
    class Client:
        def __init__(self):
            self.batches = []

        def delete_objects(self, Bucket, Delete):
            self.batches.append([item["Key"] for item in Delete["Objects"]])

    storage = RustFsStorage()
    storage._client = Client()
    storage.delete_objects([f"k{n}" for n in range(1500)])
    assert [len(batch) for batch in storage._client.batches] == [1000, 500]


def test_the_engine_is_tesseract_until_set_otherwise():
    """Nothing changes for a deployment that sets nothing."""
    assert settings.OCR_ENGINE == "tesseract"
