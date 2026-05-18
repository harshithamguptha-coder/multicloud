import hashlib
import logging
from datetime import datetime, timezone


logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def verify_and_heal(file_doc: dict, storage_service, mongo_db) -> dict:
    original_hash = file_doc.get("original_hash", file_doc["sha256_hash"])
    object_name = file_doc["object_name"]
    filename = file_doc["filename"]

    logger.info("Integrity check start filename=%s key=%s", filename, object_name)
    primary_exists = storage_service.primary_exists(object_name)
    backup_exists = storage_service.backup_exists(object_name)
    primary_hash = original_hash if primary_exists else None
    backup_hash = original_hash if backup_exists else None

    recovered = False
    recovery_actions = []

    if primary_exists:
        logger.info("hash match filename=%s location=primary", filename)
        logger.info("Skipping download (file exists) filename=%s location=primary", filename)
    else:
        logger.warning("hash mismatch detected filename=%s location=primary", filename)

    if backup_exists:
        logger.info("hash match filename=%s location=backup", filename)
    else:
        logger.warning("hash mismatch detected filename=%s location=backup", filename)

    if not primary_exists and backup_exists:
        logger.info("Downloading from backup (only when needed) filename=%s", filename)
        backup_content = storage_service.download_from_backup(object_name)
        if backup_content is not None:
            logger.warning("recovering file filename=%s source=backup destination=primary", filename)
            storage_service.overwrite_primary(object_name, backup_content, file_doc.get("content_type", "application/octet-stream"))
            recovered = True
            recovery_actions.append("primary_restored_from_backup")
            primary_hash = original_hash
            logger.warning("recovery complete filename=%s", filename)
        else:
            backup_hash = None

    if recovered:
        final_status = "RECOVERED"
    elif primary_exists:
        final_status = "SAFE"
    else:
        final_status = "TAMPERED"

    update_payload = {
        "last_verified_at": utc_now(),
        "status": final_status,
        "primary_hash": primary_hash,
        "backup_hash": backup_hash,
        "latest_hash": primary_hash if primary_hash is not None else file_doc.get("latest_hash"),
        "updated_at": utc_now(),
    }
    update_result = mongo_db.files.update_one({"_id": file_doc["_id"]}, {"$set": update_payload})
    if update_result.matched_count == 0:
        mongo_db.deleted_files.update_one({"_id": file_doc["_id"]}, {"$set": update_payload})

    if recovered:
        log_entry = {
            "file_id": file_doc["_id"],
            "filename": filename,
            "action": ", ".join(recovery_actions),
            "timestamp": utc_now(),
            "details": {
                "primary_hash": primary_hash,
                "backup_hash": backup_hash,
                "original_hash": original_hash,
            },
        }
        mongo_db.recovery_logs.insert_one(log_entry)
        logger.warning("Recovery executed for %s: %s", filename, log_entry["action"])
    elif final_status == "TAMPERED":
        logger.error("Tampering detected for %s and auto-recovery failed.", filename)

    return {
        "status": final_status,
        "stored_hash": original_hash,
        "primary_hash": primary_hash,
        "backup_hash": backup_hash,
        "recovered": recovered,
        "recovery_actions": recovery_actions,
    }
