"""A2A Protocol definitions and message handling"""

from enum import Enum
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime


class MessagePriority(Enum):
    """Message priority levels for routing"""
    URGENT = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


class RequestType(Enum):
    """Types of requests in A2A protocol"""
    TASK_ASSIGNMENT = "task_assignment"
    CAPABILITY_QUERY = "capability_query"
    STATUS_REQUEST = "status_request"
    CLARIFICATION_REQUEST = "clarification_request"
    RESOURCE_REQUEST = "resource_request"
    COLLABORATION_REQUEST = "collaboration_request"
    RESULT_NOTIFICATION = "result_notification"
    ERROR_REPORT = "error_report"


@dataclass
class ProtocolMessage:
    """Extended protocol message for A2A communication"""
    
    # Standard fields
    message_id: str
    sender_id: str
    recipient_id: str
    message_type: str
    payload: Dict[str, Any]
    timestamp: datetime
    
    # Protocol-specific fields
    protocol_version: str = "1.0"
    priority: MessagePriority = MessagePriority.NORMAL
    ttl: Optional[int] = None  # Time to live in seconds
    requires_ack: bool = False
    requires_response: bool = False
    
    # Routing and correlation
    correlation_id: Optional[str] = None
    reply_to: Optional[str] = None
    conversation_id: Optional[str] = None
    
    # Security and validation
    signature: Optional[str] = None
    encrypted: bool = False
    
    # Metadata
    headers: Dict[str, str] = field(default_factory=dict)
    trace_id: Optional[str] = None
    span_id: Optional[str] = None


@dataclass
class TaskAssignmentProtocol:
    """Protocol for task assignment messages"""
    
    task_id: str
    task_type: str
    priority: int
    deadline: Optional[datetime]
    requirements: List[str]
    constraints: Dict[str, Any]
    resources: Dict[str, Any]
    dependencies: List[str]
    
    def to_payload(self) -> Dict[str, Any]:
        """Convert to message payload"""
        return {
            'task_id': self.task_id,
            'task_type': self.task_type,
            'priority': self.priority,
            'deadline': self.deadline.isoformat() if self.deadline else None,
            'requirements': self.requirements,
            'constraints': self.constraints,
            'resources': self.resources,
            'dependencies': self.dependencies
        }


@dataclass
class CapabilityQueryProtocol:
    """Protocol for capability queries"""
    
    query_type: str  # 'specific', 'general', 'availability'
    required_capabilities: List[str]
    preferred_capabilities: List[str]
    task_context: Optional[Dict[str, Any]]
    
    def to_payload(self) -> Dict[str, Any]:
        """Convert to message payload"""
        return {
            'query_type': self.query_type,
            'required_capabilities': self.required_capabilities,
            'preferred_capabilities': self.preferred_capabilities,
            'task_context': self.task_context
        }


@dataclass
class CollaborationProtocol:
    """Protocol for inter-agent collaboration"""
    
    collaboration_type: str  # 'code_review', 'pair_programming', 'consultation'
    initiator_id: str
    participants: List[str]
    task_id: str
    shared_context: Dict[str, Any]
    coordination_plan: Dict[str, Any]
    
    def to_payload(self) -> Dict[str, Any]:
        """Convert to message payload"""
        return {
            'collaboration_type': self.collaboration_type,
            'initiator_id': self.initiator_id,
            'participants': self.participants,
            'task_id': self.task_id,
            'shared_context': self.shared_context,
            'coordination_plan': self.coordination_plan
        }


@dataclass
class ClarificationProtocol:
    """Protocol for clarification requests"""
    
    task_id: str
    question_type: str  # 'requirement', 'constraint', 'context', 'technical'
    question: str
    context: Dict[str, Any]
    suggested_options: Optional[List[str]]
    urgency: MessagePriority
    
    def to_payload(self) -> Dict[str, Any]:
        """Convert to message payload"""
        return {
            'task_id': self.task_id,
            'question_type': self.question_type,
            'question': self.question,
            'context': self.context,
            'suggested_options': self.suggested_options,
            'urgency': self.urgency.value
        }


class ProtocolHandler:
    """Handler for A2A protocol messages"""
    
    def __init__(self, agent_id: str, version: str = "1.0"):
        self.agent_id = agent_id
        self.protocol_version = version
        self.handlers = {}
        self._register_handlers()
    
    def _register_handlers(self):
        """Register protocol message handlers"""
        self.handlers = {
            RequestType.TASK_ASSIGNMENT: self._handle_task_assignment,
            RequestType.CAPABILITY_QUERY: self._handle_capability_query,
            RequestType.STATUS_REQUEST: self._handle_status_request,
            RequestType.CLARIFICATION_REQUEST: self._handle_clarification,
            RequestType.COLLABORATION_REQUEST: self._handle_collaboration,
            RequestType.RESULT_NOTIFICATION: self._handle_result,
            RequestType.ERROR_REPORT: self._handle_error
        }
    
    async def handle_protocol_message(self, message: ProtocolMessage) -> Optional[ProtocolMessage]:
        """Handle incoming protocol message"""
        request_type = RequestType(message.message_type)
        
        if request_type in self.handlers:
            handler = self.handlers[request_type]
            return await handler(message)
        
        return None
    
    async def _handle_task_assignment(self, message: ProtocolMessage) -> Optional[ProtocolMessage]:
        """Handle task assignment message"""
        # Extract task details from payload
        task_data = message.payload
        
        # Create acknowledgment
        ack_payload = {
            'task_id': task_data['task_id'],
            'status': 'accepted',
            'estimated_completion': None,
            'agent_id': self.agent_id
        }
        
        return self._create_response(message, 'task_acknowledgment', ack_payload)
    
    async def _handle_capability_query(self, message: ProtocolMessage) -> Optional[ProtocolMessage]:
        """Handle capability query"""
        query_data = message.payload
        
        # Prepare capability response
        response_payload = {
            'agent_id': self.agent_id,
            'capabilities': [
                'python_implementation',
                'refactoring',
                'test_generation',
                'code_analysis'
            ],
            'availability': True,
            'current_load': 0,
            'max_capacity': 3
        }
        
        return self._create_response(message, 'capability_response', response_payload)
    
    async def _handle_status_request(self, message: ProtocolMessage) -> Optional[ProtocolMessage]:
        """Handle status request"""
        status_payload = {
            'agent_id': self.agent_id,
            'status': 'active',
            'current_tasks': [],
            'completed_tasks': 0,
            'failed_tasks': 0,
            'uptime': 0
        }
        
        return self._create_response(message, 'status_response', status_payload)
    
    async def _handle_clarification(self, message: ProtocolMessage) -> Optional[ProtocolMessage]:
        """Handle clarification request"""
        # This would typically involve asking the user or consulting documentation
        clarification_data = message.payload
        
        response_payload = {
            'task_id': clarification_data['task_id'],
            'question_id': message.message_id,
            'answer': None,
            'confidence': 0.0,
            'sources': []
        }
        
        return self._create_response(message, 'clarification_response', response_payload)
    
    async def _handle_collaboration(self, message: ProtocolMessage) -> Optional[ProtocolMessage]:
        """Handle collaboration request"""
        collab_data = message.payload
        
        response_payload = {
            'collaboration_id': message.message_id,
            'participant_id': self.agent_id,
            'acceptance': True,
            'availability': 'immediate',
            'constraints': {}
        }
        
        return self._create_response(message, 'collaboration_response', response_payload)
    
    async def _handle_result(self, message: ProtocolMessage) -> Optional[ProtocolMessage]:
        """Handle result notification"""
        # Acknowledge receipt of results
        ack_payload = {
            'result_id': message.message_id,
            'received': True,
            'agent_id': self.agent_id
        }
        
        return self._create_response(message, 'result_acknowledgment', ack_payload)
    
    async def _handle_error(self, message: ProtocolMessage) -> Optional[ProtocolMessage]:
        """Handle error report"""
        # Log error and acknowledge
        error_data = message.payload
        
        ack_payload = {
            'error_id': message.message_id,
            'acknowledged': True,
            'action': 'logged',
            'agent_id': self.agent_id
        }
        
        return self._create_response(message, 'error_acknowledgment', ack_payload)
    
    def _create_response(self, original: ProtocolMessage, response_type: str, 
                        payload: Dict[str, Any]) -> ProtocolMessage:
        """Create a response message"""
        return ProtocolMessage(
            message_id=f"{self.agent_id}_{datetime.utcnow().timestamp()}",
            sender_id=self.agent_id,
            recipient_id=original.sender_id,
            message_type=response_type,
            payload=payload,
            timestamp=datetime.utcnow(),
            protocol_version=self.protocol_version,
            priority=original.priority,
            correlation_id=original.message_id,
            reply_to=original.message_id,
            conversation_id=original.conversation_id
        )
    
    def create_task_assignment(self, recipient_id: str, task_data: TaskAssignmentProtocol,
                              priority: MessagePriority = MessagePriority.NORMAL) -> ProtocolMessage:
        """Create a task assignment message"""
        return ProtocolMessage(
            message_id=f"{self.agent_id}_{datetime.utcnow().timestamp()}",
            sender_id=self.agent_id,
            recipient_id=recipient_id,
            message_type=RequestType.TASK_ASSIGNMENT.value,
            payload=task_data.to_payload(),
            timestamp=datetime.utcnow(),
            protocol_version=self.protocol_version,
            priority=priority,
            requires_ack=True,
            requires_response=True
        )
    
    def create_capability_query(self, recipient_id: str, query_data: CapabilityQueryProtocol) -> ProtocolMessage:
        """Create a capability query message"""
        return ProtocolMessage(
            message_id=f"{self.agent_id}_{datetime.utcnow().timestamp()}",
            sender_id=self.agent_id,
            recipient_id=recipient_id,
            message_type=RequestType.CAPABILITY_QUERY.value,
            payload=query_data.to_payload(),
            timestamp=datetime.utcnow(),
            protocol_version=self.protocol_version,
            requires_response=True
        )
    
    def create_collaboration_request(self, recipient_id: str, collab_data: CollaborationProtocol,
                                    priority: MessagePriority = MessagePriority.HIGH) -> ProtocolMessage:
        """Create a collaboration request message"""
        return ProtocolMessage(
            message_id=f"{self.agent_id}_{datetime.utcnow().timestamp()}",
            sender_id=self.agent_id,
            recipient_id=recipient_id,
            message_type=RequestType.COLLABORATION_REQUEST.value,
            payload=collab_data.to_payload(),
            timestamp=datetime.utcnow(),
            protocol_version=self.protocol_version,
            priority=priority,
            requires_response=True
        )
    
    def create_clarification_request(self, recipient_id: str, clarification_data: ClarificationProtocol) -> ProtocolMessage:
        """Create a clarification request message"""
        return ProtocolMessage(
            message_id=f"{self.agent_id}_{datetime.utcnow().timestamp()}",
            sender_id=self.agent_id,
            recipient_id=recipient_id,
            message_type=RequestType.CLARIFICATION_REQUEST.value,
            payload=clarification_data.to_payload(),
            timestamp=datetime.utcnow(),
            protocol_version=self.protocol_version,
            priority=clarification_data.urgency,
            requires_response=True
        )