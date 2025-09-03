"""
Quick start example for orchestrator integration with Coding Agent

This example demonstrates how to implement basic orchestrator functionality
to communicate with the Coding Agent via message queue.
"""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
import aio_pika


class SimpleOrchestrator:
    """Minimal orchestrator implementation for Coding Agent integration"""
    
    def __init__(self, rabbitmq_url: str = "amqp://guest:guest@localhost/"):
        self.url = rabbitmq_url
        self.connection = None
        self.channel = None
        self.exchange = None
        self.queue = None
        self.agent_registry = {}  # Track registered agents
        self.task_assignments = {}  # Track task assignments
        
    async def connect(self):
        """Connect to RabbitMQ"""
        self.connection = await aio_pika.connect_robust(self.url)
        self.channel = await self.connection.channel()
        
        # Declare exchange
        self.exchange = await self.channel.declare_exchange(
            'agent_swarm',
            aio_pika.ExchangeType.TOPIC,
            durable=True
        )
        
        # Create orchestrator queue
        self.queue = await self.channel.declare_queue(
            'orchestrator_queue',
            durable=True
        )
        
        # Bind to receive messages
        await self.queue.bind(self.exchange, routing_key='orchestrator.messages')
        await self.queue.bind(self.exchange, routing_key='orchestrator.#')
        
        print("Orchestrator connected to message queue")
        
    async def send_message(self, recipient_id: str, message_type: str, payload: Dict[str, Any]):
        """Send a message to an agent"""
        message = {
            'message_id': str(uuid.uuid4()),
            'sender_id': 'orchestrator',
            'recipient_id': recipient_id,
            'message_type': message_type,
            'payload': payload,
            'timestamp': datetime.utcnow().isoformat(),
            'correlation_id': None,
            'reply_to': None
        }
        
        # Determine routing key
        if recipient_id == 'all':
            routing_key = 'agent.all'
        else:
            routing_key = f'agent.{recipient_id}'
        
        # Publish message
        await self.exchange.publish(
            aio_pika.Message(
                body=json.dumps(message).encode(),
                content_type='application/json',
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key=routing_key
        )
        
        print(f"Sent {message_type} to {recipient_id}")
        return message['message_id']
    
    async def assign_task(self, agent_id: str, task_type: str, title: str, description: str):
        """Assign a task to a coding agent"""
        task_spec = {
            'task_id': str(uuid.uuid4()),
            'type': task_type,
            'priority': 3,  # MEDIUM
            'title': title,
            'description': description,
            'requirements': [
                'Implement the requested functionality',
                'Follow Python best practices',
                'Include appropriate error handling'
            ],
            'acceptance_criteria': [
                'Code executes without errors',
                'All requirements are met',
                'Code is properly documented'
            ],
            'context': {
                'repository_url': 'https://github.com/example/repo',
                'branch': 'main',
                'base_branch': 'main',
                'relevant_files': [],
                'dependencies': [],
                'related_issues': [],
                'environment_vars': {},
                'constraints': {
                    'style_guide': 'PEP 8',
                    'python_version': '3.11+'
                },
                'metadata': {}
            },
            'deadline': None,
            'estimated_hours': 1.0,
            'assigned_to': agent_id,
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }
        
        # Track assignment
        self.task_assignments[task_spec['task_id']] = {
            'agent_id': agent_id,
            'task': task_spec,
            'status': 'assigned',
            'assigned_at': datetime.utcnow()
        }
        
        # Send task to agent
        message_id = await self.send_message(agent_id, 'task', task_spec)
        
        print(f"Assigned task {task_spec['task_id']} to {agent_id}")
        return task_spec['task_id']
    
    async def process_messages(self):
        """Process incoming messages from agents"""
        async with self.queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    try:
                        data = json.loads(message.body.decode())
                        await self.handle_message(data)
                    except Exception as e:
                        print(f"Error processing message: {e}")
    
    async def handle_message(self, message: Dict[str, Any]):
        """Handle incoming message from agent"""
        msg_type = message['message_type']
        sender_id = message['sender_id']
        payload = message['payload']
        
        print(f"Received {msg_type} from {sender_id}")
        
        if msg_type == 'registration':
            # Agent registration
            self.agent_registry[payload['agent_id']] = {
                'agent_type': payload['agent_type'],
                'capabilities': payload['capabilities'],
                'max_concurrent_tasks': payload['max_concurrent_tasks'],
                'version': payload['version'],
                'registered_at': datetime.utcnow()
            }
            print(f"Registered agent: {payload['agent_id']}")
            
        elif msg_type == 'acknowledgment':
            # Task acknowledgment
            task_id = payload['task_id']
            if task_id in self.task_assignments:
                self.task_assignments[task_id]['status'] = payload['status']
                print(f"Task {task_id} {payload['status']}")
            
        elif msg_type == 'progress':
            # Progress update
            task_id = payload['task_id']
            progress = payload['progress']
            message = payload['message']
            print(f"Task {task_id}: {progress*100:.0f}% - {message}")
            
        elif msg_type == 'task_result':
            # Task completion
            task_id = payload['task_id']
            status = payload['status']
            if task_id in self.task_assignments:
                self.task_assignments[task_id]['status'] = status
                self.task_assignments[task_id]['completed_at'] = datetime.utcnow()
                self.task_assignments[task_id]['result'] = payload
                
                print(f"Task {task_id} {status}")
                if status == 'completed':
                    print(f"  Files modified: {payload.get('files_modified', [])}")
                    print(f"  Files created: {payload.get('files_created', [])}")
                    print(f"  Tests added: {payload.get('tests_added', [])}")
                    print(f"  Execution time: {payload.get('execution_time', 0):.2f}s")
                elif status == 'failed':
                    print(f"  Error: {payload.get('error_message', 'Unknown error')}")
            
        elif msg_type == 'heartbeat':
            # Heartbeat
            agent_id = payload['agent_id']
            if agent_id in self.agent_registry:
                self.agent_registry[agent_id]['last_heartbeat'] = datetime.utcnow()
                self.agent_registry[agent_id]['current_load'] = payload['current_tasks']
                self.agent_registry[agent_id]['available_capacity'] = payload['available_capacity']
            
        elif msg_type == 'query' and payload.get('query_type') == 'clarification':
            # Clarification request
            task_id = payload['task_id']
            question = payload['question']
            options = payload.get('suggested_options', [])
            
            print(f"Clarification needed for task {task_id}:")
            print(f"  Question: {question}")
            if options:
                print(f"  Options: {options}")
            
            # Auto-respond with first option for demo
            if options:
                response_payload = {
                    'query_type': 'clarification',
                    'task_id': task_id,
                    'answer': options[0],
                    'additional_context': 'Automated response - chose first option'
                }
                await self.send_message(sender_id, 'response', response_payload)
    
    async def list_agents(self):
        """List all registered agents"""
        print("\nRegistered Agents:")
        for agent_id, info in self.agent_registry.items():
            print(f"  {agent_id}:")
            print(f"    Type: {info['agent_type']}")
            print(f"    Capabilities: {', '.join(info['capabilities'])}")
            print(f"    Capacity: {info.get('available_capacity', 'Unknown')}/{info['max_concurrent_tasks']}")
    
    async def list_tasks(self):
        """List all tasks"""
        print("\nTasks:")
        for task_id, assignment in self.task_assignments.items():
            task = assignment['task']
            print(f"  {task_id}:")
            print(f"    Title: {task['title']}")
            print(f"    Agent: {assignment['agent_id']}")
            print(f"    Status: {assignment['status']}")
    
    async def run_demo(self):
        """Run a demo workflow"""
        print("Starting Orchestrator Demo")
        print("=" * 50)
        
        await self.connect()
        
        # Start message processing in background
        asyncio.create_task(self.process_messages())
        
        # Wait for agents to register
        print("\nWaiting for coding agents to register...")
        await asyncio.sleep(5)
        
        await self.list_agents()
        
        if not self.agent_registry:
            print("No agents registered. Please start a coding agent.")
            return
        
        # Get first registered coding agent
        coding_agents = [
            agent_id for agent_id, info in self.agent_registry.items()
            if info['agent_type'] == 'coding_agent'
        ]
        
        if not coding_agents:
            print("No coding agents available.")
            return
        
        agent_id = coding_agents[0]
        print(f"\nUsing agent: {agent_id}")
        
        # Assign some example tasks
        tasks = [
            ('implementation', 'Create User Model', 'Implement a User model with email and password fields'),
            ('refactoring', 'Refactor Database Connection', 'Extract database connection logic into a separate module'),
            ('test_generation', 'Add API Tests', 'Generate tests for the REST API endpoints')
        ]
        
        print("\nAssigning tasks...")
        task_ids = []
        for task_type, title, description in tasks:
            task_id = await self.assign_task(agent_id, task_type, title, description)
            task_ids.append(task_id)
            await asyncio.sleep(1)
        
        # Monitor task progress
        print("\nMonitoring task progress...")
        completed = set()
        
        while len(completed) < len(task_ids):
            await asyncio.sleep(5)
            
            for task_id in task_ids:
                if task_id not in completed:
                    assignment = self.task_assignments.get(task_id)
                    if assignment and assignment['status'] in ['completed', 'failed']:
                        completed.add(task_id)
                        print(f"\nTask {task_id} finished with status: {assignment['status']}")
            
            # Show current status
            await self.list_tasks()
        
        print("\n" + "=" * 50)
        print("Demo completed!")
        
        # Final summary
        print("\nFinal Summary:")
        for task_id in task_ids:
            assignment = self.task_assignments[task_id]
            print(f"  {assignment['task']['title']}: {assignment['status']}")


async def main():
    """Main entry point"""
    orchestrator = SimpleOrchestrator()
    
    try:
        await orchestrator.run_demo()
    except KeyboardInterrupt:
        print("\nShutting down orchestrator...")
    finally:
        if orchestrator.connection:
            await orchestrator.connection.close()


if __name__ == "__main__":
    asyncio.run(main())