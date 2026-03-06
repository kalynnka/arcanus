"""Tests for association_proxy field handling in SqlalchemyMateria.

Verifies that pydantic fields mapped to SQLAlchemy ``association_proxy``
descriptors are:

- Populated when the underlying relationship is already loaded (eager /
  selectinload).
- Safely skipped (fallback to the field default) when the relationship is
  **not** loaded, so that ``lazy='select'`` stays lazy and ``lazy='raise'``
  does not explode.
- Correctly handled in both ``model_validate`` and ``model_construct``
  paths.
"""

from __future__ import annotations

from sqlalchemy import Engine, select
from sqlalchemy.orm import raiseload, selectinload

from arcanus.materia.sqlalchemy import Session
from tests.models import BlogAuthor as BlogAuthorModel
from tests.models import BlogPost as BlogPostModel
from tests.models import BlogTag as BlogTagModel
from tests.transmuters import BlogPost


def _seed_post(session, *, title: str = "Hello World") -> BlogPostModel:
    """Insert a BlogPost with an author and two tags, flush and return ORM row."""
    author = BlogAuthorModel(name="Alice")
    session.add(author)
    session.flush()

    tag1 = BlogTagModel(label="python")
    tag2 = BlogTagModel(label="testing")
    session.add_all([tag1, tag2])
    session.flush()

    post = BlogPostModel(title=title, author_id=author.id, tags=[tag1, tag2])
    session.add(post)
    session.flush()
    return post


class TestAssociationProxyModelValidate:
    """Tests for association proxy handling through the model_validate path."""

    def test_scalar_proxy_included_when_relationship_loaded(self, engine: Engine):
        """author_name should be populated when author relationship is eagerly loaded."""
        with Session(engine) as session:
            orm_post = _seed_post(session)
            post_id = orm_post.id

            # Eagerly load author
            stmt = (
                select(BlogPostModel)
                .where(BlogPostModel.id == post_id)
                .options(selectinload(BlogPostModel.author))
            )
            orm_post = session.execute(stmt).scalar_one()

            result = BlogPost.model_validate(orm_post)
            assert result.author_name == "Alice"

    def test_collection_proxy_included_when_relationship_loaded(self, engine: Engine):
        """tag_labels should be populated when tags relationship is eagerly loaded."""
        with Session(engine) as session:
            orm_post = _seed_post(session)
            post_id = orm_post.id

            stmt = (
                select(BlogPostModel)
                .where(BlogPostModel.id == post_id)
                .options(selectinload(BlogPostModel.tags))
            )
            orm_post = session.execute(stmt).scalar_one()

            result = BlogPost.model_validate(orm_post)
            assert set(result.tag_labels) == {"python", "testing"}

    def test_scalar_proxy_falls_back_to_default_when_not_loaded(self, engine: Engine):
        """author_name should fall back to None when author is not loaded."""
        with Session(engine) as session:
            orm_post = _seed_post(session)

            # Expire the author relationship so it is not in inspector.dict
            session.expire(orm_post, ["author"])

            result = BlogPost.model_validate(orm_post)
            assert result.author_name is None

    def test_collection_proxy_falls_back_to_default_when_not_loaded(
        self, engine: Engine
    ):
        """tag_labels should fall back to [] when tags is not loaded."""
        with Session(engine) as session:
            orm_post = _seed_post(session)

            # Expire the tags relationship
            session.expire(orm_post, ["tags"])

            result = BlogPost.model_validate(orm_post)
            assert result.tag_labels == []

    def test_proxy_does_not_trigger_raise_load(self, engine: Engine):
        """Association proxy must not trigger loading when strategy is 'raise'."""
        with Session(engine) as session:
            orm_post = _seed_post(session)
            post_id = orm_post.id

            # Expire all loaded relationship data so the identity-map
            # instance no longer holds them in __dict__.
            session.expire(orm_post)

            # Re-query with raiseload on both relationships
            stmt = (
                select(BlogPostModel)
                .where(BlogPostModel.id == post_id)
                .options(
                    raiseload(BlogPostModel.author),
                    raiseload(BlogPostModel.tags),
                )
            )
            orm_post = session.execute(stmt).scalar_one()

            # Should NOT raise -- the proxy fields simply get their defaults
            result = BlogPost.model_validate(orm_post)
            assert result.author_name is None
            assert result.tag_labels == []

    def test_both_proxies_populated_with_full_eager_load(self, engine: Engine):
        """Both scalar and collection proxies populated when relationships loaded."""
        with Session(engine) as session:
            orm_post = _seed_post(session, title="Fully loaded")
            post_id = orm_post.id

            stmt = (
                select(BlogPostModel)
                .where(BlogPostModel.id == post_id)
                .options(
                    selectinload(BlogPostModel.author),
                    selectinload(BlogPostModel.tags),
                )
            )
            orm_post = session.execute(stmt).scalar_one()

            result = BlogPost.model_validate(orm_post)
            assert result.title == "Fully loaded"
            assert result.author_name == "Alice"
            assert set(result.tag_labels) == {"python", "testing"}


class TestAssociationProxyModelConstruct:
    """Tests for association proxy handling through the model_construct path."""

    def test_scalar_proxy_included_via_construct_when_loaded(self, engine: Engine):
        """model_construct should include proxy values when relationship loaded."""
        with Session(engine) as session:
            orm_post = _seed_post(session)
            post_id = orm_post.id

            stmt = (
                select(BlogPostModel)
                .where(BlogPostModel.id == post_id)
                .options(selectinload(BlogPostModel.author))
            )
            orm_post = session.execute(stmt).scalar_one()

            result = BlogPost.model_construct(data=orm_post)
            assert result.author_name == "Alice"

    def test_collection_proxy_included_via_construct_when_loaded(self, engine: Engine):
        """model_construct should include collection proxy values when loaded."""
        with Session(engine) as session:
            orm_post = _seed_post(session)
            post_id = orm_post.id

            stmt = (
                select(BlogPostModel)
                .where(BlogPostModel.id == post_id)
                .options(selectinload(BlogPostModel.tags))
            )
            orm_post = session.execute(stmt).scalar_one()

            result = BlogPost.model_construct(data=orm_post)
            assert set(result.tag_labels) == {"python", "testing"}

    def test_proxy_skipped_via_construct_when_not_loaded(self, engine: Engine):
        """model_construct should skip proxy values when relationship not loaded."""
        with Session(engine) as session:
            orm_post = _seed_post(session)

            # Expire the relationships
            session.expire(orm_post, ["author", "tags"])

            result = BlogPost.model_construct(data=orm_post)
            # Fields not provided to construct will not be present;
            # accessing them returns the class-level default or None.
            assert getattr(result, "author_name", None) is None

    def test_construct_does_not_trigger_raise_load(self, engine: Engine):
        """model_construct must not trigger loading when strategy is 'raise'."""
        with Session(engine) as session:
            orm_post = _seed_post(session)
            post_id = orm_post.id

            stmt = (
                select(BlogPostModel)
                .where(BlogPostModel.id == post_id)
                .options(
                    raiseload(BlogPostModel.author),
                    raiseload(BlogPostModel.tags),
                )
            )
            orm_post = session.execute(stmt).scalar_one()

            # Must not raise
            result = BlogPost.model_construct(data=orm_post)
            assert getattr(result, "author_name", None) is None


class TestAssociationProxyWithAssociations:
    """Ensure normal Relation/RelationCollection associations are unaffected."""

    def test_relation_association_still_deferred(self, engine: Engine):
        """The 'author' Relation association should still be deferred/loadable."""
        with Session(engine) as session:
            orm_post = _seed_post(session)
            post_id = orm_post.id

            stmt = (
                select(BlogPostModel)
                .where(BlogPostModel.id == post_id)
                .options(selectinload(BlogPostModel.author))
            )
            orm_post = session.execute(stmt).scalar_one()

            result = BlogPost.model_validate(orm_post)
            # proxy scalar
            assert result.author_name == "Alice"
            # association still works
            assert result.author.value.name == "Alice"

    def test_relation_collection_still_works(self, engine: Engine):
        """The 'tags' RelationCollection should still be loadable."""
        with Session(engine) as session:
            orm_post = _seed_post(session)
            post_id = orm_post.id

            stmt = (
                select(BlogPostModel)
                .where(BlogPostModel.id == post_id)
                .options(
                    selectinload(BlogPostModel.author),
                    selectinload(BlogPostModel.tags),
                )
            )
            orm_post = session.execute(stmt).scalar_one()

            result = BlogPost.model_validate(orm_post)
            # proxy collection
            assert set(result.tag_labels) == {"python", "testing"}
            # association collection
            tag_labels_via_assoc = {t.label for t in result.tags}
            assert tag_labels_via_assoc == {"python", "testing"}
