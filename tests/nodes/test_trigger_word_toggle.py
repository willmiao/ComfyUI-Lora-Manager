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
