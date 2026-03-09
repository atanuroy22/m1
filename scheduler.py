"""
Auto-publish scheduler for LinkedIn posts
Run via Windows Task Scheduler or as background thread
"""

import json
import os
import requests
import mimetypes
from datetime import datetime
import time

def _load_env_file():
    # Load .env file
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                if "=" not in s:
                    continue
                key, val = s.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and val:
                    os.environ.setdefault(key, val)
    except Exception:
        # Fall back to process env
        pass

_load_env_file()


def _parse_scheduled_datetime(value: str):
    # Parse YYYY-MM-DD HH:MM:SS format
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except Exception:
        pass

    # Common ISO inputs (UTC Z or offset) coming from integrations
    try:
        # Handle Z format
        iso = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        # If timezone-aware, convert to local naive
        if dt.tzinfo is not None:
            return dt.astimezone().replace(tzinfo=None)
        return dt
    except Exception:
        return None

def start_scheduler_background(interval_seconds: int | None = None):
    """Start the auto-publish loop in a background thread.
    Use when importing from a running app (e.g., Streamlit) so it checks
    `published_log.json` periodically without Windows Task Scheduler.
    """
    try:
        import threading
        interval = interval_seconds or int(os.getenv("SCHEDULER_INTERVAL_SECONDS", "20"))

        def _loop():
            while True:
                try:
                    count = auto_publish_scheduled_posts()
                    # Optional lightweight logging only when something happened
                    if count and os.getenv("SCHEDULER_LOG_ENABLED", "false").lower() in ("1", "true", "yes"):
                        try:
                            with open(os.path.join(os.path.dirname(__file__), ".scheduler_log.txt"), "a", encoding="utf-8") as f:
                                f.write(f"{datetime.now()}: Published {count} post(s)\n")
                        except Exception:
                            pass
                except Exception:
                    pass
                time.sleep(interval)

        t = threading.Thread(target=_loop, daemon=True)
        t.start()
        return t
    except Exception:
        return None

def auto_publish_scheduled_posts():
    base_dir = os.path.dirname(__file__)

    def _load_json(path_value):
        if not os.path.exists(path_value):
            return {}
        try:
            with open(path_value, "r") as f:
                data = json.load(f) or {}
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _load_json_list(path_value):
        if not os.path.exists(path_value):
            return []
        try:
            with open(path_value, "r") as f:
                data = json.load(f) or []
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _write_json_list(path_value, items):
        try:
            with open(path_value, "w") as f:
                json.dump(items or [], f, indent=4)
            return True
        except Exception:
            return False

    legacy_log = os.path.join(base_dir, "published_log.json")
    split_logs = {
        "LinkedIn": os.path.join(base_dir, "published_log_linkedin.json"),
        "Facebook": os.path.join(base_dir, "published_log_facebook.json"),
        "Instagram": os.path.join(base_dir, "published_log_instagram.json"),
    }

    if os.path.exists(legacy_log):
        if not any(os.path.exists(p) for p in split_logs.values()):
            legacy_items = _load_json_list(legacy_log)
            grouped = {"LinkedIn": [], "Facebook": [], "Instagram": []}
            for item in legacy_items:
                if not isinstance(item, dict):
                    continue
                p = item.get("platform") or "LinkedIn"
                if p not in grouped:
                    p = "LinkedIn"
                grouped[p].append(item)
            for p, items in grouped.items():
                if items and not os.path.exists(split_logs[p]):
                    _write_json_list(split_logs[p], items)

    linkedin_creds = _load_json(os.path.join(base_dir, ".linkedin_credentials.json"))
    facebook_creds = _load_json(os.path.join(base_dir, ".facebook_credentials.json"))
    instagram_creds = _load_json(os.path.join(base_dir, ".instagram_credentials.json"))

    linkedin_token = os.getenv("LINKEDIN_ACCESS_TOKEN") or linkedin_creds.get("access_token", "")
    linkedin_member_id = os.getenv("LINKEDIN_MEMBER_ID") or linkedin_creds.get("member_id", "")

    facebook_token = os.getenv("FACEBOOK_ACCESS_TOKEN") or facebook_creds.get("access_token", "")
    facebook_page_id = os.getenv("FACEBOOK_PAGE_ID") or facebook_creds.get("page_id", "")

    instagram_token = os.getenv("INSTAGRAM_ACCESS_TOKEN") or instagram_creds.get("access_token", "")
    instagram_user_id = os.getenv("INSTAGRAM_USER_ID") or instagram_creds.get("user_id", "")
    instagram_facebook_page_id = os.getenv("INSTAGRAM_FACEBOOK_PAGE_ID") or instagram_creds.get("facebook_page_id", "")

    published_count = 0
    current_time = datetime.now()

    for platform_name in ("LinkedIn", "Facebook", "Instagram"):
        log_file = split_logs.get(platform_name)
        if not log_file or not os.path.exists(log_file):
            continue

        data = _load_json_list(log_file)
        if not data:
            continue

        updated = False
        for post in data:
            if not isinstance(post, dict):
                continue
            if post.get("status") != "Scheduled":
                continue
            scheduled_for = post.get("scheduled_for")
            if not scheduled_for:
                continue

            try:
                scheduled_time = _parse_scheduled_datetime(scheduled_for)
                if not scheduled_time:
                    post["status"] = "Error: Invalid scheduled time"
                    updated = True
                    continue

                if current_time < scheduled_time:
                    continue

                content = post.get("content", "") or ""
                image_path = post.get("image_path")
                video_path = post.get("video_path")
                image_bytes = _load_file_bytes(image_path)
                video_bytes = _load_file_bytes(video_path)

                if platform_name == "LinkedIn":
                    if not linkedin_token or not linkedin_member_id:
                        post["status"] = "Error: Missing LinkedIn credentials"
                        updated = True
                        continue

                    if video_bytes:
                        success, message = publish_to_linkedin_with_video(content, video_bytes, linkedin_token, linkedin_member_id)
                    elif image_bytes:
                        success, message = publish_to_linkedin_with_image(content, image_bytes, linkedin_token, linkedin_member_id, image_path=image_path)
                    else:
                        success, message = publish_to_linkedin(content, linkedin_token, linkedin_member_id)

                elif platform_name == "Facebook":
                    if not facebook_token or not facebook_page_id:
                        post["status"] = "Error: Missing Facebook credentials"
                        updated = True
                        continue

                    if video_bytes:
                        success, message = publish_to_facebook_with_video(content, video_bytes, facebook_token, facebook_page_id)
                    elif image_bytes:
                        success, message = publish_to_facebook_with_image(content, image_bytes, facebook_token, facebook_page_id)
                    else:
                        success, message = publish_to_facebook(content, facebook_token, facebook_page_id)

                else:
                    if not instagram_token or not instagram_user_id:
                        post["status"] = "Error: Missing Instagram credentials"
                        updated = True
                        continue

                    success, message = publish_to_instagram(
                        content,
                        instagram_token,
                        instagram_user_id,
                        image_bytes=image_bytes,
                        video_bytes=video_bytes,
                        facebook_access_token=instagram_token,
                        facebook_page_id=instagram_facebook_page_id,
                    )

                if success:
                    post["status"] = "Published"
                    post["published_at"] = current_time.strftime("%Y-%m-%d %H:%M:%S")
                    published_count += 1
                else:
                    post["status"] = f"Error: {message}"
                updated = True

            except Exception as e:
                post["status"] = f"Error: {str(e)}"
                updated = True

        if updated:
            _write_json_list(log_file, data)

    return published_count


def _format_author_urn(member_id):
    if "urn:" in str(member_id):
        return member_id
    return f"urn:li:person:{member_id}"


def _load_file_bytes(path_value):
    if not path_value:
        return None
    if not os.path.exists(path_value):
        return None
    try:
        with open(path_value, "rb") as f:
            return f.read()
    except Exception:
        return None


def publish_to_linkedin(content, access_token, member_id):
    try:
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
            'X-Restli-Protocol-Version': '2.0.0'
        }
        
        author_urn = _format_author_urn(member_id)
        
        payload = {
            "author": author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {
                        "text": content
                    },
                    "shareMediaCategory": "NONE"
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            }
        }
        
        response = requests.post(
            "https://api.linkedin.com/v2/ugcPosts",
            headers=headers,
            json=payload
        )
        
        if response.status_code in [201, 200]:
            return True, "Published to LinkedIn successfully"
        return False, f"Publish Failed (HTTP {response.status_code}): {response.text}"
    except Exception as e:
        return False, f"API Error: {str(e)}"


def publish_to_linkedin_with_image(content, image_bytes, access_token, member_id, image_path=None):
    try:
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
            'X-Restli-Protocol-Version': '2.0.0'
        }
        
        author_urn = _format_author_urn(member_id)
        
        upload_url = "https://api.linkedin.com/v2/assets?action=registerUpload"
        upload_payload = {
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "owner": author_urn,
                "serviceRelationships": [
                    {
                        "relationshipType": "OWNER",
                        "identifier": "urn:li:userGeneratedContent"
                    }
                ]
            }
        }
        
        upload_response = requests.post(upload_url, headers=headers, json=upload_payload)
        
        if upload_response.status_code not in [200, 201]:
            return False, f"Image upload registration failed (HTTP {upload_response.status_code}): {upload_response.text}"
        
        upload_data = upload_response.json()
        upload_url_actual = upload_data.get('value', {}).get('uploadMechanism', {}).get('com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest', {}).get('uploadUrl')
        asset_urn = upload_data.get('value', {}).get('asset')
        
        if not upload_url_actual or not asset_urn:
            return False, f"Invalid upload response: {upload_response.text}"
        
        content_type = "image/png"
        if image_path:
            guessed = mimetypes.guess_type(image_path)[0]
            if guessed:
                content_type = guessed
        
        image_upload_response = requests.put(
            upload_url_actual,
            data=image_bytes,
            headers={'Content-Type': content_type}
        )
        
        if image_upload_response.status_code not in [200, 201]:
            return False, f"Image upload failed (HTTP {image_upload_response.status_code})"
        
        post_url = "https://api.linkedin.com/v2/ugcPosts"
        
        payload = {
            "author": author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {
                        "text": content
                    },
                    "shareMediaCategory": "IMAGE",
                    "media": [
                        {
                            "status": "READY",
                            "media": asset_urn
                        }
                    ]
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            }
        }
        
        response = requests.post(post_url, headers=headers, json=payload)
        
        if response.status_code in [201, 200]:
            return True, "Published to LinkedIn with image successfully"
        return False, f"Publish Failed (HTTP {response.status_code}): {response.text}"
    except Exception as e:
        return False, f"API Error: {str(e)}"


def publish_to_linkedin_with_video(content, video_bytes, access_token, member_id):
    try:
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
            'X-Restli-Protocol-Version': '2.0.0'
        }
        
        author_urn = _format_author_urn(member_id)
        
        upload_url = "https://api.linkedin.com/v2/assets?action=registerUpload"
        upload_payload = {
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-video"],
                "owner": author_urn,
                "serviceRelationships": [
                    {
                        "relationshipType": "OWNER",
                        "identifier": "urn:li:userGeneratedContent"
                    }
                ]
            }
        }
        
        upload_response = requests.post(upload_url, headers=headers, json=upload_payload)
        if upload_response.status_code not in [200, 201]:
            return False, f"Video upload registration failed (HTTP {upload_response.status_code}): {upload_response.text}"
        
        upload_data = upload_response.json()
        upload_url_actual = upload_data.get('value', {}).get('uploadMechanism', {}).get('com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest', {}).get('uploadUrl')
        asset_urn = upload_data.get('value', {}).get('asset')
        
        if not upload_url_actual or not asset_urn:
            return False, f"Invalid upload response: {upload_response.text}"
        
        video_upload_response = requests.put(
            upload_url_actual,
            data=video_bytes,
            headers={'Content-Type': 'video/mp4'}
        )
        
        if video_upload_response.status_code not in [200, 201]:
            return False, f"Video upload failed (HTTP {video_upload_response.status_code})"
        
        post_url = "https://api.linkedin.com/v2/ugcPosts"
        
        payload = {
            "author": author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {
                        "text": content
                    },
                    "shareMediaCategory": "VIDEO",
                    "media": [
                        {
                            "status": "READY",
                            "media": asset_urn,
                            "title": {
                                "text": "Video"
                            }
                        }
                    ]
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            }
        }
        
        response = requests.post(post_url, headers=headers, json=payload)
        
        if response.status_code in [201, 200]:
            return True, "Published to LinkedIn with video successfully"
        return False, f"Publish Failed (HTTP {response.status_code}): {response.text}"
    except Exception as e:
        return False, f"API Error: {str(e)}"


def publish_to_facebook(content, access_token, page_id):
    try:
        url = f"https://graph.facebook.com/v19.0/{page_id}/feed"
        payload = {"message": content or "", "access_token": access_token}
        response = requests.post(url, data=payload)
        if response.status_code in (200, 201):
            return True, "Published to Facebook successfully"
        return False, f"Facebook publish failed (HTTP {response.status_code}): {response.text}"
    except Exception as e:
        return False, f"Facebook API Error: {str(e)}"


def publish_to_facebook_with_image(content, image_bytes, access_token, page_id):
    try:
        url = f"https://graph.facebook.com/v19.0/{page_id}/photos"
        files = {"source": ("image.png", image_bytes, "image/png")}
        data = {"caption": content or "", "published": "true", "access_token": access_token}
        response = requests.post(url, files=files, data=data)
        if response.status_code in (200, 201):
            return True, "Published to Facebook with image successfully"
        return False, f"Facebook image publish failed (HTTP {response.status_code}): {response.text}"
    except Exception as e:
        return False, f"Facebook API Error: {str(e)}"


def publish_to_facebook_with_video(content, video_bytes, access_token, page_id):
    try:
        url = f"https://graph.facebook.com/v19.0/{page_id}/videos"
        files = {"source": ("video.mp4", video_bytes, "video/mp4")}
        data = {"description": content or "", "access_token": access_token}
        response = requests.post(url, files=files, data=data)
        if response.status_code in (200, 201):
            return True, "Published to Facebook with video successfully"
        return False, f"Facebook video publish failed (HTTP {response.status_code}): {response.text}"
    except Exception as e:
        return False, f"Facebook API Error: {str(e)}"


def _facebook_upload_image_and_get_url(image_bytes, access_token, page_id):
    try:
        upload_url = f"https://graph.facebook.com/v19.0/{page_id}/photos"
        files = {"source": ("image.png", image_bytes, "image/png")}
        data = {"published": "false", "access_token": access_token}
        upload_resp = requests.post(upload_url, files=files, data=data)
        if upload_resp.status_code not in (200, 201):
            return None
        photo_id = (upload_resp.json() or {}).get("id")
        if not photo_id:
            return None
        meta_url = f"https://graph.facebook.com/v19.0/{photo_id}"
        meta_resp = requests.get(meta_url, params={"fields": "images", "access_token": access_token})
        if meta_resp.status_code != 200:
            return None
        images = (meta_resp.json() or {}).get("images") or []
        if not images:
            return None
        best = max(images, key=lambda x: int(x.get("width") or 0))
        return best.get("source")
    except Exception:
        return None


def _facebook_upload_video_and_get_url(video_bytes, access_token, page_id):
    try:
        upload_url = f"https://graph.facebook.com/v19.0/{page_id}/videos"
        files = {"source": ("video.mp4", video_bytes, "video/mp4")}
        data = {"published": "false", "access_token": access_token}
        upload_resp = requests.post(upload_url, files=files, data=data)
        if upload_resp.status_code not in (200, 201):
            return None
        video_id = (upload_resp.json() or {}).get("id")
        if not video_id:
            return None
        meta_url = f"https://graph.facebook.com/v19.0/{video_id}"
        meta_resp = requests.get(meta_url, params={"fields": "source", "access_token": access_token})
        if meta_resp.status_code != 200:
            return None
        return (meta_resp.json() or {}).get("source")
    except Exception:
        return None


def publish_to_instagram(content, access_token, user_id, image_bytes=None, video_bytes=None, facebook_access_token=None, facebook_page_id=None):
    try:
        fb_token = facebook_access_token or access_token
        fb_page = facebook_page_id

        if video_bytes:
            video_url = _facebook_upload_video_and_get_url(video_bytes, fb_token, fb_page)
            if not video_url:
                return False, "Instagram video publish requires a valid Facebook Page token + Page ID"

            create_url = f"https://graph.facebook.com/v19.0/{user_id}/media"
            create_resp = requests.post(
                create_url,
                data={
                    "media_type": "REELS",
                    "video_url": video_url,
                    "caption": content or "",
                    "access_token": access_token,
                },
            )
            if create_resp.status_code not in (200, 201):
                return False, f"Instagram media creation failed (HTTP {create_resp.status_code}): {create_resp.text}"
            creation_id = (create_resp.json() or {}).get("id")
            if not creation_id:
                return False, "Instagram media creation returned no id"

            status_url = f"https://graph.facebook.com/v19.0/{creation_id}"
            for _ in range(24):
                status_resp = requests.get(status_url, params={"fields": "status_code", "access_token": access_token})
                if status_resp.status_code != 200:
                    break
                status_code = (status_resp.json() or {}).get("status_code")
                if status_code == "FINISHED":
                    break
                if status_code == "ERROR":
                    return False, "Instagram media processing failed"
                time.sleep(5)

            publish_url = f"https://graph.facebook.com/v19.0/{user_id}/media_publish"
            publish_resp = requests.post(publish_url, data={"creation_id": creation_id, "access_token": access_token})
            if publish_resp.status_code in (200, 201):
                return True, "Published to Instagram successfully"
            return False, f"Instagram publish failed (HTTP {publish_resp.status_code}): {publish_resp.text}"

        if image_bytes:
            image_url = _facebook_upload_image_and_get_url(image_bytes, fb_token, fb_page)
            if not image_url:
                return False, "Instagram image publish requires a valid Facebook Page token + Page ID"
            create_url = f"https://graph.facebook.com/v19.0/{user_id}/media"
            create_resp = requests.post(
                create_url,
                data={"image_url": image_url, "caption": content or "", "access_token": access_token},
            )
            if create_resp.status_code not in (200, 201):
                return False, f"Instagram media creation failed (HTTP {create_resp.status_code}): {create_resp.text}"
            creation_id = (create_resp.json() or {}).get("id")
            if not creation_id:
                return False, "Instagram media creation returned no id"
            publish_url = f"https://graph.facebook.com/v19.0/{user_id}/media_publish"
            publish_resp = requests.post(publish_url, data={"creation_id": creation_id, "access_token": access_token})
            if publish_resp.status_code in (200, 201):
                return True, "Published to Instagram successfully"
            return False, f"Instagram publish failed (HTTP {publish_resp.status_code}): {publish_resp.text}"

        return False, "Instagram publishing requires an image or video"
    except Exception as e:
        return False, f"Instagram API Error: {str(e)}"


if __name__ == "__main__":
    interval = int(os.getenv("SCHEDULER_INTERVAL_SECONDS", "20"))
    run_once = os.getenv("SCHEDULER_RUN_ONCE", "").lower() in ("1", "true", "yes")
    if run_once:
        count = auto_publish_scheduled_posts()
        if count and os.getenv("SCHEDULER_LOG_ENABLED", "false").lower() in ("1", "true", "yes"):
            try:
                with open(os.path.join(os.path.dirname(__file__), ".scheduler_log.txt"), "a", encoding="utf-8") as f:
                    f.write(f"{datetime.now()}: Published {count} post(s)\n")
            except Exception:
                pass
    else:
        try:
            while True:
                count = auto_publish_scheduled_posts()
                if count and os.getenv("SCHEDULER_LOG_ENABLED", "false").lower() in ("1", "true", "yes"):
                    try:
                        with open(os.path.join(os.path.dirname(__file__), ".scheduler_log.txt"), "a", encoding="utf-8") as f:
                            f.write(f"{datetime.now()}: Published {count} post(s)\n")
                    except Exception:
                        pass
                time.sleep(interval)
        except KeyboardInterrupt:
            pass
