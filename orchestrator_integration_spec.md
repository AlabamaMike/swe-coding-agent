# Orchestrator Integration Specification for Coding Agent

## Overview
This specification defines the A2A (Agent-to-Agent) protocol requirements for orchestrators to communicate with the Coding Agent. The Coding Agent is a specialized autonomous agent for implementation and refactoring tasks in Python projects.

## Agent Identification
- **Agent Type**: `coding_agent`
- **Capabilities**: `["implementation", "refactoring", "bug_fix", "feature", "optimization", "test_generation"]`
- **Protocol Version**: `1.0`
- **Max Concurrent Tasks**: 3 (configurable)

## Message Queue Configuration

### Supported Brokers
- **RabbitMQ** (recommended)
  - Exchange: `agent_swarm` (topic exchange)
  - Routing patterns:
    - To specific agent: `agent.{agent_id}`
    - To all agents: `agent.all`
    - To coding agents: `coding.#`
    - To orchestrator: `orchestrator.messages`

- **Kafka**
  - Topics: `agent-{agent_id}`, `agent-all`, `coding-tasks`, `orchestrator-messages`
  
- **Redis**
  - Channels: `agent:{agent_id}`, `agent:all`, `coding:tasks`, `orchestrator:messages`

## Task Specification Format

### JSON Schema for Task Assignment

```json
{
  "task_id": "uuid-v4",
  "type": "implementation|refactoring|bug_fix|feature|optimization|test_generation",
  "priority": 1-5,  // 1=CRITICAL, 2=HIGH, 3=MEDIUM, 4=LOW, 5=TRIVIAL
  "title": "Short descriptive title",
  "description": "Detailed description of the task",
  "requirements": [
    "List of specific requirements",
    "Each requirement should be clear and testable"
  ],
  "acceptance_criteria": [
    "Measurable criteria for task completion",
    "Should be verifiable"
  ],
  "context": {
    "repository_url": "https://github.com/org/repo",
    "branch": "feature/branch-name",
    "base_branch": "main",
    "relevant_files": [
      "path/to/file1.py",
      "path/to/file2.py"
    ],
    "dependencies": ["task-id-1", "task-id-2"],
    "related_issues": ["#123", "#456"],
    "environment_vars": {
      "KEY": "value"
    },
    "constraints": {
      "performance": "Must execute in < 100ms",
      "style_guide": "PEP 8",
      "framework_version": "Django 4.2+"
    },
    "metadata": {
      "additional": "context"
    }
  },
  "deadline": "2024-12-31T23:59:59Z",  // ISO 8601
  "estimated_hours": 2.5,
  "assigned_to": "coding_agent_12345",
  "parent_task_id": "parent-uuid",  // Optional
  "subtask_ids": []  // Optional
}
```

## Message Types and Protocols

### 1. Agent Registration (Agent → Orchestrator)
```json
{
  "message_id": "uuid",
  "sender_id": "coding_agent_12345",
  "recipient_id": "orchestrator",
  "message_type": "registration",
  "payload": {
    "agent_id": "coding_agent_12345",
    "agent_type": "coding_agent",
    "capabilities": ["implementation", "refactoring", "bug_fix", "feature", "optimization", "test_generation"],
    "max_concurrent_tasks": 3,
    "version": "0.1.0"
  },
  "timestamp": "2024-01-01T00:00:00Z"
}
```

### 2. Task Assignment (Orchestrator → Agent)
```json
{
  "message_id": "uuid",
  "sender_id": "orchestrator",
  "recipient_id": "coding_agent_12345",
  "message_type": "task",
  "payload": {
    // Complete task specification as defined above
  },
  "timestamp": "2024-01-01T00:00:00Z",
  "correlation_id": null,
  "reply_to": null
}
```

### 3. Task Acknowledgment (Agent → Orchestrator)
```json
{
  "message_id": "uuid",
  "sender_id": "coding_agent_12345",
  "recipient_id": "orchestrator",
  "message_type": "acknowledgment",
  "payload": {
    "task_id": "task-uuid",
    "status": "accepted|rejected",
    "reason": "Optional rejection reason"
  },
  "timestamp": "2024-01-01T00:00:00Z",
  "correlation_id": "original-message-id"
}
```

### 4. Progress Update (Agent → Orchestrator)
```json
{
  "message_id": "uuid",
  "sender_id": "coding_agent_12345",
  "recipient_id": "orchestrator",
  "message_type": "progress",
  "payload": {
    "task_id": "task-uuid",
    "progress": 0.75,  // 0.0 to 1.0
    "message": "Completed implementation, running tests",
    "timestamp": "2024-01-01T00:00:00Z"
  },
  "timestamp": "2024-01-01T00:00:00Z"
}
```

### 5. Clarification Request (Agent → Orchestrator)
```json
{
  "message_id": "uuid",
  "sender_id": "coding_agent_12345",
  "recipient_id": "orchestrator",
  "message_type": "query",
  "payload": {
    "query_type": "clarification",
    "task_id": "task-uuid",
    "question": "Should the API endpoint return JSON or XML?",
    "context": {
      "file": "api/views.py",
      "line": 42,
      "code_snippet": "def get_data(request):"
    },
    "suggested_options": ["JSON", "XML", "Both"],
    "urgency": "high"
  },
  "timestamp": "2024-01-01T00:00:00Z"
}
```

### 6. Clarification Response (Orchestrator → Agent)
```json
{
  "message_id": "uuid",
  "sender_id": "orchestrator",
  "recipient_id": "coding_agent_12345",
  "message_type": "response",
  "payload": {
    "query_type": "clarification",
    "task_id": "task-uuid",
    "answer": "JSON",
    "additional_context": "Follow REST API standards"
  },
  "timestamp": "2024-01-01T00:00:00Z",
  "correlation_id": "query-message-id"
}
```

### 7. Task Result (Agent → Orchestrator)
```json
{
  "message_id": "uuid",
  "sender_id": "coding_agent_12345",
  "recipient_id": "orchestrator",
  "message_type": "task_result",
  "payload": {
    "task_id": "task-uuid",
    "status": "completed|failed|blocked",
    "result_type": "success|error|partial",
    "files_modified": ["path/to/file1.py", "path/to/file2.py"],
    "files_created": ["path/to/new_file.py"],
    "files_deleted": [],
    "tests_added": ["test_feature.py::test_new_functionality"],
    "issues_created": ["#789"],
    "pull_request_url": "https://github.com/org/repo/pull/123",
    "commit_hash": "abc123def456",
    "error_message": null,
    "warnings": ["Consider refactoring large function at line 150"],
    "execution_time": 45.67,  // seconds
    "metrics": {
      "lines_added": 250,
      "lines_removed": 50,
      "test_coverage": 85.5,
      "complexity_reduced": true
    }
  },
  "timestamp": "2024-01-01T00:00:00Z"
}
```

### 8. Capability Query (Orchestrator → Agent)
```json
{
  "message_id": "uuid",
  "sender_id": "orchestrator",
  "recipient_id": "coding_agent_12345",
  "message_type": "query",
  "payload": {
    "query_type": "capabilities",
    "required_capabilities": ["refactoring", "django"],
    "task_context": {
      "framework": "Django",
      "complexity": "high"
    }
  },
  "timestamp": "2024-01-01T00:00:00Z"
}
```

### 9. Capability Response (Agent → Orchestrator)
```json
{
  "message_id": "uuid",
  "sender_id": "coding_agent_12345",
  "recipient_id": "orchestrator",
  "message_type": "response",
  "payload": {
    "query_type": "capabilities",
    "supported_task_types": ["implementation", "refactoring", "bug_fix", "feature", "optimization", "test_generation"],
    "max_concurrent_tasks": 3,
    "current_load": 1,
    "available_capacity": 2,
    "supported_frameworks": ["Django", "FastAPI", "Flask", "SQLAlchemy"],
    "confidence_score": 0.95
  },
  "timestamp": "2024-01-01T00:00:00Z",
  "correlation_id": "query-message-id"
}
```

### 10. Heartbeat (Agent → Orchestrator)
```json
{
  "message_id": "uuid",
  "sender_id": "coding_agent_12345",
  "recipient_id": "orchestrator",
  "message_type": "heartbeat",
  "payload": {
    "agent_id": "coding_agent_12345",
    "timestamp": "2024-01-01T00:00:00Z",
    "current_tasks": 1,
    "available_capacity": 2,
    "status": "healthy",
    "uptime": 3600  // seconds
  },
  "timestamp": "2024-01-01T00:00:00Z"
}
```

### 11. Status Request (Orchestrator → Agent)
```json
{
  "message_id": "uuid",
  "sender_id": "orchestrator",
  "recipient_id": "coding_agent_12345",
  "message_type": "status_request",
  "payload": {
    "include_task_details": true
  },
  "timestamp": "2024-01-01T00:00:00Z"
}
```

### 12. Status Response (Agent → Orchestrator)
```json
{
  "message_id": "uuid",
  "sender_id": "coding_agent_12345",
  "recipient_id": "orchestrator",
  "message_type": "status_response",
  "payload": {
    "agent_id": "coding_agent_12345",
    "status": "active|idle|busy|error",
    "current_tasks": [
      {
        "task_id": "task-uuid",
        "status": "in_progress",
        "progress": 0.5,
        "started_at": "2024-01-01T00:00:00Z"
      }
    ],
    "completed_tasks": 42,
    "failed_tasks": 2,
    "available_capacity": 2,
    "uptime": 3600,
    "last_error": null
  },
  "timestamp": "2024-01-01T00:00:00Z",
  "correlation_id": "status-request-id"
}
```

### 13. Task Cancellation (Orchestrator → Agent)
```json
{
  "message_id": "uuid",
  "sender_id": "orchestrator",
  "recipient_id": "coding_agent_12345",
  "message_type": "cancel",
  "payload": {
    "task_id": "task-uuid",
    "reason": "Priority change"
  },
  "timestamp": "2024-01-01T00:00:00Z"
}
```

### 14. Collaboration Request (Agent → Orchestrator/Other Agent)
```json
{
  "message_id": "uuid",
  "sender_id": "coding_agent_12345",
  "recipient_id": "orchestrator",
  "message_type": "collaboration_request",
  "payload": {
    "collaboration_type": "code_review",
    "task_id": "task-uuid",
    "target_agent_type": "review_agent",
    "context": {
      "files_to_review": ["path/to/file.py"],
      "focus_areas": ["security", "performance"]
    }
  },
  "timestamp": "2024-01-01T00:00:00Z"
}
```

## Error Handling

### Error Message Format
```json
{
  "message_id": "uuid",
  "sender_id": "coding_agent_12345",
  "recipient_id": "orchestrator",
  "message_type": "error",
  "payload": {
    "error_type": "task_failure|system_error|resource_error",
    "task_id": "task-uuid",  // Optional
    "error_code": "E001",
    "error_message": "Detailed error description",
    "stack_trace": "Optional stack trace",
    "recoverable": true,
    "suggested_action": "Retry with modified parameters"
  },
  "timestamp": "2024-01-01T00:00:00Z",
  "correlation_id": "original-message-id"  // Optional
}
```

## Best Practices for Orchestrator Implementation

### 1. Task Assignment Strategy
- Verify agent capabilities before assignment
- Consider current agent load
- Implement task priority queue
- Support task dependencies

### 2. Communication Patterns
- Always include correlation IDs for request-response pairs
- Implement timeout handling (suggested: 30s for acknowledgment, 1800s for task completion)
- Use heartbeat monitoring (every 30s)
- Implement exponential backoff for retries

### 3. State Management
- Track task states: `queued → assigned → in_progress → completed/failed`
- Maintain agent registry with capabilities and status
- Implement task history for GitHub issue tracking

### 4. Error Recovery
- Implement automatic retry for recoverable errors
- Reassign tasks if agent becomes unresponsive
- Maintain error logs for debugging

### 5. Performance Optimization
- Batch related tasks when possible
- Use message priorities effectively
- Implement load balancing across multiple coding agents
- Cache agent capabilities to reduce query overhead

## GitHub Integration

The Coding Agent uses GitHub issues for persistence. The orchestrator should:

1. Create issues for each task with:
   - Title: Task title
   - Body: Task specification in JSON
   - Labels: `coding-agent`, `automated`, task type
   - Assignee: Agent ID

2. Update issues with:
   - Progress comments
   - Result summary
   - Links to PRs/commits
   - Error reports

3. Close issues when tasks complete

## Example Orchestrator Workflow

```python
# Pseudo-code for orchestrator implementation

async def assign_task_to_coding_agent(task_spec):
    # 1. Find available coding agent
    agent = await find_available_agent("coding_agent")
    
    # 2. Create GitHub issue
    issue = await create_github_issue(task_spec)
    task_spec.metadata["github_issue"] = issue.number
    
    # 3. Send task assignment
    message = create_task_message(agent.id, task_spec)
    await send_message(message)
    
    # 4. Wait for acknowledgment
    ack = await wait_for_acknowledgment(message.id, timeout=30)
    
    if ack.status == "accepted":
        # 5. Monitor progress
        await monitor_task_progress(task_spec.task_id)
    else:
        # Find another agent or queue task
        await handle_rejection(task_spec, ack.reason)
    
    # 6. Handle result
    result = await wait_for_result(task_spec.task_id)
    await update_github_issue(issue, result)
    
    return result
```

## Security Considerations

1. **Authentication**: Implement agent authentication tokens
2. **Message Signing**: Consider signing critical messages
3. **Encryption**: Use TLS for message queue connections
4. **Rate Limiting**: Implement rate limits per agent
5. **Input Validation**: Validate all message payloads against schemas
6. **Audit Logging**: Log all agent interactions

## Monitoring and Observability

Track these metrics:
- Task completion rate
- Average task execution time
- Agent availability
- Message queue latency
- Error rates by type
- Agent resource utilization

## Version Compatibility

- Protocol Version: 1.0
- Minimum orchestrator version: 1.0.0
- Backward compatibility: Will maintain for 2 major versions

## Contact and Support

For questions about integration:
- Documentation: [Link to detailed docs]
- GitHub: [Repository URL]
- Support: [Contact information]