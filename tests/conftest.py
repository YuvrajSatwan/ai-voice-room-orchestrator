import logging

from roxstar.log import TextFormatter


def pytest_configure(config) -> None:
    """Show our structured fields (bot, error, latency) in pytest's live log output."""
    logging.getLogger("roxstar").handlers[:] = []
    config.option.log_cli_format = None


def pytest_collection_finish(session) -> None:
    plugin = session.config.pluginmanager.get_plugin("logging-plugin")
    if plugin is not None and getattr(plugin, "log_cli_handler", None) is not None:
        plugin.log_cli_handler.setFormatter(TextFormatter())
