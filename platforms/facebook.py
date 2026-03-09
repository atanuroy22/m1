def build_post_prompt(topic: str, tone: str) -> str:
    topic = (topic or "").strip()
    tone = (tone or "").strip()
    return f"""You are a senior marketing strategist for Primacy Infotech, an Odoo Silver Partner.

COMPETITOR RESEARCH (USE GOOGLE SEARCH):
Before creating content, research recent Facebook posts from these top Odoo ERP competitors:
- CYBROSYS Technologies Pvt Ltd
- Ksolves India Limited
- Brainvire
- Alligator Infosoft
- Serpent Consulting Services

Analyze what makes their posts engaging and create content that OUTPERFORMS them.

TASK: Create a Facebook post about: {topic}
TONE: {tone}

POST GOAL:
Explain "Why growing businesses fail with ERP—and how Odoo fixes it" with focus on: {topic}

REQUIREMENTS:
- Use short paragraphs and simple language.
- Include one practical checklist or 3 actionable bullets.
- End with a friendly question to drive comments.
- Avoid hard selling.
- Length: 80-180 words.
- Hashtags: 3-6 max, include #OdooERP and #PrimacyInfotech.
- Make it MORE engaging than competitor posts (stronger value, clearer insights).

OUTPUT FORMAT:
Return ONLY the final Facebook post text, ready to copy-paste.
"""


def build_image_prompt(post_content: str, style_prompt: str) -> str:
    lines = (post_content or "").split("\n")
    hook = (lines[0] if lines else (post_content or "")).strip()[:120]
    return (
        "Create a Facebook post image that OUTPERFORMS competitors.\n\n"
        
        "COMPETITIVE RESEARCH: Analyze recent Facebook images from CYBROSYS, Ksolves, Brainvire, Alligator, Serpent Consulting.\n"
        "YOUR GOAL: Create MORE engaging visuals with stronger hooks and better clarity than their best posts.\n\n"
        
        "Output: a single 1200x630 PNG.\n"
        "Design: clean corporate layout with bold headline and 3 short points.\n"
        "Colors: Primacy Infotech palette (#1E3A8A, #3B82F6) with plenty of white space.\n\n"
        
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
    hook = (lines[0] if lines else (post_content or "")).strip()[:90]
    return (
        "Create a short Facebook feed video that OUTPERFORMS competitors.\n\n"
        
        "COMPETITIVE RESEARCH: Analyze recent videos from CYBROSYS, Ksolves, Brainvire, Alligator, Serpent Consulting.\n"
        "YOUR GOAL: Create MORE engaging videos with instant value and smooth transitions than their best content.\n\n"
        
        "Output: a single MP4 video.\n"
        "Aspect ratio: 4:5.\n"
        "Style: corporate and clean, Primacy Infotech colors (#1E3A8A, #3B82F6).\n"
        "On-screen text: 1 headline + 3 short bullet points.\n\n"
        
        "BRANDING ELEMENTS:\n"
        "- Top left: Primacy logo visible https://primacyinfotech.com/assets/images/logo-p.webp\n"
        "- Top right: Entrepreneur logo visible https://primacyinfotech.com/assets/images/enterpreneur-logo.webp\n"
        "- ODOO logo in frames: https://upload.wikimedia.org/wikipedia/commons/thumb/4/4d/Odoo_logo_rgb.svg/1280px-Odoo_logo_rgb.svg.png?20151230141100\n"
        "- Bottom contact: 📞 +919088015866/65 | odoo@primacyinfotech.com | primacyinfotech.com\n"
        "- Country flags: 🇧🇩 🇦🇪 🇮🇳 🇬🇧\n\n"
        
        f"Headline: {hook}\n\n"
        f"{style_prompt}\n"
    )

