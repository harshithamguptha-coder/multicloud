# Secure Multi-Cloud Data Integrity and Self-Healing Storage System

Production-style Flask application that stores every uploaded file in two Backblaze B2 buckets, tracks a trusted SHA-256 hash in MongoDB, verifies integrity, auto-recovers the primary copy from the backup bucket when needed, and authenticates real users with hashed passwords stored in MongoDB.

## Folder Structure

```text
cloud final/
|-- app.py
|-- config.py
|-- requirements.txt
|-- .env.example
|-- services/
|   |-- integrity.py
|   `-- storage.py
|-- static/
|   |-- css/
|   |   `-- styles.css
|   `-- js/
|       `-- app.js
`-- templates/
    |-- dashboard.html
    |-- login.html
    `-- signup.html
```

## Features

- Upload files from the dashboard to both Backblaze B2 buckets
- Compute and store SHA-256 hash plus metadata in MongoDB
- Register and log in users with Flask sessions and hashed passwords
- Verify integrity through `/verify/<file_id>`
- Automatically restore the damaged primary copy from the backup bucket
- Record recovery logs in MongoDB
- Soft-delete metadata to a dedicated `deleted_files` collection
- Recover deleted file metadata while keeping cloud-backed content restorable
- Run integrity checks every 60 seconds with APScheduler
- Protect dashboard and storage actions with authenticated Flask sessions

## Prerequisites

- Python 3.11+
- MongoDB running locally or remotely
- Two Backblaze B2 buckets with S3-compatible app keys

## Setup

1. Create a virtual environment and install dependencies:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and fill in real values.

3. Start MongoDB and ensure `MONGO_URI` points to the target database.

4. Run the Flask app:

```powershell
python app.py
```

5. Open `http://127.0.0.1:5000`.
6. Create an account on `/signup`, then log in and use `/dashboard`.

## Backblaze B2 Configuration

1. Create a Backblaze B2 account.
2. Create two buckets:
   - one primary bucket
   - one backup bucket
3. Create an application key that can access both buckets.
4. Copy these values into `.env`:
   - `S3_ACCESS_KEY_ID`: your Backblaze key ID
   - `S3_SECRET_ACCESS_KEY`: your Backblaze application key
   - `S3_REGION`: the B2 region code, for example `us-east-005`
   - `S3_BUCKET_PRIMARY`: your primary bucket name
   - `S3_BUCKET_BACKUP`: your backup bucket name
   - `S3_ENDPOINT_URL`: for example `https://s3.us-east-005.backblazeb2.com`
   - `S3_PUBLIC_BASE_URL_PRIMARY`: for example `https://f005.backblazeb2.com/file/your-primary-bucket`
   - `S3_PUBLIC_BASE_URL_BACKUP`: for example `https://f005.backblazeb2.com/file/your-backup-bucket`

The Flask code uses Backblaze's S3-compatible API through `boto3`, so uploads, downloads, verification, and recovery all use real B2 storage.

## Example `.env`

```env
FLASK_SECRET_KEY=replace-with-a-random-secret
MONGO_URI=mongodb://localhost:27017/multicloud_integrity
S3_ACCESS_KEY_ID=005abc1234567890000000001
S3_SECRET_ACCESS_KEY=K001exampleBackblazeSecretKey
S3_REGION=us-east-005
S3_BUCKET_PRIMARY=my-integrity-primary
S3_BUCKET_BACKUP=my-integrity-backup
S3_ENDPOINT_URL=https://s3.us-east-005.backblazeb2.com
S3_PUBLIC_BASE_URL_PRIMARY=https://f005.backblazeb2.com/file/my-integrity-primary
S3_PUBLIC_BASE_URL_BACKUP=https://f005.backblazeb2.com/file/my-integrity-backup
```

## Authentication

- `GET/POST /signup` stores a new user in the `users` collection
- Passwords are hashed with Werkzeug before saving
- `GET/POST /login` verifies the hashed password and starts a Flask session
- `POST /logout` clears the current session
- Upload, verify, delete, recover, and dashboard routes require login

## API Summary

- `GET /login`
- `GET /signup`
- `GET /dashboard`
- `GET /api/me`
- `POST /api/upload`
- `GET /api/files`
- `GET /verify/<file_id>`
- `DELETE /api/files/<file_id>`
- `POST /api/recover/<file_id>`
- `GET /api/recovery-logs`

## MongoDB Collections

- `files`
- `users`
- `deleted_files`
- `recovery_logs`

## Notes

- Integrity verification uses SHA-256 only; it does not compare plaintext bodies directly.
- Auto-recovery succeeds only when either the primary or backup bucket still matches the stored trusted hash.
- If both bucket copies are corrupted or missing, the system marks the file as `TAMPERED`.
- Backblaze B2 is used through the official S3-compatible endpoint with `boto3`.
