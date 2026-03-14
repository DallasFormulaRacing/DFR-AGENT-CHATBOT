import os
import json
from datetime import date
from dotenv import load_dotenv
from logger import setup_logger


load_dotenv()

class APIKeyRotatorError(Exception):
    pass

class NoAPIKeysConfiguredError(APIKeyRotatorError):
    pass

class AllAPIKeysExhaustedError(APIKeyRotatorError):
    pass

class APIKeyRotator:
    def __init__(self, daily_limit, state_file="api_state.json"):
        self.keys = [
            os.getenv("GROQ_API_KEY"),
            os.getenv("GROQ_API_KEY_BACKUP_1"),
            os.getenv("GROQ_API_KEY_BACKUP_2")
        ]
        
        # Filter out any keys that failed to load (are None)
        self.keys = [k for k in self.keys if k]
        if not self.keys:
            raise NoAPIKeysConfiguredError("No API keys found in environment variables.")

        self.daily_limit = daily_limit
        self.state_file = state_file
        self.logger = setup_logger(self.__class__.__name__, "api_key_rotator.log")
        
        # Use string indices instead of raw keys for JSON compatibility and security
        self.usage_counts = {str(i): 0 for i in range(len(self.keys))}
        self.current_index = 0
        self.last_reset_date = date.today()

        # Load persistent state and verify daily reset
        self._load_state()
        self._check_daily_reset()

    def _load_state(self):
        """Loads usage data from the JSON file if it exists."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    self.last_reset_date = date.fromisoformat(data.get("last_reset_date", str(date.today())))
                    self.current_index = data.get("current_index", 0)
                    self.usage_counts = data.get("usage_counts", self.usage_counts)
            except (json.JSONDecodeError, ValueError):
                self.logger.warning("State file is corrupted. Starting fresh.")

    def _save_state(self):
        """Saves current usage data to the JSON file."""
        with open(self.state_file, 'w') as f:
            json.dump({
                "last_reset_date": str(self.last_reset_date),
                "current_index": self.current_index,
                "usage_counts": self.usage_counts
            }, f, indent=4)

    def _check_daily_reset(self):
        """Checks if the date has changed and resets the counters if so."""
        today = date.today()
        if today != self.last_reset_date:
            self.usage_counts = {str(i): 0 for i in range(len(self.keys))}
            self.last_reset_date = today
            self.current_index = 0
            self._save_state()

    def change_api_key(self):
        """Moves to the next available API key that has quota left."""
        self._check_daily_reset()
        
        start_index = self.current_index
        
        while True:
            self.current_index = (self.current_index + 1) % len(self.keys)
            str_idx = str(self.current_index)
            
            if self.usage_counts[str_idx] < self.daily_limit:
                self.logger.info(f"Limit reached. Switched to API Key {self.current_index + 1}")
                self._save_state()
                return self.keys[self.current_index]
                
            if self.current_index == start_index:
                self.logger.error("CRITICAL: Daily limit reached for all API keys.")
                raise AllAPIKeysExhaustedError("Daily limit reached for all API keys.")

    def get_current_key(self):
        """Returns the current key, changing it if it's currently maxed out."""
        self._check_daily_reset()
        str_idx = str(self.current_index)
        
        if self.usage_counts[str_idx] >= self.daily_limit:
            return self.change_api_key()
            
        return self.keys[self.current_index]

    def record_usage(self):
        """Call this function every time you make an API request."""
        str_idx = str(self.current_index)
        self.usage_counts[str_idx] += 1
        self._save_state()