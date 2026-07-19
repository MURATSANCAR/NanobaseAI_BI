"""Scenario family catalog codes."""

from __future__ import annotations

from enum import Enum


class ScenarioFamily(str, Enum):
    LIST_ENTITY = "LIST_ENTITY"
    COUNT_ENTITY = "COUNT_ENTITY"
    SUM_MEASURE = "SUM_MEASURE"
    AVERAGE_MEASURE = "AVERAGE_MEASURE"
    MIN_MAX = "MIN_MAX"
    TOP_N = "TOP_N"
    GROUP_MEASURE = "GROUP_MEASURE"
    COMPARE_PERIOD = "COMPARE_PERIOD"
    AGING = "AGING"
    STATUS_FILTER = "STATUS_FILTER"
    MISSING_DATA = "MISSING_DATA"
    ORPHAN_RELATION = "ORPHAN_RELATION"
    DUPLICATE = "DUPLICATE"
    RATIO = "RATIO"
    TIME_TREND = "TIME_TREND"
