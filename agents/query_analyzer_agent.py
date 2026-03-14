#Function : This agent is responsible for analyzing the user query and generating a query analysis object which includes the type of data needed to analyze to answer the query. 
from schemas import QueryAnalysis
import sys, os, json
from datetime import date, datetime, UTC
from pathlib import Path
from pydantic import ValidationError

# Calculates the path to the project root (one level up from /agents/)
root_path = str(Path(__file__).resolve().parents[1])
if root_path not in sys.path:
    sys.path.append(root_path)

from utils.helper_functions import retrieve_prompt
from utils.groq_llm_service import GroqServiceError, GroqAllKeysExhaustedError, GroqNoAPIKeysConfiguredError, generate_groq_response
from utils.logger import setup_logger


class QueryAnalyzerAgent:

    def __init__(self,model, llm_service):
        self.error_logger = setup_logger(self.__class__.__name__, "error.log")
        self.logger = setup_logger(self.__class__.__name__, "system.log")
        self.llm_service = llm_service
        self.model = model

    def _analyze_query(self, query: str, run_id: str) -> QueryAnalysis:
        """
        Sends the user query to the LLM and returns a validated QueryAnalysis object.
        """
        try:
            self.logger.info(f"[{run_id}] Sending query to QueryAnalyzer LLM")

            system_prompt = retrieve_prompt("query_analyzer_agent")

            user_prompt = f"""
                User query:
                {query}

                Return only valid JSON.
                """.strip()

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

            raw_content = self.llm_service(messages=messages, model=self.model, require_json=True)
            parsed_response = json.loads(raw_content)

            query_analysis = QueryAnalysis(**parsed_response)

            self.logger.info(
                f"[{run_id}] Query analysis completed | "
                f"intent={query_analysis.intent} | "
                f"fields={query_analysis.telemetry_fields_needed} | "
                f"operations={query_analysis.analysis_operations} | "
                f"confidence={query_analysis.confidence:.2f}"
            )

            return query_analysis
        
        except GroqNoAPIKeysConfiguredError as e:
            self.error_logger.error(
                f"[{run_id}] QueryAnalyzerAgent configuration error: no Groq API keys configured | {e}"
            )
            raise

        except GroqAllKeysExhaustedError as e:
            self.error_logger.error(
                f"[{run_id}] QueryAnalyzerAgent blocked: all Groq API keys exhausted | {e}"
            )
            raise

        except GroqServiceError as e:
            self.error_logger.error(
                f"[{run_id}] QueryAnalyzerAgent LLM service failure | {e}"
            )
            raise

        except json.JSONDecodeError as e:
            self.error_logger.error(
                f"[{run_id}] QueryAnalyzerAgent returned invalid JSON | {e}"
            )
            raise

        except ValidationError as e:
            self.error_logger.error(
                f"[{run_id}] QueryAnalyzerAgent schema validation failed | {e}"
            )
            raise

        except Exception as e:
            self.error_logger.error(f"[{run_id}] QueryAnalyzerAgent _analyze_query failed: {e}")
            raise

    def run_query_analyzer(self, state: dict) -> dict:
        """
        Main function for the query analyzer node.

        Expected input state:
        {
            "run_id": "some_unique_id",
            "query": "what was the max rpm?"
        }

        Returns:
        {
            "query_analysis": QueryAnalysis(...)
        }
        """
        run_id = state["run_id"]
        query = state["query"]

        try:
            self.logger.info(f"[{run_id}] QueryAnalyzerAgent started")

            query_analysis = self._analyze_query(query=query, run_id=run_id)

            self.logger.info(f"[{run_id}] QueryAnalyzerAgent completed")

            return {
                "query_analysis": query_analysis
            }

        except GroqNoAPIKeysConfiguredError as e:
            self.error_logger.error(
                f"[{run_id}] QueryAnalyzerAgent failed: no API keys configured | {e}"
            )
            raise

        except GroqAllKeysExhaustedError as e:
            self.error_logger.error(
                f"[{run_id}] QueryAnalyzerAgent failed: API key limit reached | {e}"
            )
            raise

        except GroqServiceError as e:
            self.error_logger.error(
                f"[{run_id}] QueryAnalyzerAgent failed: Groq service error | {e}"
            )
            raise

        except Exception as e:
            self.error_logger.error(f"[{run_id}] QueryAnalyzerAgent failed: {e}")
            raise


if __name__ == "__main__":
    qagent = QueryAnalyzerAgent(model="openai/gpt-oss-120b")
