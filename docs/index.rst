:og:title: discord4py documentation
:og:description: Welcome to the documentation for the discord4py api-wrapper

.. |flag_ua| image:: ./images/flag_ua.png
   :alt: Ukraine
   :width: 30px
   :height: 30px
   :scale: 100%

.. image:: ./images/drop_down_icon.svg

|flag_ua| Welcome to discord\.py-message-components |flag_ua|
==============================================================

.. image:: ./images/banner_light.png

.. figure:: ./images/banner_dark.png
   :name: discord.py-message-components
   :align: center
   :alt: Name of the Project (discord.py-message-components)

   ..
   .. image:: https://discord.com/api/guilds/852871920411475968/embed.png
      :target: https://discord.gg/sb69muSqsg
      :alt: Discord Server Invite

   .. image:: https://img.shields.io/pypi/v/discord.py-message-components.svg
      :target: https://pypi.python.org/pypi/discord.py-message-components
      :alt: PyPI version info

   .. image:: https://img.shields.io/pypi/pyversions/discord.py-message-components.svg
      :target: https://pypi.python.org/pypi/discord.py-message-components
      :alt: PyPI supported Python versions

   .. image:: https://static.pepy.tech/personalized-badge/discord-py-message-components?period=total&units=international_system&left_color=grey&right_color=green&left_text=Downloads
      :target: https://pepy.tech/project/discord.py-message-components
      :alt: Total downloads for the project

   .. image:: https://readthedocs.org/projects/discordpy-message-components/badge/?version=developer
      :target: https://discordpy-message-components.readthedocs.io/en/developer/
      :alt: Documentation Status

   .. image:: https://img.shields.io/static/v1?label=Sponsor&message=%E2%9D%A4&logo=GitHub&color=%23fe8e86
       :target: https://github.com/sponsors/mccoderpy
       :alt: Sponsor button

   A "fork" of `discord.py <https://pypi.org/project/discord.py/1.7.3>`_ library made by `Rapptz <https://github.com/Rapptz>`_ with implementation of the `Discord-Message-Components <https://discord.com/developers/docs/interactions/message-components>`_ & many other features by `mccoderpy <https://github.com/mccoderpy/>`_

.. important::

     This library will be further developed independently of discord.py.
     New features are also implemented. It's not an extension!
     The name only comes from the fact that the original purpose of the library was to add support for message components and we haven't found a better one yet.

.. |PyPI| image:: https://cdn.discordapp.com/emojis/854380926548967444.png?v=1
   :alt: PyPI Logo
   :width: 30px
   :target: https://pypi.org

.. centered::
    **Visit on** |PyPI| **PyPI** `here <https://pypi.org/project/discord.py-message-components>`_


discord.py-message-components is a modern, easy to use, feature-rich, and async ready API wrapper
for Discord.

**Features:**

- Modern Pythonic API using ``async``\/``await`` syntax
- Sane rate limit handling that prevents 429s
- Implements the entire Discord API
- Command extension to aid with bot creation
- Easy to use with an object oriented design
- Optimised for both speed and memory

Getting started
-----------------

Is this your first time using the library? This is the place to get started!

- **First steps:** :doc:`intro` | :doc:`quickstart` | :doc:`logging`
- **Working with Discord:** :doc:`discord` | :doc:`intents`
- **Examples:** Many examples are available in the :resource:`repository <examples>`.

Getting help
--------------

If you're having trouble with something, these resources might help.

- Try the :doc:`faq` first, it's got answers to all common questions.
- Ask us and hang out with us in our :resource:`Discord <discord>` server.
- If you're looking for something specific, try the :ref:`index <genindex>` or :ref:`searching <search>`.
- Report bugs in the :resource:`issue tracker <issues>`.
- Ask in our :resource:`GitHub discussions page <discussions>`.

Extensions
------------

These extensions help you during development when it comes to common tasks.

.. toctree::
  :maxdepth: 1

  ext/commands/index.rst
  ext/tasks/index.rst

Manuals
---------

These pages go into great detail about everything the API can do.

.. toctree::
  :maxdepth: 1

  API Reference </api/index.rst>
  Interactions <Interactions/index.rst>
  OAuth2 <oauth2/index.rst>
  discord.ext.commands API Reference <ext/commands/api.rst>
  discord.ext.tasks API Reference <ext/tasks/index.rst>

Meta
------

If you're looking for something related to the project itself, it's here.

.. toctree::
    :maxdepth: 1

    whats_new
    version_guarantees
    migrating
