import pytest

from app.search import chunking
from app.search.chunking import Chunk, ChunkingSettings, ChunkPlan, ChunkRange


def _text_of(page: str, chunk: Chunk) -> str:
    return page[chunk.char_start : chunk.char_end]


# --- Découpage classique ---


def test_classic_short_text_is_one_chunk():
    assert chunking.split_classic("Bonjour le monde", 100, 10) == [Chunk("Bonjour le monde", 0, 16)]


def test_classic_chunks_respect_size_and_keep_their_position():
    page = " ".join(f"mot{i}" for i in range(300))
    chunks = chunking.split_classic(page, 200, 40)
    assert len(chunks) > 3
    assert all(len(c.text) <= 200 for c in chunks)
    assert all(_text_of(page, c) == c.text for c in chunks)


def test_classic_chunks_overlap_and_cover_the_text():
    page = " ".join(f"mot{i}" for i in range(300))
    chunks = chunking.split_classic(page, 200, 40)
    assert chunks[0].char_start == 0 and chunks[-1].char_end == len(page)
    for before, after in zip(chunks, chunks[1:], strict=False):
        assert after.char_start < before.char_end  # chevauchement
        assert after.char_start > before.char_start  # toujours en avant


def test_classic_cuts_on_a_paragraph_rather_than_mid_word():
    page = ("a" * 80 + "\n\n") + ("b" * 80)
    chunks = chunking.split_classic(page, 120, 0)
    assert chunks[0].text == "a" * 80


def test_classic_without_overlap_does_not_repeat_text():
    page = "x" * 450
    chunks = chunking.split_classic(page, 200, 0)
    assert [len(c.text) for c in chunks] == [200, 200, 50]


def test_classic_text_with_no_separator_is_still_cut():
    assert len(chunking.split_classic("x" * 1000, 300, 50)) >= 4


@pytest.mark.parametrize("size,overlap", [(0, 0), (100, 100), (100, 150), (100, -1)])
def test_classic_refuses_bad_parameters(size, overlap):
    with pytest.raises(ValueError):
        chunking.split_classic("texte", size, overlap)


def test_blank_page_gives_no_chunk():
    classic = ChunkingSettings(strategy="classique")
    assert chunking.split_page("   \n ", classic) == []
    assert chunking.split_page("", ChunkingSettings(model="m")) == []


# --- Découpage par IA ---

LINES = [f"Ligne {i} " + "x" * 90 for i in range(1, 21)]
PAGE = "\n".join(LINES)  # ~2000 caractères sur 20 lignes
AI = ChunkingSettings(strategy="ia", model="modele-decoupage")


@pytest.fixture
def plan(monkeypatch):
    calls = []

    def install(chunks: list[tuple[int, int]] | Exception):
        def fake(model, numbered):
            calls.append((model, numbered))
            if isinstance(chunks, Exception):
                raise chunks
            return ChunkPlan(chunks=[ChunkRange(start_line=a, end_line=b) for a, b in chunks])

        monkeypatch.setattr(chunking, "_plan_chunks", fake)
        return calls

    return install


def test_ai_cuts_where_the_model_says_and_keeps_positions(plan):
    calls = plan([(1, 5), (6, 12), (13, 20)])
    chunks = chunking.split_page(PAGE, AI)
    assert [c.text.count("\n") + 1 for c in chunks] == [5, 7, 8]
    assert all(_text_of(PAGE, c) == c.text for c in chunks)
    assert calls[0][0] == "modele-decoupage"
    assert calls[0][1].startswith("1: Ligne 1 ")


def test_ai_attaches_forgotten_lines_to_the_previous_chunk(plan):
    plan([(1, 5), (9, 20)])  # lignes 6 à 8 oubliées
    chunks = chunking.split_page(PAGE, AI)
    assert [c.text.count("\n") + 1 for c in chunks] == [8, 12]
    assert "".join(c.text for c in chunks).count("Ligne") == 20


def test_ai_skips_the_model_for_a_short_page(plan):
    calls = plan([(1, 1)])
    chunks = chunking.split_page("  Un texte court.  ", AI)
    assert chunks == [Chunk("Un texte court.", 2, 17)]
    assert calls == []


@pytest.mark.parametrize(
    "ranges",
    [[(1, 30)], [(0, 5)], [(1, 10), (8, 20)], [(5, 3)], []],
    ids=["hors bornes", "ligne zéro", "chevauchement", "inversé", "vide"],
)
def test_ai_unusable_answer_falls_back_to_classic(plan, ranges):
    plan(ranges)
    chunks = chunking.split_page(PAGE, ChunkingSettings(strategy="ia", model="m", size=500, overlap=50))
    assert chunks == chunking.split_classic(PAGE, 500, 50)


def test_ai_model_failure_falls_back_to_classic(plan):
    plan(RuntimeError("hub indisponible"))
    assert chunking.split_page(PAGE, ChunkingSettings(strategy="ia", model="m", size=500, overlap=50))


def test_ai_without_a_model_falls_back_to_classic(plan):
    calls = plan([(1, 20)])
    assert chunking.split_page(PAGE, ChunkingSettings(strategy="ia", model=None, size=500, overlap=50))
    assert calls == []


def test_ai_recuts_a_chunk_that_is_too_long(plan):
    long_page = "\n".join(["y" * 100] * 80)  # 8000 caractères
    plan([(1, 80)])
    chunks = chunking.split_page(long_page, ChunkingSettings(strategy="ia", model="m", size=1000, overlap=100))
    assert len(chunks) > 2
    assert all(len(c.text) <= chunking.AI_MAX_CHARS for c in chunks)
    assert all(_text_of(long_page, c) == c.text for c in chunks)


def test_ai_long_page_is_sent_in_several_slices(plan, monkeypatch):
    monkeypatch.setattr(chunking, "AI_MAX_INPUT_CHARS", 1000)
    calls = plan([(1, 4)])  # chaque tranche est numérotée à partir de 1
    chunking.split_page(PAGE, AI)
    assert len(calls) > 1
    assert all(numbered.startswith("1: ") for _, numbered in calls)


# --- Réglages ---


def test_settings_from_dict_uses_defaults():
    s = ChunkingSettings.from_dict(None)
    assert (s.strategy, s.size, s.overlap, s.window) == ("ia", 1000, 150, 1)
    assert ChunkingSettings.from_dict({"strategy": "classique", "size": 500, "overlap": 0, "window": 0}).overlap == 0


def test_validate():
    chunking.validate(ChunkingSettings(strategy="ia", model="m"))
    chunking.validate(ChunkingSettings(strategy="classique"))
    with pytest.raises(ValueError, match="modèle"):
        chunking.validate(ChunkingSettings(strategy="ia"))
    with pytest.raises(ValueError, match="inconnue"):
        chunking.validate(ChunkingSettings(strategy="x"))
    with pytest.raises(ValueError, match="invalides"):
        chunking.validate(ChunkingSettings(strategy="classique", size=100, overlap=100))
