import requests
import logging
from backend.config import VAPI_API_KEY, VAPI_ASSISTANT_ID, VAPI_PHONE_NUMBER_ID

logger = logging.getLogger("alertx.vapi")

def trigger_ai_dispatch(service: str, incident_details: str, destination_number: str):
    """
    Triggers a Vapi Voice AI call to a specific number.
    The AI will inform the service about the incident using a custom prompt.
    """
    if not VAPI_API_KEY or not VAPI_ASSISTANT_ID:
        logger.warning(f"[STUB] Vapi Dispatch: Calling {service} @ {destination_number} regarding {incident_details}")
        return False

    logger.info(f"Initiating AI Call Dispatch for {service} to {destination_number}...")

    url = "https://api.vapi.ai/call/phone"
    
    # Customize the prompt based on the incident
    custom_prompt = f"You are an automated emergency dispatcher for AlertX AI. An incident has been detected: {incident_details}. Please send {service} assistance to our monitored location immediately. This is an official AI-triggered emergency alert."

    payload = {
        "assistantId": VAPI_ASSISTANT_ID,
        "phoneNumberId": VAPI_PHONE_NUMBER_ID or None, # Use specific number if provided
        "customer": {
            "number": destination_number,
        },
        "assistantOverrides": {
            "firstMessage": f"Hello, this is AlertX AI Emergency Dispatch. We have detected a {incident_details}. We require {service} assistance immediately.",
            "model": {
                "provider": "openai",
                "model": "gpt-4o",
                "messages": [
                    {
                        "role": "system",
                        "content": custom_prompt
                    }
                ]
            }
        }
    }

    headers = {
        "Authorization": f"Bearer {VAPI_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 201:
            logger.info(f"AI Voice Dispatch triggered for {service}. Call SID: {response.json().get('id')}")
            return True
        else:
            logger.error(f"Vapi Error: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Vapi connection failed: {e}")
        return False
