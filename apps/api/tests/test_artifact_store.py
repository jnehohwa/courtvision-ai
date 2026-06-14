from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

import pytest

from courtvision.artifact_store import (
    ArtifactConfigurationError,
    ArtifactIntegrityError,
    ArtifactStorageConfig,
    ArtifactUnavailableError,
    ModelArtifactStore,
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class FakeStreamingBody(BytesIO):
    closed_by_store = False

    def close(self) -> None:
        self.closed_by_store = True
        super().close()


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.metadata: dict[tuple[str, str], dict[str, str]] = {}
        self.last_body: FakeStreamingBody | None = None

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes,
        ContentType: str,
        Metadata: dict[str, str],
    ) -> None:
        assert ContentType == "application/octet-stream"
        self.objects[(Bucket, Key)] = Body
        self.metadata[(Bucket, Key)] = Metadata

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        data = self.objects[(Bucket, Key)]
        body = FakeStreamingBody(data)
        self.last_body = body
        return {
            "Body": body,
            "ContentLength": len(data),
        }


async def test_managed_local_publish_is_content_addressed_and_immutable(
    tmp_path: Path,
):
    source = tmp_path / "candidate.joblib"
    data = b"verified-model"
    source.write_bytes(data)
    storage_root = tmp_path / "managed"
    store = ModelArtifactStore(
        ArtifactStorageConfig(local_root=storage_root)
    )

    artifact_uri = await store.publish(
        source,
        model_type="pregame",
        version="pregame-2.0",
        artifact_kind="model",
        expected_sha256=sha256(data),
    )
    source.write_bytes(b"changed-training-output")

    assert Path(artifact_uri).is_relative_to(storage_root)
    assert await store.read_verified(artifact_uri, sha256(data)) == data
    assert Path(artifact_uri).read_bytes() == data


def test_legacy_local_path_is_verified_against_registry_hash(tmp_path: Path):
    source = tmp_path / "legacy.joblib"
    source.write_bytes(b"legacy")
    store = ModelArtifactStore(ArtifactStorageConfig())

    assert store.read_verified_sync(str(source), sha256(b"legacy")) == b"legacy"
    with pytest.raises(ArtifactIntegrityError, match="SHA-256"):
        store.read_verified_sync(str(source), sha256(b"different"))


def test_managed_local_store_rejects_path_outside_root(tmp_path: Path):
    outside = tmp_path / "outside.joblib"
    outside.write_bytes(b"outside")
    store = ModelArtifactStore(
        ArtifactStorageConfig(local_root=tmp_path / "managed")
    )

    with pytest.raises(ArtifactConfigurationError, match="outside"):
        store.read_verified_sync(str(outside), sha256(b"outside"))


async def test_artifact_size_limit_applies_before_publish(tmp_path: Path):
    source = tmp_path / "large.joblib"
    source.write_bytes(b"12345")
    store = ModelArtifactStore(ArtifactStorageConfig(max_bytes=4))

    with pytest.raises(ArtifactUnavailableError, match="byte limit"):
        await store.publish(
            source,
            model_type="pregame",
            version="pregame-2.0",
            artifact_kind="model",
            expected_sha256=sha256(b"12345"),
        )


async def test_s3_store_publishes_and_reads_only_configured_scope(tmp_path: Path):
    source = tmp_path / "candidate.joblib"
    data = b"s3-model"
    source.write_bytes(data)
    client = FakeS3Client()
    store = ModelArtifactStore(
        ArtifactStorageConfig(
            backend="s3",
            s3_bucket="courtvision-models",
            s3_prefix="private/models",
        ),
        s3_client=client,
    )

    artifact_uri = await store.publish(
        source,
        model_type="live_win",
        version="live-2.0",
        artifact_kind="model",
        expected_sha256=sha256(data),
    )

    assert artifact_uri.startswith(
        "s3://courtvision-models/private/models/live_win/live-2.0/model-"
    )
    assert await store.read_verified(artifact_uri, sha256(data)) == data
    assert client.last_body is not None and client.last_body.closed_by_store
    with pytest.raises(ArtifactConfigurationError, match="bucket"):
        await store.read_verified(
            artifact_uri.replace("courtvision-models", "other-bucket"),
            sha256(data),
        )
    with pytest.raises(ArtifactConfigurationError, match="prefix"):
        await store.read_verified(
            "s3://courtvision-models/public/model.joblib",
            sha256(data),
        )


async def test_s3_store_detects_remote_tampering(tmp_path: Path):
    source = tmp_path / "candidate.joblib"
    data = b"s3-model"
    source.write_bytes(data)
    client = FakeS3Client()
    store = ModelArtifactStore(
        ArtifactStorageConfig(
            backend="s3",
            s3_bucket="courtvision-models",
        ),
        s3_client=client,
    )
    artifact_uri = await store.publish(
        source,
        model_type="shot_quality",
        version="shot-2.0",
        artifact_kind="model",
        expected_sha256=sha256(data),
    )
    parsed_key = artifact_uri.split("courtvision-models/", 1)[1]
    client.objects[("courtvision-models", parsed_key)] = b"tampered"

    with pytest.raises(ArtifactIntegrityError, match="SHA-256"):
        await store.read_verified(artifact_uri, sha256(data))


async def test_s3_store_rejects_oversized_uri_before_upload(tmp_path: Path):
    source = tmp_path / "candidate.joblib"
    data = b"s3-model"
    source.write_bytes(data)
    client = FakeS3Client()
    store = ModelArtifactStore(
        ArtifactStorageConfig(
            backend="s3",
            s3_bucket="courtvision-models",
        ),
        s3_client=client,
    )

    with pytest.raises(ArtifactConfigurationError, match="column limit"):
        await store.publish(
            source,
            model_type="pregame",
            version="v" * 180,
            artifact_kind="model",
            expected_sha256=sha256(data),
        )

    assert client.objects == {}


def test_artifact_uri_rejects_query_parameters(tmp_path: Path):
    source = tmp_path / "model.joblib"
    source.write_bytes(b"model")
    store = ModelArtifactStore(ArtifactStorageConfig())

    with pytest.raises(ArtifactConfigurationError, match="query"):
        store.read_verified_sync(
            f"{source}?version=2",
            sha256(b"model"),
        )


def test_s3_backend_requires_bucket():
    with pytest.raises(ArtifactConfigurationError, match="bucket"):
        ArtifactStorageConfig(backend="s3")


def test_managed_local_root_must_be_absolute():
    with pytest.raises(ArtifactConfigurationError, match="absolute"):
        ArtifactStorageConfig(local_root=Path("relative/model-artifacts"))
