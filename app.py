import atexit
import logging
import re
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit

from bson import ObjectId
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
import certifi
from pymongo import MongoClient
from pymongo.errors import ConfigurationError, ConnectionFailure, PyMongoError, ServerSelectionTimeoutError
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from config import Config
from services.integrity import sha256_bytes, utc_now, verify_and_heal
from services.storage import MultiCloudStorage


BASE_DIR = Path(__file__).resolve().parent
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)
storage_service = None


COPY_SUFFIX_RE = re.compile(
    r"(?:"
    r"\s*\(\s*\d+\s*\)"
    r"|[\s._-]+(?:copy|final|edited|modified|new|latest|updated|revision|rev)\d*"
    r"|[\s._-]+v?\d{1,3}"
    r")$",
    re.IGNORECASE,
)


class MongoState:
    def __init__(self):
        self.cx = None
        self.db = None
        self.db_name = None

    def init_app(self, app: Flask):
        self.cx, self.db, self.db_name = create_mongo_client(app.config["MONGO_URI"])

    def close(self):
        if self.cx is not None:
            self.cx.close()


mongo = MongoState()


def create_mongo_client(mongo_uri: str):
    if not mongo_uri:
        raise RuntimeError("MONGO_URI is required and must point to your MongoDB Atlas cluster.")
    if not mongo_uri.startswith("mongodb+srv://"):
        raise RuntimeError("Atlas connections must use a mongodb+srv:// URI.")

    parsed_uri = urlsplit(mongo_uri)
    database_name = parsed_uri.path.lstrip("/")
    if not database_name:
        raise RuntimeError("Your MONGO_URI must include a database name, for example /multicloud_integrity.")

    try:
        client = MongoClient(
            mongo_uri,
            tls=True,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=20000,
            connectTimeoutMS=20000,
            socketTimeoutMS=20000,
            appname="multicloud-integrity",
        )
        client.admin.command("ping")
        database = client.get_database(database_name)
        collections = database.list_collection_names()
        logger.info("MongoDB Atlas connected db=%s collections=%s", database_name, collections)
        return client, database, database_name
    except (ConfigurationError, ConnectionFailure, ServerSelectionTimeoutError) as exc:
        raise RuntimeError(build_mongo_connection_error(exc)) from exc
    except PyMongoError as exc:
        raise RuntimeError(f"MongoDB connection failed: {exc}") from exc


def build_mongo_connection_error(exc: Exception) -> str:
    message = str(exc)
    atlas_guidance = (
        "Check that your Atlas Network Access list includes your current public IP, "
        "your database user credentials are correct, and outbound TLS traffic to Atlas is not blocked."
    )
    if "resolution lifetime expired" in message.lower() or "dns operation timed out" in message.lower():
        return (
            "MongoDB Atlas SRV DNS lookup failed. Your network could not resolve the mongodb+srv host, "
            "so Atlas shard addresses were never discovered. Check local DNS, firewall, VPN, or proxy settings."
        )
    if "TLSV1_ALERT_INTERNAL_ERROR" in message or "SSL handshake failed" in message:
        return (
            "MongoDB Atlas TLS handshake failed. This usually means the local TLS trust store/OpenSSL "
            "stack could not complete certificate validation or a firewall/proxy interrupted the TLS "
            f"connection. {atlas_guidance}"
        )
    return f"MongoDB connection failed: {message}. {atlas_guidance}"


def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(Config)

    try:
        mongo.init_app(app)
    except RuntimeError:
        logger.exception("Unable to initialize MongoDB Atlas connection")
        raise

    global storage_service
    storage_service = MultiCloudStorage(app)

    ensure_indexes()
    register_routes(app)
    return app


def ensure_indexes():
    mongo.db.users.create_index("username", unique=True)
    mongo.db.files.create_index("filename")
    mongo.db.files.create_index("normalized_filename")
    mongo.db.files.create_index("status")
    mongo.db.deleted_files.create_index("filename")
    mongo.db.deleted_files.create_index("normalized_filename")
    mongo.db.recovery_logs.create_index("timestamp")


def normalize_filename_for_integrity(filename: str) -> str:
    raw_name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    raw_path = Path(raw_name)
    stem = raw_path.stem
    suffix = raw_path.suffix.lower()

    previous = None
    while stem != previous:
        previous = stem
        stem = COPY_SUFFIX_RE.sub("", stem).strip(" ._-")

    normalized = secure_filename(f"{stem}{suffix}")
    if normalized:
        return normalized.lower()

    safe_name = secure_filename(filename or "")
    if not safe_name:
        return ""
    return safe_name.lower()


def find_existing_normalized_file(normalized_filename: str, uploaded_filename: str) -> dict | None:
    uploaded_candidates = {
        normalized_filename,
        normalize_filename_for_integrity(uploaded_filename),
        normalize_filename_for_integrity(secure_filename(uploaded_filename)),
    }
    uploaded_candidates.discard("")

    active_docs = mongo.db.files.find({"deleted": {"$ne": True}}).sort("uploaded_at", 1)
    for doc in active_docs:
        doc_candidates = {
            normalize_filename_for_integrity(doc.get("normalized_filename", "")),
            normalize_filename_for_integrity(doc.get("original_filename", "")),
            normalize_filename_for_integrity(doc.get("filename", "")),
        }
        doc_candidates.discard("")
        if uploaded_candidates.intersection(doc_candidates):
            return doc
    return None


def log_tamper_event(file_doc: dict, uploaded_filename: str, normalized_filename: str, uploaded_hash: str) -> None:
    original_hash = file_doc.get("original_hash", file_doc["sha256_hash"])
    mongo.db.recovery_logs.insert_one(
        {
            "file_id": file_doc["_id"],
            "filename": file_doc.get("filename", uploaded_filename),
            "action": "tamper_detected_on_upload",
            "timestamp": utc_now(),
            "details": {
                "uploaded_filename": uploaded_filename,
                "normalized_filename": normalized_filename,
                "stored_hash": original_hash,
                "uploaded_hash": uploaded_hash,
                "performed_by": current_user(),
            },
        }
    )

def allowed_file(filename: str, app: Flask) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]


def serialize_file(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "filename": doc["filename"],
        "original_filename": doc.get("original_filename", doc["filename"]),
        "latest_uploaded_filename": doc.get("latest_uploaded_filename", doc.get("original_filename", doc["filename"])),
        "normalized_filename": doc.get("normalized_filename", normalize_filename_for_integrity(doc["filename"])),
        "status": doc.get("status", "UNKNOWN"),
        "sha256_hash": doc.get("original_hash", doc["sha256_hash"]),
        "current_hash": doc.get("current_hash"),
        "latest_hash": doc.get("latest_hash"),
        "version_count": doc.get("version_count", 1),
        "content_type": doc.get("content_type"),
        "uploaded_at": doc.get("uploaded_at").isoformat() if doc.get("uploaded_at") else None,
        "last_verified_at": doc.get("last_verified_at").isoformat() if doc.get("last_verified_at") else None,
        "uploaded_by": doc.get("uploaded_by"),
        "cloud_urls": {"primary": None, "backup": None},
        "deleted": doc.get("deleted", False),
    }


def current_user():
    return session.get("user")


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if current_user():
            return view(*args, **kwargs)
        if request.path.startswith("/api/") or request.path.startswith("/verify/"):
            return jsonify({"error": "Authentication required"}), 401
        return redirect(url_for("login"))

    return wrapped_view


def fetch_file_or_404(file_id: str, collection_name: str = "files"):
    if not ObjectId.is_valid(file_id):
        return None
    return mongo.db[collection_name].find_one({"_id": ObjectId(file_id)})


def restore_primary_from_backup(file_doc: dict) -> dict:
    object_key = file_doc["object_name"]
    logger.info("Downloading from backup filename=%s key=%s", file_doc["filename"], file_doc["object_name"])
    backup_content = storage_service.download_from_backup(object_key)
    if backup_content is None:
        raise ValueError("Backup copy is missing.")

    backup_hash = sha256_bytes(backup_content)
    original_hash = file_doc.get("original_hash", file_doc["sha256_hash"])
    if backup_hash != original_hash:
        raise ValueError("Backup copy failed integrity validation.")

    logger.info("Uploading to primary filename=%s key=%s", file_doc["filename"], object_key)
    storage_service.simple_overwrite_primary(
        object_key,
        backup_content,
        file_doc.get("content_type", "application/octet-stream"),
    )
    logger.info("Recovery successful filename=%s", file_doc["filename"])
    return {"backup_hash": backup_hash, "object_key": object_key}


def register_routes(app: Flask):
    @app.route("/")
    def index():
        if current_user():
            return redirect(url_for("dashboard"))
        return redirect(url_for("login"))

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if current_user():
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")

            if not username or not password:
                flash("Username and password are required.", "error")
                return render_template("signup.html", username=username), 400
            if len(username) < 3:
                flash("Username must be at least 3 characters long.", "error")
                return render_template("signup.html", username=username), 400
            if len(password) < 6:
                flash("Password must be at least 6 characters long.", "error")
                return render_template("signup.html", username=username), 400
            if password != confirm_password:
                flash("Passwords do not match.", "error")
                return render_template("signup.html", username=username), 400
            if mongo.db.users.find_one({"username": username}):
                flash("Username already exists. Choose a different one.", "error")
                return render_template("signup.html", username=username), 409

            user_doc = {
                "username": username,
                "password": generate_password_hash(password),
                "created_at": utc_now(),
                "updated_at": utc_now(),
            }
            mongo.db.users.insert_one(user_doc)
            session["user"] = username
            flash("Account created successfully.", "success")
            return redirect(url_for("dashboard"))

        return render_template("signup.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user():
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            user_doc = mongo.db.users.find_one({"username": username})

            if user_doc is None or not check_password_hash(user_doc["password"], password):
                flash("Invalid username or password.", "error")
                return render_template("login.html", username=username), 401

            session.clear()
            session["user"] = username
            flash("Logged in successfully.", "success")
            return redirect(url_for("dashboard"))

        return render_template("login.html")

    @app.post("/logout")
    @login_required
    def logout():
        session.clear()
        flash("Logged out successfully.", "success")
        return redirect(url_for("login"))

    @app.get("/dashboard")
    @login_required
    def dashboard():
        return render_template("dashboard.html", username=current_user())

    @app.get("/integrity")
    @login_required
    def integrity():
        return render_template("integrity.html", username=current_user())

    @app.get("/recovery")
    @login_required
    def recovery():
        return render_template("recovery.html", username=current_user())

    @app.get("/storage")
    @login_required
    def storage():
        return render_template("storage.html", username=current_user())

    @app.get("/api/me")
    def me():
        return jsonify(
            {
                "authenticated": bool(current_user()),
                "username": current_user(),
            }
        )

    @app.post("/api/upload")
    @login_required
    def upload_file():
        file = request.files.get("file")
        if file is None or file.filename == "":
            return jsonify({"error": "File is required"}), 400

        filename = secure_filename(file.filename)
        if not filename or not allowed_file(filename, app):
            return jsonify({"error": "File type is not allowed"}), 400

        content = file.read()
        if not content:
            return jsonify({"error": "Uploaded file is empty"}), 400

        content_type = file.mimetype or "application/octet-stream"
        file_hash = sha256_bytes(content)
        normalized_filename = normalize_filename_for_integrity(file.filename)
        logger.info(
            "upload start filename=%s normalized=%s user=%s size=%s",
            filename,
            normalized_filename,
            current_user(),
            len(content),
        )
        existing_doc = find_existing_normalized_file(normalized_filename, filename)

        if existing_doc:
            original_hash = existing_doc.get("original_hash", existing_doc["sha256_hash"])
            new_status = "SAFE" if file_hash == original_hash else "TAMPERED"
            logger.warning(
                "TAMPER DEBUG upload filename=%s normalized=%s old_hash=%s new_hash=%s decision=%s matched_id=%s",
                filename,
                normalized_filename,
                original_hash,
                file_hash,
                new_status,
                existing_doc["_id"],
            )
            logger.warning(
                "existing normalized filename upload detected filename=%s normalized=%s id=%s",
                filename,
                normalized_filename,
                existing_doc["_id"],
            )
            try:
                storage_service.overwrite_primary(existing_doc["object_name"], content, content_type)
            except Exception as exc:
                logger.exception("replacement upload failed filename=%s user=%s error=%s", filename, current_user(), exc)
                return jsonify({"error": f"Upload failed: {exc}"}), 500

            now = utc_now()
            mongo.db.files.update_one(
                {"_id": existing_doc["_id"]},
                {
                    "$set": {
                        "original_filename": existing_doc.get("original_filename", existing_doc["filename"]),
                        "latest_uploaded_filename": filename,
                        "normalized_filename": normalized_filename,
                        "content_type": content_type,
                        "current_hash": file_hash,
                        "latest_hash": file_hash,
                        "status": new_status,
                        "updated_at": now,
                        "uploaded_at": now,
                        "uploaded_by": current_user(),
                    },
                    "$inc": {"version_count": 1},
                },
            )
            if new_status == "TAMPERED":
                log_tamper_event(existing_doc, filename, normalized_filename, file_hash)
            updated_doc = fetch_file_or_404(str(existing_doc["_id"]))
            message = (
                "Tampering detected: uploaded content does not match the trusted SHA-256 hash."
                if new_status == "TAMPERED"
                else "Existing file checked against trusted SHA-256 hash and marked safe."
            )
            return (
                jsonify(
                    {
                        "message": message,
                        "file": serialize_file(updated_doc),
                    }
                ),
                200,
            )

        logger.warning(
            "TAMPER DEBUG upload filename=%s normalized=%s old_hash=%s new_hash=%s decision=%s matched_id=%s",
            filename,
            normalized_filename,
            None,
            file_hash,
            "NEW_FILE",
            None,
        )
        try:
            storage_result = storage_service.upload_to_both(filename, content, content_type)
        except Exception as exc:
            logger.exception("upload failed filename=%s user=%s error=%s", filename, current_user(), exc)
            return jsonify({"error": f"Upload failed: {exc}"}), 500

        document = {
            "filename": filename,
            "original_filename": filename,
            "latest_uploaded_filename": filename,
            "normalized_filename": normalized_filename,
            "object_name": storage_result["object_name"],
            "sha256_hash": file_hash,
            "original_hash": file_hash,
            "current_hash": file_hash,
            "latest_hash": file_hash,
            "version_count": 1,
            "uploaded_at": utc_now(),
            "updated_at": utc_now(),
            "last_verified_at": None,
            "status": "SAFE",
            "content_type": content_type,
            "uploaded_by": current_user(),
            "deleted": False,
        }
        try:
            inserted = mongo.db.files.insert_one(document)
        except Exception as exc:
            logger.exception("metadata save failed filename=%s error=%s", filename, exc)
            return jsonify({"error": f"Metadata save failed: {exc}"}), 500
        document["_id"] = inserted.inserted_id
        return jsonify({"message": "File uploaded successfully", "file": serialize_file(document)}), 201

    @app.get("/api/files")
    @login_required
    def list_files():
        files = [serialize_file(doc) for doc in mongo.db.files.find().sort("uploaded_at", -1)]
        deleted = [serialize_file(doc) for doc in mongo.db.deleted_files.find().sort("deleted_at", -1)]
        return jsonify({"files": files, "deleted_files": deleted})

    @app.get("/api/view/<file_id>/<location>")
    @login_required
    def view_file(file_id, location):
        file_doc = fetch_file_or_404(file_id) or fetch_file_or_404(file_id, "deleted_files")
        if not file_doc:
            return jsonify({"error": "File not found"}), 404

        if location == "primary":
            bucket_name = storage_service.primary_bucket
        elif location == "backup":
            bucket_name = storage_service.backup_bucket
        else:
            return jsonify({"error": "Invalid location"}), 400

        try:
            url = storage_service.generate_download_url(bucket_name, file_doc["object_name"])
        except Exception as exc:
            logger.exception("view url generation failed filename=%s location=%s error=%s", file_doc["filename"], location, exc)
            return jsonify({"error": f"View unavailable: {exc}"}), 500

        return jsonify({"url": url})

    @app.get("/api/download/<file_id>")
    @login_required
    def download_file(file_id):
        file_doc = fetch_file_or_404(file_id)
        if not file_doc:
            return jsonify({"error": "File not found"}), 404

        try:
            url = storage_service.generate_download_url(
                storage_service.primary_bucket,
                file_doc["object_name"],
                filename=file_doc["filename"],
                as_attachment=True,
            )
        except Exception as exc:
            logger.exception("download url generation failed filename=%s error=%s", file_doc["filename"], exc)
            return jsonify({"error": f"Download unavailable: {exc}"}), 500

        return jsonify({"url": url, "filename": file_doc["filename"]})

    @app.get("/api/verify/<file_id>")
    @login_required
    def verify_file(file_id):
        file_doc = fetch_file_or_404(file_id)
        if not file_doc:
            return jsonify({"error": "File not found"}), 404

        result = verify_and_heal(file_doc, storage_service, mongo.db)
        latest_doc = fetch_file_or_404(file_id)
        return jsonify({"file": serialize_file(latest_doc), "verification": result})

    @app.get("/verify/<file_id>")
    @login_required
    def verify_file_compat(file_id):
        return verify_file(file_id)

    @app.post("/api/delete/<file_id>")
    @login_required
    def delete_file(file_id):
        file_doc = fetch_file_or_404(file_id)
        if not file_doc:
            return jsonify({"error": "File not found"}), 404

        try:
            logger.info("delete start filename=%s key=%s", file_doc["filename"], file_doc["object_name"])
            storage_service.delete_from_bucket(storage_service.primary_bucket, file_doc["object_name"])
        except Exception as exc:
            logger.exception("primary delete failed filename=%s error=%s", file_doc["filename"], exc)
            return jsonify({"error": f"Primary delete failed: {exc}"}), 500

        delete_payload = dict(file_doc)
        delete_payload["deleted"] = True
        delete_payload["status"] = "DELETED"
        delete_payload["deleted_at"] = utc_now()
        delete_payload["deleted_by"] = current_user()
        mongo.db.deleted_files.insert_one(delete_payload)
        mongo.db.files.delete_one({"_id": file_doc["_id"]})
        return jsonify({"message": "Primary file deleted and metadata moved to deleted files"})

    @app.post("/api/files/<file_id>")
    @login_required
    def delete_file_compat(file_id):
        return delete_file(file_id)

    @app.post("/api/recover/<file_id>")
    @login_required
    def recover_file(file_id):
        active_doc = fetch_file_or_404(file_id)
        if active_doc:
            try:
                recovery_details = restore_primary_from_backup(active_doc)
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 409
            except Exception as exc:
                logger.exception("active recovery failed filename=%s error=%s", active_doc["filename"], exc)
                return jsonify({"error": f"Recovery failed: {exc}"}), 500

            mongo.db.files.update_one(
                {"_id": active_doc["_id"]},
                {
                    "$set": {
                        "status": "SAFE",
                        "updated_at": utc_now(),
                        "last_verified_at": utc_now(),
                        "primary_hash": active_doc.get("original_hash", active_doc["sha256_hash"]),
                        "backup_hash": recovery_details["backup_hash"],
                        "current_hash": active_doc.get("original_hash", active_doc["sha256_hash"]),
                        "latest_hash": active_doc.get("original_hash", active_doc["sha256_hash"]),
                        "deleted": False,
                        "deleted_at": None,
                        "recovered_at": utc_now(),
                        "recovered_by": current_user(),
                    }
                },
            )
            mongo.db.recovery_logs.insert_one(
                {
                    "file_id": active_doc["_id"],
                    "filename": active_doc["filename"],
                    "action": "primary_restored_from_backup_manual",
                    "timestamp": utc_now(),
                    "details": {"performed_by": current_user()},
                }
            )
            return jsonify({"message": "Recovery successful. File restored to active files.", "status": "SAFE"})

        file_doc = fetch_file_or_404(file_id, "deleted_files")
        if not file_doc:
            return jsonify({"error": "Deleted file not found"}), 404
        if mongo.db.files.find_one({"_id": file_doc["_id"]}):
            return jsonify({"error": "File already exists in active collection"}), 409

        try:
            recovery_details = restore_primary_from_backup(file_doc)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 409
        except Exception as exc:
            logger.exception("deleted recovery failed filename=%s error=%s", file_doc["filename"], exc)
            return jsonify({"error": f"Recovery failed: {exc}"}), 500

        restore_payload = dict(file_doc)
        restore_payload["deleted"] = False
        restore_payload["status"] = "SAFE"
        restore_payload["updated_at"] = utc_now()
        restore_payload["last_verified_at"] = utc_now()
        restore_payload["primary_hash"] = file_doc.get("original_hash", file_doc["sha256_hash"])
        restore_payload["backup_hash"] = recovery_details["backup_hash"]
        restore_payload["current_hash"] = file_doc.get("original_hash", file_doc["sha256_hash"])
        restore_payload["latest_hash"] = file_doc.get("original_hash", file_doc["sha256_hash"])
        restore_payload["deleted_at"] = None
        restore_payload["recovered_at"] = utc_now()
        restore_payload["recovered_by"] = current_user()
        restore_payload.pop("deleted_at", None)
        restore_payload.pop("deleted_by", None)

        try:
            mongo.db.files.insert_one(restore_payload)
            mongo.db.deleted_files.delete_one({"_id": file_doc["_id"]})
        except Exception as exc:
            logger.exception("recovery metadata move failed filename=%s error=%s", file_doc["filename"], exc)
            return jsonify({"error": f"Recovery failed: {exc}"}), 500
        mongo.db.recovery_logs.insert_one(
            {
                "file_id": file_doc["_id"],
                "filename": file_doc["filename"],
                "action": "metadata_restored_from_deleted_collection",
                "timestamp": utc_now(),
                "details": {"performed_by": current_user()},
            }
        )
        return jsonify({"message": "Recovery successful. File moved back to Active Files.", "status": "SAFE"})

    @app.get("/api/recovery-logs")
    @login_required
    def recovery_logs():
        logs = []
        for log in mongo.db.recovery_logs.find().sort("timestamp", -1).limit(50):
            logs.append(
                {
                    "file_id": str(log["file_id"]),
                    "filename": log["filename"],
                    "action": log["action"],
                    "timestamp": log["timestamp"].isoformat(),
                    "details": log.get("details", {}),
                }
            )
        return jsonify({"logs": logs})


atexit.register(mongo.close)


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
