from howlhouse.platform.event_bus import EventBus


def test_event_bus_caps_history_and_prunes_closed_channels():
    bus = EventBus(history_limit=2)

    history, queue = bus.subscribe("match_1")
    assert history == []
    assert "match_1" in bus._channels

    bus.publish("match_1", '{"id":"evt_1"}')
    bus.publish("match_1", '{"id":"evt_2"}')
    bus.publish("match_1", '{"id":"evt_3"}')

    channel = bus._channels["match_1"]
    assert channel.history == ['{"id":"evt_2"}', '{"id":"evt_3"}']

    bus.close("match_1")
    assert queue.get_nowait() == '{"id":"evt_1"}'
    assert queue.get_nowait() == '{"id":"evt_2"}'
    assert queue.get_nowait() == '{"id":"evt_3"}'
    assert queue.get_nowait() is None

    bus.unsubscribe("match_1", queue)
    assert "match_1" not in bus._channels
