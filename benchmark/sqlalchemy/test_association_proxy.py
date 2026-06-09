"""Axis B — association proxies (scalar ``author_name`` + collection ``tag_labels``).

Context = pure ORM proxy access, reference = Pydantic+SQLAlchemy (resolve proxy,
then validate), candidate = arcanus transmuter resolving proxy fields
automatically. Reads and serialization over seeded blog posts.
"""

from __future__ import annotations

import random
from typing import Any

import pytest
from pytest_benchmark.fixture import BenchmarkFixture
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm import selectinload as sa_selectinload

from arcanus.materia.sqlalchemy import Session as ArcanusSession
from arcanus.materia.sqlalchemy import selectinload
from tests import models, schemas
from tests.transmuters import BlogPost

BATCH_SIZE = 50


class TestReadSinglePostScalarProxy:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="read-single-post-proxy")
    def test_sqlalchemy_read(
        self,
        benchmark: BenchmarkFixture,
        session_factory: sessionmaker[Session],
        seeded_blog_posts: list[models.BlogPost],
    ):
        post_id = random.choice(seeded_blog_posts).id

        def read() -> None:
            with session_factory() as session:
                post = session.scalars(
                    select(models.BlogPost)
                    .where(models.BlogPost.id == post_id)
                    .options(sa_selectinload(models.BlogPost.author))
                ).first()
                assert post is not None and post.author_name is not None

        benchmark(read)

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="read-single-post-proxy")
    def test_pydantic_sqlalchemy_read(
        self,
        benchmark: BenchmarkFixture,
        session_factory: sessionmaker[Session],
        seeded_blog_posts: list[models.BlogPost],
    ):
        post_id = random.choice(seeded_blog_posts).id

        def read() -> None:
            with session_factory() as session:
                post = session.scalars(
                    select(models.BlogPost)
                    .where(models.BlogPost.id == post_id)
                    .options(sa_selectinload(models.BlogPost.author))
                ).one()
                validated = schemas.BlogPostFlat.model_validate(
                    {
                        "id": post.id,
                        "title": post.title,
                        "author_id": post.author_id,
                        "author_name": post.author_name,
                    }
                )
                assert validated.author_name is not None

        benchmark(read)

    @pytest.mark.benchmark(group="read-single-post-proxy")
    def test_arcanus_read(
        self,
        benchmark: BenchmarkFixture,
        arcanus_session_factory: sessionmaker[ArcanusSession],
        seeded_blog_posts: list[models.BlogPost],
    ):
        post_id = random.choice(seeded_blog_posts).id

        def read() -> None:
            with arcanus_session_factory() as session:
                post = session.scalars(
                    select(BlogPost)
                    .where(BlogPost["id"] == post_id)
                    .options(selectinload(BlogPost["author"]))
                ).first()
                assert post is not None and post.author_name is not None

        benchmark(read)


class TestReadManyPostsScalarProxy:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="read-many-posts-proxy")
    def test_sqlalchemy_read_many(
        self,
        benchmark: BenchmarkFixture,
        session_factory: sessionmaker[Session],
        seeded_blog_posts: list[models.BlogPost],
    ):
        def read() -> None:
            with session_factory() as session:
                rows = session.scalars(
                    select(models.BlogPost)
                    .options(sa_selectinload(models.BlogPost.author))
                    .limit(BATCH_SIZE)
                ).all()
                assert all(r.author_name is not None for r in rows)

        benchmark(read)

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="read-many-posts-proxy")
    def test_pydantic_sqlalchemy_read_many(
        self,
        benchmark: BenchmarkFixture,
        session_factory: sessionmaker[Session],
        seeded_blog_posts: list[models.BlogPost],
    ):
        def read() -> None:
            with session_factory() as session:
                rows = session.scalars(
                    select(models.BlogPost)
                    .options(sa_selectinload(models.BlogPost.author))
                    .limit(BATCH_SIZE)
                ).all()
                validated = [
                    schemas.BlogPostFlat.model_validate(
                        {
                            "id": p.id,
                            "title": p.title,
                            "author_id": p.author_id,
                            "author_name": p.author_name,
                        }
                    )
                    for p in rows
                ]
                assert len(validated) == BATCH_SIZE

        benchmark(read)

    @pytest.mark.benchmark(group="read-many-posts-proxy")
    def test_arcanus_read_many(
        self,
        benchmark: BenchmarkFixture,
        arcanus_session_factory: sessionmaker[ArcanusSession],
        seeded_blog_posts: list[models.BlogPost],
    ):
        def read() -> None:
            with arcanus_session_factory() as session:
                rows = session.scalars(
                    select(BlogPost)
                    .options(selectinload(BlogPost["author"]))
                    .limit(BATCH_SIZE)
                ).all()
                assert all(r.author_name is not None for r in rows)

        benchmark(read)


class TestReadPostCollectionProxy:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="read-single-post-collection-proxy")
    def test_sqlalchemy_read(
        self,
        benchmark: BenchmarkFixture,
        session_factory: sessionmaker[Session],
        seeded_blog_posts: list[models.BlogPost],
    ):
        post_id = random.choice(seeded_blog_posts).id

        def read() -> None:
            with session_factory() as session:
                post = session.scalars(
                    select(models.BlogPost)
                    .where(models.BlogPost.id == post_id)
                    .options(sa_selectinload(models.BlogPost.tags))
                ).first()
                assert post is not None and len(list(post.tag_labels)) >= 0

        benchmark(read)

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="read-single-post-collection-proxy")
    def test_pydantic_sqlalchemy_read(
        self,
        benchmark: BenchmarkFixture,
        session_factory: sessionmaker[Session],
        seeded_blog_posts: list[models.BlogPost],
    ):
        post_id = random.choice(seeded_blog_posts).id

        def read() -> None:
            with session_factory() as session:
                post = session.scalars(
                    select(models.BlogPost)
                    .where(models.BlogPost.id == post_id)
                    .options(sa_selectinload(models.BlogPost.tags))
                ).one()
                validated = schemas.BlogPostFlat.model_validate(
                    {
                        "id": post.id,
                        "title": post.title,
                        "author_id": post.author_id,
                        "tag_labels": list(post.tag_labels),
                    }
                )
                assert validated is not None

        benchmark(read)

    @pytest.mark.benchmark(group="read-single-post-collection-proxy")
    def test_arcanus_read(
        self,
        benchmark: BenchmarkFixture,
        arcanus_session_factory: sessionmaker[ArcanusSession],
        seeded_blog_posts: list[models.BlogPost],
    ):
        post_id = random.choice(seeded_blog_posts).id

        def read() -> None:
            with arcanus_session_factory() as session:
                post = session.scalars(
                    select(BlogPost)
                    .where(BlogPost["id"] == post_id)
                    .options(selectinload(BlogPost["tags"]))
                ).first()
                assert post is not None and len(post.tag_labels) >= 0

        benchmark(read)


class TestSerializePostProxies:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="serialize-post-proxy-dict")
    def test_sqlalchemy_serialize(
        self,
        benchmark: BenchmarkFixture,
        session_factory: sessionmaker[Session],
        seeded_blog_posts: list[models.BlogPost],
    ):
        def serialize() -> list[Any]:
            with session_factory() as session:
                rows = session.scalars(
                    select(models.BlogPost)
                    .options(
                        sa_selectinload(models.BlogPost.author),
                        sa_selectinload(models.BlogPost.tags),
                    )
                    .limit(BATCH_SIZE)
                ).all()
                return [
                    {
                        "id": p.id,
                        "title": p.title,
                        "author_id": p.author_id,
                        "author_name": p.author_name,
                        "tag_labels": list(p.tag_labels),
                    }
                    for p in rows
                ]

        assert len(benchmark(serialize)) == BATCH_SIZE

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="serialize-post-proxy-dict")
    def test_pydantic_sqlalchemy_serialize(
        self,
        benchmark: BenchmarkFixture,
        session_factory: sessionmaker[Session],
        seeded_blog_posts: list[models.BlogPost],
    ):
        def serialize() -> list[Any]:
            with session_factory() as session:
                rows = session.scalars(
                    select(models.BlogPost)
                    .options(
                        sa_selectinload(models.BlogPost.author),
                        sa_selectinload(models.BlogPost.tags),
                    )
                    .limit(BATCH_SIZE)
                ).all()
                return [
                    schemas.BlogPostFlat.model_validate(
                        {
                            "id": p.id,
                            "title": p.title,
                            "author_id": p.author_id,
                            "author_name": p.author_name,
                            "tag_labels": list(p.tag_labels),
                        }
                    ).model_dump()
                    for p in rows
                ]

        assert len(benchmark(serialize)) == BATCH_SIZE

    @pytest.mark.benchmark(group="serialize-post-proxy-dict")
    def test_arcanus_serialize(
        self,
        benchmark: BenchmarkFixture,
        arcanus_session_factory: sessionmaker[ArcanusSession],
        seeded_blog_posts: list[models.BlogPost],
    ):
        def serialize() -> list[Any]:
            with arcanus_session_factory() as session:
                rows = session.scalars(
                    select(BlogPost)
                    .options(
                        selectinload(BlogPost["author"]),
                        selectinload(BlogPost["tags"]),
                    )
                    .limit(BATCH_SIZE)
                ).all()
                return [
                    p.model_dump(exclude={"author", "tags", "test_id"}) for p in rows
                ]

        assert len(benchmark(serialize)) == BATCH_SIZE
