from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Type, Union, get_args, get_origin

if TYPE_CHECKING:
    import asyncpg

from pypika.queries import QueryBuilder
from pypika.terms import (
    BasicCriterion,
    Comparator,
    ComplexCriterion,
    ContainsCriterion,
    Criterion,
    Dialects,
    Equality,
    NullValue,
    Parameter,
    RangeCriterion,
)

from p3orm.core import dialect
from p3orm.exceptions import InvalidSQLiteVersion


class PormComparator(Comparator):
    empty = " "
    in_ = " IN "


def record_to_kwargs(record: asyncpg.Record) -> Dict[str, Any]:
    return {k: v for k, v in record.items()}


def with_returning(query: QueryBuilder, returning: Optional[str] = "*") -> str:
    return f"{query.get_sql()} RETURNING {returning}"


def _param(index: int) -> Parameter:
    if dialect() == Dialects.SQLLITE:
        return Parameter("?")
    else:
        return Parameter(f"${index}")


def _parameterize(criterion: Criterion, query_args: List[Any], param_index: int = 0) -> Tuple[Criterion, List[Any]]:
    if isinstance(criterion, ComplexCriterion):
        left, query_args = _parameterize(criterion.left, query_args, dialect, param_index)
        right, query_args = _parameterize(criterion.right, query_args, dialect, param_index)
        return ComplexCriterion(criterion.comparator, left, right, criterion.alias), query_args

    elif isinstance(criterion, BasicCriterion):
        print(f"\n within parameterize func")
        print(f"\n\n{criterion.right.value=}\n\n")
        query_args.append(criterion.right.value)
        print(f"\n{query_args=}\n\n")
        param_index += 1
        return (
            BasicCriterion(
                criterion.comparator,
                criterion.left,
                _param(param_index),
                criterion.alias,
            ),
            query_args,
        )

    elif isinstance(criterion, ContainsCriterion):
        if dialect() == Dialects.POSTGRESQL:
            criterion_args = [i.value for i in criterion.container.values if not isinstance(i, NullValue)]
            query_args += criterion_args
            params = []
            for i in range(len(criterion_args)):
                param_index += 1
                params.append(f"${param_index}")

            # return (
            #     ContainsCriterion(
            #         criterion.term,
            #         ", ".join(params),
            #         container.alias,
            #     ),
            #     query_args,
            # )

            return (
                BasicCriterion(
                    PormComparator.in_,
                    criterion.term,
                    Parameter(f"""({", ".join(params)})"""),
                    criterion.alias,
                ),
                query_args,
            )

            # return (
            #     BasicCriterion(
            #         Equality.eq,
            #         criterion.term,
            #         _param(len(query_args)),
            #         criterion.alias,
            #     ),
            #     query_args,
            # )
        else:
            qs = ", ".join("?" for i in range(len(criterion.container.values)))
            param = Parameter(f"IN ({qs})")

            for i in criterion.container.values:
                if not isinstance(i, NullValue):
                    query_args.append(i.value)
                else:
                    query_args.append(None)

            return BasicCriterion(PormComparator.empty, criterion.term, param, criterion.alias), query_args

    elif isinstance(criterion, RangeCriterion):
        # query_args.append(criterion.start.value)
        # start_param = _param(len(query_args))
        # query_args.append(criterion.end.value)
        # end_param = _param(len(query_args))

        query_args += [criterion.start.value, criterion.end.value]
        param_index += 1
        start_param = _param(param_index)
        param_index += 1
        end_param = _param(param_index)
        # There are several RangeCriterion, create a new one with the same subclass
        return criterion.__class__(criterion.term, start_param, end_param, criterion.alias), query_args

    return criterion, query_args


def paramaterize(
    criterion: Criterion,
    query_args: List[Any] = None,
) -> Tuple[Criterion, List[Any]]:
    if query_args == None:
        query_args = []

    return _parameterize(criterion, query_args)


def is_optional(_type: Type):
    return get_origin(_type) is Union and type(None) in get_args(_type)


def validate_sqlite_version():
    if sqlite3.sqlite_version_info < (3, 35, 0):
        raise InvalidSQLiteVersion("p3orm requires SQLite engine version 3.35 or higher")
