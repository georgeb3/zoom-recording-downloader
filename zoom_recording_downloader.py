#!/usr/bin/env python3
import os
import re
import json
import time
import pathlib
import datetime as dt
from typing import Callable
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import requests

ZOOM_TOKEN_URL = "https://zoom.us/oauth/token"
ZOOM_API_BASE = "https://api.zoom.us/v2"

def env(name: str, default: str | None = None) -> str:
    v = os.environ.get(name, default)
    if not v:
        raise SystemExit(f"Missing required env var: {name}")
    return v

def sanitize(s: str, max_len: int = 120) -> str:
    s = (s or "").strip()
    s = re.sub(r"[^\w\-\.\(\)\s]+", "", s)
    s = re.sub(r"\s+", " ", s)
    return s[:max_len].strip() or "untitled"

def get_s2s_access_token(account_id: str, client_id: str, client_secret: str) -> str:
    # Server-to-Server OAuth: grant_type=account_credentials&account_id=...
    # Uses Basic Auth with client_id/client_secret
    # Request required scopes for cloud recording access
    params = {
        "grant_type": "account_credentials",
        "account_id": account_id,
    }
    # Explicitly request the required scopes (must be enabled in Zoom app settings)
    scope = "cloud_recording:read:list_user_recordings cloud_recording:read:list_user_recordings:admin"
    params["scope"] = scope
    
    resp = requests.post(
        ZOOM_TOKEN_URL,
        params=params,
        auth=(client_id, client_secret),
        timeout=30,
    )
    if resp.status_code != 200:
        raise SystemExit(f"Token error {resp.status_code}: {resp.text}")
    return resp.json()["access_token"]

def zoom_get(path: str, token_container: dict, params: dict | None = None, refresh_token_callback: Callable[[], str] | None = None) -> dict:
    """
    Make a GET request to Zoom API with automatic token refresh on expiration.
    
    Args:
        path: API endpoint path
        token_container: Dict with 'token' key holding the current access token (will be updated if refreshed)
        params: Optional query parameters
        refresh_token_callback: Optional callback function that returns a new token when called
    """
    token = token_container["token"]
    resp = requests.get(
        f"{ZOOM_API_BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params or {},
        timeout=60,
    )
    
    # Check for token expiration (401 with code 124)
    if resp.status_code == 401:
        try:
            error_data = resp.json()
            if error_data.get("code") == 124 and refresh_token_callback:
                # Token expired, refresh and retry
                print("Access token expired, refreshing...")
                new_token = refresh_token_callback()
                token_container["token"] = new_token  # Update the token container
                # Retry the request with new token
                resp = requests.get(
                    f"{ZOOM_API_BASE}{path}",
                    headers={"Authorization": f"Bearer {new_token}"},
                    params=params or {},
                    timeout=60,
                )
                if resp.status_code != 200:
                    raise SystemExit(f"Zoom API error {resp.status_code} for {path} (after token refresh): {resp.text}")
                return resp.json()
        except (json.JSONDecodeError, KeyError):
            pass  # Not a token expiration error, fall through to normal error handling
    
    if resp.status_code != 200:
        raise SystemExit(f"Zoom API error {resp.status_code} for {path}: {resp.text}")
    return resp.json()

def add_access_token_to_download_url(download_url: str, token: str) -> str:
    """
    Zoom cloud recording downloads may require adding `access_token` to the download_url
    to access protected recordings.  [oai_citation:2‡Harvard APIs Portal](https://portal.apis.huit.harvard.edu/docs/ccs-zoom-api/1/routes/users/%7BuserId%7D/recordings/get?utm_source=chatgpt.com)
    """
    u = urlparse(download_url)
    q = parse_qs(u.query)
    q["access_token"] = [token]
    new_query = urlencode(q, doseq=True)
    return urlunparse((u.scheme, u.netloc, u.path, u.params, new_query, u.fragment))

def stream_download(url: str, out_path: pathlib.Path, token_container: dict | None = None, refresh_token_callback: Callable[[], str] | None = None) -> None:
    """
    Download a file from URL with automatic token refresh on expiration.
    
    Args:
        url: Download URL (may contain access_token parameter)
        out_path: Local path to save the file
        token_container: Optional dict with 'token' key (will be updated if refreshed)
        refresh_token_callback: Optional callback function that returns a new token when called
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".part")

    max_retries = 2
    current_url = url
    for attempt in range(max_retries):
        try:
            with requests.get(current_url, stream=True, timeout=120) as r:
                # Check for token expiration (401)
                if r.status_code == 401 and token_container and refresh_token_callback and attempt < max_retries - 1:
                    print("  Download token expired, refreshing...")
                    new_token = refresh_token_callback()
                    token_container["token"] = new_token
                    # Rebuild URL with new token - extract base URL and add new token
                    u = urlparse(current_url)
                    q = parse_qs(u.query)
                    q["access_token"] = [new_token]  # Update or add access_token
                    new_query = urlencode(q, doseq=True)
                    current_url = urlunparse((u.scheme, u.netloc, u.path, u.params, new_query, u.fragment))
                    continue  # Retry with new token
                
                r.raise_for_status()
                with open(tmp_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
                break  # Success
        except requests.exceptions.HTTPError as e:
            if e.response and e.response.status_code == 401 and token_container and refresh_token_callback and attempt < max_retries - 1:
                # Token expired, refresh and retry
                print("  Download token expired, refreshing...")
                new_token = refresh_token_callback()
                token_container["token"] = new_token
                # Rebuild URL with new token
                u = urlparse(current_url)
                q = parse_qs(u.query)
                q["access_token"] = [new_token]
                new_query = urlencode(q, doseq=True)
                current_url = urlunparse((u.scheme, u.netloc, u.path, u.params, new_query, u.fragment))
                continue
            raise

    tmp_path.replace(out_path)

def load_manifest(root: pathlib.Path) -> dict:
    p = root / "manifest.json"
    if p.exists():
        return json.loads(p.read_text("utf-8"))
    return {"downloaded": {}}

def save_manifest(root: pathlib.Path, manifest: dict) -> None:
    p = root / "manifest.json"
    p.write_text(json.dumps(manifest, indent=2, sort_keys=True), "utf-8")

def month_windows_back(months_back: int) -> list[tuple[str, str]]:
    """
    Builds month-sized (from,to) windows going back N months.
    Some Zoom recording listing behaviors historically work best in smaller windows.  [oai_citation:3‡Zoom Developer Forum](https://devforum.zoom.us/t/retrieve-all-past-zoom-cloud-recordings/22487?utm_source=chatgpt.com)
    """
    today = dt.date.today()
    first_of_this_month = today.replace(day=1)
    windows = []

    cur = first_of_this_month
    for _ in range(months_back):
        prev_month_end = cur - dt.timedelta(days=1)
        prev_month_start = prev_month_end.replace(day=1)
        windows.append((prev_month_start.isoformat(), prev_month_end.isoformat()))
        cur = prev_month_start

    # include current month-to-date as a final window
    windows.insert(0, (first_of_this_month.isoformat(), today.isoformat()))
    return windows

def list_user_recordings(user_id: str, token_container: dict, from_date: str, to_date: str, refresh_token_callback: Callable[[], str] | None = None) -> list[dict]:
    # GET /users/{userId}/recordings
    # Returns meetings array with recording_files inside each meeting.  [oai_citation:4‡Harvard APIs Portal](https://portal.apis.huit.harvard.edu/docs/ccs-zoom-api/1/routes/users/%7BuserId%7D/recordings/get?utm_source=chatgpt.com)
    meetings = []
    next_token = None

    while True:
        params = {
            "from": from_date,
            "to": to_date,
            "page_size": 300,
        }
        if next_token:
            params["next_page_token"] = next_token

        data = zoom_get(f"/users/{user_id}/recordings", token_container, params=params, refresh_token_callback=refresh_token_callback)
        meetings.extend(data.get("meetings", []))
        next_token = data.get("next_page_token")
        if not next_token:
            break

    return meetings

def main():
    # === REQUIRED ENV VARS ===
    account_id = env("ZOOM_ACCOUNT_ID")
    client_id = env("ZOOM_CLIENT_ID")
    client_secret = env("ZOOM_CLIENT_SECRET")
    out_dir = pathlib.Path(env("ZOOM_OUT_DIR")).expanduser().resolve()

    # user_id can be: "me" (common for Server-to-Server OAuth), a Zoom userId, or an email depending on your setup
    user_id = os.environ.get("ZOOM_USER_ID", "me")

    # How far back to pull (months)
    months_back = int(os.environ.get("ZOOM_MONTHS_BACK", "24"))

    print("Getting access token...")
    access_token = get_s2s_access_token(account_id, client_id, client_secret)
    
    # Create token container for refreshable token management
    token_container = {"token": access_token}
    
    # Create token refresh callback function
    def refresh_token():
        """Refresh the access token and update the container."""
        new_token = get_s2s_access_token(account_id, client_id, client_secret)
        token_container["token"] = new_token
        return new_token

    manifest = load_manifest(out_dir)

    windows = month_windows_back(months_back)
    total_files = 0
    downloaded = 0

    for (from_date, to_date) in windows:
        print(f"\nListing recordings for {user_id} from {from_date} to {to_date} ...")
        meetings = list_user_recordings(user_id, token_container, from_date, to_date, refresh_token_callback=refresh_token)
        print(f"Found {len(meetings)} meetings in this window.")

        for m in meetings:
            topic = sanitize(m.get("topic", "untitled"))
            start_time = m.get("start_time") or "unknown_start"
            start_time_safe = sanitize(start_time.replace(":", "-"))
            meeting_id = str(m.get("uuid") or m.get("id") or "unknown_meeting")

            base = out_dir / f"{start_time_safe} - {topic}" / sanitize(meeting_id, 80)

            for rf in m.get("recording_files", []) or []:
                total_files += 1
                file_id = rf.get("id") or rf.get("recording_end") or rf.get("file_type") or str(total_files)
                file_type = (rf.get("file_type") or "FILE").upper()
                ext = (rf.get("file_extension") or "").lower()

                # Some types come without extension; give helpful defaults
                if not ext:
                    ext = {
                        "MP4": "mp4",
                        "M4A": "m4a",
                        "CHAT": "txt",
                        "VTT": "vtt",
                        "TRANSCRIPT": "vtt",
                    }.get(file_type, "bin")

                download_url = rf.get("download_url")
                if not download_url:
                    continue

                out_name = f"{file_type}.{ext}"
                out_path = base / out_name

                key = f"{meeting_id}:{file_id}:{out_name}"
                if manifest["downloaded"].get(key):
                    continue

                # Add access_token to download_url for protected recordings  [oai_citation:5‡Harvard APIs Portal](https://portal.apis.huit.harvard.edu/docs/ccs-zoom-api/1/routes/users/%7BuserId%7D/recordings/get?utm_source=chatgpt.com)
                # Use current token from container (may be refreshed during execution)
                final_url = add_access_token_to_download_url(download_url, token_container["token"])

                print(f"Downloading {out_name} -> {out_path}")
                try:
                    stream_download(final_url, out_path, token_container=token_container, refresh_token_callback=refresh_token)
                except Exception as e:
                    print(f"  !! Failed: {e}")
                    continue

                manifest["downloaded"][key] = {
                    "saved_to": str(out_path),
                    "downloaded_at": dt.datetime.utcnow().isoformat() + "Z",
                    "from": from_date,
                    "to": to_date,
                }
                downloaded += 1

                # polite pacing (avoid tripping rate limits too fast)
                time.sleep(0.2)

        save_manifest(out_dir, manifest)

    print(f"\nDone. Files seen: {total_files}, newly downloaded: {downloaded}")
    print(f"Output folder: {out_dir}")

if __name__ == "__main__":
    main()