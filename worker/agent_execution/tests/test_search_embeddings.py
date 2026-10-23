from types import SimpleNamespace

import pytest

from app.search import embeddings


def test_tokenize_ignores_case_accents_stop_words_and_plurals():
    assert embeddings.tokenize("Les Dossiers des ÉTUDIANTS") == embeddings.tokenize("dossier etudiant")


def test_tokenize_keeps_numbers_and_identifiers():
    tokens = embeddings.tokenize("Facture n° 2024-0042 du 12/03")
    assert "2024" in tokens and "0042" in tokens


def test_tokenize_of_nothing():
    assert embeddings.tokenize("") == []
    assert embeddings.tokenize(None) == []
    assert embeddings.tokenize("le la de") == []


def test_term_index_is_stable_across_runs():
    assert embeddings.term_index("dossier") == embeddings.term_index("dossier")
    assert 0 <= embeddings.term_index("dossier") < 2**32
    # Valeur figée : une autre empreinte rendrait tous les index déjà écrits illisibles.
    assert embeddings.term_index("dossier") == 3756465160


def test_sparse_weight_saturates_with_frequency():
    once = embeddings.encode_sparse("loyer")
    many = embeddings.encode_sparse("loyer " * 20)
    assert many["values"][0] > once["values"][0]
    assert many["values"][0] < 2.2 * (1 + 1.2)  # borné par k1 + 1


def test_sparse_of_an_empty_text():
    assert embeddings.encode_sparse("") == {"indices": [], "values": []}


def test_sparse_query_counts_each_distinct_term_once():
    query = embeddings.encode_sparse_query("loyer loyer charges")
    assert len(query["indices"]) == 2
    assert query["values"] == [1.0, 1.0]
    assert set(query["indices"]) <= set(embeddings.encode_sparse("le loyer et les charges")["indices"])


class _FakeEmbeddings:
    def __init__(self, shuffle: bool = False, short: bool = False) -> None:
        self.calls: list[list[str]] = []
        self._shuffle = shuffle
        self._short = short

    def create(self, model: str, input: list[str]):
        self.calls.append(input)
        items = [SimpleNamespace(index=i, embedding=[float(len(text)), 0.0]) for i, text in enumerate(input)]
        if self._short:
            items = items[:-1]
        if self._shuffle:
            items.reverse()
        return SimpleNamespace(data=items)


@pytest.fixture
def fake_client(monkeypatch):
    def install(**options):
        fake = _FakeEmbeddings(**options)
        monkeypatch.setattr(embeddings, "_client", lambda: SimpleNamespace(embeddings=fake))
        return fake

    return install


def test_embed_dense_sends_batches_and_keeps_the_order(fake_client, monkeypatch):
    monkeypatch.setattr(embeddings.settings, "EMBEDDING_BATCH_SIZE", 2)
    fake = fake_client()
    vectors = embeddings.embed_dense(["a", "bb", "ccc", "dddd", "eeeee"], "m")
    assert [len(call) for call in fake.calls] == [2, 2, 1]
    assert [v[0] for v in vectors] == [1.0, 2.0, 3.0, 4.0, 5.0]


def test_embed_dense_reorders_a_shuffled_answer(fake_client):
    fake_client(shuffle=True)
    assert [v[0] for v in embeddings.embed_dense(["a", "bb", "ccc"], "m")] == [1.0, 2.0, 3.0]


def test_embed_dense_refuses_a_missing_vector(fake_client):
    fake_client(short=True)
    with pytest.raises(RuntimeError, match="vecteurs"):
        embeddings.embed_dense(["a", "bb"], "m")


def test_embed_dense_of_nothing_does_not_call_the_model(fake_client):
    fake = fake_client()
    assert embeddings.embed_dense([], "m") == []
    assert fake.calls == []
