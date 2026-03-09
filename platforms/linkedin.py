def build_post_prompt(topic: str, tone: str) -> str:
    topic = (topic or "").strip()
    tone = (tone or "").strip()
    return f"""You are a senior marketing strategist for Primacy Infotech, an Odoo Silver Partner specializing in ERP implementation and business process re-engineering.

PRIMACY INFOTECH BRAND PROFILE:
- **Who We Are**: Primacy Infotech is an Odoo Silver Partner specializing in ERP implementation and business process re-engineering
- **Core Odoo Value Proposition**: We are process-first experts who rescue failed ERP implementations, position ERP as a growth driver (not cost center), and specialize in scalability engineering for growing businesses
- **Brand Tone**: Corporate, Consultative, Insight-driven, Authoritative
- **Ideal LinkedIn Audience**: Growing businesses (50-500 employees), CFOs, Operations Directors, CIOs at companies struggling with ERP implementations

COMPETITIVE LANDSCAPE & RESEARCH MANDATE:
Key Odoo ERP Implementation Competitors to Analyze:

1. **CYBROSYS Technologies Pvt Ltd** (20,082 followers) - Highest engagement rate leader
2. **Ksolves India Limited** (75,183 followers) - Largest follower base
3. **Brainvire** (71,069 followers) - Strong brand presence
4. **Alligator Infosoft** (24,915 followers) - Quality content producer
5. **Serpent Consulting Services** (11,432 followers) - Consistent performer
6. **BrowseInfo** (12,154 followers) - Selective high-quality posting
7. **DreamzTech Solutions** (8,914 followers)
8. **Envertis Software Solutions** (2,441 followers)
9. **OODU Implementers** (1,171 followers)
10. **Primacy Infotech** (2,864 followers) - OUR COMPANY (need to outperform competitors)

COMPETITOR INTELLIGENCE (MANDATORY - USE GOOGLE SEARCH TOOL):
Before writing the post, you MUST research recent LinkedIn posts from the top 5 competitors (CYBROSYS, Ksolves, Brainvire, Alligator, Serpent Consulting) related to: {topic}.

RESEARCH OBJECTIVES:
1. Use Google Search tool to find recent posts from these competitors about {topic}
2. Analyze their hooks, content structure, engagement tactics, and value propositions
3. Identify what makes their content engaging (data points, controversy, specificity, insights)
4. Study their posting frequency and content quality balance
5. Note any gaps or weaknesses in their approach

CONTENT CREATION RULES:
- Do NOT copy competitor wording, structure, or examples
- Do NOT mention competitors by name in the final post
- Create content MORE engaging than what you found (sharper insights, stronger hooks, clearer differentiation)
- Use data/statistics grounded from research tools
- Position Primacy with unique expertise they lack

TASK: Create a LinkedIn post about: {topic}
TONE: {tone}

POST REQUIREMENTS:
The post MUST be about "Why growing businesses fail with ERP—and how Odoo fixes it" with focus on: {topic}

1. **Strong Hook (First 2 Lines)**
   - Opening must be counterintuitive, challenging, or provocative
   - Create immediate curiosity and stop-scroll effect
   - Related to {topic} and ERP challenges

2. **Problem Articulation (2-3 lines)**
   - Specific pain points growing businesses (50-500 employees) face
   - Research-backed data or statistics if possible
   - Related to {topic}
   - Vivid, concrete language

3. **Root Cause Insight (2-3 lines)**
   - Explain WHY the problem exists
   - Challenge conventional thinking
   - Thought-provoking and educational

4. **Solution & Approach (2-3 lines)**
   - How Odoo + Primacy's process-first approach solves {topic}
   - Concrete benefits: visibility, standardization, adoption
   - Position Primacy as the expert

5. **Soft Call-to-Action (1-2 lines)**
   - Engagement question related to {topic}
   - NOT salesy (NO "Book demo", "Contact sales", "Buy now")
   - Invite discussion, not transactions

6. **Hashtags (5-7 maximum)**
   - REQUIRED: #OdooERP #ERPImplementation #BusinessProcess #PrimacyInfotech
   - OPTIONAL: Relevant to {topic}

TONE GUIDELINES FOR '{tone}':
- Professional: Formal corporate language, focus on ROI, compliance, strategic value
- Consultative: Advisory tone, questions, expert insights, trusted advisor positioning
- Urgent: Sense of immediacy, risks, time-sensitive opportunities, competitive threats
- Storytelling: Customer scenario, emotional connection, relatable challenges, transformation

CONTENT GUIDELINES:
- **Length**: 150-250 words (MUST BE UNDER 3000 CHARACTERS for LinkedIn)
- **Educational + Authoritative**: Provide insight, not sales pitch
- **Shares, Saves, Comments**: Content that drives engagement through value
- **No Emoji Overload**: Maximum 1-2 strategic emojis
- **CEO-Friendly**: Professional, authoritative, accessible
- **Concrete Examples**: Use specific scenarios from {topic}
- **Active Voice**: Strong, direct language
- **FORMAT**: Short lines, white space, easy to scan

CRITICAL REQUIREMENTS:
1. This post MUST directly address: "Why growing businesses fail with ERP—and how Odoo fixes it"
2. Must be SPECIFIC to {topic}, NOT generic
3. Must use {tone} tone throughout
4. Must position Primacy as expert in solving {topic}
5. Must provide educational value, not sales pitch
6. MUST BE UNDER 2800 CHARACTERS

OUTPUT FORMAT:
Provide ONLY the final LinkedIn post - ready to copy-paste.
No explanations, metadata, or commentary.
No structure labels like "Hook:", "Problem:", etc.
"""


def build_image_prompt(post_content: str, style_prompt: str) -> str:
    lines = (post_content or "").split("\n")
    hook = (lines[0] if lines else (post_content or "")).strip()[:140]
    return (
        "Create a LinkedIn post image that OUTPERFORMS competitors (CYBROSYS, Ksolves, Brainvire, Alligator, Serpent Consulting).\n\n"
        
        "COMPETITIVE ANALYSIS:\n"
        "Research recent image posts from these Odoo ERP competitors and identify what makes them engaging:\n"
        "- CYBROSYS Technologies Pvt Ltd (highest engagement rate)\n"
        "- Ksolves India Limited (largest audience)\n"
        "- Brainvire (strong brand)\n"
        "- Alligator Infosoft (quality focus)\n"
        "- Serpent Consulting Services (consistent performer)\n\n"
        
        "YOUR GOAL: Create an image MORE engaging than their best posts by:\n"
        "1. Stronger hook/headline (more controversial, specific, or data-driven than theirs)\n"
        "2. Better visual clarity (easier to scan in 2 seconds)\n"
        "3. More professional polish (high-end corporate design)\n\n"
        
        "Output: a single 1200x627 PNG.\n"
        "Design: Top 30% dark blue header band (#1E3A8A) with white bold headline text.\n"
        "Middle 40%: modern business/tech illustration, icons, charts; minimal style.\n"
        "Bottom 30%: clean white space with subtle brand mark.\n"
        "Use accent blue (#3B82F6). High contrast, professional corporate look.\n\n"
        
        "IMPORTANT - Include these elements:\n"
        "- Top left corner: Primacy Infotech logo (https://primacyinfotech.com/assets/images/logo-p.webp)\n"
        "- Integrate ODOO logo badge prominently (https://upload.wikimedia.org/wikipedia/commons/thumb/4/4d/Odoo_logo_rgb.svg/1280px-Odoo_logo_rgb.svg.png?20151230141100)\n"
        "- Bottom left: Contact details in small text:\n"
        "  📞 +919088015866 / +919088015865\n"
        "  ✉️ odoo@primacyinfotech.com\n"
        "  🌐 primacyinfotech.com\n"
        "- Bottom right corner: Small 4 country flags in a horizontal row: 🇧🇩 Bangladesh, 🇦🇪 UAE, 🇮🇳 India, 🇬🇧 UK (each flag 20x15px)\n\n"
        
        f"Headline text: {hook}\n\n"
        f"{style_prompt}\n"
    )


def build_video_prompt(post_content: str, style_prompt: str) -> str:
    lines = (post_content or "").split("\n")
    hook = (lines[0] if lines else (post_content or "")).strip()[:120]
    return (
        "Create a short LinkedIn-ready video that OUTPERFORMS competitors (CYBROSYS, Ksolves, Brainvire, Alligator, Serpent Consulting).\n\n"
        
        "COMPETITIVE ANALYSIS:\n"
        "Research recent video posts from these Odoo ERP competitors and identify engagement tactics:\n"
        "- CYBROSYS Technologies Pvt Ltd (highest engagement rate)\n"
        "- Ksolves India Limited (largest audience)\n"
        "- Brainvire (strong brand)\n"
        "- Alligator Infosoft (quality focus)\n"
        "- Serpent Consulting Services (consistent performer)\n\n"
        
        "YOUR GOAL: Create a video MORE engaging than their best videos by:\n"
        "1. Instant attention grab (controversial stat, bold claim, or question in first 2 seconds)\n"
        "2. Smooth transitions that guide the viewer's eye\n"
        "3. Professional polish (corporate quality, not amateur)\n"
        "4. Clear value delivered in 8 seconds\n\n"
        
        "Output: a single MP4 video.\n"
        "Style: corporate, minimal, Primacy Infotech colors (#1E3A8A, #3B82F6).\n"
        "Motion: subtle animated shapes, charts, icons, transitions.\n\n"
        
        "IMPORTANT - Include these elements throughout the video:\n"
        "- Top left corner: Primacy Infotech logo visible throughout (https://primacyinfotech.com/assets/images/logo-p.webp)\n"
        "- Integrate ODOO logo badge prominently in middle section (https://upload.wikimedia.org/wikipedia/commons/thumb/4/4d/Odoo_logo_rgb.svg/1280px-Odoo_logo_rgb.svg.png?20151230141100)\n"
        "- Bottom overlay bar showing contact details:\n"
        "  📞 +919088015866 / +919088015865\n"
        "  ✉️ odoo@primacyinfotech.com\n"
        "  🌐 primacyinfotech.com\n"
        "- Bottom right corner: Small 4 country flags animated: 🇧🇩 Bangladesh, 🇦🇪 UAE, 🇮🇳 India, 🇬🇧 UK\n\n"
        
        f"On-screen headline: {hook}\n\n"
        f"{style_prompt}\n"
    )

