"""Normalisation des fichiers passés à l'upload multipart."""

from __future__ import annotations

import mimetypes
from collections.abc import Iterable
from pathlib import Path
from typing import BinaryIO

from millefeuille._http import FileTuple

# str/Path (chemin), bytes, objet fichier binaire, ou tuple (nom, contenu[, type MIME]).
FileInput = str | Path | bytes | BinaryIO | tuple[str, bytes | BinaryIO] | tuple[str, bytes | BinaryIO, str]


def _guess_mimetype(name: str) -> str:
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


def _read(content: bytes | BinaryIO) -> bytes:
    return content if isinstance(content, bytes) else content.read()


def _one(item: FileInput, index: int) -> FileTuple:
    name: str
    content: bytes
    mimetype: str | None = None
    if isinstance(item, tuple):
        name = item[0]
        content = _read(item[1])
        if len(item) == 3:
            mimetype = item[2]
    elif isinstance(item, bytes):
        name, content = f"document-{index + 1}", item
    elif isinstance(item, str | Path):
        path = Path(item)
        name, content = path.name, path.read_bytes()
    else:
        raw_name = getattr(item, "name", None)
        name = Path(raw_name).name if isinstance(raw_name, str) else f"document-{index + 1}"
        content = item.read()
    return ("files", (name, content, mimetype or _guess_mimetype(name)))


def prepare_files(files: Iterable[FileInput]) -> list[FileTuple]:
    """Lit chaque fichier en mémoire et renvoie les tuples multipart attendus par httpx."""
    prepared = [_one(item, index) for index, item in enumerate(files)]
    if not prepared:
        raise ValueError("Au moins un fichier est requis.")
    return prepared


def prepare_file(file: FileInput) -> FileTuple:
    """Lit un seul fichier en mémoire sous le champ multipart `file` (routes qui n'acceptent qu'un document)."""
    _, part = _one(file, 0)
    return ("file", part)
