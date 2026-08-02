from typing import List

from bot.models import Task


async def top_categories(limit: int = 3) -> List[str]:
    """Most used task categories across the household, most-used first."""
    rows = await Task.aggregate(
        [
            {"$match": {"category": {"$ne": None}}},
            {"$group": {"_id": "$category", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": limit},
        ]
    ).to_list()
    return [row["_id"] for row in rows]
