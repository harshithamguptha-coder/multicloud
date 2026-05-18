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
    primary_content = storage_service.download_from_primary(object_name)
    backup_content = storage_service.download_from_backup(object_name)
    primary_hash = sha256_bytes(primary_content) if primary_content is not None else None
    backup_hash = sha256_bytes(backup_content) if backup_content is not None else None
    primary_valid = primary_hash == original_hash
    backup_valid = backup_hash == original_hash

    recovered = False
    recovery_actions = []

    if primary_valid:
        logger.info("hash match filename=%s location=primary", filename)
    else:
        logger.warning(
            "hash mismatch detected filename=%s location=primary expected=%s actual=%s",
            filename,
            original_hash,
            primary_hash,
        )

    if backup_valid:
        logger.info("hash match filename=%s location=backup", filename)
    else:
        logger.warning(
            "hash mismatch detected filename=%s location=backup expected=%s actual=%s",
            filename,
            original_hash,
            backup_hash,
        )

    if not primary_valid and backup_valid and backup_content is not None:
        logger.warning("recovering file filename=%s source=backup destination=primary", filename)
        storage_service.overwrite_primary(object_name, backup_content, file_doc.get("content_type", "application/octet-stream"))
        recovered = True
        recovery_actions.append("primary_restored_from_backup")
        primary_hash = backup_hash
        primary_valid = True
        logger.warning("recovery complete filename=%s", filename)

    if recovered:
        final_status = "RECOVERED"
    elif primary_valid:
        final_status = "SAFE"
    else:
        final_status = "TAMPERED"

    update_payload = {
        "last_verified_at": utc_now(),
        "status": final_status,
        "primary_hash": primary_hash,
        "backup_hash": backup_hash,
        "current_hash": primary_hash,
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
        mongo_db.recovery_logs.insert_one(
            {
                "file_id": file_doc["_id"],
                "filename": filename,
                "action": "tamper_detected_on_verify",
                "timestamp": utc_now(),
                "details": {
                    "primary_hash": primary_hash,
                    "backup_hash": backup_hash,
                    "original_hash": original_hash,
                },
            }
        )
        logger.error("Tampering detected for %s and auto-recovery failed.", filename)

    return {
        "status": final_status,
        "stored_hash": original_hash,
        "primary_hash": primary_hash,
        "backup_hash": backup_hash,
        "recovered": recovered,
        "recovery_actions": recovery_actions,
    }
