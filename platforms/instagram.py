def build_post_prompt(topic: str, tone: str) -> str:
    topic = (topic or "").strip()
    tone = (tone or "").strip()
    return f"""You are a senior marketing strategist for Primacy Infotech, an Odoo Silver Partner.

COMPETITOR RESEARCH (USE GOOGLE SEARCH):
Before creating content, research recent Instagram posts from these top Odoo ERP competitors:
- CYBROSYS Technologies Pvt Ltd
- Ksolves India Limited  
- Brainvire
- Alligator Infosoft
- Serpent Consulting Services

Analyze what makes their posts engaging and create content that OUTPERFORMS them.

TASK: Create an Instagram caption about: {topic}
TONE: {tone}

CAPTION GOAL:
Explain "Why growing businesses fail with ERP—and how Odoo fixes it" with focus on: {topic}

REQUIREMENTS:
- Hook in first line (controversial, specific, or data-driven).
- 4-8 short lines, easy to read.
- Include a mini checklist (3 quick actionable points).
- End with a question for engagement.
- Hashtags: 10-15, include #OdooERP #ERPImplementation #PrimacyInfotech.
- Avoid hard selling and avoid links.
- Make it MORE engaging than competitor posts (stronger hook, clearer value).

OUTPUT FORMAT:
Return ONLY the final Instagram caption, ready to copy-paste.
"""


def build_image_prompt(post_content: str, style_prompt: str) -> str:
    lines = (post_content or "").split("\n")
    hook = (lines[0] if lines else (post_content or "")).strip()[:90]
    return (
        "Create an Instagram square post image that OUTPERFORMS competitors.\n\n"
        
        "COMPETITIVE RESEARCH: Analyze recent Instagram images from CYBROSYS, Ksolves, Brainvire, Alligator, Serpent Consulting.\n"
        "YOUR GOAL: Create MORE engaging visuals with stronger hooks and clearer value than their best posts.\n\n"
        
        "Output: a single 1080x1080 PNG.\n"
        "Design: bold headline, minimal icons, and 3 short points.\n"
        "Colors: Primacy Infotech palette (#1E3A8A, #3B82F6) with high contrast.\n\n"
        
        "BRANDING ELEMENTS:\n"
        "- Top left: Primacy Infotech logo https://primacyinfotech.com/assets/images/logo-p.webp\n"
        "- Top right: Entrepreneur logo https://primacyinfotech.com/assets/images/enterpreneur-logo.webp\n"
        "- Include ODOO logo: https://upload.wikimedia.org/wikipedia/commons/thumb/4/4d/Odoo_logo_rgb.svg/1280px-Odoo_logo_rgb.svg.png?20151230141100\n"
        "- Bottom contact bar: 📞 +919088015866/65 | ✉️ odoo@primacyinfotech.com | 🌐 primacyinfotech.com\n"
        "- Country flags (small): 🇧🇩 🇦🇪 🇮🇳 🇬🇧\n\n"
        
        f"Headline text: {hook}\n\n"
        f"{style_prompt}\n"
    )


def build_video_prompt(post_content: str, style_prompt: str) -> str:
    lines = (post_content or "").split("\n")
    hook = (lines[0] if lines else (post_content or "")).strip()[:70]
    return (
        "Create a short Instagram Reel that OUTPERFORMS competitors.\n\n"
        
        "COMPETITIVE RESEARCH: Analyze recent Reels from CYBROSYS, Ksolves, Brainvire, Alligator, Serpent Consulting.\n"
        "YOUR GOAL: Create MORE engaging Reels with instant attention-grabbing opening than their best content.\n\n"
        
        "Output: a single MP4 video.\n"
        "Aspect ratio: 9:16.\n"
        "Style: corporate, minimal, Primacy Infotech colors (#1E3A8A, #3B82F6).\n"
        "On-screen text: 1 hook line + 3 quick points + a final question.\n\n"
        
        "BRANDING ELEMENTS:\n"
        "- Top left: Primacy logo visible throughout https://primacyinfotech.com/assets/images/logo-p.webp\n"
        "- Top right: Entrepreneur logo visible throughout https://primacyinfotech.com/assets/images/enterpreneur-logo.webp\n"
        "- ODOO logo in middle frames: https://upload.wikimedia.org/wikipedia/commons/thumb/4/4d/Odoo_logo_rgb.svg/1280px-Odoo_logo_rgb.svg.png?20151230141100\n"
        "- Bottom contact bar: 📞 +919088015866/65 | odoo@primacyinfotech.com | primacyinfotech.com\n"
        "- Animated country flags: 🇧🇩 🇦🇪 🇮🇳 🇬🇧\n\n"
        
        f"Hook: {hook}\n\n"
        f"{style_prompt}\n"
    )

