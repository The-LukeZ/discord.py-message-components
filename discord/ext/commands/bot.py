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

import asyncio
import collections.abc
import copy
import inspect
import importlib.util
import re
import sys
import traceback
import types
from typing import (
    Callable,
    Optional,
    Union,
    Dict,
    List,
    Tuple
)

import discord

from .core import GroupMixin
from .view import StringView
from .context import Context
from . import errors
from .help import HelpCommand, DefaultHelpCommand
from .cog import Cog


def when_mentioned(bot, msg):
    """A callable that implements a command prefix equivalent to being mentioned.

    These are meant to be passed into the :attr:`.Bot.command_prefix` attribute.
    """
    return [bot.user.mention + ' ', '<@!%s> ' % bot.user.id]


def when_mentioned_or(*prefixes):
    """A callable that implements when mentioned or other prefixes provided.

    These are meant to be passed into the :attr:`.Bot.command_prefix` attribute.

    Example
    --------

    .. code-block:: python3

        bot = commands.Bot(command_prefix=commands.when_mentioned_or('!'))


    .. note::

        This callable returns another callable, so if this is done inside a custom
        callable, you must call the returned callable, for example:

        .. code-block:: python3

            async def get_prefix(bot, message):
                extras = await prefixes_for(message.guild) # returns a list
                return commands.when_mentioned_or(*extras)(bot, message)


    See Also
    ----------
    :func:`.when_mentioned`
    """

    def inner(bot, msg):
        r = list(prefixes)
        r = when_mentioned(bot, msg) + r
        return r

    return inner


def _is_submodule(parent, child):
    return parent == child or child.startswith(parent + ".")


class _DefaultRepr:
    def __repr__(self):
        return '<default-help-command>'


_default = _DefaultRepr()


class BotBase(GroupMixin):
    def __init__(self, command_prefix, help_command=_default, description=None, **options):
        super().__init__(**options)
        self.command_prefix = command_prefix
        self.extra_events: Dict[str, List[Callable[..., ...]]] = {}
        self.extra_interaction_events: Dict[str, List[Tuple[Callable[..., ...], Callable[..., ...]]]] = {}
        self.__cogs = {}
        self.__extensions = {}
        self._checks = []
        self._check_once = []
        self._before_invoke = None
        self._after_invoke = None
        self._help_command = None
        self.description = inspect.cleandoc(description) if description else ''
        self.owner_id = options.get('owner_id')
        self.owner_ids = options.get('owner_ids', set())
        self.strip_after_prefix = options.get('strip_after_prefix', False)
        self.sync_commands: bool = options.get('sync_commands', False)
        self.delete_not_existing_commands: bool = options.get('delete_not_existing_commands', True)
        self.sync_commands_on_cog_reload: bool = options.get('sync_commands_on_cog_reload', False)
        if self.owner_id and self.owner_ids:
            raise TypeError('Both owner_id and owner_ids are set.')

        if self.owner_ids and not isinstance(self.owner_ids, collections.abc.Collection):
            raise TypeError('owner_ids must be a collection not {0.__class__!r}'.format(self.owner_ids))

        if options.pop('self_bot', False):
            self._skip_check = lambda x, y: x != y
        else:
            self._skip_check = lambda x, y: x == y

        if help_command is _default:
            self.help_command = DefaultHelpCommand()
        else:
            self.help_command = help_command

    # internal helpers

    def dispatch(self, event_name, *args, **kwargs):
        super().dispatch(event_name, *args, **kwargs)
        ev = 'on_' + event_name
        for event in self.extra_events.get(ev, []):
            self._schedule_event(event, ev, *args, **kwargs)
        for (func, check) in self.extra_interaction_events.get(event_name, []):
            if check(*args, **kwargs):
                self._schedule_event(func, ev, *args, **kwargs)

    async def close(self):
        """|coro|

        This has the same behaviour as :meth:`discord.Client.close` except that it unload all extensions and cogs first.
        """
        for extension in tuple(self.__extensions):
            try:
                self.unload_extension(extension)
            except Exception:
                pass

        for cog in tuple(self.__cogs):
            try:
                self.remove_cog(cog)
            except Exception:
                pass

        await super().close()

    async def on_command_error(self, context, exception):
        """|coro|

        The default command error handler provided by the bot.

        By default this prints to :data:`sys.stderr` however it could be
        overridden to have a different implementation.

        This only fires if you do not specify any listeners for command error.
        """
        if self.extra_events.get('on_command_error', None):
            return

        if hasattr(context.command, 'on_error'):
            return

        cog = context.cog
        if cog and Cog._get_overridden_method(cog.cog_command_error) is not None:
            return

        print('Ignoring exception in command {}:'.format(context.command), file=sys.stderr)
        traceback.print_exception(type(exception), exception, exception.__traceback__, file=sys.stderr)

    async def on_application_command_error(self, cmd, interaction, exception):
        """|coro|

        The default error handler when an Exception was raised when invoking an application-command.

        By default this prints to :data:`sys.stderr` however it could be
        overridden to have a different implementation.
        Check :func:`~discord.on_application_command_error` for more details.
        """
        if self.extra_events.get('on_application_command_error', None):
            return

        if hasattr(cmd, 'on_error'):
            return

        cog: Cog = cmd.cog
        if cog and Cog._get_overridden_method(cog.cog_application_command_error) is not None:
            return
        await super().on_application_command_error(cmd, interaction, exception)

    # global check registration

    def check(self, func):
        r"""A decorator that adds a global check to the bot.

        A global check is similar to a :func:`.check` that is applied
        on a per command basis except it is run before any command checks
        have been verified and applies to every command the bot has.

        .. note::

            This function can either be a regular function or a coroutine.

        Similar to a command :func:`.check`\, this takes a single parameter
        of type :class:`.Context` and can only raise exceptions inherited from
        :exc:`.CommandError`.

        Example
        ---------

        .. code-block:: python3

            @bot.check
            def check_commands(ctx):
                return ctx.command.qualified_name in allowed_commands

        """
        self.add_check(func)
        return func

    def add_check(self, func, *, call_once=False):
        """Adds a global check to the bot.

        This is the non-decorator interface to :meth:`.check`
        and :meth:`.check_once`.

        Parameters
        -----------
        func
            The function that was used as a global check.
        call_once: :class:`bool`
            If the function should only be called once per
            :meth:`.Command.invoke` call.
        """

        if call_once:
            self._check_once.append(func)
        else:
            self._checks.append(func)

    def remove_check(self, func, *, call_once=False):
        """Removes a global check from the bot.

        This function is idempotent and will not raise an exception
        if the function is not in the global checks.

        Parameters
        -----------
        func
            The function to remove from the global checks.
        call_once: :class:`bool`
            If the function was added with ``call_once=True`` in
            the :meth:`.Bot.add_check` call or using :meth:`.check_once`.
        """
        l = self._check_once if call_once else self._checks

        try:
            l.remove(func)
        except ValueError:
            pass

    def check_once(self, func):
        r"""A decorator that adds a "call once" global check to the bot.

        Unlike regular global checks, this one is called only once
        per :meth:`.Command.invoke` call.

        Regular global checks are called whenever a command is called
        or :meth:`.Command.can_run` is called. This type of check
        bypasses that and ensures that it's called only once, even inside
        the default help command.

        .. note::

            When using this function the :class:`.Context` sent to a group subcommand
            may only parse the parent command and not the subcommands due to it
            being invoked once per :meth:`.Bot.invoke` call.

        .. note::

            This function can either be a regular function or a coroutine.

        Similar to a command :func:`.check`\, this takes a single parameter
        of type :class:`.Context` and can only raise exceptions inherited from
        :exc:`.CommandError`.

        Example
        ---------

        .. code-block:: python3

            @bot.check_once
            def whitelist(ctx):
                return ctx.message.author.id in my_whitelist

        """
        self.add_check(func, call_once=True)
        return func

    async def can_run(self, ctx, *, call_once=False):
        data = self._check_once if call_once else self._checks

        if len(data) == 0:
            return True

        return await discord.utils.async_all(f(ctx) for f in data)

    async def is_owner(self, user):
        """|coro|

        Checks if a :class:`~discord.User` or :class:`~discord.Member` is the owner of
        this bot.

        If an :attr:`owner_id` is not set, it is fetched automatically
        through the use of :meth:`~.Bot.application_info`.

        .. versionchanged:: 1.3
            The function also checks if the application is team-owned if
            :attr:`owner_ids` is not set.

        Parameters
        -----------
        user: :class:`.abc.User`
            The user to check for.

        Returns
        --------
        :class:`bool`
            Whether the user is the owner.
        """

        if self.owner_id:
            return user.id == self.owner_id
        elif self.owner_ids:
            return user.id in self.owner_ids
        else:
            app = await self.application_info()
            if app.team:
                self.owner_ids = ids = {m.id for m in app.team.members}
                return user.id in ids
            else:
                self.owner_id = owner_id = app.owner.id
                return user.id == owner_id

    def before_invoke(self, coro):
        """A decorator that registers a coroutine as a pre-invoke hook.

        A pre-invoke hook is called directly before the command is
        called. This makes it a useful function to set up database
        connections or any type of set up required.

        This pre-invoke hook takes a sole parameter, a :class:`.Context`.

        .. note::

            The :meth:`~.Bot.before_invoke` and :meth:`~.Bot.after_invoke` hooks are
            only called if all checks and argument parsing procedures pass
            without error. If any check or argument parsing procedures fail
            then the hooks are not called.

        Parameters
        -----------
        coro: :ref:`coroutine <coroutine>`
            The coroutine to register as the pre-invoke hook.

        Raises
        -------
        TypeError
            The coroutine passed is not actually a coroutine.
        """
        if not asyncio.iscoroutinefunction(coro):
            raise TypeError('The pre-invoke hook must be a coroutine.')

        self._before_invoke = coro
        return coro

    def after_invoke(self, coro):
        r"""A decorator that registers a coroutine as a post-invoke hook.

        A post-invoke hook is called directly after the command is
        called. This makes it a useful function to clean-up database
        connections or any type of clean up required.

        This post-invoke hook takes a sole parameter, a :class:`.Context`.

        .. note::

            Similar to :meth:`~.Bot.before_invoke`\, this is not called unless
            checks and argument parsing procedures succeed. This hook is,
            however, **always** called regardless of the internal command
            callback raising an error (i.e. :exc:`.CommandInvokeError`\).
            This makes it ideal for clean-up scenarios.

        Parameters
        -----------
        coro: :ref:`coroutine <coroutine>`
            The coroutine to register as the post-invoke hook.

        Raises
        -------
        TypeError
            The coroutine passed is not actually a coroutine.
        """
        if not asyncio.iscoroutinefunction(coro):
            raise TypeError('The post-invoke hook must be a coroutine.')

        self._after_invoke = coro
        return coro

    # listener registration
    def add_interaction_listener(self, _type, func, custom_id: re.Pattern):
        """
        This adds an interaction(decorator) like :meth:`on_click` or :meth:`on_select` to the client listeners.

        .. note::
            This should not be used directly; it's used internal when a Cog is loaded.

        """
        try:
            listeners = self.extra_interaction_events[_type]
        except KeyError:
            listeners = []
            self.extra_interaction_events[_type] = listeners
        if _type == 'modal_submit':
            def _check(i):
                match = custom_id.match(str(i.custom_id))
                if match:
                    i.match = match
                    return True
                return False
        else:
            def _check(i, b):
                match = custom_id.match(str(b.custom_id))
                if match:
                    i.match = match
                    return True
                return False

        # We store this in the function here, so we can remove it later easily
        listener = (func, _check)
        setattr(func.__func__, '__listener__', listener)
        listeners.append(listener)

    def remove_interaction_listener(self, _type, func):
        """
        This removes an interaction(decorator) like :meth:`on_click` or :meth:`on_select` from the client listeners.

        .. note::
            This should not be used directly; it's used internal when a Cog is un-loaded.
        """
        try:
            if _type in self.extra_interaction_events:
                self.extra_interaction_events[_type].remove(func.__listener__)
        except ValueError:
            pass

    def add_listener(self, func, name=None):
        """The non decorator alternative to :meth:`.listen`.

        Parameters
        -----------
        func: :ref:`coroutine <coroutine>`
            The function to call.
        name: Optional[:class:`str`]
            The name of the event to listen for. Defaults to ``func.__name__``.

        Example
        --------

        .. code-block:: python3

            async def on_ready(): pass
            async def my_message(message): pass

            bot.add_listener(on_ready)
            bot.add_listener(my_message, 'on_message')

        """
        name = func.__name__ if name is None else name

        if not asyncio.iscoroutinefunction(func):
            raise TypeError('Listeners must be coroutines')

        if name in self.extra_events:
            self.extra_events[name].append(func)
        else:
            self.extra_events[name] = [func]

    def remove_listener(self, func, name=None):
        """Removes a listener from the pool of listeners.

        Parameters
        -----------
        func
            The function that was used as a listener to remove.
        name: :class:`str`
            The name of the event we want to remove. Defaults to
            ``func.__name__``.
        """

        name = func.__name__ if name is None else name

        if name in self.extra_events:
            try:
                self.extra_events[name].remove(func)
            except ValueError:
                pass

    def listen(self, name=None):
        """A decorator that registers another function as an external
        event listener. Basically this allows you to listen to multiple
        events from different places e.g. such as :func:`.on_ready`

        The functions being listened to must be a :ref:`coroutine <coroutine>`.

        Example
        --------

        .. code-block:: python3

            @bot.listen()
            async def on_message(message):
                print('one')

            # in some other file...

            @bot.listen('on_message')
            async def my_message(message):
                print('two')

        Would print one and two in an unspecified order.

        Raises
        -------
        TypeError
            The function being listened to is not a coroutine.
        """

        def decorator(func):
            self.add_listener(func, name)
            return func

        return decorator

    # cogs

    def add_cog(self, cog):
        """Adds a "cog" to the bot.

        A cog is a class that has its own event listeners and commands.

        Parameters
        -----------
        cog: :class:`.Cog`
            The cog to register to the bot.

        Raises
        -------
        TypeError
            The cog does not inherit from :class:`.Cog`.
        CommandError
            An error happened during loading.
        """

        if not isinstance(cog, Cog):
            raise TypeError('cogs must derive from Cog')

        cog = cog._inject(self)
        self.__cogs[cog.__cog_name__] = cog

    def get_cog(self, name):
        """Gets the cog instance requested.

        If the cog is not found, ``None`` is returned instead.

        Parameters
        -----------
        name: :class:`str`
            The name of the cog you are requesting.
            This is equivalent to the name passed via keyword
            argument in class creation or the class name if unspecified.

        Returns
        --------
        Optional[:class:`Cog`]
            The cog that was requested. If not found, returns ``None``.
        """
        return self.__cogs.get(name)

    def remove_cog(self, name):
        """Removes a cog from the bot.

        All registered commands and event listeners that the
        cog has registered will be removed as well.

        If no cog is found then this method has no effect.

        Parameters
        -----------
        name: :class:`str`
            The name of the cog to remove.
        """

        cog = self.__cogs.pop(name, None)
        if cog is None:
            return

        help_command = self._help_command
        if help_command and help_command.cog is cog:
            help_command.cog = None
        cog._eject(self)

    @property
    def cogs(self) -> Dict[str, Cog]:
        """Mapping[:class:`str`, :class:`Cog`]: A read-only mapping of cog name to cog."""
        return types.MappingProxyType(self.__cogs)

    # extensions

    def _remove_module_references(self, name):
        # find all references to the module
        # remove the cogs registered from the module
        for cogname, cog in self.__cogs.copy().items():
            if _is_submodule(name, cog.__module__):
                self.remove_cog(cogname)

        # remove all the commands from the module
        for cmd in self.all_commands.copy().values():
            if cmd.module is not None and _is_submodule(name, cmd.module):
                if isinstance(cmd, GroupMixin):
                    cmd.recursively_remove_all_commands()
                self.remove_command(cmd.name)

        # remove all the listeners from the module
        for event_list in self.extra_events.copy().values():
            remove = []
            for index, event in enumerate(event_list):
                if event.__module__ is not None and _is_submodule(name, event.__module__):
                    remove.append(index)

            for index in reversed(remove):
                del event_list[index]

        for event_list in self.extra_interaction_events.copy().values():
            remove = []
            for index, event in enumerate(event_list):
                if event[0].__module__ is not None and _is_submodule(name, event[0].__module__):
                    remove.append(index)

            for index in reversed(remove):
                del event_list[index]

    def _call_module_finalizers(self, lib, key):
        try:
            func = getattr(lib, 'teardown')
        except AttributeError:
            pass
        else:
            try:
                func(self)
            except Exception:
                pass
        finally:
            self.__extensions.pop(key, None)
            sys.modules.pop(key, None)
            name = lib.__name__
            for module in list(sys.modules.keys()):
                if _is_submodule(name, module):
                    del sys.modules[module]

    def _load_from_module_spec(self, spec, key):
        # precondition: key not in self.__extensions
        lib = importlib.util.module_from_spec(spec)
        sys.modules[key] = lib
        try:
            spec.loader.exec_module(lib)
        except Exception as e:
            del sys.modules[key]
            raise errors.ExtensionFailed(key, e) from e

        try:
            setup = getattr(lib, 'setup')
        except AttributeError:
            del sys.modules[key]
            raise errors.NoEntryPointError(key)

        try:
            setup(self)
        except Exception as e:
            del sys.modules[key]
            self._remove_module_references(lib.__name__)
            self._call_module_finalizers(lib, key)
            raise errors.ExtensionFailed(key, e) from e
        else:
            self.__extensions[key] = lib

    def _resolve_name(self, name, package):
        try:
            return importlib.util.resolve_name(name, package)
        except ImportError:
            raise errors.ExtensionNotFound(name)

    def load_extension(self, name, *, package: Optional[str] = None):
        """Loads an extension.

        An extension is a python module that contains commands, cogs, or
        listeners.

        An extension must have a global function, ``setup`` defined as
        the entry point on what to do when the extension is loaded. This entry
        point must have a single argument, the ``bot``.

        Parameters
        ------------
        name: :class:`str`
            The extension name to load. It must be dot separated like
            regular Python imports if accessing a sub-module. e.g.
            ``foo.test`` if you want to import ``foo/test.py``.
        package: Optional[:class:`str`]
            The package name to resolve relative imports with.
            This is required when loading an extension using a relative path, e.g ``.foo.test``.
            Defaults to ``None``.

            .. versionadded:: 1.7

        Raises
        --------
        ExtensionNotFound
            The extension could not be imported.
            This is also raised if the name of the extension could not
            be resolved using the provided ``package`` parameter.
        ExtensionAlreadyLoaded
            The extension is already loaded.
        NoEntryPointError
            The extension does not have a setup function.
        ExtensionFailed
            The extension or its setup function had an execution error.
        """

        name = self._resolve_name(name, package)
        if name in self.__extensions:
            raise errors.ExtensionAlreadyLoaded(name)

        spec = importlib.util.find_spec(name)
        if spec is None:
            raise errors.ExtensionNotFound(name)

        self._load_from_module_spec(spec, name)

    def unload_extension(self, name, *, package: Optional[str] = None):
        """Unloads an extension.

        When the extension is unloaded, all commands, listeners, and cogs are
        removed from the bot and the module is un-imported.

        The extension can provide an optional global function, ``teardown``,
        to do miscellaneous clean-up if necessary. This function takes a single
        parameter, the ``bot``, similar to ``setup`` from
        :meth:`~.Bot.load_extension`.

        Parameters
        ------------
        name: :class:`str`
            The extension name to unload. It must be dot separated like
            regular Python imports if accessing a sub-module. e.g.
            ``foo.test`` if you want to import ``foo/test.py``.
        package: Optional[:class:`str`]
            The package name to resolve relative imports with.
            This is required when unloading an extension using a relative path, e.g ``.foo.test``.
            Defaults to ``None``.

            .. versionadded:: 1.7

        Raises
        -------
        ExtensionNotFound
            The name of the extension could not
            be resolved using the provided ``package`` parameter.
        ExtensionNotLoaded
            The extension was not loaded.
        """

        name = self._resolve_name(name, package)
        lib = self.__extensions.get(name)
        if lib is None:
            raise errors.ExtensionNotLoaded(name)

        self._remove_module_references(lib.__name__)
        self._call_module_finalizers(lib, name)

    def reload_extension(self, name, *, package: Optional[str] = None):
        """Atomically reloads an extension.

        This replaces the extension with the same extension, only refreshed. This is
        equivalent to a :meth:`unload_extension` followed by a :meth:`load_extension`
        except done in an atomic way. That is, if an operation fails mid-reload then
        the bot will roll-back to the prior working state.

        Parameters
        ------------
        name: :class:`str`
            The extension name to reload. It must be dot separated like
            regular Python imports if accessing a sub-module. e.g.
            ``foo.test`` if you want to import ``foo/test.py``.
        package: Optional[:class:`str`]
            The package name to resolve relative imports with.
            This is required when reloading an extension using a relative path, e.g ``.foo.test``.
            Defaults to ``None``.

            .. versionadded:: 1.7

        Raises
        -------
        ExtensionNotLoaded
            The extension was not loaded.
        ExtensionNotFound
            The extension could not be imported.
            This is also raised if the name of the extension could not
            be resolved using the provided ``package`` parameter.
        NoEntryPointError
            The extension does not have a setup function.
        ExtensionFailed
            The extension setup function had an execution error.
        """
        name = self._resolve_name(name, package)
        lib = self.__extensions.get(name)
        if lib is None:
            raise errors.ExtensionNotLoaded(name)

        # get the previous module states from sys modules
        modules = {
            name: module
            for name, module in sys.modules.items()
            if _is_submodule(lib.__name__, name)
        }

        try:
            # Unload and then load the module...
            self._remove_module_references(lib.__name__)
            self._call_module_finalizers(lib, name)
            self.load_extension(name)
        except Exception:
            # if the load failed, the remnants should have been
            # cleaned from the load_extension function call
            # so let's load it from our old compiled library.
            lib.setup(self)
            self.__extensions[name] = lib

            # revert sys.modules back to normal and raise back to caller
            sys.modules.update(modules)

            self.loop.create_task(
                self._request_sync_commands(
                    is_cog_reload=True,
                    reload_failed=True
                )
            )
            raise
        else:
            self.loop.create_task(self._request_sync_commands(is_cog_reload=True))

    def reload_extensions(self, *names: Tuple[str], package: Optional[str] = None) -> None:
        """
        Same behaviour as :meth:`.reload_extension` excepts that it reloads multiple extensions
        and triggers application commands syncing after all has been reloaded
        """
        before_sync = copy.copy(self.sync_commands_on_cog_reload)
        self.sync_commands_on_cog_reload = False
        try:
            for name in names:
                self.reload_extension(name, package=package)
        finally:
            self.sync_commands_on_cog_reload = before_sync
            self.loop.create_task(self._request_sync_commands(is_cog_reload=True))

    @property
    def extensions(self):
        """Mapping[:class:`str`, :class:`py:types.ModuleType`]: A read-only mapping of extension name to extension."""
        return types.MappingProxyType(self.__extensions)

    def add_application_cmds_from_cog(self, cog: Cog):
        """
        Add all application-commands in the given cog to the internal list of application-commands.

        Parameters
        ----------
        cog: :class:`.Cog`
            The cog wich application-commands should be added to the internal list of application-commands.
        """

        self.remove_application_cmds_from_cog(cog)  # to ensure that commands that aren't in the cog anymore get removed

        for cmd_type, commands in cog.__application_commands_by_type__.items():

            for command in commands.values():
                # check if there is already a command with the same name
                command._set_cog(cog, recursive=True)
                if command.name in self._application_commands_by_type[cmd_type]:
                    existing_command = self._application_commands_by_type[cmd_type][command.name]
                    existing_command.disabled = False
                    if cmd_type == 'chat_input':
                        if command.has_subcommands:
                            # if the command has subcommands add them to the existing one.
                            for sub_command in command.sub_commands:
                                sub_command.disabled = False
                                if sub_command.type.sub_command_group:
                                    # if the subcommand is a group that already exists, add the subcommands of it
                                    # to the existing group
                                    if sub_command.name in existing_command.sub_commands \
                                            and existing_command._sub_commands[sub_command.name].type.sub_command_group:
                                        existing_group = existing_command._sub_commands[sub_command.name]
                                        for sub_cmd in sub_command.sub_commands:
                                            # set the parent of the subcommand to the existing group
                                            sub_cmd.parent = existing_group
                                            sub_cmd.disabled = False
                                            existing_group._sub_commands[sub_cmd.name] = sub_cmd
                                        if command.description != 'No Description':
                                            existing_command.description = command.description
                                        existing_group.name_localizations.update(command.name_localizations)
                                        existing_group.description_localizations.update(
                                            command.description_localizations
                                        )
                                        # maybe remove the if-statement in the future
                                        if command.default_required_permissions:
                                            existing_group.default_required_permissions = command.default_required_permissions
                                        continue
                                    else:
                                        for sub_cmd in sub_command.sub_commands:
                                            sub_cmd.disabled = False
                                        existing_command._sub_commands[sub_command.name] = sub_command

                                # set the parent of the subcommand to the existing command
                                sub_command.parent = existing_command
                                existing_command._sub_commands[sub_command.name] = sub_command
                        else:
                            # Just overwrite the existing one
                            self._application_commands_by_type[cmd_type][command.name] = command
                            continue

                    else:
                        # if it's not a slash-command overwrite the existing one
                        self._application_commands_by_type[cmd_type][command.name] = command
                        continue

                    if command.description != 'No Description':
                        existing_command.description = command.description
                    existing_command.name_localizations.update(command.name_localizations)
                    existing_command.description_localizations.update(command.description_localizations)
                    # maybe remove the if-statement in the future
                    if command.default_member_permissions:
                        existing_command.member_required_permissions = command.default_member_permissions

                else:
                    self._application_commands_by_type[cmd_type][command.name] = command

        for guild_id, commands_by_type in cog.__guild_specific_application_commands__.items():
            # Set the cog og the commands to the Cog isinstance
            for cmd_type, commands in commands_by_type.items():
                for command in commands.values():
                    command._set_cog(cog, recursive=True)

            if guild_id not in self._guild_specific_application_commands:
                # There are no commands only for this guild yet. So skip the checks and just add them.
                self._guild_specific_application_commands[guild_id] = commands_by_type
                continue

            for cmd_type, commands in commands_by_type.items():
                for command in commands.values():
                    if command.name in self._guild_specific_application_commands[guild_id][cmd_type]:
                        existing_command = self._guild_specific_application_commands[guild_id][cmd_type][command.name]
                        existing_command.disabled = False
                        if cmd_type == 'chat_input':
                            if command.has_subcommands:

                                # if the command has subcommands add them to the existing one.
                                for sub_command in command.sub_commands:
                                    sub_command.disabled = False
                                    if sub_command.type.sub_command_group:
                                        # if the subcommand is a group that already exists, add the subcommands of it
                                        # to the existing group
                                        if sub_command.name in existing_command.sub_commands \
                                                and existing_command._sub_commands[
                                            sub_command.name].type.sub_command_group:
                                            existing_group = existing_command._sub_commands[sub_command.name]
                                            for sub_cmd in sub_command.sub_commands:
                                                # set the parent of the subcommand to the existing group
                                                sub_cmd.parent = existing_group
                                                sub_cmd.disabled = False
                                                existing_group._sub_commands[sub_cmd.name] = sub_cmd
                                            existing_group.name_localizations.update(sub_command.name_localizations)
                                            existing_group.description_localizations.update(
                                                sub_command.description_localizations
                                                )
                                            continue
                                        else:
                                            for sub_cmd in sub_command.sub_commands:
                                                sub_cmd.disabled = False
                                            existing_command._sub_commands[sub_command.name] = sub_command

                                    # set the parent of the subcommand to the existing command
                                    sub_command.parent = existing_command
                                    existing_command._sub_commands[sub_command.name] = sub_command
                            else:
                                # Just overwrite the existing one
                                self._guild_specific_application_commands[guild_id][cmd_type][command.name] = command
                        else:
                            # If it's not a slash-command overwrite the existing one
                            self._guild_specific_application_commands[guild_id][cmd_type][command.name] = command

                            continue

                        if command.description != 'No Description':
                            existing_command.description = command.description
                        existing_command.name_localizations.update(command.name_localizations)
                        existing_command.description_localizations.update(command.description_localizations)
                        # maybe remove the if-statement in the future
                        if command.default_member_permissions:
                            existing_command.default_member_permissions = command.default_member_permissions

                    else:
                        self._guild_specific_application_commands[guild_id][cmd_type][command.name] = command

    def remove_application_cmds_from_cog(self, cog: Cog):
        """
        Removes all application-commands in the given cog from the internal list of application-commands.

        Parameters
        ----------
        cog: :class:`.Cog`
            The cog wich application-commands should be removed from the internal list of application-commands.
        """
        to_remove = []
        for t in self._application_commands_by_type.values():
            for cmd in t.values():
                if cmd.cog and cmd.cog == cog:
                    to_remove.append(cmd)
                    continue
                # Remove all subcommands from this command if they are in the cog.
                if cmd.type.chat_input and cmd.has_subcommands:
                    for sub_command in cmd.sub_commands:
                        if sub_command.type.sub_command_group:
                            for sub_cmd in sub_command.sub_commands:
                                if sub_cmd.cog and sub_cmd.cog == cog:
                                    del sub_command._sub_commands[sub_cmd.name]
                        if sub_command.cog and sub_command.cog == cog:
                            del cmd._sub_commands[sub_command.name]

        for guild_id, t in self._guild_specific_application_commands.items():
            for commands in t.values():
                for cmd in commands.values():
                    if cmd.cog and cmd.cog == cog:
                        to_remove.append(cmd)
                        continue
                    # Remove all subcommands from this command if they are in the cog.
                    if cmd.type == 'chat_input' and cmd.has_subcommands:
                        for sub_command in cmd.sub_commands:
                            if sub_command.type.sub_command_group:
                                for sub_cmd in sub_command.sub_commands:
                                    if sub_cmd.cog and sub_cmd.cog == cog:
                                        del sub_command._sub_commands[sub_cmd.name]
                            if sub_command.cog and sub_command.cog == cog:
                                del cmd._sub_commands[sub_command.name]
        for cmd in to_remove:
            self._remove_application_command(cmd, from_cache=False)

    # help command stuff

    @property
    def help_command(self):
        return self._help_command

    @help_command.setter
    def help_command(self, value):
        if value is not None:
            if not isinstance(value, HelpCommand):
                raise TypeError('help_command must be a subclass of HelpCommand')
            if self._help_command is not None:
                self._help_command._remove_from_bot(self)
            self._help_command = value
            value._add_to_bot(self)
        elif self._help_command is not None:
            self._help_command._remove_from_bot(self)
            self._help_command = None
        else:
            self._help_command = None

    # command processing

    async def get_prefix(self, message):
        """|coro|

        Retrieves the prefix the bot is listening to
        with the message as a context.

        Parameters
        -----------
        message: :class:`discord.Message`
            The message context to get the prefix of.

        Returns
        --------
        Union[List[:class:`str`], :class:`str`]
            A list of prefixes or a single prefix that the bot is
            listening for.
        """
        prefix = ret = self.command_prefix
        if callable(prefix):
            ret = await discord.utils.maybe_coroutine(prefix, self, message)

        if not isinstance(ret, str):
            try:
                ret = list(ret)
            except TypeError:
                # It's possible that a generator raised this exception.  Don't
                # replace it with our own error if that's the case.
                if isinstance(ret, collections.abc.Iterable):
                    raise

                raise TypeError(
                    "command_prefix must be plain string, iterable of strings, or callable "
                    "returning either of these, not {}".format(ret.__class__.__name__)
                )

            if not ret:
                raise ValueError("Iterable command_prefix must contain at least one prefix")

        return ret

    async def get_context(self, message, *, cls=Context):
        r"""|coro|

        Returns the invocation context from the message.

        This is a more low-level counter-part for :meth:`.process_commands`
        to allow users more fine grained control over the processing.

        The returned context is not guaranteed to be a valid invocation
        context, :attr:`.Context.valid` must be checked to make sure it is.
        If the context is not valid then it is not a valid candidate to be
        invoked under :meth:`~.Bot.invoke`.

        Parameters
        -----------
        message: :class:`discord.Message`
            The message to get the invocation context from.
        cls
            The factory class that will be used to create the context.
            By default, this is :class:`.Context`. Should a custom
            class be provided, it must be similar enough to :class:`.Context`\'s
            interface.

        Returns
        --------
        :class:`.Context`
            The invocation context. The type of this can change via the
            ``cls`` parameter.
        """

        view = StringView(message.content)
        ctx = cls(prefix=None, view=view, bot=self, message=message)

        if self._skip_check(message.author.id, self.user.id):
            return ctx

        prefix = await self.get_prefix(message)
        invoked_prefix = prefix

        if isinstance(prefix, str):
            if not view.skip_string(prefix):
                return ctx
        else:
            try:
                # if the context class' __init__ consumes something from the view this
                # will be wrong.  That seems unreasonable though.
                if message.content.startswith(tuple(prefix)):
                    invoked_prefix = discord.utils.find(view.skip_string, prefix)
                else:
                    return ctx

            except TypeError:
                if not isinstance(prefix, list):
                    raise TypeError(
                        "get_prefix must return either a string or a list of string, "
                        "not {}".format(prefix.__class__.__name__)
                    )

                # It's possible a bad command_prefix got us here.
                for value in prefix:
                    if not isinstance(value, str):
                        raise TypeError(
                            "Iterable command_prefix or list returned from get_prefix must "
                            "contain only strings, not {}".format(value.__class__.__name__)
                        )

                # Getting here shouldn't happen
                raise

        if self.strip_after_prefix:
            view.skip_ws()

        invoker = view.get_word()
        ctx.invoked_with = invoker
        ctx.prefix = invoked_prefix
        ctx.command = self.all_commands.get(invoker)
        return ctx

    async def invoke(self, ctx):
        """|coro|

        Invokes the command given under the invocation context and
        handles all the internal event dispatch mechanisms.

        Parameters
        -----------
        ctx: :class:`.Context`
            The invocation context to invoke.
        """
        if ctx.command is not None:
            self.dispatch('command', ctx)
            try:
                if await self.can_run(ctx, call_once=True):
                    await ctx.command.invoke(ctx)
                else:
                    raise errors.CheckFailure('The global check once functions failed.')
            except errors.CommandError as exc:
                await ctx.command.dispatch_error(ctx, exc)
            else:
                self.dispatch('command_completion', ctx)
        elif ctx.invoked_with:
            exc = errors.CommandNotFound('Command "{}" is not found'.format(ctx.invoked_with))
            self.dispatch('command_error', ctx, exc)

    async def process_commands(self, message):
        """|coro|

        This function processes the commands that have been registered
        to the bot and other groups. Without this coroutine, none of the
        commands will be triggered.

        By default, this coroutine is called inside the :func:`.on_message`
        event. If you choose to override the :func:`.on_message` event, then
        you should invoke this coroutine as well.

        This is built using other low level tools, and is equivalent to a
        call to :meth:`~.Bot.get_context` followed by a call to :meth:`~.Bot.invoke`.

        This also checks if the message's author is a bot and doesn't
        call :meth:`~.Bot.get_context` or :meth:`~.Bot.invoke` if so.

        Parameters
        -----------
        message: :class:`discord.Message`
            The message to process commands for.
        """
        if message.author.bot:
            return

        ctx = await self.get_context(message)
        await self.invoke(ctx)

    async def on_message(self, message):
        await self.process_commands(message)


class Bot(BotBase, discord.Client):
    """Represents a discord bot.

    This class is a subclass of :class:`discord.Client` and as a result
    anything that you can do with a :class:`discord.Client` you can do with
    this bot.

    This class also subclasses :class:`.GroupMixin` to provide the functionality
    to manage commands.

    Attributes
    -----------
    command_prefix
        The command prefix is what the message content must contain initially
        to have a command invoked. This prefix could either be a string to
        indicate what the prefix should be, or a callable that takes in the bot
        as its first parameter and :class:`discord.Message` as its second
        parameter and returns the prefix. This is to facilitate "dynamic"
        command prefixes. This callable can be either a regular function or
        a coroutine.

        An empty string as the prefix always matches, enabling prefix-less
        command invocation. While this may be useful in DMs it should be avoided
        in servers, as it's likely to cause performance issues and unintended
        command invocations.

        The command prefix could also be an iterable of strings indicating that
        multiple checks for the prefix should be used and the first one to
        match will be the invocation prefix. You can get this prefix via
        :attr:`.Context.prefix`. To avoid confusion empty iterables are not
        allowed.

        .. note::

            When passing multiple prefixes be careful to not pass a prefix
            that matches a longer prefix occurring later in the sequence.  For
            example, if the command prefix is ``('!', '!?')``  the ``'!?'``
            prefix will never be matched to any message as the previous one
            matches messages starting with ``!?``. This is especially important
            when passing an empty string, it should always be last as no prefix
            after it will be matched.
    case_insensitive: :class:`bool`
        Whether the commands should be case insensitive. Defaults to ``False``. This
        attribute does not carry over to groups. You must set it to every group if
        you require group commands to be case insensitive as well.
    description: :class:`str`
        The content prefixed into the default help message.
    self_bot: :class:`bool`
        If ``True``, the bot will only listen to commands invoked by itself rather
        than ignoring itself. If ``False`` (the default) then the bot will ignore
        itself. This cannot be changed once initialised.
    help_command: Optional[:class:`.HelpCommand`]
        The help command implementation to use. This can be dynamically
        set at runtime. To remove the help command pass ``None``. For more
        information on implementing a help command, see :ref:`ext_commands_help_command`.
    owner_id: Optional[:class:`int`]
        The user ID that owns the bot. If this is not set and is then queried via
        :meth:`.is_owner` then it is fetched automatically using
        :meth:`~.Bot.application_info`.
    owner_ids: Optional[Collection[:class:`int`]]
        The user IDs that owns the bot. This is similar to :attr:`owner_id`.
        If this is not set and the application is team based, then it is
        fetched automatically using :meth:`~.Bot.application_info`.
        For performance reasons it is recommended to use a :class:`set`
        for the collection. You cannot set both ``owner_id`` and ``owner_ids``.

        .. versionadded:: 1.3
    strip_after_prefix: :class:`bool`
        Whether to strip whitespace characters after encountering the command
        prefix. This allows for ``!   hello`` and ``!hello`` to both work if
        the ``command_prefix`` is set to ``!``. Defaults to ``False``.

        .. versionadded:: 1.7
    sync_commands: :class:`bool`
        Whether to sync application-commands on startup, default ``False``.

        This will register global and guild application-commands(slash-, user- and message-commands)
        that are not registered yet, update changes and remove application-commands that could not be found
        in the code anymore if :attr:`delete_not_existing_commands` is set to ``True`` what it is by default.

    delete_not_existing_commands: :class:`bool`
        Whether to remove global and guild-only application-commands that are not in the code anymore, default ``True``.
    sync_commands_on_cog_reload: :class:`bool`
        Whether to sync global and guild-only application-commands when reloading an extension, default ``False``.
    """
    pass


class AutoShardedBot(BotBase, discord.AutoShardedClient):
    """This is similar to :class:`.Bot` except that it is inherited from
    :class:`discord.AutoShardedClient` instead.
    """
    pass
