# Recommended AI Architecture: Primacy Marketing Agent

## Overview
This document outlines a scalable, cost-effective architecture for the Primacy AI Marketing Agent. The goal is to minimize operational costs while maximizing output quality and reliability.

---

## 1. High-Level Architecture
The system follows a modular **Agentic Workflow**:
1.  **Observer (Trend/Competitor Analysis):** Scans the web and social platforms.
2.  **Strategist (Content Planning):** Maps trends to Primacy's services.
3.  **Creator (Content Generation):** Generates text and images.
4.  **Reviewer (Human-in-the-Loop):** Streamlit dashboard for approval.
5.  **Publisher (Automation):** APIs to post content.

---

## 2. Tech Stack Selection

### 2.1 Core Application Framework
*   **Language:** Python 3.10+
*   **Web Framework:** Streamlit (Rapid prototyping, easy UI for approval).
*   **Task Orchestration:** LangGraph or simple Python functions with `schedule` library (for Phase 1).

### 2.2 LLM (Text Generation & Reasoning)
*   **Primary Model:** **Google Gemini 1.5 Flash** (Low cost, high speed, large context window for reading many competitor posts).
*   **Alternative:** **OpenAI GPT-4o-mini** (Good balance of cost/performance).
*   **Reasoning:** Use Gemini 1.5 Pro for complex strategy tasks (e.g., monthly planning).

### 2.3 Image Generation
*   **Primary:** **Flux.1 [schnell]** (via Replicate or local if GPU available). High quality, follows prompts well.
*   **Alternative:** **DALL-E 3** (Easy integration, but higher cost).
*   **Branding Overlay:** `Pillow` (Python Imaging Library) to programmatically add logos and text overlays *after* generation to ensure brand consistency.

### 2.4 Data Collection & Search
*   **Web Search:** **Tavily API** (Optimized for LLM agents, provides clean text).
*   **Social Scraping:** **Apify** (Robust social media scrapers) or **Browserless** (for custom scraping).

### 2.5 Database & Storage
*   **Metadata:** SQLite (local file) or JSON for Phase 1. Easy to back up and move.
*   **Files:** Local filesystem (`images/`, `videos/`) or S3-compatible storage (MinIO/AWS S3) for scalability.

---

## 3. Workflow Logic

### Step 1: Trend Discovery
1.  Agent queries Tavily/Google Trends for "latest trends in ERP/AI/Odoo".
2.  Agent scrapes top 3 competitor LinkedIn pages (via Apify/custom scraper).
3.  **Output:** A list of 5 potential topics with "Viral Score" and "Relevance to Primacy".

### Step 2: Content Strategy
1.  LLM selects the top topic.
2.  LLM drafts 3 angles:
    *   **Educational:** "How Odoo helps X..."
    *   **Controversial/Thought Leadership:** "Why ERP implementation fails..."
    *   **Promotional:** "Primacy's new AI module..."
3.  **Output:** Selected Angle + Key Points.

### Step 3: Generation
1.  **Text:** LLM writes the caption (LinkedIn/IG/FB styles) and blog post (Markdown).
2.  **Image:** LLM generates an image prompt based on the text. Image Model generates the visual.
3.  **Branding:** Python script adds Primacy logo overlay.
4.  **Output:** Draft Object in `pending_approval.json`.

### Step 4: Approval
1.  Human logs into Streamlit.
2.  Views "Drafts".
3.  Clicks "Approve" -> Moves to `scheduled_posts.json`.
4.  Clicks "Edit" -> Modifies text/image prompt -> Regenerate.

### Step 5: Publishing
1.  Scheduler checks `scheduled_posts.json` every hour.
2.  If `scheduled_time` <= `now`, post to APIs (LinkedIn, Facebook, Instagram).
3.  Move to `published_log.json`.

---

## 4. Cost Analysis (Estimated)

| Component | Service | Est. Monthly Cost (Low Volume) |
| :--- | :--- | :--- |
| **LLM** | Gemini 1.5 Flash | Free Tier / <$5 |
| **Image Gen** | Flux.1 (Replicate) | ~$10 (approx. $0.01/img) |
| **Search** | Tavily | Free Tier (1000 searches/mo) |
| **Hosting** | Streamlit Cloud / VPS | Free / ~$5 |
| **Total** | | **~$15 - $20 / month** |

This architecture prioritizes low operational costs while maintaining high quality through state-of-the-art models like Gemini and Flux.
