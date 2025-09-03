"""High-level MCP integration for the coding agent"""

import asyncio
import logging
import tempfile
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from dataclasses import dataclass
import json

from .mcp_client import ComposioMCPClient, ToolSchema, ConnectionStatus
from ..core.config import MCPConfig
from ..core.base import TaskSpecification, TaskResult, TaskStatus


@dataclass
class CodeExecutionResult:
    """Result of code execution"""
    success: bool
    output: str
    error: Optional[str] = None
    exit_code: int = 0
    execution_time: float = 0.0
    artifacts: List[str] = None


@dataclass
class FileOperation:
    """File operation details"""
    operation: str  # create, update, delete, read
    path: str
    content: Optional[str] = None
    sha: Optional[str] = None
    encoding: str = "utf-8"


class MCPIntegration:
    """High-level MCP integration for the coding agent"""
    
    def __init__(self, config: MCPConfig):
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.client = ComposioMCPClient(config)
        self._workspace_path: Optional[Path] = None
    
    async def initialize(self):
        """Initialize MCP integration"""
        self.logger.info("Initializing MCP integration")
        
        # Initialize the MCP client
        await self.client.initialize()
        
        # Setup workspace
        await self._setup_workspace()
        
        # Verify required toolkits are connected
        await self._verify_toolkits()
        
        self.logger.info("MCP integration initialized successfully")
    
    async def close(self):
        """Close MCP integration"""
        await self.client.close()
        
        # Cleanup workspace if needed
        if self._workspace_path and self._workspace_path.exists():
            try:
                import shutil
                shutil.rmtree(self._workspace_path)
            except Exception as e:
                self.logger.error(f"Failed to cleanup workspace: {e}")
    
    async def _setup_workspace(self):
        """Setup local workspace for temporary files"""
        self._workspace_path = Path(tempfile.mkdtemp(prefix="coding_agent_"))
        self.logger.info(f"Created workspace at {self._workspace_path}")
    
    async def _verify_toolkits(self):
        """Verify required toolkits are connected"""
        required_toolkits = ["github", "composio"]
        
        for toolkit in required_toolkits:
            status = await self.client.check_connection(toolkit)
            if not status.is_connected:
                self.logger.warning(f"Toolkit {toolkit} not connected, attempting to connect")
                status = await self.client.connect_toolkit(toolkit)
                
                if not status.is_connected:
                    raise RuntimeError(f"Failed to connect to required toolkit: {toolkit}")
    
    async def execute_code(self, code: str, language: str = "python",
                          timeout: int = 300) -> CodeExecutionResult:
        """Execute code in the appropriate environment"""
        self.logger.info(f"Executing {language} code")
        
        try:
            if language == "python":
                result = await self._execute_python(code, timeout)
            elif language == "bash":
                result = await self._execute_bash(code, timeout)
            else:
                return CodeExecutionResult(
                    success=False,
                    output="",
                    error=f"Unsupported language: {language}"
                )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Code execution failed: {e}")
            return CodeExecutionResult(
                success=False,
                output="",
                error=str(e),
                exit_code=1
            )
    
    async def _execute_python(self, code: str, timeout: int) -> CodeExecutionResult:
        """Execute Python code in the remote workbench"""
        result = await self.client.execute_python(
            code=code,
            thought_process="Executing Python code for task implementation",
            timeout=timeout
        )
        
        return CodeExecutionResult(
            success=not result.get("errors"),
            output=result.get("output", ""),
            error="\n".join(result.get("errors", [])) if result.get("errors") else None,
            exit_code=0 if not result.get("errors") else 1,
            artifacts=result.get("artifacts", [])
        )
    
    async def _execute_bash(self, command: str, timeout: int) -> CodeExecutionResult:
        """Execute bash command remotely"""
        result = await self.client.execute_bash(command, timeout)
        
        return CodeExecutionResult(
            success=result.get("exit_code", 0) == 0,
            output=result.get("stdout", ""),
            error=result.get("stderr") if result.get("stderr") else None,
            exit_code=result.get("exit_code", 0)
        )
    
    async def read_repository_file(self, repo_url: str, file_path: str,
                                  branch: Optional[str] = None) -> Optional[str]:
        """Read a file from a repository"""
        # Parse repository URL
        owner, repo = self._parse_repo_url(repo_url)
        
        try:
            content = await self.client.read_github_file(
                owner=owner,
                repo=repo,
                path=file_path,
                ref=branch
            )
            return content
        except Exception as e:
            self.logger.error(f"Failed to read file {file_path} from {repo_url}: {e}")
            return None
    
    async def write_repository_file(self, repo_url: str, file_path: str,
                                   content: str, message: str,
                                   branch: Optional[str] = None) -> bool:
        """Write or update a file in a repository"""
        owner, repo = self._parse_repo_url(repo_url)
        
        try:
            # Check if file exists to get SHA for update
            sha = None
            try:
                existing = await self.client.execute_tool(
                    "GITHUB_GET_REPOSITORY_CONTENT",
                    {"owner": owner, "repo": repo, "path": file_path}
                )
                sha = existing.get("sha")
            except:
                pass  # File doesn't exist, will create new
            
            result = await self.client.write_github_file(
                owner=owner,
                repo=repo,
                path=file_path,
                content=content,
                message=message,
                branch=branch,
                sha=sha
            )
            
            return result.get("content") is not None
            
        except Exception as e:
            self.logger.error(f"Failed to write file {file_path} to {repo_url}: {e}")
            return False
    
    async def create_pull_request(self, repo_url: str, title: str,
                                 head_branch: str, base_branch: str,
                                 body: Optional[str] = None) -> Optional[str]:
        """Create a pull request"""
        owner, repo = self._parse_repo_url(repo_url)
        
        try:
            result = await self.client.create_github_pr(
                owner=owner,
                repo=repo,
                title=title,
                head=head_branch,
                base=base_branch,
                body=body,
                draft=False
            )
            
            return result.get("html_url")
            
        except Exception as e:
            self.logger.error(f"Failed to create pull request: {e}")
            return None
    
    async def create_issue(self, repo_url: str, title: str,
                          body: str, labels: Optional[List[str]] = None) -> Optional[str]:
        """Create an issue for task tracking"""
        owner, repo = self._parse_repo_url(repo_url)
        
        # Add default labels
        if labels is None:
            labels = []
        labels.extend(["coding-agent", "automated"])
        
        try:
            result = await self.client.create_github_issue(
                owner=owner,
                repo=repo,
                title=title,
                body=body,
                labels=labels
            )
            
            return result.get("html_url")
            
        except Exception as e:
            self.logger.error(f"Failed to create issue: {e}")
            return None
    
    async def list_repository_files(self, repo_url: str,
                                   path: str = "", branch: Optional[str] = None) -> List[str]:
        """List files in a repository directory"""
        owner, repo = self._parse_repo_url(repo_url)
        
        try:
            # Use GitHub API to list directory contents
            result = await self.client.execute_tool(
                "GITHUB_GET_REPOSITORY_CONTENT",
                {
                    "owner": owner,
                    "repo": repo,
                    "path": path,
                    "ref": branch
                }
            )
            
            # Parse directory listing
            if isinstance(result, list):
                return [item["path"] for item in result if item["type"] == "file"]
            
            return []
            
        except Exception as e:
            self.logger.error(f"Failed to list files in {repo_url}/{path}: {e}")
            return []
    
    async def run_tests(self, test_command: str = "pytest",
                       working_dir: Optional[str] = None) -> CodeExecutionResult:
        """Run tests in the remote environment"""
        self.logger.info(f"Running tests with command: {test_command}")
        
        # Prepare command with working directory
        if working_dir:
            command = f"cd {working_dir} && {test_command}"
        else:
            command = test_command
        
        # Add coverage if pytest
        if "pytest" in test_command and "--cov" not in test_command:
            command += " --cov --cov-report=term-missing"
        
        return await self.execute_code(command, language="bash", timeout=600)
    
    async def install_dependencies(self, requirements: List[str],
                                  package_manager: str = "pip") -> bool:
        """Install dependencies in the remote environment"""
        self.logger.info(f"Installing {len(requirements)} dependencies with {package_manager}")
        
        if package_manager == "pip":
            command = f"pip install {' '.join(requirements)}"
        elif package_manager == "poetry":
            command = f"poetry add {' '.join(requirements)}"
        elif package_manager == "conda":
            command = f"conda install -y {' '.join(requirements)}"
        else:
            self.logger.error(f"Unsupported package manager: {package_manager}")
            return False
        
        result = await self.execute_code(command, language="bash", timeout=300)
        return result.success
    
    async def analyze_code_structure(self, repo_url: str,
                                    branch: Optional[str] = None) -> Dict[str, Any]:
        """Analyze repository code structure"""
        owner, repo = self._parse_repo_url(repo_url)
        
        analysis = {
            "files": [],
            "languages": {},
            "frameworks": [],
            "test_files": [],
            "config_files": []
        }
        
        try:
            # Get repository file tree
            python_code = f"""
import json
import requests

# Get repository tree
url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch or 'main'}?recursive=1"
headers = {{"Authorization": "token YOUR_GITHUB_TOKEN"}}

response = requests.get(url)
if response.status_code == 200:
    tree = response.json()
    files = [item['path'] for item in tree['tree'] if item['type'] == 'blob']
    
    # Analyze file types
    python_files = [f for f in files if f.endswith('.py')]
    test_files = [f for f in python_files if 'test' in f.lower()]
    config_files = [f for f in files if f.endswith(('.yml', '.yaml', '.json', '.toml', '.ini'))]
    
    # Detect frameworks
    frameworks = []
    if any('django' in f.lower() for f in files):
        frameworks.append('django')
    if any('fastapi' in f.lower() or 'main.py' in f for f in files):
        frameworks.append('fastapi')
    if any('flask' in f.lower() or 'app.py' in f for f in files):
        frameworks.append('flask')
    
    result = {{
        'total_files': len(files),
        'python_files': len(python_files),
        'test_files': test_files,
        'config_files': config_files,
        'frameworks': frameworks
    }}
    
    print(json.dumps(result))
"""
            
            result = await self.execute_code(python_code, language="python")
            
            if result.success and result.output:
                analysis.update(json.loads(result.output))
            
        except Exception as e:
            self.logger.error(f"Failed to analyze code structure: {e}")
        
        return analysis
    
    async def create_workflow_plan(self, task: TaskSpecification) -> Dict[str, Any]:
        """Create a workflow plan for a task"""
        use_case = f"{task.type.value}: {task.title} - {task.description}"
        
        # Determine difficulty based on task complexity
        difficulty = "easy"
        if len(task.requirements) > 5:
            difficulty = "hard"
        elif len(task.requirements) > 2:
            difficulty = "medium"
        
        return await self.client.create_workflow_plan(use_case, difficulty)
    
    def _parse_repo_url(self, repo_url: str) -> Tuple[str, str]:
        """Parse repository URL to extract owner and repo name"""
        # Handle various URL formats
        url = repo_url.replace("https://", "").replace("http://", "")
        url = url.replace("github.com/", "").replace(".git", "")
        
        parts = url.split("/")
        if len(parts) >= 2:
            return parts[0], parts[1]
        
        raise ValueError(f"Invalid repository URL: {repo_url}")
    
    async def validate_environment(self) -> Dict[str, bool]:
        """Validate the execution environment"""
        validations = {}
        
        # Check Python version
        result = await self.execute_code("python --version", language="bash")
        validations["python"] = result.success
        
        # Check common tools
        for tool in ["git", "pip", "pytest", "black", "ruff"]:
            result = await self.execute_code(f"which {tool}", language="bash")
            validations[tool] = result.success
        
        # Check GitHub connection
        github_status = await self.client.check_connection("github")
        validations["github"] = github_status.is_connected
        
        # Check Composio connection
        composio_status = await self.client.check_connection("composio")
        validations["composio"] = composio_status.is_connected
        
        return validations
    
    async def save_task_state(self, task_id: str, state: Dict[str, Any]) -> bool:
        """Save task state for recovery"""
        try:
            state_file = self._workspace_path / f"{task_id}_state.json"
            state_file.write_text(json.dumps(state, indent=2))
            return True
        except Exception as e:
            self.logger.error(f"Failed to save task state: {e}")
            return False
    
    async def load_task_state(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Load saved task state"""
        try:
            state_file = self._workspace_path / f"{task_id}_state.json"
            if state_file.exists():
                return json.loads(state_file.read_text())
            return None
        except Exception as e:
            self.logger.error(f"Failed to load task state: {e}")
            return None