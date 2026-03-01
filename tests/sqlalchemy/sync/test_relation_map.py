"""Test RelationMap association with SQLAlchemy Materia.

Tests:
- CRUD operations with dict-based relationships (Shelf <-> ShelfItem via attribute_keyed_dict)
- Lazy and eager loading of dict relationships
- Serialization after ORM load
- Dict mutation operations persisted through SQLAlchemy
"""

from __future__ import annotations

from sqlalchemy import Engine, select
from sqlalchemy.orm import selectinload

from arcanus.association import RelationMap
from arcanus.materia.sqlalchemy import Session
from tests.transmuters import Shelf, ShelfItem


class TestRelationMapCRUD:
    """Test basic CRUD operations with dict-based relationships."""

    def test_create_shelf_with_items(self, engine: Engine):
        """Test creating a Shelf with ShelfItems through RelationMap."""
        with Session(engine) as session:
            shelf = Shelf(name="Science")
            item1 = ShelfItem(label="physics", description="Physics books")
            item2 = ShelfItem(label="chemistry", description="Chemistry books")
            shelf.items["physics"] = item1
            shelf.items["chemistry"] = item2

            session.add(shelf)
            session.flush()
            shelf.revalidate()
            item1.revalidate()
            item2.revalidate()

            assert shelf.id is not None
            assert item1.id is not None
            assert item2.id is not None
            assert len(shelf.items) == 2

    def test_create_shelf_empty(self, engine: Engine):
        """Test creating a Shelf with no items."""
        with Session(engine) as session:
            shelf = Shelf(name="Empty Shelf")
            session.add(shelf)
            session.flush()
            shelf.revalidate()

            assert shelf.id is not None
            assert len(shelf.items) == 0

    def test_add_item_to_existing_shelf(self, engine: Engine):
        """Test adding a ShelfItem to an existing Shelf."""
        with Session(engine) as session:
            shelf = Shelf(name="Growing Shelf")
            session.add(shelf)
            session.flush()

            item = ShelfItem(label="math", description="Math books")
            shelf.items["math"] = item
            session.flush()
            item.revalidate()

            assert item.id is not None
            assert len(shelf.items) == 1
            assert shelf.items["math"].description == "Math books"

    def test_remove_item_from_shelf(self, engine: Engine):
        """Test removing a ShelfItem from a Shelf."""
        with Session(engine) as session:
            shelf = Shelf(name="Shrinking Shelf")
            item = ShelfItem(label="temp", description="Temporary item")
            shelf.items["temp"] = item
            session.add(shelf)
            session.flush()

            assert len(shelf.items) == 1
            del shelf.items["temp"]
            session.flush()

            assert len(shelf.items) == 0

    def test_update_item_in_shelf(self, engine: Engine):
        """Test replacing a ShelfItem at an existing key."""
        with Session(engine) as session:
            shelf = Shelf(name="Update Shelf")
            item1 = ShelfItem(label="slot", description="Original")
            shelf.items["slot"] = item1
            session.add(shelf)
            session.flush()

            item2 = ShelfItem(label="slot", description="Replacement")
            shelf.items["slot"] = item2
            session.flush()

            assert shelf.items["slot"].description == "Replacement"

    def test_clear_all_items(self, engine: Engine):
        """Test clearing all items from a shelf."""
        with Session(engine) as session:
            shelf = Shelf(name="Clearable Shelf")
            for i in range(3):
                shelf.items[f"item{i}"] = ShelfItem(
                    label=f"item{i}", description=f"Item {i}"
                )
            session.add(shelf)
            session.flush()

            assert len(shelf.items) == 3
            shelf.items.clear()
            session.flush()

            assert len(shelf.items) == 0


class TestRelationMapLoading:
    """Test lazy and eager loading of dict-based relationships."""

    def test_lazy_load_items(self, engine: Engine):
        """Test that items are lazily loaded when accessed."""
        with Session(engine) as session:
            shelf = Shelf(name="Lazy Shelf")
            shelf.items["a"] = ShelfItem(label="a", description="Alpha")
            shelf.items["b"] = ShelfItem(label="b", description="Beta")
            session.add(shelf)
            session.flush()
            shelf.revalidate()
            shelf_id = shelf.id
            session.commit()

        # New session to test lazy loading
        with Session(engine) as session:
            stmt = select(Shelf).where(Shelf["id"] == shelf_id)
            shelf = session.scalars(stmt).unique().one()
            assert isinstance(shelf, Shelf)
            assert isinstance(shelf.items, RelationMap)

            # Accessing items triggers lazy load
            assert len(shelf.items) == 2
            assert shelf.items["a"].description == "Alpha"
            assert shelf.items["b"].description == "Beta"

    def test_eager_load_selectinload(self, engine: Engine):
        """Test eager loading items with selectinload."""
        with Session(engine) as session:
            shelf = Shelf(name="Eager Shelf")
            shelf.items["x"] = ShelfItem(label="x", description="X-ray")
            shelf.items["y"] = ShelfItem(label="y", description="Yankee")
            session.add(shelf)
            session.flush()
            shelf.revalidate()
            shelf_id = shelf.id
            session.commit()

        with Session(engine) as session:
            stmt = (
                select(Shelf)
                .where(Shelf["id"] == shelf_id)
                .options(selectinload(Shelf["items"]))
            )
            shelf = session.scalars(stmt).unique().one()
            assert isinstance(shelf, Shelf)
            assert len(shelf.items) == 2

    def test_load_preserves_keys(self, engine: Engine):
        """Test that dict keys are preserved after loading from DB."""
        with Session(engine) as session:
            shelf = Shelf(name="Key Shelf")
            shelf.items["alpha"] = ShelfItem(label="alpha", description="First")
            shelf.items["beta"] = ShelfItem(label="beta", description="Second")
            shelf.items["gamma"] = ShelfItem(label="gamma", description="Third")
            session.add(shelf)
            session.flush()
            shelf.revalidate()
            shelf_id = shelf.id
            session.commit()

        with Session(engine) as session:
            stmt = select(Shelf).where(Shelf["id"] == shelf_id)
            shelf = session.scalars(stmt).unique().one()
            assert set(shelf.items.keys()) == {"alpha", "beta", "gamma"}


class TestRelationMapSerialization:
    """Test serialization of RelationMap after ORM operations."""

    def test_model_dump_after_create(self, engine: Engine):
        """Test model_dump after creating shelf with items."""
        with Session(engine) as session:
            shelf = Shelf(name="Dump Shelf")
            shelf.items["py"] = ShelfItem(label="py", description="Python")
            shelf.items["rs"] = ShelfItem(label="rs", description="Rust")
            session.add(shelf)
            session.flush()

            data = shelf.model_dump()
            assert isinstance(data["items"], dict)
            assert set(data["items"].keys()) == {"py", "rs"}
            assert data["items"]["py"]["description"] == "Python"

    def test_model_dump_after_load(self, engine: Engine):
        """Test model_dump after loading from DB with selectinload."""
        with Session(engine) as session:
            shelf = Shelf(name="Load Dump Shelf")
            shelf.items["a"] = ShelfItem(label="a", description="Alpha")
            session.add(shelf)
            session.flush()
            shelf.revalidate()
            shelf_id = shelf.id
            session.commit()

        with Session(engine) as session:
            stmt = (
                select(Shelf)
                .where(Shelf["id"] == shelf_id)
                .options(selectinload(Shelf["items"]))
            )
            shelf = session.scalars(stmt).unique().one()
            data = shelf.model_dump()
            assert isinstance(data["items"], dict)
            assert "a" in data["items"]
            assert data["items"]["a"]["description"] == "Alpha"

    def test_model_dump_empty_items(self, engine: Engine):
        """Test model_dump with empty items dict."""
        with Session(engine) as session:
            shelf = Shelf(name="Empty Dump Shelf")
            session.add(shelf)
            session.flush()

            data = shelf.model_dump()
            assert data["items"] == {}


class TestRelationMapDictOperations:
    """Test dict operations through the ORM."""

    def test_get_existing_key(self, engine: Engine):
        """Test get() on a loaded shelf."""
        with Session(engine) as session:
            shelf = Shelf(name="Get Shelf")
            shelf.items["k"] = ShelfItem(label="k", description="Known")
            session.add(shelf)
            session.flush()

            assert shelf.items.get("k") is not None
            assert shelf.items["k"].description == "Known"
            assert shelf.items.get("missing") is None

    def test_pop_from_shelf(self, engine: Engine):
        """Test pop() removes and returns the item."""
        with Session(engine) as session:
            shelf = Shelf(name="Pop Shelf")
            shelf.items["p"] = ShelfItem(label="p", description="Poppable")
            session.add(shelf)
            session.flush()

            item = shelf.items.pop("p")
            assert item.description == "Poppable"
            assert len(shelf.items) == 0

    def test_keys_values_items(self, engine: Engine):
        """Test keys(), values(), items() views."""
        with Session(engine) as session:
            shelf = Shelf(name="Views Shelf")
            shelf.items["one"] = ShelfItem(label="one", description="First")
            shelf.items["two"] = ShelfItem(label="two", description="Second")
            session.add(shelf)
            session.flush()

            assert set(shelf.items.keys()) == {"one", "two"}
            assert len(list(shelf.items.values())) == 2
            assert len(list(shelf.items.items())) == 2

    def test_contains_key(self, engine: Engine):
        """Test key membership check."""
        with Session(engine) as session:
            shelf = Shelf(name="Contains Shelf")
            shelf.items["here"] = ShelfItem(label="here", description="Present")
            session.add(shelf)
            session.flush()

            assert "here" in shelf.items
            assert "gone" not in shelf.items

    def test_update_dict(self, engine: Engine):
        """Test update() with a dict of new items."""
        with Session(engine) as session:
            shelf = Shelf(name="Update Shelf")
            session.add(shelf)
            session.flush()

            shelf.items.update(
                {
                    "a": ShelfItem(label="a", description="Alpha"),
                    "b": ShelfItem(label="b", description="Beta"),
                }
            )
            session.flush()

            assert len(shelf.items) == 2
            assert shelf.items["a"].description == "Alpha"

    def test_setdefault(self, engine: Engine):
        """Test setdefault() inserts only if key is absent."""
        with Session(engine) as session:
            shelf = Shelf(name="Setdefault Shelf")
            existing = ShelfItem(label="k", description="Original")
            shelf.items["k"] = existing
            session.add(shelf)
            session.flush()

            new = ShelfItem(label="k", description="New")
            result = shelf.items.setdefault("k", new)
            assert result.description == "Original"


class TestRelationMapBackReference:
    """Test back-reference from ShelfItem to Shelf."""

    def test_item_has_shelf_reference(self, engine: Engine):
        """Test that ShelfItem can reference its parent Shelf."""
        with Session(engine) as session:
            shelf = Shelf(name="BackRef Shelf")
            item = ShelfItem(label="ref", description="Has back-ref")
            shelf.items["ref"] = item
            session.add(shelf)
            session.flush()

            assert item.shelf.value is not None
            assert item.shelf.value.name == "BackRef Shelf"
