import os
import json
from datetime import datetime
from google import genai
from google.genai import types

class CompetitorAnalyzer:
    def __init__(self, api_key=None):
        # Prefer GEMINI_API_KEY from env if not provided
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            print("Warning: GEMINI_API_KEY not found.")
            self.client = None
        else:
            self.client = genai.Client(api_key=self.api_key)
        
        # Use a model that supports search grounding
        self.model_name = os.getenv("GEMINI_TEXT_MODEL", "")

    def _search_with_gemini(self, query):
        """
        Helper to perform a grounded search using Gemini and return structured results.
        """
        if not self.client:
            return None

        # Prompt engineering to get structured JSON output from search results
        prompt = f"""
        Perform a Google Search for: "{query}"
        
        Return a JSON object with a key "results" which is a list of items found.
        Each item must have:
        - "title": The title of the article or page
        - "content": A 2-3 sentence summary of the finding
        - "url": The source URL (if available from grounding, otherwise use a relevant domain)
        
        Focus on the most recent and relevant information.
        Ensure the output is valid JSON.
        """
        
        try:
            # Enable Google Search tool
            google_search_tool = types.Tool(google_search=types.GoogleSearch())
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[google_search_tool],
                    response_modalities=["TEXT"],
                    temperature=0.3, # Lower temperature for more factual extraction
                )
            )
            
            # Extract JSON from response text
            text = response.text
            if not text:
                return []
                
            # Naive JSON extraction
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                json_str = text[start:end+1]
                data = json.loads(json_str)
                return data.get("results", [])
            
            return []
            
        except Exception as e:
            print(f"Error during Gemini search: {e}")
            return []

    def search_competitor_news(self, competitor_name):
        """
        Search for recent news or mentions of a competitor.
        """
        if not self.client:
            # Mock data for demonstration if no API key
            return [
                {
                    "title": f"Mock News: {competitor_name} Launches AI Tool",
                    "content": f"{competitor_name} has announced a new AI-driven marketing platform that competes directly with industry leaders...",
                    "url": "https://example.com/news/1"
                },
                {
                    "title": f"Review: Is {competitor_name} worth it?",
                    "content": "A detailed breakdown of the pros and cons of using their services for small businesses...",
                    "url": "https://example.com/review/2"
                }
            ]
        
        query = f"latest news and social media posts about {competitor_name} marketing automation"
        return self._search_with_gemini(query)

    def get_market_trends(self, industry_keywords):
        """
        Get trending topics in the industry.
        """
        if not self.client:
             # Mock data for demonstration
            return [
                {
                    "title": "AI in ERP Systems: The Next Big Thing",
                    "content": "Enterprise Resource Planning (ERP) is undergoing a revolution with the integration of generative AI...",
                    "url": "https://example.com/trend/1"
                },
                {
                    "title": "Why Marketing Automation is Essential in 2026",
                    "content": "Small businesses are adopting automation at record rates to compete with larger firms...",
                    "url": "https://example.com/trend/2"
                }
            ]

        query = f"trending topics in {industry_keywords} {datetime.now().year}"
        return self._search_with_gemini(query)

    def analyze_competitors(self, competitors_list):
        """
        Aggregate insights from a list of competitors.
        """
        insights = {}
        for comp in competitors_list:
            results = self.search_competitor_news(comp)
            insights[comp] = results
        return insights

if __name__ == "__main__":
    # Test
    from dotenv import load_dotenv
    load_dotenv()
    
    analyzer = CompetitorAnalyzer()
    if analyzer.client:
        print("Searching trends with Gemini...")
        trends = analyzer.get_market_trends("AI marketing automation")
        print(json.dumps(trends, indent=2))
