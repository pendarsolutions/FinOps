"""AI gateway: text -> InventoryDraft extraction and the evidence-bound advisor. Never computes prices."""

from .advisor import TOOLS, AdvisorAnswer, run_advisor, template_answer
from .extraction import extract_inventory
from .guard import GuardResult, check_numbers
from .llm import PROMPT_VERSION, LLMConfig
from .offline_parser import parse_description

__all__ = ["PROMPT_VERSION", "TOOLS", "AdvisorAnswer", "GuardResult", "LLMConfig", "check_numbers",
           "extract_inventory", "parse_description", "run_advisor", "template_answer"]
