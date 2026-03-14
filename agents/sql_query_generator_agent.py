from agents.schemas import SQLQuery
from schemas import QueryAnalysis, SQLQuery, SQLGeneration
import sys, os, json
from datetime import date, datetime, UTC
from pathlib import Path
from pydantic import ValidationError
from typing import List, Dict, Any


# Calculates the path to the project root (one level up from /agents/)
root_path = str(Path(__file__).resolve().parents[1])
if root_path not in sys.path:
    sys.path.append(root_path)

from utils.helper_functions import retrieve_prompt
from utils.groq_llm_service import GroqServiceError, GroqAllKeysExhaustedError, GroqNoAPIKeysConfiguredError, generate_groq_response
from utils.logger import setup_logger


class SQLQueryGeneratorAgent:

    def __init__(self,model, llm_service):
        self.error_logger = setup_logger(self.__class__.__name__, "error.log")
        self.logger = setup_logger(self.__class__.__name__, "system.log")
        self.llm_service = llm_service
        self.model = model

    def _build_user_prompt(self, user_query: str, query_analysis: QueryAnalysis) -> str:
        return f"""
            User query:
            {user_query}

            Structured query analysis:
            {query_analysis.model_dump_json(indent=2)}

            Instructions:
            - Generate the full SQLGeneration JSON object.
            - Each item in sql_queries must contain:
            - query_name
            - purpose
            - sql
            - The sql field must itself be a JSON object with this shape:
            {{
                "sql": "SELECT ...",
                "params": {{}},
                "max_rows": 10
            }}
            - params is optional if not needed.
            - max_rows is optional if not needed.
            - Use parameterized SQL wherever possible.
            - Return only valid JSON.
            """.strip()

    def _generate_sql_queries(
        self,
        user_query: str,
        query_analysis: QueryAnalysis,
        run_id: str
    ) -> SQLGeneration:
        """
        Sends the query analysis and user query to the LLM and returns
        a validated SQLGeneration object.
        """
        try:
            self.logger.info(f"[{run_id}] Sending query analysis to SQL Query Generator LLM")

            system_prompt = retrieve_prompt("sql_query_generator_agent")
            user_prompt = self._build_user_prompt(
                user_query=user_query,
                query_analysis=query_analysis
            )

            messages = [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ]

            raw_content = self.llm_service(
                messages=messages,
                model=self.model,
                require_json=True
            )

            parsed_response = json.loads(raw_content)
            sql_generation = SQLGeneration(**parsed_response)

            self.logger.info(
                f"[{run_id}] SQL query generation completed | "
                f"fields={sql_generation.telemetry_fields_needed} | "
                f"operations={sql_generation.analysis_operations} | "
                f"num_queries={len(sql_generation.sql_queries)} | "
                f"confidence={sql_generation.confidence:.2f}"
            )

            for idx, sql_query in enumerate(sql_generation.sql_queries, start=1):
                self.logger.info(
                    f"[{run_id}] SQL query {idx} | "
                    f"name={sql_query.query_name} | "
                    f"purpose={sql_query.purpose} | "
                    f"payload={sql_query.sql.model_dump()}"
                )

            return sql_generation

        except GroqNoAPIKeysConfiguredError as e:
            self.error_logger.error(
                f"[{run_id}] SQLQueryGeneratorAgent configuration error: no Groq API keys configured | {e}"
            )
            raise

        except GroqAllKeysExhaustedError as e:
            self.error_logger.error(
                f"[{run_id}] SQLQueryGeneratorAgent blocked: all Groq API keys exhausted | {e}"
            )
            raise

        except GroqServiceError as e:
            self.error_logger.error(
                f"[{run_id}] SQLQueryGeneratorAgent LLM service failure | {e}"
            )
            raise

        except json.JSONDecodeError as e:
            self.error_logger.error(
                f"[{run_id}] SQLQueryGeneratorAgent returned invalid JSON | {e}"
            )
            raise

        except ValidationError as e:
            self.error_logger.error(
                f"[{run_id}] SQLQueryGeneratorAgent schema validation failed | {e}"
            )
            raise

        except Exception as e:
            self.error_logger.error(
                f"[{run_id}] SQLQueryGeneratorAgent _generate_sql_queries failed: {e}"
            )
            raise

    def run_sql_query_generator(self, state: dict) -> dict:
        """
        Main function for the SQL query generator node.

        Expected input state:
        {
            "run_id": "some_unique_id",
            "query": "what was the max rpm?",
            "query_analysis": QueryAnalysis(...)
        }

        Returns:
        {
            "sql_generation": SQLGeneration(...)
        }
        """
        run_id = state["run_id"]
        user_query = state["query"]
        query_analysis = state["query_analysis"]

        try:
            self.logger.info(f"[{run_id}] SQLQueryGeneratorAgent started")

            sql_generation = self._generate_sql_queries(
                user_query=user_query,
                query_analysis=query_analysis,
                run_id=run_id
            )

            self.logger.info(f"[{run_id}] SQLQueryGeneratorAgent completed")

            return {
                "sql_generation": sql_generation
            }

        except GroqNoAPIKeysConfiguredError as e:
            self.error_logger.error(
                f"[{run_id}] SQLQueryGeneratorAgent failed: no API keys configured | {e}"
            )
            raise

        except GroqAllKeysExhaustedError as e:
            self.error_logger.error(
                f"[{run_id}] SQLQueryGeneratorAgent failed: API key limit reached | {e}"
            )
            raise

        except GroqServiceError as e:
            self.error_logger.error(
                f"[{run_id}] SQLQueryGeneratorAgent failed: Groq service error | {e}"
            )
            raise

        except Exception as e:
            self.error_logger.error(
                f"[{run_id}] SQLQueryGeneratorAgent failed: {e}"
            )
            raise


if __name__ == "__main__":
    sqagent = SQLQueryGeneratorAgent(
        model="openai/gpt-oss-120b",
        llm_service=generate_groq_response
    )