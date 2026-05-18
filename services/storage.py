import io
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError


class StorageError(Exception):
    pass


logger = logging.getLogger(__name__)


class MultiCloudStorage:
    def __init__(self, app):
        self.primary_bucket = app.config["S3_BUCKET_PRIMARY"]
        self.backup_bucket = app.config["S3_BUCKET_BACKUP"]
        self.s3_region = app.config["S3_REGION"]
        self.s3_endpoint_url = app.config["S3_ENDPOINT_URL"]
        self.primary_public_base_url = app.config["S3_PUBLIC_BASE_URL_PRIMARY"]
        self.backup_public_base_url = app.config["S3_PUBLIC_BASE_URL_BACKUP"]
        self.max_upload_attempts = 3
        self.upload_timeout_seconds = 60
        self.signed_url_expiry = 3600

        if not self.primary_bucket:
            raise StorageError("S3_BUCKET_PRIMARY is not configured.")
        if not self.backup_bucket:
            raise StorageError("S3_BUCKET_BACKUP is not configured.")
        if not app.config["S3_ACCESS_KEY_ID"] or not app.config["S3_SECRET_ACCESS_KEY"]:
            raise StorageError("S3 access credentials are not configured.")
        if not self.s3_endpoint_url:
            raise StorageError("S3_ENDPOINT_URL is not configured.")

        client_config = Config(
            signature_version="s3v4",
            connect_timeout=10,
            read_timeout=15,
            retries={"max_attempts": 3, "mode": "standard"},
        )
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=self.s3_endpoint_url,
            aws_access_key_id=app.config["S3_ACCESS_KEY_ID"],
            aws_secret_access_key=app.config["S3_SECRET_ACCESS_KEY"],
            config=client_config,
            region_name=self.s3_region,
        )

    @staticmethod
    def build_object_name(filename: str) -> str:
        return f"files/{uuid.uuid4()}-{filename}"

    def object_url(self, bucket_name: str, object_name: str, public_base_url: Optional[str] = None) -> str:
        if public_base_url:
            return f"{public_base_url.rstrip('/')}/{object_name}"
        return f"{self.s3_endpoint_url.rstrip('/')}/{bucket_name}/{object_name}"

    def generate_download_url(
        self,
        bucket_name: str,
        object_name: str,
        expires_in: Optional[int] = None,
        filename: Optional[str] = None,
        as_attachment: bool = False,
    ) -> str:
        params = {"Bucket": bucket_name, "Key": object_name}
        if as_attachment and filename:
            params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
        return self.s3_client.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=expires_in or self.signed_url_expiry,
        )

    def object_exists(self, bucket_name: str, object_name: str) -> bool:
        try:
            self.s3_client.head_object(Bucket=bucket_name, Key=object_name)
            return True
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in {"404", "NoSuchKey", "NotFound", "NoSuchBucket"}:
                return False
            raise

    def primary_exists(self, object_name: str) -> bool:
        return self.object_exists(self.primary_bucket, object_name)

    def backup_exists(self, object_name: str) -> bool:
        return self.object_exists(self.backup_bucket, object_name)

    def upload_to_bucket(self, bucket_name: str, object_name: str, content: bytes, content_type: str) -> None:
        for attempt in range(1, self.max_upload_attempts + 1):
            logger.info(
                "Starting upload to Backblaze B2 bucket=%s key=%s attempt=%s",
                bucket_name,
                object_name,
                attempt,
            )
            try:
                file_obj = io.BytesIO(content)
                self.s3_client.upload_fileobj(
                    Fileobj=file_obj,
                    Bucket=bucket_name,
                    Key=object_name,
                    ExtraArgs={"ContentType": content_type},
                )
                logger.info("Upload completed for bucket=%s key=%s", bucket_name, object_name)
                return
            except Exception as exc:
                logger.exception(
                    "Upload failed for bucket=%s key=%s attempt=%s error=%s",
                    bucket_name,
                    object_name,
                    attempt,
                    exc,
                )
                if attempt == self.max_upload_attempts:
                    raise StorageError(
                        f"Backblaze upload failed for bucket '{bucket_name}' after {self.max_upload_attempts} attempts: {exc}"
                    ) from exc
                time.sleep(attempt)

    def simple_upload_to_bucket(self, bucket_name: str, object_name: str, content: bytes, content_type: str) -> None:
        file_obj = io.BytesIO(content)
        self.s3_client.upload_fileobj(
            Fileobj=file_obj,
            Bucket=bucket_name,
            Key=object_name,
            ExtraArgs={"ContentType": content_type},
        )

    def upload_to_both(self, filename: str, content: bytes, content_type: str) -> dict:
        object_name = self.build_object_name(filename)
        logger.info("upload start filename=%s key=%s", filename, object_name)
        upload_results = {"primary": False, "backup": False}
        started_at = time.perf_counter()
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                future_map = {
                    "primary": executor.submit(
                        self.upload_to_bucket,
                        self.primary_bucket,
                        object_name,
                        content,
                        content_type,
                    ),
                    "backup": executor.submit(
                        self.upload_to_bucket,
                        self.backup_bucket,
                        object_name,
                        content,
                        content_type,
                    ),
                }
                for label, future in future_map.items():
                    future.result()
                    upload_results[label] = True
                    logger.info("%s done key=%s", label, object_name)
            elapsed = time.perf_counter() - started_at
            logger.info(
                "dual upload success filename=%s key=%s duration_seconds=%.2f",
                filename,
                object_name,
                elapsed,
            )
        except Exception as exc:
            logger.exception("Dual-bucket upload failed for filename=%s key=%s error=%s", filename, object_name, exc)
            if upload_results["primary"]:
                try:
                    self.delete_from_bucket(self.primary_bucket, object_name)
                except Exception as cleanup_exc:
                    logger.exception(
                        "Cleanup failed for primary bucket=%s key=%s error=%s",
                        self.primary_bucket,
                        object_name,
                        cleanup_exc,
                    )
            if upload_results["backup"]:
                try:
                    self.delete_from_bucket(self.backup_bucket, object_name)
                except Exception as cleanup_exc:
                    logger.exception(
                        "Cleanup failed for backup bucket=%s key=%s error=%s",
                        self.backup_bucket,
                        object_name,
                        cleanup_exc,
                    )
            raise
        return {
            "object_name": object_name,
            "primary": True,
            "backup": True,
        }

    def download_from_bucket(self, bucket_name: str, object_name: str) -> Optional[bytes]:
        try:
            response = self.s3_client.get_object(Bucket=bucket_name, Key=object_name)
            return response["Body"].read()
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in {"NoSuchKey", "404", "NoSuchBucket"}:
                return None
            raise

    def download_from_primary(self, object_name: str) -> Optional[bytes]:
        return self.download_from_bucket(self.primary_bucket, object_name)

    def download_from_backup(self, object_name: str) -> Optional[bytes]:
        return self.download_from_bucket(self.backup_bucket, object_name)

    def overwrite_primary(self, object_name: str, content: bytes, content_type: str) -> None:
        self.upload_to_bucket(self.primary_bucket, object_name, content, content_type)

    def simple_overwrite_primary(self, object_name: str, content: bytes, content_type: str) -> None:
        self.simple_upload_to_bucket(self.primary_bucket, object_name, content, content_type)

    def overwrite_backup(self, object_name: str, content: bytes, content_type: str) -> None:
        self.upload_to_bucket(self.backup_bucket, object_name, content, content_type)

    def overwrite_both(self, object_name: str, content: bytes, content_type: str) -> None:
        self.overwrite_primary(object_name, content, content_type)
        self.overwrite_backup(object_name, content, content_type)

    def delete_from_bucket(self, bucket_name: str, object_name: str) -> None:
        self.s3_client.delete_object(Bucket=bucket_name, Key=object_name)
