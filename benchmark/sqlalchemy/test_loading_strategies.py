"""Axis B — relationship loading strategies.

Compares the option-translation + result-adaptation cost arcanus adds for each
eager strategy (selectin / subquery / joined) and relationship kind (1-M, M-M)
versus hand-written SQLAlchemy options + Pydantic validation. Context = pure ORM.
Each group targets a fixed slice of the *specific* seeded rows (by id) so the
strategy is the only variable and results don't depend on seed/DB ordering.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import joinedload as sa_joinedload
from sqlalchemy.orm import selectinload as sa_selectinload
from sqlalchemy.orm import subqueryload as sa_subqueryload

from arcanus.materia.sqlalchemy import joinedload, selectinload, subqueryload
from benchmark.data import ref_schemas as R
from tests import models, schemas
from tests.transmuters import Author, Book

LIMIT = 20


class TestSelectinloadBooks:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="load-selectinload-books")
    def test_sqlalchemy_selectinload(
        self, benchmark, session_factory, seeded_authors_with_books
    ):
        ids = [a.id for a in seeded_authors_with_books[:LIMIT]]

        def read():
            with session_factory() as session:
                rows = session.scalars(
                    select(models.Author)
                    .where(models.Author.id.in_(ids))
                    .options(sa_selectinload(models.Author.books))
                ).all()
                assert sum(len(a.books) for a in rows) > 0

        benchmark(read)

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="load-selectinload-books")
    def test_pydantic_sqlalchemy_selectinload(
        self, benchmark, session_factory, seeded_authors_with_books
    ):
        ids = [a.id for a in seeded_authors_with_books[:LIMIT]]

        def read():
            with session_factory() as session:
                rows = session.scalars(
                    select(models.Author)
                    .where(models.Author.id.in_(ids))
                    .options(sa_selectinload(models.Author.books))
                ).all()
                validated = [R.AuthorWithBooksRef.model_validate(a) for a in rows]
                assert sum(len(a.books) for a in validated) > 0

        benchmark(read)

    @pytest.mark.benchmark(group="load-selectinload-books")
    def test_arcanus_selectinload(
        self, benchmark, arcanus_session_factory, seeded_authors_with_books
    ):
        ids = [a.id for a in seeded_authors_with_books[:LIMIT]]

        def read():
            with arcanus_session_factory() as session:
                rows = session.scalars(
                    select(Author)
                    .where(Author["id"].in_(ids))
                    .options(selectinload(Author["books"]))
                ).all()
                assert sum(len(list(a.books)) for a in rows) > 0

        benchmark(read)


class TestSubqueryloadBooks:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="load-subqueryload-books")
    def test_sqlalchemy_subqueryload(
        self, benchmark, session_factory, seeded_authors_with_books
    ):
        ids = [a.id for a in seeded_authors_with_books[:LIMIT]]

        def read():
            with session_factory() as session:
                rows = session.scalars(
                    select(models.Author)
                    .where(models.Author.id.in_(ids))
                    .options(sa_subqueryload(models.Author.books))
                ).all()
                assert sum(len(a.books) for a in rows) > 0

        benchmark(read)

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="load-subqueryload-books")
    def test_pydantic_sqlalchemy_subqueryload(
        self, benchmark, session_factory, seeded_authors_with_books
    ):
        ids = [a.id for a in seeded_authors_with_books[:LIMIT]]

        def read():
            with session_factory() as session:
                rows = session.scalars(
                    select(models.Author)
                    .where(models.Author.id.in_(ids))
                    .options(sa_subqueryload(models.Author.books))
                ).all()
                validated = [R.AuthorWithBooksRef.model_validate(a) for a in rows]
                assert sum(len(a.books) for a in validated) > 0

        benchmark(read)

    @pytest.mark.benchmark(group="load-subqueryload-books")
    def test_arcanus_subqueryload(
        self, benchmark, arcanus_session_factory, seeded_authors_with_books
    ):
        ids = [a.id for a in seeded_authors_with_books[:LIMIT]]

        def read():
            with arcanus_session_factory() as session:
                rows = session.scalars(
                    select(Author)
                    .where(Author["id"].in_(ids))
                    .options(subqueryload(Author["books"]))
                ).all()
                assert sum(len(list(a.books)) for a in rows) > 0

        benchmark(read)


class TestJoinedloadBookRels:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="load-joinedload-book-rels")
    def test_sqlalchemy_joinedload(self, benchmark, session_factory, seeded_books):
        ids = [b.id for b in seeded_books[:LIMIT]]

        def read():
            with session_factory() as session:
                rows = session.scalars(
                    select(models.Book)
                    .where(models.Book.id.in_(ids))
                    .options(
                        sa_joinedload(models.Book.author),
                        sa_joinedload(models.Book.publisher),
                    )
                ).all()
                assert all(b.author is not None for b in rows)

        benchmark(read)

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="load-joinedload-book-rels")
    def test_pydantic_sqlalchemy_joinedload(
        self, benchmark, session_factory, seeded_books
    ):
        ids = [b.id for b in seeded_books[:LIMIT]]

        def read():
            with session_factory() as session:
                rows = session.scalars(
                    select(models.Book)
                    .where(models.Book.id.in_(ids))
                    .options(
                        sa_joinedload(models.Book.author),
                        sa_joinedload(models.Book.publisher),
                    )
                ).all()
                validated = [schemas.BookFlat.model_validate(b) for b in rows]
                assert all(b.author is not None for b in validated)

        benchmark(read)

    @pytest.mark.benchmark(group="load-joinedload-book-rels")
    def test_arcanus_joinedload(self, benchmark, arcanus_session_factory, seeded_books):
        ids = [b.id for b in seeded_books[:LIMIT]]

        def read():
            with arcanus_session_factory() as session:
                rows = session.scalars(
                    select(Book)
                    .where(Book["id"].in_(ids))
                    .options(joinedload(Book["author"]), joinedload(Book["publisher"]))
                ).all()
                assert all(b.author.value is not None for b in rows)

        benchmark(read)


class TestLoadCategoriesMM:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="load-categories-mm")
    def test_sqlalchemy_categories(
        self, benchmark, session_factory, seeded_books_with_categories
    ):
        ids = [b.id for b in seeded_books_with_categories[:LIMIT]]

        def read():
            with session_factory() as session:
                rows = session.scalars(
                    select(models.Book)
                    .where(models.Book.id.in_(ids))
                    .options(sa_selectinload(models.Book.categories))
                ).all()
                assert sum(len(b.categories) for b in rows) > 0

        benchmark(read)

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="load-categories-mm")
    def test_pydantic_sqlalchemy_categories(
        self, benchmark, session_factory, seeded_books_with_categories
    ):
        ids = [b.id for b in seeded_books_with_categories[:LIMIT]]

        def read():
            with session_factory() as session:
                rows = session.scalars(
                    select(models.Book)
                    .where(models.Book.id.in_(ids))
                    .options(sa_selectinload(models.Book.categories))
                ).all()
                validated = [R.BookWithCategoriesRef.model_validate(b) for b in rows]
                assert sum(len(b.categories) for b in validated) > 0

        benchmark(read)

    @pytest.mark.benchmark(group="load-categories-mm")
    def test_arcanus_categories(
        self, benchmark, arcanus_session_factory, seeded_books_with_categories
    ):
        ids = [b.id for b in seeded_books_with_categories[:LIMIT]]

        def read():
            with arcanus_session_factory() as session:
                rows = session.scalars(
                    select(Book)
                    .where(Book["id"].in_(ids))
                    .options(selectinload(Book["categories"]))
                ).all()
                assert sum(len(list(b.categories)) for b in rows) > 0

        benchmark(read)


class TestLoadReviews1M:
    @pytest.mark.baseline
    @pytest.mark.benchmark(group="load-reviews-1m")
    def test_sqlalchemy_reviews(
        self, benchmark, session_factory, seeded_books_with_reviews
    ):
        ids = [b.id for b in seeded_books_with_reviews[:LIMIT]]

        def read():
            with session_factory() as session:
                rows = session.scalars(
                    select(models.Book)
                    .where(models.Book.id.in_(ids))
                    .options(sa_selectinload(models.Book.reviews))
                ).all()
                assert sum(len(b.reviews) for b in rows) > 0

        benchmark(read)

    @pytest.mark.baseline
    @pytest.mark.benchmark(group="load-reviews-1m")
    def test_pydantic_sqlalchemy_reviews(
        self, benchmark, session_factory, seeded_books_with_reviews
    ):
        ids = [b.id for b in seeded_books_with_reviews[:LIMIT]]

        def read():
            with session_factory() as session:
                rows = session.scalars(
                    select(models.Book)
                    .where(models.Book.id.in_(ids))
                    .options(sa_selectinload(models.Book.reviews))
                ).all()
                validated = [R.BookWithReviewsRef.model_validate(b) for b in rows]
                assert sum(len(b.reviews) for b in validated) > 0

        benchmark(read)

    @pytest.mark.benchmark(group="load-reviews-1m")
    def test_arcanus_reviews(
        self, benchmark, arcanus_session_factory, seeded_books_with_reviews
    ):
        ids = [b.id for b in seeded_books_with_reviews[:LIMIT]]

        def read():
            with arcanus_session_factory() as session:
                rows = session.scalars(
                    select(Book)
                    .where(Book["id"].in_(ids))
                    .options(selectinload(Book["reviews"]))
                ).all()
                assert sum(len(list(b.reviews)) for b in rows) > 0

        benchmark(read)
