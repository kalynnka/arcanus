"""ORM-like plain objects for ``from_attributes`` validation benchmarks.

These mimic an ORM row (attribute access, no dict) so the validation path that
reads attributes — the common FastAPI/Django response pattern — is measured.
"""

from __future__ import annotations

import random

from benchmark.data import corpus


class MockAuthor:
    __slots__ = ("id", "name", "field")

    def __init__(self, id: int, name: str, field: str):
        self.id = id
        self.name = name
        self.field = field


class MockPublisher:
    __slots__ = ("id", "name", "country")

    def __init__(self, id: int, name: str, country: str):
        self.id = id
        self.name = name
        self.country = country


class MockBook:
    __slots__ = ("id", "title", "year", "author", "publisher")

    def __init__(
        self,
        id: int,
        title: str,
        year: int,
        author: MockAuthor,
        publisher: MockPublisher,
    ):
        self.id = id
        self.title = title
        self.year = year
        self.author = author
        self.publisher = publisher


def mock_authors(n: int) -> list[MockAuthor]:
    rng = random.Random(corpus.SEED)
    return [
        MockAuthor(
            i,
            f"{rng.choice(corpus.AUTHOR_NAMES)} {rng.randint(1, 999)}",
            rng.choice(corpus.FIELDS),
        )
        for i in range(n)
    ]


def mock_books(n: int) -> list[MockBook]:
    rng = random.Random(corpus.SEED + 1)
    books = []
    for i in range(n):
        author = MockAuthor(
            i % 10,
            f"{rng.choice(corpus.AUTHOR_NAMES)} {rng.randint(1, 999)}",
            rng.choice(corpus.FIELDS),
        )
        publisher = MockPublisher(
            i % 5,
            f"Publisher {rng.choice(corpus.PUBLISHER_KINDS)} {rng.randint(1, 50)}",
            rng.choice(corpus.COUNTRIES),
        )
        books.append(
            MockBook(
                i,
                f"The {rng.choice(corpus.BOOK_ADJECTIVES)} Book {i}",
                rng.randint(1990, 2024),
                author,
                publisher,
            )
        )
    return books
