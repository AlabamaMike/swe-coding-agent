"""Local execution environment that combines bash and file operations"""

import asyncio
import logging
import os
import sys
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List, Union, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import tempfile
import venv
import json

from .bash_executor import BashExecutor, BashCommand, BashResult
from .file_handler import FileHandler, FileInfo, FileChange
from ..core.base import TaskSpecification, TaskResult, TaskStatus, TaskExecutor


@dataclass
class LocalEnvironment:
    """Local execution environment configuration"""
    working_dir: Path
    python_executable: str = sys.executable
    virtual_env: Optional[Path] = None
    environment_vars: Dict[str, str] = field(default_factory=dict)
    installed_packages: List[str] = field(default_factory=list)
    active_branch: Optional[str] = None
    remote_url: Optional[str] = None


class LocalExecutor(TaskExecutor):
    """
    Expert local executor that uses bash and file operations
    instead of relying on MCP/remote execution
    """
    
    def __init__(self, base_dir: Optional[Path] = None):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.base_dir = base_dir or Path.cwd()
        
        # Initialize components
        self.bash = BashExecutor(self.base_dir)
        self.files = FileHandler(self.base_dir)
        
        # Environment tracking
        self.environment = LocalEnvironment(working_dir=self.base_dir)
        self._original_dir = Path.cwd()
        
        # Execution metrics
        self.execution_stats = {
            "commands_executed": 0,
            "files_created": 0,
            "files_modified": 0,
            "tests_run": 0,
            "errors_encountered": 0
        }
    
    async def initialize(self):
        """Initialize the local executor"""
        self.logger.info("Initializing local executor")
        
        # Initialize bash session
        await self.bash.initialize_session()
        
        # Detect environment
        await self._detect_environment()
        
        # Setup workspace
        await self._setup_workspace()
        
        self.logger.info("Local executor initialized")
    
    async def cleanup(self):
        """Cleanup resources"""
        await self.bash.close_session()
        
        # Return to original directory
        os.chdir(self._original_dir)
    
    async def validate(self, task: TaskSpecification) -> bool:
        """Validate if we can execute the task locally"""
        
        # Check if we have repository access
        if task.context.repository_url:
            # Check if it's a local path or we can clone it
            repo_path = Path(task.context.repository_url)
            if not repo_path.exists() and not task.context.repository_url.startswith(('http', 'git')):
                self.logger.warning(f"Repository not accessible: {task.context.repository_url}")
                return False
        
        # Check required tools
        required_tools = self._get_required_tools(task)
        for tool in required_tools:
            exists, _ = await self.bash.check_tool(tool)
            if not exists:
                self.logger.warning(f"Required tool not found: {tool}")
                # Try to install
                if not await self.bash.install_tool(tool):
                    return False
        
        return True
    
    async def execute(self, task: TaskSpecification) -> TaskResult:
        """Execute a task using local bash and file operations"""
        self.logger.info(f"Executing task locally: {task.title}")
        
        start_time = datetime.now()
        result = TaskResult(
            task_id=task.task_id,
            status=TaskStatus.IN_PROGRESS
        )
        
        try:
            # Setup repository if needed
            if task.context.repository_url:
                await self._setup_repository(task.context.repository_url, task.context.branch)
            
            # Setup Python environment if needed
            if task.type.value in ["implementation", "test_generation"]:
                await self._setup_python_environment()
            
            # Execute based on task type
            if task.type.value == "implementation":
                await self._execute_implementation(task, result)
            elif task.type.value == "refactoring":
                await self._execute_refactoring(task, result)
            elif task.type.value == "bug_fix":
                await self._execute_bugfix(task, result)
            elif task.type.value == "test_generation":
                await self._execute_test_generation(task, result)
            elif task.type.value == "optimization":
                await self._execute_optimization(task, result)
            else:
                raise ValueError(f"Unsupported task type: {task.type.value}")
            
            # Run tests if available
            await self._run_tests(result)
            
            # Commit changes if in git repository
            if await self._is_git_repository():
                await self._commit_changes(task, result)
            
            result.status = TaskStatus.COMPLETED
            result.result_type = "success"
            
        except Exception as e:
            self.logger.error(f"Task execution failed: {e}")
            result.status = TaskStatus.FAILED
            result.result_type = "error"
            result.error_message = str(e)
            self.execution_stats["errors_encountered"] += 1
        
        finally:
            # Calculate execution time
            result.execution_time = (datetime.now() - start_time).total_seconds()
            
            # Add execution metrics
            result.metrics = {
                "commands_executed": self.execution_stats["commands_executed"],
                "files_created": len(result.files_created),
                "files_modified": len(result.files_modified),
                "tests_run": self.execution_stats["tests_run"]
            }
        
        return result
    
    async def _detect_environment(self):
        """Detect current environment configuration"""
        
        # Detect Python version
        result = await self.bash.execute("python --version")
        if result.success:
            self.logger.info(f"Python version: {result.stdout.strip()}")
        
        # Detect virtual environment
        if os.environ.get("VIRTUAL_ENV"):
            self.environment.virtual_env = Path(os.environ["VIRTUAL_ENV"])
            self.logger.info(f"Virtual environment: {self.environment.virtual_env}")
        
        # Detect git repository
        result = await self.bash.execute("git rev-parse --show-toplevel")
        if result.success:
            repo_root = result.stdout.strip()
            self.logger.info(f"Git repository: {repo_root}")
            
            # Get current branch
            result = await self.bash.execute("git branch --show-current")
            if result.success:
                self.environment.active_branch = result.stdout.strip()
            
            # Get remote URL
            result = await self.bash.execute("git config --get remote.origin.url")
            if result.success:
                self.environment.remote_url = result.stdout.strip()
        
        # Detect installed packages
        result = await self.bash.execute("pip list --format=json")
        if result.success:
            try:
                packages = json.loads(result.stdout)
                self.environment.installed_packages = [p["name"] for p in packages]
            except:
                pass
    
    async def _setup_workspace(self):
        """Setup workspace for execution"""
        
        # Create working directory if needed
        self.environment.working_dir.mkdir(parents=True, exist_ok=True)
        
        # Change to working directory
        os.chdir(self.environment.working_dir)
        await self.bash.change_directory(self.environment.working_dir)
        
        self.logger.info(f"Working directory: {self.environment.working_dir}")
    
    async def _setup_repository(self, repo_url: str, branch: Optional[str] = None):
        """Setup repository for task execution"""
        
        # Check if it's a local path
        repo_path = Path(repo_url)
        if repo_path.exists():
            # Local repository
            await self.bash.change_directory(repo_path)
            self.environment.working_dir = repo_path
        else:
            # Remote repository - need to clone
            repo_name = repo_url.split("/")[-1].replace(".git", "")
            local_path = self.base_dir / repo_name
            
            if not local_path.exists():
                self.logger.info(f"Cloning repository: {repo_url}")
                result = await self.bash.git_operations("clone", url=repo_url, dest=str(local_path))
                
                if not result.success:
                    raise RuntimeError(f"Failed to clone repository: {result.stderr}")
            
            await self.bash.change_directory(local_path)
            self.environment.working_dir = local_path
        
        # Checkout branch if specified
        if branch:
            result = await self.bash.git_operations("checkout", ref=branch)
            if not result.success:
                # Try creating the branch
                result = await self.bash.git_operations("branch", name=branch)
    
    async def _setup_python_environment(self):
        """Setup Python environment with virtual env"""
        
        # Check if we should create a virtual environment
        if not self.environment.virtual_env:
            venv_path = self.environment.working_dir / "venv"
            
            if not venv_path.exists():
                self.logger.info("Creating virtual environment")
                result = await self.bash.python_operations("venv_create", name="venv")
                
                if result.success:
                    self.environment.virtual_env = venv_path
            
            # Activate virtual environment
            if venv_path.exists():
                activate_script = venv_path / "bin" / "activate"
                if activate_script.exists():
                    # Update environment
                    self.bash.environment["VIRTUAL_ENV"] = str(venv_path)
                    self.bash.environment["PATH"] = f"{venv_path / 'bin'}:{self.bash.environment.get('PATH', '')}"
                    self.environment.python_executable = str(venv_path / "bin" / "python")
        
        # Install dependencies if requirements.txt exists
        requirements_file = self.environment.working_dir / "requirements.txt"
        if requirements_file.exists():
            self.logger.info("Installing dependencies from requirements.txt")
            result = await self.bash.execute("pip install -r requirements.txt")
            self.execution_stats["commands_executed"] += 1
    
    async def _execute_implementation(self, task: TaskSpecification, result: TaskResult):
        """Execute an implementation task"""
        self.logger.info("Executing implementation task")
        
        # Analyze existing code structure
        analysis = await self.bash.analyze_project()
        
        # Create implementation based on requirements
        for requirement in task.requirements:
            self.logger.info(f"Implementing requirement: {requirement}")
            
            # This is a simplified example - in reality, this would use
            # code generation techniques, templates, or LLM-based generation
            
            # Example: Create a simple Python module
            if "api" in requirement.lower() or "endpoint" in requirement.lower():
                await self._create_api_endpoint(requirement, result)
            elif "model" in requirement.lower() or "class" in requirement.lower():
                await self._create_model_class(requirement, result)
            elif "function" in requirement.lower() or "method" in requirement.lower():
                await self._create_function(requirement, result)
    
    async def _execute_refactoring(self, task: TaskSpecification, result: TaskResult):
        """Execute a refactoring task"""
        self.logger.info("Executing refactoring task")
        
        # Identify files to refactor
        for file_path in task.context.relevant_files:
            full_path = self.environment.working_dir / file_path
            
            if not full_path.exists():
                self.logger.warning(f"File not found: {file_path}")
                continue
            
            # Read file content
            content = self.files.read_file(full_path)
            if not content:
                continue
            
            # Apply refactoring (simplified example)
            refactored = await self._apply_refactoring(content, task.requirements)
            
            # Write back
            if refactored != content:
                self.files.write_file(full_path, refactored)
                result.files_modified.append(file_path)
                self.execution_stats["files_modified"] += 1
    
    async def _execute_bugfix(self, task: TaskSpecification, result: TaskResult):
        """Execute a bug fix task"""
        self.logger.info("Executing bug fix task")
        
        # First, try to reproduce the bug with existing tests
        test_result = await self.bash.python_operations("test", path=".", options="-v")
        
        if not test_result.success:
            # Analyze test output to understand the failure
            self.logger.info("Found failing tests, analyzing...")
            
            # Fix the bug (simplified)
            for file_path in task.context.relevant_files:
                await self._fix_bug_in_file(file_path, test_result.stdout, result)
    
    async def _execute_test_generation(self, task: TaskSpecification, result: TaskResult):
        """Execute a test generation task"""
        self.logger.info("Executing test generation task")
        
        # Identify modules to test
        for file_path in task.context.relevant_files:
            if file_path.endswith(".py"):
                await self._generate_tests_for_file(file_path, result)
    
    async def _execute_optimization(self, task: TaskSpecification, result: TaskResult):
        """Execute an optimization task"""
        self.logger.info("Executing optimization task")
        
        # Profile the code first
        profile_result = await self.bash.execute("python -m cProfile -s cumulative main.py")
        
        # Apply optimizations based on profiling
        for file_path in task.context.relevant_files:
            await self._optimize_file(file_path, profile_result.stdout, result)
    
    async def _create_api_endpoint(self, requirement: str, result: TaskResult):
        """Create an API endpoint"""
        
        # Simple FastAPI endpoint example
        endpoint_code = '''
from fastapi import APIRouter, HTTPException
from typing import Optional
from pydantic import BaseModel

router = APIRouter()

class ItemModel(BaseModel):
    name: str
    description: Optional[str] = None
    price: float

@router.get("/items/{item_id}")
async def get_item(item_id: int):
    """Get an item by ID"""
    # TODO: Implement database lookup
    return {"item_id": item_id, "name": "Sample Item"}

@router.post("/items/")
async def create_item(item: ItemModel):
    """Create a new item"""
    # TODO: Implement database insertion
    return {"message": "Item created", "item": item}
'''
        
        # Write the endpoint file
        endpoint_file = self.environment.working_dir / "api" / "endpoints" / "items.py"
        self.files.write_file(endpoint_file, endpoint_code, create_dirs=True)
        result.files_created.append(str(endpoint_file.relative_to(self.environment.working_dir)))
        self.execution_stats["files_created"] += 1
    
    async def _create_model_class(self, requirement: str, result: TaskResult):
        """Create a model class"""
        
        model_code = '''
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class Model:
    """Generated model class"""
    id: int
    name: str
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    
    def update(self, **kwargs):
        """Update model attributes"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.updated_at = datetime.now()
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
'''
        
        model_file = self.environment.working_dir / "models" / "generated_model.py"
        self.files.write_file(model_file, model_code, create_dirs=True)
        result.files_created.append(str(model_file.relative_to(self.environment.working_dir)))
        self.execution_stats["files_created"] += 1
    
    async def _create_function(self, requirement: str, result: TaskResult):
        """Create a function"""
        
        function_code = '''
def process_data(data: list) -> dict:
    """Process data according to requirements"""
    if not data:
        return {"error": "No data provided"}
    
    result = {
        "count": len(data),
        "items": data,
        "processed_at": datetime.now().isoformat()
    }
    
    return result
'''
        
        utils_file = self.environment.working_dir / "utils" / "processor.py"
        self.files.write_file(utils_file, function_code, create_dirs=True)
        result.files_created.append(str(utils_file.relative_to(self.environment.working_dir)))
        self.execution_stats["files_created"] += 1
    
    async def _generate_tests_for_file(self, file_path: str, result: TaskResult):
        """Generate tests for a Python file"""
        
        source_file = self.environment.working_dir / file_path
        if not source_file.exists():
            return
        
        # Create test file
        test_file = self.environment.working_dir / "tests" / f"test_{source_file.stem}.py"
        
        test_code = f'''
import pytest
from {file_path.replace("/", ".").replace(".py", "")} import *

class Test{source_file.stem.title()}:
    """Tests for {source_file.stem}"""
    
    def test_basic(self):
        """Basic test case"""
        # TODO: Implement test
        assert True
    
    def test_edge_case(self):
        """Edge case test"""
        # TODO: Implement test
        with pytest.raises(ValueError):
            pass
    
    @pytest.fixture
    def sample_data(self):
        """Sample data fixture"""
        return {{"test": "data"}}
'''
        
        self.files.write_file(test_file, test_code, create_dirs=True)
        result.tests_added.append(str(test_file.relative_to(self.environment.working_dir)))
        self.execution_stats["files_created"] += 1
    
    async def _apply_refactoring(self, content: str, requirements: List[str]) -> str:
        """Apply refactoring to code content"""
        
        # This is a simplified example
        # In reality, would use AST manipulation, rope library, etc.
        
        refactored = content
        
        for req in requirements:
            if "extract method" in req.lower():
                # Simple example: extract long functions
                # Would use AST in real implementation
                pass
            elif "rename" in req.lower():
                # Simple rename operation
                # Would use rope or similar in real implementation
                pass
        
        return refactored
    
    async def _fix_bug_in_file(self, file_path: str, test_output: str, result: TaskResult):
        """Fix a bug in a specific file"""
        
        full_path = self.environment.working_dir / file_path
        content = self.files.read_file(full_path)
        
        if content:
            # Analyze test output and apply fix
            # This is simplified - would use more sophisticated analysis
            fixed_content = content
            
            self.files.write_file(full_path, fixed_content)
            result.files_modified.append(file_path)
    
    async def _optimize_file(self, file_path: str, profile_output: str, result: TaskResult):
        """Optimize a file based on profiling"""
        
        full_path = self.environment.working_dir / file_path
        content = self.files.read_file(full_path)
        
        if content:
            # Apply optimizations
            # This is simplified - would use actual optimization techniques
            optimized = content
            
            self.files.write_file(full_path, optimized)
            result.files_modified.append(file_path)
    
    async def _run_tests(self, result: TaskResult):
        """Run tests if available"""
        
        # Check for test framework
        if (self.environment.working_dir / "pytest.ini").exists() or \
           (self.environment.working_dir / "tests").exists():
            
            self.logger.info("Running tests...")
            test_result = await self.bash.python_operations("test", path=".", options="-v --tb=short")
            self.execution_stats["tests_run"] += 1
            
            if not test_result.success:
                result.warnings.append("Some tests failed")
    
    async def _commit_changes(self, task: TaskSpecification, result: TaskResult):
        """Commit changes to git"""
        
        # Add files
        await self.bash.git_operations("add", files=".")
        
        # Create commit message
        commit_message = f"{task.type.value}: {task.title}\n\n"
        commit_message += f"Task ID: {task.task_id}\n"
        commit_message += f"Files modified: {len(result.files_modified)}\n"
        commit_message += f"Files created: {len(result.files_created)}\n"
        
        if result.tests_added:
            commit_message += f"Tests added: {len(result.tests_added)}\n"
        
        # Commit
        commit_result = await self.bash.git_operations("commit", message=commit_message)
        
        if commit_result.success:
            # Get commit hash
            hash_result = await self.bash.execute("git rev-parse HEAD")
            if hash_result.success:
                result.commit_hash = hash_result.stdout.strip()
    
    async def _is_git_repository(self) -> bool:
        """Check if current directory is a git repository"""
        result = await self.bash.execute("git rev-parse --is-inside-work-tree")
        return result.success and result.stdout.strip() == "true"
    
    def _get_required_tools(self, task: TaskSpecification) -> List[str]:
        """Determine required tools for a task"""
        
        tools = ["git", "python", "pip"]
        
        if task.type.value == "test_generation":
            tools.append("pytest")
        
        if "docker" in str(task.requirements).lower():
            tools.append("docker")
        
        if "lint" in str(task.requirements).lower():
            tools.extend(["ruff", "black"])
        
        return tools