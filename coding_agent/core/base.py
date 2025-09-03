"""Base classes and interfaces for the coding agent"""

from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
import uuid


class TaskType(Enum):
    """Types of tasks the agent can handle"""
    IMPLEMENTATION = "implementation"
    REFACTORING = "refactoring"
    BUG_FIX = "bug_fix"
    FEATURE = "feature"
    OPTIMIZATION = "optimization"
    DOCUMENTATION = "documentation"
    TEST_GENERATION = "test_generation"


class TaskStatus(Enum):
    """Status of a task"""
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    NEEDS_CLARIFICATION = "needs_clarification"
    UNDER_REVIEW = "under_review"


class Priority(Enum):
    """Task priority levels"""
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4
    TRIVIAL = 5


@dataclass
class TaskContext:
    """Context information for a task"""
    repository_url: Optional[str] = None
    branch: str = "main"
    base_branch: Optional[str] = None
    relevant_files: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    related_issues: List[str] = field(default_factory=list)
    environment_vars: Dict[str, str] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskSpecification:
    """Complete specification for a task"""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: TaskType = TaskType.IMPLEMENTATION
    priority: Priority = Priority.MEDIUM
    title: str = ""
    description: str = ""
    requirements: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    context: TaskContext = field(default_factory=TaskContext)
    deadline: Optional[datetime] = None
    estimated_hours: float = 1.0
    assigned_to: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    parent_task_id: Optional[str] = None
    subtask_ids: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'task_id': self.task_id,
            'type': self.type.value,
            'priority': self.priority.value,
            'title': self.title,
            'description': self.description,
            'requirements': self.requirements,
            'acceptance_criteria': self.acceptance_criteria,
            'context': {
                'repository_url': self.context.repository_url,
                'branch': self.context.branch,
                'base_branch': self.context.base_branch,
                'relevant_files': self.context.relevant_files,
                'dependencies': self.context.dependencies,
                'related_issues': self.context.related_issues,
                'environment_vars': self.context.environment_vars,
                'constraints': self.context.constraints,
                'metadata': self.context.metadata
            },
            'deadline': self.deadline.isoformat() if self.deadline else None,
            'estimated_hours': self.estimated_hours,
            'assigned_to': self.assigned_to,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'parent_task_id': self.parent_task_id,
            'subtask_ids': self.subtask_ids
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskSpecification":
        """Create from dictionary"""
        spec = cls()
        
        spec.task_id = data.get('task_id', str(uuid.uuid4()))
        spec.type = TaskType(data.get('type', 'implementation'))
        spec.priority = Priority(data.get('priority', 3))
        spec.title = data.get('title', '')
        spec.description = data.get('description', '')
        spec.requirements = data.get('requirements', [])
        spec.acceptance_criteria = data.get('acceptance_criteria', [])
        
        if 'context' in data:
            ctx = data['context']
            spec.context = TaskContext(
                repository_url=ctx.get('repository_url'),
                branch=ctx.get('branch', 'main'),
                base_branch=ctx.get('base_branch'),
                relevant_files=ctx.get('relevant_files', []),
                dependencies=ctx.get('dependencies', []),
                related_issues=ctx.get('related_issues', []),
                environment_vars=ctx.get('environment_vars', {}),
                constraints=ctx.get('constraints', {}),
                metadata=ctx.get('metadata', {})
            )
        
        if 'deadline' in data and data['deadline']:
            spec.deadline = datetime.fromisoformat(data['deadline'])
        
        spec.estimated_hours = data.get('estimated_hours', 1.0)
        spec.assigned_to = data.get('assigned_to')
        
        if 'created_at' in data:
            spec.created_at = datetime.fromisoformat(data['created_at'])
        if 'updated_at' in data:
            spec.updated_at = datetime.fromisoformat(data['updated_at'])
        
        spec.parent_task_id = data.get('parent_task_id')
        spec.subtask_ids = data.get('subtask_ids', [])
        
        return spec


@dataclass
class TaskResult:
    """Result of task execution"""
    task_id: str
    status: TaskStatus
    result_type: str = "success"  # success, error, partial
    changes_made: List[Dict[str, Any]] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    files_created: List[str] = field(default_factory=list)
    files_deleted: List[str] = field(default_factory=list)
    tests_added: List[str] = field(default_factory=list)
    issues_created: List[str] = field(default_factory=list)
    pull_request_url: Optional[str] = None
    commit_hash: Optional[str] = None
    error_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    execution_time: float = 0.0
    completed_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AgentMessage:
    """Message format for agent communication"""
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender_id: str = ""
    recipient_id: str = ""
    message_type: str = ""  # task, result, query, response, heartbeat
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    correlation_id: Optional[str] = None
    reply_to: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'message_id': self.message_id,
            'sender_id': self.sender_id,
            'recipient_id': self.recipient_id,
            'message_type': self.message_type,
            'payload': self.payload,
            'timestamp': self.timestamp.isoformat(),
            'correlation_id': self.correlation_id,
            'reply_to': self.reply_to
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentMessage":
        """Create from dictionary"""
        msg = cls()
        msg.message_id = data.get('message_id', str(uuid.uuid4()))
        msg.sender_id = data.get('sender_id', '')
        msg.recipient_id = data.get('recipient_id', '')
        msg.message_type = data.get('message_type', '')
        msg.payload = data.get('payload', {})
        
        if 'timestamp' in data:
            msg.timestamp = datetime.fromisoformat(data['timestamp'])
        
        msg.correlation_id = data.get('correlation_id')
        msg.reply_to = data.get('reply_to')
        
        return msg


class TaskExecutor(ABC):
    """Abstract base class for task executors"""
    
    @abstractmethod
    async def execute(self, task: TaskSpecification) -> TaskResult:
        """Execute a task and return the result"""
        pass
    
    @abstractmethod
    async def validate(self, task: TaskSpecification) -> bool:
        """Validate if the task can be executed"""
        pass


class MessageHandler(ABC):
    """Abstract base class for message handlers"""
    
    @abstractmethod
    async def send_message(self, message: AgentMessage) -> bool:
        """Send a message"""
        pass
    
    @abstractmethod
    async def receive_message(self) -> Optional[AgentMessage]:
        """Receive a message"""
        pass
    
    @abstractmethod
    async def send_progress(self, task_id: str, progress: float, message: str) -> bool:
        """Send progress update"""
        pass