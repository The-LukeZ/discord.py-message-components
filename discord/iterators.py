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

import asyncio
import datetime
from collections import namedtuple

from typing import (
    TYPE_CHECKING,
    Optional,
    Union,
    List,
)
from typing_extensions import Literal

if TYPE_CHECKING:
    from .types import (
        monetization,
    )
    from .state import ConnectionState
    from .guild import Guild
    from .abc import Snowflake, Messageable
    from .scheduled_event import GuildScheduledEvent
    from .channel import ThreadChannel, ForumPost, TextChannel, ForumChannel
    from .monetization import Entitlement

from .utils import MISSING
from .errors import NoMoreItems
from .utils import time_snowflake, maybe_coroutine
from .object import Object

OLDEST_OBJECT = Object(id=0)
BanEntry = namedtuple('BanEntry', 'reason user')


__all__ = (
    'BanEntry',
    'AuditLogIterator',
    'BanIterator',
    'EventUsersIterator',
    'GuildIterator',
    'HistoryIterator',
    'MemberIterator',
    'ReactionIterator',
    'ThreadMemberIterator',
    'EntitlementIterator',
)


class _AsyncIterator:
    __slots__ = ()

    def get(self, **attrs):
        def predicate(elem):
            for attr, val in attrs.items():
                nested = attr.split('__')
                obj = elem
                for attribute in nested:
                    obj = getattr(obj, attribute)

                if obj != val:
                    return False
            return True

        return self.find(predicate)

    async def find(self, predicate):
        while True:
            try:
                elem = await self.next()
            except NoMoreItems:
                return None

            ret = await maybe_coroutine(predicate, elem)
            if ret:
                return elem

    def chunk(self, max_size):
        if max_size <= 0:
            raise ValueError('async iterator chunk sizes must be greater than 0.')
        return _ChunkedAsyncIterator(self, max_size)

    def map(self, func):
        return _MappedAsyncIterator(self, func)

    def filter(self, predicate):
        return _FilteredAsyncIterator(self, predicate)

    async def flatten(self):
        ret = []
        while True:
            try:
                item = await self.next()
            except NoMoreItems:
                return ret
            else:
                ret.append(item)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            msg = await self.next()
        except NoMoreItems:
            raise StopAsyncIteration()
        else:
            return msg


def _identity(x):
    return x


class _ChunkedAsyncIterator(_AsyncIterator):
    def __init__(self, iterator, max_size):
        self.iterator = iterator
        self.max_size = max_size

    async def next(self):
        ret = []
        n = 0
        while n < self.max_size:
            try:
                item = await self.iterator.next()
            except NoMoreItems:
                if ret:
                    return ret
                raise
            else:
                ret.append(item)
                n += 1
        return ret


class _MappedAsyncIterator(_AsyncIterator):
    def __init__(self, iterator, func):
        self.iterator = iterator
        self.func = func

    async def next(self):
        # this raises NoMoreItems and will propagate appropriately
        item = await self.iterator.next()
        return await maybe_coroutine(self.func, item)


class _FilteredAsyncIterator(_AsyncIterator):
    def __init__(self, iterator, predicate):
        self.iterator = iterator

        if predicate is None:
            predicate = _identity

        self.predicate = predicate

    async def next(self):
        getter = self.iterator.next
        pred = self.predicate
        while True:
            # propagate NoMoreItems similar to _MappedAsyncIterator
            item = await getter()
            ret = await maybe_coroutine(pred, item)
            if ret:
                return item


class ReactionIterator(_AsyncIterator):
    def __init__(self, message, emoji, reaction_type: int, limit: int = 100, after: Optional[Snowflake] = None):
        self.message = message
        self.limit = limit
        self.after = after
        state = message._state
        self.getter = state.http.get_reaction_users
        self.state = state
        self.reaction_type = reaction_type
        self.emoji = emoji
        self.guild = message.guild
        self.channel_id = message.channel.id
        self.users = asyncio.Queue()

    async def next(self):
        if self.users.empty():
            await self.fill_users()

        try:
            return self.users.get_nowait()
        except asyncio.QueueEmpty:
            raise NoMoreItems()

    async def fill_users(self):
        # this is a hack because >circular imports<
        from .user import User

        if self.limit > 0:
            retrieve = self.limit if self.limit <= 100 else 100

            after = self.after.id if self.after else None
            data = await self.getter(
                self.channel_id, self.message.id, self.emoji, retrieve, reaction_type=self.reaction_type, after=after
            )

            if data:
                self.limit -= retrieve
                self.after = Object(id=int(data[-1]['id']))

            if self.guild is None or isinstance(self.guild, Object):
                for element in reversed(data):
                    await self.users.put(User(state=self.state, data=element))
            else:
                for element in reversed(data):
                    member_id = int(element['id'])
                    member = self.guild.get_member(member_id)
                    if member is not None:
                        await self.users.put(member)
                    else:
                        await self.users.put(User(state=self.state, data=element))


class HistoryIterator(_AsyncIterator):
    """Iterator for receiving a channel's message history.

    The messages endpoint has two behaviours we care about here:
    If ``before`` is specified, the messages endpoint returns the `limit`
    newest messages before ``before``, sorted with newest first. For filling over
    100 messages, update the ``before`` parameter to the oldest message received.
    Messages will be returned in order by time.
    If ``after`` is specified, it returns the ``limit`` oldest messages after
    ``after``, sorted with newest first. For filling over 100 messages, update the
    ``after`` parameter to the newest message received. If messages are not
    reversed, they will be out of order (99-0, 199-100, so on)

    A note that if both ``before`` and ``after`` are specified, ``before`` is ignored by the
    messages endpoint.

    Parameters
    -----------
    messageable: :class:`abc.Messageable`
        Messageable class to retrieve message history from.
    limit: :class:`int`
        Maximum number of messages to retrieve
    before: Optional[Union[:class:`abc.Snowflake`, :class:`datetime.datetime`]]
        Message before which all messages must be.
    after: Optional[Union[:class:`abc.Snowflake`, :class:`datetime.datetime`]]
        Message after which all messages must be.
    around: Optional[Union[:class:`abc.Snowflake`, :class:`datetime.datetime`]]
        Message around which all messages must be. Limit max 101. Note that if
        limit is an even number, this will return at most limit+1 messages.
    oldest_first: Optional[:class:`bool`]
        If set to ``True``, return messages in oldest->newest order. Defaults to
        ``True`` if `after` is specified, otherwise ``False``.
    """

    def __init__(self,
                 messageable: 'Messageable',
                 limit: int,
                 before: Optional[Union['Snowflake', datetime.datetime]] = None,
                 after: Optional[Union['Snowflake', datetime.datetime]] = None,
                 around: Optional[Union['Snowflake', datetime.datetime]] = None,
                 oldest_first: Optional[bool] = None):

        if isinstance(before, datetime.datetime):
            before = Object(id=time_snowflake(before, high=False))
        if isinstance(after, datetime.datetime):
            after = Object(id=time_snowflake(after, high=True))
        if isinstance(around, datetime.datetime):
            around = Object(id=time_snowflake(around))

        if oldest_first is None:
            self.reverse = after is not None
        else:
            self.reverse = oldest_first

        self.messageable = messageable
        self.limit: int = limit
        self.before: Optional[Object] = before
        self.after: Optional[Object] = after or OLDEST_OBJECT
        self.around: Optional[Object] = around

        self._filter = None  # message dict -> bool

        self.state = self.messageable._state
        self.logs_from = self.state.http.logs_from
        self.messages = asyncio.Queue()

        if self.around:
            if self.limit is None:
                raise ValueError('history does not support around with limit=None')
            if self.limit > 101:
                raise ValueError("history max limit 101 when specifying around parameter")
            elif self.limit == 101:
                self.limit = 100  # Thanks discord

            self._retrieve_messages = self._retrieve_messages_around_strategy
            if self.before and self.after:
                self._filter = lambda m: self.after.id < int(m['id']) < self.before.id
            elif self.before:
                self._filter = lambda m: int(m['id']) < self.before.id
            elif self.after:
                self._filter = lambda m: self.after.id < int(m['id'])
        else:
            if self.reverse:
                self._retrieve_messages = self._retrieve_messages_after_strategy
                if (self.before):
                    self._filter = lambda m: int(m['id']) < self.before.id
            else:
                self._retrieve_messages = self._retrieve_messages_before_strategy
                if (self.after and self.after != OLDEST_OBJECT):
                    self._filter = lambda m: int(m['id']) > self.after.id

    async def next(self):
        if self.messages.empty():
            await self.fill_messages()

        try:
            return self.messages.get_nowait()
        except asyncio.QueueEmpty:
            raise NoMoreItems()

    def _get_retrieve(self):
        l = self.limit
        if l is None or l > 100:
            r = 100
        else:
            r = l
        self.retrieve = r
        return r > 0

    async def flatten(self):
        # this is similar to fill_messages except it uses a list instead
        # of a queue to place the messages in.
        result = []
        channel = await self.messageable._get_channel()
        self.channel = channel
        while self._get_retrieve():
            data = await self._retrieve_messages(self.retrieve)
            if len(data) < 100:
                self.limit = 0  # terminate the infinite loop

            if self.reverse:
                data = reversed(data)
            if self._filter:
                data = filter(self._filter, data)

            for element in data:
                result.append(self.state.create_message(channel=channel, data=element))
        return result

    async def fill_messages(self):
        if not hasattr(self, 'channel'):
            # do the required set up
            channel = await self.messageable._get_channel()
            self.channel = channel

        if self._get_retrieve():
            data = await self._retrieve_messages(self.retrieve)
            if len(data) < 100:
                self.limit = 0  # terminate the infinite loop

            if self.reverse:
                data = reversed(data)
            if self._filter:
                data = filter(self._filter, data)

            channel = self.channel
            for element in data:
                await self.messages.put(self.state.create_message(channel=channel, data=element))

    async def _retrieve_messages(self, retrieve):
        """Retrieve messages and update next parameters."""
        pass

    async def _retrieve_messages_before_strategy(self, retrieve):
        """Retrieve messages using before parameter."""
        before = self.before.id if self.before else None
        data = await self.logs_from(self.channel.id, retrieve, before=before)
        if len(data):
            if self.limit is not None:
                self.limit -= retrieve
            self.before = Object(id=int(data[-1]['id']))
        return data

    async def _retrieve_messages_after_strategy(self, retrieve):
        """Retrieve messages using after parameter."""
        after = self.after.id if self.after else None
        data = await self.logs_from(self.channel.id, retrieve, after=after)
        if len(data):
            if self.limit is not None:
                self.limit -= retrieve
            self.after = Object(id=int(data[0]['id']))
        return data

    async def _retrieve_messages_around_strategy(self, retrieve):
        """Retrieve messages using around parameter."""
        if self.around:
            around = self.around.id if self.around else None
            data = await self.logs_from(self.channel.id, retrieve, around=around)
            self.around = None
            return data
        return []


class AuditLogIterator(_AsyncIterator):
    def __init__(self,
                 guild,
                 limit=None,
                 before=None,
                 after=None,
                 oldest_first=None,
                 user_id=None,
                 action_type=None):
        if isinstance(before, datetime.datetime):
            before = Object(id=time_snowflake(before, high=False))
        if isinstance(after, datetime.datetime):
            after = Object(id=time_snowflake(after, high=True))

        if oldest_first is None:
            self.reverse = after is not None
        else:
            self.reverse = oldest_first

        self.guild = guild
        self.loop = guild._state.loop
        self.request = guild._state.http.get_audit_logs
        self.limit = limit
        self.before = before
        self.user_id = user_id
        self.action_type = action_type
        self.after = OLDEST_OBJECT
        self._users = {}
        self._integrations = {}
        self._webhooks = {}
        self._scheduled_events = {}
        self._threads = {}
        self._application_commands = {}
        self._auto_moderation_rules = {}
        self._state = guild._state

        self._filter = None  # entry dict -> bool

        self.entries = asyncio.Queue()

        if self.reverse:
            self._strategy = self._after_strategy
            if self.before:
                self._filter = lambda m: int(m['id']) < self.before.id
        else:
            self._strategy = self._before_strategy
            if self.after and self.after != OLDEST_OBJECT:
                self._filter = lambda m: int(m['id']) > self.after.id

    async def _before_strategy(self, retrieve):
        before = self.before.id if self.before else None
        data = await self.request(self.guild.id, limit=retrieve, user_id=self.user_id,
                                  action_type=self.action_type, before=before)
        entries = data.get('audit_log_entries', [])
        if len(data) and entries:
            if self.limit is not None:
                self.limit -= retrieve
            self.before = Object(id=int(entries[-1]['id']))
        return data, entries

    async def _after_strategy(self, retrieve):
        after = self.after.id if self.after else None
        data = await self.request(self.guild.id, limit=retrieve, user_id=self.user_id,
                                  action_type=self.action_type, after=after)
        entries = data.get('audit_log_entries', [])
        if len(data) and entries:
            if self.limit is not None:
                self.limit -= retrieve
            self.after = Object(id=int(entries[0]['id']))
        return data, entries

    async def next(self):
        if self.entries.empty():
            await self._fill()

        try:
            return self.entries.get_nowait()
        except asyncio.QueueEmpty:
            raise NoMoreItems()

    def _get_retrieve(self):
        l = self.limit
        if l is None or l > 100:
            r = 100
        else:
            r = l
        self.retrieve = r
        return r > 0

    async def _fill(self):
        from .user import User
        from .integrations import _integration_factory, PartialIntegration
        from .webhook import Webhook
        from .scheduled_event import GuildScheduledEvent
        from .channel import ForumChannel, ForumPost, ThreadChannel
        from .application_commands import ApplicationCommand
        from .automod import AutoModRule
        from .audit_logs import AuditLogEntry

        if self._get_retrieve():
            data, entries = await self._strategy(self.retrieve)
            if len(entries) < 100:
                self.limit = 0  # terminate the infinite loop

            if self.reverse:
                entries = reversed(entries)
            if self._filter:
                data = filter(self._filter, data)

            _state = self._state
            _guild = self.guild

            for user in data.get('users', []):
                u = User(data=user, state=_state)
                self._users[u.id] = u

            for integration in data.get('integrations', []):
                i = PartialIntegration(data=integration, guild=_guild)
                self._integrations[i.id] = i

            for webhook in data.get('webhooks', []):
                w = Webhook.from_state(data=webhook, state=_state)
                self._webhooks[w.id] = w

            for scheduled_event in data.get('guild_scheduled_events', []):
                e = GuildScheduledEvent(state=_state, guild=_guild, data=scheduled_event)
                self._scheduled_events[e.id] = e

            for thread in data.get('threads', []):
                parent_id = int(thread.get('parent_id'))
                parent_channel = _guild.get_channel(parent_id)
                if isinstance(parent_channel, ForumChannel):
                    t = ForumPost(state=_state, guild=_guild, data=thread)
                else:
                    t = ThreadChannel(state=_state, guild=_guild, data=thread)
                self._threads[t.id] = t

            for application_command in data.get('application_commands', []):
                c = ApplicationCommand._from_type(state=_state, data=application_command)
                self._application_commands[c.id] = c

            for automod_rule in data.get('auto_moderation_rules', []):
                r = AutoModRule(state=_state, guild=_guild, **automod_rule)
                self._auto_moderation_rules[r.id] = r

            for entry in entries:
                # TODO: remove this if statement later
                if entry['action_type'] is None:
                    continue

                await self.entries.put(
                    AuditLogEntry(
                        data=entry,
                        guild=self.guild,
                        users=self._users,

                    )
                )


class GuildIterator(_AsyncIterator):
    """Iterator for receiving the client's guilds.

    The guilds endpoint has the same two behaviours as described
    in :class:`HistoryIterator`:
    If ``before`` is specified, the guilds endpoint returns the ``limit``
    newest guilds before ``before``, sorted with newest first. For filling over
    100 guilds, update the ``before`` parameter to the oldest guild received.
    Guilds will be returned in order by time.
    If `after` is specified, it returns the ``limit`` oldest guilds after ``after``,
    sorted with newest first. For filling over 100 guilds, update the ``after``
    parameter to the newest guild received, If guilds are not reversed, they
    will be out of order (99-0, 199-100, so on)

    Not that if both ``before`` and ``after`` are specified, ``before`` is ignored by the
    guilds endpoint.

    Parameters
    -----------
    bot: :class:`discord.Client`
        The client to retrieve the guilds from.
    limit: :class:`int`
        Maximum number of guilds to retrieve.
    before: Optional[Union[:class:`abc.Snowflake`, :class:`datetime.datetime`]]
        Object before which all guilds must be.
    after: Optional[Union[:class:`abc.Snowflake`, :class:`datetime.datetime`]]
        Object after which all guilds must be.
    """
    def __init__(self,
                 bot,
                 limit: int,
                 before: Optional[Union['Snowflake', datetime.datetime]] = None,
                 after: Optional[Union['Snowflake', datetime.datetime]] = None):

        if isinstance(before, datetime.datetime):
            before = Object(id=time_snowflake(before, high=False))
        if isinstance(after, datetime.datetime):
            after = Object(id=time_snowflake(after, high=True))

        self.bot = bot
        self.limit: int = limit
        self.before: Optional[Object] = before
        self.after: Optional[Object] = after

        self._filter = None

        self.state = self.bot._connection
        self.get_guilds = self.bot.http.get_guilds
        self.guilds = asyncio.Queue()

        if self.before and self.after:
            self._retrieve_guilds = self._retrieve_guilds_before_strategy
            self._filter = lambda m: int(m['id']) > self.after.id
        elif self.after:
            self._retrieve_guilds = self._retrieve_guilds_after_strategy
        else:
            self._retrieve_guilds = self._retrieve_guilds_before_strategy

    async def next(self):
        if self.guilds.empty():
            await self.fill_guilds()

        try:
            return self.guilds.get_nowait()
        except asyncio.QueueEmpty:
            raise NoMoreItems()

    def _get_retrieve(self):
        l = self.limit
        if l is None or l > 100:
            r = 100
        else:
            r = l
        self.retrieve = r
        return r > 0

    def create_guild(self, data):
        from .guild import Guild
        return Guild(state=self.state, data=data)

    async def flatten(self):
        result = []
        while self._get_retrieve():
            data = await self._retrieve_guilds(self.retrieve)
            if len(data) < 100:
                self.limit = 0

            if self._filter:
                entries = filter(self._filter, entries)

            for element in data:
                result.append(self.create_guild(element))
        return result

    async def fill_guilds(self):
        if self._get_retrieve():
            data = await self._retrieve_guilds(self.retrieve)
            if self.limit is None or len(data) < 100:
                self.limit = 0

            if self._filter:
                data = filter(self._filter, data)

            for element in data:
                await self.guilds.put(self.create_guild(element))

    async def _retrieve_guilds(self, retrieve):
        """Retrieve guilds and update next parameters."""
        pass

    async def _retrieve_guilds_before_strategy(self, retrieve):
        """Retrieve guilds using before parameter."""
        before = self.before.id if self.before else None
        data = await self.get_guilds(retrieve, before=before)
        if len(data):
            if self.limit is not None:
                self.limit -= retrieve
            self.before = Object(id=int(data[-1]['id']))
        return data

    async def _retrieve_guilds_after_strategy(self, retrieve):
        """Retrieve guilds using after parameter."""
        after = self.after.id if self.after else None
        data = await self.get_guilds(retrieve, after=after)
        if len(data):
            if self.limit is not None:
                self.limit -= retrieve
            self.after = Object(id=int(data[0]['id']))
        return data


class MemberIterator(_AsyncIterator):
    def __init__(self, guild, limit=1000, after=None):

        if isinstance(after, datetime.datetime):
            after = Object(id=time_snowflake(after, high=True))

        self.guild = guild
        self.limit = limit
        self.after = after or OLDEST_OBJECT

        self.state = self.guild._state
        self.get_members = self.state.http.get_members
        self.members = asyncio.Queue()

    async def next(self):
        if self.members.empty():
            await self.fill_members()

        try:
            return self.members.get_nowait()
        except asyncio.QueueEmpty:
            raise NoMoreItems()

    def _get_retrieve(self):
        l = self.limit
        if l is None or l > 1000:
            r = 1000
        else:
            r = l
        self.retrieve = r
        return r > 0

    async def fill_members(self):
        if self._get_retrieve():
            after = self.after.id if self.after else None
            data = await self.get_members(self.guild.id, self.retrieve, after)
            if not data:
                # no data, terminate
                return

            if len(data) < 1000:
                self.limit = 0 # terminate loop

            self.after = Object(id=int(data[-1]['user']['id']))

            for element in reversed(data):
                await self.members.put(self.create_member(element))

    def create_member(self, data):
        from .member import Member
        return Member(data=data, guild=self.guild, state=self.state)


class ThreadMemberIterator(_AsyncIterator):
    def __init__(
            self,
            thread: ThreadChannel,
            limit: int = 100,
            after: Optional[Union[Snowflake, datetime.datetime]] = None,
            with_member: bool = False
    ):
        self.state = state = thread._state
        self.guild = thread.guild
        self.thread = thread
        self.channel_id = thread.id
        self.limit = limit

        if isinstance(after, datetime.datetime):
            after = Object(id=time_snowflake(after, high=True))

        self.after: Optional[Object] = after

        self.with_member = with_member
        self.members = asyncio.Queue()
        self.getter = state.http.list_thread_members

        self._retrieve_members = self._retrieve_members_after_strategy

    async def next(self):
        if self.members.empty():
            await self.fill_members()

        try:
            return self.members.get_nowait()
        except asyncio.QueueEmpty:
            raise NoMoreItems()

    def _get_retrieve(self):
        l = self.limit
        if l is None or l > 100:
            r = 100
        else:
            r = l
        self.retrieve = r
        return r > 0

    async def fill_members(self):
        # this is a hack because >circular imports<
        from .member import Member
        from .channel import ThreadMember

        guild = self.guild
        state = self.state
        thread = self.thread
        with_member = self.with_member
        cache_joined = state.member_cache_flags.joined
        cache_online = state.member_cache_flags.online

        if self._get_retrieve():

            data = await self._retrieve_members(self.retrieve)
            if self.limit is None or len(data) < 100:
                self.limit = 0

            if not with_member or guild is None or isinstance(guild, Object):
                for element in data:
                    thread_member = ThreadMember(state=state, guild=guild, data=element)
                    thread._add_member(thread_member)
                    await self.members.put(thread_member)
                    
            else:
                for element in data:
                    member = Member(data=element.pop('member'), guild=guild, state=state)
                    if cache_joined or (cache_online and 'online' in member.raw_status):
                        guild._add_member(member)
                    thread_member = ThreadMember(state=state, guild=guild, data=element)
                    thread._add_member(thread_member)
                    await self.members.put(thread_member)

    async def _retrieve_members_after_strategy(self, retrieve: int):
        """Retrieve thread members using after parameter."""
        after = self.after.id if self.after else None
        data = await self.getter(self.channel_id, limit=retrieve, after=after, with_member=self.with_member)
        if len(data):
            if self.limit is not None:
                self.limit -= retrieve
            self.after = Object(id=int(data[0]['user_id']))
            data = reversed(data)
        return data


class ArchivedThreadIterator(_AsyncIterator):
    def __init__(
        self,
        channel: Union[TextChannel, ForumChannel],
        limit: int = 100,
        before: Optional[Union[Snowflake, datetime.datetime]] = None,
        private: bool = False,
        joined_private: bool = True
    ) -> None:
        self.state = state = channel._state
        self.guild = channel.guild
        self.channel_id = channel.id
        self.limit = limit
        self._retrieve_type = 0 if channel.__class__.__name__ == 'TextChannel' else 1

        if isinstance(before, datetime.datetime):
            before = Object(id=time_snowflake(before, high=False))

        self.before: Optional[Object] = before

        self.threads = asyncio.Queue()
        self.getter = state.http.list_archived_threads
        self.type: Literal['private', 'public'] = 'private' if private else 'public'
        self.joined_private = joined_private
        self.getter = state.http.list_archived_threads

    async def next(self):
        if self.threads.empty():
            await self.fill_threads()

        try:
            return self.threads.get_nowait()
        except asyncio.QueueEmpty:
            raise NoMoreItems()

    def _get_retrieve(self):
        l = self.limit
        r = 100 if l is None or l > 100 else l
        self.retrieve = r
        return r > 0

    async def fill_threads(self):
        # this is a hack because >circular imports<
        if self._retrieve_type == 0:
            from .channel import ThreadChannel as Factory
        else:
            from .channel import ForumPost as Factory

        if self._get_retrieve():
            guild = self.guild
            data = await self.getter(
                self.channel_id,
                type=self.type,
                joined_private=self.joined_private,
                limit=self.retrieve
            )
            if self.limit is None or len(data) < 100 and not data.get('has_more'):
                self.limit = 0

            members_dict = {int(member['id']): member for member in data['members']}

            for element in data['threads']:
                thread_member = members_dict.get(int(element['id']))
                if thread_member is not None:
                    element['member'] = thread_member
                await self.threads.put(Factory(guild=guild, state=self.state, data=element))


class EventUsersIterator(_AsyncIterator):
    def __init__(self,
                 event: 'GuildScheduledEvent',
                 limit: int = 100,
                 before: Optional[Union['Snowflake', datetime.datetime]] = None,
                 after: Optional[Union['Snowflake', datetime.datetime]] = None,
                 with_member: bool = False):
        self.guild = event.guild
        self.guild_id = event.guild_id
        self.state = event._state
        self.event = event
        self.limit = limit

        if isinstance(before, datetime.datetime):
            before = Object(id=time_snowflake(before, high=True))
        if isinstance(after, datetime.datetime):
            after = Object(id=time_snowflake(after, high=True))

        self.before: Optional[Object] = before
        self.after: Optional[Object] = after

        self.with_member = with_member
        self.users = asyncio.Queue()
        self.getter = event._state.http.get_guild_event_users

        self._filter = None

        if self.before and self.after:
            self._retrieve_users = self._retrieve_users_before_strategy
            self._filter = lambda m: int(m['user']['id']) > self.after.id
        elif self.before:
            self._retrieve_users = self._retrieve_users_before_strategy
        else:
            self._retrieve_users = self._retrieve_users_after_strategy

    async def next(self):
        if self.users.empty():
            await self.fill_users()

        try:
            return self.users.get_nowait()
        except asyncio.QueueEmpty:
            raise NoMoreItems()

    def _get_retrieve(self):
        l = self.limit
        if l is None or l > 100:
            r = 100
        else:
            r = l
        self.retrieve = r
        return r > 0

    async def fill_users(self):
        # this is a hack because >circular imports<
        from .user import User
        from .member import Member

        guild = self.guild
        state = self.state
        cache_joined = state.member_cache_flags.joined
        cache_online = state.member_cache_flags.online

        if self._get_retrieve():

            data = await self._retrieve_users(self.retrieve)
            if self.limit is None or len(data) < 100:
                self.limit = 0

            if self._filter:
                data = filter(self._filter, data)

            if guild is None or isinstance(guild, Object):
                for element in data:
                    await self.users.put(User(state=state, data=element['user']))
            else:
                for element in data:
                    member_id = int(element['user']['id'])
                    member = self.guild.get_member(member_id)
                    if member is not None:
                        await self.users.put(member)
                    else:
                        if self.with_member:
                            element['member']['user'] = element['user']
                            member = Member(data=element['member'], guild=guild, state=state)
                            if cache_joined or (cache_online and 'online' in member.raw_status):
                                self.guild._add_member(member)
                            await self.users.put(member)
                        else:
                            await self.users.put(User(state=self.state, data=element))

    async def _retrieve_users_before_strategy(self, retrieve):
        """Retrieve users using before parameter."""
        before = self.before.id if self.before else None
        data = await self.getter(self.guild_id, self.event.id, limit=retrieve, before=before, with_member=self.with_member)
        if len(data):
            if self.limit is not None:
                self.limit -= retrieve
            self.before = Object(id=int(data[-1]['user']['id']))
        return data

    async def _retrieve_users_after_strategy(self, retrieve):
        """Retrieve users using after parameter."""
        after = self.after.id if self.after else None
        data = await self.getter(self.guild_id, self.event.id, limit=retrieve, after=after, with_member=self.with_member)
        if len(data):
            if self.limit is not None:
                self.limit -= retrieve
            self.after = Object(id=int(data[0]['user']['id']))
            data = reversed(data)
        return data


class BanIterator(_AsyncIterator):
    def __init__(
            self,
            guild: Guild,
            limit: int = 1000,
            before: Optional[Union[Snowflake, datetime.datetime]] = None,
            after: Optional[Union[Snowflake, datetime.datetime]] = None
    ):
        self.guild = guild
        self.guild_id = guild.id
        self.state = guild._state
        self.limit = limit

        if isinstance(before, datetime.datetime):
            before = Object(id=time_snowflake(before, high=True))
        if isinstance(after, datetime.datetime):
            after = Object(id=time_snowflake(after, high=True))

        self.before: Optional[Object] = before
        self.after: Optional[Object] = after
        
        self.ban_entries = asyncio.Queue()
        self.getter = guild._state.http.get_bans

        self._filter = None

        if self.before and self.after:
            self._retrieve_bans = self._retrieve_bans_before_strategy
            self._filter = lambda be: int(be['user']['id']) > self.after.id
        elif self.before:
            self._retrieve_bans = self._retrieve_bans_before_strategy
        else:
            self._retrieve_bans = self._retrieve_bans_after_strategy

    async def next(self):
        if self.ban_entries.empty():
            await self.fill_ban_entries()

        try:
            return self.ban_entries.get_nowait()
        except asyncio.QueueEmpty:
            raise NoMoreItems()

    def _get_retrieve(self):
        l = self.limit
        if l is None or l > 1000:
            r = 1000
        else:
            r = l
        self.retrieve = r
        return r > 0

    async def fill_ban_entries(self):
        # this is a hack because >circular imports<
        from .user import User

        state = self.state

        if self._get_retrieve():

            data = await self._retrieve_bans(self.retrieve)
            if self.limit is None or len(data) < 100:
                self.limit = 0

            if self._filter:
                data = filter(self._filter, data)

            for element in data:
                await self.ban_entries.put(
                    BanEntry(user=User(state=state, data=element['user']), reason=element['reason'])
                )

    async def _retrieve_bans_before_strategy(self, retrieve):
        """Retrieve bans using before parameter."""
        before = self.before.id if self.before else None
        data = await self.getter(self.guild_id, limit=retrieve, before=before)
        if len(data):
            if self.limit is not None:
                self.limit -= retrieve
            self.before = Object(id=int(data[-1]['user']['id']))
        return data

    async def _retrieve_bans_after_strategy(self, retrieve):
        """Retrieve bans using after parameter."""
        after = self.after.id if self.after else None
        data = await self.getter(self.guild_id, limit=retrieve, after=after)
        if len(data):
            if self.limit is not None:
                self.limit -= retrieve
            self.after = Object(id=int(data[0]['user']['id']))
            data = reversed(data)
        return data


class EntitlementIterator(_AsyncIterator):
    def __init__(
            self,
            state: ConnectionState,
            limit: int = 100,
            user_id: int = MISSING,
            guild_id: int = MISSING,
            sku_ids: List[int] = MISSING,
            before: Optional[Union[datetime.datetime, Snowflake]] = None,
            after: Optional[Union[datetime.datetime, Snowflake]] = None,
            exclude_ended: bool = False
    ):
        self.application_id = state.application_id
        self.guild_id = guild_id
        self.user_id = user_id
        self.sku_ids = sku_ids
        self.state: ConnectionState = state
        self.limit: int = limit
        self.exclude_ended: bool = exclude_ended

        if isinstance(before, datetime.datetime):
            before = Object(id=time_snowflake(before, high=True))
        if isinstance(after, datetime.datetime):
            after = Object(id=time_snowflake(after, high=True))

        self.before: Optional[Object] = before
        self.after: Optional[Object] = after

        self.entitlements = asyncio.Queue()
        self.getter = state.http.list_entitlements

        self._filter = None

        if self.before and self.after:
            self._retrieve_entitlements = self._retrieve_entitlements_before_strategy
            self._filter = lambda e: int(e['id']) > self.after.id
        elif self.before:
            self._retrieve_entitlements = self._retrieve_entitlements_before_strategy
        else:
            self._retrieve_entitlements = self._retrieve_entitlements_after_strategy

    async def next(self):
        if self.entitlements.empty():
            await self.fill_entitlements()

        try:
            return self.entitlements.get_nowait()
        except asyncio.QueueEmpty:
            raise NoMoreItems()

    def _get_retrieve(self):
        l = self.limit
        r = 100 if l is None or l > 100 else l
        self.retrieve = r
        return r > 0

    async def fill_entitlements(self):
        # this is a hack because >circular imports<
        from .monetization import Entitlement

        state = self.state

        if self._get_retrieve():

            data = await self._retrieve_entitlements(self.retrieve)
            if self.limit is None or len(data) < 100:
                self.limit = 0

            if self._filter:
                data = filter(self._filter, data)

            for element in data:
                await self.entitlements.put(
                    Entitlement(data=element, state=state)
                )

    async def _retrieve_entitlements_before_strategy(self, retrieve) -> List[monetization.Entitlement]:
        """Retrieve bans using before parameter."""
        before = self.before.id if self.before else MISSING
        data = await self.getter(
            self.application_id,
            limit=retrieve,
            before=before,
            user_id=self.user_id,
            guild_id=self.guild_id,
            sku_ids=self.sku_ids,
            exclude_ended=self.exclude_ended
        )
        if len(data):
            if self.limit is not None:
                self.limit -= retrieve
            self.before = Object(id=int(data[-1]['id']))
        return data

    async def _retrieve_entitlements_after_strategy(self, retrieve) -> List[monetization.Entitlement]:
        """Retrieve bans using after parameter."""
        after = self.after.id if self.after else MISSING
        data = await self.getter(
            self.application_id,
            limit=retrieve,
            after=after,
            user_id=self.user_id,
            guild_id=self.guild_id,
            sku_ids=self.sku_ids,
            exclude_ended=self.exclude_ended,
        )
        if len(data):
            if self.limit is not None:
                self.limit -= retrieve
            self.after = Object(id=int(data[0]['id']))
            data = reversed(data)
        return data
