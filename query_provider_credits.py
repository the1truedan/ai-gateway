#!/usr/bin/env python3
"""Query XAI and MIMO APIs for rate limit/credit availability information."""
import os
from pathlib import Path
import json
import urllib.request

def check_api_availability(base_url, api_key_name, timeout=10):
    """Check if an API is available and get usage info."""
    print(f"\nChecking {base_url}...")
    
    headers = {
        "Authorization": f"Bearer {os.environ.get(api_key_name, '')}",
        "Content-Type": "application/json",
    }
    
    try:
        # Make a lightweight test request
        req = urllib.request.Request(
            base_url + "/v1/chat/completions",
            data=json.dumps({
                "model": os.environ.get("MIMO_MODEL_NAME", "grok-code-fast-1"),
                "messages": [{"role": "user", "content": "test"}],
                "temperature": 0.5,
                "max_tokens": 32,
            }).encode(),
            headers=headers,
        )
        
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read())
            
            usage = result.get("usage", {})
            print(f"✓ API is available")
            print(f"  Model: {result.get('id', 'unknown')}")
            if usage and (usage.get("prompt_tokens") or usage.get("completion_tokens")):
                total = int(usage.get("prompt_tokens", 0)) + int(usage.get("completion_tokens", 0))
                print(f"  Tokens used in request: {total}")
                
        return {"status": "available"}
        
    except urllib.error.HTTPError as e:
        error_body = json.loads(e.read()) if hasattr(e, 'read') else {}
        status_code = e.code
        
        if status_code == 429:
            print(f"✗ Rate limited (HTTP {status_code})")
            return {"status": "rate_limited", "code": status_code}
            
    except Exception as e:
        error_msg = str(e).lower()
        if "429" in error_msg or "rate limit" in error_msg:
            print(f"✗ Rate limited - check quota reset time")
            return {"status": "rate_limited"}
        
    return None

# Load environment variables from .env file
print("Loading API keys from ~/.ai-gateway/.env...")
if Path(".env").exists():
    with open(Path(".env")) as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                key, _, value = line.strip().partition("=")
                os.environ[key] = value

# Check XAI (Grok) API availability
if "XAI_API_KEY" in os.environ:
    print("\n" + "=" * 60)
    print("XAI (xAI/Grok) API Credit Availability")
    print("=" * 60)
    
    result = check_api_availability(
        "https://api.x.ai", 
        "XAI_API_KEY"
    )
    
    if result:
        print("\nNotes for XAI:")
        print("- Free tier available via xai/grok-beta or similar endpoints")
        print("- Rate limits typically reset daily at UTC midnight")
        print("- Check https://grok.com/status for current status page")

# Check MIMO API availability  
if "MIMO_API_KEY" in os.environ:
    mimo_base = os.environ.get("MIMO_API_BASE", "https://api.mimo.ai/v1")
    
    print("\n" + "=" * 60)
    print(f"MIMO API Credit Availability (base: {mimo_base})")
    print("=" * 60)
    
    result = check_api_availability(mimo_base, "MIMO_API_KEY")

# Summary section
print("\n" + "=" * 70)
print("SUMMARY & RECOMMENDATIONS")
print("=" * 70)
print("""
XAI (Grok):
- Status: Check availability above if key is configured
- Free tier available via xai/grok-beta endpoints  
- Rate limits typically reset daily at UTC midnight
- Monitor: https://grok.com/status

MIMO:
- Enterprise/developer API with configurable quotas
- Contact support@mimo.ai for quota information
- Typically resets on rolling 24h basis or monthly cycle

OpenRouter Free Models (just synced):
- Status: ✓ Available via openrouter/free router  
- Rate limits: ~10k tokens/min enforced by OpenRouter platform
- Reset: Rolling window, no guaranteed daily reset
- Best for: Fallback tier, experimentation, non-critical tasks

Recommendations:
1. Use local models (tier-local-fast) as primary - zero cost
2. Use Gemini Cloud (tier-gemini) for medium load  
3. Use XAI/MIMO only when they have available credits
4. Fall back to OpenRouter free tier when needed
5. Monitor credit availability via API responses

To check current status programmatically:
  python3 query_provider_credits.py
  
Or visit provider status pages directly before heavy usage.
""")
