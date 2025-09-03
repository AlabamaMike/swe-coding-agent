"""Autonomous Coding Agent for Implementation and Refactoring Tasks"""

__version__ = "0.1.0"

from .core.agent import CodingAgent
from .core.config import AgentConfig

__all__ = ["CodingAgent", "AgentConfig"]