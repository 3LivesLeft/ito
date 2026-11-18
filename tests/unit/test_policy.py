# SPDX-License-Identifier: Apache-2.0
"""Bounded recovery policy (ADR 0005)."""

from meshbeacon.policy import RestartPolicy, StartHistory, Timings

T = Timings()


def test_backoff_doubles_and_caps():
    p = RestartPolicy(T)
    delays = []
    now = 0.0
    for _ in range(4):
        p.record_failure(now)
        delays.append(p.next_start(now) - now)
        now += 1000  # spread failures so the breaker never opens
    assert delays == [1.0, 2.0, 4.0, 8.0]
    p2 = RestartPolicy(Timings(breaker_failures=100))
    for i in range(20):
        p2.record_failure(i * 1.0)
    assert p2.next_start(19.0) - 19.0 == T.backoff_max


def test_breaker_opens_then_gives_up_after_three_openings():
    p = RestartPolicy(T)
    now = 0.0
    for _ in range(5):
        p.record_failure(now)
        now += 1
    assert p.breaker_open and p.openings == 1
    assert p.next_start(now) == p.open_until
    # Two failed half-open attempts → gave up.
    for _ in range(2):
        now = p.open_until
        p.attempt_started()
        now += 5
        p.record_failure(now)
    assert p.gave_up
    assert p.next_start(now) is None


def test_total_time_before_giving_up_is_bounded():
    p = RestartPolicy(T)
    now = 0.0
    attempts = 0
    while True:
        p.attempt_started()
        attempts += 1
        now += 1  # child dies after a second
        p.record_failure(now)
        nxt = p.next_start(now)
        if nxt is None:
            break
        now = nxt
        assert attempts < 100
    assert now < 2 * 60 * 60  # gives up within two hours (about one hour with defaults)


def test_stable_run_resets():
    p = RestartPolicy(T)
    for i in range(5):
        p.record_failure(float(i))
    p.attempt_started()
    p.record_stable()
    assert not p.breaker_open and p.openings == 0 and p.consecutive == 0 and not p.gave_up


def test_start_history_safe_mode_after_five_starts():
    h = StartHistory(T)
    results = [h.begin(100.0 + i, "opts") for i in range(5)]
    assert [r[0] for r in results] == [False, False, False, False, True]
    assert results[-1][1] == 100.0 + T.starts_window


def test_start_history_window_expiry_allows_a_new_attempt():
    h = StartHistory(T)
    for i in range(4):
        h.begin(float(i), "opts")
    safe, _ = h.begin(T.starts_window + 1, "opts")
    assert not safe


def test_start_history_options_change_resets():
    h = StartHistory(T)
    for i in range(4):
        h.begin(float(i), "a")
    safe, _ = h.begin(5.0, "b")
    assert not safe


def test_start_history_stable_resets_and_roundtrips():
    h = StartHistory(T)
    for i in range(4):
        h.begin(float(i), "a")
    h.mark_stable()
    h2 = StartHistory.from_json(T, h.to_json())
    assert not h2.begin(5.0, "a")[0]
    assert StartHistory.from_json(T, "garbage").starts == []
