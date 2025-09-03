"""Configuration management for the coding agent"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from pathlib import Path
import os
import json


@dataclass
class MessageQueueConfig:
    """Message queue configuration"""
    broker_type: str = "rabbitmq"  # rabbitmq, kafka, redis
    host: str = "localhost"
    port: int = 5672
    username: str = "guest"
    password: str = "guest"
    queue_name: str = "coding_agent_tasks"
    exchange: str = "agent_swarm"
    routing_key: str = "coding.tasks"
    ssl_enabled: bool = False
    connection_timeout: int = 30
    retry_attempts: int = 3
    retry_delay: int = 5


@dataclass
class MCPConfig:
    """MCP (Model Context Protocol) configuration"""
    server_type: str = "composio"  # composio, rube
    api_key: Optional[str] = field(default_factory=lambda: os.getenv("COMPOSIO_API_KEY"))
    base_url: str = "https://api.composio.dev"
    timeout: int = 60
    max_retries: int = 3
    tools: List[str] = field(default_factory=lambda: [
        "github",
        "git",
        "file_manager",
        "code_interpreter"
    ])


@dataclass
class GitHubConfig:
    """GitHub integration configuration"""
    token: Optional[str] = field(default_factory=lambda: os.getenv("GITHUB_TOKEN"))
    api_url: str = "https://api.github.com"
    timeout: int = 30
    max_issues_per_task: int = 5
    auto_create_issues: bool = True
    issue_labels: List[str] = field(default_factory=lambda: ["coding-agent", "automated"])


@dataclass
class ExecutionConfig:
    """Execution environment configuration"""
    max_execution_time: int = 3600  # seconds
    max_memory_mb: int = 2048
    max_file_size_mb: int = 100
    allowed_file_extensions: List[str] = field(default_factory=lambda: [
        ".py", ".pyi", ".ipynb", ".yml", ".yaml", ".json", ".toml", ".cfg", ".ini",
        ".txt", ".md", ".rst", ".requirements", ".gitignore", ".env.example"
    ])
    sandbox_enabled: bool = True
    docker_image: str = "python:3.11-slim"
    working_directory: Path = field(default_factory=lambda: Path("/tmp/coding_agent"))


@dataclass
class RefactoringConfig:
    """Refactoring capabilities configuration"""
    enabled_refactorings: List[str] = field(default_factory=lambda: [
        "extract_method",
        "extract_class",
        "inline_method",
        "inline_variable",
        "rename_symbol",
        "move_method",
        "pull_up_method",
        "push_down_method",
        "extract_interface",
        "introduce_parameter_object",
        "replace_temp_with_query",
        "replace_conditional_with_polymorphism",
        "decompose_conditional",
        "consolidate_duplicate_conditionals",
        "remove_dead_code"
    ])
    auto_format: bool = True
    formatter: str = "black"
    linter: str = "ruff"
    type_checker: str = "mypy"


@dataclass
class TestingConfig:
    """Test generation configuration"""
    framework: str = "pytest"  # pytest, unittest
    coverage_threshold: float = 80.0
    generate_fixtures: bool = True
    generate_mocks: bool = True
    generate_edge_cases: bool = True
    test_types: List[str] = field(default_factory=lambda: [
        "unit", "integration", "end_to_end"
    ])
    mock_library: str = "unittest.mock"  # unittest.mock, pytest-mock


@dataclass
class LoggingConfig:
    """Logging configuration"""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file_path: Optional[Path] = field(default_factory=lambda: Path("coding_agent.log"))
    console_output: bool = True
    max_file_size_mb: int = 100
    backup_count: int = 5


@dataclass
class AgentConfig:
    """Main configuration for the coding agent"""
    agent_id: str = field(default_factory=lambda: f"coding_agent_{os.getpid()}")
    agent_name: str = "CodingAgent"
    version: str = "0.1.0"
    
    message_queue: MessageQueueConfig = field(default_factory=MessageQueueConfig)
    mcp: MCPConfig = field(default_factory=MCPConfig)
    github: GitHubConfig = field(default_factory=GitHubConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    refactoring: RefactoringConfig = field(default_factory=RefactoringConfig)
    testing: TestingConfig = field(default_factory=TestingConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    
    max_concurrent_tasks: int = 3
    task_timeout: int = 1800  # seconds
    heartbeat_interval: int = 30  # seconds
    
    @classmethod
    def from_file(cls, path: Path) -> "AgentConfig":
        """Load configuration from JSON or YAML file"""
        with open(path, 'r') as f:
            if path.suffix in ['.yml', '.yaml']:
                import yaml
                data = yaml.safe_load(f)
            else:
                data = json.load(f)
        return cls.from_dict(data)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentConfig":
        """Create configuration from dictionary"""
        config = cls()
        
        if 'message_queue' in data:
            config.message_queue = MessageQueueConfig(**data['message_queue'])
        if 'mcp' in data:
            config.mcp = MCPConfig(**data['mcp'])
        if 'github' in data:
            config.github = GitHubConfig(**data['github'])
        if 'execution' in data:
            config.execution = ExecutionConfig(**data['execution'])
        if 'refactoring' in data:
            config.refactoring = RefactoringConfig(**data['refactoring'])
        if 'testing' in data:
            config.testing = TestingConfig(**data['testing'])
        if 'logging' in data:
            config.logging = LoggingConfig(**data['logging'])
        
        for key in ['agent_id', 'agent_name', 'version', 'max_concurrent_tasks', 
                    'task_timeout', 'heartbeat_interval']:
            if key in data:
                setattr(config, key, data[key])
        
        return config
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return {
            'agent_id': self.agent_id,
            'agent_name': self.agent_name,
            'version': self.version,
            'message_queue': self.message_queue.__dict__,
            'mcp': self.mcp.__dict__,
            'github': self.github.__dict__,
            'execution': self.execution.__dict__,
            'refactoring': self.refactoring.__dict__,
            'testing': self.testing.__dict__,
            'logging': self.logging.__dict__,
            'max_concurrent_tasks': self.max_concurrent_tasks,
            'task_timeout': self.task_timeout,
            'heartbeat_interval': self.heartbeat_interval
        }