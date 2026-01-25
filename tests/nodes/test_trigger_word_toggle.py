from py.nodes.trigger_word_toggle import TriggerWordToggleLM


def test_group_mode_preserves_parenthesized_groups():
    node = TriggerWordToggleLM()
    trigger_data = [
        {
            "text": "flat color, dark theme",
            "active": True,
            "strength": None,
            "highlighted": False,
        },
        {
            "text": "(a, really, long, test, trigger, word:1.06)",
            "active": True,
            "strength": 1.06,
            "highlighted": False,
        },
        {
            "text": "(sinozick style:0.94)",
            "active": True,
            "strength": 0.94,
            "highlighted": False,
        },
    ]

    original_message = (
        "flat color, dark theme, (a, really, long, test, trigger, word:1.06), "
        "(sinozick style:0.94)"
    )

    (filtered,) = node.process_trigger_words(
        id="node",
        group_mode=True,
        default_active=True,
        allow_strength_adjustment=False,
        orinalMessage=original_message,
        toggle_trigger_words=trigger_data,
    )

    assert filtered == original_message


def test_duplicate_words_keep_individual_active_states():
    node = TriggerWordToggleLM()
    trigger_data = [
        {"text": "A", "active": True, "strength": None, "highlighted": False},
        {"text": "A", "active": False, "strength": None, "highlighted": False},
    ]

    (filtered,) = node.process_trigger_words(
        id="node",
        group_mode=False,
        default_active=True,
        allow_strength_adjustment=False,
        orinalMessage="A, A",
        toggle_trigger_words=trigger_data,
    )

    assert filtered == "A"


def test_duplicate_words_preserve_strength_per_instance():
    node = TriggerWordToggleLM()
    trigger_data = [
        {"text": "(A:0.50)", "active": False, "strength": 0.50, "highlighted": False},
        {"text": "A", "active": True, "strength": 1.2, "highlighted": False},
        {"text": "(A:0.75)", "active": True, "strength": 0.75, "highlighted": False},
    ]

    (filtered,) = node.process_trigger_words(
        id="node",
        group_mode=False,
        default_active=True,
        allow_strength_adjustment=True,
        orinalMessage="A, A, A",
        toggle_trigger_words=trigger_data,
    )

    assert filtered == "(A:1.20), (A:0.75)"


def test_duplicate_groups_respect_active_state():
    node = TriggerWordToggleLM()
    trigger_data = [
        {"text": "A, B", "active": False, "strength": None, "highlighted": False},
        {"text": "A, B", "active": True, "strength": None, "highlighted": False},
    ]

    (filtered,) = node.process_trigger_words(
        id="node",
        group_mode=True,
        default_active=True,
        allow_strength_adjustment=False,
        orinalMessage="A, B,, A, B",
        toggle_trigger_words=trigger_data,
    )

    assert filtered == "A, B"


def test_trigger_words_override_different_from_original():
    node = TriggerWordToggleLM()
    trigger_data = [
        {
            "text": "69yottea_style_illu",
            "active": [
                {"text": "createconcept", "active": True},
                {"text": "DS-Illu", "active": True},
            ],
            "strength": None,
            "highlighted": False,
        }
    ]

    (filtered,) = node.process_trigger_words(
        id="node",
        group_mode=True,
        default_active=True,
        allow_strength_adjustment=False,
        orinalMessage="69yottea_style_illu",
        trigger_words="masterpiece, best quality, very aesthetic, absurdres",
        toggle_trigger_words=trigger_data,
    )

    assert filtered == "masterpiece, best quality, very aesthetic, absurdres"


def test_trigger_words_override_with_new_format():
    node = TriggerWordToggleLM()

    (filtered,) = node.process_trigger_words(
        id="node",
        group_mode=True,
        default_active=True,
        allow_strength_adjustment=False,
        orinalMessage="69yottea_style_illu",
        trigger_words="masterpiece, best quality, very aesthetic, absurdres",
    )

    assert filtered == "masterpiece, best quality, very aesthetic, absurdres"


def test_trigger_words_same_as_original_processes_toggle():
    node = TriggerWordToggleLM()
    trigger_data = [
        {"text": "word1", "active": True, "strength": None, "highlighted": False},
        {"text": "word2", "active": False, "strength": None, "highlighted": False},
    ]

    (filtered,) = node.process_trigger_words(
        id="node",
        group_mode=False,
        default_active=True,
        allow_strength_adjustment=False,
        orinalMessage="word1, word2",
        trigger_words="word1, word2",
        toggle_trigger_words=trigger_data,
    )

    assert filtered == "word1"


def test_trigger_words_override_empty_toggle_data():
    node = TriggerWordToggleLM()

    (filtered,) = node.process_trigger_words(
        id="node",
        group_mode=True,
        default_active=True,
        allow_strength_adjustment=False,
        orinalMessage="69yottea_style_illu",
        trigger_words="custom trigger words",
    )

    assert filtered == "custom trigger words"
