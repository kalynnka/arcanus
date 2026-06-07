"""Pure, deterministic builders that produce plain dict payloads for benchmarks.

No pytest, no ORM, no Pydantic imports — just dicts seeded from `corpus`. The
same payloads validate under both the pure-Pydantic reference schemas and the
arcanus transmuters, so every Axis-A comparison feeds identical input to both
sides. Each builder takes its own `random.Random(SEED)` so call order never
changes another builder's output.
"""

from __future__ import annotations

import random
from typing import Any

from benchmark.data import corpus


def _rng(salt: int = 0) -> random.Random:
    return random.Random(corpus.SEED + salt)


def author_dicts(n: int) -> list[dict[str, Any]]:
    """Flat authors: ``{id, name, field}``."""
    rng = _rng()
    return [
        {
            "id": i,
            "name": f"{rng.choice(corpus.AUTHOR_NAMES)} {rng.randint(100, 999)}",
            "field": rng.choice(corpus.FIELDS),
        }
        for i in range(n)
    ]


def _author_dict(rng: random.Random, idx: int) -> dict[str, Any]:
    return {
        "id": idx,
        "name": f"{rng.choice(corpus.AUTHOR_NAMES)} {rng.randint(100, 999)}",
        "field": rng.choice(corpus.FIELDS),
    }


def _publisher_dict(rng: random.Random, idx: int) -> dict[str, Any]:
    return {
        "id": idx,
        "name": f"Publisher {rng.choice(corpus.PUBLISHER_KINDS)} {rng.randint(1, 50)}",
        "country": rng.choice(corpus.COUNTRIES),
    }


def _book_title(rng: random.Random) -> str:
    return (
        f"The {rng.choice(corpus.BOOK_ADJECTIVES)} "
        f"{rng.choice(corpus.BOOK_NOUNS)} {rng.randint(1, 99)}"
    )


def nested_book_dicts(n: int) -> list[dict[str, Any]]:
    """Books with one level of nested author + publisher."""
    rng = _rng(1)
    return [
        {
            "id": i,
            "title": _book_title(rng),
            "year": rng.randint(1990, 2024),
            "author": _author_dict(rng, i),
            "publisher": _publisher_dict(rng, i % 5),
        }
        for i in range(n)
    ]


def deep_author_dicts(n_authors: int, books_per: int) -> list[dict[str, Any]]:
    """Authors each owning a ``books`` collection (each book carries its author)."""
    rng = _rng(2)
    authors = []
    for i in range(n_authors):
        author = _author_dict(rng, i)
        books = [
            {
                "id": i * books_per + j,
                "title": _book_title(rng),
                "year": rng.randint(1995, 2024),
                "author": dict(author),
                "publisher": _publisher_dict(rng, j % 5),
            }
            for j in range(books_per)
        ]
        authors.append({**author, "books": books})
    return authors


def _stub_company(rng: random.Random) -> dict[str, Any]:
    return {
        "name": f"Company {rng.randint(100, 999)}",
        "industry": rng.choice(("Tech", "Finance", "Healthcare", "Retail")),
    }


def graph_company_dicts(
    n: int, depts_per: int = 3, emps_per: int = 4
) -> list[dict[str, Any]]:
    """Finite, acyclic company graphs valid for both Company schema and transmuter.

    Wide multi-relation shape: each company has a ``departments`` collection, an
    ``employees`` collection and a scalar ``ceo`` relation. Children reference
    *stub* parents (empty child lists) so the payload is finite — pure Pydantic
    cannot validate true cycles, so both sides receive the same acyclic graph.
    """
    rng = _rng(3)
    companies = []
    for _ in range(n):
        stub_company = _stub_company(rng)
        stub_department = {
            "name": f"Dept {rng.randint(1, 99)}",
            "budget": rng.randint(100_000, 5_000_000),
            "company": stub_company,
        }
        employees = [
            {
                "name": f"Employee {rng.randint(100, 999)}",
                "title": rng.choice(("Engineer", "Manager", "Analyst", "Director")),
                "salary": rng.randint(50_000, 200_000),
                "company": stub_company,
                "department": stub_department,
            }
            for _ in range(emps_per)
        ]
        departments = [
            {
                "name": f"Dept {rng.randint(1, 99)}",
                "budget": rng.randint(100_000, 5_000_000),
                "company": stub_company,
                "employees": employees,
            }
            for _ in range(depts_per)
        ]
        companies.append(
            {
                "name": f"Company {rng.randint(100, 999)}",
                "industry": rng.choice(("Tech", "Finance", "Healthcare", "Retail")),
                "departments": departments,
                "employees": employees,
                "ceo": employees[0] if employees else None,
            }
        )
    return companies


def _tag_dict(rng: random.Random, idx: int) -> dict[str, Any]:
    return {"id": idx, "name": f"{rng.choice(corpus.TAG_WORDS)}-{idx}"}


def catalog_dicts(n: int, tags_per: int = 6) -> list[dict[str, Any]]:
    """Catalogs with a ``tags`` dict keyed by label (RelationMap shape)."""
    rng = _rng(4)
    catalogs = []
    for i in range(n):
        tags = {
            corpus.TAG_WORDS[j % len(corpus.TAG_WORDS)]: _tag_dict(
                rng, i * tags_per + j
            )
            for j in range(tags_per)
        }
        catalogs.append({"id": i, "title": f"Catalog {i}", "tags": tags})
    return catalogs


def grouped_catalog_dicts(
    n: int, groups: int = 3, per_group: int = 4
) -> list[dict[str, Any]]:
    """Catalogs with a ``tags`` dict-of-lists (RelationGroupMap shape)."""
    rng = _rng(5)
    catalogs = []
    for i in range(n):
        tags = {
            corpus.WAREHOUSE_GROUP_NAMES[g % len(corpus.WAREHOUSE_GROUP_NAMES)]: [
                _tag_dict(rng, i * groups * per_group + g * per_group + k)
                for k in range(per_group)
            ]
            for g in range(groups)
        }
        catalogs.append({"id": i, "title": f"Grouped {i}", "tags": tags})
    return catalogs


def gallery_dicts(n: int) -> list[dict[str, Any]]:
    """Galleries with a typed ``media`` map (TypedRelationMap shape)."""
    rng = _rng(6)
    galleries = []
    for i in range(n):
        galleries.append(
            {
                "id": i,
                "name": f"Gallery {i}",
                "media": {
                    "image": {
                        "slot": "image",
                        "name": f"image-{i}.png",
                        "media_type": "image",
                        "width": rng.randint(320, 1920),
                        "height": rng.randint(240, 1080),
                    },
                    "video": {
                        "slot": "video",
                        "name": f"video-{i}.mp4",
                        "media_type": "video",
                        "duration": rng.uniform(10.0, 600.0),
                    },
                },
            }
        )
    return galleries


def image_media_dicts(n: int) -> list[dict[str, Any]]:
    """Flat image-media payloads (polymorphic subtype shape)."""
    rng = _rng(7)
    return [
        {
            "slot": "image",
            "name": f"image-{i}.png",
            "media_type": "image",
            "width": rng.randint(320, 1920),
            "height": rng.randint(240, 1080),
        }
        for i in range(n)
    ]


def create_author_dicts(n: int) -> list[dict[str, Any]]:
    """Author create payloads using the ``write_field`` alias (no id)."""
    rng = _rng(8)
    return [
        {
            "name": f"{rng.choice(corpus.AUTHOR_NAMES)} {rng.randint(100, 999)}",
            "write_field": rng.choice(corpus.FIELDS),
        }
        for _ in range(n)
    ]


def create_nested_book_dicts(n: int) -> list[dict[str, Any]]:
    """Book create payloads with nested author + publisher (no ids)."""
    rng = _rng(9)
    return [
        {
            "title": _book_title(rng),
            "year": rng.randint(1990, 2024),
            "author": {
                "name": f"{rng.choice(corpus.AUTHOR_NAMES)} {rng.randint(100, 999)}",
                "field": rng.choice(corpus.FIELDS),
            },
            "publisher": {
                "name": f"Publisher {rng.choice(corpus.PUBLISHER_KINDS)} {rng.randint(1, 50)}",
                "country": rng.choice(corpus.COUNTRIES),
            },
        }
        for _ in range(n)
    ]


def create_deep_author_dicts(n: int, books_per: int) -> list[dict[str, Any]]:
    """Author create payloads each carrying a list of books (no ids)."""
    rng = _rng(10)
    return [
        {
            "name": f"{rng.choice(corpus.AUTHOR_NAMES)} {rng.randint(100, 999)}",
            "field": rng.choice(corpus.FIELDS),
            "books": [
                {"title": _book_title(rng), "year": rng.randint(1990, 2024)}
                for _ in range(books_per)
            ],
        }
        for _ in range(n)
    ]
