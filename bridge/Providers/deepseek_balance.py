"""
DeepSeek Balance — Fetch account balance from DeepSeek API.

Endpoint: GET /providers/deepseek/balance

Returns balance information including:
- is_available: bool (sufficient balance for API calls)
- balances: list of balance info per currency (USD, CNY)
- key_preview: last 4 chars of API key

DeepSeek API docs: https://api-docs.deepseek.com/api/get-user-balance
"""

import os
import logging
import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/deepseek/balance")
async def deepseek_balance():
    """Fetch DeepSeek account balance.
    
    Returns:
      - connected: bool (has valid API key)
      - balance: dict with currency, total_balance, granted_balance, topped_up_balance
      - is_available: bool (sufficient balance for API calls)
    """
    # Check if DeepSeek API key is configured
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        return JSONResponse({
            "connected": False,
            "balance": None,
            "is_available": False,
            "error": "No DeepSeek API key configured",
        })
    
    # Fetch balance from DeepSeek API
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.deepseek.com/user/balance",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            
            if resp.status_code == 200:
                data = resp.json()
                is_available = data.get("is_available", False)
                balance_infos = data.get("balance_infos", [])
                
                # Format balance data for UI
                balances = []
                for info in balance_infos:
                    balances.append({
                        "currency": info.get("currency", "USD"),
                        "total_balance": float(info.get("total_balance", "0")),
                        "granted_balance": float(info.get("granted_balance", "0")),
                        "topped_up_balance": float(info.get("topped_up_balance", "0")),
                    })
                
                return JSONResponse({
                    "connected": True,
                    "is_available": is_available,
                    "balances": balances,
                    "key_preview": api_key[-4:],
                })
            elif resp.status_code == 401:
                return JSONResponse({
                    "connected": False,
                    "balance": None,
                    "is_available": False,
                    "error": "Invalid DeepSeek API key",
                })
            else:
                return JSONResponse({
                    "connected": True,
                    "balance": None,
                    "is_available": False,
                    "error": f"DeepSeek API returned status {resp.status_code}",
                })
                
    except Exception as exc:
        logger.warning("Failed to fetch DeepSeek balance: %s", exc)
        return JSONResponse({
            "connected": True,
            "balance": None,
            "is_available": False,
            "error": f"Failed to fetch balance: {str(exc)}",
        })
