# -*- coding: utf-8 -*-

"""
The MIT License (MIT)

Copyright (c) 2015-2021 Rapptz & (c) 2021-present mccoderpy

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""

from __future__ import annotations

from typing import (
    Any,
    Type,
    Optional,
    TYPE_CHECKING
)

if TYPE_CHECKING:
    from .abc import Snowflake
    from datetime import datetime
    from .state import ConnectionState


from .types.snowflake import SnowflakeID

from . import utils
from .mixins import Hashable

MISSING = utils.MISSING

__all__ = (
    'Object',
)


class Object(Hashable):
    """Represents a generic Discord object.

    The purpose of this class is to allow you to create 'miniature'
    versions of data classes if you want to pass in just an ID. Most functions
    that take in a specific data class with an ID can also take in this class
    as a substitute instead. Note that even though this is the case, not all
    objects (if any) actually inherit from this class.

    There are also some cases where some websocket events are received
    in :old-issue:`strange order <21>` and when such events happened you would
    receive this class rather than the actual data class. These cases are
    extremely rare.

    .. container:: operations

        .. describe:: x == y

            Checks if two objects are equal.

        .. describe:: x != y

            Checks if two objects are not equal.

        .. describe:: hash(x)

            Returns the object's hash.

    Attributes
    -----------
    id: :class:`int`
        The ID of the object.
    type: :class:`object`
        The object this should represent if any.
    """
    id: int

    def __init__(
            self,
            id: SnowflakeID,
            type: Type = MISSING,
            *,
            state: Optional[ConnectionState] = MISSING
    ):
        try:
            self.id: int = int(id)
        except (ValueError, TypeError):
            raise TypeError('id parameter must be convertible to int not {0.__class__!r}'.format(id)) from None

        self.type: Type = type
        self._state: Optional[ConnectionState] = state

    def __repr__(self) -> str:
        return f'<Object id={self.id!r} type={self.type!r}>'
    
    def __instancecheck__(self, other: Any) -> bool:
        if self.type is not MISSING:
            return self.type == type(other)  # This can make some problems, so the lib doesn't use it
        return self.__class__ == type(other)
    
    @property
    def created_at(self) -> datetime:
        """:class:`datetime.datetime`: Returns the snowflake's creation time in UTC."""
        return utils.snowflake_time(self.id)


if TYPE_CHECKING:
    class Object(Snowflake, Object):
        pass