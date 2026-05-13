"""Tests covering interaction between :class:`RedisMateria` and
:class:`SqlalchemyMateria` — context switching and cache-aside patterns.
"""

from __future__ import annotations

from typing import Annotated, Optional

import fakeredis
import pytest
from pydantic import ConfigDict, Field
from sqlalchemy import Engine, Integer, String, create_engine, delete, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from arcanus.base import BaseTransmuter, Identity, TransmuterProxiedMixin, validated
from arcanus.materia.base import NoOpMateria, active_materia
from arcanus.materia.redis import Redis, RedisMateria
from arcanus.materia.sqlalchemy import Session, SqlalchemyMateria


class _Base(DeclarativeBase, TransmuterProxiedMixin):
    pass


class CityORM(_Base):
    __tablename__ = "redis_switching_city"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)


sqlalchemy_materia = SqlalchemyMateria()
redis_materia = RedisMateria()


@redis_materia.bless()
@sqlalchemy_materia.bless(CityORM)
class City(BaseTransmuter):
    model_config = ConfigDict(from_attributes=True)
    id: Annotated[Optional[int], Identity] = Field(default=None, frozen=True)
    name: str


class FakeClient(Redis, fakeredis.FakeRedis):
    """Sync Redis backed by an in-memory fakeredis server."""


@pytest.fixture(scope="module")
def engine() -> Engine:
    eng = create_engine("sqlite:///:memory:")
    _Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def fake_client() -> FakeClient:
    return FakeClient()


class TestActiveMateriaSwapping:
    def test_nested_contexts_restore_correctly(self):
        """Nested with-statements: inner replaces, exit restores outer."""
        outer = active_materia.get()

        with redis_materia:
            assert active_materia.get() is redis_materia
            with sqlalchemy_materia:
                assert active_materia.get() is sqlalchemy_materia
            assert active_materia.get() is redis_materia

        assert active_materia.get() is outer

    def test_reverse_nesting(self):
        """Order doesn't matter — sql first, then redis inside."""
        with sqlalchemy_materia:
            assert active_materia.get() is sqlalchemy_materia
            with redis_materia:
                assert active_materia.get() is redis_materia
            assert active_materia.get() is sqlalchemy_materia

    def test_default_is_noop(self):
        """Outside any context the default NoOpMateria is active."""
        assert isinstance(active_materia.get(), NoOpMateria)


class TestDualBless:
    """A single transmuter class can be registered in multiple materias."""

    def test_in_sqlalchemy_registry(self):
        assert City in sqlalchemy_materia.formulars

    def test_in_redis_registry(self):
        assert City in redis_materia.key_prefixes

    def test_same_class_object(self):
        # Both registries reference the very same class object.
        assert sqlalchemy_materia.formulars[City] is CityORM
        assert redis_materia.key_prefixes[City] == "City"


class TestCacheAside:
    """The classic cache-aside pattern: try Redis, fall back to SQL, then cache."""

    def test_miss_then_hit(self, engine: Engine, fake_client: FakeClient):
        paris_id = 1

        # 1. Seed the database under sql_materia
        with sqlalchemy_materia, Session(engine) as session, session.begin():
            session.add(City(id=paris_id, name="Paris"))

        # 2. Cache lookup misses
        with redis_materia:
            assert fake_client.tget(City, paris_id) is None

        # 3. Fall back to SQL
        with sqlalchemy_materia, Session(engine) as session:
            from_db = session.get(City, paris_id)
            assert from_db is not None
            assert from_db.name == "Paris"

        # 4. Populate the cache
        with redis_materia:
            fake_client.tset(from_db)

        # 5. Now Redis hits
        with redis_materia:
            cached = fake_client.tget(City, paris_id)
            assert cached is not None
            assert cached.name == "Paris"
            # Cached instance is decoupled from the SQL session — it's a fresh
            # transmuter validated from the JSON payload.
            assert cached is not from_db

    def test_cache_invalidation_on_delete(
        self, engine: Engine, fake_client: FakeClient
    ):
        rome_id = 2

        with sqlalchemy_materia, Session(engine) as session, session.begin():
            session.add(City(id=rome_id, name="Rome"))

        # Cache it
        with redis_materia:
            fake_client.tset(City(id=rome_id, name="Rome"))
            assert fake_client.tget(City, rome_id) is not None

        # Invalidate the cache when SQL row is deleted
        with sqlalchemy_materia, Session(engine) as session, session.begin():
            session.execute(delete(CityORM).where(CityORM.id == rome_id))
        with redis_materia:
            fake_client.tdelete(City, rome_id)
            assert fake_client.tget(City, rome_id) is None

    def test_redis_lookup_inside_sql_context(
        self, engine: Engine, fake_client: FakeClient
    ):
        """A common real-world shape: outer SQL session, inner Redis check."""
        tokyo_id = 3

        with sqlalchemy_materia, Session(engine) as session, session.begin():
            session.add(City(id=tokyo_id, name="Tokyo"))

            # Switch to redis briefly to populate the cache, without leaving
            # the SQL transaction.
            with redis_materia:
                fake_client.tset(City(id=tokyo_id, name="Tokyo"))

            # Active materia is restored to sql_materia after the inner block.
            assert active_materia.get() is sqlalchemy_materia

        # Cache survives across the SQL commit.
        with redis_materia:
            cached = fake_client.tget(City, tokyo_id)
            assert cached is not None and cached.name == "Tokyo"


class TestIsolation:
    """Two materias must not leak state into each other."""

    def test_redis_keys_unaware_of_sql_inserts(
        self, engine: Engine, fake_client: FakeClient
    ):
        with sqlalchemy_materia, Session(engine) as session, session.begin():
            session.add(City(name="Berlin"))

        # Redis still empty — no automatic mirroring.
        with redis_materia:
            assert fake_client.tget(City, 9999) is None
            # Native MGET on the empty redis namespace returns nothing.
            assert fake_client.keys("City:*") == []

    def test_sql_unaware_of_redis_writes(self, engine: Engine, fake_client: FakeClient):
        # Write into Redis only
        with redis_materia:
            fake_client.tset(City(id=42424242, name="Atlantis"))

        # SQL doesn't have it
        with sqlalchemy_materia, Session(engine) as session:
            assert (
                session.execute(
                    select(CityORM).where(CityORM.name == "Atlantis")
                ).scalar_one_or_none()
                is None
            )


class TestProviderResolution:
    """``__transmuter_provider__`` and ``transmuter_formulars`` reflect the
    *currently active* materia, not whatever was active when the instance was
    built — these are dynamic properties.
    """

    def test_provider_under_sqlalchemy(self):
        with sqlalchemy_materia:
            assert City.__transmuter_provider__ is CityORM
            # transmuter_formulars exposes the active materia's bidi map.
            assert City in City.transmuter_formulars
            assert City.transmuter_formulars[City] is CityORM

    def test_provider_under_redis(self):
        with redis_materia:
            # redis_materia leaves ``formulars`` empty; no provider is exposed.
            assert City.__transmuter_provider__ is None
            assert City.transmuter_formulars == {}

    def test_provider_under_noop(self):
        # Default context (NoOp) — also no provider.
        assert City.__transmuter_provider__ is None
        assert City.transmuter_formulars == {}

    def test_property_changes_when_active_materia_swaps(self):
        """Same class, observed under different active materias."""
        with sqlalchemy_materia:
            assert City.__transmuter_provider__ is CityORM
            with redis_materia:
                # Same class, different active materia ⇒ different provider.
                assert City.__transmuter_provider__ is None
            # Restored after exit.
            assert City.__transmuter_provider__ is CityORM


class TestAutoProviderCreation:
    """``model_formulate`` auto-constructs the ORM provider only when the
    active materia has the transmuter blessed with a provider class.
    """

    def test_sqlalchemy_auto_creates_orm(self):
        with sqlalchemy_materia:
            city = City(id=3001, name="Athens")
            # __transmuter_provided__ holds the auto-created ORM instance.
            assert isinstance(city.__transmuter_provided__, CityORM)
            assert city.__transmuter_provided__.id == 3001
            assert city.__transmuter_provided__.name == "Athens"

    def test_redis_does_not_auto_create_orm(self):
        with redis_materia:
            city = City(id=3002, name="Reykjavik")
            assert city.__transmuter_provided__ is None

    def test_noop_does_not_auto_create_orm(self):
        city = City(id=3003, name="Quito")
        assert city.__transmuter_provided__ is None


class TestSameMateriaReentry:
    def test_reentering_same_materia_raises(self):
        """``with materia: with materia:`` is forbidden — must use the call
        form for nested contexts."""
        with redis_materia:
            with pytest.raises(RuntimeError, match="already active"):
                with redis_materia:
                    pass

    def test_call_form_is_safe_to_nest(self):
        """``with redis_materia():`` creates a shallow copy that's safe to
        nest, even under the original ``with redis_materia:`` block."""
        with redis_materia:
            with redis_materia():  # shallow copy
                inner_active = active_materia.get()
                assert isinstance(inner_active, RedisMateria)
                # The copy shares state with the original (shallow).
                assert inner_active.key_prefixes is redis_materia.key_prefixes
            assert active_materia.get() is redis_materia


class TestMultipleRedisMateriaInstances:
    """Two ``RedisMateria`` instances are independent registries — same
    transmuter class can carry different prefixes per materia."""

    def test_independent_key_prefixes(self):
        m1 = RedisMateria()
        m2 = RedisMateria()

        @m1.bless("namespace1")
        @m2.bless("namespace2")
        class Probe(BaseTransmuter):
            id: Annotated[int, Identity] = Field(frozen=True)
            value: str

        assert m1.key_prefixes[Probe] == "namespace1"
        assert m2.key_prefixes[Probe] == "namespace2"
        # And the registries are physically separate dicts.
        assert m1.key_prefixes is not m2.key_prefixes

    def test_swapping_between_two_redis_materias(self, fake_client: FakeClient):
        """The active RedisMateria determines which key prefix Redis uses."""
        m1 = RedisMateria()
        m2 = RedisMateria()

        @m1.bless("alpha")
        @m2.bless("beta")
        class Item(BaseTransmuter):
            id: Annotated[int, Identity] = Field(frozen=True)
            value: str

        with m1:
            fake_client.tset(Item(id=1, value="a"))
        with m2:
            fake_client.tset(Item(id=1, value="b"))

        # Both writes coexist under different namespaces.
        assert fake_client.get("alpha:1") is not None
        assert fake_client.get("beta:1") is not None

        with m1:
            got = fake_client.tget(Item, 1)
            assert got is not None and got.value == "a"
        with m2:
            got = fake_client.tget(Item, 1)
            assert got is not None and got.value == "b"


class TestValidationContextIsolation:
    """The SQL session's per-transaction validation_context must not be touched
    by Redis operations, and Redis-rehydrated transmuters must not leak into
    any active SQL validation_context.
    """

    def test_redis_ops_do_not_mutate_sql_validation_context(
        self, engine: Engine, fake_client: FakeClient
    ):
        madrid_id = 1004

        with sqlalchemy_materia, Session(engine) as session, session.begin():
            session.add(City(id=madrid_id, name="Madrid"))

        with sqlalchemy_materia, Session(engine) as session:
            from_db = session.get(City, madrid_id)
            assert from_db is not None

            # The session's validation_context now binds the ORM provider to
            # the wrapping transmuter.
            ctx = session._validation_context
            keys_before = set(ctx.keys())
            assert from_db.__transmuter_provided__ in keys_before

            # Switch to redis briefly — these ops must NOT mutate the SQL ctx.
            with redis_materia:
                fake_client.tset(from_db)
                cached = fake_client.tget(City, madrid_id)
                assert cached is not None

            # Same dict object, same keys, same values.
            assert session._validation_context is ctx
            assert set(ctx.keys()) == keys_before
            assert ctx[from_db.__transmuter_provided__] is from_db

    def test_active_validated_contextvar_restored_after_redis_block(
        self, engine: Engine, fake_client: FakeClient
    ):
        """Entering/leaving a redis context must not perturb the global
        ``validated`` ContextVar that SQL Session has set up."""
        with sqlalchemy_materia, Session(engine) as session:
            sql_ctx = validated.get()
            assert sql_ctx is session._validation_context

            with redis_materia:
                fake_client.tset(City(id=1005, name="Lima"))
                # Inside the redis block the ContextVar is unchanged — Redis
                # never touches `validated`.
                assert validated.get() is sql_ctx

            # And it is still pointing at the SQL session's context after exit.
            assert validated.get() is sql_ctx

    def test_redis_rehydrated_transmuter_has_no_provider(
        self, engine: Engine, fake_client: FakeClient
    ):
        """A transmuter loaded from Redis JSON has no ORM provider attached,
        so it cannot accidentally collide with a SQL session's validation_context."""
        with redis_materia:
            fake_client.tset(City(id=1006, name="Cairo"))

        with redis_materia:
            cached = fake_client.tget(City, 1006)
        assert cached is not None
        assert cached.__transmuter_provided__ is None

    def test_redis_get_inside_sql_session_does_not_register_in_ctx(
        self, engine: Engine, fake_client: FakeClient
    ):
        """A redis tget while a SQL session is open must not register the
        rehydrated instance in the SQL session's validation_context."""
        oslo_id = 1007

        with redis_materia:
            fake_client.tset(City(id=oslo_id, name="Oslo"))

        with sqlalchemy_materia, Session(engine) as session:
            keys_before = set(session._validation_context.keys())

            with redis_materia:
                cached = fake_client.tget(City, oslo_id)
                assert cached is not None

            # The redis-rehydrated instance is NOT in the SQL ctx, and the
            # SQL ctx itself is unchanged.
            assert set(session._validation_context.keys()) == keys_before
            assert cached not in session._validation_context.values()
