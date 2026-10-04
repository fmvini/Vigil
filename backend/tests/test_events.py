import asyncio
import json
from datetime import timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from conftest import authenticate
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import select
from starlette.requests import ClientDisconnect

from app.api import events as events_api
from app.api.errors import ApiError
from app.db.models import Project, Session, User
from app.security import utcnow
from app.services.events import EventHub, event_stream, session_valid


class ConnectedRequest:
    disconnected = False

    async def is_disconnected(self):
        return self.disconnected


async def valid():
    return True


def event(owner_id, project_id=None, revision=1):
    return {
        "type": "project.updated",
        "owner_id": str(owner_id),
        "project_id": str(project_id or uuid4()),
        "revision": revision,
    }


async def test_sse_auth_cookie_not_query_and_origin(client, authenticated):
    cookie = authenticated.cookies.get("vigil_session")
    authenticated.cookies.clear()
    assert (await client.get("/api/v1/events")).status_code == 401
    assert (await client.get(f"/api/v1/events?token={cookie}")).status_code == 401
    authenticated.cookies.set("vigil_session", cookie)
    assert (await client.get("/api/v1/events?token=forbidden")).status_code == 400
    assert (
        await client.get("/api/v1/events", headers={"Origin": "https://evil.test"})
    ).status_code == 403


async def test_max_three_connections_and_cleanup():
    hub = EventHub()
    owner = uuid4()
    entries = [hub.subscribe(owner) for _ in range(3)]
    with pytest.raises(ApiError) as exc:
        hub.subscribe(owner)
    assert exc.value.status == 429 and exc.value.code == "sse_connection_limit"
    hub.unsubscribe(entries.pop())
    entries.append(hub.subscribe(owner))
    for entry in entries:
        hub.unsubscribe(entry)
    assert hub.subscriptions == {}


async def test_sse_http_limit_returns_envelope(api_app, authenticated):
    hub = api_app.state.event_hub
    hub.redis_factory = None
    owner = UUID((await authenticated.get("/api/v1/auth/me")).json()["user"]["id"])
    subscriptions = [hub.subscribe(owner) for _ in range(3)]
    response = await authenticated.get("/api/v1/events")
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "sse_connection_limit"
    for subscription in subscriptions:
        hub.unsubscribe(subscription)


async def test_sse_asgi_cookie_stream_and_disconnect_cleanup(api_app, authenticated):
    hub = api_app.state.event_hub
    hub.redis_factory = None
    cookie = authenticated.cookies.get("vigil_session")
    disconnected = asyncio.Event()
    frames = []
    request_sent = False

    async def receive():
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await disconnected.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        frames.append(message)
        if message["type"] == "http.response.body" and b"snapshot.required" in message.get(
            "body", b""
        ):
            disconnected.set()

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.0"},
        "method": "GET",
        "path": "/api/v1/events",
        "raw_path": b"/api/v1/events",
        "query_string": b"",
        "root_path": "",
        "scheme": "https",
        "http_version": "1.1",
        "server": ("app.test", 443),
        "client": ("127.0.0.1", 12345),
        "headers": [(b"host", b"app.test"), (b"cookie", f"vigil_session={cookie}".encode())],
    }
    await asyncio.wait_for(api_app(scope, receive, send), 2)
    initial = next(message for message in frames if message["type"] == "http.response.start")
    assert initial["status"] == 200
    headers = dict(initial["headers"])
    assert headers[b"content-type"].startswith(b"text/event-stream")
    assert headers[b"x-accel-buffering"] == b"no" and headers[b"cache-control"] == b"no-store"
    assert any(b"snapshot.required" in frame.get("body", b"") for frame in frames)
    assert hub.subscriptions == {}


async def test_owner_filter_and_public_envelope_whitelist():
    hub = EventHub()
    owner, other_owner = uuid4(), uuid4()
    subscription, other = hub.subscribe(owner), hub.subscribe(other_owner)
    hub.dispatch(event(owner))
    payload = subscription.queue.get_nowait()
    assert "owner_id" not in payload and "project_id" in payload
    assert other.queue.empty()
    hub.dispatch({**event(owner), "url": "https://private-url.test", "secret": "secret"})
    assert subscription.queue.empty()
    await hub.close()


async def test_backpressure_is_bounded_and_demands_snapshot():
    hub = EventHub(queue_size=2)
    owner = uuid4()
    subscription = hub.subscribe(owner)
    for n in range(100):
        hub.dispatch(event(owner, revision=n))
    assert subscription.queue.qsize() <= 2
    remaining = [subscription.queue.get_nowait() for _ in range(subscription.queue.qsize())]
    assert any(value["type"] == "snapshot.required" for value in remaining)
    await hub.close()


async def test_stream_immediate_periodic_snapshot_heartbeat_and_disconnect():
    hub = EventHub()
    subscription = hub.subscribe(uuid4())
    request = ConnectedRequest()
    stream = event_stream(
        request,
        hub,
        subscription,
        valid,
        snapshot_seconds=0.025,
        heartbeat_seconds=0.01,
        session_check_seconds=0.02,
    )
    assert b"snapshot.required" in await anext(stream)
    frames = [await asyncio.wait_for(anext(stream), 0.2) for _ in range(4)]
    assert b": heartbeat\n\n" in frames
    assert any(b"periodic" in frame for frame in frames)
    request.disconnected = True
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    assert hub.subscriptions == {}


async def test_stream_revocation_check_closes_and_cleans_slot():
    hub = EventHub()
    subscription = hub.subscribe(uuid4())
    checks = []

    async def invalid():
        checks.append(True)
        return len(checks) == 1

    stream = event_stream(
        ConnectedRequest(),
        hub,
        subscription,
        invalid,
        snapshot_seconds=10,
        heartbeat_seconds=10,
        session_check_seconds=0.01,
    )
    await anext(stream)
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(anext(stream), 0.1)
    assert checks == [True, True] and hub.subscriptions == {}


async def test_stream_cancellation_releases_slot():
    hub = EventHub()
    subscription = hub.subscribe(uuid4())
    stream = event_stream(
        ConnectedRequest(),
        hub,
        subscription,
        valid,
        snapshot_seconds=10,
        heartbeat_seconds=10,
        session_check_seconds=10,
    )
    await anext(stream)
    pending = asyncio.create_task(anext(stream))
    await asyncio.sleep(0)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert hub.subscriptions == {}


@pytest.mark.parametrize("kind", ["revoked", "expired", "idle", "inactive", "deleted"])
async def test_actual_database_session_revalidation(api_app, authenticated, kind):
    factory = api_app.state.session_factory
    async with factory() as db:
        session = await db.scalar(select(Session).where(Session.revoked_at.is_(None)))
        session_id, user_id = session.id, session.user_id
    assert await session_valid(factory, session_id, user_id, api_app.state.settings)
    async with factory.begin() as db:
        session = await db.get(Session, session_id)
        if kind == "revoked":
            session.revoked_at = utcnow()
        elif kind == "inactive":
            user = await db.get(User, user_id)
            user.is_active = False
        elif kind == "deleted":
            await db.delete(session)
        else:
            session.created_at = utcnow() - timedelta(days=8)
            if kind == "expired":
                session.expires_at = utcnow() - timedelta(seconds=1)
            else:
                session.last_seen_at = utcnow() - timedelta(hours=25)
    assert not await session_valid(factory, session_id, user_id, api_app.state.settings)


async def test_crud_event_emits_after_commit_and_failed_mutation_is_silent(api_app, authenticated):
    hub = api_app.state.event_hub
    hub.redis_factory = None
    me = (await authenticated.get("/api/v1/auth/me")).json()
    subscription = hub.subscribe(UUID(me["user"]["id"]))
    emitted = []
    original_emit = hub.emit

    async def emit(payload):
        async with api_app.state.session_factory() as db:
            project = await db.get(Project, UUID(payload["project_id"]))
            assert project is not None and project.revision == payload["revision"]
        emitted.append(payload)
        await original_emit(payload)

    hub.emit = emit
    created = await authenticated.post("/api/v1/projects", json={"name": "SSE"})
    assert created.status_code == 201
    assert len(emitted) == 1 and subscription.queue.qsize() == 1
    authenticated.headers["X-CSRF-Token"] = "invalid"
    assert (
        await authenticated.post("/api/v1/projects", json={"name": "blocked"})
    ).status_code == 403
    assert len(emitted) == 1
    hub.unsubscribe(subscription)


async def test_pubsub_failure_preserves_local_delivery_and_periodic_snapshots():
    hub = EventHub(reconnect_seconds=0.01)
    owner = uuid4()

    class OfflineRedis:
        def pubsub(self):
            raise ConnectionError("private-redis-credential")

        async def aclose(self):
            pass

    hub.redis_factory = OfflineRedis
    subscription = hub.subscribe(owner)
    await asyncio.sleep(0.02)
    assert not hub.connected
    await hub.emit(event(owner))
    assert subscription.queue.get_nowait()["type"] == "project.updated"
    stream = event_stream(
        ConnectedRequest(),
        hub,
        subscription,
        valid,
        snapshot_seconds=0.01,
        heartbeat_seconds=10,
        session_check_seconds=10,
    )
    assert b"connected" in await anext(stream)
    assert b"periodic" in await asyncio.wait_for(anext(stream), 0.1)
    await stream.aclose()
    await hub.close()
    assert hub.task is None and hub.subscriptions == {}


async def test_pubsub_filters_owner_and_closes_resources():
    owner = uuid4()
    ready = asyncio.Event()
    queue = asyncio.Queue()
    closed = []

    class PubSub:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            closed.append("pubsub")

        async def subscribe(self, channel):
            assert channel == "vigil:updates"
            ready.set()

        async def get_message(self, **kwargs):
            return await queue.get()

    class FakeRedis:
        def pubsub(self):
            return PubSub()

        async def aclose(self):
            closed.append("redis")

    hub = EventHub(redis_factory=FakeRedis)
    subscription = hub.subscribe(owner)
    other = hub.subscribe(uuid4())
    await ready.wait()
    # Echoes of local publication and invalid envelopes must not reach either owner.
    await queue.put({"data": json.dumps({**event(owner), "source": hub.source}).encode()})
    await queue.put({"data": b"not-json"})
    await queue.put({"data": b"x" * 4097})
    await queue.put({"data": json.dumps({**event(owner), "secret": "private"}).encode()})
    await queue.put({"data": json.dumps(event(owner, revision=99)).encode()})
    payload = await asyncio.wait_for(subscription.queue.get(), 0.1)
    assert payload["type"] == "project.updated" and payload["revision"] == 99
    assert subscription.queue.empty() and other.queue.empty()
    await hub.close()
    assert closed == ["pubsub", "redis"]


async def test_invalid_session_never_receives_initial_or_queued_signals():
    hub = EventHub()
    owner = uuid4()
    subscription = hub.subscribe(owner)
    hub.dispatch(event(owner))

    async def invalid():
        return False

    stream = event_stream(ConnectedRequest(), hub, subscription, invalid)
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    assert hub.subscriptions == {}


async def test_session_check_runs_even_when_queue_stays_busy():
    hub = EventHub()
    owner = uuid4()
    subscription = hub.subscribe(owner)
    active = True
    checks = []

    async def check():
        checks.append(active)
        return active

    stream = event_stream(ConnectedRequest(), hub, subscription, check, session_check_seconds=0.01)
    assert b"connected" in await anext(stream)
    hub.dispatch(event(owner))
    assert b"project.updated" in await anext(stream)
    active = False
    hub.dispatch(event(owner))
    await asyncio.sleep(0.02)
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    assert checks == [True, False] and hub.subscriptions == {}


async def test_session_owner_mismatch_and_check_failure_are_closed(api_app, authenticated, caplog):
    factory = api_app.state.session_factory
    async with factory() as db:
        session = await db.scalar(select(Session))
        session_id, user_id = session.id, session.user_id
        original_last_seen = session.last_seen_at
    assert not await session_valid(factory, session_id, uuid4(), api_app.state.settings)
    assert await session_valid(factory, session_id, user_id, api_app.state.settings)
    async with factory() as db:
        assert (await db.get(Session, session_id)).last_seen_at == original_last_seen

    def failed_factory():
        raise ConnectionError("private-db-password")

    assert not await session_valid(failed_factory, session_id, user_id, api_app.state.settings)
    assert "sse_session_check_unavailable" in caplog.text
    assert "private-db-password" not in caplog.text


def stream_scope(cookie, spec_version="2.0"):
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": spec_version},
        "method": "GET",
        "path": "/api/v1/events",
        "raw_path": b"/api/v1/events",
        "query_string": b"",
        "root_path": "",
        "scheme": "https",
        "http_version": "1.1",
        "server": ("app.test", 443),
        "client": ("127.0.0.1", 12345),
        "headers": [(b"host", b"app.test"), (b"cookie", f"vigil_session={cookie}".encode())],
    }


@pytest.mark.parametrize("kind", ["logout", "rotate", "inactive", "expired", "idle"])
async def test_http_stream_stops_after_committed_session_invalidation(
    api_app, authenticated, monkeypatch, kind
):
    hub = api_app.state.event_hub
    hub.redis_factory = None
    cookie = authenticated.cookies.get("vigil_session")
    factory = api_app.state.session_factory
    async with factory() as db:
        session = await db.scalar(select(Session))
        session_id, owner_id = session.id, session.user_id
    original_stream = events_api.event_stream
    committed = asyncio.Event()
    initial_check = True

    async def check_committed_session(*args):
        nonlocal initial_check
        if initial_check:
            initial_check = False
        else:
            # SQLite's in-memory adapter shares one connection; do not overlap its
            # login write with a second Session's rollback. Revalidate the committed row.
            await committed.wait()
        return await session_valid(*args)

    def fast_stream(*args):
        return original_stream(
            *args, snapshot_seconds=10, heartbeat_seconds=10, session_check_seconds=0.005
        )

    monkeypatch.setattr(events_api, "event_stream", fast_stream)
    monkeypatch.setattr(events_api, "session_valid", check_committed_session)
    bodies = []

    async def receive():
        await asyncio.Event().wait()

    async def send(message):
        if message["type"] != "http.response.body":
            return
        body = message.get("body", b"")
        bodies.append(body)
        if b"connected" not in body:
            return
        pool = api_app.state.engine.sync_engine.pool
        if hasattr(pool, "checkedout"):
            assert pool.checkedout() == 0
        if kind == "logout":
            assert (await authenticated.post("/api/v1/auth/logout")).status_code == 204
        elif kind == "rotate":
            response = await authenticated.post(
                "/api/v1/auth/login",
                json={"email": "owner@example.com", "password": "a strong test password"},
            )
            assert response.status_code == 200
        else:
            async with factory.begin() as db:
                session = await db.get(Session, session_id)
                if kind == "inactive":
                    user = await db.get(User, owner_id)
                    user.is_active = False
                elif kind == "expired":
                    session.created_at = utcnow() - timedelta(days=8)
                    session.expires_at = utcnow() - timedelta(seconds=1)
                else:
                    session.created_at = utcnow() - timedelta(days=8)
                    session.last_seen_at = utcnow() - timedelta(days=2)
        committed.set()
        # Invalidation is delivered only after the configured revalidation deadline.
        await asyncio.sleep(0.01)
        hub.dispatch(event(owner_id))

    await asyncio.wait_for(api_app(stream_scope(cookie), receive, send), 2)
    assert len([body for body in bodies if body]) == 1
    assert not any(b"project.updated" in body for body in bodies)
    assert hub.subscriptions == {}
    assert not await session_valid(factory, session_id, owner_id, api_app.state.settings)
    if kind == "rotate":
        async with factory() as db:
            new_session = await db.scalar(select(Session).where(Session.revoked_at.is_(None)))
        assert new_session.id != session_id
        assert await session_valid(factory, new_session.id, owner_id, api_app.state.settings)


async def test_failed_auth_commit_does_not_reserve_stream_slot(api_app, authenticated):
    hub = api_app.state.event_hub
    hub.redis_factory = None
    subscriptions = []
    original_subscribe = hub.subscribe

    def subscribe(owner):
        subscriptions.append(owner)
        return original_subscribe(owner)

    hub.subscribe = subscribe

    def fail_commit(connection):
        raise RuntimeError("auth_commit_failed")

    sqlalchemy_event.listen(api_app.state.engine.sync_engine, "commit", fail_commit)
    try:
        with pytest.raises(RuntimeError, match="auth_commit_failed"):
            await authenticated.get("/api/v1/events")
    finally:
        sqlalchemy_event.remove(api_app.state.engine.sync_engine, "commit", fail_commit)
    assert subscriptions == [] and hub.subscriptions == {}


@pytest.mark.parametrize("spec_version", ["2.0", "2.4"])
@pytest.mark.parametrize("blocked_frame", ["http.response.start", "http.response.body"])
async def test_slow_send_releases_slot_and_closes_generator(spec_version, blocked_frame):
    hub = EventHub()
    subscription = hub.subscribe(uuid4())
    closed = []

    async def frames():
        try:
            yield b"event: snapshot.required\ndata: {}\n\n"
            await asyncio.Event().wait()
        finally:
            closed.append(True)

    stream = frames()
    response = events_api.EventResponse(
        stream, hub=hub, subscription=subscription, send_timeout_seconds=0.01
    )

    async def receive():
        await asyncio.Event().wait()

    async def send(message):
        if message["type"] == blocked_frame:
            await asyncio.Event().wait()

    expected = ClientDisconnect if spec_version == "2.4" else TimeoutError
    with pytest.raises(expected):
        await asyncio.wait_for(response(stream_scope("unused", spec_version), receive, send), 1)
    assert hub.subscriptions == {} and stream.ag_frame is None
    if blocked_frame == "http.response.body":
        assert closed == [True]


@pytest.mark.parametrize(
    "kind", ["project.updated", "monitor.updated", "incident.opened", "incident.closed"]
)
async def test_all_signal_types_are_owner_scoped_and_exclude_internal_fields(kind):
    hub = EventHub()
    owner = uuid4()
    subscription, other = hub.subscribe(owner), hub.subscribe(uuid4())
    payload = {
        **event(owner),
        "type": kind,
        "monitor_id": str(uuid4()),
        "incident_id": str(uuid4()),
        "source": "other-replica",
    }
    hub.dispatch(payload)
    public = subscription.queue.get_nowait()
    assert set(public) == {"type", "project_id", "monitor_id", "incident_id", "revision"}
    assert public["type"] == kind and other.queue.empty()
    await hub.close()


async def test_publish_without_local_subscribers_and_validation():
    published, closed = [], []

    class Publisher:
        async def publish(self, channel, payload):
            published.append((channel, json.loads(payload)))

        async def aclose(self):
            closed.append(True)

    hub = EventHub(redis_factory=Publisher)
    owner = uuid4()
    await hub.emit(event(owner))
    assert hub.task is None and hub.subscriptions == {}
    assert len(published) == 1 and closed == [True]
    channel, payload = published[0]
    assert channel == "vigil:updates" and payload["owner_id"] == str(owner)
    assert payload["source"] == hub.source
    await hub.emit({**event(owner), "secret": "must-not-publish"})
    assert len(published) == 1
    await hub.close()
    with pytest.raises(ApiError) as exc:
        hub.subscribe(owner)
    assert exc.value.status == 503


async def test_publish_failure_does_not_disable_connected_listener(caplog):
    published = []

    class Publisher:
        async def publish(self, channel, payload):
            published.append(payload)
            if len(published) == 1:
                raise ConnectionError("private-redis-password")

    hub = EventHub()
    owner = uuid4()
    subscription = hub.subscribe(owner)
    hub.redis_factory = Publisher
    hub.redis = Publisher()
    hub.connected = True
    await hub.emit(event(owner))
    assert hub.connected
    await hub.emit(event(owner))
    assert len(published) == 2 and subscription.queue.qsize() == 2
    assert "private-redis-password" not in caplog.text
    await hub.close()


async def test_real_crud_signals_follow_owner_and_authorization(api_app, authenticated):
    hub = api_app.state.event_hub
    hub.redis_factory = None
    owner = UUID((await authenticated.get("/api/v1/auth/me")).json()["user"]["id"])
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api_app),
        base_url="https://app.test",
        headers={"Origin": "https://app.test", "X-Vigil-Request": "browser"},
    ) as other:
        identity = await authenticate(other, "other@example.com")
        other.headers["X-CSRF-Token"] = identity["csrf_token"]
        owned_stream, other_stream = (
            hub.subscribe(owner),
            hub.subscribe(UUID(identity["user"]["id"])),
        )
        created = await authenticated.post("/api/v1/projects", json={"name": "Owned"})
        assert created.status_code == 201
        project = created.json()
        signal = owned_stream.queue.get_nowait()
        assert signal["project_id"] == project["id"] and other_stream.queue.empty()
        created_monitor = await authenticated.post(
            f"/api/v1/projects/{project['id']}/monitors",
            json={"name": "Private", "url": "https://example.com/private"},
        )
        assert created_monitor.status_code == 201
        monitor = created_monitor.json()
        signal = owned_stream.queue.get_nowait()
        assert signal == {
            "type": "monitor.updated",
            "project_id": project["id"],
            "monitor_id": monitor["id"],
            "revision": project["revision"] + 1,
        }
        assert other_stream.queue.empty()
        forbidden = await other.post(f"/api/v1/monitors/{monitor['id']}/pause")
        assert forbidden.status_code == 404
        assert owned_stream.queue.empty() and other_stream.queue.empty()
        assert (
            await authenticated.post(f"/api/v1/monitors/{monitor['id']}/pause")
        ).status_code == 200
        assert owned_stream.queue.get_nowait()["revision"] == project["revision"] + 2
        assert other_stream.queue.empty()
        assert (await other.post("/api/v1/projects", json={"name": "Other"})).status_code == 201
        assert other_stream.queue.get_nowait()["type"] == "project.updated"
        assert owned_stream.queue.empty()
        hub.unsubscribe(owned_stream)
        hub.unsubscribe(other_stream)


async def test_rolled_back_mutation_never_emits_or_persists(api_app, authenticated):
    hub = api_app.state.event_hub
    hub.redis_factory = None
    owner = UUID((await authenticated.get("/api/v1/auth/me")).json()["user"]["id"])
    subscription = hub.subscribe(owner)

    def fail_commit(connection):
        raise RuntimeError("mutation_commit_failed")

    sqlalchemy_event.listen(api_app.state.engine.sync_engine, "commit", fail_commit)
    try:
        with pytest.raises(RuntimeError, match="mutation_commit_failed"):
            await authenticated.post("/api/v1/projects", json={"name": "Rolled back"})
    finally:
        sqlalchemy_event.remove(api_app.state.engine.sync_engine, "commit", fail_commit)
    assert subscription.queue.empty()
    async with api_app.state.session_factory() as db:
        assert await db.scalar(select(Project).where(Project.name == "Rolled back")) is None
    hub.unsubscribe(subscription)
