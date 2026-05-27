"""Test RelationGroupMap + association proxy integration with SQLAlchemy Materia.

Part 1 – Alongside proxy:
    Verifies that a transmuter with both a ``RelationGroupMap`` (backed by
    ``attribute_keyed_list_dict``) and a scalar ``association_proxy`` field works
    correctly.

Part 2 – Proxy *over* attribute_keyed_list_dict:
    Verifies that a ``RelationGroupMap`` mapped to an ``association_proxy``
    that targets a ``attribute_keyed_list_dict``-backed relationship resolves
    the proxy values correctly — the scenario where SQLAlchemy's
    ``_AssociationDict`` cannot iterate dict-of-lists values on its own.
"""

from __future__ import annotations

from sqlalchemy import Engine, select

from arcanus.association import RelationGroupMap
from arcanus.materia.sqlalchemy import Session, raiseload, selectinload
from tests.models import Article as ArticleModel
from tests.models import ArticleGeneratedFile as ArticleGeneratedFileModel
from tests.models import GeneratedFile as GeneratedFileModel
from tests.models import Warehouse as WarehouseModel
from tests.models import WarehouseItem as WarehouseItemModel
from tests.models import WarehouseManager as WarehouseManagerModel
from tests.transmuters import Article, Warehouse, WarehouseItem


def _seed_warehouse(
    session, *, name: str = "Main", manager_name: str | None = "Alice"
) -> WarehouseModel:
    """Insert a Warehouse with optional manager and sample items, flush & return."""
    manager = None
    if manager_name is not None:
        manager = WarehouseManagerModel(name=manager_name)
        session.add(manager)
        session.flush()

    wh = WarehouseModel(
        name=name,
        manager_id=manager.id if manager else None,
    )
    session.add(wh)
    session.flush()

    # Add some grouped items
    items = [
        WarehouseItemModel(
            category="tools", name="Hammer", quantity=10, warehouse_id=wh.id
        ),
        WarehouseItemModel(
            category="tools", name="Wrench", quantity=5, warehouse_id=wh.id
        ),
        WarehouseItemModel(
            category="parts", name="Bolt", quantity=100, warehouse_id=wh.id
        ),
    ]
    session.add_all(items)
    session.flush()

    return wh


class TestRelationGroupMapWithProxyModelValidate:
    """Test model_validate path with both grouped items and association proxy."""

    def test_proxy_populated_when_manager_loaded(self, engine: Engine):
        """manager_name proxy populated when manager relationship eagerly loaded."""
        with Session(engine) as session:
            orm_wh = _seed_warehouse(session, manager_name="Alice")
            wh_id = orm_wh.id
            session.commit()

        with Session(engine) as session:
            stmt = (
                select(WarehouseModel)
                .where(WarehouseModel.id == wh_id)
                .options(selectinload(WarehouseModel.manager))
            )
            orm_wh = session.execute(stmt).scalar_one()

            wh = Warehouse.model_validate(orm_wh)
            assert wh.manager_name == "Alice"

    def test_proxy_falls_back_when_manager_not_loaded(self, engine: Engine):
        """manager_name falls back to None when manager relationship not loaded."""
        with Session(engine) as session:
            orm_wh = _seed_warehouse(session, manager_name="Bob")
            wh_id = orm_wh.id
            session.commit()

        with Session(engine) as session:
            stmt = select(WarehouseModel).where(WarehouseModel.id == wh_id)
            orm_wh = session.execute(stmt).scalar_one()
            # Expire to ensure not in inspector.dict
            session.expire(orm_wh, ["manager"])

            wh = Warehouse.model_validate(orm_wh)
            assert wh.manager_name is None

    def test_proxy_does_not_trigger_raiseload(self, engine: Engine):
        """manager_name proxy must not trigger raiseload on manager."""
        with Session(engine) as session:
            orm_wh = _seed_warehouse(session, manager_name="Carol")
            wh_id = orm_wh.id
            session.commit()

        with Session(engine) as session:
            stmt = (
                select(WarehouseModel)
                .where(WarehouseModel.id == wh_id)
                .options(raiseload(WarehouseModel.manager))
            )
            orm_wh = session.execute(stmt).scalar_one()

            # Should NOT raise
            wh = Warehouse.model_validate(orm_wh)
            assert wh.manager_name is None

    def test_grouped_items_load_alongside_proxy(self, engine: Engine):
        """RelationGroupMap items load correctly when proxy is also present."""
        with Session(engine) as session:
            orm_wh = _seed_warehouse(session, manager_name="Diana")
            wh_id = orm_wh.id
            session.commit()

        with Session(engine) as session:
            stmt = (
                select(WarehouseModel)
                .where(WarehouseModel.id == wh_id)
                .options(
                    selectinload(WarehouseModel.manager),
                    selectinload(WarehouseModel.items),
                )
            )
            orm_wh = session.execute(stmt).scalar_one()

            wh = Warehouse.model_validate(orm_wh)

            # Proxy populated
            assert wh.manager_name == "Diana"

            # Grouped items populated
            assert isinstance(wh.items, RelationGroupMap)
            assert len(wh.items) == 2
            assert len(wh.items["tools"]) == 2
            assert len(wh.items["parts"]) == 1

    def test_grouped_items_lazy_load_with_proxy(self, engine: Engine):
        """Grouped items lazy-load after model_validate regardless of proxy state."""
        with Session(engine) as session:
            orm_wh = _seed_warehouse(session, manager_name="Eve")
            wh_id = orm_wh.id
            session.commit()

        with Session(engine) as session:
            stmt = (
                select(WarehouseModel)
                .where(WarehouseModel.id == wh_id)
                .options(selectinload(WarehouseModel.manager))
            )
            orm_wh = session.execute(stmt).scalar_one()

            wh = Warehouse.model_validate(orm_wh)
            assert wh.manager_name == "Eve"

            # Items not eagerly loaded — accessing triggers lazy load
            assert len(wh.items) == 2
            tool_names = {item.name for item in wh.items["tools"]}
            assert tool_names == {"Hammer", "Wrench"}

    def test_no_manager_with_grouped_items(self, engine: Engine):
        """Warehouse without a manager still works with grouped items."""
        with Session(engine) as session:
            orm_wh = _seed_warehouse(session, manager_name=None)
            wh_id = orm_wh.id
            session.commit()

        with Session(engine) as session:
            stmt = (
                select(WarehouseModel)
                .where(WarehouseModel.id == wh_id)
                .options(selectinload(WarehouseModel.items))
            )
            orm_wh = session.execute(stmt).scalar_one()

            wh = Warehouse.model_validate(orm_wh)
            assert wh.manager_name is None
            assert len(wh.items) == 2


class TestRelationGroupMapWithProxyCRUD:
    """Test CRUD mutations on grouped items when association proxy is present."""

    def test_create_with_proxy_and_grouped_items(self, engine: Engine):
        """Create a warehouse with manager + grouped items through transmuters."""
        with Session(engine) as session:
            wh = Warehouse(name="New Warehouse")
            session.add(wh)
            session.flush()
            wh.revalidate()

            # Add items
            wh.items["tools"] = [
                WarehouseItem(category="tools", name="Drill", quantity=3),
            ]
            wh.items["parts"] = [
                WarehouseItem(category="parts", name="Nut", quantity=50),
            ]
            session.flush()

            assert len(wh.items) == 2
            assert len(wh.items["tools"]) == 1
            assert len(wh.items["parts"]) == 1

    def test_append_items_with_proxy_present(self, engine: Engine):
        """Append to grouped items while proxy field exists on the transmuter."""
        with Session(engine) as session:
            orm_wh = _seed_warehouse(session, manager_name="Frank")
            wh_id = orm_wh.id
            session.commit()

        with Session(engine) as session:
            stmt = (
                select(WarehouseModel)
                .where(WarehouseModel.id == wh_id)
                .options(
                    selectinload(WarehouseModel.manager),
                    selectinload(WarehouseModel.items),
                )
            )
            orm_wh = session.execute(stmt).scalar_one()
            wh = Warehouse.model_validate(orm_wh)

            assert wh.manager_name == "Frank"

            # Append a new item
            wh.items.append(
                "tools",
                WarehouseItem(category="tools", name="Level", quantity=1),
            )
            session.flush()

            assert len(wh.items["tools"]) == 3
            assert wh.manager_name == "Frank"

    def test_discard_item_with_proxy_present(self, engine: Engine):
        """Discard from grouped items while proxy field exists."""
        with Session(engine) as session:
            orm_wh = _seed_warehouse(session, manager_name="Grace")
            wh_id = orm_wh.id
            session.commit()

        with Session(engine) as session:
            stmt = (
                select(WarehouseModel)
                .where(WarehouseModel.id == wh_id)
                .options(
                    selectinload(WarehouseModel.manager),
                    selectinload(WarehouseModel.items),
                )
            )
            orm_wh = session.execute(stmt).scalar_one()
            wh = Warehouse.model_validate(orm_wh)

            assert wh.manager_name == "Grace"
            assert len(wh.items["tools"]) == 2

            # Remove one tool
            tool_to_remove = wh.items["tools"][0]
            wh.items.discard("tools", tool_to_remove)
            session.flush()

            assert len(wh.items["tools"]) == 1
            assert wh.manager_name == "Grace"


class TestRelationGroupMapWithProxySerialization:
    """Test model_dump includes both grouped items and proxy values."""

    def test_model_dump_includes_proxy_and_items(self, engine: Engine):
        """model_dump contains both manager_name (proxy) and items (group map)."""
        with Session(engine) as session:
            orm_wh = _seed_warehouse(session, manager_name="Hank")
            wh_id = orm_wh.id
            session.commit()

        with Session(engine) as session:
            stmt = (
                select(WarehouseModel)
                .where(WarehouseModel.id == wh_id)
                .options(
                    selectinload(WarehouseModel.manager),
                    selectinload(WarehouseModel.items),
                )
            )
            orm_wh = session.execute(stmt).scalar_one()
            wh = Warehouse.model_validate(orm_wh)

            data = wh.model_dump()
            assert data["manager_name"] == "Hank"
            assert isinstance(data["items"], dict)
            assert "tools" in data["items"]
            assert "parts" in data["items"]
            assert len(data["items"]["tools"]) == 2
            assert len(data["items"]["parts"]) == 1

    def test_model_dump_proxy_none_with_items(self, engine: Engine):
        """model_dump has manager_name=None but items populated."""
        with Session(engine) as session:
            orm_wh = _seed_warehouse(session, manager_name=None)
            wh_id = orm_wh.id
            session.commit()

        with Session(engine) as session:
            stmt = (
                select(WarehouseModel)
                .where(WarehouseModel.id == wh_id)
                .options(selectinload(WarehouseModel.items))
            )
            orm_wh = session.execute(stmt).scalar_one()
            wh = Warehouse.model_validate(orm_wh)

            data = wh.model_dump()
            assert data["manager_name"] is None
            assert len(data["items"]["tools"]) == 2


class TestRelationGroupMapWithProxyModelConstruct:
    """Test model_construct path with both grouped items and association proxy."""

    def test_construct_with_proxy_and_items_loaded(self, engine: Engine):
        """model_construct populates proxy + defers items when both loaded."""
        with Session(engine) as session:
            orm_wh = _seed_warehouse(session, manager_name="Ivy")
            wh_id = orm_wh.id
            session.commit()

        with Session(engine) as session:
            stmt = (
                select(WarehouseModel)
                .where(WarehouseModel.id == wh_id)
                .options(
                    selectinload(WarehouseModel.manager),
                    selectinload(WarehouseModel.items),
                )
            )
            orm_wh = session.execute(stmt).scalar_one()

            wh = Warehouse.model_construct(data=orm_wh)
            assert wh.manager_name == "Ivy"

            # items should be accessible (lazy or eager)
            assert isinstance(wh.items, RelationGroupMap)

    def test_construct_proxy_skipped_when_not_loaded(self, engine: Engine):
        """model_construct skips proxy when manager not loaded."""
        with Session(engine) as session:
            orm_wh = _seed_warehouse(session, manager_name="Jake")
            wh_id = orm_wh.id
            session.commit()

        with Session(engine) as session:
            stmt = select(WarehouseModel).where(WarehouseModel.id == wh_id)
            orm_wh = session.execute(stmt).scalar_one()
            session.expire(orm_wh, ["manager"])

            wh = Warehouse.model_construct(data=orm_wh)
            assert getattr(wh, "manager_name", None) is None


class TestRelationGroupMapWithProxyPersistence:
    """Test cross-session persistence with both features active."""

    def test_items_persist_across_sessions_with_proxy(self, engine: Engine):
        """Grouped items created in one session load correctly in another,
        with association proxy also resolving correctly."""
        with Session(engine) as session:
            orm_wh = _seed_warehouse(session, manager_name="Karen")
            wh_id = orm_wh.id
            session.commit()

        with Session(engine) as session:
            stmt = (
                select(WarehouseModel)
                .where(WarehouseModel.id == wh_id)
                .options(
                    selectinload(WarehouseModel.manager),
                    selectinload(WarehouseModel.items),
                )
            )
            orm_wh = session.execute(stmt).scalar_one()
            wh = Warehouse.model_validate(orm_wh)

            assert wh.manager_name == "Karen"
            assert set(wh.items.keys()) == {"tools", "parts"}
            assert len(wh.items.flatten()) == 3


# ═════════════════════════════════════════════════════════════════════════════
# Part 2 – RelationGroupMap mapped to an association_proxy over
#           attribute_keyed_list_dict (proxy *over* the grouped relationship)
# ═════════════════════════════════════════════════════════════════════════════


def _seed_article(session, *, title: str = "Test Article") -> ArticleModel:
    """Insert an Article with generated files grouped by role, flush & return."""
    file1 = GeneratedFileModel(filename="cover.png", size=1024)
    file2 = GeneratedFileModel(filename="banner.png", size=2048)
    file3 = GeneratedFileModel(filename="data.csv", size=512)
    session.add_all([file1, file2, file3])
    session.flush()

    article = ArticleModel(title=title)
    session.add(article)
    session.flush()

    assocs = [
        ArticleGeneratedFileModel(
            role="image", article_id=article.id, file_id=file1.id
        ),
        ArticleGeneratedFileModel(
            role="image", article_id=article.id, file_id=file2.id
        ),
        ArticleGeneratedFileModel(role="data", article_id=article.id, file_id=file3.id),
    ]
    session.add_all(assocs)
    session.flush()

    return article


class TestProxyOverGroupedRelationshipLoading:
    """Test that RelationGroupMap resolves association_proxy over
    attribute_keyed_list_dict correctly during loading."""

    def test_load_with_selectinload(self, engine: Engine):
        """Eagerly loaded proxy-over-grouped-relationship populates RelationGroupMap."""
        with Session(engine) as session:
            orm_article = _seed_article(session)
            article_id = orm_article.id
            session.commit()

        with Session(engine) as session:
            stmt = (
                select(ArticleModel)
                .where(ArticleModel.id == article_id)
                .options(
                    selectinload(ArticleModel.generated_file_associations).selectinload(
                        ArticleGeneratedFileModel.file
                    )
                )
            )
            orm_article = session.execute(stmt).scalar_one()

            article = Article.model_validate(orm_article)
            assert isinstance(article.generated_files, RelationGroupMap)
            assert len(article.generated_files) == 2
            assert len(article.generated_files["image"]) == 2
            assert len(article.generated_files["data"]) == 1

    def test_load_resolves_target_objects(self, engine: Engine):
        """Values in the RelationGroupMap are the proxied target (GeneratedFile),
        not the intermediate association (ArticleGeneratedFile)."""
        with Session(engine) as session:
            orm_article = _seed_article(session)
            article_id = orm_article.id
            session.commit()

        with Session(engine) as session:
            stmt = (
                select(ArticleModel)
                .where(ArticleModel.id == article_id)
                .options(
                    selectinload(ArticleModel.generated_file_associations).selectinload(
                        ArticleGeneratedFileModel.file
                    )
                )
            )
            orm_article = session.execute(stmt).scalar_one()

            article = Article.model_validate(orm_article)
            filenames = {f.filename for f in article.generated_files["image"]}
            assert filenames == {"cover.png", "banner.png"}
            assert article.generated_files["data"][0].filename == "data.csv"

    def test_lazy_load_proxy_over_grouped(self, engine: Engine):
        """Lazy load works for proxy-over-grouped-relationship."""
        with Session(engine) as session:
            orm_article = _seed_article(session)
            article_id = orm_article.id
            session.commit()

        with Session(engine) as session:
            stmt = select(ArticleModel).where(ArticleModel.id == article_id)
            orm_article = session.execute(stmt).scalar_one()

            article = Article.model_validate(orm_article)
            # Accessing should trigger lazy load
            assert len(article.generated_files) == 2
            assert len(article.generated_files["image"]) == 2


class TestProxyOverGroupedRelationshipSerialization:
    """Test model_dump with proxy-over-grouped-relationship."""

    def test_model_dump_includes_resolved_files(self, engine: Engine):
        """model_dump contains the resolved GeneratedFile data, not intermediates."""
        with Session(engine) as session:
            orm_article = _seed_article(session)
            article_id = orm_article.id
            session.commit()

        with Session(engine) as session:
            stmt = (
                select(ArticleModel)
                .where(ArticleModel.id == article_id)
                .options(
                    selectinload(ArticleModel.generated_file_associations).selectinload(
                        ArticleGeneratedFileModel.file
                    )
                )
            )
            orm_article = session.execute(stmt).scalar_one()

            article = Article.model_validate(orm_article)
            data = article.model_dump()
            assert isinstance(data["generated_files"], dict)
            assert "image" in data["generated_files"]
            assert "data" in data["generated_files"]
            assert len(data["generated_files"]["image"]) == 2
            assert len(data["generated_files"]["data"]) == 1
            # Verify we get GeneratedFile fields, not ArticleGeneratedFile fields
            img = data["generated_files"]["image"][0]
            assert "filename" in img
            assert "size" in img


class TestProxyOverGroupedRelationshipPersistence:
    """Test cross-session loading with proxy-over-grouped-relationship."""

    def test_persist_and_reload(self, engine: Engine):
        """Data created in one session loads correctly via proxy in another."""
        with Session(engine) as session:
            orm_article = _seed_article(session, title="Persistent Article")
            article_id = orm_article.id
            session.commit()

        with Session(engine) as session:
            stmt = (
                select(ArticleModel)
                .where(ArticleModel.id == article_id)
                .options(
                    selectinload(ArticleModel.generated_file_associations).selectinload(
                        ArticleGeneratedFileModel.file
                    )
                )
            )
            orm_article = session.execute(stmt).scalar_one()

            article = Article.model_validate(orm_article)
            assert article.title == "Persistent Article"
            assert set(article.generated_files.keys()) == {"image", "data"}
            assert len(article.generated_files.flatten()) == 3
