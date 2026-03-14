import os
import httpx
from dotenv import load_dotenv

load_dotenv(override=True)


class PostgresAPIServiceError(Exception):
    pass


class PostgresAPIRateLimitError(PostgresAPIServiceError):
    pass


class PostgresAPIAuthError(PostgresAPIServiceError):
    pass


class PostgresAPIBadRequestError(PostgresAPIServiceError):
    pass


class PostgresAPIUnavailableError(PostgresAPIServiceError):
    pass


class PostgresAPIConfigError(PostgresAPIServiceError):
    pass


class PostgresAPIService:
    def __init__(self, timeout_seconds: float = 20.0):
        self.base_url = os.getenv("POSTGRES_API_URL")
        self.api_key = os.getenv("POSTGRES_API_KEY")
        self.timeout_seconds = timeout_seconds

        if not self.base_url:
            raise PostgresAPIConfigError("POSTGRES_API_URL is not configured.")
        if not self.api_key:
            raise PostgresAPIConfigError("POSTGRES_API_KEY is not configured.")

    def _build_headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
        }

    async def execute_query(self, client: httpx.AsyncClient, payload: dict) -> dict:
        """
        Sends one SQL payload to the Postgres API and returns parsed JSON on success.
        Raises specific service exceptions on failure.
        """
        try:
            response = await client.post(
                self.base_url,
                json=payload,
                headers=self._build_headers()
            )
        except httpx.TimeoutException as e:
            raise PostgresAPIUnavailableError(
                f"Postgres API request timed out: {e}"
            ) from e
        except httpx.RequestError as e:
            raise PostgresAPIUnavailableError(
                f"Postgres API request failed: {e}"
            ) from e

        if response.status_code == 200:
            return response.json()

        if response.status_code == 401:
            raise PostgresAPIAuthError("Invalid Postgres API key.")

        if response.status_code == 429:
            raise PostgresAPIRateLimitError("Postgres API rate limit exceeded.")

        if response.status_code == 400:
            raise PostgresAPIBadRequestError(response.text)

        if 500 <= response.status_code < 600:
            raise PostgresAPIUnavailableError(
                f"Postgres API server error: HTTP {response.status_code} | {response.text}"
            )

        raise PostgresAPIServiceError(
            f"Unexpected Postgres API response: HTTP {response.status_code} | {response.text}"
        )