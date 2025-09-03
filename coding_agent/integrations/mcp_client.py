"""MCP (Model Context Protocol) client for Composio/Rube integration"""

import asyncio
import json
import logging
import base64
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from tenacity import retry, stop_after_attempt, wait_exponential
import aiohttp

from ..core.config import MCPConfig


@dataclass
class ToolSchema:
    """Schema definition for a Composio tool"""
    toolkit: str
    tool_slug: str
    description: str
    input_schema: Dict[str, Any]
    order: int = 0
    
    def validate_arguments(self, arguments: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate arguments against the input schema"""
        errors = []
        required_fields = self.input_schema.get('required', [])
        properties = self.input_schema.get('properties', {})
        
        # Check required fields
        for field in required_fields:
            if field not in arguments:
                errors.append(f"Missing required field: {field}")
        
        # Check field types
        for field, value in arguments.items():
            if field in properties:
                expected_type = properties[field].get('type')
                if expected_type:
                    if not self._check_type(value, expected_type):
                        errors.append(f"Field {field} has wrong type. Expected {expected_type}")
        
        return len(errors) == 0, errors
    
    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Check if value matches expected type"""
        type_map = {
            'string': str,
            'integer': int,
            'number': (int, float),
            'boolean': bool,
            'array': list,
            'object': dict
        }
        expected = type_map.get(expected_type)
        if expected:
            return isinstance(value, expected)
        return True


@dataclass
class ConnectionStatus:
    """Status of a toolkit connection"""
    toolkit: str
    is_connected: bool
    connection_details: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    redirect_url: Optional[str] = None
    required_parameters: List[str] = field(default_factory=list)


class ComposioMCPClient:
    """Client for interacting with Composio MCP tools"""
    
    def __init__(self, config: MCPConfig):
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.session: Optional[aiohttp.ClientSession] = None
        self.available_tools: Dict[str, ToolSchema] = {}
        self.connected_toolkits: Dict[str, ConnectionStatus] = {}
        self._initialized = False
    
    async def initialize(self):
        """Initialize the MCP client and discover available tools"""
        if self._initialized:
            return
        
        self.logger.info("Initializing Composio MCP client")
        
        # Create HTTP session
        self.session = aiohttp.ClientSession(
            headers={
                'Authorization': f'Bearer {self.config.api_key}',
                'Content-Type': 'application/json'
            },
            timeout=aiohttp.ClientTimeout(total=self.config.timeout)
        )
        
        # Discover available tools
        await self._discover_tools()
        
        # Check connections for configured toolkits
        await self._check_connections()
        
        self._initialized = True
        self.logger.info(f"MCP client initialized with {len(self.available_tools)} tools")
    
    async def close(self):
        """Close the MCP client"""
        if self.session:
            await self.session.close()
            self.session = None
        self._initialized = False
    
    async def _discover_tools(self):
        """Discover available tools from Composio"""
        try:
            # Search for coding-related tools
            tools_to_discover = [
                ("github", "Repository and git operations"),
                ("composio", "Remote execution and workbench"),
                ("file_manager", "File operations"),
                ("code_interpreter", "Code execution")
            ]
            
            for toolkit, description in tools_to_discover:
                self.logger.info(f"Discovering tools for {toolkit}: {description}")
                # In a real implementation, this would call RUBE_SEARCH_TOOLS
                # For now, we'll register known tools based on our search results
            
            # Register GitHub tools
            self._register_github_tools()
            
            # Register Composio execution tools
            self._register_composio_tools()
            
        except Exception as e:
            self.logger.error(f"Failed to discover tools: {e}")
            raise
    
    def _register_github_tools(self):
        """Register GitHub tools"""
        github_tools = [
            ToolSchema(
                toolkit="github",
                tool_slug="GITHUB_CREATE_OR_UPDATE_FILE_CONTENTS",
                description="Create or update files in a GitHub repository",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repo": {"type": "string"},
                        "path": {"type": "string"},
                        "message": {"type": "string"},
                        "content": {"type": "string"},
                        "branch": {"type": "string"},
                        "sha": {"type": "string"}
                    },
                    "required": ["owner", "repo", "path", "message", "content"]
                }
            ),
            ToolSchema(
                toolkit="github",
                tool_slug="GITHUB_GET_REPOSITORY_CONTENT",
                description="Get file content from a GitHub repository",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repo": {"type": "string"},
                        "path": {"type": "string"},
                        "ref": {"type": "string"}
                    },
                    "required": ["owner", "repo", "path"]
                }
            ),
            ToolSchema(
                toolkit="github",
                tool_slug="GITHUB_CREATE_A_PULL_REQUEST",
                description="Create a pull request in a GitHub repository",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repo": {"type": "string"},
                        "title": {"type": "string"},
                        "head": {"type": "string"},
                        "base": {"type": "string"},
                        "body": {"type": "string"},
                        "draft": {"type": "boolean"}
                    },
                    "required": ["owner", "repo", "head", "base"]
                }
            ),
            ToolSchema(
                toolkit="github",
                tool_slug="GITHUB_CREATE_AN_ISSUE",
                description="Create an issue in a GitHub repository",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repo": {"type": "string"},
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                        "labels": {"type": "array", "items": {"type": "string"}},
                        "assignees": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["owner", "repo", "title"]
                }
            ),
            ToolSchema(
                toolkit="github",
                tool_slug="GITHUB_LIST_BRANCHES",
                description="List branches in a GitHub repository",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repo": {"type": "string"},
                        "protected": {"type": "boolean"},
                        "page": {"type": "integer"},
                        "per_page": {"type": "integer"}
                    },
                    "required": ["owner", "repo"]
                }
            )
        ]
        
        for tool in github_tools:
            self.available_tools[tool.tool_slug] = tool
    
    def _register_composio_tools(self):
        """Register Composio execution tools"""
        composio_tools = [
            ToolSchema(
                toolkit="composio",
                tool_slug="COMPOSIO_REMOTE_BASH_TOOL",
                description="Execute bash commands remotely",
                input_schema={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "timeout": {"type": "integer", "default": 300}
                    },
                    "required": ["command"]
                }
            ),
            ToolSchema(
                toolkit="composio",
                tool_slug="COMPOSIO_REMOTE_WORKBENCH",
                description="Execute Python code in a remote workbench",
                input_schema={
                    "type": "object",
                    "properties": {
                        "code_to_execute": {"type": "string"},
                        "thought_process": {"type": "string"},
                        "file_path": {"type": "string"},
                        "timeout": {"type": "integer", "default": 600},
                        "disabled_tools": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["code_to_execute", "thought_process"]
                }
            )
        ]
        
        for tool in composio_tools:
            self.available_tools[tool.tool_slug] = tool
    
    async def _check_connections(self):
        """Check connection status for configured toolkits"""
        for toolkit in self.config.tools:
            status = await self.check_connection(toolkit)
            self.connected_toolkits[toolkit] = status
            
            if status.is_connected:
                self.logger.info(f"Toolkit {toolkit} is connected")
            else:
                self.logger.warning(f"Toolkit {toolkit} is not connected: {status.error_message}")
    
    async def check_connection(self, toolkit: str) -> ConnectionStatus:
        """Check if a toolkit is connected"""
        # In a real implementation, this would call COMPOSIO_MANAGE_CONNECTIONS
        # For now, we'll simulate based on known state
        
        if toolkit == "github":
            return ConnectionStatus(
                toolkit="github",
                is_connected=True,
                connection_details={
                    "connected_account_id": "ca_1NWS2Z315htY",
                    "status": "ACTIVE",
                    "user": "AlabamaMike"
                }
            )
        elif toolkit == "composio":
            return ConnectionStatus(
                toolkit="composio",
                is_connected=True,
                connection_details={"status": "ACTIVE"}
            )
        else:
            return ConnectionStatus(
                toolkit=toolkit,
                is_connected=False,
                error_message="Toolkit not configured",
                required_parameters=["api_key"]
            )
    
    async def connect_toolkit(self, toolkit: str, auth_params: Optional[Dict[str, Any]] = None) -> ConnectionStatus:
        """Connect to a toolkit with optional authentication parameters"""
        self.logger.info(f"Connecting to toolkit: {toolkit}")
        
        # In a real implementation, this would call COMPOSIO_MANAGE_CONNECTIONS
        # For now, we'll simulate the connection process
        
        if auth_params:
            self.logger.info(f"Using custom auth parameters for {toolkit}")
        
        # Simulate connection
        await asyncio.sleep(0.5)
        
        status = ConnectionStatus(
            toolkit=toolkit,
            is_connected=True,
            connection_details={"status": "ACTIVE", "connected_at": datetime.utcnow().isoformat()}
        )
        
        self.connected_toolkits[toolkit] = status
        return status
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def execute_tool(self, tool_slug: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a Composio tool"""
        if not self._initialized:
            await self.initialize()
        
        # Get tool schema
        tool = self.available_tools.get(tool_slug)
        if not tool:
            raise ValueError(f"Unknown tool: {tool_slug}")
        
        # Validate arguments
        is_valid, errors = tool.validate_arguments(arguments)
        if not is_valid:
            raise ValueError(f"Invalid arguments for {tool_slug}: {', '.join(errors)}")
        
        # Check toolkit connection
        if tool.toolkit not in self.connected_toolkits or not self.connected_toolkits[tool.toolkit].is_connected:
            self.logger.warning(f"Toolkit {tool.toolkit} not connected, attempting to connect")
            await self.connect_toolkit(tool.toolkit)
        
        self.logger.info(f"Executing tool {tool_slug} with arguments: {arguments}")
        
        # In a real implementation, this would call RUBE_MULTI_EXECUTE_TOOL
        # For now, we'll simulate the execution
        
        try:
            result = await self._simulate_tool_execution(tool_slug, arguments)
            self.logger.info(f"Tool {tool_slug} executed successfully")
            return result
        except Exception as e:
            self.logger.error(f"Failed to execute tool {tool_slug}: {e}")
            raise
    
    async def _simulate_tool_execution(self, tool_slug: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate tool execution for testing"""
        await asyncio.sleep(0.5)  # Simulate API call
        
        if tool_slug == "GITHUB_GET_REPOSITORY_CONTENT":
            return {
                "content": base64.b64encode(b"# Sample file content").decode(),
                "encoding": "base64",
                "sha": "abc123"
            }
        elif tool_slug == "COMPOSIO_REMOTE_BASH_TOOL":
            return {
                "stdout": f"Executed: {arguments['command']}",
                "stderr": "",
                "exit_code": 0
            }
        elif tool_slug == "COMPOSIO_REMOTE_WORKBENCH":
            return {
                "output": "Code executed successfully",
                "results": {},
                "errors": []
            }
        else:
            return {"status": "success", "data": {}}
    
    async def create_workflow_plan(self, use_case: str, difficulty: str = "medium") -> Dict[str, Any]:
        """Create a workflow plan for a use case"""
        self.logger.info(f"Creating workflow plan for: {use_case}")
        
        # In a real implementation, this would call COMPOSIO_CREATE_PLAN
        # For now, we'll create a sample plan
        
        plan = {
            "use_case": use_case,
            "difficulty": difficulty,
            "workflow_steps": [],
            "required_tools": [],
            "estimated_time": 0
        }
        
        # Add workflow steps based on use case
        if "implementation" in use_case.lower():
            plan["workflow_steps"] = [
                "1. Analyze requirements and existing code",
                "2. Create implementation plan",
                "3. Write code",
                "4. Test implementation",
                "5. Create pull request"
            ]
            plan["required_tools"] = [
                "GITHUB_GET_REPOSITORY_CONTENT",
                "COMPOSIO_REMOTE_WORKBENCH",
                "GITHUB_CREATE_OR_UPDATE_FILE_CONTENTS",
                "GITHUB_CREATE_A_PULL_REQUEST"
            ]
            plan["estimated_time"] = 300  # 5 minutes
        
        return plan
    
    async def execute_bash(self, command: str, timeout: int = 300) -> Dict[str, Any]:
        """Execute a bash command remotely"""
        return await self.execute_tool(
            "COMPOSIO_REMOTE_BASH_TOOL",
            {"command": command, "timeout": timeout}
        )
    
    async def execute_python(self, code: str, thought_process: str, 
                           file_path: Optional[str] = None, timeout: int = 600) -> Dict[str, Any]:
        """Execute Python code in the remote workbench"""
        arguments = {
            "code_to_execute": code,
            "thought_process": thought_process,
            "timeout": timeout
        }
        
        if file_path:
            arguments["file_path"] = file_path
        
        return await self.execute_tool("COMPOSIO_REMOTE_WORKBENCH", arguments)
    
    async def read_github_file(self, owner: str, repo: str, path: str, 
                              ref: Optional[str] = None) -> str:
        """Read a file from GitHub"""
        arguments = {"owner": owner, "repo": repo, "path": path}
        if ref:
            arguments["ref"] = ref
        
        result = await self.execute_tool("GITHUB_GET_REPOSITORY_CONTENT", arguments)
        
        # Decode base64 content
        if result.get("encoding") == "base64":
            content = base64.b64decode(result["content"]).decode('utf-8')
            return content
        
        return result.get("content", "")
    
    async def write_github_file(self, owner: str, repo: str, path: str,
                               content: str, message: str, branch: Optional[str] = None,
                               sha: Optional[str] = None) -> Dict[str, Any]:
        """Write or update a file in GitHub"""
        # Encode content to base64
        encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        
        arguments = {
            "owner": owner,
            "repo": repo,
            "path": path,
            "message": message,
            "content": encoded_content
        }
        
        if branch:
            arguments["branch"] = branch
        if sha:
            arguments["sha"] = sha
        
        return await self.execute_tool("GITHUB_CREATE_OR_UPDATE_FILE_CONTENTS", arguments)
    
    async def create_github_pr(self, owner: str, repo: str, title: str,
                              head: str, base: str, body: Optional[str] = None,
                              draft: bool = False) -> Dict[str, Any]:
        """Create a pull request in GitHub"""
        arguments = {
            "owner": owner,
            "repo": repo,
            "title": title,
            "head": head,
            "base": base,
            "draft": draft
        }
        
        if body:
            arguments["body"] = body
        
        return await self.execute_tool("GITHUB_CREATE_A_PULL_REQUEST", arguments)
    
    async def create_github_issue(self, owner: str, repo: str, title: str,
                                 body: Optional[str] = None, labels: Optional[List[str]] = None,
                                 assignees: Optional[List[str]] = None) -> Dict[str, Any]:
        """Create an issue in GitHub"""
        arguments = {
            "owner": owner,
            "repo": repo,
            "title": title
        }
        
        if body:
            arguments["body"] = body
        if labels:
            arguments["labels"] = labels
        if assignees:
            arguments["assignees"] = assignees
        
        return await self.execute_tool("GITHUB_CREATE_AN_ISSUE", arguments)
    
    def get_available_tools(self) -> List[str]:
        """Get list of available tool slugs"""
        return list(self.available_tools.keys())
    
    def get_connected_toolkits(self) -> List[str]:
        """Get list of connected toolkits"""
        return [k for k, v in self.connected_toolkits.items() if v.is_connected]
    
    def get_tool_schema(self, tool_slug: str) -> Optional[ToolSchema]:
        """Get schema for a specific tool"""
        return self.available_tools.get(tool_slug)