"""Getting the bots (back) into a room, including after a worker restart."""

from roxstar.token_server import dispatch_action


def test_new_room_gets_the_worker() -> None:
    assert dispatch_action(brain_present=False, dispatch_ages_s=[]) == "create"


def test_room_with_the_brain_present_is_left_alone() -> None:
    assert dispatch_action(brain_present=True, dispatch_ages_s=[600]) == "keep"


def test_stale_dispatch_after_a_worker_restart_is_replaced() -> None:
    """Seen live: people stayed in the room, the worker restarted, and no bots came back."""
    assert dispatch_action(brain_present=False, dispatch_ages_s=[900]) == "replace"


def test_a_fresh_dispatch_is_not_duplicated_while_its_brain_is_joining() -> None:
    assert dispatch_action(brain_present=False, dispatch_ages_s=[3]) == "keep"
