from groq import Groq, RateLimitError
import time
from api_key_rotator import APIKeyRotator, AllAPIKeysExhaustedError, APIKeyRotatorError, NoAPIKeysConfiguredError

class GroqServiceError(Exception):
    pass

class GroqAllKeysExhaustedError(GroqServiceError):
    pass

class GroqNoAPIKeysConfiguredError(GroqServiceError):
    pass


try:
    rotator = APIKeyRotator(daily_limit=1000)

except NoAPIKeysConfiguredError as e:
    raise GroqNoAPIKeysConfiguredError(
        "No Groq API keys are configured in environment variables."
    ) from e

except APIKeyRotatorError as e:
    raise GroqServiceError(
        f"Failed to initialize API key rotator: {e}"
    ) from e

def generate_groq_response(messages, model, require_json=False):
    """
    A single, centralized function to call Groq. 
    Set require_json=True to force the model to reply in JSON format.
    """
    max_attempts = len(rotator.keys)
    attempts = 0
    
    api_args = {
        "messages": messages,
        "model": model,
    }
    
    #Add json only if require_json = true
    if require_json:
        api_args["response_format"] = {"type": "json_object"}
    
    while attempts < max_attempts:
        current_key = rotator.get_current_key()
        client = Groq(api_key=current_key)
        
        try:
            response = client.chat.completions.create(**api_args)
            
            rotator.record_usage()
            return response.choices[0].message.content
            
        except RateLimitError:
            rotator.logger.warning("429 Rate Limit. Forcing rotation.")
            attempts += 1

            try:
                rotator.change_api_key()
            except AllAPIKeysExhaustedError as e:
                rotator.logger.error("All API keys exhausted while rotating after 429.")
                raise GroqAllKeysExhaustedError(
                    "All Groq API keys have reached their daily limit or are rate-limited."
                ) from e

            time.sleep(1)
            
        except AllAPIKeysExhaustedError as e:
            rotator.logger.error("All API keys exhausted before request could be made.")
            raise GroqAllKeysExhaustedError(
                "All Groq API keys have reached their daily limit or are rate-limited."
            ) from e
        
        except APIKeyRotatorError as e:
            rotator.logger.error(f"API key rotator failure: {e}")
            raise GroqServiceError(
                f"API key rotator failure: {e}"
            ) from e

        except Exception as e:
            rotator.logger.error(f"Groq API Error: {e}")
            raise GroqServiceError(f"Groq API call failed: {e}") from e
            
    raise GroqAllKeysExhaustedError(
        "All Groq API keys are currently rate-limited or exhausted."
    )