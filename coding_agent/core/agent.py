"""Main coding agent implementation"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import signal
import sys

from .base import (
    TaskSpecification, TaskResult, TaskStatus, TaskType,
    AgentMessage, TaskExecutor, MessageHandler
)
from .config import AgentConfig
from ..integrations.mcp_integration import MCPIntegration


class CodingAgent:
    """Main autonomous coding agent"""
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.agent_id = config.agent_id
        self.logger = self._setup_logging()
        
        self.message_handler: Optional[MessageHandler] = None
        self.task_executors: Dict[TaskType, TaskExecutor] = {}
        self.mcp_integration: Optional[MCPIntegration] = None
        
        self.current_tasks: Dict[str, TaskSpecification] = {}
        self.task_results: Dict[str, TaskResult] = {}
        
        self.running = False
        self.shutdown_event = asyncio.Event()
        self.task_semaphore = asyncio.Semaphore(config.max_concurrent_tasks)
        
        self._setup_signal_handlers()
    
    def _setup_logging(self) -> logging.Logger:
        """Setup logging configuration"""
        logger = logging.getLogger(self.config.agent_name)
        logger.setLevel(getattr(logging, self.config.logging.level))
        
        formatter = logging.Formatter(self.config.logging.format)
        
        if self.config.logging.console_output:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
        
        if self.config.logging.file_path:
            from logging.handlers import RotatingFileHandler
            file_handler = RotatingFileHandler(
                self.config.logging.file_path,
                maxBytes=self.config.logging.max_file_size_mb * 1024 * 1024,
                backupCount=self.config.logging.backup_count
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        
        return logger
    
    def _setup_signal_handlers(self):
        """Setup graceful shutdown handlers"""
        def signal_handler(signum, frame):
            self.logger.info(f"Received signal {signum}, initiating shutdown...")
            self.shutdown_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def register_message_handler(self, handler: MessageHandler):
        """Register a message handler for A2A communication"""
        self.message_handler = handler
        self.logger.info(f"Registered message handler: {type(handler).__name__}")
    
    def register_task_executor(self, task_type: TaskType, executor: TaskExecutor):
        """Register a task executor for a specific task type"""
        self.task_executors[task_type] = executor
        self.logger.info(f"Registered executor for {task_type.value}: {type(executor).__name__}")
    
    async def initialize_mcp(self):
        """Initialize MCP integration"""
        if self.config.mcp.api_key:
            self.logger.info("Initializing MCP integration")
            self.mcp_integration = MCPIntegration(self.config.mcp)
            await self.mcp_integration.initialize()
            
            # Validate environment
            validations = await self.mcp_integration.validate_environment()
            self.logger.info(f"MCP environment validation: {validations}")
            
            if not all(validations.values()):
                self.logger.warning("Some MCP environment checks failed")
        else:
            self.logger.warning("MCP API key not configured, MCP integration disabled")
    
    async def start(self):
        """Start the agent and begin processing tasks"""
        self.logger.info(f"Starting {self.config.agent_name} (ID: {self.agent_id})")
        self.running = True
        
        if not self.message_handler:
            self.logger.error("No message handler registered!")
            return
        
        # Initialize MCP if configured
        try:
            await self.initialize_mcp()
        except Exception as e:
            self.logger.error(f"Failed to initialize MCP: {e}")
            # Continue without MCP if initialization fails
        
        tasks = [
            asyncio.create_task(self._message_loop()),
            asyncio.create_task(self._heartbeat_loop()),
            asyncio.create_task(self._monitor_tasks())
        ]
        
        await self._send_registration_message()
        
        try:
            await self.shutdown_event.wait()
        finally:
            self.running = False
            await self._cleanup(tasks)
    
    async def _message_loop(self):
        """Main message processing loop"""
        self.logger.info("Starting message processing loop")
        
        while self.running:
            try:
                message = await self.message_handler.receive_message()
                if message:
                    await self._handle_message(message)
                else:
                    await asyncio.sleep(0.1)
            except Exception as e:
                self.logger.error(f"Error in message loop: {e}", exc_info=True)
                await asyncio.sleep(1)
    
    async def _handle_message(self, message: AgentMessage):
        """Handle incoming messages"""
        self.logger.debug(f"Received message: {message.message_type} from {message.sender_id}")
        
        try:
            if message.message_type == "task":
                await self._handle_task_message(message)
            elif message.message_type == "query":
                await self._handle_query_message(message)
            elif message.message_type == "cancel":
                await self._handle_cancel_message(message)
            elif message.message_type == "status_request":
                await self._handle_status_request(message)
            else:
                self.logger.warning(f"Unknown message type: {message.message_type}")
        except Exception as e:
            self.logger.error(f"Error handling message: {e}", exc_info=True)
            await self._send_error_response(message, str(e))
    
    async def _handle_task_message(self, message: AgentMessage):
        """Handle incoming task assignment"""
        try:
            task_spec = TaskSpecification.from_dict(message.payload)
            
            if task_spec.type not in self.task_executors:
                raise ValueError(f"No executor for task type: {task_spec.type.value}")
            
            executor = self.task_executors[task_spec.type]
            
            if not await executor.validate(task_spec):
                raise ValueError("Task validation failed")
            
            self.current_tasks[task_spec.task_id] = task_spec
            
            await self._send_acknowledgment(message, task_spec.task_id)
            
            asyncio.create_task(self._execute_task(task_spec, executor))
            
        except Exception as e:
            self.logger.error(f"Failed to handle task: {e}")
            await self._send_error_response(message, str(e))
    
    async def _execute_task(self, task: TaskSpecification, executor: TaskExecutor):
        """Execute a task with proper resource management"""
        async with self.task_semaphore:
            start_time = datetime.utcnow()
            self.logger.info(f"Starting execution of task {task.task_id}: {task.title}")
            
            try:
                await self._send_progress(task.task_id, 0, "Task execution started")
                
                result = await asyncio.wait_for(
                    executor.execute(task),
                    timeout=self.config.task_timeout
                )
                
                result.execution_time = (datetime.utcnow() - start_time).total_seconds()
                self.task_results[task.task_id] = result
                
                await self._send_task_result(task.task_id, result)
                
                self.logger.info(f"Completed task {task.task_id} in {result.execution_time:.2f}s")
                
            except asyncio.TimeoutError:
                self.logger.error(f"Task {task.task_id} timed out after {self.config.task_timeout}s")
                result = TaskResult(
                    task_id=task.task_id,
                    status=TaskStatus.FAILED,
                    result_type="error",
                    error_message=f"Task timed out after {self.config.task_timeout} seconds",
                    execution_time=(datetime.utcnow() - start_time).total_seconds()
                )
                await self._send_task_result(task.task_id, result)
                
            except Exception as e:
                self.logger.error(f"Task {task.task_id} failed: {e}", exc_info=True)
                result = TaskResult(
                    task_id=task.task_id,
                    status=TaskStatus.FAILED,
                    result_type="error",
                    error_message=str(e),
                    execution_time=(datetime.utcnow() - start_time).total_seconds()
                )
                await self._send_task_result(task.task_id, result)
                
            finally:
                if task.task_id in self.current_tasks:
                    del self.current_tasks[task.task_id]
    
    async def _handle_query_message(self, message: AgentMessage):
        """Handle query for clarification or additional context"""
        query_type = message.payload.get('query_type')
        task_id = message.payload.get('task_id')
        
        response_payload = {
            'query_type': query_type,
            'task_id': task_id,
            'response': None,
            'status': 'success'
        }
        
        if query_type == 'capabilities':
            response_payload['response'] = {
                'supported_task_types': [t.value for t in self.task_executors.keys()],
                'max_concurrent_tasks': self.config.max_concurrent_tasks,
                'current_load': len(self.current_tasks)
            }
        elif query_type == 'task_status' and task_id:
            if task_id in self.current_tasks:
                response_payload['response'] = {'status': 'in_progress'}
            elif task_id in self.task_results:
                response_payload['response'] = {'status': self.task_results[task_id].status.value}
            else:
                response_payload['response'] = {'status': 'unknown'}
        
        response = AgentMessage(
            sender_id=self.agent_id,
            recipient_id=message.sender_id,
            message_type='response',
            payload=response_payload,
            correlation_id=message.message_id
        )
        
        await self.message_handler.send_message(response)
    
    async def _handle_cancel_message(self, message: AgentMessage):
        """Handle task cancellation request"""
        task_id = message.payload.get('task_id')
        
        if task_id in self.current_tasks:
            self.logger.info(f"Cancellation requested for task {task_id}")
            # Implementation would depend on executor support for cancellation
            response_payload = {'task_id': task_id, 'cancelled': True}
        else:
            response_payload = {'task_id': task_id, 'cancelled': False, 'reason': 'Task not found'}
        
        response = AgentMessage(
            sender_id=self.agent_id,
            recipient_id=message.sender_id,
            message_type='response',
            payload=response_payload,
            correlation_id=message.message_id
        )
        
        await self.message_handler.send_message(response)
    
    async def _handle_status_request(self, message: AgentMessage):
        """Handle status request"""
        status = {
            'agent_id': self.agent_id,
            'status': 'active' if self.running else 'inactive',
            'current_tasks': len(self.current_tasks),
            'completed_tasks': len(self.task_results),
            'available_capacity': self.config.max_concurrent_tasks - len(self.current_tasks),
            'uptime': (datetime.utcnow() - self.startup_time).total_seconds() if hasattr(self, 'startup_time') else 0
        }
        
        response = AgentMessage(
            sender_id=self.agent_id,
            recipient_id=message.sender_id,
            message_type='status_response',
            payload=status,
            correlation_id=message.message_id
        )
        
        await self.message_handler.send_message(response)
    
    async def _heartbeat_loop(self):
        """Send periodic heartbeat messages"""
        self.startup_time = datetime.utcnow()
        
        while self.running:
            try:
                heartbeat = AgentMessage(
                    sender_id=self.agent_id,
                    recipient_id='orchestrator',
                    message_type='heartbeat',
                    payload={
                        'agent_id': self.agent_id,
                        'timestamp': datetime.utcnow().isoformat(),
                        'current_tasks': len(self.current_tasks),
                        'available_capacity': self.config.max_concurrent_tasks - len(self.current_tasks)
                    }
                )
                
                await self.message_handler.send_message(heartbeat)
                await asyncio.sleep(self.config.heartbeat_interval)
                
            except Exception as e:
                self.logger.error(f"Error sending heartbeat: {e}")
                await asyncio.sleep(self.config.heartbeat_interval)
    
    async def _monitor_tasks(self):
        """Monitor task execution and handle timeouts"""
        while self.running:
            try:
                current_time = datetime.utcnow()
                
                for task_id, task in list(self.current_tasks.items()):
                    if task.deadline and current_time > task.deadline:
                        self.logger.warning(f"Task {task_id} has exceeded its deadline")
                        # Could implement deadline handling here
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                self.logger.error(f"Error in task monitor: {e}")
                await asyncio.sleep(30)
    
    async def _send_registration_message(self):
        """Send initial registration message to orchestrator"""
        registration = AgentMessage(
            sender_id=self.agent_id,
            recipient_id='orchestrator',
            message_type='registration',
            payload={
                'agent_id': self.agent_id,
                'agent_type': 'coding_agent',
                'capabilities': [t.value for t in self.task_executors.keys()],
                'max_concurrent_tasks': self.config.max_concurrent_tasks,
                'version': self.config.version
            }
        )
        
        await self.message_handler.send_message(registration)
        self.logger.info("Sent registration message to orchestrator")
    
    async def _send_acknowledgment(self, original_message: AgentMessage, task_id: str):
        """Send task acknowledgment"""
        ack = AgentMessage(
            sender_id=self.agent_id,
            recipient_id=original_message.sender_id,
            message_type='acknowledgment',
            payload={'task_id': task_id, 'status': 'accepted'},
            correlation_id=original_message.message_id
        )
        
        await self.message_handler.send_message(ack)
    
    async def _send_error_response(self, original_message: AgentMessage, error: str):
        """Send error response"""
        error_response = AgentMessage(
            sender_id=self.agent_id,
            recipient_id=original_message.sender_id,
            message_type='error',
            payload={'error': error},
            correlation_id=original_message.message_id
        )
        
        await self.message_handler.send_message(error_response)
    
    async def _send_progress(self, task_id: str, progress: float, message: str):
        """Send task progress update"""
        if self.message_handler:
            await self.message_handler.send_progress(task_id, progress, message)
    
    async def _send_task_result(self, task_id: str, result: TaskResult):
        """Send task completion result"""
        result_message = AgentMessage(
            sender_id=self.agent_id,
            recipient_id='orchestrator',
            message_type='task_result',
            payload={
                'task_id': task_id,
                'status': result.status.value,
                'result_type': result.result_type,
                'files_modified': result.files_modified,
                'files_created': result.files_created,
                'tests_added': result.tests_added,
                'pull_request_url': result.pull_request_url,
                'error_message': result.error_message,
                'execution_time': result.execution_time,
                'metrics': result.metrics
            }
        )
        
        await self.message_handler.send_message(result_message)
    
    async def _cleanup(self, tasks: List[asyncio.Task]):
        """Cleanup resources on shutdown"""
        self.logger.info("Shutting down agent...")
        
        deregistration = AgentMessage(
            sender_id=self.agent_id,
            recipient_id='orchestrator',
            message_type='deregistration',
            payload={'agent_id': self.agent_id}
        )
        
        try:
            await self.message_handler.send_message(deregistration)
        except Exception as e:
            self.logger.error(f"Failed to send deregistration: {e}")
        
        # Cleanup MCP integration
        if self.mcp_integration:
            try:
                await self.mcp_integration.close()
                self.logger.info("MCP integration closed")
            except Exception as e:
                self.logger.error(f"Failed to close MCP integration: {e}")
        
        for task in tasks:
            task.cancel()
        
        await asyncio.gather(*tasks, return_exceptions=True)
        
        self.logger.info("Agent shutdown complete")