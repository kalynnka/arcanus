"""Test RelationGroupMap association with SQLAlchemy Materia.

Tests:
- CRUD operations with grouped dict relationships (Warehouse <-> WarehouseItem via attribute_keyed_list_dict)
- Lazy and eager loading of grouped dict relationships
- Serialization after ORM load
- Dict mutation operations persisted through SQLAlchemy
- Convenience methods: append, extend, discard, flatten
"""

from __future__ import annotations

from sqlalchemy import Engine, select
from sqlalchemy.orm import selectinload

from arcanus.association import RelationGroupMap
from arcanus.materia.sqlalchemy import Session
from tests.transmuters import Warehouse, WarehouseItem


class TestRelationGroupMapCRUD:
    """Test basic CRUD operations with grouped dict relationships."""

    def test_create_warehouse_with_items(self, engine: Engine):
        """Test creating a Warehouse with WarehouseItems through RelationGroupMap."""
        with Session(engine) as session:
            wh = Warehouse(name="Main")
            item1 = WarehouseItem(category="tools", name="Hammer", quantity=10)
            item2 = WarehouseItem(category="tools", name="Wrench", quantity=5)
            item3 = WarehouseItem(category="parts", name="Bolt", quantity=100)
            wh.items["tools"] = [item1, item2]
            wh.items["parts"] = [item3]

            session.add(wh)
            session.flush()
            wh.revalidate()
            item1.revalidate()
            item2.revalidate()
            item3.revalidate()

            assert wh.id is not None
            assert item1.id is not None
            assert item2.id is not None
            assert item3.id is not None
            assert len(wh.items) == 2
            assert len(wh.items["tools"]) == 2
            assert len(wh.items["parts"]) == 1

    def test_create_warehouse_empty(self, engine: Engine):
        """Test creating a Warehouse with no items."""
        with Session(engine) as session:
            wh = Warehouse(name="Empty")
            session.add(wh)
            session.flush()
            wh.revalidate()

            assert wh.id is not None
            assert len(wh.items) == 0

    def test_append_item(self, engine: Engine):
        """Test appending a single item to a group."""
        with Session(engine) as session:
            wh = Warehouse(name="Append Test")
            session.add(wh)
            session.flush()

            item = WarehouseItem(category="tools", name="Drill", quantity=3)
            wh.items.append("tools", item)
            session.flush()
            item.revalidate()

            assert item.id is not None
            assert len(wh.items["tools"]) == 1

    def test_append_multiple_same_key(self, engine: Engine):
        """Test appending multiple items to the same key."""
        with Session(engine) as session:
            wh = Warehouse(name="Multi Append")
            session.add(wh)
            session.flush()

            wh.items.append(
                "tools", WarehouseItem(category="tools", name="Saw", quantity=2)
            )
            wh.items.append(
                "tools", WarehouseItem(category="tools", name="Drill", quantity=1)
            )
            wh.items.append(
                "tools", WarehouseItem(category="tools", name="Level", quantity=1)
            )
            session.flush()

            assert len(wh.items["tools"]) == 3

    def test_discard_from_group(self, engine: Engine):
        """Test removing a single item from a group."""
        with Session(engine) as session:
            wh = Warehouse(name="Remove Test")
            item1 = WarehouseItem(category="tools", name="Hammer", quantity=10)
            item2 = WarehouseItem(category="tools", name="Wrench", quantity=5)
            wh.items["tools"] = [item1, item2]
            session.add(wh)
            session.flush()

            assert len(wh.items["tools"]) == 2
            wh.items.discard("tools", item1)
            session.flush()

            assert len(wh.items["tools"]) == 1
            assert wh.items["tools"][0].name == "Wrench"

    def test_remove_last_item_deletes_key(self, engine: Engine):
        """Test removing the last item from a group deletes the key."""
        with Session(engine) as session:
            wh = Warehouse(name="Remove Last")
            item = WarehouseItem(category="tools", name="Hammer", quantity=1)
            wh.items["tools"] = [item]
            session.add(wh)
            session.flush()

            wh.items.discard("tools", item)
            session.flush()

            assert "tools" not in wh.items
            assert len(wh.items) == 0

    def test_delete_group(self, engine: Engine):
        """Test deleting an entire group."""
        with Session(engine) as session:
            wh = Warehouse(name="Delete Group")
            wh.items["tools"] = [
                WarehouseItem(category="tools", name="Hammer", quantity=10),
                WarehouseItem(category="tools", name="Wrench", quantity=5),
            ]
            wh.items["parts"] = [
                WarehouseItem(category="parts", name="Bolt", quantity=100),
            ]
            session.add(wh)
            session.flush()

            assert len(wh.items) == 2
            del wh.items["tools"]
            session.flush()

            assert len(wh.items) == 1
            assert "parts" in wh.items

    def test_clear_all(self, engine: Engine):
        """Test clearing all groups."""
        with Session(engine) as session:
            wh = Warehouse(name="Clear All")
            for cat in ["tools", "parts", "misc"]:
                wh.items[cat] = [
                    WarehouseItem(category=cat, name=f"{cat} item", quantity=1)
                ]
            session.add(wh)
            session.flush()

            assert len(wh.items) == 3
            wh.items.clear()
            session.flush()

            assert len(wh.items) == 0


class TestRelationGroupMapLoading:
    """Test lazy and eager loading of grouped dict relationships."""

    def test_lazy_load_items(self, engine: Engine):
        """Test that items are lazily loaded when accessed."""
        with Session(engine) as session:
            wh = Warehouse(name="Lazy Load")
            wh.items["tools"] = [
                WarehouseItem(category="tools", name="Hammer", quantity=10),
                WarehouseItem(category="tools", name="Wrench", quantity=5),
            ]
            wh.items["parts"] = [
                WarehouseItem(category="parts", name="Bolt", quantity=100),
            ]
            session.add(wh)
            session.flush()
            wh.revalidate()
            wh_id = wh.id
            session.commit()

        with Session(engine) as session:
            stmt = select(Warehouse).where(Warehouse["id"] == wh_id)
            wh = session.scalars(stmt).unique().one()
            assert isinstance(wh, Warehouse)
            assert isinstance(wh.items, RelationGroupMap)

            # Accessing items triggers lazy load
            assert len(wh.items) == 2
            assert len(wh.items["tools"]) == 2
            assert len(wh.items["parts"]) == 1

    def test_eager_load_selectinload(self, engine: Engine):
        """Test eager loading items with selectinload."""
        with Session(engine) as session:
            wh = Warehouse(name="Eager Load")
            wh.items["tools"] = [
                WarehouseItem(category="tools", name="Drill", quantity=3),
            ]
            wh.items["parts"] = [
                WarehouseItem(category="parts", name="Nut", quantity=50),
                WarehouseItem(category="parts", name="Washer", quantity=200),
            ]
            session.add(wh)
            session.flush()
            wh.revalidate()
            wh_id = wh.id
            session.commit()

        with Session(engine) as session:
            stmt = (
                select(Warehouse)
                .where(Warehouse["id"] == wh_id)
                .options(selectinload(Warehouse["items"]))
            )
            wh = session.scalars(stmt).unique().one()
            assert isinstance(wh, Warehouse)
            assert len(wh.items) == 2
            assert len(wh.items["tools"]) == 1
            assert len(wh.items["parts"]) == 2

    def test_load_preserves_grouping(self, engine: Engine):
        """Test that grouping keys are preserved after loading from DB."""
        with Session(engine) as session:
            wh = Warehouse(name="Preserved Grouping")
            for cat in ["alpha", "beta", "gamma"]:
                wh.items[cat] = [
                    WarehouseItem(category=cat, name=f"{cat}1", quantity=1),
                    WarehouseItem(category=cat, name=f"{cat}2", quantity=2),
                ]
            session.add(wh)
            session.flush()
            wh.revalidate()
            wh_id = wh.id
            session.commit()

        with Session(engine) as session:
            stmt = select(Warehouse).where(Warehouse["id"] == wh_id)
            wh = session.scalars(stmt).unique().one()
            assert set(wh.items.keys()) == {"alpha", "beta", "gamma"}
            for cat in ["alpha", "beta", "gamma"]:
                assert len(wh.items[cat]) == 2


class TestRelationGroupMapSerialization:
    """Test serialization of RelationGroupMap after ORM operations."""

    def test_model_dump_after_create(self, engine: Engine):
        """Test model_dump after creating warehouse with grouped items."""
        with Session(engine) as session:
            wh = Warehouse(name="Dump Warehouse")
            wh.items["tools"] = [
                WarehouseItem(category="tools", name="Hammer", quantity=10),
                WarehouseItem(category="tools", name="Wrench", quantity=5),
            ]
            session.add(wh)
            session.flush()

            data = wh.model_dump()
            assert isinstance(data["items"], dict)
            assert "tools" in data["items"]
            assert len(data["items"]["tools"]) == 2

    def test_model_dump_after_load(self, engine: Engine):
        """Test model_dump after loading from DB with selectinload."""
        with Session(engine) as session:
            wh = Warehouse(name="Load Dump Warehouse")
            wh.items["parts"] = [
                WarehouseItem(category="parts", name="Bolt", quantity=100),
            ]
            session.add(wh)
            session.flush()
            wh.revalidate()
            wh_id = wh.id
            session.commit()

        with Session(engine) as session:
            stmt = (
                select(Warehouse)
                .where(Warehouse["id"] == wh_id)
                .options(selectinload(Warehouse["items"]))
            )
            wh = session.scalars(stmt).unique().one()
            data = wh.model_dump()
            assert isinstance(data["items"], dict)
            assert "parts" in data["items"]
            assert len(data["items"]["parts"]) == 1
            assert data["items"]["parts"][0]["name"] == "Bolt"

    def test_model_dump_empty(self, engine: Engine):
        """Test model_dump with empty items."""
        with Session(engine) as session:
            wh = Warehouse(name="Empty Dump Warehouse")
            session.add(wh)
            session.flush()

            data = wh.model_dump()
            assert data["items"] == {}


class TestRelationGroupMapDictOperations:
    """Test dict operations through the ORM."""

    def test_get_existing_key(self, engine: Engine):
        """Test get() on a loaded warehouse."""
        with Session(engine) as session:
            wh = Warehouse(name="Get Warehouse")
            wh.items["tools"] = [
                WarehouseItem(category="tools", name="Hammer", quantity=10),
            ]
            session.add(wh)
            session.flush()

            result = wh.items.get("tools")
            assert result is not None
            assert len(result) == 1
            assert wh.items.get("missing") is None

    def test_pop_group(self, engine: Engine):
        """Test pop() removes and returns the group."""
        with Session(engine) as session:
            wh = Warehouse(name="Pop Warehouse")
            wh.items["tools"] = [
                WarehouseItem(category="tools", name="Hammer", quantity=10),
                WarehouseItem(category="tools", name="Wrench", quantity=5),
            ]
            session.add(wh)
            session.flush()

            items = wh.items.pop("tools")
            assert len(items) == 2
            assert len(wh.items) == 0

    def test_keys_values_items(self, engine: Engine):
        """Test keys(), values(), items() views."""
        with Session(engine) as session:
            wh = Warehouse(name="Views Warehouse")
            wh.items["tools"] = [
                WarehouseItem(category="tools", name="Hammer", quantity=10),
            ]
            wh.items["parts"] = [
                WarehouseItem(category="parts", name="Bolt", quantity=100),
            ]
            session.add(wh)
            session.flush()

            assert set(wh.items.keys()) == {"tools", "parts"}
            assert len(list(wh.items.values())) == 2
            assert len(list(wh.items.items())) == 2

    def test_contains_key(self, engine: Engine):
        """Test key membership check."""
        with Session(engine) as session:
            wh = Warehouse(name="Contains Warehouse")
            wh.items["tools"] = [
                WarehouseItem(category="tools", name="Hammer", quantity=10),
            ]
            session.add(wh)
            session.flush()

            assert "tools" in wh.items
            assert "gone" not in wh.items

    def test_flatten(self, engine: Engine):
        """Test flatten() returns all items across all groups."""
        with Session(engine) as session:
            wh = Warehouse(name="Flat Warehouse")
            wh.items["tools"] = [
                WarehouseItem(category="tools", name="Hammer", quantity=10),
                WarehouseItem(category="tools", name="Wrench", quantity=5),
            ]
            wh.items["parts"] = [
                WarehouseItem(category="parts", name="Bolt", quantity=100),
            ]
            session.add(wh)
            session.flush()

            flat = wh.items.flatten()
            assert len(flat) == 3
            names = {item.name for item in flat}
            assert names == {"Hammer", "Wrench", "Bolt"}

    def test_extend_group(self, engine: Engine):
        """Test extend() adds multiple items to a group."""
        with Session(engine) as session:
            wh = Warehouse(name="Extend Warehouse")
            wh.items["tools"] = [
                WarehouseItem(category="tools", name="Hammer", quantity=10),
            ]
            session.add(wh)
            session.flush()

            wh.items.extend(
                "tools",
                [
                    WarehouseItem(category="tools", name="Wrench", quantity=5),
                    WarehouseItem(category="tools", name="Drill", quantity=3),
                ],
            )
            session.flush()

            assert len(wh.items["tools"]) == 3

    def test_update_groups(self, engine: Engine):
        """Test update() with a mapping of groups."""
        with Session(engine) as session:
            wh = Warehouse(name="Update Warehouse")
            session.add(wh)
            session.flush()

            wh.items.update(
                {
                    "tools": [
                        WarehouseItem(category="tools", name="Hammer", quantity=10)
                    ],
                    "parts": [
                        WarehouseItem(category="parts", name="Bolt", quantity=100)
                    ],
                }
            )
            session.flush()

            assert len(wh.items) == 2
            assert len(wh.items["tools"]) == 1
            assert len(wh.items["parts"]) == 1


class TestRelationGroupMapPersistence:
    """Test that mutations are persisted across sessions."""

    def test_append_persists(self, engine: Engine):
        """Test that appended items are visible in a new session."""
        with Session(engine) as session:
            wh = Warehouse(name="Persist Append")
            session.add(wh)
            session.flush()

            wh.items.append(
                "tools", WarehouseItem(category="tools", name="Hammer", quantity=10)
            )
            wh.items.append(
                "tools", WarehouseItem(category="tools", name="Wrench", quantity=5)
            )
            session.flush()
            wh.revalidate()
            wh_id = wh.id
            session.commit()

        with Session(engine) as session:
            stmt = select(Warehouse).where(Warehouse["id"] == wh_id)
            wh = session.scalars(stmt).unique().one()
            assert len(wh.items["tools"]) == 2
            names = {item.name for item in wh.items["tools"]}
            assert names == {"Hammer", "Wrench"}

    def test_multiple_groups_persist(self, engine: Engine):
        """Test that multiple groups are persisted correctly."""
        with Session(engine) as session:
            wh = Warehouse(name="Persist Multi")
            wh.items["tools"] = [
                WarehouseItem(category="tools", name="Hammer", quantity=10),
                WarehouseItem(category="tools", name="Wrench", quantity=5),
            ]
            wh.items["parts"] = [
                WarehouseItem(category="parts", name="Bolt", quantity=100),
                WarehouseItem(category="parts", name="Nut", quantity=200),
                WarehouseItem(category="parts", name="Washer", quantity=300),
            ]
            session.add(wh)
            session.flush()
            wh.revalidate()
            wh_id = wh.id
            session.commit()

        with Session(engine) as session:
            stmt = select(Warehouse).where(Warehouse["id"] == wh_id)
            wh = session.scalars(stmt).unique().one()
            assert set(wh.items.keys()) == {"tools", "parts"}
            assert len(wh.items["tools"]) == 2
            assert len(wh.items["parts"]) == 3
