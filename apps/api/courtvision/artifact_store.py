from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import ParseResult, unquote, urlparse

from courtvision.config import settings


class ArtifactStoreError(RuntimeError):
    pass


class ArtifactConfigurationError(ArtifactStoreError):
    pass


class ArtifactUnavailableError(ArtifactStoreError):
    pass


class ArtifactIntegrityError(ArtifactStoreError):
    pass


@dataclass(frozen=True)
class ArtifactStorageConfig:
    backend: Literal["local", "s3"] = "local"
    local_root: Path | None = None
    s3_bucket: str | None = None
    s3_prefix: str = "courtvision/models"
    s3_endpoint_url: str | None = None
    s3_region: str | None = None
    max_bytes: int = 100 * 1024 * 1024

    def __post_init__(self) -> None:
        if self.max_bytes < 1:
            raise ArtifactConfigurationError("Artifact byte limit must be positive")
        if self.local_root is not None and not self.local_root.expanduser().is_absolute():
            raise ArtifactConfigurationError(
                "Managed local artifact root must be absolute"
            )
        if self.backend == "s3" and not self.s3_bucket:
            raise ArtifactConfigurationError(
                "S3 artifact storage requires a configured bucket"
            )
        if self.s3_bucket and (
            len(self.s3_bucket) > 63
            or any(
                character
                not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
                for character in self.s3_bucket
            )
        ):
            raise ArtifactConfigurationError("S3 artifact bucket is invalid")
        normalized_prefix = self.s3_prefix.strip("/")
        if (
            not normalized_prefix
            or ".." in normalized_prefix.split("/")
            or any(
                character
                not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-/"
                for character in normalized_prefix
            )
        ):
            raise ArtifactConfigurationError("S3 artifact prefix is invalid")
        if len(normalized_prefix) > 48:
            raise ArtifactConfigurationError("S3 artifact prefix is too long")
        object.__setattr__(self, "s3_prefix", normalized_prefix)


class ModelArtifactStore:
    def __init__(
        self,
        config: ArtifactStorageConfig,
        *,
        s3_client: Any | None = None,
    ) -> None:
        self.config = config
        self._s3_client = s3_client

    async def publish(
        self,
        source: Path,
        *,
        model_type: str,
        version: str,
        artifact_kind: Literal["model", "calibration"],
        expected_sha256: str,
    ) -> str:
        return await asyncio.to_thread(
            self.publish_sync,
            source,
            model_type=model_type,
            version=version,
            artifact_kind=artifact_kind,
            expected_sha256=expected_sha256,
        )

    def publish_sync(
        self,
        source: Path,
        *,
        model_type: str,
        version: str,
        artifact_kind: Literal["model", "calibration"],
        expected_sha256: str,
    ) -> str:
        data = self._read_local_file(source)
        self._verify_hash(data, expected_sha256)
        if self.config.backend == "s3":
            artifact_uri = self._publish_s3(
                data,
                model_type=model_type,
                version=version,
                artifact_kind=artifact_kind,
                expected_sha256=expected_sha256,
            )
        elif self.config.local_root is None:
            artifact_uri = self._validate_uri_length(str(source.resolve()))
        else:
            artifact_uri = self._publish_managed_local(
                data,
                model_type=model_type,
                version=version,
                artifact_kind=artifact_kind,
                expected_sha256=expected_sha256,
            )
        return self._validate_uri_length(artifact_uri)

    async def read_verified(
        self,
        artifact_uri: str,
        expected_sha256: str,
    ) -> bytes:
        return await asyncio.to_thread(
            self.read_verified_sync,
            artifact_uri,
            expected_sha256,
        )

    def read_verified_sync(
        self,
        artifact_uri: str,
        expected_sha256: str,
    ) -> bytes:
        parsed = urlparse(artifact_uri)
        if parsed.params or parsed.query or parsed.fragment:
            raise ArtifactConfigurationError(
                "Model artifact URI cannot contain parameters, query, or fragment"
            )
        if parsed.scheme == "s3":
            data = self._read_s3(parsed)
        elif parsed.scheme in {"", "file"}:
            data = self._read_local_uri(parsed, artifact_uri)
        else:
            raise ArtifactConfigurationError(
                f"Unsupported model artifact URI scheme: {parsed.scheme}"
            )
        self._verify_hash(data, expected_sha256)
        return data

    def _publish_managed_local(
        self,
        data: bytes,
        *,
        model_type: str,
        version: str,
        artifact_kind: str,
        expected_sha256: str,
    ) -> str:
        root = self._managed_root()
        target = (
            root
            / self._safe_component(model_type, "model type")
            / self._safe_component(version, "model version")
            / f"{artifact_kind}-{expected_sha256}"
        )
        self._validate_uri_length(str(target))
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            self._verify_hash(self._read_local_file(target), expected_sha256)
            return str(target)

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=target.parent,
                prefix=".upload-",
                delete=False,
            ) as temporary:
                temporary.write(data)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, target)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        return str(target)

    def _publish_s3(
        self,
        data: bytes,
        *,
        model_type: str,
        version: str,
        artifact_kind: str,
        expected_sha256: str,
    ) -> str:
        bucket = self.config.s3_bucket
        if not bucket:
            raise ArtifactConfigurationError("S3 artifact bucket is not configured")
        key = "/".join(
            (
                self.config.s3_prefix,
                self._safe_component(model_type, "model type"),
                self._safe_component(version, "model version"),
                f"{artifact_kind}-{expected_sha256}",
            )
        )
        artifact_uri = self._validate_uri_length(f"s3://{bucket}/{key}")
        try:
            self._s3().put_object(
                Bucket=bucket,
                Key=key,
                Body=data,
                ContentType="application/octet-stream",
                Metadata={"sha256": expected_sha256},
            )
        except Exception as exc:
            raise ArtifactUnavailableError("Failed to publish model artifact") from exc
        return artifact_uri

    def _read_local_uri(
        self,
        parsed: ParseResult,
        original_uri: str,
    ) -> bytes:
        if parsed.scheme == "file":
            if parsed.netloc not in {"", "localhost"}:
                raise ArtifactConfigurationError(
                    "Remote file artifact URIs are not supported"
                )
            path = Path(unquote(parsed.path))
        else:
            path = Path(original_uri)

        resolved_path = path.resolve()
        if self.config.local_root is not None:
            root = self._managed_root()
            if not resolved_path.is_relative_to(root):
                raise ArtifactConfigurationError(
                    "Local artifact URI is outside the configured storage root"
                )
        return self._read_local_file(resolved_path)

    def _read_s3(self, parsed: ParseResult) -> bytes:
        if self.config.backend != "s3":
            raise ArtifactConfigurationError(
                "S3 artifact URI requires the S3 storage backend"
            )
        if parsed.netloc != self.config.s3_bucket:
            raise ArtifactConfigurationError(
                "S3 artifact URI does not match the configured bucket"
            )
        key = parsed.path.lstrip("/")
        allowed_prefix = f"{self.config.s3_prefix}/"
        if not key.startswith(allowed_prefix):
            raise ArtifactConfigurationError(
                "S3 artifact URI is outside the configured prefix"
            )

        body = None
        try:
            response = self._s3().get_object(
                Bucket=self.config.s3_bucket,
                Key=key,
            )
            content_length = int(response.get("ContentLength", 0))
            if content_length > self.config.max_bytes:
                raise ArtifactUnavailableError("Model artifact exceeds the byte limit")
            body = response["Body"]
            data = body.read(self.config.max_bytes + 1)
        except ArtifactStoreError:
            raise
        except Exception as exc:
            raise ArtifactUnavailableError("Failed to read model artifact") from exc
        finally:
            if body is not None and callable(getattr(body, "close", None)):
                body.close()
        if len(data) > self.config.max_bytes:
            raise ArtifactUnavailableError("Model artifact exceeds the byte limit")
        if content_length and len(data) != content_length:
            raise ArtifactUnavailableError("Model artifact read was truncated")
        return data

    def _read_local_file(self, path: Path) -> bytes:
        try:
            size = path.stat().st_size
            if size > self.config.max_bytes:
                raise ArtifactUnavailableError("Model artifact exceeds the byte limit")
            data = path.read_bytes()
        except ArtifactStoreError:
            raise
        except OSError as exc:
            raise ArtifactUnavailableError(
                f"Model artifact is unavailable: {path}"
            ) from exc
        if len(data) > self.config.max_bytes:
            raise ArtifactUnavailableError("Model artifact exceeds the byte limit")
        return data

    def _managed_root(self) -> Path:
        if self.config.local_root is None:
            raise ArtifactConfigurationError(
                "Managed local storage root is not configured"
            )
        return self.config.local_root.expanduser().resolve()

    def _s3(self) -> Any:
        if self._s3_client is None:
            try:
                import boto3
            except ImportError as exc:
                raise ArtifactConfigurationError(
                    "The boto3 dependency is required for S3 artifact storage"
                ) from exc
            self._s3_client = boto3.client(
                "s3",
                endpoint_url=self.config.s3_endpoint_url,
                region_name=self.config.s3_region,
            )
        return self._s3_client

    @staticmethod
    def _safe_component(value: str, label: str) -> str:
        allowed = (
            "abcdefghijklmnopqrstuvwxyz"
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "0123456789._-"
        )
        if (
            not value
            or value in {".", ".."}
            or any(character not in allowed for character in value)
        ):
            raise ArtifactConfigurationError(f"Invalid {label} for artifact storage")
        return value

    @staticmethod
    def _validate_uri_length(artifact_uri: str) -> str:
        if len(artifact_uri) > 255:
            raise ArtifactConfigurationError(
                "Model artifact URI exceeds the registry column limit"
            )
        return artifact_uri

    @staticmethod
    def _verify_hash(data: bytes, expected_sha256: str) -> None:
        actual_sha256 = hashlib.sha256(data).hexdigest()
        if actual_sha256 != expected_sha256:
            raise ArtifactIntegrityError(
                "Model artifact SHA-256 does not match the registry"
            )


artifact_storage_config = ArtifactStorageConfig(
    backend=settings.model_artifact_backend,
    local_root=settings.model_artifact_local_root,
    s3_bucket=settings.model_artifact_s3_bucket,
    s3_prefix=settings.model_artifact_s3_prefix,
    s3_endpoint_url=settings.model_artifact_s3_endpoint_url,
    s3_region=settings.model_artifact_s3_region,
    max_bytes=settings.model_artifact_max_bytes,
)
model_artifact_store = ModelArtifactStore(artifact_storage_config)
