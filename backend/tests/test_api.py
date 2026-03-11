from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from reels_backend.api import create_app
from reels_backend.config import Settings
from reels_backend.registry import AvatarRegistry
from reels_backend.token_service import ConnectionDetails


def build_settings(registry_path: Path) -> Settings:
    return Settings(
        livekit_api_key="devkey",
        livekit_api_secret="devsecret",
        livekit_url="wss://example.livekit.cloud",
        agent_name="valentines-reels-agent",
        mistral_api_key="mistral",
        eleven_api_key="eleven",
        lemonslice_api_key="lemonslice",
        mistral_model="mistral-medium-latest",
        eleven_stt_model="scribe_v2_realtime",
        eleven_tts_model="eleven_turbo_v2_5",
        eleven_tts_voice_id="voice",
        eleven_tts_streaming_latency=4,
        eleven_tts_sync_alignment=False,
        eleven_language_code="en",
        eleven_validate_stt_runtime=False,
        eleven_server_vad_enabled=True,
        eleven_server_vad_threshold=0.72,
        eleven_server_vad_silence_threshold_secs=0.45,
        eleven_server_vad_min_speech_duration_ms=420,
        eleven_server_vad_min_silence_duration_ms=500,
        token_ttl_minutes=15,
        idle_silence_seconds=7,
        vad_activation_threshold=0.72,
        vad_deactivation_threshold=0.60,
        vad_min_speech_seconds=0.25,
        vad_min_silence_seconds=0.85,
        vad_prefix_padding_seconds=0.35,
        min_endpointing_delay=0.6,
        max_endpointing_delay=1.9,
        preemptive_generation=True,
        allow_interruptions=True,
        min_interruption_duration=0.9,
        min_interruption_words=2,
        worker_num_idle_processes=1,
        avatar_registry_path=registry_path,
    )


def build_registry(path: Path) -> AvatarRegistry:
    path.write_text(
        """
avatars:
  - avatar_id: easy
    display_name: The Encourager
    system_prompt: "Hello"
    lemonslice:
      type: image_url
      value: https://example.com/easy.png
    preview_image_url: https://example.com/easy.png
    is_active: true
""",
        encoding="utf-8",
    )
    return AvatarRegistry.from_path(path)


def build_poke_shirley_registry(path: Path) -> AvatarRegistry:
    path.write_text(
        """
avatars:
  - avatar_id: poke
    display_name: Her
    system_prompt: "Hello"
    lemonslice:
      type: agent_id
      value: agent_c165f81938710a19
    is_active: true
  - avatar_id: shirley
    display_name: Shirley
    system_prompt: "Hello"
    lemonslice:
      type: agent_id
      value: agent_b1c0f1faf5938acc
    is_active: true
""",
        encoding="utf-8",
    )
    return AvatarRegistry.from_path(path)


def test_get_avatars_hides_system_prompt(tmp_path: Path) -> None:
    registry_path = tmp_path / "avatars.yaml"
    registry = build_registry(registry_path)
    app = create_app(settings=build_settings(registry_path), registry=registry)

    with TestClient(app) as client:
        response = client.get("/avatars")
        assert response.status_code == 200
        payload = response.json()
        assert payload["avatars"][0]["avatar_id"] == "easy"
        assert "system_prompt" not in payload["avatars"][0]


def test_get_avatars_returns_caption_when_present(tmp_path: Path) -> None:
    registry_path = tmp_path / "avatars.yaml"
    registry_path.write_text(
        """
avatars:
  - avatar_id: shirley
    display_name: Shirley
    caption: Beauty Advice
    system_prompt: "Hello"
    lemonslice:
      type: agent_id
      value: agent_b1c0f1faf5938acc
    is_active: true
""",
        encoding="utf-8",
    )
    registry = AvatarRegistry.from_path(registry_path)
    app = create_app(settings=build_settings(registry_path), registry=registry)

    with TestClient(app) as client:
        response = client.get("/avatars")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload["avatars"]) == 1
        assert payload["avatars"][0]["avatar_id"] == "shirley"
        assert payload["avatars"][0]["caption"] == "Beauty Advice"


def test_demo_route_serves_html(tmp_path: Path) -> None:
    registry_path = tmp_path / "avatars.yaml"
    registry = build_registry(registry_path)
    app = create_app(settings=build_settings(registry_path), registry=registry)

    with TestClient(app) as client:
        response = client.get("/demo")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "Valentines Reels Demo" in response.text


def test_post_token_unknown_avatar_returns_404(tmp_path: Path) -> None:
    registry_path = tmp_path / "avatars.yaml"
    registry = build_registry(registry_path)
    app = create_app(settings=build_settings(registry_path), registry=registry)

    with TestClient(app) as client:
        response = client.post("/token", json={"avatar_id": "missing"})
        assert response.status_code == 404
        assert response.json()["detail"] == "Unknown avatar_id"


def test_post_token_invalid_payload_returns_400(tmp_path: Path) -> None:
    registry_path = tmp_path / "avatars.yaml"
    registry = build_registry(registry_path)
    app = create_app(settings=build_settings(registry_path), registry=registry)

    with TestClient(app) as client:
        response = client.post("/token", json={})
        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid request payload"


def test_post_token_valid_avatar_returns_connection_details(
    tmp_path: Path, monkeypatch
) -> None:
    registry_path = tmp_path / "avatars.yaml"
    registry = build_registry(registry_path)
    app = create_app(settings=build_settings(registry_path), registry=registry)

    fake_expiry = datetime.now(UTC) + timedelta(minutes=15)

    def fake_issue_connection_details(*, settings: Settings, avatar_id: str, participant_name: str = "user"):
        assert avatar_id == "easy"
        return ConnectionDetails(
            server_url=settings.livekit_url,
            room_name="reels_easy_abc",
            participant_name=participant_name,
            participant_identity="reels_user_xyz",
            participant_token="token",
            expires_at=fake_expiry,
        )

    monkeypatch.setattr("reels_backend.api.issue_connection_details", fake_issue_connection_details)

    with TestClient(app) as client:
        response = client.post("/token", json={"avatar_id": "easy"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["provider"] == "livekit"
        assert payload["serverUrl"] == "wss://example.livekit.cloud"
        assert payload["roomName"] == "reels_easy_abc"
        assert payload["participantIdentity"] == "reels_user_xyz"
        assert payload["participantToken"] == "token"
        assert payload["expiresAt"].endswith("Z")


def test_post_token_uses_managed_livekit_for_poke_and_shirley(
    tmp_path: Path, monkeypatch
) -> None:
    registry_path = tmp_path / "avatars.yaml"
    registry = build_poke_shirley_registry(registry_path)
    app = create_app(settings=build_settings(registry_path), registry=registry)

    fake_expiry = datetime.now(UTC) + timedelta(minutes=15)
    requested_avatar_ids: list[str] = []

    def fake_issue_connection_details(
        *,
        settings: Settings,
        avatar_id: str,
        participant_name: str = "user",
    ):
        requested_avatar_ids.append(avatar_id)
        return ConnectionDetails(
            server_url=settings.livekit_url,
            room_name=f"reels_{avatar_id}_abc",
            participant_name=participant_name,
            participant_identity=f"reels_user_{avatar_id}",
            participant_token=f"token_{avatar_id}",
            expires_at=fake_expiry,
        )

    monkeypatch.setattr("reels_backend.api.issue_connection_details", fake_issue_connection_details)

    with TestClient(app) as client:
        poke_response = client.post("/token", json={"avatar_id": "poke"})
        assert poke_response.status_code == 200
        poke_payload = poke_response.json()
        assert poke_payload["provider"] == "livekit"
        assert poke_payload["roomName"] == "reels_poke_abc"

        shirley_response = client.post("/token", json={"avatar_id": "shirley"})
        assert shirley_response.status_code == 200
        shirley_payload = shirley_response.json()
        assert shirley_payload["provider"] == "livekit"
        assert shirley_payload["roomName"] == "reels_shirley_abc"

    assert requested_avatar_ids == ["poke", "shirley"]


def test_post_dispatch_agent_unknown_avatar_returns_404(tmp_path: Path) -> None:
    registry_path = tmp_path / "avatars.yaml"
    registry = build_registry(registry_path)
    app = create_app(settings=build_settings(registry_path), registry=registry)

    with TestClient(app) as client:
        response = client.post(
            "/dispatch-agent",
            json={
                "room_name": "reels_room_123",
                "avatar_id": "missing",
                "switch_id": str(uuid4()),
            },
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Unknown avatar_id"


def test_post_dispatch_agent_invalid_payload_returns_error(tmp_path: Path) -> None:
    registry_path = tmp_path / "avatars.yaml"
    registry = build_registry(registry_path)
    app = create_app(settings=build_settings(registry_path), registry=registry)

    with TestClient(app) as client:
        response = client.post("/dispatch-agent", json={"room_name": "reels_room_123"})
        assert response.status_code in (400, 422)  # validation error missing avatar_id

        response = client.post("/dispatch-agent", json={"avatar_id": "easy"})
        assert response.status_code in (400, 422)  # validation error missing room_name

        response = client.post(
            "/dispatch-agent",
            json={"room_name": "reels_room_123", "avatar_id": "easy"},
        )
        assert response.status_code in (400, 422)  # validation error missing switch_id


def test_post_dispatch_agent_valid_calls_livekit_api(tmp_path: Path, monkeypatch) -> None:
    import json as _json

    registry_path = tmp_path / "avatars.yaml"
    registry = build_registry(registry_path)
    app = create_app(settings=build_settings(registry_path), registry=registry)

    captured = []

    async def fake_create_dispatch(self, req) -> None:
        captured.append(req)

    fake_dispatch_svc = type("FakeDispatch", (), {"create_dispatch": fake_create_dispatch})()

    class FakeLiveKitAPI:
        def __init__(self, **kwargs) -> None:
            pass

        @property
        def agent_dispatch(self):
            return fake_dispatch_svc

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr("reels_backend.api.livekit_api.LiveKitAPI", FakeLiveKitAPI)

    switch_id = str(uuid4())
    with TestClient(app) as client:
        response = client.post(
            "/dispatch-agent",
            json={
                "room_name": "reels_room_abc",
                "avatar_id": "easy",
                "switch_id": switch_id,
            },
        )
        assert response.status_code == 204, response.text
        assert len(captured) == 1
        assert captured[0].room == "reels_room_abc"
        assert captured[0].agent_name == "valentines-reels-agent"
        meta = _json.loads(captured[0].metadata)
        assert meta["avatar_id"] == "easy"
        assert meta["switch_id"] == switch_id
