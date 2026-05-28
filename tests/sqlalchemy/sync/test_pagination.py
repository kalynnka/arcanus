from __future__ import annotations

from sqlalchemy import Engine

from arcanus import Criteria, Cursor, Page
from arcanus.materia.sqlalchemy import Session
from tests.transmuters import Author


class TestCursorPagination:
    def test_cursor_pagination_with_expressions_orders_and_count(self, engine: Engine):
        criteria = Criteria[Author].model_validate(
            {
                "name": {"starts_with": "Cursor Manual Page"},
                "field": {"eq": "Science Fiction"},
            }
        )
        limit = 2
        orders = (Author["id"].asc(),)

        with Session(engine) as session:
            authors = [
                Author(name="Cursor Manual Page A", field="Science Fiction"),
                Author(name="Cursor Manual Page B", field="Science Fiction"),
                Author(name="Cursor Manual Page C", field="Science Fiction"),
                Author(name="Cursor Manual Page D", field="Science Fiction"),
                Author(name="Cursor Manual Page Outside", field="History"),
            ]
            session.add_all(authors)
            session.flush()
            for author in authors:
                author.revalidate()

            total = session.count(Author, expressions=criteria.expressions)
            first_items = session.list(
                Author,
                limit=limit + 1,
                order_bys=orders,
                expressions=criteria.expressions,
            )
            first_page_items = tuple(first_items[:limit])
            first_bookmark = Cursor[Author].bookmark_from_item(
                first_page_items[-1], orders
            )
            first_cursor = Cursor[Author].from_expressions(
                expressions=criteria.expressions,
                bookmark=first_bookmark,
                order_bys=orders,
                limit=limit,
            )
            first_page = Page(
                items=first_page_items,
                total=total,
                next_cursor=str(first_cursor),
                has_more=len(first_items) > limit,
            )

            decoded = Cursor[Author](first_page.next_cursor)
            assert decoded.criteria is not None
            bookmark_expression = decoded.bookmark.expression
            second_items = session.list(
                Author,
                limit=decoded.limit + 1 if decoded.limit is not None else None,
                order_bys=decoded.order_by.orders,
                expressions=(
                    *decoded.criteria.expressions,
                    *(
                        (bookmark_expression,)
                        if bookmark_expression is not None
                        else ()
                    ),
                ),
            )
            second_page_items = tuple(second_items[: decoded.limit])
            second_bookmark = (
                Cursor[Author].bookmark_from_item(
                    second_page_items[-1], decoded.order_by.orders
                )
                if second_page_items
                else decoded.bookmark.expression
            )
            second_cursor = Cursor[Author].from_expressions(
                expressions=decoded.criteria.expressions,
                bookmark=second_bookmark,
                order_bys=decoded.order_by.orders,
                limit=decoded.limit,
            )
            second_page = Page(
                items=second_page_items,
                total=total,
                next_cursor=str(second_cursor),
                has_more=len(second_items) > limit,
            )

            assert total == 4
            assert first_page.has_more is True
            assert [author.name for author in first_page] == [
                "Cursor Manual Page A",
                "Cursor Manual Page B",
            ]
            assert decoded.order_by == ("+id",)
            assert decoded.bookmark.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ) == {"id": {"gt": authors[1].id}}
            assert second_page.has_more is False
            assert second_page.next_cursor is not None
            assert [author.name for author in second_page] == [
                "Cursor Manual Page C",
                "Cursor Manual Page D",
            ]

    def test_cursor_pagination_with_descending_user_order(self, engine: Engine):
        criteria = Criteria[Author].model_validate(
            {"name": {"starts_with": "Descending Manual Cursor"}}
        )
        limit = 2
        orders = (Author["name"].desc(),)

        with Session(engine) as session:
            authors = [
                Author(name="Descending Manual Cursor A", field="Physics"),
                Author(name="Descending Manual Cursor B", field="Physics"),
                Author(name="Descending Manual Cursor C", field="Physics"),
                Author(name="Descending Manual Cursor D", field="Physics"),
            ]
            session.add_all(authors)
            session.flush()
            for author in authors:
                author.revalidate()

            first_items = session.list(
                Author,
                limit=limit + 1,
                order_bys=orders,
                expressions=criteria.expressions,
            )
            first_page_items = tuple(first_items[:limit])
            bookmark = Cursor[Author].bookmark_from_item(first_page_items[-1], orders)
            cursor = Cursor[Author].from_expressions(
                expressions=criteria.expressions,
                bookmark=bookmark,
                order_bys=orders,
                limit=limit,
            )
            decoded = Cursor[Author](str(cursor))
            assert decoded.criteria is not None
            bookmark_expression = decoded.bookmark.expression

            second_items = session.list(
                Author,
                limit=decoded.limit + 1 if decoded.limit is not None else None,
                order_bys=decoded.order_by.orders,
                expressions=(
                    *decoded.criteria.expressions,
                    *(
                        (bookmark_expression,)
                        if bookmark_expression is not None
                        else ()
                    ),
                ),
            )
            second_page_items = tuple(second_items[: decoded.limit])
            second_bookmark = (
                Cursor[Author].bookmark_from_item(
                    second_page_items[-1], decoded.order_by.orders
                )
                if second_page_items
                else decoded.bookmark.expression
            )
            second_cursor = Cursor[Author].from_expressions(
                expressions=decoded.criteria.expressions,
                bookmark=second_bookmark,
                order_bys=decoded.order_by.orders,
                limit=decoded.limit,
            )
            second_page = Page(
                items=second_page_items,
                total=4,
                next_cursor=str(second_cursor),
                has_more=len(second_items) > limit,
            )

            assert [author.name for author in first_page_items] == [
                "Descending Manual Cursor D",
                "Descending Manual Cursor C",
            ]
            assert decoded.order_by == ("-name",)
            assert decoded.bookmark.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ) == {"name": {"lt": "Descending Manual Cursor C"}}
            assert second_page.has_more is False
            assert second_page.next_cursor is not None
            assert [author.name for author in second_page] == [
                "Descending Manual Cursor B",
                "Descending Manual Cursor A",
            ]

    def test_cursor_pagination_with_empty_result_has_empty_bookmark(
        self, engine: Engine
    ):
        criteria = Criteria[Author].model_validate(
            {"name": {"starts_with": "Empty Manual Cursor"}}
        )
        limit = 2
        orders = (Author["id"].desc(),)

        with Session(engine) as session:
            total = session.count(Author, expressions=criteria.expressions)
            first_items = session.list(
                Author,
                limit=limit + 1,
                order_bys=orders,
                expressions=criteria.expressions,
            )
            first_page_items = tuple(first_items[:limit])
            bookmark = (
                Cursor[Author].bookmark_from_item(first_page_items[-1], orders)
                if first_page_items
                else None
            )
            cursor = Cursor[Author].from_expressions(
                expressions=criteria.expressions,
                bookmark=bookmark,
                order_bys=orders,
                limit=limit,
            )
            page = Page(
                items=first_page_items,
                total=total,
                next_cursor=str(cursor),
                has_more=len(first_items) > limit,
            )

            decoded = Cursor[Author](page.next_cursor)

            assert page.items == ()
            assert page.total == 0
            assert page.has_more is False
            assert decoded.bookmark.expression is None
            assert (
                decoded.bookmark.model_dump(
                    mode="json", by_alias=True, exclude_none=True
                )
                == {}
            )
