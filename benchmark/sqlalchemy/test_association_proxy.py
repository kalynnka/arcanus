"""
Association Proxy Benchmark Tests

This module benchmarks arcanus's handling of SQLAlchemy association proxies
against common patterns. Comparing three approaches:

1. PURE SQLALCHEMY (Baseline)
   - Access association proxy values directly on ORM objects

2. PYDANTIC + SQLALCHEMY (Common Pattern)
   - Access proxy values on ORM objects, then validate with Pydantic

3. arcanus (Combined)
   - Transmuter automatically resolves proxy fields from loaded relationships

Run locally:  pytest benchmark/sqlalchemy/test_association_proxy.py -v --benchmark-enable
With CodSpeed: pytest benchmark/sqlalchemy/test_association_proxy.py --codspeed
"""

from __future__ import annotations

import random

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from tests import models, schemas
from tests.transmuters import BlogPost

# Batch size for benchmark tests
BATCH_SIZE = 50


class TestReadSingleBlogPostWithProxy:
    """
    Benchmark reading a single blog post and accessing association proxy values.

    Simulates: GET /api/posts/{id} where the response includes author_name (scalar proxy)
    Each iteration reads one randomly selected post with eagerly loaded author.
    """

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="read-single-post-proxy")
    def test_sqlalchemy_read(
        self,
        benchmark,
        session_factory,
        seeded_blog_posts: list[models.BlogPost],
    ):
        """Pure SQLAlchemy: Query with selectinload, access proxy."""
        post = random.choice(seeded_blog_posts)
        post_id = post.id

        def read():
            with session_factory() as session:
                stmt = (
                    select(models.BlogPost)
                    .where(models.BlogPost.id == post_id)
                    .options(selectinload(models.BlogPost.author))
                )
                result = session.scalars(stmt).first()
                assert result is not None
                # Access the scalar association proxy
                _ = result.author_name

        benchmark(read)

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="read-single-post-proxy")
    def test_pydantic_sqlalchemy_read(
        self,
        benchmark,
        session_factory,
        seeded_blog_posts: list[models.BlogPost],
    ):
        """Pydantic + SQLAlchemy: Query, access proxy, validate."""
        post = random.choice(seeded_blog_posts)
        post_id = post.id

        def read():
            with session_factory() as session:
                stmt = (
                    select(models.BlogPost)
                    .where(models.BlogPost.id == post_id)
                    .options(selectinload(models.BlogPost.author))
                )
                orm_post = session.scalars(stmt).first()
                # Build dict with proxy values resolved
                data = {
                    "id": orm_post.id,
                    "title": orm_post.title,
                    "author_id": orm_post.author_id,
                    "author_name": orm_post.author_name,
                }
                validated = schemas.BlogPostFlat.model_validate(data)
                assert validated is not None

        benchmark(read)

    @pytest.mark.benchmark(group="read-single-post-proxy")
    def test_arcanus_read(
        self,
        benchmark,
        arcanus_session_factory,
        seeded_blog_posts: list[models.BlogPost],
    ):
        """arcanus: Transmuter resolves proxy fields automatically."""
        post = random.choice(seeded_blog_posts)
        post_id = post.id

        def read():
            with arcanus_session_factory() as session:
                stmt = (
                    select(BlogPost)
                    .where(BlogPost["id"] == post_id)
                    .options(selectinload(BlogPost["author"]))
                )
                result = session.scalars(stmt).first()
                assert result is not None
                assert result.author_name is not None

        benchmark(read)


class TestReadManyBlogPostsWithProxy:
    """
    Benchmark reading many blog posts with association proxy values.

    Simulates: GET /api/posts?limit=50 where each post includes author_name
    Each iteration fetches 50 posts with eagerly loaded authors.
    """

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="read-many-posts-proxy")
    def test_sqlalchemy_read_many(
        self,
        benchmark,
        session_factory,
        seeded_blog_posts: list[models.BlogPost],
    ):
        """Pure SQLAlchemy: Query list, access proxies."""

        def read():
            with session_factory() as session:
                stmt = (
                    select(models.BlogPost)
                    .options(selectinload(models.BlogPost.author))
                    .limit(BATCH_SIZE)
                )
                results = session.scalars(stmt).all()
                # Access scalar proxy on each
                for r in results:
                    _ = r.author_name
                assert len(results) == BATCH_SIZE

        benchmark(read)

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="read-many-posts-proxy")
    def test_pydantic_sqlalchemy_read_many(
        self,
        benchmark,
        session_factory,
        seeded_blog_posts: list[models.BlogPost],
    ):
        """Pydantic + SQLAlchemy: Query list, resolve proxies, validate."""

        def read():
            with session_factory() as session:
                stmt = (
                    select(models.BlogPost)
                    .options(selectinload(models.BlogPost.author))
                    .limit(BATCH_SIZE)
                )
                orm_posts = session.scalars(stmt).all()
                validated = [
                    schemas.BlogPostFlat.model_validate(
                        {
                            "id": p.id,
                            "title": p.title,
                            "author_id": p.author_id,
                            "author_name": p.author_name,
                        }
                    )
                    for p in orm_posts
                ]
                assert len(validated) == BATCH_SIZE

        benchmark(read)

    @pytest.mark.benchmark(group="read-many-posts-proxy")
    def test_arcanus_read_many(
        self,
        benchmark,
        arcanus_session_factory,
        seeded_blog_posts: list[models.BlogPost],
    ):
        """arcanus: Transmuters resolve proxy fields automatically."""

        def read():
            with arcanus_session_factory() as session:
                stmt = (
                    select(BlogPost)
                    .options(selectinload(BlogPost["author"]))
                    .limit(BATCH_SIZE)
                )
                results = session.scalars(stmt).all()
                for r in results:
                    assert r.author_name is not None
                assert len(results) == BATCH_SIZE

        benchmark(read)


class TestReadBlogPostWithCollectionProxy:
    """
    Benchmark reading blog posts with collection association proxy (tag_labels).

    Simulates: GET /api/posts/{id} where the response includes tag_labels (collection proxy)
    Each iteration reads one post with eagerly loaded tags.
    """

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="read-single-post-collection-proxy")
    def test_sqlalchemy_read(
        self,
        benchmark,
        session_factory,
        seeded_blog_posts: list[models.BlogPost],
    ):
        """Pure SQLAlchemy: Query with selectinload, access collection proxy."""
        post = random.choice(seeded_blog_posts)
        post_id = post.id

        def read():
            with session_factory() as session:
                stmt = (
                    select(models.BlogPost)
                    .where(models.BlogPost.id == post_id)
                    .options(selectinload(models.BlogPost.tags))
                )
                result = session.scalars(stmt).first()
                assert result is not None
                _ = list(result.tag_labels)

        benchmark(read)

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="read-single-post-collection-proxy")
    def test_pydantic_sqlalchemy_read(
        self,
        benchmark,
        session_factory,
        seeded_blog_posts: list[models.BlogPost],
    ):
        """Pydantic + SQLAlchemy: Query, access collection proxy, validate."""
        post = random.choice(seeded_blog_posts)
        post_id = post.id

        def read():
            with session_factory() as session:
                stmt = (
                    select(models.BlogPost)
                    .where(models.BlogPost.id == post_id)
                    .options(selectinload(models.BlogPost.tags))
                )
                orm_post = session.scalars(stmt).first()
                data = {
                    "id": orm_post.id,
                    "title": orm_post.title,
                    "author_id": orm_post.author_id,
                    "tag_labels": list(orm_post.tag_labels),
                }
                validated = schemas.BlogPostFlat.model_validate(data)
                assert validated is not None

        benchmark(read)

    @pytest.mark.benchmark(group="read-single-post-collection-proxy")
    def test_arcanus_read(
        self,
        benchmark,
        arcanus_session_factory,
        seeded_blog_posts: list[models.BlogPost],
    ):
        """arcanus: Transmuter resolves collection proxy automatically."""
        post = random.choice(seeded_blog_posts)
        post_id = post.id

        def read():
            with arcanus_session_factory() as session:
                stmt = (
                    select(BlogPost)
                    .where(BlogPost["id"] == post_id)
                    .options(selectinload(BlogPost["tags"]))
                )
                result = session.scalars(stmt).first()
                assert result is not None
                assert len(result.tag_labels) > 0

        benchmark(read)


class TestReadManyBlogPostsWithAllProxies:
    """
    Benchmark reading many blog posts with both scalar and collection proxies.

    Simulates: GET /api/posts?limit=50 with author_name and tag_labels included
    Each iteration fetches 50 posts with both relationships eagerly loaded.
    """

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="read-many-posts-all-proxies")
    def test_sqlalchemy_read_many(
        self,
        benchmark,
        session_factory,
        seeded_blog_posts: list[models.BlogPost],
    ):
        """Pure SQLAlchemy: Query list, access both proxies."""

        def read():
            with session_factory() as session:
                stmt = (
                    select(models.BlogPost)
                    .options(
                        selectinload(models.BlogPost.author),
                        selectinload(models.BlogPost.tags),
                    )
                    .limit(BATCH_SIZE)
                )
                results = session.scalars(stmt).all()
                for r in results:
                    _ = r.author_name
                    _ = list(r.tag_labels)
                assert len(results) == BATCH_SIZE

        benchmark(read)

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="read-many-posts-all-proxies")
    def test_pydantic_sqlalchemy_read_many(
        self,
        benchmark,
        session_factory,
        seeded_blog_posts: list[models.BlogPost],
    ):
        """Pydantic + SQLAlchemy: Query list, resolve all proxies, validate."""

        def read():
            with session_factory() as session:
                stmt = (
                    select(models.BlogPost)
                    .options(
                        selectinload(models.BlogPost.author),
                        selectinload(models.BlogPost.tags),
                    )
                    .limit(BATCH_SIZE)
                )
                orm_posts = session.scalars(stmt).all()
                validated = [
                    schemas.BlogPostFlat.model_validate(
                        {
                            "id": p.id,
                            "title": p.title,
                            "author_id": p.author_id,
                            "author_name": p.author_name,
                            "tag_labels": list(p.tag_labels),
                        }
                    )
                    for p in orm_posts
                ]
                assert len(validated) == BATCH_SIZE

        benchmark(read)

    @pytest.mark.benchmark(group="read-many-posts-all-proxies")
    def test_arcanus_read_many(
        self,
        benchmark,
        arcanus_session_factory,
        seeded_blog_posts: list[models.BlogPost],
    ):
        """arcanus: Transmuters resolve all proxy fields automatically."""

        def read():
            with arcanus_session_factory() as session:
                stmt = (
                    select(BlogPost)
                    .options(
                        selectinload(BlogPost["author"]),
                        selectinload(BlogPost["tags"]),
                    )
                    .limit(BATCH_SIZE)
                )
                results = session.scalars(stmt).all()
                for r in results:
                    assert r.author_name is not None
                    assert len(r.tag_labels) > 0
                assert len(results) == BATCH_SIZE

        benchmark(read)


class TestSerializeBlogPostWithProxies:
    """
    Benchmark serializing blog posts with proxy fields to dict.

    Simulates: Converting query results with proxy fields to JSON response
    Each iteration serializes 50 posts including proxy values.
    """

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="serialize-post-proxy-dict")
    def test_sqlalchemy_serialize(
        self,
        benchmark,
        session_factory,
        seeded_blog_posts: list[models.BlogPost],
    ):
        """Pure SQLAlchemy: Manual dict construction with proxy values."""

        def serialize():
            with session_factory() as session:
                stmt = (
                    select(models.BlogPost)
                    .options(
                        selectinload(models.BlogPost.author),
                        selectinload(models.BlogPost.tags),
                    )
                    .limit(BATCH_SIZE)
                )
                posts = session.scalars(stmt).all()
                return [
                    {
                        "id": p.id,
                        "title": p.title,
                        "author_id": p.author_id,
                        "author_name": p.author_name,
                        "tag_labels": list(p.tag_labels),
                    }
                    for p in posts
                ]

        result = benchmark(serialize)
        assert len(result) == BATCH_SIZE

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="serialize-post-proxy-dict")
    def test_pydantic_sqlalchemy_serialize(
        self,
        benchmark,
        session_factory,
        seeded_blog_posts: list[models.BlogPost],
    ):
        """Pydantic + SQLAlchemy: Validate then dump."""

        def serialize():
            with session_factory() as session:
                stmt = (
                    select(models.BlogPost)
                    .options(
                        selectinload(models.BlogPost.author),
                        selectinload(models.BlogPost.tags),
                    )
                    .limit(BATCH_SIZE)
                )
                orm_posts = session.scalars(stmt).all()
                validated = [
                    schemas.BlogPostFlat.model_validate(
                        {
                            "id": p.id,
                            "title": p.title,
                            "author_id": p.author_id,
                            "author_name": p.author_name,
                            "tag_labels": list(p.tag_labels),
                        }
                    )
                    for p in orm_posts
                ]
                return [v.model_dump() for v in validated]

        result = benchmark(serialize)
        assert len(result) == BATCH_SIZE

    @pytest.mark.benchmark(group="serialize-post-proxy-dict")
    def test_arcanus_serialize(
        self,
        benchmark,
        arcanus_session_factory,
        seeded_blog_posts: list[models.BlogPost],
    ):
        """arcanus: model_dump with proxy fields resolved."""

        def serialize():
            with arcanus_session_factory() as session:
                stmt = (
                    select(BlogPost)
                    .options(
                        selectinload(BlogPost["author"]),
                        selectinload(BlogPost["tags"]),
                    )
                    .limit(BATCH_SIZE)
                )
                posts = session.scalars(stmt).all()
                return [p.model_dump(exclude={"author", "tags"}) for p in posts]

        result = benchmark(serialize)
        assert len(result) == BATCH_SIZE
