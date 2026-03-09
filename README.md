# Primacy Infotech - LinkedIn Marketing Automation System

A complete marketing automation system built for Primacy Infotech to streamline LinkedIn content creation, approval workflows, and automated publishing.

## Quick Setup

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# streamlit run app.py
.\.venv\Scripts\streamlit.exe run app.py
```

or

```bash
 & "c:/Users/Atanu Roy/Downloads/Freelancer/marketing-agent/.venv/Scripts/Activate.ps1"
streamlit run app.py
```

## Key Features

- AI-powered content generation with Google Gemini
- CEO approval workflow with PIN-based security
- Automated scheduling and publishing (LinkedIn API)
- Email notifications
- Visual content creation
- Analytics and version history

## Installation

### Prerequisites

- Python 3.8 or higher
- Gmail account (for email notifications)
- LinkedIn Developer Account (optional, for API publishing)
- Google Gemini API key (free from AI Studio) - Used for both text generation and Grounding Search

### Dependencies

```
streamlit
google-genai
python-dotenv
requests
Pillow
schedule
```

## Usage

```bash
streamlit run app.py
```

Open browser at `http://localhost:8501`

## File Structure

```
├── app.py                    # Main Streamlit application
├── scheduler.py              # Background auto-publisher
├── requirements.txt          # Python dependencies
├── .env                      # Credentials (gitignored)
├── .approvals.json           # Draft storage
├── published_log.json        # Post history
└── README.md                 # This file
```

## Troubleshooting

### Email Not Sending

Use App Password from Gmail, not regular password.

### LinkedIn API 403 Error

Verify token has `w_member_social` scope and "Share on LinkedIn" access is approved.

### Scheduled Posts Not Publishing

Check `published_log.json` for status. Verify LinkedIn credentials and Member ID.

## Documentation

- [Project Requirement Document (Phase 1)](docs/PRD_Phase1.md)
- [Sprint Tasks](docs/TASKS.md)
- [Architecture](docs/ARCHITECTURE.md)

## Security

- Never commit `.env` file to git
- Rotate LinkedIn tokens every 60 days
- Backup JSON files weekly
- All data stored locally
