from py.nodes.trigger_word_toggle import TriggerWordToggle


def test_group_mode_preserves_parenthesized_groups():
    node = TriggerWordToggle()
    trigger_data = [
        {'text': 'flat color, dark theme', 'active': True, 'strength': None, 'highlighted': False},
        {'text': '(a, really, long, test, trigger, word:1.06)', 'active': True, 'strength': 1.06, 'highlighted': False},
        {'text': '(sinozick style:0.94)', 'active': True, 'strength': 0.94, 'highlighted': False},
    ]

    original_message = (
        "flat color, dark theme, (a, really, long, test, trigger, word:1.06), "
        "(sinozick style:0.94)"
    )

    filtered, = node.process_trigger_words(
        id="node",
        group_mode=True,
        default_active=True,
        allow_strength_adjustment=False,
        orinalMessage=original_message,
        toggle_trigger_words=trigger_data,
    )

    assert filtered == original_message


def test_duplicate_words_keep_individual_active_states():
    node = TriggerWordToggle()
    trigger_data = [
        {'text': 'A', 'active': True, 'strength': None, 'highlighted': False},
        {'text': 'A', 'active': False, 'strength': None, 'highlighted': False},
    ]

    filtered, = node.process_trigger_words(
        id="node",
        group_mode=False,
        default_active=True,
        allow_strength_adjustment=False,
        orinalMessage="A, A",
        toggle_trigger_words=trigger_data,
    )

    assert filtered == "A"


def test_duplicate_words_preserve_strength_per_instance():
    node = TriggerWordToggle()
    trigger_data = [
        {'text': '(A:0.50)', 'active': False, 'strength': 0.50, 'highlighted': False},
        {'text': 'A', 'active': True, 'strength': 1.2, 'highlighted': False},
        {'text': '(A:0.75)', 'active': True, 'strength': 0.75, 'highlighted': False},
    ]

    filtered, = node.process_trigger_words(
        id="node",
        group_mode=False,
        default_active=True,
        allow_strength_adjustment=True,
        orinalMessage="A, A, A",
        toggle_trigger_words=trigger_data,
    )

    assert filtered == "(A:1.20), (A:0.75)"


def test_duplicate_groups_respect_active_state():
    node = TriggerWordToggle()
    trigger_data = [
        {'text': 'A, B', 'active': False, 'strength': None, 'highlighted': False},
        {'text': 'A, B', 'active': True, 'strength': None, 'highlighted': False},
    ]

    filtered, = node.process_trigger_words(
        id="node",
        group_mode=True,
        default_active=True,
        allow_strength_adjustment=False,
        orinalMessage="A, B,, A, B",
        toggle_trigger_words=trigger_data,
    )

    assert filtered == "A, B"
