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

import datetime
from typing import (
    Optional,
    TYPE_CHECKING,
    overload
)
from typing_extensions import Literal

from .asset import Asset
from .utils import _get_as_snowflake, parse_time
from .role import Role
from .user import User
from .errors import InvalidArgument
from .enums import try_enum, ExpireBehaviour

if TYPE_CHECKING:
    from .guild import Guild
    from .state import ConnectionState
    from .types.integration import (
        Integration as IntegrationPayload,
        IntegrationAccount as IntegrationAccountPayload,
        IntegrationApplication as IntegrationApplicationPayload,
        StreamIntegration as StreamIntegrationPayload,
        BotIntegration as BotIntegrationPayload,
        IntegrationType
    )

__all__ = (
    'IntegrationAccount',
    'IntegrationApplication',
    'PartialIntegration',
    'Integration',
    'StreamIntegration',
    'BotIntegration',
    '_integration_factory'
)


class IntegrationAccount:
    """Represents an integration account.
    
    .. versionadded:: 1.4
    
    Attributes
    -----------
    id: :class:`int`
        The account ID.
    name: :class:`str`
        The account name.
    """

    __slots__ = ('id', 'name')

    def __init__(self, data: IntegrationAccountPayload) -> None:
        self.id: Optional[int] = _get_as_snowflake(data, 'id')
        self.name: str = data['name']

    def __repr__(self) -> str:
        return f'<IntegrationAccount id={self.id} name={self.name!r}>'


class PartialIntegration:
    """Represents a partial integration.

    .. versionadded:: 2.0

    Attributes
    -----------
    id: :class:`int`
        The integration ID.
    name: :class:`str`
        The integration name.
    type: :class:`str`
        The integration type (i.e. discord).
    application_id: Optional[:class:`int`]
        The ID of the application for this integration.
    account: :class:`IntegrationAccount`
        The account linked to this integration.
    """

    __slots__ = (
        'id',
        'name',
        'type',
        'application_id',
        'account',
        'guild',
    )

    def __init__(self, *, data: IntegrationPayload, guild: Guild) -> None:
        self.guild: Guild = guild
        self.id: int = int(data['id'])
        self.name: str = data['name']
        self.type: str = data['type']
        self.application_id: Optional[int] = _get_as_snowflake(data, 'application_id')
        self.account: IntegrationAccount = IntegrationAccount(data['account'])

    def __repr__(self) -> str:
        return f'<PartialIntegration id={self.id} name={self.name!r} type={self.type!r}>'


class Integration:
    """Represents a guild integration.
    
    .. versionadded:: 1.4
    
    Attributes
    -----------
    id: :class:`int`
        The integration ID.
    name: :class:`str`
        The integration name.
    guild: :class:`Guild`
        The guild of the integration.
    type: :class:`str`
        The integration type (i.e. Twitch).
    enabled: :class:`bool`
        Whether the integration is currently enabled.
    account: :class:`IntegrationAccount`
        The account linked to this integration.
    user: :class:`User`
        The user that added this integration.
    """

    __slots__ = (
        'guild',
        'id',
        '_state',
        'type',
        'name',
        'account',
        'user',
        'enabled',
    )

    def __init__(self, *, data: IntegrationPayload, guild: Guild) -> None:
        self.guild: Guild = guild
        self._state: ConnectionState = guild._state
        self._from_data(data)

    def __repr__(self):
        return f"<{self.__class__.__name__} id={self.id} name={self.name!r}>"

    def _from_data(self, data) -> None:
        self.id: int = int(data['id'])
        self.type = data['type']
        self.name: str = data['name']
        self.account: IntegrationAccount = IntegrationAccount(data['account'])

        user = data.get('user')
        self.user = User(state=self._state, data=user) if user else None
        self.enabled: bool = data['enabled']

    async def delete(self) -> None:
        """|coro|
        Deletes the integration.
        You must have the :attr:`~Permissions.manage_guild` permission to
        do this.
        
        Raises
        -------
        Forbidden
            You do not have permission to delete the integration.
        HTTPException
            Deleting the integration failed.
        """
        await self._state.http.delete_integration(self.guild.id, self.id)


class StreamIntegration(Integration):
    """Represents a stream integration for Twitch or YouTube.
    
    .. versionadded:: 2.0
    
    Attributes
    ----------
    id: :class:`int`
        The integration ID.
    name: :class:`str`
        The integration name.
    guild: :class:`Guild`
        The guild of the integration.
    type: :class:`str`
        The integration type (i.e. Twitch).
    enabled: :class:`bool`
        Whether the integration is currently enabled.
    syncing: :class:`bool`
        Where the integration is currently syncing.
    role: :class:`Role`
        The role which the integration uses for subscribers.
    enable_emoticons: Optional[:class:`bool`]
        Whether emoticons should be synced for this integration (currently twitch only).
    expire_behaviour: :class:`ExpireBehaviour`
        The behaviour of expiring subscribers. Aliased to ``expire_behavior`` as well.
    expire_grace_period: :class:`int`
        The grace period (in days) for expiring subscribers.
    user: :class:`User`
        The user for the integration.
    account: :class:`IntegrationAccount`
        The integration account information.
    synced_at: :class:`datetime.datetime`
        An aware UTC datetime representing when the integration was last synced.
    """

    __slots__ = Integration.__slots__ + (
        'revoked',
        'expire_behaviour',
        'expire_behavior',
        'expire_grace_period',
        'synced_at',
        '_role_id',
        'role',
        'syncing',
        'enable_emoticons',
        'subscriber_count'
    )

    def _from_data(self, data: StreamIntegrationPayload) -> None:
        super()._from_data(data)
        self.revoked: bool = data['revoked']
        self.expire_behaviour: ExpireBehaviour = try_enum(ExpireBehaviour, data['expire_behavior'])
        self.expire_grace_period: int = data['expire_grace_period']
        self.synced_at: datetime.datetime = parse_time(data['synced_at'])
        self._role_id: int = int(data['role_id'])
        self.role: Role = self.guild.get_role(self._role_id)
        self.syncing: bool = data['syncing']
        self.enable_emoticons: bool = data['enable_emoticons']
        self.subscriber_count: int = data['subscriber_count']

    @overload
    async def edit(
            self,
            *,
            expire_behaviour: Optional[ExpireBehaviour] = ...,
            expire_grace_period: Optional[int] = ...,
            enable_emoticons: Optional[bool] = ...,
    ) -> None:
        ...

    @overload
    async def edit(self, **fields) -> None:
        ...

    async def edit(self, **fields) -> None:
        """|coro|
        Edits the integration.
        You must have the :attr:`~Permissions.manage_guild` permission to
        do this.
        
        Parameters
        -----------
        expire_behaviour: :class:`ExpireBehaviour`
            The behaviour when an integration subscription lapses. Aliased to ``expire_behavior`` as well.
        expire_grace_period: :class:`int`
            The period (in days) where the integration will ignore lapsed subscriptions.
        enable_emoticons: :class:`bool`
            Where emoticons should be synced for this integration (currently twitch only).
        
        Raises
        -------
        Forbidden
            You do not have permission to edit the integration.
        HTTPException
            Editing the guild failed.
        InvalidArgument
            ``expire_behaviour`` did not receive a :class:`ExpireBehaviour`.
        """
        try:
            expire_behaviour = fields['expire_behaviour']
        except KeyError:
            expire_behaviour = fields.get('expire_behavior', self.expire_behaviour)

        if not isinstance(expire_behaviour, ExpireBehaviour):
            raise InvalidArgument('expire_behaviour field must be of type ExpireBehaviour')

        expire_grace_period = fields.get('expire_grace_period', self.expire_grace_period)

        payload = {
            'expire_behavior': expire_behaviour.value,
            'expire_grace_period': expire_grace_period,
        }

        enable_emoticons = fields.get('enable_emoticons')

        if enable_emoticons is not None:
            payload['enable_emoticons'] = enable_emoticons

        await self._state.http.edit_integration(self.guild.id, self.id, **payload)

        self.expire_behaviour = expire_behaviour
        self.expire_behavior = self.expire_behaviour
        self.expire_grace_period = expire_grace_period
        self.enable_emoticons = enable_emoticons

    async def sync(self) -> None:
        """|coro|
        Syncs the integration.
        You must have the :attr:`~Permissions.manage_guild` permission to
        do this.
        
        Raises
        -------
        Forbidden
            You do not have permission to sync the integration.
        HTTPException
            Syncing the integration failed.
        """
        await self._state.http.sync_integration(self.guild.id, self.id)
        self.synced_at = datetime.datetime.now(datetime.timezone.utc)


class IntegrationApplication:
    """Represents an application for a bot integration.
    
    .. versionadded:: 2.0
    
    Attributes
    ----------
    id: :class:`int`
        The ID for this application.
    name: :class:`str`
        The application's name.
    icon: Optional[:class:`str`]
        The application's icon hash.
    description: :class:`str`
        The application's description. Can be an empty string.
    user: Optional[:class:`User`]
        The bot user on this application.
    """

    __slots__ = (
        'id',
        'name',
        'icon',
        'description',
        'user',
        '_state',
    )

    def __init__(self, *, data: IntegrationApplicationPayload, state: ConnectionState):
        self._state: ConnectionState = state
        self.id: int = int(data['id'])
        self.name: str = data['name']
        self.icon: Optional[str] = data['icon']
        self.description: str = data['description']
        user = data.get('bot')
        self.user: Optional[User] = User(state=state, data=user) if user else None
    
    def icon_url(self) -> Asset:
        """Returns an :class:`Asset` for the application's icon."""
        return self.icon_url_as()
    
    def icon_url_as(
            self,
            *,
            format: Literal['png', 'jpg', 'jpeg', 'webp'] = 'webp',
            size: int = 1024
    ) -> Asset:
        """
        Returns an :class:`Asset` for the application's icon.
        
        Parameters
        -----------
        format: Optional[:class:`str`]
            The format to attempt to convert the image to. Defaults to ``webp``.
        size: :class:`int`
            The size of the image to return. Defaults to 1024.
        
        Returns
        -------
        :class:`Asset`
            The resulting CDN asset.
        """
        return Asset._from_icon(self._state, self, 'app', format=format, size=size)


class BotIntegration(Integration):
    """Represents a bot integration on discord.

    .. versionadded:: 2.0
    
    Attributes
    ----------
    id: :class:`int`
        The integration ID.
    name: :class:`str`
        The integration name.
    guild: :class:`Guild`
        The guild of the integration.
    type: :class:`str`
        The integration type (i.e. Twitch).
    enabled: :class:`bool`
        Whether the integration is currently enabled.
    user: :class:`User`
        The user that added this integration.
    account: :class:`IntegrationAccount`
        The integration account information.
    application: :class:`IntegrationApplication`
        The application tied to this integration.
    """

    __slots__ = Integration.__slots__ + ('application',)

    def _from_data(self, data: BotIntegrationPayload) -> None:
        super()._from_data(data)
        self.application = IntegrationApplication(data=data['application'], state=self._state)


def _integration_factory(value: IntegrationType):
    if value == 'discord':
        return BotIntegration, value
    elif value in ('twitch', 'youtube'):
        return StreamIntegration, value
    else:
        return Integration, value
    # TODO: Add guild_integration type
