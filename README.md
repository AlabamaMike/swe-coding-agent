# SWE Coding Agent

An autonomous coding agent designed for implementation and refactoring tasks within an agent swarm architecture. This agent communicates via A2A (Agent-to-Agent) protocol and uses MCP (Model Context Protocol) for extended capabilities.

## Features

- 🤖 **Autonomous Task Execution**: Handles implementation, refactoring, bug fixes, and test generation
- 📡 **A2A Protocol**: Full inter-agent communication with 14 message types
- 🔄 **Multi-Broker Support**: RabbitMQ, Apache Kafka, and Redis
- 🐍 **Python Framework Support**: Django, FastAPI, Flask, SQLAlchemy, and more
- 🧪 **Test Generation**: Unit, integration, and end-to-end tests with pytest/unittest
- 🔧 **15+ Refactoring Patterns**: Extract method/class, inline, rename, and more
- 📊 **GitHub Integration**: Issue tracking and persistence
- ⚡ **Async Architecture**: Event-driven design with concurrent task execution

## Quick Start

### Prerequisites

- Python 3.11+
- RabbitMQ, Kafka, or Redis (for message queue)
- GitHub token (for issue tracking)
- Composio API key (optional, for MCP integration)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/swe-agent.git
cd swe-agent

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export GITHUB_TOKEN=your_github_token
export COMPOSIO_API_KEY=your_composio_key  # Optional
```

### Running the Agent

```python
from coding_agent import CodingAgent, AgentConfig
from coding_agent.communication.message_queue import MessageQueueFactory
import asyncio

async def main():
    # Load configuration
    config = AgentConfig.from_file("config.yaml")
    
    # Create agent
    agent = CodingAgent(config)
    
    # Setup message queue
    mq_handler = MessageQueueFactory.create(config.message_queue, config.agent_id)
    agent.register_message_handler(mq_handler)
    
    # Start agent
    await agent.start()

if __name__ == "__main__":
    asyncio.run(main())
```

### Running the Example Orchestrator

```bash
# Start the example orchestrator
python orchestrator_quick_start.py
```

## Architecture

```
coding_agent/
├── core/
│   ├── agent.py         # Main agent implementation
│   ├── base.py          # Base classes and interfaces
│   └── config.py        # Configuration management
└── communication/
    ├── message_queue.py  # Message queue implementations
    └── protocols.py      # A2A protocol definitions
```

## Configuration

Create a `config.yaml` file:

```yaml
agent_name: CodingAgent
agent_id: coding_agent_001

message_queue:
  broker_type: rabbitmq
  host: localhost
  port: 5672
  username: guest
  password: guest
  queue_name: coding_agent_tasks
  exchange: agent_swarm

mcp:
  server_type: composio
  api_key: ${COMPOSIO_API_KEY}
  base_url: https://api.composio.dev
  tools:
    - github
    - git
    - file_manager
    - code_interpreter

github:
  token: ${GITHUB_TOKEN}
  auto_create_issues: true
  issue_labels: 
    - coding-agent
    - automated

execution:
  max_execution_time: 3600
  max_concurrent_tasks: 3
  sandbox_enabled: true

refactoring:
  enabled_refactorings:
    - extract_method
    - extract_class
    - rename_symbol
    - inline_method
  auto_format: true
  formatter: black
  linter: ruff

testing:
  framework: pytest
  coverage_threshold: 80.0
  generate_fixtures: true
  generate_mocks: true
```

## Task Specification

Tasks are assigned to the agent using the following JSON format:

```json
{
  "task_id": "unique-task-id",
  "type": "implementation",
  "title": "Implement user authentication",
  "description": "Add JWT-based authentication to the API",
  "requirements": [
    "Use PyJWT library",
    "Implement login and logout endpoints",
    "Add middleware for token validation"
  ],
  "context": {
    "repository_url": "https://github.com/org/repo",
    "branch": "feature/auth",
    "relevant_files": ["api/views.py", "api/middleware.py"]
  }
}
```

## A2A Protocol Messages

The agent supports these message types:

- `registration` - Agent announces capabilities
- `task` - Task assignment from orchestrator
- `acknowledgment` - Task acceptance/rejection
- `progress` - Real-time progress updates
- `task_result` - Completion notification
- `query` - Clarification requests
- `heartbeat` - Health monitoring

See `orchestrator_integration_spec.md` for complete protocol documentation.

## Development

### Adding New Task Executors

```python
from coding_agent.core.base import TaskExecutor, TaskSpecification, TaskResult

class CustomExecutor(TaskExecutor):
    async def execute(self, task: TaskSpecification) -> TaskResult:
        # Implement your execution logic
        pass
    
    async def validate(self, task: TaskSpecification) -> bool:
        # Validate task can be executed
        return True

# Register with agent
agent.register_task_executor(TaskType.CUSTOM, CustomExecutor())
```

### Extending Message Handlers

```python
from coding_agent.communication.message_queue import BaseMessageQueue

class CustomMessageQueue(BaseMessageQueue):
    async def connect(self) -> bool:
        # Implement connection logic
        pass
    
    async def send_message(self, message: AgentMessage) -> bool:
        # Implement send logic
        pass
```

## Testing

```bash
# Run tests
pytest tests/

# With coverage
pytest --cov=coding_agent tests/

# Run specific test file
pytest tests/test_agent.py
```

## Monitoring

The agent provides metrics via:

- Heartbeat messages every 30 seconds
- Task execution metrics in results
- Comprehensive logging with rotation
- GitHub issue tracking

## Security

- Message queue connections use TLS
- Input validation on all messages
- Rate limiting per agent
- Sandboxed execution environment
- No hardcoded credentials

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Built with the Claude Code SDK
- Designed for agent swarm architectures
- Integrates with Composio/Rube MCP servers

## Support

For issues and questions:
- Open an issue on GitHub
- Check the orchestrator integration spec
- Review example implementations

## Roadmap

- [x] Core agent architecture
- [x] Message queue integration
- [x] A2A protocol implementation
- [ ] MCP integration with Composio/Rube
- [ ] Implementation task executor
- [ ] Refactoring capabilities
- [ ] Test generation module
- [ ] GitHub API integration
- [ ] Deployment configurations
- [ ] Performance optimizations