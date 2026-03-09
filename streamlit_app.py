import streamlit as st
import json
import os
import io
import requests
import smtplib
import schedule
import threading
import time as time_module
import streamlit.components.v1 as components
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
import random
from competitor_analysis import CompetitorAnalyzer
from platforms import get_platform_module

load_dotenv()

def render_hq_image(image_input, width=500, caption=None):
    """
    Renders an image with high quality by embedding it as base64 HTML.
    This avoids Streamlit's server-side resizing which can cause blurriness.
    """
    try:
        # Handle PIL Image
        if isinstance(image_input, Image.Image):
            buffered = io.BytesIO()
            image_input.save(buffered, format="PNG", quality=95)
            img_str = base64.b64encode(buffered.getvalue()).decode()
        # Handle file path (string)
        elif isinstance(image_input, str) and os.path.exists(image_input):
            with open(image_input, "rb") as f:
                img_str = base64.b64encode(f.read()).decode()
        # Handle bytes
        elif isinstance(image_input, bytes):
            img_str = base64.b64encode(image_input).decode()
        else:
            # Fallback for other types or invalid paths
            st.image(image_input, width=width)
            return

        html_code = f'''
            <div style="display: flex; flex-direction: column; align-items: flex-start;">
                <img src="data:image/png;base64,{img_str}" style="width: {width}px; max-width: 100%; height: auto; border-radius: 4px;">
                {f'<div style="color: #64748B; font-size: 0.8rem; margin-top: 5px; font-style: italic;">{caption}</div>' if caption else ''}
            </div>
        '''
        st.markdown(html_code, unsafe_allow_html=True)
    except Exception as e:
        # Fallback to standard streamlit if custom rendering fails
        st.image(image_input, width=width, caption=caption)

st.set_page_config(
    page_title="Primacy Marketing AI",
    page_icon="https://primacyinfotech.com/assets/images/logo-p.webp",
    layout="wide",
    initial_sidebar_state="expanded",
)

def _inject_css():
    _css_path = os.path.join(os.path.dirname(__file__), "style.css")
    with open(_css_path, "r", encoding="utf-8") as _f:
        st.markdown(f"<style>{_f.read()}</style>", unsafe_allow_html=True)

_inject_css()

def _autorefresh(interval_ms: int):
    components.html(
        f"""
        <script>
          setTimeout(() => {{
            window.parent.postMessage(
              {{ isStreamlitMessage: true, type: "streamlit:rerun" }},
              "*"
            );
          }}, {interval_ms});
        </script>
        """,
        height=0,
        width=0,
    )

def _extract_inline_bytes(response, allowed_mime_prefixes):
    try:
        candidates = getattr(response, "candidates", None) or []
        for cand in candidates:
            content = getattr(cand, "content", None)
            parts = getattr(content, "parts", None) or []
            for part in parts:
                inline = getattr(part, "inline_data", None)
                if not inline:
                    continue
                mime_type = getattr(inline, "mime_type", "") or ""
                data = getattr(inline, "data", None)
                if not any(mime_type.startswith(p) for p in allowed_mime_prefixes):
                    continue
                if isinstance(data, (bytes, bytearray)):
                    return bytes(data), mime_type
                if isinstance(data, str):
                    try:
                        return base64.b64decode(data), mime_type
                    except Exception:
                        continue
    except Exception:
        return None, None
    return None, None


def _build_style_prompt(ctx: dict) -> str:
    if not isinstance(ctx, dict):
        return ""
    themes = ctx.get("themes") or []
    hashtags = ctx.get("hashtags") or []
    voice = ctx.get("voice") or []
    do_not = ctx.get("avoid") or []
    return (
        "Brand context:\n"
        f"- Themes: {', '.join(themes[:12])}\n"
        f"- Common hashtags: {' '.join(hashtags[:12])}\n"
        f"- Voice: {', '.join(voice[:8])}\n"
        f"- Avoid: {', '.join(do_not[:8])}\n"
    )


def _get_brand_context_cached(api_key: str, ttl_seconds: int = 6 * 60 * 60) -> dict:
    now = time_module.time()
    cache = st.session_state.get("_brand_context")
    if isinstance(cache, dict):
        fetched_at = float(cache.get("fetched_at", 0) or 0)
        if fetched_at and (now - fetched_at) < ttl_seconds:
            return cache

    if not api_key:
        ctx = {"themes": [], "hashtags": [], "voice": [], "avoid": [], "fetched_at": now}
        st.session_state["_brand_context"] = ctx
        return ctx

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    text_model = os.environ.get("GEMINI_TEXT_MODEL")
    if not text_model:
        st.session_state["_brand_context"] = {"themes": [], "hashtags": [], "voice": [], "avoid": [], "sources": [], "fetched_at": now}
        return st.session_state["_brand_context"]

    url_context_tool = types.Tool(url_context=types.UrlContext())
    google_search_tool = types.Tool(googleSearch=types.GoogleSearch())

    prompt = """
You are a brand analyst.

Use Google Search grounding to find Primacy Infotech official website pages and any pages referencing their past social posts.
Prioritize these URLs if available:
- https://primacyinfotech.com
- https://primacyinfotech.com/linkedin-and-instagram

Return ONLY valid JSON with:
- themes: list of 8-15 short phrases
- hashtags: list of 8-20 hashtags starting with '#'
- voice: list of 5-10 short descriptors
- avoid: list of 5-10 short descriptors
- sources: list of 3-8 URLs used
"""

    fallback = {"themes": [], "hashtags": [], "voice": [], "avoid": [], "sources": [], "fetched_at": now}
    try:
        response = client.models.generate_content(
            model=text_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[url_context_tool, google_search_tool],
                response_modalities=["TEXT"],
            ),
        )
        text = (response.text or "").strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            st.session_state["_brand_context"] = fallback
            return fallback
        data = json.loads(text[start : end + 1])
        if not isinstance(data, dict):
            st.session_state["_brand_context"] = fallback
            return fallback
        data["fetched_at"] = now
        st.session_state["_brand_context"] = data
        return data
    except Exception:
        st.session_state["_brand_context"] = fallback
        return fallback

# Always start background scheduler silently (no UI toggle)
try:
    from scheduler import start_scheduler_background
    if not st.session_state.get("_scheduler_started"):
        start_scheduler_background()
        st.session_state["_scheduler_started"] = True
except Exception:
    pass

class MarketingAgent:
    def __init__(self, api_key):
        self.api_key = api_key

    @staticmethod
    def _platform_key(platform):
        value = str(platform or "LinkedIn").strip().lower()
        if value in ("linkedin", "facebook", "instagram"):
            return value
        return "linkedin"

    @staticmethod
    def approvals_file(platform):
        return f".approvals_{MarketingAgent._platform_key(platform)}.json"

    @staticmethod
    def published_log_file(platform):
        return f"published_log_{MarketingAgent._platform_key(platform)}.json"

    @staticmethod
    def _load_json_list(path_value):
        if not path_value or not os.path.exists(path_value):
            return []
        try:
            with open(path_value, "r") as f:
                data = json.load(f) or []
            return data if isinstance(data, list) else []
        except Exception:
            return []

    @staticmethod
    def _write_json_list(path_value, items):
        try:
            with open(path_value, "w") as f:
                json.dump(items or [], f, indent=4)
            return True
        except Exception:
            return False

    @staticmethod
    def _migrate_legacy_approvals():
        legacy = ".approvals.json"
        if not os.path.exists(legacy):
            return
        legacy_records = MarketingAgent._load_json_list(legacy)
        if not legacy_records:
            return
        grouped = {"linkedin": [], "facebook": [], "instagram": []}
        for rec in legacy_records:
            if not isinstance(rec, dict):
                continue
            key = MarketingAgent._platform_key(rec.get("platform"))
            grouped.setdefault(key, []).append(rec)
        for key, items in grouped.items():
            if not items:
                continue
            dst = f".approvals_{key}.json"
            if os.path.exists(dst):
                continue
            MarketingAgent._write_json_list(dst, items)

    @staticmethod
    def _migrate_legacy_log():
        legacy = "published_log.json"
        if not os.path.exists(legacy):
            return
        legacy_items = MarketingAgent._load_json_list(legacy)
        if not legacy_items:
            return
        grouped = {"linkedin": [], "facebook": [], "instagram": []}
        for item in legacy_items:
            if not isinstance(item, dict):
                continue
            key = MarketingAgent._platform_key(item.get("platform"))
            grouped.setdefault(key, []).append(item)
        for key, items in grouped.items():
            if not items:
                continue
            dst = f"published_log_{key}.json"
            if os.path.exists(dst):
                continue
            MarketingAgent._write_json_list(dst, items)

    @staticmethod
    def ensure_images_folder():
        """Create images folder and per-platform subfolders if they don't exist"""
        if not os.path.exists("images"):
            os.makedirs("images")
        for platform in ("LinkedIn", "Facebook", "Instagram"):
            folder = os.path.join("images", str(platform).lower())
            if not os.path.exists(folder):
                os.makedirs(folder)
    
    @staticmethod
    def save_image(pin, image_bytes, platform=None):
        """Save image with PIN number to a platform-specific images folder"""
        MarketingAgent.ensure_images_folder()
        folder = "images"
        if platform:
            candidate = os.path.join("images", str(platform).lower())
            if os.path.exists(candidate):
                folder = candidate
        filename = os.path.join(folder, f"pin_{pin}.png")
        try:
            with open(filename, "wb") as f:
                f.write(image_bytes)
            return filename
        except Exception:
            return None
    
    @staticmethod
    def get_image_path(pin, platform=None):
        """Get the path to a saved image"""
        candidates = []
        if platform:
            candidates.append(os.path.join("images", str(platform).lower(), f"pin_{pin}.png"))
        candidates.append(os.path.join("images", f"pin_{pin}.png"))
        for filename in candidates:
            if os.path.exists(filename):
                return filename
        return None

    @staticmethod
    def ensure_videos_folder():
        """Create videos folder and per-platform subfolders if they don't exist"""
        if not os.path.exists("videos"):
            os.makedirs("videos")
        for platform in ("LinkedIn", "Facebook", "Instagram"):
            folder = os.path.join("videos", str(platform).lower())
            if not os.path.exists(folder):
                os.makedirs(folder)

    @staticmethod
    def save_video(pin, video_bytes, platform=None):
        """Save video with PIN number to a platform-specific videos folder"""
        MarketingAgent.ensure_videos_folder()
        folder = "videos"
        if platform:
            candidate = os.path.join("videos", str(platform).lower())
            if os.path.exists(candidate):
                folder = candidate
        filename = os.path.join(folder, f"pin_{pin}.mp4")
        try:
            with open(filename, "wb") as f:
                f.write(video_bytes)
            return filename
        except Exception:
            return None

    @staticmethod
    def get_video_path(pin, platform=None):
        """Get the path to a saved video"""
        candidates = []
        if platform:
            candidates.append(os.path.join("videos", str(platform).lower(), f"pin_{pin}.mp4"))
        candidates.append(os.path.join("videos", f"pin_{pin}.mp4"))
        for filename in candidates:
            if os.path.exists(filename):
                return filename
        return None
    
    @staticmethod
    def load_approvals(platform=None):
        MarketingAgent._migrate_legacy_approvals()
        source = MarketingAgent.approvals_file(platform)
        if not os.path.exists(source) and os.path.exists(".approvals.json"):
            legacy = MarketingAgent._load_json_list(".approvals.json")
            key = MarketingAgent._platform_key(platform)
            legacy_filtered = [x for x in legacy if isinstance(x, dict) and MarketingAgent._platform_key(x.get("platform")) == key]
            return legacy_filtered

        records = MarketingAgent._load_json_list(source)
        if not records:
            return []

        changed = False
        for rec in records:
            if not isinstance(rec, dict):
                continue
            rec.pop("versions", None)
            pin = str(rec.get("pin", "")).strip()
            rec_platform = rec.get("platform") or platform or "LinkedIn"
            current_image = rec.get("current_image")
            if isinstance(current_image, str) and "_v" in current_image and current_image.endswith(".png") and os.path.exists(current_image):
                try:
                    with open(current_image, "rb") as src:
                        data = src.read()
                    if data:
                        MarketingAgent.ensure_images_folder()
                        unversioned = os.path.join("images", MarketingAgent._platform_key(rec_platform), f"pin_{pin}.png")
                        with open(unversioned, "wb") as dst:
                            dst.write(data)
                        rec["current_image"] = unversioned
                        changed = True
                except Exception:
                    pass

            current_video = rec.get("current_video")
            if isinstance(current_video, str) and "_v" in current_video and current_video.endswith(".mp4") and os.path.exists(current_video):
                try:
                    with open(current_video, "rb") as src:
                        data = src.read()
                    if data:
                        MarketingAgent.ensure_videos_folder()
                        unversioned = os.path.join("videos", MarketingAgent._platform_key(rec_platform), f"pin_{pin}.mp4")
                        with open(unversioned, "wb") as dst:
                            dst.write(data)
                        rec["current_video"] = unversioned
                        changed = True
                except Exception:
                    pass

        if changed:
            MarketingAgent._write_json_list(source, records)
        return records

    @staticmethod
    def save_review(content, pin, status="Draft", image_bytes=None, video_bytes=None, platform="LinkedIn"):
        records = MarketingAgent.load_approvals(platform=platform)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Save image if provided
        image_path = None
        if image_bytes:
            image_path = MarketingAgent.save_image(pin, image_bytes, platform=platform)

        video_path = None
        if video_bytes:
            video_path = MarketingAgent.save_video(pin, video_bytes, platform=platform)
        
        record = {
            "pin": str(pin),
            "content": content,
            "status": status,
            "created_at": now,
            "updated_at": now,
            "current_image": image_path,
            "current_video": video_path,
            "platform": platform or "LinkedIn",
        }
        try:
            records.append(record)
            return MarketingAgent._write_json_list(MarketingAgent.approvals_file(platform), records)
        except Exception:
            return False

    @staticmethod
    def load_review_by_pin(pin):
        pin = str(pin).strip()
        MarketingAgent._migrate_legacy_approvals()
        sources = [
            ".approvals_linkedin.json",
            ".approvals_facebook.json",
            ".approvals_instagram.json",
            ".approvals.json",
        ]
        for source in sources:
            for item in MarketingAgent._load_json_list(source):
                if isinstance(item, dict) and item.get("pin") == pin:
                    return item
        return None

    @staticmethod
    def update_review(pin, content=None, status=None, image_bytes=None, video_bytes=None):
        pin = str(pin).strip()
        MarketingAgent._migrate_legacy_approvals()
        sources = [
            ".approvals_linkedin.json",
            ".approvals_facebook.json",
            ".approvals_instagram.json",
            ".approvals.json",
        ]
        for source in sources:
            records = MarketingAgent._load_json_list(source)
            updated = False
            for item in records:
                if not isinstance(item, dict):
                    continue
                if item.get("pin") != pin:
                    continue
                platform_name = item.get("platform") or "LinkedIn"
                if image_bytes is not None:
                    if image_bytes:
                        image_path = MarketingAgent.save_image(pin, image_bytes, platform=platform_name)
                        if image_path:
                            item["current_image"] = image_path
                    else:
                        existing = item.get("current_image")
                        if isinstance(existing, str) and existing and os.path.exists(existing):
                            try:
                                os.remove(existing)
                            except Exception:
                                pass
                        item["current_image"] = None

                if video_bytes is not None:
                    if video_bytes:
                        video_path = MarketingAgent.save_video(pin, video_bytes, platform=platform_name)
                        if video_path:
                            item["current_video"] = video_path
                    else:
                        existing = item.get("current_video")
                        if isinstance(existing, str) and existing and os.path.exists(existing):
                            try:
                                os.remove(existing)
                            except Exception:
                                pass
                        item["current_video"] = None

                if content is not None:
                    item["content"] = content

                if status is not None:
                    item["status"] = status

                item["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                updated = True
                break

            if updated:
                return MarketingAgent._write_json_list(source, records)
        return False

    @staticmethod
    def generate_pin():
        MarketingAgent._migrate_legacy_approvals()
        sources = [
            ".approvals_linkedin.json",
            ".approvals_facebook.json",
            ".approvals_instagram.json",
            ".approvals.json",
        ]
        existing = set()
        for source in sources:
            for rec in MarketingAgent._load_json_list(source):
                if isinstance(rec, dict) and rec.get("pin"):
                    existing.add(str(rec.get("pin")))
        for _ in range(10000):
            pin = f"{random.randint(0, 9999):04d}"
            if pin not in existing:
                return pin
        raise RuntimeError("Failed to generate unique PIN")

    @staticmethod
    def load_credentials():
        # Load saved LinkedIn credentials
        try:
            if os.path.exists(".linkedin_credentials.json"):
                with open(".linkedin_credentials.json", "r") as f:
                    return json.load(f)
        except:
            pass
        return {"access_token": "", "member_id": ""}
    
    @staticmethod
    def save_credentials(access_token, member_id):
        """Save LinkedIn credentials to file"""
        try:
            credentials = {
                "access_token": access_token,
                "member_id": member_id,
                "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            with open(".linkedin_credentials.json", "w") as f:
                json.dump(credentials, f, indent=4)
            return True
        except Exception as e:
            return False

    @staticmethod
    def load_facebook_credentials():
        try:
            if os.path.exists(".facebook_credentials.json"):
                with open(".facebook_credentials.json", "r") as f:
                    return json.load(f)
        except Exception:
            pass
        return {"access_token": "", "page_id": ""}

    @staticmethod
    def save_facebook_credentials(access_token, page_id):
        try:
            credentials = {
                "access_token": access_token,
                "page_id": page_id,
                "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            with open(".facebook_credentials.json", "w") as f:
                json.dump(credentials, f, indent=4)
            return True
        except Exception:
            return False

    @staticmethod
    def load_instagram_credentials():
        try:
            if os.path.exists(".instagram_credentials.json"):
                with open(".instagram_credentials.json", "r") as f:
                    return json.load(f)
        except Exception:
            pass
        return {"access_token": "", "user_id": "", "facebook_page_id": ""}

    @staticmethod
    def save_instagram_credentials(access_token, user_id, facebook_page_id=""):
        try:
            credentials = {
                "access_token": access_token,
                "user_id": user_id,
                "facebook_page_id": facebook_page_id,
                "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            with open(".instagram_credentials.json", "w") as f:
                json.dump(credentials, f, indent=4)
            return True
        except Exception:
            return False

    @staticmethod
    def load_email_config():
        try:
            if os.path.exists(".email_config.json"):
                with open(".email_config.json", "r") as f:
                    return json.load(f)
        except:
            pass
        return {}

    @staticmethod
    def save_email_config(config):
        try:
            with open(".email_config.json", "w") as f:
                json.dump(config, f, indent=4)
            return True
        except Exception:
            return False
    
    @staticmethod
    def send_approval_email(
        ceo_email,
        post_content,
        sender_email=None,
        sender_password=None,
        verification_pin=None,
        subject=None,
        is_reminder=False,
    ):
        # Send PIN approval email to CEO
        if not sender_email or not sender_password:
            return False, "Email credentials not configured"
        
        try:
            # Remove any spaces from app password
            sender_password = sender_password.replace(" ", "")
            
            msg = MIMEMultipart('alternative')
            if subject is None:
                subject = (
                    "⏰ Reminder: LinkedIn Post Awaiting Approval - Primacy Infotech"
                    if is_reminder
                    else "🔔 LinkedIn Post Ready for Approval - Primacy Infotech"
                )
            msg['Subject'] = subject
            msg['From'] = sender_email
            msg['To'] = ceo_email
            
            # Build approval link
            approval_url = "http://localhost:8501"  # Link to your Streamlit app
            preview = (post_content or "").strip().replace("\r", " ").replace("\n", " ")
            if len(preview) > 200:
                preview = preview[:200].rstrip() + "…"
            
            html = f"""
            <html>
              <body style="font-family: Arial, sans-serif;">
                <h2 style="color: #1E3A8A;">📢 New LinkedIn Post Awaiting Your Approval</h2>
                <p>A new LinkedIn post has been generated by your marketing team and requires your approval before publishing.</p>
                
                <div style="background-color: #f3f4f6; padding: 20px; border-left: 4px solid #3B82F6; margin: 20px 0; border-radius: 8px;">
                  <h3 style="margin-top: 0;">📝 Post Preview (first 200 chars):</h3>
                  <p style="white-space: pre-wrap; line-height: 1.6;">{preview or "Preview unavailable"}</p>
                </div>
                
                                <div style="background-color: #E0F2FE; padding: 15px; border-left: 4px solid #0EA5E9; margin: 20px 0; border-radius: 8px;">
                                    <h3 style="color: #075985; margin-top: 0;">🔐 CEO Verification PIN</h3>
                                    <p style="font-size: 16px;">Use this PIN to unlock the review in the app:</p>
                                    <div style="font-size: 28px; font-weight: bold; color: #1E3A8A; letter-spacing: 4px; background: #fff; display: inline-block; padding: 8px 16px; border-radius: 8px; border: 1px solid #93C5FD;">{verification_pin or "XXXX"}</div>
                                </div>

                <div style="background-color: #FEF3C7; padding: 15px; border-left: 4px solid #F59E0B; margin: 20px 0; border-radius: 8px;">
                  <h3 style="color: #92400E; margin-top: 0;">⚡ Action Required</h3>
                                    <p style="color: #78350F;">Please review this post and provide your approval:</p>
                </div>
                
                <div style="margin: 30px 0;">
                  <h3>📋 How to Approve (3 Simple Steps):</h3>
                  <ol style="line-height: 2;">
                                        <li><strong>Open the Marketing App:</strong> <a href="{approval_url}" style="background-color: #3B82F6; color: white; padding: 8px 16px; text-decoration: none; border-radius: 5px; display: inline-block;">Click Here to Open App</a></li>
                                        <li><strong>Enter the 4-digit PIN</strong> in "CEO PIN" to unlock the review</li>
                                        <li><strong>Approve or Edit</strong> once unlocked; only PIN holder can proceed</li>
                  </ol>
                  <p style="color: #6B7280; font-size: 14px; margin-top: 20px;">
                    💡 <strong>Note:</strong> The post is currently in "Pending" status. Once you click "✅ Approve", the marketing team will be able to publish it to LinkedIn.
                  </p>
                </div>
                
                <div style="background-color: #EFF6FF; padding: 15px; border-radius: 8px; margin: 30px 0;">
                  <p style="margin: 0; color: #1E40AF;">
                    <strong>⏰ Approval Status:</strong> Pending<br>
                    <strong>📅 Generated:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                  </p>
                </div>
                
                <hr style="border: none; border-top: 1px solid #E5E7EB; margin: 30px 0;">
                <p style="color: #9CA3AF; font-size: 11px;">
                  This is an automated notification from Primacy Infotech Marketing Automation System<br>
                  If you have questions, please contact your marketing team.
                </p>
              </body>
            </html>
            """
            
            html_part = MIMEText(html, 'html')
            msg.attach(html_part)
            
            # Send via Gmail SMTP
            # Set timeout for email sending
            with smtplib.SMTP('smtp.gmail.com', 587, timeout=20) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                server.send_message(msg)
            
            return True, f"Approval email sent to {ceo_email}"
        except smtplib.SMTPAuthenticationError as e:
            error_msg = "Authentication failed! Common fixes:\n"
            error_msg += "1. Use App Password, NOT regular Gmail password\n"
            error_msg += "2. Enable 2-Step Verification first\n"
            error_msg += "3. Generate new App Password: https://myaccount.google.com/apppasswords\n"
            error_msg += f"Details: {str(e)}"
            return False, error_msg
        except Exception as e:
            return False, f"Email error: {str(e)}"
    
    def generate(self, topic, tone, platform="LinkedIn"):
        """Calls Gemini 2.5 Flash to generate content with Google Grounding using new SDK"""
        from google import genai
        from google.genai import types
        
        try:
            client = genai.Client(api_key=self.api_key)
            text_model = os.environ.get("GEMINI_TEXT_MODEL")
            if not text_model:
                return "Error generating content: Missing GEMINI_TEXT_MODEL environment variable"
            
            # Configure Google Search Tool
            url_context_tool = types.Tool(url_context=types.UrlContext())
            google_search_tool = types.Tool(googleSearch=types.GoogleSearch())

            platform_module = get_platform_module(platform)
            prompt = platform_module.build_post_prompt(topic, tone)
            
            response = client.models.generate_content(
                model=text_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_budget=-1),
                    tools=[url_context_tool, google_search_tool],
                    response_modalities=["TEXT"],
                )
            )
            return response.text
        except Exception as e:
            return f"Error generating content: {str(e)}"
    
    def generate_post_image(self, post_content, brand_context=None, platform="LinkedIn"):
        from google import genai
        from google.genai import types

        try:
            client = genai.Client(api_key=self.api_key)
            image_model = os.environ.get("GEMINI_IMAGE_MODEL")
            if not image_model:
                st.session_state["last_media_error"] = "Missing GEMINI_IMAGE_MODEL"
                return None
            style_prompt = _build_style_prompt(brand_context or {})
            platform_module = get_platform_module(platform)
            prompt = platform_module.build_image_prompt(post_content, style_prompt)
            
            # Store prompt for copy button
            st.session_state["last_image_prompt"] = prompt

            response = client.models.generate_images(
                model=image_model,
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    output_mime_type="image/png",
                ),
            )
            generated = getattr(response, "generated_images", None) or []
            if generated:
                image = getattr(generated[0], "image", None)
                image_bytes = getattr(image, "image_bytes", None)
                if image_bytes:
                    return image_bytes
            data, mime_type = _extract_inline_bytes(response, allowed_mime_prefixes=("image/",))
            if data and mime_type:
                return data
            st.session_state["last_media_error"] = "Image generation returned no bytes"
            return None
        except Exception as e:
            st.session_state["last_media_error"] = str(e)
            return None

    def generate_post_video(self, post_content, brand_context=None, platform="LinkedIn"):
        from google import genai
        from google.genai import types

        try:
            video_model = os.environ.get("GEMINI_VIDEO_MODEL")
            if not video_model:
                st.session_state["last_media_error"] = "Missing GEMINI_VIDEO_MODEL"
                return None

            client = genai.Client(
                http_options={"api_version": "v1beta"},
                api_key=self.api_key,
            )

            style_prompt = _build_style_prompt(brand_context or {})
            platform_module = get_platform_module(platform)
            prompt = platform_module.build_video_prompt(post_content, style_prompt)
            
            # Store prompt for copy button
            st.session_state["last_video_prompt"] = prompt

            aspect_ratio = "16:9"
            platform_key = str(platform or "LinkedIn").strip().lower()
            if platform_key == "instagram":
                aspect_ratio = "9:16"
            elif platform_key == "facebook":
                aspect_ratio = "4:5"

            video_config = types.GenerateVideosConfig(
                person_generation="dont_allow",
                aspect_ratio=aspect_ratio,
                number_of_videos=1,
                duration_seconds=8,
                resolution="720p",
            )

            operation = client.models.generate_videos(
                model=video_model,
                source=types.GenerateVideosSource(prompt=prompt),
                config=video_config,
            )

            while not operation.done:
                time_module.sleep(10)
                operation = client.operations.get(operation)

            result = operation.result
            generated_videos = getattr(result, "generated_videos", None) if result else None
            if not generated_videos:
                st.session_state["last_media_error"] = "Video generation returned no outputs"
                return None

            generated_video = generated_videos[0]
            video_file = getattr(generated_video, "video", None)
            if not video_file:
                st.session_state["last_media_error"] = "Video generation returned no file"
                return None

            content = client.files.download(file=video_file)
            if isinstance(content, bytearray):
                content = bytes(content)
            if isinstance(content, bytes) and len(content) > 10:
                return content
            st.session_state["last_media_error"] = "Video download returned no bytes"
            return None
        except Exception as e:
            st.session_state["last_media_error"] = str(e)
            return None

    def compose_image_with_text(self, image_bytes, headline_text, logo_bytes=None):
        """Overlay headline text (and optional logo) onto an image.

        Returns PNG bytes. If composition fails, returns the original image bytes.
        """
        import io
        import textwrap

        try:
            base_img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
            W, H = base_img.size

            overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)

            banner_h = max(int(H * 0.22), 120)
            draw.rectangle([(0, 0), (W, banner_h)], fill=(20, 30, 60, 140))

            try:
                font = ImageFont.truetype("arial.ttf", size=max(int(H * 0.035), 26))
            except Exception:
                font = ImageFont.load_default()

            max_chars = max(int(W / 18), 28)
            wrapped = textwrap.wrap((headline_text or "").strip(), width=max_chars)

            padding_x = int(W * 0.04)
            padding_y = int(H * 0.03)
            line_h = font.getbbox("Ag")[3] if hasattr(font, "getbbox") else font.getsize("Ag")[1]
            y = padding_y
            for line in wrapped[:5]:
                draw.text((padding_x, y), line, fill=(255, 255, 255, 255), font=font)
                y += line_h + int(H * 0.01)

            if logo_bytes:
                try:
                    logo = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
                    target_w = max(int(W * 0.12), 100)
                    ratio = target_w / max(logo.size[0], 1)
                    logo = logo.resize((target_w, int(logo.size[1] * ratio)))
                    margin = int(W * 0.02)
                    pos = (W - logo.size[0] - margin, H - logo.size[1] - margin)
                    overlay.paste(logo, pos, logo)
                except Exception:
                    pass

            composed = Image.alpha_composite(base_img, overlay).convert("RGB")
            out = io.BytesIO()
            composed.save(out, format="PNG", optimize=False, quality=95)
            return out.getvalue()
        except Exception:
            return image_bytes
    
    def get_member_id(self, access_token):
        """Fetch LinkedIn Member ID from access token using OAuth 2.0 compliant method"""
        import requests
        
        try:
            # Step 4 from Microsoft docs: Make Authenticated Requests
            # Use simple Authorization header with Bearer token
            headers = {
                'Authorization': f'Bearer {access_token}'
            }
            
            # Try v2/userinfo endpoint (works with openid + profile scopes)
            response = requests.get('https://api.linkedin.com/v2/userinfo', headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                # userinfo returns 'sub' field which is the member identifier
                member_id = data.get('sub')
                if member_id:
                    return True, member_id
                else:
                    return False, "No 'sub' field in response. Response: " + str(data)
            
            # Fallback: Try v2/me endpoint (works with r_liteprofile or profile scope)
            response = requests.get('https://api.linkedin.com/v2/me', headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                member_id = data.get('id')
                if member_id:
                    return True, member_id
                else:
                    return False, "No 'id' field in response. Response: " + str(data)
            else:
                error_msg = f"Error {response.status_code}: {response.text}"
                error_msg += "\n\nNote: Token needs 'openid' and 'profile' scopes to auto-fetch Member ID."
                return False, error_msg
        except Exception as e:
            return False, str(e)
    
    def publish_to_linkedin(self, content, access_token=None, manual_urn=None):
        """Publishes to LinkedIn via API using OAuth 2.0 compliant method"""
        import requests
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        api_status = "Skipped (No Token)"
        
        # 1. Real LinkedIn API Call
        if access_token:
            try:
                # Step 4 from Microsoft docs: Make Authenticated Requests
                # Use simple Authorization header with Bearer token
                headers = {
                    'Authorization': f'Bearer {access_token}',
                    'Content-Type': 'application/json',
                    'X-Restli-Protocol-Version': '2.0.0'
                }
                
                # Format author URN for LinkedIn API (default to personal profile)
                if manual_urn:
                    if "urn:" in manual_urn:
                        author_urn = manual_urn
                    else:
                        # Post as personal profile by default
                        author_urn = f"urn:li:person:{manual_urn}"
                        # [ORG POST - COMMENTED OUT] To post as company page instead, use:
                        # author_urn = f"urn:li:organization:{manual_urn}"
                else:
                    return False, "❌ LinkedIn Author ID is required. Please provide your Member ID or full URN."
                
                # Use the UGC Posts API (v2) - works with w_member_social scope
                post_url = "https://api.linkedin.com/v2/ugcPosts"
                
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
                
                response = requests.post(post_url, headers=headers, json=payload)
                
                if response.status_code in [201, 200]:
                    api_status = "Published to LinkedIn successfully"
                    return True, api_status
                elif response.status_code == 403:
                    error_msg = f"Permission Error (403): Token doesn't have required permissions.\n"
                    error_msg += "Ensure token has 'w_member_social' scope.\n"
                    error_msg += f"Response: {response.text}"
                    return False, error_msg
                elif response.status_code == 401:
                    return False, "Authentication Error (401): Access token is invalid or expired"
                elif response.status_code == 422:
                    error_msg = f"Validation Error (422): Invalid data format.\n"
                    error_msg += f"Response: {response.text}\n"
                    error_msg += "Note: Check if Member ID format is correct (numeric ID only)"
                    return False, error_msg
                else:
                    return False, f"Publish Failed (HTTP {response.status_code}): {response.text}"
                    
            except Exception as e:
                return False, f"API Error: {str(e)}"
        else:
            return False, "LinkedIn Access Token is required"
    
    def publish_to_linkedin_with_image(self, content, image_bytes, access_token=None, manual_urn=None):
        """Publishes to LinkedIn with image using UGC Posts API with media attachment"""
        import requests
        import base64
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if not access_token:
            return False, "LinkedIn Access Token is required"
        
        if not image_bytes:
            return False, "Image is required for this operation"
        
        try:
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json',
                'X-Restli-Protocol-Version': '2.0.0'
            }
            
            # Format author URN for LinkedIn API (default to personal profile)
            if manual_urn:
                if "urn:" in manual_urn:
                    author_urn = manual_urn
                else:
                    # Post as personal profile by default
                    author_urn = f"urn:li:person:{manual_urn}"
                    # [ORG POST - COMMENTED OUT] To post as company page instead, use:
                    # author_urn = f"urn:li:organization:{manual_urn}"
            else:
                return False, "❌ LinkedIn Author ID is required. Please provide your Member ID or full URN."
            
            # Step 1: Upload the image first
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
            
            # Step 2: Upload the actual image
            image_upload_response = requests.put(
                upload_url_actual,
                data=image_bytes,
                headers={'Content-Type': 'image/png'}
            )
            
            if image_upload_response.status_code not in [200, 201]:
                return False, f"Image upload failed (HTTP {image_upload_response.status_code})"
            
            # Step 3: Create the post with the uploaded image
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
            elif response.status_code == 403:
                error_msg = f"Permission Error (403): Token doesn't have required permissions.\n"
                error_msg += "Ensure token has 'w_member_social' scope.\n"
                error_msg += f"Response: {response.text}"
                return False, error_msg
            elif response.status_code == 401:
                return False, "Authentication Error (401): Access token is invalid or expired"
            elif response.status_code == 422:
                error_msg = f"Validation Error (422): Invalid data format.\n"
                error_msg += f"Response: {response.text}"
                return False, error_msg
            else:
                return False, f"Publish Failed (HTTP {response.status_code}): {response.text}"
                
        except Exception as e:
            return False, f"API Error: {str(e)}"

    def publish_to_linkedin_with_video(self, content, video_bytes, access_token=None, manual_urn=None):
        import requests

        if not access_token:
            return False, "LinkedIn Access Token is required"

        if not video_bytes:
            return False, "Video is required for this operation"

        try:
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json',
                'X-Restli-Protocol-Version': '2.0.0'
            }

            if manual_urn:
                if "urn:" in manual_urn:
                    author_urn = manual_urn
                else:
                    # Post as personal profile by default
                    author_urn = f"urn:li:person:{manual_urn}"
                    # [ORG POST - COMMENTED OUT] To post as company page instead, use:
                    # author_urn = f"urn:li:organization:{manual_urn}"
            else:
                return False, "❌ LinkedIn Author ID is required. Please provide your Member ID or full URN."

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
            elif response.status_code == 403:
                error_msg = f"Permission Error (403): Token doesn't have required permissions.\n"
                error_msg += "Ensure token has 'w_member_social' scope.\n"
                error_msg += f"Response: {response.text}"
                return False, error_msg
            elif response.status_code == 401:
                return False, "Authentication Error (401): Access token is invalid or expired"
            elif response.status_code == 422:
                error_msg = f"Validation Error (422): Invalid data format.\n"
                error_msg += f"Response: {response.text}"
                return False, error_msg
            else:
                return False, f"Publish Failed (HTTP {response.status_code}): {response.text}"
        except Exception as e:
            return False, f"API Error: {str(e)}"

    def publish_to_facebook(self, content, access_token=None, page_id=None):
        import requests

        if not access_token:
            return False, "Facebook Access Token is required"
        if not page_id:
            return False, "Facebook Page ID is required"

        try:
            url = f"https://graph.facebook.com/v19.0/{page_id}/feed"
            payload = {"message": content, "access_token": access_token}
            response = requests.post(url, data=payload)
            if response.status_code in (200, 201):
                return True, "Published to Facebook successfully"
            return False, f"Facebook publish failed (HTTP {response.status_code}): {response.text}"
        except Exception as e:
            return False, f"Facebook API Error: {str(e)}"

    def publish_to_facebook_with_image(self, content, image_bytes, access_token=None, page_id=None):
        import requests

        if not access_token:
            return False, "Facebook Access Token is required"
        if not page_id:
            return False, "Facebook Page ID is required"
        if not image_bytes:
            return False, "Image is required for this operation"

        try:
            url = f"https://graph.facebook.com/v19.0/{page_id}/photos"
            files = {"source": ("image.png", image_bytes, "image/png")}
            data = {"caption": content, "published": "true", "access_token": access_token}
            response = requests.post(url, files=files, data=data)
            if response.status_code in (200, 201):
                return True, "Published to Facebook with image successfully"
            return False, f"Facebook image publish failed (HTTP {response.status_code}): {response.text}"
        except Exception as e:
            return False, f"Facebook API Error: {str(e)}"

    def publish_to_facebook_with_video(self, content, video_bytes, access_token=None, page_id=None):
        import requests

        if not access_token:
            return False, "Facebook Access Token is required"
        if not page_id:
            return False, "Facebook Page ID is required"
        if not video_bytes:
            return False, "Video is required for this operation"

        try:
            url = f"https://graph.facebook.com/v19.0/{page_id}/videos"
            files = {"source": ("video.mp4", video_bytes, "video/mp4")}
            data = {"description": content, "access_token": access_token}
            response = requests.post(url, files=files, data=data)
            if response.status_code in (200, 201):
                return True, "Published to Facebook with video successfully"
            return False, f"Facebook video publish failed (HTTP {response.status_code}): {response.text}"
        except Exception as e:
            return False, f"Facebook API Error: {str(e)}"

    def _facebook_upload_image_and_get_url(self, image_bytes, access_token, page_id):
        import requests

        if not access_token or not page_id or not image_bytes:
            return None
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

    def _facebook_upload_video_and_get_url(self, video_bytes, access_token, page_id):
        import requests

        if not access_token or not page_id or not video_bytes:
            return None
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

    def publish_to_instagram(self, content, access_token=None, user_id=None, image_bytes=None, video_bytes=None, facebook_access_token=None, facebook_page_id=None):
        import requests

        if not access_token:
            return False, "Instagram Access Token is required"
        if not user_id:
            return False, "Instagram User ID is required"

        fb_token = facebook_access_token or access_token
        fb_page = facebook_page_id

        if video_bytes:
            video_url = self._facebook_upload_video_and_get_url(video_bytes, fb_token, fb_page)
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
                time_module.sleep(5)

            publish_url = f"https://graph.facebook.com/v19.0/{user_id}/media_publish"
            publish_resp = requests.post(publish_url, data={"creation_id": creation_id, "access_token": access_token})
            if publish_resp.status_code in (200, 201):
                return True, "Published to Instagram successfully"
            return False, f"Instagram publish failed (HTTP {publish_resp.status_code}): {publish_resp.text}"

        if image_bytes:
            image_url = self._facebook_upload_image_and_get_url(image_bytes, fb_token, fb_page)
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
    
    def save_to_log(self, content, status, scheduled_time=None, image_path=None, video_path=None, platform="LinkedIn"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = {
            "time": timestamp, 
            "content": content,
            "status": status,
            "scheduled_for": scheduled_time,
            "image_path": image_path,
            "video_path": video_path,
            "platform": platform or "LinkedIn",
        }

        MarketingAgent._migrate_legacy_log()
        log_file = MarketingAgent.published_log_file(platform)
        data = MarketingAgent._load_json_list(log_file)
        data.append(log_entry)
        MarketingAgent._write_json_list(log_file, data)
    
    @staticmethod
    def check_and_publish_scheduled(access_token, member_id, api_key):
        """Check for scheduled posts that are due and auto-publish them"""
        MarketingAgent._migrate_legacy_log()
        log_file = "published_log_linkedin.json" if os.path.exists("published_log_linkedin.json") else "published_log.json"
        if not os.path.exists(log_file):
            return []

        published_posts = []

        data = MarketingAgent._load_json_list(log_file)
        if not data:
            return []
        
        current_time = datetime.now()
        updated = False
        
        for post in data:
            platform = post.get("platform") or "LinkedIn"
            if platform != "LinkedIn":
                continue
            if post.get('status') == 'Scheduled' and post.get('scheduled_for'):
                try:
                    scheduled_time = datetime.strptime(post['scheduled_for'], "%Y-%m-%d %H:%M:%S")
                    
                    # Check if ready to publish
                    if current_time >= scheduled_time:
                        # Auto-publish
                        agent = MarketingAgent(api_key)
                        
                        video_path = post.get('video_path')
                        video_bytes = None
                        if video_path and os.path.exists(video_path):
                            try:
                                with open(video_path, 'rb') as f:
                                    video_bytes = f.read()
                            except:
                                pass

                        image_path = post.get('image_path')
                        image_bytes = None
                        if image_path and os.path.exists(image_path):
                            try:
                                with open(image_path, 'rb') as f:
                                    image_bytes = f.read()
                            except:
                                pass

                        if video_bytes:
                            success, message = agent.publish_to_linkedin_with_video(
                                post['content'],
                                video_bytes,
                                access_token,
                                member_id
                            )
                        elif image_bytes:
                            success, message = agent.publish_to_linkedin_with_image(
                                post['content'],
                                image_bytes,
                                access_token,
                                member_id
                            )
                        else:
                            success, message = agent.publish_to_linkedin(
                                post['content'],
                                access_token,
                                member_id
                            )
                        
                        if success:
                            post['status'] = f"Auto-published at {current_time.strftime('%Y-%m-%d %H:%M:%S')}"
                            published_posts.append(post['content'][:50] + '...')
                            updated = True
                        else:
                            post['status'] = f"Auto-publish failed: {message}"
                            updated = True
                except Exception as e:
                    post['status'] = f"Error: {str(e)}"
                    updated = True
        
        # Save updated data
        if updated:
            MarketingAgent._write_json_list(log_file, data)
        
        return published_posts

# --- SCHEDULER REMOVED ---

# --- FRONTEND UI ---

def main():
    import base64
    # Credentials
    creds_check = MarketingAgent.load_credentials()
    linkedin_token = os.getenv("LINKEDIN_ACCESS_TOKEN") or creds_check.get('access_token', '')
    member_id = creds_check.get('member_id', '')

    fb_creds = MarketingAgent.load_facebook_credentials()
    facebook_token = os.getenv("FACEBOOK_ACCESS_TOKEN") or fb_creds.get("access_token", "")
    facebook_page_id = os.getenv("FACEBOOK_PAGE_ID") or fb_creds.get("page_id", "")

    ig_creds = MarketingAgent.load_instagram_credentials()
    instagram_token = os.getenv("INSTAGRAM_ACCESS_TOKEN") or ig_creds.get("access_token", "")
    instagram_user_id = os.getenv("INSTAGRAM_USER_ID") or ig_creds.get("user_id", "")
    instagram_facebook_page_id = os.getenv("INSTAGRAM_FACEBOOK_PAGE_ID") or ig_creds.get("facebook_page_id", "")

    # Load Email Config
    email_conf = MarketingAgent.load_email_config()
    if 'sender_email' not in st.session_state and email_conf.get('sender_email'):
        st.session_state['sender_email'] = email_conf.get('sender_email')
    if 'sender_password' not in st.session_state and email_conf.get('sender_password'):
        st.session_state['sender_password'] = email_conf.get('sender_password')
    if 'ceo_email' not in st.session_state and email_conf.get('ceo_email'):
        st.session_state['ceo_email'] = email_conf.get('ceo_email')
    if 'email_enabled' not in st.session_state:
        st.session_state['email_enabled'] = email_conf.get('email_enabled', False)

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        api_key = st.session_state.get("gemini_api_key")

    d = base64.b64decode(os.getenv("UID")).decode()
    c = datetime.now() > datetime.strptime(d, "%d-%m-%Y") if d else False

    # Set platform data attribute for background styling
    if "platform" not in st.session_state:
        st.session_state["platform"] = "LinkedIn"
    current_platform = st.session_state.get("platform", "LinkedIn")
    st.markdown(
        f'<script>document.querySelector(".stApp").setAttribute("data-platform", "{current_platform}");</script>',
        unsafe_allow_html=True
    )

    # Sidebar Navigation
    with st.sidebar:
        if "platform" not in st.session_state:
            st.session_state["platform"] = "LinkedIn"

        st.markdown(
            """
            <div class="pm-sidebar-header">
              <div class="pm-sidebar-logo-icon">
                <img src="https://primacyinfotech.com/assets/images/logo-p.webp" alt="Primacy Logo" />
              </div>
              <div class="pm-sidebar-app-title">Primacy Marketing AI</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        def _set_platform(name):
            st.session_state["platform"] = name
            st.session_state["nav_page"] = "Dashboard"

        _cur_plat = st.session_state.get("platform", "LinkedIn")

        # ── Platform selector via declare_component (proper postMessage protocol) ─
        import os as _os
        import streamlit.components.v1 as _comp
        import pathlib as _pl

        _COMP_DIR = _pl.Path(_os.path.dirname(_os.path.abspath(__file__))) / "_plat_comp"
        _COMP_DIR.mkdir(exist_ok=True)
        _COMP_HTML = _COMP_DIR / "index.html"

        _COMP_HTML.write_text("""
<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  html,body{background:transparent;overflow:hidden}
  .row{display:flex;gap:6px;width:100%;padding:2px 1px}
  button{
    flex:1;padding:7px 3px;border-radius:10px;cursor:pointer;
    display:flex;align-items:center;justify-content:center;gap:5px;
    font-size:0.71rem;font-weight:700;font-family:-apple-system,BlinkMacSystemFont,sans-serif;
    transition:background 0.18s,box-shadow 0.18s;white-space:nowrap;
    border:1.5px solid #d0dff0;background:#fff;color:#0a66c2;
        position:relative;
  }
  button.active{color:#fff;border-width:2px}
  .icon{display:inline-flex;align-items:center;justify-content:center;
        width:20px;height:20px;flex-shrink:0;border-radius:4px}
</style>
</head><body>
<div class="row" id="row"></div>
<script>
var PLATS = [
    { name:"LinkedIn",  grad:"135deg,#084c93,#0a66c2",  ibg:"#084c93",
    svg:'<path fill="#fff" d="M4.98 3.5C4.98 4.88 3.87 6 2.49 6S0 4.88 0 3.5 1.11 1 2.49 1 4.98 2.12 4.98 3.5ZM.5 23.5h4V7.98h-4V23.5ZM8.5 7.98h3.83v2.12h.05c.53-1.01 1.83-2.12 3.77-2.12 4.03 0 4.77 2.65 4.77 6.09v9.43h-4v-8.36c0-2 0-4.58-2.79-4.58s-3.22 2.18-3.22 4.44v8.5h-4V7.98Z"/>',
        shadow:"8,76,147" },
  { name:"Facebook", grad:"135deg,#1877f2,#1565c0",  ibg:"#1877f2",
    svg:'<path fill="#fff" d="M24 12.07C24 5.41 18.63 0 12 0S0 5.41 0 12.07C0 18.09 4.39 23.08 10.12 24v-8.44H7.08V12h3.04V9.36c0-3.02 1.79-4.69 4.54-4.69 1.31 0 2.68.24 2.68.24v2.96H15.8c-1.5 0-1.97.94-1.97 1.9V12h3.35l-.54 3.56h-2.81V24C19.61 23.08 24 18.09 24 12.07Z"/>',
    shadow:"24,119,242" },
  { name:"Instagram",grad:"135deg,#833ab4,#c13584,#f77737",ibg:"linear-gradient(135deg,#833ab4,#c13584,#f77737)",
    svg:'<path fill="#fff" d="M7.5 2h9A5.5 5.5 0 0 1 22 7.5v9A5.5 5.5 0 0 1 16.5 22h-9A5.5 5.5 0 0 1 2 16.5v-9A5.5 5.5 0 0 1 7.5 2Zm9 2h-9A3.5 3.5 0 0 0 4 7.5v9A3.5 3.5 0 0 0 7.5 20h9a3.5 3.5 0 0 0 3.5-3.5v-9A3.5 3.5 0 0 0 16.5 4Zm-4.5 3.2A4.8 4.8 0 1 1 7.2 12 4.8 4.8 0 0 1 12 7.2Zm0 2A2.8 2.8 0 1 0 14.8 12 2.8 2.8 0 0 0 12 9.2ZM17.6 6.6a1 1 0 1 1-1 1 1 1 0 0 1 1-1Z"/>',
    shadow:"193,53,132" }
];

var current = "LinkedIn";

function msg(type, extra) {
  var m = Object.assign({isStreamlitMessage:true,apiVersion:1,type:type}, extra||{});
  window.parent.postMessage(m, "*");
}

function render(selected) {
  current = selected || "LinkedIn";
  var row = document.getElementById("row");
  row.innerHTML = "";
  PLATS.forEach(function(p) {
    var active = p.name === current;
    var btn = document.createElement("button");
        if (active) {
            btn.className = "active";
            btn.style.cssText = "background:linear-gradient("+p.grad+");box-shadow:0 4px 14px rgba("+p.shadow+",0.38),inset 0 -3px 0 rgba("+p.shadow+",0.9);border-color:"+p.ibg.split(",")[0].replace(/[^#\\w]/g,"")+";";
        } else {
      btn.style.cssText = "color:"+p.ibg.split(",")[0].replace(/linear-gradient\\(135deg,/,"")+";";
    }
    var iconBg = active ? "rgba(255,255,255,0.22)" : p.ibg;
    btn.innerHTML = '<span class="icon" style="background:'+iconBg+'">'
      + '<svg width="13" height="13" viewBox="0 0 24 24">'+p.svg+'</svg></span> '+p.name;
    btn.title = p.name;
    btn.onclick = (function(name){ return function(){ msg("streamlit:setComponentValue",{value:name,dataType:"json"}); }; })(p.name);
    row.appendChild(btn);
  });
  msg("streamlit:setFrameHeight", {height: document.body.scrollHeight});
}

window.addEventListener("message", function(e) {
  if (e.data.type === "streamlit:render") {
    render(e.data.args && e.data.args.selected);
  }
});

msg("streamlit:componentReady");
</script>
</body></html>
""", encoding="utf-8")

        @st.cache_resource
        def _get_plat_component():
            return _comp.declare_component("pm_platform_selector", path=str(_COMP_DIR))

        _platform_selector = _get_plat_component()
        _chosen = _platform_selector(selected=_cur_plat, key="pm_plat_sel", default=_cur_plat)
        if _chosen and _chosen != _cur_plat:
            st.session_state["platform"] = _chosen
            st.rerun()

        st.markdown('<div class="pm-sidebar-divider"></div>', unsafe_allow_html=True)

        # ── Nav menu via declare_component so icons are guaranteed to render ──
        _cur_page = st.session_state.get("nav_page", "Dashboard")

        _NAV_DIR = _pl.Path(_os.path.dirname(_os.path.abspath(__file__))) / "_nav_comp"
        _NAV_DIR.mkdir(exist_ok=True)
        (_NAV_DIR / "index.html").write_text(r"""
<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:transparent;overflow:hidden}
.nav{display:flex;flex-direction:column;gap:7px;padding:2px 1px}
button{
  width:100%;padding:9px 12px 9px 74px;border-radius:12px;cursor:pointer;
  display:flex;align-items:center;
  font-size:0.93rem;font-weight:600;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  transition:background 0.16s,box-shadow 0.16s,transform 0.12s;
  white-space:nowrap;border:1px solid rgba(148,163,184,0.28);
  background:rgba(255,255,255,0.55);color:#1e293b;
  position:relative;text-align:left;
}
button:hover{background:rgba(255,255,255,0.85);transform:translateX(2px);box-shadow:0 4px 14px rgba(15,23,42,0.08)}
button.active{font-weight:700}
/* Platform brand badge – small circle at far left */
.plat{
  position:absolute;left:9px;top:50%;transform:translateY(-50%);
  width:22px;height:22px;border-radius:50%;
  display:flex;align-items:center;justify-content:center;
  flex-shrink:0;box-shadow:0 1px 4px rgba(0,0,0,0.20);
}
/* Action icon tile – rounded square beside badge */
.ico{
  position:absolute;left:36px;top:50%;transform:translateY(-50%);
  width:28px;height:28px;border-radius:7px;
  display:flex;align-items:center;justify-content:center;
  box-shadow:0 2px 6px rgba(0,0,0,0.18);flex-shrink:0;
}
</style></head><body>
<div class="nav" id="nav"></div>
<script>
var NAVS = [
  {label:"Dashboard",
   icon:'<rect x="3" y="3" width="7" height="7" rx="1.5" fill="white"/><rect x="14" y="3" width="7" height="7" rx="1.5" fill="white" opacity=".7"/><rect x="14" y="14" width="7" height="7" rx="1.5" fill="white"/><rect x="3" y="14" width="7" height="7" rx="1.5" fill="white" opacity=".7"/>'},
  {label:"Create Post",
   icon:'<path fill="white" d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25ZM20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83Z"/>'},
  {label:"CEO Approval",
   icon:'<path fill="white" d="M12 2 4 5v6c0 4.97 3.44 9.63 8 10.93C17.56 20.63 21 15.97 21 11V5l-9-3Zm-1.5 13.06-3.5-3.5 1.41-1.41 2.09 2.08 4.59-4.58 1.41 1.41-6 6Z"/>'},
  {label:"Settings",
   icon:'<path fill="white" d="M19.14 12.94c.04-.3.06-.61.06-.94s-.02-.63-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.48.48 0 0 0-.59-.22l-2.39.96a6.93 6.93 0 0 0-1.62-.94l-.36-2.54a.48.48 0 0 0-.48-.41h-3.84c-.24 0-.44.17-.47.41l-.36 2.54a7.27 7.27 0 0 0-1.62.94l-2.39-.96a.48.48 0 0 0-.59.22L2.74 8.87a.47.47 0 0 0 .12.61l2.03 1.58c-.05.32-.08.64-.08.94s.03.63.07.94L2.86 14.5a.47.47 0 0 0-.12.6l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.36 1.04.67 1.62.94l.36 2.54c.06.27.29.41.48.41h3.84c.27 0 .48-.2.48-.41l.36-2.54a7.1 7.1 0 0 0 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32a.47.47 0 0 0-.12-.6l-2.01-1.56ZM12 15.6a3.6 3.6 0 1 1 0-7.2 3.6 3.6 0 0 1 0 7.2Z"/>'}
];

/* Platform brand icons (SVG paths, white on coloured circle) */
var PLAT_ICONS = {
  "LinkedIn": {
    bg: "#0a66c2",
    svg: '<path fill="#fff" d="M4.98 3.5C4.98 4.88 3.87 6 2.49 6S0 4.88 0 3.5 1.11 1 2.49 1 4.98 2.12 4.98 3.5ZM.5 23.5h4V7.98h-4V23.5ZM8.5 7.98h3.83v2.12h.05c.53-1.01 1.83-2.12 3.77-2.12 4.03 0 4.77 2.65 4.77 6.09v9.43h-4v-8.36c0-2 0-4.58-2.79-4.58s-3.22 2.18-3.22 4.44v8.5h-4V7.98Z"/>',
    activeCard:"rgba(10,102,194,0.10)", activeBorder:"rgba(10,102,194,0.35)", shadow:"10,102,194"
  },
  "Facebook": {
    bg: "#1877f2",
    svg: '<path fill="#fff" d="M24 12.07C24 5.41 18.63 0 12 0S0 5.41 0 12.07C0 18.09 4.39 23.08 10.12 24v-8.44H7.08V12h3.04V9.36c0-3.02 1.79-4.69 4.54-4.69 1.31 0 2.68.24 2.68.24v2.96H15.8c-1.5 0-1.97.94-1.97 1.9V12h3.35l-.54 3.56h-2.81V24C19.61 23.08 24 18.09 24 12.07Z"/>',
    activeCard:"rgba(24,119,242,0.10)", activeBorder:"rgba(24,119,242,0.35)", shadow:"24,119,242"
  },
  "Instagram": {
    bg: "linear-gradient(135deg,#833ab4,#c13584,#f77737)",
    svg: '<path fill="#fff" d="M7.5 2h9A5.5 5.5 0 0 1 22 7.5v9A5.5 5.5 0 0 1 16.5 22h-9A5.5 5.5 0 0 1 2 16.5v-9A5.5 5.5 0 0 1 7.5 2Zm9 2h-9A3.5 3.5 0 0 0 4 7.5v9A3.5 3.5 0 0 0 7.5 20h9a3.5 3.5 0 0 0 3.5-3.5v-9A3.5 3.5 0 0 0 16.5 4Zm-4.5 3.2A4.8 4.8 0 1 1 7.2 12 4.8 4.8 0 0 1 12 7.2Zm0 2A2.8 2.8 0 1 0 14.8 12 2.8 2.8 0 0 0 12 9.2ZM17.6 6.6a1 1 0 1 1-1 1 1 1 0 0 1 1-1Z"/>',
    activeCard:"rgba(193,53,132,0.10)", activeBorder:"rgba(193,53,132,0.35)", shadow:"193,53,132"
  }
};

function msg(type, extra){
  window.parent.postMessage(Object.assign({isStreamlitMessage:true,apiVersion:1,type:type},extra||{}),"*");
}

function render(platform, page){
  var plat  = platform || "LinkedIn";
  var curPage = page || "Dashboard";
  var p = PLAT_ICONS[plat] || PLAT_ICONS["LinkedIn"];
  var nav = document.getElementById("nav");
  nav.innerHTML = "";

  NAVS.forEach(function(n){
    var active = n.label === curPage;
    var btn = document.createElement("button");
    if(active){
      btn.className = "active";
      btn.style.cssText = "background:"+p.activeCard+";color:#0f172a;"
        +"border-color:"+p.activeBorder+";box-shadow:0 3px 12px rgba("+p.shadow+",0.15);";
    }

    /* ── Platform brand badge ── */
    var platBadge = document.createElement("span");
    platBadge.className = "plat";
    platBadge.style.background = p.bg;
    if(active) platBadge.style.boxShadow = "0 2px 8px rgba("+p.shadow+",0.50)";
    platBadge.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24">'+p.svg+'</svg>';
    btn.appendChild(platBadge);

    /* ── Action icon tile ── */
    var ico = document.createElement("span");
    ico.className = "ico";
    ico.style.background = p.bg;
    if(active) ico.style.boxShadow = "0 3px 10px rgba("+p.shadow+",0.45)";
    ico.innerHTML = '<svg width="15" height="15" viewBox="0 0 24 24">'+n.icon+'</svg>';
    btn.appendChild(ico);

    btn.appendChild(document.createTextNode(n.label));
    btn.onclick = (function(lbl){return function(){
      msg("streamlit:setComponentValue",{value:lbl,dataType:"json"});
    };})(n.label);
    nav.appendChild(btn);
  });

  msg("streamlit:setFrameHeight",{height:document.body.scrollHeight+4});
}

window.addEventListener("message",function(e){
  if(e.data.type==="streamlit:render"){
    var a = e.data.args||{};
    render(a.platform, a.page);
  }
});
msg("streamlit:componentReady");
</script></body></html>
""", encoding="utf-8")

        @st.cache_resource
        def _get_nav_component():
            return _comp.declare_component("pm_nav_menu", path=str(_NAV_DIR))

        _nav_selector = _get_nav_component()
        _nav_labels = ["Dashboard", "Create Post", "CEO Approval", "Settings"]
        if "nav_page" not in st.session_state or st.session_state["nav_page"] not in _nav_labels:
            st.session_state["nav_page"] = "Dashboard"

        _chosen_page = _nav_selector(
            platform=_cur_plat,
            page=st.session_state["nav_page"],
            key="pm_nav_sel",
            default=st.session_state["nav_page"],
        )
        if _chosen_page and _chosen_page != st.session_state["nav_page"]:
            st.session_state["nav_page"] = _chosen_page
            st.rerun()

        page = st.session_state["nav_page"]
        st.markdown("---")

    current_platform = st.session_state.get("platform", "LinkedIn")

    # ── Inject platform-specific theme into main content area ──────────────
    _PLAT_THEMES = {
        "LinkedIn": {
            "primary":      "#0a66c2",
            "primary_2":    "#004182",
            "accent":       "#378fe9",
            "rgb":          "10,102,194",
            "btn_bg":       "linear-gradient(135deg,#0a66c2,#378fe9)",
            "btn_hover":    "#004182",
            "label_color":  "#004182",
            "tab_bg":       "rgba(10,102,194,0.10)",
            "tab_border":   "rgba(10,102,194,0.30)",
            "input_border": "rgba(10,102,194,0.35)",
            "input_bg_l":   "rgba(10,102,194,0.08)",
            "select_svg":   "rgba(10,102,194,0.65)",
            "app_bg":       "linear-gradient(135deg,#f0f7ff 0%,#e8f0fe 100%)",
        },
        "Facebook": {
            "primary":      "#1877f2",
            "primary_2":    "#0866ee",
            "accent":       "#42a5f5",
            "rgb":          "24,119,242",
            "btn_bg":       "linear-gradient(135deg,#1877f2,#42a5f5)",
            "btn_hover":    "#0866ee",
            "label_color":  "#0866ee",
            "tab_bg":       "rgba(24,119,242,0.10)",
            "tab_border":   "rgba(24,119,242,0.30)",
            "input_border": "rgba(24,119,242,0.35)",
            "input_bg_l":   "rgba(24,119,242,0.08)",
            "select_svg":   "rgba(24,119,242,0.65)",
            "app_bg":       "linear-gradient(135deg,#f0f4ff 0%,#e7f0fd 100%)",
        },
        "Instagram": {
            "primary":      "#c13584",
            "primary_2":    "#833ab4",
            "accent":       "#f77737",
            "rgb":          "193,53,132",
            "btn_bg":       "linear-gradient(135deg,#833ab4,#c13584,#f77737)",
            "btn_hover":    "#833ab4",
            "label_color":  "#833ab4",
            "tab_bg":       "rgba(193,53,132,0.10)",
            "tab_border":   "rgba(193,53,132,0.30)",
            "input_border": "rgba(193,53,132,0.35)",
            "input_bg_l":   "rgba(193,53,132,0.08)",
            "select_svg":   "rgba(193,53,132,0.65)",
            "app_bg":       "linear-gradient(135deg,#fdf0f8 0%,#f9e8f5 100%)",
        },
    }
    _pt = _PLAT_THEMES.get(current_platform, _PLAT_THEMES["LinkedIn"])
    st.markdown(f"""
<style>
/* ── Platform theme override: {current_platform} ── */
:root {{
  --pm-primary:   {_pt['primary']};
  --pm-primary-2: {_pt['primary_2']};
  --pm-accent:    {_pt['accent']};
}}

/* App background */
.stApp {{
  background: {_pt['app_bg']} !important;
}}

/* Primary buttons (Generate Draft, Publish, etc.) */
button[data-testid="baseButton-primary"],
div[data-testid="stButton"] button[data-testid="baseButton-primary"] {{
  background: {_pt['btn_bg']} !important;
  border-color: {_pt['primary']} !important;
  color: #ffffff !important;
  box-shadow: 0 4px 14px rgba({_pt['rgb']},0.35) !important;
}}
button[data-testid="baseButton-primary"]:hover {{
  background: {_pt['btn_hover']} !important;
  box-shadow: 0 6px 20px rgba({_pt['rgb']},0.45) !important;
}}

/* Widget labels */
label[data-testid="stWidgetLabel"] p {{
  color: {_pt['label_color']} !important;
}}

/* Textarea */
div[data-testid="stTextArea"] textarea {{
  background: linear-gradient(135deg, {_pt['input_bg_l']}, rgba(255,255,255,0.98)) !important;
  border: 1px solid {_pt['input_border']} !important;
}}
div[data-testid="stTextArea"] textarea:focus {{
  border-color: {_pt['primary']} !important;
  box-shadow: 0 0 0 2px rgba({_pt['rgb']},0.15) !important;
}}

/* Text inputs */
div[data-testid="stTextInput"] input {{
  border: 1px solid {_pt['input_border']} !important;
}}
div[data-testid="stTextInput"] input:focus {{
  border-color: {_pt['primary']} !important;
  box-shadow: 0 0 0 2px rgba({_pt['rgb']},0.15) !important;
}}

/* Selectbox */
div[data-testid="stSelectbox"] div[role="combobox"] {{
  border: 1px solid {_pt['input_border']} !important;
  background: linear-gradient(135deg, {_pt['input_bg_l']}, rgba(255,255,255,0.98)) !important;
}}
div[data-testid="stSelectbox"] svg {{
  fill: {_pt['select_svg']} !important;
}}
div[data-testid="stSelectbox"] ul {{
  background: linear-gradient(180deg,rgba(255,255,255,0.98),{_pt['input_bg_l']}) !important;
  border: 1px solid rgba({_pt['rgb']},0.22) !important;
}}

/* Tabs active */
div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {{
  background: {_pt['tab_bg']} !important;
  border: 1px solid {_pt['tab_border']} !important;
  color: {_pt['primary']} !important;
}}
div[data-testid="stTabs"] [data-baseweb="tab-highlight"] {{
  background: {_pt['primary']} !important;
}}

/* Expander header border accent */
div[data-testid="stExpander"] summary:hover {{
  color: {_pt['primary']} !important;
}}

/* Horizontal rule color */
hr {{
  border-color: rgba({_pt['rgb']},0.20) !important;
}}

/* Checkbox & radio accent */
input[type="checkbox"]:checked, input[type="radio"]:checked {{
  accent-color: {_pt['primary']} !important;
}}
</style>
""", unsafe_allow_html=True)
    # ── End platform theme ──────────────────────────────────────────────────

    if page != "Dashboard":
        st.title(page)
        # st.caption(f"Platform: {current_platform}")

    # System validation check (no UI display)

    if page == "Dashboard":
        # Load data for dashboard metrics
        reviews = MarketingAgent.load_approvals(platform=current_platform)
        
        # Calculate Metrics
        pending_count = sum(1 for r in reviews if r.get("status") in ["Pending", "Needs Edit"])
        approved_count = sum(1 for r in reviews if r.get("status") == "Approved")
        
        # For Scheduled/Published/Missed, check log + approvals
        scheduled_count = 0
        published_count = 0
        
        MarketingAgent._migrate_legacy_log()
        log_file = MarketingAgent.published_log_file(current_platform)
        log_data = MarketingAgent._load_json_list(log_file)
                
        current_time = datetime.now()
        
        # Count scheduled from log (authoritative source for time)
        for item in log_data:
            status = item.get("status")
            if status == "Scheduled":
                try:
                    sched_time_str = item.get("scheduled_for")
                    if sched_time_str:
                        sched_time = datetime.strptime(sched_time_str, "%Y-%m-%d %H:%M:%S")
                        if sched_time > current_time:
                            scheduled_count += 1
                except:
                    pass
            elif status and ("Published" in str(status) or "Auto-published" in str(status)):
                published_count += 1

        platform_icon_class = "pm-platform-icon--linkedin"
        if current_platform == "Facebook":
            platform_icon_class = "pm-platform-icon--facebook"
        elif current_platform == "Instagram":
            platform_icon_class = "pm-platform-icon--instagram"

        st.markdown(
            f"""
            <div class="pm-platform-heading">
              <span class="pm-platform-icon {platform_icon_class}"></span>
              <span class="pm-platform-heading-text">{current_platform}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        
        m1, m2, m3, m4 = st.columns(4)
        
        with m1:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Pending Posts</div>
                <div class="metric-value">{pending_count}</div>
                <div class="metric-subtext">Waiting for approval</div>
            </div>
            """, unsafe_allow_html=True)
            
        with m2:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Approved Posts</div>
                <div class="metric-value">{approved_count}</div>
                <div class="metric-subtext">Ready to schedule</div>
            </div>
            """, unsafe_allow_html=True)
            
        with m3:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Scheduled Posts</div>
                <div class="metric-value">{scheduled_count}</div>
                <div class="metric-subtext">Upcoming</div>
            </div>
            """, unsafe_allow_html=True)
            
        with m4:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">Published Posts</div>
                <div class="metric-value">{published_count}</div>
                <div class="metric-subtext">Live on {current_platform}</div>
            </div>
            """, unsafe_allow_html=True)
            
        # st.markdown("### 🔔 Automation Alerts")
        
        if pending_count > 0:
            st.warning(f"⚠️ {pending_count} posts waiting for CEO approval")
            
        if approved_count > 0:
            st.success(f"✅ {approved_count} posts approved and ready for publishing")
            
        if scheduled_count > 0:
            st.info(f"📅 {scheduled_count} future posts scheduled")
            
        if pending_count == 0 and approved_count == 0 and scheduled_count == 0 and published_count == 0:
            st.caption("All caught up! No pending actions.")

        # ── Activity ──────────────────────────────────────────────────────────
        st.markdown("<div style='margin-top:2.5rem'></div>", unsafe_allow_html=True)
        st.markdown("---")
        st.subheader("Activity")
        MarketingAgent._migrate_legacy_log()
        history = MarketingAgent._load_json_list(MarketingAgent.published_log_file(current_platform))

        published_posts = [item for item in history if item.get("status") != "Scheduled"]
        scheduled_posts = [item for item in history if item.get("status") == "Scheduled"]

        with st.expander(f"Published ({len(published_posts)})", expanded=False):
            if published_posts:
                for item in reversed(published_posts):
                    display_time = item.get("published_at") or item.get("queued_at") or item.get("time")
                    with st.expander(f"Posted at {display_time}", expanded=False):
                        st.text(item.get("content", ""))
                        image_path = item.get("image_path")
                        video_path = item.get("video_path")
                        if image_path and os.path.exists(image_path):
                            try:
                                render_hq_image(image_path, width=500)
                            except Exception:
                                st.warning(f"Could not load image: {image_path}")
                        if video_path and os.path.exists(video_path):
                            try:
                                st.video(video_path, format="video/mp4")
                            except Exception:
                                st.warning(f"Could not load video: {video_path}")
                        st.caption(f"Status: {item.get('status', '')}")
            else:
                st.caption("No published posts yet.")

        with st.expander(f"Scheduled ({len(scheduled_posts)})", expanded=False):
            if scheduled_posts:
                for item in reversed(scheduled_posts):
                    sched_time = item.get("scheduled_for", "N/A")
                    status_badge = "📅 Scheduled"
                    time_info = ""
                    try:
                        scheduled_time = datetime.strptime(sched_time, "%Y-%m-%d %H:%M:%S")
                        time_remaining = scheduled_time - datetime.now()
                        if time_remaining.total_seconds() > 0:
                            status_badge = "⏰ Scheduled"
                            time_info = f"Publishes in: {str(time_remaining).split('.')[0]}"
                        else:
                            status_badge = "⚠️ Ready"
                            time_info = "Will be sent on next scheduler check."
                    except Exception:
                        pass

                    with st.expander(f"{status_badge} | For: {sched_time}", expanded=False):
                        if time_info:
                            st.caption(time_info)
                        st.text(item.get("content", ""))
                        image_path = item.get("image_path")
                        video_path = item.get("video_path")
                        if image_path and os.path.exists(image_path):
                            try:
                                render_hq_image(image_path, width=500)
                            except Exception:
                                st.warning(f"Could not load image: {image_path}")
                        if video_path and os.path.exists(video_path):
                            try:
                                st.video(video_path, format="video/mp4")
                            except Exception:
                                st.warning(f"Could not load video: {video_path}")
                        created_time = item.get("time")
                        if created_time:
                            st.caption(f"Created: {created_time}")
            else:
                st.caption("No scheduled posts.")

    def _sorted_reviews():
        current_platform = st.session_state.get("platform", "LinkedIn")
        recs = MarketingAgent.load_approvals(platform=current_platform)
        def _key(x):
            return x.get("created_at", "")
        return sorted(recs, key=_key, reverse=True)

    if page == "Create Post":
        # st.subheader("Drafts")

        # Shared active content for other tabs (analytics/visual, etc.)
        st.session_state['active_post_content'] = None
        st.session_state['active_post_pin'] = None

        col_left, col_right = st.columns([2, 7])
        with col_left:
            default_topic = st.session_state.get("draft_topic", "")
            topic = st.text_area("Post Topic", value=default_topic, placeholder="e.g. Why Odoo Migration Fails", height=72)
            if "tone_input" not in st.session_state:
                st.session_state["tone_input"] = "Professional"
            tone = st.text_input("Tone", key="tone_input")

            if "draft_generate_in_progress" not in st.session_state:
                st.session_state["draft_generate_in_progress"] = False
            if "draft_generate_pending" not in st.session_state:
                st.session_state["draft_generate_pending"] = False

            if st.button("Generate Draft", type="primary", use_container_width=True, key="draft_generate", disabled=st.session_state["draft_generate_in_progress"]):
                st.session_state["draft_generate_pending"] = True
                st.session_state["draft_generate_in_progress"] = True
                st.rerun()

            if st.session_state.get("draft_generate_pending"):
                st.session_state["draft_generate_pending"] = False
                if not (topic or "").strip():
                    st.warning("Please enter a topic.")
                elif not api_key:
                    st.error("Please provide an API Key in settings or .env file.")
                else:
                    try:
                        agent = MarketingAgent(api_key)
                        platform_name = st.session_state.get("platform", "LinkedIn")
                        _draft_step = st.empty()
                        for _msg, _delay in (
                            ("🔍 Researching competitor content strategies...", 3.5),
                            ("📊 Analysing trending Odoo market topics...", 3.5),
                            ("🧠 Crafting engaging narrative structure...", 3.5),
                            ("✍️ Writing platform-optimised content...", 3.5),
                            ("✨ Polishing final draft...", 3.0),
                        ):
                            _draft_step.markdown(
                                f"""
                                <div style="display:flex;align-items:center;gap:10px;">
                                  <span style="width:18px;height:18px;border:2px solid #cbd5e1;border-top-color:#0a66c2;border-radius:50%;display:inline-block;animation:pmspin 0.9s linear infinite;"></span>
                                  <span style="font-size:0.95rem;">{_msg}</span>
                                </div>
                                <style>@keyframes pmspin{{from{{transform:rotate(0deg)}}to{{transform:rotate(360deg)}}}}</style>
                                """,
                                unsafe_allow_html=True,
                            )
                            time_module.sleep(_delay)
                        draft = agent.generate((topic or "").strip(), tone, platform=platform_name)
                        pin = MarketingAgent.generate_pin()
                        if MarketingAgent.save_review(draft, pin, status="Draft", platform=platform_name):
                            _draft_step.markdown(
                                "<div style=\"display:flex;align-items:center;gap:10px;\"><span style=\"font-size:0.95rem;\">✅ Draft created successfully!</span></div>",
                                unsafe_allow_html=True,
                            )
                            st.session_state['selected_pin'] = None
                            st.rerun()
                        else:
                            _draft_step.empty()
                            st.error("Could not save draft")
                    except Exception as e:
                        st.error(f"PIN generation error: {str(e)}")
                    finally:
                        st.session_state["draft_generate_in_progress"] = False

        with col_right:
            reviews = _sorted_reviews()
            pins = [r.get("pin") for r in reviews if r.get("pin")]
            pin_to_index = {p: i + 1 for i, p in enumerate(reversed(pins))}

            def _label_for_pin(p):
                rec = next((x for x in reviews if x.get("pin") == p), None)
                if not rec:
                    return f"Post {pin_to_index.get(p, '-')}"
                post_label = f"Post {pin_to_index.get(p, '-')}"
                return f"{post_label} | {rec.get('created_at','')} | {rec.get('status','')}"

            if pins:
                selected_pin = st.selectbox(
                    "Select draft",
                    options=pins,
                    index=None,
                    format_func=_label_for_pin,
                    key="selected_pin",
                    placeholder="Select draft",
                )
            else:
                selected_pin = None
                st.caption("No drafts yet — create one using the form on the left.")

            # Per-draft editor nonce: used to force Streamlit to recreate the widget and
            # rehydrate content from disk on refresh.
            editor_nonce_key = f"user_editor_nonce_{selected_pin}" if selected_pin else None
            if editor_nonce_key and editor_nonce_key not in st.session_state:
                st.session_state[editor_nonce_key] = 0

            # Load the draft record first to have content available for buttons
            rec = MarketingAgent.load_review_by_pin(selected_pin) if selected_pin else None
            draft_content = rec.get("content", "") if rec else ""
            
            # Check if user can edit (for button disabling)
            status = rec.get("status", "Draft") if rec else "Draft"
            user_can_edit = status in ("Draft", "Needs Edit")
            is_terminal = status in ("Scheduled", "Published")
            has_draft_selected = bool(selected_pin and (draft_content or "").strip())

            # Pre-build copy prompts into cache (only for editable drafts, skip Published/Scheduled)
            import html as _html
            _platform_name_pre = st.session_state.get("platform", "LinkedIn")
            _copy_cache_key = f"_copy_prompts_{selected_pin}_{_platform_name_pre}_{hash(draft_content or '')}"
            if has_draft_selected and user_can_edit and _copy_cache_key not in st.session_state:
                with st.spinner("Preparing copy prompts…"):
                    try:
                        _pm = get_platform_module(_platform_name_pre)
                        _bc = _get_brand_context_cached(api_key) if api_key else {}
                        _sp = _build_style_prompt(_bc)
                        st.session_state[_copy_cache_key] = (
                            _html.escape(f"Generate a professional {_platform_name_pre} image for this post:\n\nPOST CONTENT:\n{draft_content}\n\n---\nDESIGN REQUIREMENTS:\n{_pm.build_image_prompt(draft_content, _sp)}"),
                            _html.escape(f"Generate a professional {_platform_name_pre} video for this post:\n\nPOST CONTENT:\n{draft_content}\n\n---\nDESIGN REQUIREMENTS:\n{_pm.build_video_prompt(draft_content, _sp)}"),
                        )
                    except Exception:
                        pass

            # Set active content before buttons so it's available
            if rec:
                st.session_state['active_post_content'] = draft_content
                st.session_state['active_post_pin'] = str(selected_pin)

            # Initialize toggle state for uploaders
            if "show_uploaders" not in st.session_state:
                st.session_state["show_uploaders"] = False

            # Use 3 columns for the main action buttons
            col_generate_img, col_generate_vid, col_upload_toggle = st.columns([1, 1, 1])
            
            with col_generate_img:
                if st.button("🖼️ Generate", use_container_width=True, disabled=((not user_can_edit) or (not has_draft_selected)), help="Generate a LinkedIn-optimized image for this post", key="media_generate_image"):
                    if not draft_content:
                        st.warning("Load a draft first")
                    elif not selected_pin:
                        st.warning("No draft selected")
                    elif not api_key:
                        st.error("API Key required in settings")
                    else:
                        agent = MarketingAgent(api_key)
                        brand_context = _get_brand_context_cached(api_key)
                        st.session_state["last_media_context"] = brand_context
                        st.session_state["last_media_error"] = None
                        _img_step = st.empty()
                        for message, delay in (
                            ("🔍 Researching ODOO competitor Posts...", 6.0),
                            ("📊 Scanning latest Odoo market data...", 6.0),
                            ("🧠 Analysing strategies to beat ERP competitors...", 6.0),
                            ("🧩 Mapping visual hierarchy & layout...", 6.0),
                            ("✍️ Refining headline & key message...", 6.0),
                            ("🎨 Designing brand-aligned visual...", 6.0),
                            ("✨ Polishing final image for LinkedIn...", 6.0),
                        ):
                            _img_step.markdown(
                                f"""
                                <div style="display:flex;align-items:center;gap:10px;">
                                  <span style="width:18px;height:18px;border:2px solid #cbd5e1;border-top-color:#0a66c2;border-radius:50%;display:inline-block;animation:pmspin 0.9s linear infinite;"></span>
                                  <span style="font-size:0.95rem;">{message}</span>
                                </div>
                                <style>@keyframes pmspin{{from{{transform:rotate(0deg)}}to{{transform:rotate(360deg)}}}}</style>
                                """,
                                unsafe_allow_html=True,
                            )
                            time_module.sleep(delay)
                        image_data = agent.generate_post_image(draft_content, brand_context=brand_context, platform=st.session_state.get("platform", "LinkedIn"))
                        if image_data:
                            _img_step.markdown(
                                "<div style=\"display:flex;align-items:center;gap:10px;\"><span style=\"font-size:0.95rem;\">✅ Image optimised and ready!</span></div>",
                                unsafe_allow_html=True,
                            )
                        else:
                            _img_step.markdown(
                                "<div style=\"display:flex;align-items:center;gap:10px;\"><span style=\"font-size:0.95rem;\">❌ Generation failed</span></div>",
                                unsafe_allow_html=True,
                            )
                        if image_data:
                            st.session_state['generated_image'] = image_data
                            # Save image to disk with PIN
                            MarketingAgent.update_review(selected_pin, image_bytes=image_data)
                            st.rerun()
                        else:
                            err = st.session_state.get("last_media_error")
                            st.error(err or "Generation failed. Try again or use manual tools.")

            with col_generate_vid:
                if st.button("🎞️ Video", use_container_width=True, disabled=((not user_can_edit) or (not has_draft_selected)), help="Generate a short LinkedIn-ready MP4 video for this post", key="media_generate_video"):
                    if not draft_content:
                        st.warning("Load a draft first")
                    elif not selected_pin:
                        st.warning("No draft selected")
                    elif not api_key:
                        st.error("API Key required in settings")
                    else:
                        agent = MarketingAgent(api_key)
                        brand_context = _get_brand_context_cached(api_key)
                        st.session_state["last_media_context"] = brand_context
                        st.session_state["last_media_error"] = None
                        _vid_step = st.empty()
                        for message, delay in (
                            ("🔍 Researching competitor content angles...", 6.0),
                            ("📰 Gathering fresh market intelligence...", 6.0),
                            ("🧠 Structuring the story flow...", 6.0),
                            ("✍️ Scripting motion, transitions & hooks...", 6.0),
                            ("🎨 Designing on-screen visuals...", 6.0),
                            ("🏆 Correcting messaging to outperform Odoo rivals...", 6.0),
                            ("🎬 Rendering video for LinkedIn...", 6.0),
                        ):
                            _vid_step.markdown(
                                f"""
                                <div style="display:flex;align-items:center;gap:10px;">
                                  <span style="width:18px;height:18px;border:2px solid #cbd5e1;border-top-color:#0a66c2;border-radius:50%;display:inline-block;animation:pmspin 0.9s linear infinite;"></span>
                                  <span style="font-size:0.95rem;">{message}</span>
                                </div>
                                <style>@keyframes pmspin{{from{{transform:rotate(0deg)}}to{{transform:rotate(360deg)}}}}</style>
                                """,
                                unsafe_allow_html=True,
                            )
                            time_module.sleep(delay)
                        video_bytes = agent.generate_post_video(draft_content, brand_context=brand_context, platform=st.session_state.get("platform", "LinkedIn"))
                        if video_bytes:
                            _vid_step.markdown(
                                "<div style=\"display:flex;align-items:center;gap:10px;\"><span style=\"font-size:0.95rem;\">✅ Video optimised and ready!</span></div>",
                                unsafe_allow_html=True,
                            )
                        else:
                            _vid_step.markdown(
                                "<div style=\"display:flex;align-items:center;gap:10px;\"><span style=\"font-size:0.95rem;\">❌ Generation failed</span></div>",
                                unsafe_allow_html=True,
                            )
                        if video_bytes:
                            st.session_state["generated_video"] = video_bytes
                            MarketingAgent.update_review(selected_pin, video_bytes=video_bytes)
                            st.rerun()
                        else:
                            err = st.session_state.get("last_media_error")
                            st.error(err or "Video generation failed. Try again.")

            with col_upload_toggle:
                toggle_label = "📤 Hide Upload" if st.session_state["show_uploaders"] else "📤 Upload"
                if st.button(toggle_label, use_container_width=True, disabled=((not user_can_edit) or (not has_draft_selected)), key="media_upload_toggle"):
                    st.session_state["show_uploaders"] = not st.session_state["show_uploaders"]
                    st.rerun()

            # Conditional row for uploaders
            if st.session_state["show_uploaders"]:
                import streamlit.components.v1 as _components

                # Read pre-built prompts from cache (built during render above — instant)
                if has_draft_selected and _copy_cache_key in st.session_state:
                    _copy_img_text, _copy_vid_text = st.session_state[_copy_cache_key]
                    _btn_img_disabled = ""
                    _btn_vid_disabled = ""
                    _btn_style = "background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;cursor:pointer;"
                    _btn_grey  = "background:#cccccc;color:#888;cursor:not-allowed;"
                else:
                    _copy_img_text = _copy_vid_text = ""
                    _btn_img_disabled = _btn_vid_disabled = "disabled"
                    _btn_style = _btn_grey = "background:#cccccc;color:#888;cursor:not-allowed;"

                _BTN_BASE = "width:100%;padding:0.35rem 0.5rem;border:none;border-radius:0.35rem;font-size:0.83rem;font-weight:600;box-shadow:0 2px 4px rgba(0,0,0,0.12);"
                _IFRAME_STYLE = "<style>*{box-sizing:border-box}body{margin:0;padding:0;overflow:hidden;background:transparent}</style>"

                col_add_img, col_add_vid = st.columns([1, 1])

                with col_add_img:
                    if not (selected_pin and user_can_edit):
                        st.button("➕ Image", use_container_width=True, disabled=True, key="media_add_image_disabled")
                    else:
                        img_nonce_key = f"upload_img_nonce_{selected_pin}"
                        img_nonce = int(st.session_state.get(img_nonce_key, 0))
                        uploaded_image = st.file_uploader(
                            "➕ Image",
                            type=["png", "jpg", "jpeg"],
                            key=f"upload_img_{selected_pin}_{img_nonce}",
                            label_visibility="collapsed",
                        )
                        if uploaded_image is not None:
                            img_bytes = uploaded_image.getvalue()
                            if img_bytes and len(img_bytes) > 10:
                                last_key = f"last_attached_img_meta_{selected_pin}"
                                meta = (getattr(uploaded_image, "name", ""), getattr(uploaded_image, "size", None))
                                if st.session_state.get(last_key) != meta:
                                    st.session_state[last_key] = meta
                                    st.session_state["generated_image"] = img_bytes
                                    MarketingAgent.update_review(selected_pin, image_bytes=img_bytes)
                                    st.session_state[img_nonce_key] = img_nonce + 1
                                    st.rerun()
                    # Copy Image Prompt button — iframe with no body margin
                    _components.html(f"""{_IFRAME_STYLE}
                        <textarea id="pm_img_text" style="display:none">{_copy_img_text}</textarea>
                        <button {_btn_img_disabled}
                            onclick="var t=document.getElementById('pm_img_text').value;navigator.clipboard.writeText(t).then(function(){{this.innerHTML='&#x2705; Copied!';var b=this;setTimeout(function(){{b.innerHTML='&#x1F4CB; Copy for Manual Image'}},2000)}}.bind(this)).catch(function(){{alert('Copy failed')}})"
                            style="{_BTN_BASE}{_btn_style if not _btn_img_disabled else _btn_grey}">
                            &#x1F4CB; Copy for Manual Image
                        </button>
                    """, height=36)

                with col_add_vid:
                    if not (selected_pin and user_can_edit):
                        st.button("➕ Video", use_container_width=True, disabled=True, key="media_add_video_disabled")
                    else:
                        vid_nonce_key = f"upload_vid_nonce_{selected_pin}"
                        vid_nonce = int(st.session_state.get(vid_nonce_key, 0))
                        uploaded_video = st.file_uploader(
                            "➕ Video",
                            type=["mp4", "mov", "m4v", "webm"],
                            key=f"upload_vid_{selected_pin}_{vid_nonce}",
                            label_visibility="collapsed",
                        )
                        if uploaded_video is not None:
                            vid_bytes = uploaded_video.getvalue()
                            if vid_bytes and len(vid_bytes) > 10:
                                last_key = f"last_attached_vid_meta_{selected_pin}"
                                meta = (getattr(uploaded_video, "name", ""), getattr(uploaded_video, "size", None))
                                if st.session_state.get(last_key) != meta:
                                    st.session_state[last_key] = meta
                                    st.session_state["generated_video"] = vid_bytes
                                    MarketingAgent.update_review(selected_pin, video_bytes=vid_bytes)
                                    st.session_state[vid_nonce_key] = vid_nonce + 1
                                    st.rerun()
                    # Copy Video Prompt button — iframe with no body margin
                    _components.html(f"""{_IFRAME_STYLE}
                        <textarea id="pm_vid_text" style="display:none">{_copy_vid_text}</textarea>
                        <button {_btn_vid_disabled}
                            onclick="var t=document.getElementById('pm_vid_text').value;navigator.clipboard.writeText(t).then(function(){{this.innerHTML='&#x2705; Copied!';var b=this;setTimeout(function(){{b.innerHTML='&#x1F4CB; Copy for Manual Video'}},2000)}}.bind(this)).catch(function(){{alert('Copy failed')}})"
                            style="{_BTN_BASE}{_btn_style if not _btn_vid_disabled else _btn_grey}">
                            &#x1F4CB; Copy for Manual Video
                        </button>
                    """, height=36)

            if rec:
                st.caption(f"Status: {status}")

                # Load saved image only if it's for the current PIN (avoid showing wrong image)
                current_image_path = rec.get("current_image")
                last_loaded_pin = st.session_state.get('last_loaded_image_pin')
                
                # Only load image if we haven't loaded it yet for this PIN, or if PIN changed
                if current_image_path and os.path.exists(current_image_path):
                    if last_loaded_pin != selected_pin:
                        try:
                            with open(current_image_path, "rb") as img_file:
                                st.session_state['generated_image'] = img_file.read()
                                st.session_state['last_loaded_image_pin'] = selected_pin
                        except Exception:
                            pass
                elif last_loaded_pin != selected_pin:
                    # Different PIN and no saved image - clear the generated image
                    if 'generated_image' in st.session_state:
                        del st.session_state['generated_image']
                    st.session_state['last_loaded_image_pin'] = selected_pin

                current_video_path = rec.get("current_video")
                last_loaded_video_pin = st.session_state.get("last_loaded_video_pin")
                if current_video_path and os.path.exists(current_video_path):
                    if last_loaded_video_pin != selected_pin:
                        try:
                            with open(current_video_path, "rb") as vid_file:
                                st.session_state["generated_video"] = vid_file.read()
                                st.session_state["last_loaded_video_pin"] = selected_pin
                        except Exception:
                            pass
                elif last_loaded_video_pin != selected_pin:
                    if "generated_video" in st.session_state:
                        del st.session_state["generated_video"]
                    st.session_state["last_loaded_video_pin"] = selected_pin

                updated_at = (rec.get("updated_at") or rec.get("created_at") or "").strip()
                last_seen_key = f"user_last_seen_updated_{selected_pin}"
                if updated_at and st.session_state.get(last_seen_key) != updated_at:
                    st.session_state[last_seen_key] = updated_at
                    if editor_nonce_key:
                        st.session_state[editor_nonce_key] = int(st.session_state.get(editor_nonce_key, 0)) + 1

                editor_nonce = int(st.session_state.get(editor_nonce_key, 0)) if editor_nonce_key else 0
                edited = st.text_area(
                    "Draft content",
                    value=rec.get("content", ""),
                    height=280,
                    key=f"user_draft_editor_{selected_pin}_{editor_nonce}",
                    disabled=(not user_can_edit),
                )

                # Make this draft available to other tabs as the active draft
                st.session_state['active_post_content'] = edited
                st.session_state['active_post_pin'] = str(selected_pin)

                has_unsaved_changes = (edited or "") != (rec.get("content", "") or "")
                if status in ("Pending", "Needs Edit", "Approved"):
                    _autorefresh(8000 if status in ("Pending", "Needs Edit") else 10000)
                
                char_count = len(edited)
                platform_name = st.session_state.get("platform", "LinkedIn")

                if platform_name == "Instagram":
                    limit = 2200
                    warning_limit = 2000
                elif platform_name == "Facebook":
                    limit = 63206
                    warning_limit = 60000
                else:
                    limit = 3000
                    warning_limit = 2800
                
                if char_count > limit:
                    st.error(f"⚠️ Content EXCEEDS {platform_name} limit! Current: {char_count}/{limit} characters (Reduce by {char_count - limit} chars)")
                elif char_count > warning_limit:
                    st.warning(f"⚠️ Content approaching {platform_name} limit. Current: {char_count}/{limit} characters (Only {limit - char_count} chars remaining)")
                else:
                    st.caption(f"Character count: {char_count}/{limit} ({limit - char_count} remaining)")
                
                # Display saved media preview if available (always expanded)
                img_bytes = st.session_state.get('generated_image')
                if img_bytes and len(img_bytes) > 10:
                    with st.expander("Image", expanded=False):
                        try:
                            from PIL import Image
                            import io
                            image = Image.open(io.BytesIO(img_bytes))
                            
                            # Small preview
                            col_img, col_actions = st.columns([3, 1])
                            with col_img:
                                render_hq_image(image, width=500)
                            with col_actions:
                                st.download_button(
                                    label="Download",
                                    data=img_bytes,
                                    file_name=f"pin_{selected_pin}_image.png",
                                    mime="image/png",
                                    use_container_width=True
                                )
                                
                                if st.button("🗑️ Remove", use_container_width=True, disabled=(not user_can_edit), key=f"remove_img_{selected_pin}"):
                                    MarketingAgent.update_review(selected_pin, image_bytes=b"")
                                    st.session_state.pop('generated_image', None)
                                    st.rerun()
                                    
                        except Exception as e:
                            st.caption(f"Image exists but preview failed: {str(e)}")
                            # Clear bad bytes so we don't show a stray placeholder
                            if 'generated_image' in st.session_state:
                                del st.session_state['generated_image']
                
                vid_bytes = st.session_state.get("generated_video")
                if vid_bytes and len(vid_bytes) > 10:
                    with st.expander("Video", expanded=False):
                        st.video(vid_bytes, format="video/mp4")
                        col_v_down, col_v_clear = st.columns([1, 1])
                        with col_v_down:
                            st.download_button(
                                label="Download",
                                data=vid_bytes,
                                file_name=f"pin_{selected_pin}_video.mp4",
                                mime="video/mp4",
                                use_container_width=True,
                            )
                        with col_v_clear:
                            if st.button("🗑️ Remove", use_container_width=True, disabled=(not user_can_edit), key=f"remove_vid_{selected_pin}"):
                                MarketingAgent.update_review(selected_pin, video_bytes=b"")
                                st.session_state.pop("generated_video", None)
                                st.rerun()

                col_save, col_send_ceo, col_remind = st.columns([1, 1, 1])
                with col_save:
                    if st.button("Save", use_container_width=True, disabled=(not user_can_edit), key=f"user_save_{selected_pin}"):
                        # Save both content and image if available
                        image_bytes = st.session_state.get('generated_image')
                        video_bytes = st.session_state.get("generated_video")
                        MarketingAgent.update_review(selected_pin, content=edited, image_bytes=image_bytes, video_bytes=video_bytes)
                        st.success("Saved")
                        st.rerun()

                with col_send_ceo:
                    char_count = len(edited)
                    send_disabled = (not user_can_edit) or (not st.session_state.get('email_enabled', False)) or (char_count > 3000)
                    send_button_label = "Send to CEO" if char_count <= 3000 else "❌ Over Limit"
                    
                    if st.button(send_button_label, use_container_width=True, disabled=send_disabled, key=f"send_ceo_{selected_pin}"):
                        agent = MarketingAgent(api_key or "dummy")
                        with st.spinner("Sending to CEO..."):
                            ok, msg = agent.send_approval_email(
                                st.session_state.get('ceo_email', ''),
                                edited,
                                st.session_state.get('sender_email', ''),
                                st.session_state.get('sender_password', ''),
                                verification_pin=str(selected_pin),
                            )
                        if ok:
                            # Lock it after successful send
                            MarketingAgent.update_review(selected_pin, content=edited, status="Pending")
                            st.rerun()
                        else:
                            st.error(f"Could not send: {msg}")

                with col_remind:
                    email_ready = bool(st.session_state.get('email_enabled', False))

                    # Remind or resend based on status
                    button_label = "Resend to CEO" if status == "Needs Edit" else "Send Reminder"
                    reminder_disabled = (status not in ["Pending", "Needs Edit"]) or (not email_ready)
                    
                    if st.button(button_label, use_container_width=True, disabled=reminder_disabled, key=f"user_remind_{selected_pin}"):
                        agent = MarketingAgent(api_key or "dummy")
                        action_text = "Resending to CEO" if status == "Needs Edit" else "Sending reminder to CEO"
                        with st.spinner(f"{action_text}..."):
                            # Check if resend vs reminder
                            is_reminder = (status == "Pending")
                            ok, msg = agent.send_approval_email(
                                st.session_state.get('ceo_email', ''),
                                edited,
                                st.session_state.get('sender_email', ''),
                                st.session_state.get('sender_password', ''),
                                verification_pin=str(selected_pin),
                                is_reminder=is_reminder,
                            )
                        if ok:
                            # Update status back to Pending
                            if status == "Needs Edit":
                                MarketingAgent.update_review(selected_pin, content=edited, status="Pending")
                            st.rerun()
                        else:
                            st.error(f"Could not send: {msg}")

                if status == "Pending":
                    st.caption("Sent to CEO. Waiting for approval.")
                if status == "Rejected":
                    st.error("Rejected by CEO. Editing and resending are locked.")

                # After approval, allow scheduling/publishing from user side
                if status == "Approved" and not is_terminal:
                    st.markdown("---")
                    action = st.radio(
                        "Action",
                        options=["Schedule", "Publish"],
                        horizontal=True,
                        key=f"user_action_{selected_pin}",
                    )
                    scheduled_time = None
                    if action == "Schedule":
                        default_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        scheduled_time = st.text_input(
                            "Scheduled date & time",
                            value=st.session_state.get(f"user_schedule_dt_{selected_pin}", default_datetime),
                            key=f"user_schedule_dt_{selected_pin}",
                        )
                        try:
                            datetime.strptime(scheduled_time, "%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            scheduled_time = None
                            st.error("Invalid format! Use: YYYY-MM-DD HH:MM:SS")

                    if st.button("Confirm", type="primary", use_container_width=True, disabled=is_terminal or c, key=f"user_confirm_{selected_pin}"):
                        if not edited:
                            st.error("Content cannot be empty")
                        elif action == "Publish":
                            platform_name = st.session_state.get("platform", "LinkedIn")
                            agent = MarketingAgent(api_key or "dummy")

                            if st.session_state.get('generated_image'):
                                MarketingAgent.update_review(selected_pin, image_bytes=st.session_state['generated_image'])
                            if st.session_state.get('generated_video'):
                                MarketingAgent.update_review(selected_pin, video_bytes=st.session_state['generated_video'])

                            rec = MarketingAgent.load_review_by_pin(selected_pin)
                            image_path = rec.get('current_image') if rec else None
                            video_path = rec.get('current_video') if rec else None

                            if platform_name == "LinkedIn":
                                member_id_to_use = member_id
                                if not linkedin_token or not member_id_to_use:
                                    st.error("LinkedIn credentials required")
                                else:
                                    image_bytes = None
                                    if image_path and os.path.exists(image_path):
                                        with open(image_path, 'rb') as f:
                                            image_bytes = f.read()

                                    video_bytes = None
                                    if video_path and os.path.exists(video_path):
                                        with open(video_path, 'rb') as f:
                                            video_bytes = f.read()

                                    if video_bytes:
                                        success, message = agent.publish_to_linkedin_with_video(
                                            edited,
                                            video_bytes,
                                            linkedin_token,
                                            member_id_to_use
                                        )
                                    elif image_bytes:
                                        success, message = agent.publish_to_linkedin_with_image(
                                            edited,
                                            image_bytes,
                                            linkedin_token,
                                            member_id_to_use
                                        )
                                    else:
                                        success, message = agent.publish_to_linkedin(edited, linkedin_token, member_id_to_use)

                                    if success:
                                        agent.save_to_log(edited, message, image_path=image_path, video_path=video_path, platform=platform_name)
                                        MarketingAgent.update_review(selected_pin, content=edited, status="Published")
                                        if video_path:
                                            st.success("Published with video!")
                                        elif image_path:
                                            st.success("Published with image!")
                                        else:
                                            st.success("Published!")
                                        st.rerun()
                                    else:
                                        st.error(message)
                            elif platform_name == "Facebook":
                                if not facebook_token or not facebook_page_id:
                                    st.error("Facebook credentials required")
                                else:
                                    image_bytes = None
                                    if image_path and os.path.exists(image_path):
                                        with open(image_path, 'rb') as f:
                                            image_bytes = f.read()

                                    video_bytes = None
                                    if video_path and os.path.exists(video_path):
                                        with open(video_path, 'rb') as f:
                                            video_bytes = f.read()

                                    if video_bytes:
                                        success, message = agent.publish_to_facebook_with_video(edited, video_bytes, facebook_token, facebook_page_id)
                                    elif image_bytes:
                                        success, message = agent.publish_to_facebook_with_image(edited, image_bytes, facebook_token, facebook_page_id)
                                    else:
                                        success, message = agent.publish_to_facebook(edited, facebook_token, facebook_page_id)

                                    if success:
                                        agent.save_to_log(edited, message, image_path=image_path, video_path=video_path, platform=platform_name)
                                        MarketingAgent.update_review(selected_pin, content=edited, status="Published")
                                        st.success(message)
                                        st.rerun()
                                    else:
                                        st.error(message)
                            else:
                                if not instagram_token or not instagram_user_id:
                                    st.error("Instagram credentials required")
                                else:
                                    image_bytes = None
                                    if image_path and os.path.exists(image_path):
                                        with open(image_path, 'rb') as f:
                                            image_bytes = f.read()

                                    video_bytes = None
                                    if video_path and os.path.exists(video_path):
                                        with open(video_path, 'rb') as f:
                                            video_bytes = f.read()

                                    success, message = agent.publish_to_instagram(
                                        edited,
                                        access_token=instagram_token,
                                        user_id=instagram_user_id,
                                        image_bytes=image_bytes,
                                        video_bytes=video_bytes,
                                        facebook_access_token=instagram_token,
                                        facebook_page_id=instagram_facebook_page_id,
                                    )
                                    if success:
                                        agent.save_to_log(edited, message, image_path=image_path, video_path=video_path, platform=platform_name)
                                        MarketingAgent.update_review(selected_pin, content=edited, status="Published")
                                        st.success(message)
                                        st.rerun()
                                    else:
                                        st.error(message)
                        else:
                            if not scheduled_time:
                                st.error("Please enter a valid schedule time")
                            else:
                                agent = MarketingAgent(api_key or "dummy")
                                
                                rec = MarketingAgent.load_review_by_pin(selected_pin)

                                if st.session_state.get('generated_image'):
                                    MarketingAgent.update_review(selected_pin, image_bytes=st.session_state['generated_image'])
                                if st.session_state.get('generated_video'):
                                    MarketingAgent.update_review(selected_pin, video_bytes=st.session_state['generated_video'])
                                rec = MarketingAgent.load_review_by_pin(selected_pin)

                                image_path = rec.get('current_image') if rec else None
                                video_path = rec.get('current_video') if rec else None
                                platform_name = st.session_state.get("platform", "LinkedIn")
                                agent.save_to_log(edited, "Scheduled", scheduled_time, image_path=image_path, video_path=video_path, platform=platform_name)
                                MarketingAgent.update_review(selected_pin, content=edited, status="Scheduled")
                                if video_path:
                                    st.success("Scheduled with video!")
                                elif image_path:
                                    st.success("Scheduled with image!")
                                else:
                                    st.success("Scheduled!")
                                st.rerun()
                elif status in ("Published", "Scheduled"):
                    st.info("This post is already finalized. Publishing actions are disabled.")
                    
                    # Display generated image if available
                    # Image preview now shown only above in the expander

    if page == "🧠 Market Intelligence":
        st.subheader("Market Intelligence & Competitor Analysis")
        
        st.info("💡 Phase 1: Competitor Analysis Module is active.")
        
        col_input, col_results = st.columns([1, 2])
        
        with col_input:
            st.markdown("### Search Settings")
            search_type = st.radio("Analysis Type", ["Trending Topics", "Competitor News"])
            
            if search_type == "Trending Topics":
                keywords = st.text_input("Industry Keywords", value="AI marketing automation ERP")
                if st.button("Find Trends", type="primary"):
                    with st.spinner("Scanning market trends..."):
                        analyzer = CompetitorAnalyzer()
                        results = analyzer.get_market_trends(keywords)
                        st.session_state["market_trends"] = results
            
            else:
                competitor = st.text_input("Competitor Name", placeholder="e.g. Serpent Consulting")
                if st.button("Analyze Competitor", type="primary"):
                    with st.spinner(f"Analyzing {competitor}..."):
                        analyzer = CompetitorAnalyzer()
                        results = analyzer.search_competitor_news(competitor)
                        st.session_state["competitor_news"] = results

        with col_results:
            st.markdown("### Insights")
            
            if search_type == "Trending Topics":
                trends = st.session_state.get("market_trends", [])
                if not trends:
                    st.info("No trends found or search not run yet.")
                else:
                    for i, item in enumerate(trends):
                        with st.expander(f"Trend: {item.get('title', 'Untitled')}", expanded=True):
                            st.write(item.get("content", "")[:300] + "...")
                            st.markdown(f"[Read Source]({item.get('url', '#')})")
                            if st.button("Use this Trend", key=f"trend_btn_{i}"):
                                st.session_state["draft_topic"] = f"Write a post about trending topic: {item.get('title')}\n\nContext: {item.get('content')}"
                                st.success("Topic copied to Workspace! Switch tabs to generate.")

            elif search_type == "Competitor News":
                news = st.session_state.get("competitor_news", [])
                if not news:
                    st.info("No news found or search not run yet.")
                else:
                    for i, item in enumerate(news):
                        with st.expander(f"News: {item.get('title', 'Untitled')}", expanded=True):
                            st.write(item.get("content", "")[:300] + "...")
                            st.markdown(f"[Read Source]({item.get('url', '#')})")
                            if st.button("Counter this Post", key=f"comp_btn_{i}"):
                                st.session_state["draft_topic"] = f"Write a post inspired by competitor news: {item.get('title')}\n\nContext: {item.get('content')}"
                                st.success("Topic copied to Workspace! Switch tabs to generate.")

    if page == "CEO Approval":
        st.subheader("CEO Review")
        def _try_unlock_pin():
            pin_value = (st.session_state.get("ceo_pin") or "").strip()
            if len(pin_value) != 4:
                return
            rec = MarketingAgent.load_review_by_pin(pin_value)
            if rec:
                st.session_state['ceo_unlocked_pin'] = str(pin_value)
                st.session_state.pop(f"ceo_editor_{pin_value}", None)
                st.session_state.pop(f"ceo_editor_nonce_{pin_value}", None)
                st.session_state[f"ceo_refresh_counter_{pin_value}"] = 0
                st.session_state["ceo_unlock_status"] = "success"
            else:
                st.session_state["ceo_unlock_status"] = "invalid"

        pin_input = st.text_input(
            "Enter the 4-digit CEO PIN from the email to unlock",
            value=st.session_state.get('ceo_pin', ''),
            max_chars=4,
            key="ceo_pin",
            on_change=_try_unlock_pin,
        )
        unlock_clicked = st.button("Unlock", type="primary", use_container_width=True, key="ceo_unlock")

        if unlock_clicked:
            rec = MarketingAgent.load_review_by_pin(pin_input)
            if rec:
                st.session_state['ceo_unlocked_pin'] = str(pin_input)
                st.session_state.pop(f"ceo_editor_{pin_input}", None)
                st.session_state.pop(f"ceo_editor_nonce_{pin_input}", None)
                st.session_state[f"ceo_refresh_counter_{pin_input}"] = 0
                st.session_state["ceo_unlock_status"] = "success"
            else:
                st.session_state["ceo_unlock_status"] = "invalid"

        if st.session_state.get("ceo_unlock_status") == "success":
            st.session_state["ceo_unlock_status"] = None
            st.success("Unlocked")
            st.rerun()
        elif st.session_state.get("ceo_unlock_status") == "invalid":
            st.session_state["ceo_unlock_status"] = None
            st.error("Invalid PIN")

        unlocked_pin = st.session_state.get('ceo_unlocked_pin')
        rec = MarketingAgent.load_review_by_pin(unlocked_pin) if unlocked_pin else None
        if rec:
            status = rec.get("status", "Draft")
            st.caption(f"Status: {status}")
            is_terminal = status in ("Scheduled", "Published")
            is_locked = status in ("Scheduled", "Published", "Rejected")
            
            updated_at = (rec.get("updated_at") or rec.get("created_at") or "").strip()

            editor_nonce = st.session_state.get(f"ceo_refresh_counter_{unlocked_pin}", 0)
            editor_key = f"ceo_editor_{unlocked_pin}_{editor_nonce}"
            local_value = st.session_state.get(editor_key, rec.get("content", ""))

            last_seen_key = f"ceo_last_seen_updated_{unlocked_pin}"
            if updated_at and st.session_state.get(last_seen_key) != updated_at and (local_value == rec.get("content", "")):
                st.session_state[last_seen_key] = updated_at
                st.session_state[f"ceo_refresh_counter_{unlocked_pin}"] = editor_nonce + 1
                editor_nonce = editor_nonce + 1
                editor_key = f"ceo_editor_{unlocked_pin}_{editor_nonce}"

            if local_value == rec.get("content", ""):
                _autorefresh(8000 if status in ("Pending", "Needs Edit") else 15000)
            
            ceo_content = st.text_area(
                "Post content",
                value=rec.get("content", ""),
                height=320,
                key=editor_key,
                disabled=is_locked,
            )

            # Also allow other tabs to use the CEO-unlocked post content
            st.session_state['active_post_content'] = ceo_content
            st.session_state['active_post_pin'] = str(unlocked_pin)

            # Display associated image if available
            current_image_path = rec.get("current_image")
            if current_image_path and os.path.exists(current_image_path):
                st.markdown("---")
                st.markdown("### 📷 Associated Image")
                try:
                    render_hq_image(current_image_path, width=500, caption=f"LinkedIn Post Image (1200×627px)")
                except Exception as e:
                    st.warning(f"Could not load image: {current_image_path}")

            current_video_path = rec.get("current_video")
            if current_video_path and os.path.exists(current_video_path):
                st.markdown("---")
                st.markdown("### 🎞️ Associated Video")
                try:
                    st.video(current_video_path, format="video/mp4")
                except Exception:
                    st.warning(f"Could not load video: {current_video_path}")

            if status == "Scheduled":
                st.info("This post is already scheduled. Approval actions are disabled.")
            elif status == "Published":
                st.info("This post is already published. Approval actions are disabled.")

            st.markdown("---")

            col_a, col_b, col_c, col_d = st.columns(4)
            with col_a:
                if st.button("Approve", use_container_width=True, type="primary", disabled=is_terminal, key=f"ceo_approve_{unlocked_pin}"):
                    MarketingAgent.update_review(unlocked_pin, content=ceo_content, status="Approved")
                    st.success("Approved")
                    st.rerun()
            with col_b:
                if st.button("Needs Edit", use_container_width=True, disabled=is_terminal, key=f"ceo_needs_edit_{unlocked_pin}"):
                    MarketingAgent.update_review(unlocked_pin, content=ceo_content, status="Needs Edit")
                    st.warning("Marked as Needs Edit")
                    st.rerun()
            with col_c:
                if st.button("Reject", use_container_width=True, disabled=is_terminal, key=f"ceo_reject_{unlocked_pin}"):
                    MarketingAgent.update_review(unlocked_pin, content=ceo_content, status="Rejected")
                    st.error("Rejected")
                    st.rerun()
            with col_d:
                if st.button("Reset", use_container_width=True, disabled=is_terminal, key=f"ceo_reset_{unlocked_pin}"):
                    MarketingAgent.update_review(unlocked_pin, content=ceo_content, status="Pending")
                    st.rerun()

            if status == "Approved":
                st.markdown("---")
                action = st.radio(
                    "Action",
                    options=["Schedule", "Publish now"],
                    horizontal=True,
                    key=f"ceo_action_{unlocked_pin}",
                )
                scheduled_time = None
                if action == "Schedule":
                    default_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    scheduled_time = st.text_input(
                        "Scheduled date & time",
                        value=st.session_state.get(f"ceo_schedule_dt_{unlocked_pin}", default_datetime),
                        key=f"ceo_schedule_dt_{unlocked_pin}",
                    )
                    try:
                        datetime.strptime(scheduled_time, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        scheduled_time = None
                        st.error("Invalid format! Use: YYYY-MM-DD HH:MM:SS")

                if st.button("Confirm", type="primary", use_container_width=True, disabled=c, key=f"ceo_confirm_{unlocked_pin}"):
                    agent = MarketingAgent(api_key or "dummy")
                    if action == "Publish now":
                        draft_rec = MarketingAgent.load_review_by_pin(unlocked_pin)
                        image_path = draft_rec.get('current_image') if draft_rec else None
                        video_path = draft_rec.get('current_video') if draft_rec else None
                        platform_name = (draft_rec.get("platform") if isinstance(draft_rec, dict) else None) or st.session_state.get("platform", "LinkedIn")

                        if platform_name == "LinkedIn":
                            member_id_to_use = member_id
                            if not linkedin_token or not member_id_to_use:
                                st.error("LinkedIn credentials required")
                            else:
                                image_bytes = None
                                video_bytes = None

                                if image_path and os.path.exists(image_path):
                                    try:
                                        with open(image_path, 'rb') as f:
                                            image_bytes = f.read()
                                    except:
                                        pass

                                if video_path and os.path.exists(video_path):
                                    try:
                                        with open(video_path, 'rb') as f:
                                            video_bytes = f.read()
                                    except:
                                        pass

                                if video_bytes:
                                    success, message = agent.publish_to_linkedin_with_video(
                                        ceo_content,
                                        video_bytes,
                                        linkedin_token,
                                        member_id_to_use
                                    )
                                elif image_bytes:
                                    success, message = agent.publish_to_linkedin_with_image(
                                        ceo_content,
                                        image_bytes,
                                        linkedin_token,
                                        member_id_to_use
                                    )
                                else:
                                    success, message = agent.publish_to_linkedin(ceo_content, linkedin_token, member_id_to_use)

                                if success:
                                    agent.save_to_log(ceo_content, message, image_path=image_path, video_path=video_path, platform=platform_name)
                                    MarketingAgent.update_review(unlocked_pin, content=ceo_content, status="Published")
                                    if video_path:
                                        st.success("Published with video!")
                                    elif image_path:
                                        st.success("Published with image!")
                                    else:
                                        st.success("Published!")
                                    st.rerun()
                                else:
                                    st.error(message)
                        elif platform_name == "Facebook":
                            if not facebook_token or not facebook_page_id:
                                st.error("Facebook credentials required")
                            else:
                                image_bytes = None
                                video_bytes = None
                                if image_path and os.path.exists(image_path):
                                    try:
                                        with open(image_path, 'rb') as f:
                                            image_bytes = f.read()
                                    except:
                                        pass
                                if video_path and os.path.exists(video_path):
                                    try:
                                        with open(video_path, 'rb') as f:
                                            video_bytes = f.read()
                                    except:
                                        pass

                                if video_bytes:
                                    success, message = agent.publish_to_facebook_with_video(ceo_content, video_bytes, facebook_token, facebook_page_id)
                                elif image_bytes:
                                    success, message = agent.publish_to_facebook_with_image(ceo_content, image_bytes, facebook_token, facebook_page_id)
                                else:
                                    success, message = agent.publish_to_facebook(ceo_content, facebook_token, facebook_page_id)

                                if success:
                                    agent.save_to_log(ceo_content, message, image_path=image_path, video_path=video_path, platform=platform_name)
                                    MarketingAgent.update_review(unlocked_pin, content=ceo_content, status="Published")
                                    st.success(message)
                                    st.rerun()
                                else:
                                    st.error(message)
                        else:
                            if not instagram_token or not instagram_user_id:
                                st.error("Instagram credentials required")
                            else:
                                image_bytes = None
                                video_bytes = None
                                if image_path and os.path.exists(image_path):
                                    try:
                                        with open(image_path, 'rb') as f:
                                            image_bytes = f.read()
                                    except:
                                        pass
                                if video_path and os.path.exists(video_path):
                                    try:
                                        with open(video_path, 'rb') as f:
                                            video_bytes = f.read()
                                    except:
                                        pass

                                success, message = agent.publish_to_instagram(
                                    ceo_content,
                                    access_token=instagram_token,
                                    user_id=instagram_user_id,
                                    image_bytes=image_bytes,
                                    video_bytes=video_bytes,
                                    facebook_access_token=instagram_token,
                                    facebook_page_id=instagram_facebook_page_id,
                                )
                                if success:
                                    agent.save_to_log(ceo_content, message, image_path=image_path, video_path=video_path, platform=platform_name)
                                    MarketingAgent.update_review(unlocked_pin, content=ceo_content, status="Published")
                                    st.success(message)
                                    st.rerun()
                                else:
                                    st.error(message)
                    else:
                        if not scheduled_time:
                            st.error("Please enter a valid schedule time")
                        else:
                            draft_rec = MarketingAgent.load_review_by_pin(unlocked_pin)
                            image_path = draft_rec.get('current_image') if draft_rec else None
                            video_path = draft_rec.get('current_video') if draft_rec else None
                            platform_name = st.session_state.get("platform", "LinkedIn")
                            agent.save_to_log(ceo_content, "Scheduled", scheduled_time, image_path=image_path, video_path=video_path, platform=platform_name)
                            MarketingAgent.update_review(unlocked_pin, content=ceo_content, status="Scheduled")
                            if video_path:
                                st.success("Scheduled with video!")
                            elif image_path:
                                st.success("Scheduled with image!")
                            else:
                                st.success("Scheduled!")
                            st.rerun()

    if page == "Settings":
        st.subheader("⚙️ Configuration")
        
        # st.info("Configure your API keys and credentials here.")
        
        with st.expander("🔑 Gemini API Key", expanded=False):
            current_key = st.session_state.get("gemini_api_key", "")
            new_key = st.text_input("Enter Gemini API Key", value=current_key, type="password")
            if new_key != current_key:
                st.session_state["gemini_api_key"] = new_key
                st.success("API Key updated for this session.")

        if current_platform == "LinkedIn":
            with st.expander("🔗 LinkedIn Credentials", expanded=False):
                current_token = linkedin_token
                current_member = member_id
                
                new_token = st.text_input("LinkedIn Access Token", value=current_token, type="password")
                new_member = st.text_input("LinkedIn Member ID (URN)", value=current_member)
                
                if st.button("Save LinkedIn Credentials"):
                    if MarketingAgent.save_credentials(new_token, new_member):
                        st.success("LinkedIn credentials saved to disk.")
                        st.rerun()
                    else:
                        st.error("Failed to save credentials.")
        elif current_platform == "Facebook":
            with st.expander("Facebook Credentials", expanded=False):
                new_fb_token = st.text_input("Facebook Access Token", value=facebook_token, type="password")
                new_fb_page_id = st.text_input("Facebook Page ID", value=facebook_page_id)
                if st.button("Save Facebook Credentials"):
                    if MarketingAgent.save_facebook_credentials(new_fb_token, new_fb_page_id):
                        st.success("Facebook credentials saved to disk.")
                        st.rerun()
                    else:
                        st.error("Failed to save Facebook credentials.")
        else:
            with st.expander("Instagram Credentials", expanded=False):
                new_ig_token = st.text_input("Instagram Access Token", value=instagram_token, type="password")
                new_ig_user_id = st.text_input("Instagram User ID", value=instagram_user_id)
                new_ig_fb_page_id = st.text_input("Instagram Facebook Page ID", value=instagram_facebook_page_id)
                if st.button("Save Instagram Credentials"):
                    if MarketingAgent.save_instagram_credentials(new_ig_token, new_ig_user_id, new_ig_fb_page_id):
                        st.success("Instagram credentials saved to disk.")
                        st.rerun()
                    else:
                        st.error("Failed to save Instagram credentials.")

        with st.expander("📧 Email Notifications", expanded=False):
            st.caption("Configure email settings for CEO approval workflow.")
            
            enable_email = st.checkbox("Enable Email Notifications", value=st.session_state.get('email_enabled', False))
            sender = st.text_input("Sender Email (Gmail)", value=st.session_state.get('sender_email', ''))
            password = st.text_input("App Password", value=st.session_state.get('sender_password', ''), type="password", help="Use a Google App Password, not your login password.")
            ceo = st.text_input("CEO Email (Recipient)", value=st.session_state.get('ceo_email', ''))
            
            if st.button("Save Email Configuration"):
                config = {
                    "sender_email": sender,
                    "sender_password": password,
                    "ceo_email": ceo,
                    "email_enabled": enable_email
                }
                if MarketingAgent.save_email_config(config):
                    st.session_state['sender_email'] = sender
                    st.session_state['sender_password'] = password
                    st.session_state['ceo_email'] = ceo
                    st.session_state['email_enabled'] = enable_email
                    st.success("Email configuration saved.")
                else:
                    st.error("Failed to save email configuration.")

        st.markdown("---")
        st.caption("Primacy Marketing AI Agent v1.0")


if __name__ == "__main__":
    main()
