from __future__ import annotations

from sqlalchemy import Engine

from arcanus import Cursor, Page, PagedCriteria
from arcanus.materia.sqlalchemy import Session
from tests.transmuters import Author, Book, BookDetail, Category, Publisher


class TestCursorPagination:
    def test_cursor_pagination_with_expressions_orders_and_count(self, engine: Engine):
        """Test cursor payloads can drive expression pagination outside Session."""
        criteria_model = PagedCriteria[Author]
        payload = {
            "name": {"starts_with": "Cursor Page"},
            "field": {"eq": "Science Fiction"},
            "order_by": ["+id"],
            "limit": 2,
        }
        criteria = criteria_model.model_validate(payload)

        with Session(engine) as session:
            authors = [
                Author(name="Cursor Page A", field="Science Fiction"),
                Author(name="Cursor Page B", field="Science Fiction"),
                Author(name="Cursor Page C", field="Science Fiction"),
                Author(name="Cursor Page D", field="Science Fiction"),
                Author(name="Cursor Page Outside", field="History"),
            ]
            session.add_all(authors)
            session.flush()
            for author in authors:
                author.revalidate()

            assert criteria.expression is not None
            criteria_expression = criteria.expression
            total = session.count(Author, expressions=[criteria_expression])
            first_items = session.list(
                Author,
                limit=criteria.limit,
                order_bys=criteria.orders,
                expressions=[criteria_expression],
            )
            last_author_id = first_items[-1].id
            assert last_author_id is not None
            next_payload = criteria_expression.dump()
            next_payload["limit"] = criteria.limit
            next_payload["order_by"] = [order.dump() for order in criteria.orders]
            next_payload["bookmark"] = {"id": {"gt": last_author_id}}
            next_criteria = criteria_model.model_validate(next_payload)
            first_cursor = Cursor[Author].from_expression(
                expression=criteria_expression,
                bookmark=Author["id"] > last_author_id,
                order_bys=criteria.orders,
                limit=criteria.limit,
            )
            first_page = Page(
                items=tuple(first_items),
                next_cursor=str(first_cursor),
                has_more=total > len(first_items),
            )

            assert first_page.next_cursor is not None
            decoded = Cursor[Author](first_page.next_cursor)
            assert decoded.criteria.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ) == next_criteria.model_dump(mode="json", by_alias=True, exclude_none=True)
            assert decoded.criteria.expression is not None
            second_items = session.list(
                Author,
                limit=decoded.criteria.limit,
                order_bys=decoded.criteria.orders,
                expressions=[decoded.criteria.expression],
            )
            second_page = Page(
                items=tuple(second_items),
                next_cursor=None,
                has_more=total > len(first_page) + len(second_items),
            )

            assert total == 4
            assert [author.name for author in first_page] == [
                "Cursor Page A",
                "Cursor Page B",
            ]
            assert first_page.has_more is True
            assert [author.name for author in second_page] == [
                "Cursor Page C",
                "Cursor Page D",
            ]
            assert second_page.has_more is False

    def test_cursor_pagination_with_reverse_non_id_order(self, engine: Engine):
        """Test user-supplied bookmark expressions with descending non-id orders."""
        criteria_model = PagedCriteria[Author]
        payload = {
            "name": {"starts_with": "Reverse Cursor"},
            "order_by": ["-name"],
            "limit": 2,
        }
        criteria = criteria_model.model_validate(payload)

        with Session(engine) as session:
            authors = [
                Author(name="Reverse Cursor A", field="Quantum Physics"),
                Author(name="Reverse Cursor B", field="Quantum Physics"),
                Author(name="Reverse Cursor C", field="Quantum Physics"),
                Author(name="Reverse Cursor D", field="Quantum Physics"),
            ]
            session.add_all(authors)
            session.flush()
            for author in authors:
                author.revalidate()

            assert criteria.expression is not None
            criteria_expression = criteria.expression
            first_items = session.list(
                Author,
                limit=criteria.limit,
                order_bys=criteria.orders,
                expressions=[criteria_expression],
            )
            cursor = Cursor[Author].from_criteria(criteria=criteria)
            decoded = Cursor[Author](str(cursor))
            assert decoded.criteria.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ) == criteria.model_dump(mode="json", by_alias=True, exclude_none=True)
            next_payload = criteria.model_dump(
                mode="json", by_alias=True, exclude_none=True
            )
            assert first_items[-1].id is not None
            next_payload["bookmark"] = {"id": {"lt": first_items[-1].id}}
            next_criteria = criteria_model.model_validate(next_payload)
            next_cursor = Cursor[Author].from_criteria(criteria=next_criteria)
            decoded = Cursor[Author](str(next_cursor))
            assert decoded.criteria.expression is not None

            next_items = session.list(
                Author,
                limit=decoded.criteria.limit,
                order_bys=decoded.criteria.orders,
                expressions=[decoded.criteria.expression],
            )

            assert [author.name for author in first_items] == [
                "Reverse Cursor D",
                "Reverse Cursor C",
            ]
            assert [author.name for author in next_items] == [
                "Reverse Cursor B",
                "Reverse Cursor A",
            ]

    def test_cursor_pagination_list_and_partitions_share_next_page(
        self, engine: Engine
    ):
        """Test decoded cursors drive the same next page through list and partitions."""
        criteria_model = PagedCriteria[Author]
        payload = {
            "and": [
                {"name": {"starts_with": "Full Cursor"}},
                {"field": {"eq": "Robotics"}},
            ],
            "not": {"name": {"ends_with": "Outside"}},
            "order_by": ["+id"],
            "limit": 2,
        }
        criteria = criteria_model.model_validate(payload)

        with Session(engine) as session:
            authors = [
                Author(name="Full Cursor A", field="Robotics"),
                Author(name="Full Cursor B", field="Robotics"),
                Author(name="Full Cursor C", field="Robotics"),
                Author(name="Full Cursor D", field="Robotics"),
                Author(name="Full Cursor Outside", field="Robotics"),
                Author(name="Full Cursor Wrong Field", field="History"),
            ]
            session.add_all(authors)
            session.flush()
            for author in authors:
                author.revalidate()

            assert criteria.expression is not None
            criteria_expression = criteria.expression
            first_items = session.list(
                Author,
                limit=criteria.limit,
                order_bys=criteria.orders,
                expressions=[criteria_expression],
            )
            last_author_id = first_items[-1].id
            assert last_author_id is not None
            next_payload = criteria.model_dump(
                mode="json", by_alias=True, exclude_none=True
            )
            next_payload["bookmark"] = {"id": {"gt": last_author_id}}
            next_criteria = criteria_model.model_validate(next_payload)
            cursor = Cursor[Author].from_criteria(criteria=next_criteria)
            first_page = Page(
                items=tuple(first_items),
                next_cursor=str(cursor),
                has_more=True,
            )

            assert first_page.next_cursor is not None
            decoded = Cursor[Author](first_page.next_cursor)
            assert decoded.criteria.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ) == next_criteria.model_dump(mode="json", by_alias=True, exclude_none=True)
            assert decoded.criteria.expression is not None
            next_list_items = session.list(
                Author,
                limit=decoded.criteria.limit,
                order_bys=decoded.criteria.orders,
                expressions=[decoded.criteria.expression],
            )
            next_partition_items = [
                item
                for partition in session.partitions(
                    Author,
                    size=1,
                    limit=decoded.criteria.limit,
                    order_bys=decoded.criteria.orders,
                    expressions=[decoded.criteria.expression],
                )
                for item in partition
            ]

            assert [author.name for author in first_page] == [
                "Full Cursor A",
                "Full Cursor B",
            ]
            assert [author.name for author in next_list_items] == [
                "Full Cursor C",
                "Full Cursor D",
            ]
            assert [author.name for author in next_partition_items] == [
                "Full Cursor C",
                "Full Cursor D",
            ]

    def test_cursor_pagination_with_complex_criteria_and_relationship_filters(
        self, engine: Engine
    ):
        """Test cursor payloads with complex criteria and relationship filters."""
        criteria_model = PagedCriteria[Book]
        payload = {
            "and": [
                {"title": {"starts_with": "Rel Cursor"}},
                {"year": {"ge": 2020}},
            ],
            "or": [
                {"title": {"contains": "Match"}},
                {"title": {"contains": "Next"}},
            ],
            "not": {"title": {"contains": "Skip"}},
            "order_by": ["+id"],
            "limit": 1,
        }
        criteria = criteria_model.model_validate(payload)

        with Session(engine) as session:
            publisher = Publisher(name="Rel Cursor Publisher", country="USA")
            matching_author = Author(name="Rel Cursor Author", field="Astrophysics")
            other_author = Author(name="Rel Cursor Other Author", field="History")
            category = Category(name="Rel Cursor Category", description="Pagination")
            other_category = Category(
                name="Rel Cursor Other Category", description="Pagination"
            )

            first_book = Book(title="Rel Cursor Match A", year=2024)
            first_book.author.value = matching_author
            first_book.publisher.value = publisher
            first_book.detail.value = BookDetail(
                isbn="978-8888830001",
                pages=310,
                abstract="first cursor match",
            )
            first_book.categories.append(category)

            second_book = Book(title="Rel Cursor Next B", year=2025)
            second_book.author.value = matching_author
            second_book.publisher.value = publisher
            second_book.detail.value = BookDetail(
                isbn="978-8888830002",
                pages=420,
                abstract="second cursor match",
            )
            second_book.categories.append(category)

            wrong_author_book = Book(title="Rel Cursor Match Wrong Author", year=2024)
            wrong_author_book.author.value = other_author
            wrong_author_book.publisher.value = publisher
            wrong_author_book.detail.value = BookDetail(
                isbn="978-8888830003",
                pages=510,
                abstract="wrong author",
            )
            wrong_author_book.categories.append(category)

            wrong_category_book = Book(
                title="Rel Cursor Match Wrong Category", year=2024
            )
            wrong_category_book.author.value = matching_author
            wrong_category_book.publisher.value = publisher
            wrong_category_book.detail.value = BookDetail(
                isbn="978-8888830004",
                pages=610,
                abstract="wrong category",
            )
            wrong_category_book.categories.append(other_category)

            skipped_book = Book(title="Rel Cursor Skip Match", year=2024)
            skipped_book.author.value = matching_author
            skipped_book.publisher.value = publisher
            skipped_book.detail.value = BookDetail(
                isbn="978-8888830005",
                pages=710,
                abstract="skipped by not criteria",
            )
            skipped_book.categories.append(category)

            short_book = Book(title="Rel Cursor Match Too Short", year=2024)
            short_book.author.value = matching_author
            short_book.publisher.value = publisher
            short_book.detail.value = BookDetail(
                isbn="978-8888830006",
                pages=120,
                abstract="too short",
            )
            short_book.categories.append(category)

            session.add_all(
                [
                    first_book,
                    second_book,
                    wrong_author_book,
                    wrong_category_book,
                    skipped_book,
                    short_book,
                ]
            )
            session.flush()
            first_book.revalidate()
            second_book.revalidate()

            assert criteria.expression is not None
            criteria_expression = criteria.expression
            relationship_expression = (
                Book["author"].has(Author["field"] == "Astrophysics")
                & Book["categories"].any(Category["name"] == "Rel Cursor Category")
                & Book["detail"].has(BookDetail["pages"] >= 300)
            )
            expressions = [criteria_expression, relationship_expression]
            total = session.count(Book, expressions=expressions)
            first_items = session.list(
                Book,
                limit=criteria.limit,
                order_bys=criteria.orders,
                expressions=expressions,
            )
            last_book_id = first_items[-1].id
            assert last_book_id is not None
            next_payload = criteria.model_dump(
                mode="json", by_alias=True, exclude_none=True
            )
            next_payload["bookmark"] = {"id": {"gt": last_book_id}}
            next_criteria = criteria_model.model_validate(next_payload)
            cursor = Cursor[Book].from_criteria(criteria=next_criteria)
            decoded = Cursor[Book](str(cursor))
            assert decoded.criteria.expression is not None
            next_expressions = [decoded.criteria.expression, relationship_expression]
            next_list_items = session.list(
                Book,
                limit=decoded.criteria.limit,
                order_bys=decoded.criteria.orders,
                expressions=next_expressions,
            )
            next_partition_items = [
                item
                for partition in session.partitions(
                    Book,
                    size=1,
                    limit=decoded.criteria.limit,
                    order_bys=decoded.criteria.orders,
                    expressions=next_expressions,
                )
                for item in partition
            ]

            assert total == 2
            assert decoded.criteria.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ) == next_criteria.model_dump(mode="json", by_alias=True, exclude_none=True)
            assert [book.title for book in first_items] == ["Rel Cursor Match A"]
            assert [book.title for book in next_list_items] == ["Rel Cursor Next B"]
            assert [book.title for book in next_partition_items] == [
                "Rel Cursor Next B"
            ]
