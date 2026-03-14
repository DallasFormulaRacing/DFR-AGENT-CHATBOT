from schemas import SQLGeneration, QueryExecutionResult, DataGetterOutput
import sys, os, asyncio, time, re
from datetime import datetime, UTC
from pathlib import Path
from typing import Dict, Any, List

import httpx
from dotenv import load_dotenv
from pydantic import ValidationError

# Calculates the path to the project root (one level up from /agents/)
root_path = str(Path(__file__).resolve().parents[1])
if root_path not in sys.path:
    sys.path.append(root_path)

from utils.logger import setup_logger
from utils.postgres_api_service import (
    PostgresAPIService,
    PostgresAPIServiceError,
    PostgresAPIRateLimitError,
    PostgresAPIAuthError,
    PostgresAPIBadRequestError,
    PostgresAPIUnavailableError,
    PostgresAPIConfigError,
)

load_dotenv(override=True)

class SQLQueryRunnerAgent:

    def __init__(self, max_concurrent_requests: int = 5, timeout_seconds: float = 20.0):
        self.error_logger = setup_logger(self.__class__.__name__, "error.log")
        self.logger = setup_logger(self.__class__.__name__, "system.log")
        self.postgres_logger = setup_logger(self.__class__.__name__, "Postgres.log")

        self.max_concurrent_requests = max_concurrent_requests
        self.timeout_seconds = timeout_seconds
        self.postgres_service = PostgresAPIService(timeout_seconds=timeout_seconds)

        self.max_rows_default = 1000
        self.max_rows_hard_cap = 10000
        self.allowed_schema = "llm_agent_api"

    def _validate_query_payload(self, payload: Dict[str, Any]) -> None:
        """
        Fast local validation to catch obvious API violations before sending.
        """
        sql_text = payload.get("sql")
        max_rows = payload.get("max_rows", self.max_rows_default)

        if not sql_text or not isinstance(sql_text, str):
            raise ValueError("SQL payload must contain a non-empty 'sql' string.")

        if not isinstance(max_rows, int):
            raise ValueError("max_rows must be an integer if provided.")

        if max_rows < 1 or max_rows > self.max_rows_hard_cap:
            raise ValueError(
                f"max_rows must be between 1 and {self.max_rows_hard_cap}."
            )

        low_sql = sql_text.lower()

        if f"{self.allowed_schema}." not in low_sql:
            raise ValueError(
                f"SQL must reference only the allowed schema '{self.allowed_schema}'."
            )

        if "pg_catalog." in low_sql or "information_schema." in low_sql:
            raise ValueError("SQL cannot reference pg_catalog or information_schema.")

    async def _execute_single_query(
        self,
        client: httpx.AsyncClient,
        sql_query,
        run_id: str,
        semaphore: asyncio.Semaphore
    ) -> QueryExecutionResult:
        async with semaphore:
            start = time.perf_counter()

            try:
                self.logger.info(
                    f"[{run_id}] Executing SQL query | "
                    f"name={sql_query.query_name} | purpose={sql_query.purpose}"
                )

                payload = sql_query.sql.model_dump() if hasattr(sql_query.sql, "model_dump") else sql_query.sql
                self._validate_query_payload(payload)

                self.postgres_logger.info(
                    f"[{run_id}] REQUEST | "
                    f"query_name={sql_query.query_name} | "
                    f"payload={payload}"
                )

                response_json = await self.postgres_service.execute_query(
                    client=client,
                    payload=payload
                )

                execution_time_ms = round((time.perf_counter() - start) * 1000, 2)
                row_count = response_json.get("row_count")

                self.postgres_logger.info(
                    f"[{run_id}] SUCCESS | "
                    f"query_name={sql_query.query_name} | "
                    f"execution_time_ms={execution_time_ms} | "
                    f"row_count={row_count} | "
                    f"response={response_json}"
                )

                return QueryExecutionResult(
                    query_name=sql_query.query_name,
                    purpose=sql_query.purpose,
                    sql=payload,
                    success=True,
                    execution_time_ms=execution_time_ms,
                    row_count=row_count,
                    result_json=response_json,
                    error_message=None
                )

            except (
                PostgresAPIRateLimitError,
                PostgresAPIAuthError,
                PostgresAPIBadRequestError,
                PostgresAPIUnavailableError,
                PostgresAPIServiceError,
                ValueError,
            ) as e:
                execution_time_ms = round((time.perf_counter() - start) * 1000, 2)

                self.error_logger.error(
                    f"[{run_id}] SQL query failed | "
                    f"query_name={sql_query.query_name} | "
                    f"execution_time_ms={execution_time_ms} | "
                    f"error={e}"
                )

                self.postgres_logger.error(
                    f"[{run_id}] FAILED | "
                    f"query_name={sql_query.query_name} | "
                    f"execution_time_ms={execution_time_ms} | "
                    f"error={e}"
                )

                return QueryExecutionResult(
                    query_name=sql_query.query_name,
                    purpose=sql_query.purpose,
                    sql=sql_query.sql.model_dump() if hasattr(sql_query.sql, "model_dump") else sql_query.sql,
                    success=False,
                    execution_time_ms=execution_time_ms,
                    row_count=None,
                    result_json=None,
                    error_message=str(e)
                )

            except Exception as e:
                execution_time_ms = round((time.perf_counter() - start) * 1000, 2)

                self.error_logger.error(
                    f"[{run_id}] Unexpected SQL query failure | "
                    f"query_name={sql_query.query_name} | "
                    f"execution_time_ms={execution_time_ms} | "
                    f"error={e}"
                )

                return QueryExecutionResult(
                    query_name=sql_query.query_name,
                    purpose=sql_query.purpose,
                    sql=sql_query.sql.model_dump() if hasattr(sql_query.sql, "model_dump") else sql_query.sql,
                    success=False,
                    execution_time_ms=execution_time_ms,
                    row_count=None,
                    result_json=None,
                    error_message=str(e)
                )

    def _aggregate_results(
        self,
        query_results: List[QueryExecutionResult],
        run_id: str
    ) -> DataGetterOutput:
        total_queries = len(query_results)
        successful_queries = sum(1 for q in query_results if q.success)
        failed_queries = total_queries - successful_queries
        total_execution_time_ms = round(sum(q.execution_time_ms or 0 for q in query_results), 2)

        aggregated_output = DataGetterOutput(
            query_results=query_results,
            total_queries=total_queries,
            successful_queries=successful_queries,
            failed_queries=failed_queries,
            total_execution_time_ms=total_execution_time_ms,
            generated_at=datetime.now(UTC)
        )

        self.logger.info(
            f"[{run_id}] Query results aggregated | "
            f"total_queries={total_queries} | "
            f"successful_queries={successful_queries} | "
            f"failed_queries={failed_queries} | "
            f"total_execution_time_ms={total_execution_time_ms}"
        )

        return aggregated_output

    async def _run_queries_async(
        self,
        sql_generation: SQLGeneration,
        run_id: str
    ) -> DataGetterOutput:
        semaphore = asyncio.Semaphore(self.max_concurrent_requests)
        timeout = httpx.Timeout(self.timeout_seconds)

        async with httpx.AsyncClient(timeout=timeout) as client:
            tasks = [
                self._execute_single_query(
                    client=client,
                    sql_query=sql_query,
                    run_id=run_id,
                    semaphore=semaphore
                )
                for sql_query in sql_generation.sql_queries
            ]

            query_results = await asyncio.gather(*tasks)

        return self._aggregate_results(query_results=query_results, run_id=run_id)

    async def run_sql_query_runner(self, state: dict) -> dict:
        run_id = state["run_id"]
        sql_generation = state["sql_generation"]

        try:
            self.logger.info(f"[{run_id}] SQLQueryRunnerAgent started")

            data_getter_output = await self._run_queries_async(
                sql_generation=sql_generation,
                run_id=run_id
            )

            self.logger.info(f"[{run_id}] SQLQueryRunnerAgent completed")

            return {
                "data_getter_output": data_getter_output
            }

        except PostgresAPIConfigError as e:
            self.error_logger.error(
                f"[{run_id}] SQLQueryRunnerAgent configuration failure | {e}"
            )
            raise

        except ValidationError as e:
            self.error_logger.error(
                f"[{run_id}] SQLQueryRunnerAgent schema validation failed | {e}"
            )
            raise

        except Exception as e:
            self.error_logger.error(
                f"[{run_id}] SQLQueryRunnerAgent failed | {e}"
            )
            raise


if __name__ == "__main__":
    agent = SQLQueryRunnerAgent(
        max_concurrent_requests=5,
        timeout_seconds=20.0
    )