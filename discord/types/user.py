# -*- coding: utf-8 -*-

"""
The MIT License (MIT)

Copyright (c) 2021-present mccoderpy

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
    List,
    Optional,
    TypedDict
)

from typing_extensions import (
    NotRequired
)

from .snowflake import SnowflakeID, SnowflakeList

__all__ = (
    'BaseUser',
    'User',
    'ClientUser',
    'WebhookUser',
    'PartialMember',
    'Member',
    'MemberWithUser',
    'UserWithMember'
)


class AvatarDecoration(TypedDict):
    sku_id: SnowflakeID
    asset: str

class BaseUser(TypedDict):
    id: SnowflakeID
    username: str
    global_name: Optional[str]
    discriminator: str  # Deprecated :(
    avatar: Optional[str]


class User(BaseUser, total=False):
    public_flags: NotRequired[int]
    bot: NotRequired[bool]
    system: NotRequired[bool]
    avatar_decoration: NotRequired[str]
    avatar_decoration_data: NotRequired[AvatarDecoration]
    banner: NotRequired[Optional[str]]
    accent_color: NotRequired[Optional[int]]


class ClientUser(User, total=False):
    verified: NotRequired[bool]
    mfa_enabled: NotRequired[bool]
    flags: NotRequired[int]
    locale: NotRequired[str]
    # There are some other fields, but they are not usable by bots so empty


class WebhookUser(TypedDict):
    id: SnowflakeID
    username: str
    avatar: Optional[str]
    

class PartialMember(TypedDict):
    roles: SnowflakeList
    deaf: bool
    mute: bool
    joined_at: str
    flags: NotRequired[int]
    

class Member(PartialMember):
    avatar: NotRequired[Optional[str]]
    banner: NotRequired[Optional[str]]
    user: User
    nick: NotRequired[Optional[str]]
    premium_since: NotRequired[Optional[str]]
    pending: NotRequired[bool]
    permissions: NotRequired[str]
    communication_disabled_until: NotRequired[Optional[str]]
    

class _OptionalMemberWithUser(PartialMember):
    avatar: NotRequired[Optional[str]]
    banner: NotRequired[Optional[str]]
    nick: NotRequired[Optional[str]]
    premium_since: Optional[str]
    pending: NotRequired[bool]
    permissions: NotRequired[str]
    communication_disabled_until: NotRequired[Optional[str]]


class MemberWithUser(_OptionalMemberWithUser):
    user: User


class UserWithMember(User, total=False):
    member: _OptionalMemberWithUser

