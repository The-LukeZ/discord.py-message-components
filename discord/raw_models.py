# -*- coding: utf-8 -*-

"""
The MIT License (MIT)

Copyright (c) 2015-2021 Rapptz & 2021-present mccoderpy

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

from typing import TYPE_CHECKING, Optional

from .utils import _get_as_snowflake
from .member import Member
from .user import User
from .partial_emoji import PartialEmoji
from .message import Message
from .enums import ReactionType, try_enum

if TYPE_CHECKING:
    from .state import ConnectionState


class _RawReprMixin:
    def __repr__(self):
        value = ' '.join('%s=%r' % (attr, getattr(self, attr)) for attr in self.__slots__)
        return '<%s %s>' % (self.__class__.__name__, value)


class RawMessageDeleteEvent(_RawReprMixin):
    """Represents the event payload for a :func:`on_raw_message_delete` event.

    Attributes
    ------------
    channel_id: :class:`int`
        The channel ID where the deletion took place.
    guild_id: Optional[:class:`int`]
        The guild ID where the deletion took place, if applicable.
    message_id: :class:`int`
        The message ID that got deleted.
    cached_message: Optional[:class:`Message`]
        The cached message, if found in the internal message cache.
    """

    __slots__ = ('message_id', 'channel_id', 'guild_id', 'cached_message')

    def __init__(self, data):
        self.message_id = int(data['id'])
        self.channel_id = int(data['channel_id'])
        self.cached_message = None
        try:
            self.guild_id = int(data['guild_id'])
        except KeyError:
            self.guild_id = None


class RawBulkMessageDeleteEvent(_RawReprMixin):
    """Represents the event payload for a :func:`on_raw_bulk_message_delete` event.

    Attributes
    -----------
    message_ids: Set[:class:`int`]
        A :class:`set` of the message IDs that were deleted.
    channel_id: :class:`int`
        The channel ID where the message got deleted.
    guild_id: Optional[:class:`int`]
        The guild ID where the message got deleted, if applicable.
    cached_messages: List[:class:`Message`]
        The cached messages, if found in the internal message cache.
    """

    __slots__ = ('message_ids', 'channel_id', 'guild_id', 'cached_messages')

    def __init__(self, data):
        self.message_ids = {int(x) for x in data.get('ids', [])}
        self.channel_id = int(data['channel_id'])
        self.cached_messages = []

        try:
            self.guild_id = int(data['guild_id'])
        except KeyError:
            self.guild_id = None


class RawMessageUpdateEvent(_RawReprMixin):
    """Represents the payload for a :func:`on_raw_message_edit` event.

    Attributes
    -----------
    message_id: :class:`int`
        The message ID that got updated.
    channel_id: :class:`int`
        The channel ID where the update took place.

        .. versionadded:: 1.3
    guild_id: Optional[:class:`int`]
        The guild ID where the message got updated, if applicable.

        .. versionadded:: 1.7

    data: :class:`dict`
        The raw data given by the `gateway <https://discord.com/developers/docs/topics/gateway#message-update>`_
    cached_message: Optional[:class:`Message`]
        The cached message, if found in the internal message cache. Represents the message before
        it is modified by the data in :attr:`RawMessageUpdateEvent.data`.
    """

    __slots__ = ('message_id', 'channel_id', 'guild_id', 'data', 'cached_message')

    def __init__(self, data):
        self.message_id = int(data['id'])
        self.channel_id = int(data['channel_id'])
        self.data = data
        self.cached_message = None

        try:
            self.guild_id = int(data['guild_id'])
        except KeyError:
            self.guild_id = None


class RawReactionActionEvent(_RawReprMixin):
    """Represents the payload for a :func:`on_raw_reaction_add` or
    :func:`on_raw_reaction_remove` event.

    Attributes
    -----------
    message_id: :class:`int`
        The message ID that got or lost a reaction.
    user_id: :class:`int`
        The user ID who added the reaction or whose reaction was removed.
    channel_id: :class:`int`
        The channel ID where the reaction got added or removed.
    guild_id: Optional[:class:`int`]
        The guild ID where the reaction got added or removed, if applicable.
    emoji: :class:`PartialEmoji`
        The custom or unicode emoji being used.
    member: Optional[:class:`Member`]
        The member who added the reaction. Only available if `event_type` is `REACTION_ADD` and the reaction is inside a guild.

        .. versionadded:: 1.3

    event_type: :class:`str`
        The event type that triggered this action. Can be
        ``REACTION_ADD`` for reaction addition or
        ``REACTION_REMOVE`` for reaction removal.

        .. versionadded:: 1.3
    """

    __slots__ = ('message_id', 'user_id', 'channel_id', 'guild_id', 'emoji',
                 'event_type', '_type', 'member')

    def __init__(self, data, emoji, event_type):
        self.message_id = int(data['message_id'])
        self.channel_id = int(data['channel_id'])
        self.user_id = int(data['user_id'])
        self.emoji = emoji
        self.event_type = event_type
        self.member = None
        self._type = data.get('type', 0)

        try:
            self.guild_id = int(data['guild_id'])
        except KeyError:
            self.guild_id = None

    @property
    def type(self) -> ReactionType:
        """
        :class:`ReactionType`: The type of reaction; e.g. normal or burst.

        .. versionadded:: 2.0
        """
        return try_enum(ReactionType, self._type)

    # TODO: Add support for things like query reaction members and co. from here.


class RawReactionClearEvent(_RawReprMixin):
    """Represents the payload for a :func:`on_raw_reaction_clear` event.

    Attributes
    -----------
    message_id: :class:`int`
        The message ID that got its reactions cleared.
    channel_id: :class:`int`
        The channel ID where the reactions got cleared.
    guild_id: Optional[:class:`int`]
        The guild ID where the reactions got cleared.
    """

    __slots__ = ('message_id', 'channel_id', 'guild_id')

    def __init__(self, data):
        self.message_id = int(data['message_id'])
        self.channel_id = int(data['channel_id'])

        try:
            self.guild_id = int(data['guild_id'])
        except KeyError:
            self.guild_id = None


class RawReactionClearEmojiEvent(_RawReprMixin):
    """Represents the payload for a :func:`on_raw_reaction_clear_emoji` event.

    .. versionadded:: 1.3

    Attributes
    -----------
    message_id: :class:`int`
        The message ID that got its reactions cleared.
    channel_id: :class:`int`
        The channel ID where the reactions got cleared.
    guild_id: Optional[:class:`int`]
        The guild ID where the reactions got cleared.
    emoji: :class:`PartialEmoji`
        The custom or unicode emoji being removed.
    """

    __slots__ = ('message_id', 'channel_id', 'guild_id', 'emoji')

    def __init__(self, data, emoji):
        self.emoji = emoji
        self.message_id = int(data['message_id'])
        self.channel_id = int(data['channel_id'])

        try:
            self.guild_id = int(data['guild_id'])
        except KeyError:
            self.guild_id = None


class VoiceChannelEffectSendEvent(_RawReprMixin):
    """
    Represents the payload for an :func:`on_voice_channel_effect_send` event.

    .. versionadded:: 2.0

    Attributes
    -----------
    guild_id: :class:`int`
        The guild ID where the effect is being sent.
    channel_id: :class:`int`
        The channel ID where the effect is being sent.
    user_id: :class:`int`
        The user ID who sent the effect.
    emoji: Optional[:class:`PartialEmoji`]
        The emoji used when this is an emoji effect or the emoji associated to the sound.
    sound_id: Optional[:class:`int`]
        The sound ID of the soundboard sound used, if any.
    sound_volume: Optional[:class:`float`]
        The volume of the soundboard sound used, if any.
    """

    __slots__ = ('guild_id', 'channel_id', 'user_id', 'emoji', 'sound_id', 'sound_volume')

    if TYPE_CHECKING:
        _state: ConnectionState
        guild_id: int
        channel_id: int
        user_id: int
        emoji: Optional[PartialEmoji]
        sound_id: Optional[int]
        sound_volume: Optional[float]

    def __init__(self, state, data):
        self._state = state
        self.guild_id = int(data['guild_id'])
        self.channel_id = int(data['channel_id'])
        self.user_id = int(data['user_id'])
        emoji = data.get('emoji')
        self.emoji = PartialEmoji.with_state(state, **emoji) if emoji else None
        self.sound_id = _get_as_snowflake(data, 'sound_id')
        self.sound_volume = data.get('sound_volume')

    @property
    def type(self) -> str:
        """
        :class:`str`: The type of effect being sent. Can be ``emoji`` or ``sound``.
        """
        return 'emoji' if self.sound_id is None else 'sound'
