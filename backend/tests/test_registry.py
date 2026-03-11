from pathlib import Path

import pytest

from reels_backend.registry import AvatarRegistry, RegistryValidationError


def write_registry(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_registry_accepts_valid_entries(tmp_path: Path) -> None:
    file_path = tmp_path / "avatars.yaml"
    write_registry(
        file_path,
        """
avatars:
  - avatar_id: alpha
    display_name: Alpha
    system_prompt: "Hello"
    lemonslice:
      type: image_url
      value: https://example.com/a.png
    is_active: true
""",
    )

    registry = AvatarRegistry.from_path(file_path)
    avatar = registry.get("alpha")
    assert avatar is not None
    assert avatar.avatar_id == "alpha"


def test_registry_rejects_missing_prompt(tmp_path: Path) -> None:
    file_path = tmp_path / "avatars.yaml"
    write_registry(
        file_path,
        """
avatars:
  - avatar_id: alpha
    display_name: Alpha
    lemonslice:
      type: image_url
      value: https://example.com/a.png
""",
    )

    with pytest.raises(RegistryValidationError):
        AvatarRegistry.from_path(file_path)


def test_registry_rejects_duplicate_avatar_id(tmp_path: Path) -> None:
    file_path = tmp_path / "avatars.yaml"
    write_registry(
        file_path,
        """
avatars:
  - avatar_id: alpha
    display_name: Alpha
    system_prompt: "Hello"
    lemonslice:
      type: image_url
      value: https://example.com/a.png
  - avatar_id: alpha
    display_name: Alpha 2
    system_prompt: "World"
    lemonslice:
      type: image_url
      value: https://example.com/b.png
""",
    )

    with pytest.raises(RegistryValidationError):
        AvatarRegistry.from_path(file_path)


def test_registry_rejects_removed_per_avatar_eleven_api_key(tmp_path: Path) -> None:
    file_path = tmp_path / "avatars.yaml"
    write_registry(
        file_path,
        """
avatars:
  - avatar_id: alpha
    display_name: Alpha
    system_prompt: "Hello"
    lemonslice:
      type: image_url
      value: https://example.com/a.png
    eleven_api_key: should_not_be_here
""",
    )

    with pytest.raises(RegistryValidationError):
        AvatarRegistry.from_path(file_path)


def test_registry_rejects_extra_lemonslice_fields(tmp_path: Path) -> None:
    file_path = tmp_path / "avatars.yaml"
    write_registry(
        file_path,
        """
avatars:
  - avatar_id: alpha
    display_name: Alpha
    system_prompt: "Hello"
    lemonslice:
      type: agent_id
      value: agent_123
      unexpected: true
""",
    )

    with pytest.raises(RegistryValidationError):
        AvatarRegistry.from_path(file_path)


def test_registry_rejects_blank_opening_line(tmp_path: Path) -> None:
    file_path = tmp_path / "avatars.yaml"
    write_registry(
        file_path,
        """
avatars:
  - avatar_id: alpha
    display_name: Alpha
    system_prompt: "Hello"
    opening_line: "   "
    lemonslice:
      type: image_url
      value: https://example.com/a.png
""",
    )

    with pytest.raises(RegistryValidationError):
        AvatarRegistry.from_path(file_path)


def test_registry_rejects_removed_connection_mode_field(tmp_path: Path) -> None:
    file_path = tmp_path / "avatars.yaml"
    write_registry(
        file_path,
        """
avatars:
  - avatar_id: alpha
    display_name: Alpha
    connection_mode: self_hosted
    system_prompt: "Hello"
    lemonslice:
      type: image_url
      value: https://example.com/a.png
""",
    )

    with pytest.raises(RegistryValidationError):
        AvatarRegistry.from_path(file_path)
