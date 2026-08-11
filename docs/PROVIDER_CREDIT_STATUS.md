# Provider Credit Availability Status

Last updated: $(date -u +"%Y-%m-%d %H:%M UTC")

## Overview

This document tracks credit availability and rate limit reset times for AI Gateway providers.

---

## XAI (xAI/Grok)

**Status:** ✅ Available  
**Endpoint:** `https://api.x.ai/v1/chat/completions`  
**Model:** `xai/grok-code-fast-1`  

### Rate Limits & Reset
- **Free tier available via xai/grok-beta endpoints**
- **Rate limits typically reset daily at UTC midnight (00:00 Z)**
- Monitor current status at: https://grok.com/status

---

## MIMO AI

**Status:** ⚠️ Contact Provider  
**Endpoint:** Configurable via `MIMO_API_BASE` env var  

### Rate Limits & Reset
- **Enterprise/developer API with configurable quotas**
- **Contact support@mimo.ai for quota information**
- Typically resets on rolling 24h basis or monthly cycle

---

## OpenRouter Free Models

**Status:** ✅ Available  
**Endpoint:** `https://openrouter.ai/api/v1/models` via router  

### Rate Limits & Reset
- **Rate limits: ~10k tokens/min enforced by OpenRouter platform**
- **Reset: Rolling window, no guaranteed daily reset**

---

## Local Models (Zero Cost)

**Status:** ✅ Always Available  
**Endpoint:** Your local GPU cluster  

### Usage Notes
- Primary tier for all production workloads
- Zero cost, full control over data and privacy

