"""Richer, scalable, reproducible database seeds for Axis B benchmarks.

Every seed is session-scoped and read-only — write benchmarks open their own
session and ``rollback()`` so the committed seed state is never mutated. Sizes
are single-sourced as module constants so the matrix stays bounded and the
local report can derive per-object timings. Imported by the Axis B conftest.
"""

from __future__ import annotations

import random
from typing import Any, Generator

import pytest
from sqlalchemy.orm import Session, sessionmaker

from benchmark.data import builders, corpus
from tests import models

N_AUTHORS = 100
N_BOOKS = 100
N_BLOG_POSTS = 100
K_BOOKS_PER_AUTHOR = 5
C_CATEGORIES_PER_BOOK = 3
R_REVIEWS_PER_BOOK = 4
N_CATEGORIES = 20
N_SHELF_ITEMS = 20
WAREHOUSE_GROUPS = 4
ITEMS_PER_GROUP = 5
N_GENERATED_FILES = 12


def _author(rng: random.Random) -> models.Author:
    return models.Author(
        name=f"{rng.choice(corpus.AUTHOR_NAMES)} {rng.randint(100, 999)}",
        field=rng.choice(corpus.FIELDS),
    )


def _publisher(rng: random.Random, idx: int) -> models.Publisher:
    return models.Publisher(
        name=f"Publisher {rng.choice(corpus.PUBLISHER_KINDS)} {idx}",
        country=rng.choice(corpus.COUNTRIES),
    )


def _title(rng: random.Random) -> str:
    return (
        f"The {rng.choice(corpus.BOOK_ADJECTIVES)} "
        f"{rng.choice(corpus.BOOK_NOUNS)} {rng.randint(1, 99)}"
    )


@pytest.fixture(scope="session")
def seeded_authors(
    session_factory: sessionmaker[Session],
) -> Generator[list[models.Author], None, None]:
    """100 flat authors (no books)."""
    rng = random.Random(corpus.SEED)
    with session_factory() as session:
        authors = [_author(rng) for _ in range(N_AUTHORS)]
        session.add_all(authors)
        session.commit()
        for a in authors:
            session.refresh(a)
        yield authors


@pytest.fixture(scope="session")
def seeded_books(
    session_factory: sessionmaker[Session],
) -> Generator[list[models.Book], None, None]:
    """100 books, each linked to an author and a publisher."""
    rng = random.Random(corpus.SEED + 1)
    with session_factory() as session:
        publishers = [_publisher(rng, i) for i in range(10)]
        authors = [_author(rng) for _ in range(20)]
        session.add_all(publishers + authors)
        session.flush()
        books = [
            models.Book(
                title=_title(rng),
                year=rng.randint(1990, 2024),
                author_id=authors[i % len(authors)].id,
                publisher_id=publishers[i % len(publishers)].id,
            )
            for i in range(N_BOOKS)
        ]
        session.add_all(books)
        session.commit()
        for b in books:
            session.refresh(b)
        yield books


@pytest.fixture(scope="session")
def seeded_authors_with_books(
    session_factory: sessionmaker[Session],
) -> Generator[list[models.Author], None, None]:
    """100 authors each owning K books — powers loading-strategy + 1-M mutation."""
    rng = random.Random(corpus.SEED + 2)
    with session_factory() as session:
        publishers = [_publisher(rng, i) for i in range(10)]
        session.add_all(publishers)
        session.flush()
        authors = []
        for _ in range(N_AUTHORS):
            author = _author(rng)
            author.books = [
                models.Book(
                    title=_title(rng),
                    year=rng.randint(1990, 2024),
                    publisher_id=publishers[j % len(publishers)].id,
                )
                for j in range(K_BOOKS_PER_AUTHOR)
            ]
            authors.append(author)
        session.add_all(authors)
        session.commit()
        for a in authors:
            session.refresh(a)
        yield authors


@pytest.fixture(scope="session")
def seeded_publisher(
    session_factory: sessionmaker[Session],
) -> Generator[models.Publisher, None, None]:
    """One committed publisher, for attaching freshly-built books in mutations."""
    with session_factory() as session:
        publisher = models.Publisher(name="Mutation Publisher", country="USA")
        session.add(publisher)
        session.commit()
        session.refresh(publisher)
        yield publisher


@pytest.fixture(scope="session")
def seeded_categories(
    session_factory: sessionmaker[Session],
) -> Generator[list[models.Category], None, None]:
    """A reusable pool of categories for M-M associate benchmarks."""
    with session_factory() as session:
        categories = [
            models.Category(name=name, description=f"{name} description")
            for name in corpus.CATEGORY_NAMES
        ]
        session.add_all(categories)
        session.commit()
        for c in categories:
            session.refresh(c)
        yield categories


@pytest.fixture(scope="session")
def seeded_books_with_categories(
    session_factory: sessionmaker[Session],
) -> Generator[list[models.Book], None, None]:
    """50 books each tagged with C categories (M-M) — powers M-M load/mutation."""
    rng = random.Random(corpus.SEED + 3)
    with session_factory() as session:
        publisher = _publisher(rng, 99)
        author = _author(rng)
        categories = [
            models.Category(name=f"MMCat {i}", description="bench")
            for i in range(N_CATEGORIES)
        ]
        session.add_all([publisher, author, *categories])
        session.flush()
        books = []
        for _ in range(50):
            book = models.Book(
                title=_title(rng),
                year=rng.randint(1990, 2024),
                author_id=author.id,
                publisher_id=publisher.id,
            )
            book.categories = rng.sample(categories, C_CATEGORIES_PER_BOOK)
            books.append(book)
        session.add_all(books)
        session.commit()
        for b in books:
            session.refresh(b)
        yield books


@pytest.fixture(scope="session")
def seeded_books_with_reviews(
    session_factory: sessionmaker[Session],
) -> Generator[list[models.Book], None, None]:
    """50 books each with R reviews (1-M) — powers 1-M load."""
    rng = random.Random(corpus.SEED + 4)
    with session_factory() as session:
        publisher = _publisher(rng, 98)
        author = _author(rng)
        session.add_all([publisher, author])
        session.flush()
        books = []
        for _ in range(50):
            book = models.Book(
                title=_title(rng),
                year=rng.randint(1990, 2024),
                author_id=author.id,
                publisher_id=publisher.id,
            )
            book.reviews = [
                models.Review(
                    reviewer_name=f"Reviewer {rng.randint(1, 999)}",
                    rating=rng.randint(1, 5),
                    comment="A benchmark review comment.",
                )
                for _ in range(R_REVIEWS_PER_BOOK)
            ]
            books.append(book)
        session.add_all(books)
        session.commit()
        for b in books:
            session.refresh(b)
        yield books


@pytest.fixture(scope="session")
def seeded_blog_posts(
    session_factory: sessionmaker[Session],
) -> Generator[list[models.BlogPost], None, None]:
    """100 blog posts with author + M-M tags — powers association-proxy reads."""
    rng = random.Random(corpus.SEED + 10)
    with session_factory() as session:
        authors = [models.BlogAuthor(name=n) for n in corpus.BLOG_AUTHOR_NAMES]
        tags = [models.BlogTag(label=w) for w in corpus.TAG_WORDS]
        session.add_all(authors + tags)
        session.flush()
        posts = []
        for i in range(N_BLOG_POSTS):
            post = models.BlogPost(
                title=(
                    f"The {rng.choice(corpus.BLOG_ADJECTIVES)} "
                    f"{rng.choice(corpus.BLOG_NOUNS)} {rng.randint(1, 99)}"
                ),
                author_id=authors[i % len(authors)].id,
            )
            post.tags = rng.sample(tags, rng.randint(1, 5))
            posts.append(post)
        session.add_all(posts)
        session.commit()
        for p in posts:
            session.refresh(p)
        yield posts


@pytest.fixture(scope="session")
def seeded_shelf(
    session_factory: sessionmaker[Session],
) -> Generator[models.Shelf, None, None]:
    """One shelf with N items keyed by label — powers RelationMap mutation."""
    with session_factory() as session:
        shelf = models.Shelf(name="Benchmark Shelf")
        session.add(shelf)
        session.flush()
        session.add_all(
            models.ShelfItem(
                label=f"slot-{i}", description=f"item {i}", shelf_id=shelf.id
            )
            for i in range(N_SHELF_ITEMS)
        )
        session.commit()
        session.refresh(shelf)
        yield shelf


@pytest.fixture(scope="session")
def seeded_warehouse(
    session_factory: sessionmaker[Session],
) -> Generator[models.Warehouse, None, None]:
    """One warehouse with grouped items + a manager — powers RelationGroupMap mutation."""
    rng = random.Random(corpus.SEED + 5)
    with session_factory() as session:
        manager = models.WarehouseManager(name="Benchmark Manager")
        session.add(manager)
        session.flush()
        warehouse = models.Warehouse(name="Benchmark Warehouse", manager_id=manager.id)
        session.add(warehouse)
        session.flush()
        session.add_all(
            models.WarehouseItem(
                category=corpus.WAREHOUSE_GROUP_NAMES[g],
                name=f"{corpus.WAREHOUSE_GROUP_NAMES[g]}-{k}",
                quantity=rng.randint(1, 100),
                warehouse_id=warehouse.id,
            )
            for g in range(WAREHOUSE_GROUPS)
            for k in range(ITEMS_PER_GROUP)
        )
        session.commit()
        session.refresh(warehouse)
        yield warehouse


@pytest.fixture(scope="session")
def create_author_data() -> list[dict[str, Any]]:
    """Author create payloads ({name, write_field}); enough for bulk n=100."""
    return builders.create_author_dicts(100)


@pytest.fixture(scope="session")
def create_nested_book_data() -> list[dict[str, Any]]:
    """Book create payloads with nested author + publisher for create benchmarks."""
    return builders.create_nested_book_dicts(50)


@pytest.fixture(scope="session")
def seeded_article(
    session_factory: sessionmaker[Session],
) -> Generator[tuple[models.Article, list[models.GeneratedFile]], None, None]:
    """One article + a pool of generated files — powers association-proxy creator."""
    with session_factory() as session:
        article = models.Article(title="Benchmark Article")
        files = [
            models.GeneratedFile(filename=f"file-{i}.bin", size=i * 100)
            for i in range(N_GENERATED_FILES)
        ]
        session.add_all([article, *files])
        session.commit()
        session.refresh(article)
        for f in files:
            session.refresh(f)
        yield article, files
