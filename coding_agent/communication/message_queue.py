"""Message queue implementations for A2A communication"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Callable
from datetime import datetime

import pika
import pika.channel
import pika.spec
import aio_pika
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
import redis.asyncio as redis
from tenacity import retry, stop_after_attempt, wait_exponential

from ..core.base import AgentMessage, MessageHandler
from ..core.config import MessageQueueConfig


class BaseMessageQueue(MessageHandler, ABC):
    """Base class for message queue implementations"""
    
    def __init__(self, config: MessageQueueConfig, agent_id: str):
        self.config = config
        self.agent_id = agent_id
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.connected = False
        self.message_callback: Optional[Callable] = None
    
    @abstractmethod
    async def connect(self) -> bool:
        """Connect to the message queue"""
        pass
    
    @abstractmethod
    async def disconnect(self) -> bool:
        """Disconnect from the message queue"""
        pass
    
    @abstractmethod
    async def send_message(self, message: AgentMessage) -> bool:
        """Send a message to the queue"""
        pass
    
    @abstractmethod
    async def receive_message(self) -> Optional[AgentMessage]:
        """Receive a message from the queue"""
        pass
    
    async def send_progress(self, task_id: str, progress: float, message: str) -> bool:
        """Send progress update"""
        progress_message = AgentMessage(
            sender_id=self.agent_id,
            recipient_id='orchestrator',
            message_type='progress',
            payload={
                'task_id': task_id,
                'progress': progress,
                'message': message,
                'timestamp': datetime.utcnow().isoformat()
            }
        )
        return await self.send_message(progress_message)
    
    def set_message_callback(self, callback: Callable):
        """Set callback for incoming messages"""
        self.message_callback = callback
    
    def _serialize_message(self, message: AgentMessage) -> bytes:
        """Serialize message to bytes"""
        return json.dumps(message.to_dict()).encode('utf-8')
    
    def _deserialize_message(self, data: bytes) -> AgentMessage:
        """Deserialize message from bytes"""
        message_dict = json.loads(data.decode('utf-8'))
        return AgentMessage.from_dict(message_dict)


class RabbitMQHandler(BaseMessageQueue):
    """RabbitMQ implementation for message queue"""
    
    def __init__(self, config: MessageQueueConfig, agent_id: str):
        super().__init__(config, agent_id)
        self.connection: Optional[aio_pika.Connection] = None
        self.channel: Optional[aio_pika.Channel] = None
        self.exchange: Optional[aio_pika.Exchange] = None
        self.queue: Optional[aio_pika.Queue] = None
        self.consumer_tag: Optional[str] = None
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def connect(self) -> bool:
        """Connect to RabbitMQ"""
        try:
            # Build connection URL
            if self.config.username and self.config.password:
                url = f"amqp://{self.config.username}:{self.config.password}@{self.config.host}:{self.config.port}/"
            else:
                url = f"amqp://{self.config.host}:{self.config.port}/"
            
            # Create connection
            self.connection = await aio_pika.connect_robust(
                url,
                connection_attempts=self.config.retry_attempts,
                retry_delay=self.config.retry_delay
            )
            
            # Create channel
            self.channel = await self.connection.channel()
            await self.channel.set_qos(prefetch_count=1)
            
            # Declare exchange
            self.exchange = await self.channel.declare_exchange(
                self.config.exchange,
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )
            
            # Declare queue for this agent
            queue_name = f"{self.config.queue_name}.{self.agent_id}"
            self.queue = await self.channel.declare_queue(
                queue_name,
                durable=True,
                auto_delete=False
            )
            
            # Bind queue to exchange with routing keys
            await self.queue.bind(self.exchange, routing_key=f"agent.{self.agent_id}")
            await self.queue.bind(self.exchange, routing_key="agent.all")
            await self.queue.bind(self.exchange, routing_key="coding.#")
            
            self.connected = True
            self.logger.info(f"Connected to RabbitMQ at {self.config.host}:{self.config.port}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to connect to RabbitMQ: {e}")
            self.connected = False
            raise
    
    async def disconnect(self) -> bool:
        """Disconnect from RabbitMQ"""
        try:
            if self.connection and not self.connection.is_closed:
                await self.connection.close()
            
            self.connected = False
            self.logger.info("Disconnected from RabbitMQ")
            return True
            
        except Exception as e:
            self.logger.error(f"Error disconnecting from RabbitMQ: {e}")
            return False
    
    async def send_message(self, message: AgentMessage) -> bool:
        """Send message to RabbitMQ"""
        if not self.connected:
            await self.connect()
        
        try:
            # Determine routing key
            if message.recipient_id == 'orchestrator':
                routing_key = 'orchestrator.messages'
            elif message.recipient_id == 'all':
                routing_key = 'agent.all'
            else:
                routing_key = f"agent.{message.recipient_id}"
            
            # Publish message
            await self.exchange.publish(
                aio_pika.Message(
                    body=self._serialize_message(message),
                    content_type='application/json',
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    headers={
                        'sender_id': self.agent_id,
                        'message_type': message.message_type,
                        'timestamp': message.timestamp.isoformat()
                    }
                ),
                routing_key=routing_key
            )
            
            self.logger.debug(f"Sent message to {routing_key}: {message.message_type}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send message: {e}")
            return False
    
    async def receive_message(self) -> Optional[AgentMessage]:
        """Receive message from RabbitMQ"""
        if not self.connected:
            await self.connect()
        
        try:
            # Get message from queue (non-blocking)
            incoming = await self.queue.get(timeout=1)
            
            if incoming:
                async with incoming.process():
                    message = self._deserialize_message(incoming.body)
                    self.logger.debug(f"Received message: {message.message_type} from {message.sender_id}")
                    
                    if self.message_callback:
                        await self.message_callback(message)
                    
                    return message
            
            return None
            
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            self.logger.error(f"Error receiving message: {e}")
            return None


class KafkaHandler(BaseMessageQueue):
    """Apache Kafka implementation for message queue"""
    
    def __init__(self, config: MessageQueueConfig, agent_id: str):
        super().__init__(config, agent_id)
        self.producer: Optional[AIOKafkaProducer] = None
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.topics = [
            f"agent-{agent_id}",
            "agent-all",
            "coding-tasks"
        ]
    
    async def connect(self) -> bool:
        """Connect to Kafka"""
        try:
            bootstrap_servers = f"{self.config.host}:{self.config.port}"
            
            # Create producer
            self.producer = AIOKafkaProducer(
                bootstrap_servers=bootstrap_servers,
                value_serializer=lambda v: self._serialize_message(v),
                compression_type='gzip',
                acks='all',
                retry_backoff_ms=100,
                request_timeout_ms=self.config.connection_timeout * 1000
            )
            await self.producer.start()
            
            # Create consumer
            self.consumer = AIOKafkaConsumer(
                *self.topics,
                bootstrap_servers=bootstrap_servers,
                group_id=f"coding-agent-{self.agent_id}",
                value_deserializer=lambda v: self._deserialize_message(v),
                auto_offset_reset='latest',
                enable_auto_commit=True,
                max_poll_records=10,
                consumer_timeout_ms=1000
            )
            await self.consumer.start()
            
            self.connected = True
            self.logger.info(f"Connected to Kafka at {bootstrap_servers}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to connect to Kafka: {e}")
            self.connected = False
            return False
    
    async def disconnect(self) -> bool:
        """Disconnect from Kafka"""
        try:
            if self.producer:
                await self.producer.stop()
            if self.consumer:
                await self.consumer.stop()
            
            self.connected = False
            self.logger.info("Disconnected from Kafka")
            return True
            
        except Exception as e:
            self.logger.error(f"Error disconnecting from Kafka: {e}")
            return False
    
    async def send_message(self, message: AgentMessage) -> bool:
        """Send message to Kafka"""
        if not self.connected:
            await self.connect()
        
        try:
            # Determine topic
            if message.recipient_id == 'orchestrator':
                topic = 'orchestrator-messages'
            elif message.recipient_id == 'all':
                topic = 'agent-all'
            else:
                topic = f"agent-{message.recipient_id}"
            
            # Send message
            await self.producer.send(
                topic,
                value=message,
                headers=[
                    ('sender_id', self.agent_id.encode()),
                    ('message_type', message.message_type.encode())
                ]
            )
            
            self.logger.debug(f"Sent message to {topic}: {message.message_type}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send message: {e}")
            return False
    
    async def receive_message(self) -> Optional[AgentMessage]:
        """Receive message from Kafka"""
        if not self.connected:
            await self.connect()
        
        try:
            # Poll for messages
            records = await self.consumer.getmany(timeout_ms=1000, max_records=1)
            
            for topic_partition, messages in records.items():
                for msg in messages:
                    message = msg.value  # Already deserialized
                    self.logger.debug(f"Received message: {message.message_type} from {message.sender_id}")
                    
                    if self.message_callback:
                        await self.message_callback(message)
                    
                    return message
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error receiving message: {e}")
            return None


class RedisHandler(BaseMessageQueue):
    """Redis Pub/Sub implementation for message queue"""
    
    def __init__(self, config: MessageQueueConfig, agent_id: str):
        super().__init__(config, agent_id)
        self.redis_client: Optional[redis.Redis] = None
        self.pubsub: Optional[redis.client.PubSub] = None
        self.channels = [
            f"agent:{agent_id}",
            "agent:all",
            "coding:tasks"
        ]
    
    async def connect(self) -> bool:
        """Connect to Redis"""
        try:
            # Create Redis connection
            self.redis_client = redis.Redis(
                host=self.config.host,
                port=self.config.port,
                password=self.config.password if self.config.password != 'guest' else None,
                decode_responses=False,
                socket_connect_timeout=self.config.connection_timeout,
                retry_on_timeout=True
            )
            
            # Test connection
            await self.redis_client.ping()
            
            # Setup pub/sub
            self.pubsub = self.redis_client.pubsub()
            for channel in self.channels:
                await self.pubsub.subscribe(channel)
            
            self.connected = True
            self.logger.info(f"Connected to Redis at {self.config.host}:{self.config.port}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to connect to Redis: {e}")
            self.connected = False
            return False
    
    async def disconnect(self) -> bool:
        """Disconnect from Redis"""
        try:
            if self.pubsub:
                await self.pubsub.unsubscribe()
                await self.pubsub.close()
            
            if self.redis_client:
                await self.redis_client.close()
            
            self.connected = False
            self.logger.info("Disconnected from Redis")
            return True
            
        except Exception as e:
            self.logger.error(f"Error disconnecting from Redis: {e}")
            return False
    
    async def send_message(self, message: AgentMessage) -> bool:
        """Send message to Redis"""
        if not self.connected:
            await self.connect()
        
        try:
            # Determine channel
            if message.recipient_id == 'orchestrator':
                channel = 'orchestrator:messages'
            elif message.recipient_id == 'all':
                channel = 'agent:all'
            else:
                channel = f"agent:{message.recipient_id}"
            
            # Publish message
            await self.redis_client.publish(
                channel,
                self._serialize_message(message)
            )
            
            # Also store in a list for persistence (last 1000 messages)
            list_key = f"messages:{self.agent_id}:sent"
            await self.redis_client.lpush(list_key, self._serialize_message(message))
            await self.redis_client.ltrim(list_key, 0, 999)
            
            self.logger.debug(f"Sent message to {channel}: {message.message_type}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send message: {e}")
            return False
    
    async def receive_message(self) -> Optional[AgentMessage]:
        """Receive message from Redis"""
        if not self.connected:
            await self.connect()
        
        try:
            # Get message from pub/sub (with timeout)
            message_data = await asyncio.wait_for(
                self.pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1),
                timeout=1.0
            )
            
            if message_data and message_data['type'] == 'message':
                message = self._deserialize_message(message_data['data'])
                self.logger.debug(f"Received message: {message.message_type} from {message.sender_id}")
                
                # Store in received list
                list_key = f"messages:{self.agent_id}:received"
                await self.redis_client.lpush(list_key, message_data['data'])
                await self.redis_client.ltrim(list_key, 0, 999)
                
                if self.message_callback:
                    await self.message_callback(message)
                
                return message
            
            return None
            
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            self.logger.error(f"Error receiving message: {e}")
            return None


class MessageQueueFactory:
    """Factory for creating message queue handlers"""
    
    @staticmethod
    def create(config: MessageQueueConfig, agent_id: str) -> BaseMessageQueue:
        """Create appropriate message queue handler based on configuration"""
        
        handlers = {
            'rabbitmq': RabbitMQHandler,
            'kafka': KafkaHandler,
            'redis': RedisHandler
        }
        
        handler_class = handlers.get(config.broker_type.lower())
        
        if not handler_class:
            raise ValueError(f"Unknown broker type: {config.broker_type}")
        
        return handler_class(config, agent_id)