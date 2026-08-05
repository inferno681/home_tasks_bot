from typing import Optional

from beanie import PydanticObjectId
from bson.errors import InvalidId


def parse_int(raw: str) -> Optional[int]:
    """Parse an int out of callback_data, tolerating forged/malformed input."""
    try:
        return int(raw)
    except ValueError:
        return None


def parse_object_id(raw: str) -> Optional[PydanticObjectId]:
    """Parse an ObjectId out of callback_data, same tolerance as above."""
    try:
        return PydanticObjectId(raw)
    except InvalidId:
        return None
