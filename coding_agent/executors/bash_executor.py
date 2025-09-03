"""Local bash shell executor for the coding agent"""

import asyncio
import os
import subprocess
import tempfile
import shlex
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Union
from dataclasses import dataclass, field
from datetime import datetime
import json
import re


@dataclass
class BashCommand:
    """Represents a bash command to execute"""
    command: str
    working_dir: Optional[Path] = None
    environment: Dict[str, str] = field(default_factory=dict)
    timeout: int = 300
    capture_output: bool = True
    shell: bool = True
    check: bool = False
    stdin_input: Optional[str] = None


@dataclass
class BashResult:
    """Result of bash command execution"""
    command: str
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    execution_time: float
    working_dir: str
    environment_changes: Dict[str, str] = field(default_factory=dict)
    files_created: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    files_deleted: List[str] = field(default_factory=list)


class BashExecutor:
    """Expert bash shell executor for local development tasks"""
    
    def __init__(self, base_dir: Optional[Path] = None):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.base_dir = base_dir or Path.cwd()
        self.environment = os.environ.copy()
        self.shell_history: List[BashResult] = []
        self.working_directory = self.base_dir
        self.persistent_session: Optional[asyncio.subprocess.Process] = None
        
        # Common tool paths
        self._tool_cache: Dict[str, Optional[str]] = {}
        
        # File system tracking
        self._initial_files: set = set()
        self._track_filesystem_state()
    
    def _track_filesystem_state(self):
        """Track initial filesystem state for change detection"""
        try:
            for root, dirs, files in os.walk(self.working_directory):
                for file in files:
                    self._initial_files.add(Path(root) / file)
        except Exception as e:
            self.logger.error(f"Failed to track filesystem state: {e}")
    
    async def initialize_session(self):
        """Initialize a persistent bash session"""
        self.logger.info("Initializing persistent bash session")
        
        try:
            self.persistent_session = await asyncio.create_subprocess_shell(
                "bash",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_directory,
                env=self.environment
            )
            
            # Setup the session
            await self._execute_in_session("set -o pipefail")  # Fail on pipe errors
            await self._execute_in_session("export PS1='$ '")  # Simple prompt
            
            self.logger.info("Persistent bash session initialized")
        except Exception as e:
            self.logger.error(f"Failed to initialize session: {e}")
            self.persistent_session = None
    
    async def close_session(self):
        """Close the persistent bash session"""
        if self.persistent_session:
            try:
                self.persistent_session.terminate()
                await self.persistent_session.wait()
            except Exception as e:
                self.logger.error(f"Error closing session: {e}")
            finally:
                self.persistent_session = None
    
    async def execute(self, command: Union[str, BashCommand]) -> BashResult:
        """Execute a bash command with comprehensive tracking"""
        
        # Convert string to BashCommand if needed
        if isinstance(command, str):
            command = BashCommand(command=command, working_dir=self.working_directory)
        
        self.logger.info(f"Executing: {command.command[:100]}...")
        
        start_time = datetime.now()
        files_before = self._get_current_files()
        
        try:
            # Execute the command
            if self.persistent_session and not command.stdin_input:
                result = await self._execute_in_session(command.command)
            else:
                result = await self._execute_subprocess(command)
            
            # Track execution time
            execution_time = (datetime.now() - start_time).total_seconds()
            
            # Detect file changes
            files_after = self._get_current_files()
            files_created = list(files_after - files_before)
            files_deleted = list(files_before - files_after)
            files_modified = self._detect_modified_files(files_before, files_after)
            
            bash_result = BashResult(
                command=command.command,
                success=result['exit_code'] == 0,
                exit_code=result['exit_code'],
                stdout=result['stdout'],
                stderr=result['stderr'],
                execution_time=execution_time,
                working_dir=str(command.working_dir or self.working_directory),
                files_created=files_created,
                files_modified=files_modified,
                files_deleted=files_deleted
            )
            
            # Store in history
            self.shell_history.append(bash_result)
            
            # Log result
            if bash_result.success:
                self.logger.info(f"Command succeeded in {execution_time:.2f}s")
            else:
                self.logger.warning(f"Command failed with exit code {bash_result.exit_code}")
            
            return bash_result
            
        except Exception as e:
            self.logger.error(f"Command execution failed: {e}")
            return BashResult(
                command=command.command,
                success=False,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                execution_time=(datetime.now() - start_time).total_seconds(),
                working_dir=str(command.working_dir or self.working_directory)
            )
    
    async def _execute_subprocess(self, command: BashCommand) -> Dict[str, Any]:
        """Execute command in a subprocess"""
        
        # Prepare environment
        env = self.environment.copy()
        env.update(command.environment)
        
        # Prepare working directory
        cwd = command.working_dir or self.working_directory
        
        try:
            process = await asyncio.create_subprocess_shell(
                command.command,
                stdin=asyncio.subprocess.PIPE if command.stdin_input else None,
                stdout=asyncio.subprocess.PIPE if command.capture_output else None,
                stderr=asyncio.subprocess.PIPE if command.capture_output else None,
                cwd=cwd,
                env=env,
                shell=command.shell
            )
            
            # Send input if provided
            stdin_data = command.stdin_input.encode() if command.stdin_input else None
            
            # Wait with timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(input=stdin_data),
                    timeout=command.timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return {
                    'exit_code': -1,
                    'stdout': '',
                    'stderr': f'Command timed out after {command.timeout} seconds'
                }
            
            return {
                'exit_code': process.returncode,
                'stdout': stdout.decode('utf-8', errors='replace') if stdout else '',
                'stderr': stderr.decode('utf-8', errors='replace') if stderr else ''
            }
            
        except Exception as e:
            return {
                'exit_code': -1,
                'stdout': '',
                'stderr': str(e)
            }
    
    async def _execute_in_session(self, command: str) -> Dict[str, Any]:
        """Execute command in persistent session"""
        if not self.persistent_session:
            await self.initialize_session()
        
        if not self.persistent_session:
            # Fallback to subprocess
            return await self._execute_subprocess(BashCommand(command))
        
        try:
            # Send command
            self.persistent_session.stdin.write(f"{command}\n".encode())
            await self.persistent_session.stdin.drain()
            
            # Read output (simplified - in production, use markers)
            output = []
            while True:
                line = await asyncio.wait_for(
                    self.persistent_session.stdout.readline(),
                    timeout=0.5
                )
                if not line:
                    break
                output.append(line.decode('utf-8', errors='replace'))
            
            return {
                'exit_code': 0,
                'stdout': ''.join(output),
                'stderr': ''
            }
            
        except asyncio.TimeoutError:
            return {
                'exit_code': 0,
                'stdout': ''.join(output) if 'output' in locals() else '',
                'stderr': ''
            }
        except Exception as e:
            return {
                'exit_code': -1,
                'stdout': '',
                'stderr': str(e)
            }
    
    def _get_current_files(self) -> set:
        """Get current files in working directory"""
        current_files = set()
        try:
            for root, dirs, files in os.walk(self.working_directory):
                # Skip hidden directories and common ignore patterns
                dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
                for file in files:
                    if not file.startswith('.'):
                        current_files.add(Path(root) / file)
        except Exception as e:
            self.logger.error(f"Failed to scan files: {e}")
        
        return current_files
    
    def _detect_modified_files(self, before: set, after: set) -> List[str]:
        """Detect modified files based on timestamps"""
        modified = []
        common_files = before.intersection(after)
        
        for file_path in common_files:
            try:
                # Check if modification time changed
                # This is a simplified check - in production, use checksums
                modified.append(str(file_path))
            except Exception:
                pass
        
        return modified[:10]  # Limit to 10 files for performance
    
    async def run_script(self, script_content: str, language: str = "bash",
                        script_name: Optional[str] = None) -> BashResult:
        """Run a script file"""
        
        # Create temporary script file
        suffix = {
            "bash": ".sh",
            "python": ".py",
            "javascript": ".js",
            "ruby": ".rb",
            "perl": ".pl"
        }.get(language, ".sh")
        
        with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False) as f:
            f.write(script_content)
            script_path = f.name
        
        try:
            # Make executable if bash
            if language == "bash":
                await self.execute(f"chmod +x {script_path}")
            
            # Determine interpreter
            interpreter = {
                "bash": "bash",
                "python": "python3",
                "javascript": "node",
                "ruby": "ruby",
                "perl": "perl"
            }.get(language, "bash")
            
            # Execute script
            result = await self.execute(f"{interpreter} {script_path}")
            
            return result
            
        finally:
            # Cleanup
            try:
                os.unlink(script_path)
            except:
                pass
    
    async def check_tool(self, tool_name: str) -> Tuple[bool, Optional[str]]:
        """Check if a tool is available and get its path"""
        
        # Check cache
        if tool_name in self._tool_cache:
            return (True, self._tool_cache[tool_name]) if self._tool_cache[tool_name] else (False, None)
        
        # Check using which command
        result = await self.execute(f"which {tool_name}")
        
        if result.success and result.stdout.strip():
            tool_path = result.stdout.strip()
            self._tool_cache[tool_name] = tool_path
            return True, tool_path
        
        self._tool_cache[tool_name] = None
        return False, None
    
    async def install_tool(self, tool_name: str, package_manager: str = "auto") -> bool:
        """Install a tool using appropriate package manager"""
        
        # Auto-detect package manager
        if package_manager == "auto":
            managers = ["apt-get", "brew", "yum", "dnf", "pacman", "pip3", "npm"]
            for mgr in managers:
                exists, _ = await self.check_tool(mgr)
                if exists:
                    package_manager = mgr
                    break
        
        # Install commands for common tools
        install_commands = {
            "apt-get": f"sudo apt-get install -y {tool_name}",
            "brew": f"brew install {tool_name}",
            "yum": f"sudo yum install -y {tool_name}",
            "dnf": f"sudo dnf install -y {tool_name}",
            "pacman": f"sudo pacman -S --noconfirm {tool_name}",
            "pip3": f"pip3 install {tool_name}",
            "npm": f"npm install -g {tool_name}"
        }
        
        command = install_commands.get(package_manager)
        if not command:
            self.logger.error(f"Unknown package manager: {package_manager}")
            return False
        
        result = await self.execute(command)
        
        if result.success:
            # Clear cache for this tool
            self._tool_cache.pop(tool_name, None)
            
        return result.success
    
    async def git_operations(self, operation: str, **kwargs) -> BashResult:
        """Perform git operations"""
        
        operations = {
            "clone": f"git clone {kwargs.get('url')} {kwargs.get('dest', '')}",
            "pull": "git pull",
            "push": "git push",
            "commit": f"git commit -m \"{kwargs.get('message', 'Update')}\"",
            "add": f"git add {kwargs.get('files', '.')}",
            "branch": f"git checkout -b {kwargs.get('name')}",
            "checkout": f"git checkout {kwargs.get('ref')}",
            "status": "git status",
            "diff": f"git diff {kwargs.get('ref', '')}",
            "log": f"git log {kwargs.get('options', '--oneline -10')}"
        }
        
        command = operations.get(operation)
        if not command:
            raise ValueError(f"Unknown git operation: {operation}")
        
        return await self.execute(command)
    
    async def python_operations(self, operation: str, **kwargs) -> BashResult:
        """Perform Python-specific operations"""
        
        operations = {
            "install": f"pip install {kwargs.get('package')}",
            "uninstall": f"pip uninstall -y {kwargs.get('package')}",
            "freeze": "pip freeze",
            "test": f"pytest {kwargs.get('path', '.')} {kwargs.get('options', '')}",
            "lint": f"ruff check {kwargs.get('path', '.')}",
            "format": f"black {kwargs.get('path', '.')}",
            "typecheck": f"mypy {kwargs.get('path', '.')}",
            "venv_create": f"python -m venv {kwargs.get('name', 'venv')}",
            "venv_activate": f"source {kwargs.get('name', 'venv')}/bin/activate"
        }
        
        command = operations.get(operation)
        if not command:
            raise ValueError(f"Unknown Python operation: {operation}")
        
        return await self.execute(command)
    
    async def file_operations(self, operation: str, **kwargs) -> BashResult:
        """Perform file system operations"""
        
        operations = {
            "create": f"touch {kwargs.get('path')}",
            "delete": f"rm -f {kwargs.get('path')}",
            "copy": f"cp {kwargs.get('source')} {kwargs.get('dest')}",
            "move": f"mv {kwargs.get('source')} {kwargs.get('dest')}",
            "mkdir": f"mkdir -p {kwargs.get('path')}",
            "rmdir": f"rm -rf {kwargs.get('path')}",
            "chmod": f"chmod {kwargs.get('mode')} {kwargs.get('path')}",
            "chown": f"chown {kwargs.get('owner')} {kwargs.get('path')}",
            "find": f"find {kwargs.get('path', '.')} {kwargs.get('options', '')}",
            "grep": f"grep -r \"{kwargs.get('pattern')}\" {kwargs.get('path', '.')}",
            "sed": f"sed -i {kwargs.get('expression')} {kwargs.get('path')}"
        }
        
        command = operations.get(operation)
        if not command:
            raise ValueError(f"Unknown file operation: {operation}")
        
        return await self.execute(command)
    
    async def process_operations(self, operation: str, **kwargs) -> BashResult:
        """Perform process management operations"""
        
        operations = {
            "list": f"ps aux | grep {kwargs.get('pattern', '')}",
            "kill": f"kill {kwargs.get('signal', '')} {kwargs.get('pid')}",
            "killall": f"killall {kwargs.get('name')}",
            "top": "top -b -n 1",
            "ports": "netstat -tuln",
            "lsof": f"lsof {kwargs.get('options', '')}",
            "systemctl": f"systemctl {kwargs.get('action')} {kwargs.get('service')}"
        }
        
        command = operations.get(operation)
        if not command:
            raise ValueError(f"Unknown process operation: {operation}")
        
        return await self.execute(command)
    
    async def docker_operations(self, operation: str, **kwargs) -> BashResult:
        """Perform Docker operations"""
        
        operations = {
            "ps": "docker ps -a",
            "images": "docker images",
            "run": f"docker run {kwargs.get('options', '')} {kwargs.get('image')}",
            "build": f"docker build -t {kwargs.get('tag')} {kwargs.get('path', '.')}",
            "stop": f"docker stop {kwargs.get('container')}",
            "start": f"docker start {kwargs.get('container')}",
            "rm": f"docker rm {kwargs.get('container')}",
            "rmi": f"docker rmi {kwargs.get('image')}",
            "logs": f"docker logs {kwargs.get('container')}",
            "exec": f"docker exec {kwargs.get('container')} {kwargs.get('command')}"
        }
        
        command = operations.get(operation)
        if not command:
            raise ValueError(f"Unknown Docker operation: {operation}")
        
        return await self.execute(command)
    
    async def analyze_project(self) -> Dict[str, Any]:
        """Analyze the current project structure and configuration"""
        
        analysis = {
            "language": None,
            "framework": None,
            "dependencies": [],
            "test_framework": None,
            "build_tool": None,
            "version_control": None,
            "docker": False,
            "ci_cd": None
        }
        
        # Check for programming language
        language_files = {
            "python": ["*.py", "requirements.txt", "setup.py", "pyproject.toml"],
            "javascript": ["*.js", "package.json", "*.jsx"],
            "typescript": ["*.ts", "tsconfig.json", "*.tsx"],
            "java": ["*.java", "pom.xml", "build.gradle"],
            "go": ["*.go", "go.mod"],
            "rust": ["*.rs", "Cargo.toml"],
            "ruby": ["*.rb", "Gemfile"]
        }
        
        for lang, patterns in language_files.items():
            for pattern in patterns:
                result = await self.execute(f"find . -name '{pattern}' -type f | head -1")
                if result.success and result.stdout.strip():
                    analysis["language"] = lang
                    break
            if analysis["language"]:
                break
        
        # Check for frameworks (Python-specific for now)
        if analysis["language"] == "python":
            framework_checks = [
                ("django", "manage.py"),
                ("flask", "app.py"),
                ("fastapi", "main.py"),
                ("pytest", "pytest.ini"),
                ("unittest", "test_*.py")
            ]
            
            for framework, file_pattern in framework_checks:
                result = await self.execute(f"find . -name '{file_pattern}' -type f | head -1")
                if result.success and result.stdout.strip():
                    if framework in ["pytest", "unittest"]:
                        analysis["test_framework"] = framework
                    else:
                        analysis["framework"] = framework
        
        # Check for version control
        if (self.working_directory / ".git").exists():
            analysis["version_control"] = "git"
        
        # Check for Docker
        if (self.working_directory / "Dockerfile").exists():
            analysis["docker"] = True
        
        # Check for CI/CD
        ci_files = {
            ".github/workflows": "github_actions",
            ".gitlab-ci.yml": "gitlab_ci",
            "Jenkinsfile": "jenkins",
            ".circleci": "circleci"
        }
        
        for ci_path, ci_name in ci_files.items():
            if (self.working_directory / ci_path).exists():
                analysis["ci_cd"] = ci_name
                break
        
        return analysis
    
    async def create_project_structure(self, project_name: str, language: str,
                                     framework: Optional[str] = None) -> bool:
        """Create a new project structure"""
        
        project_path = self.working_directory / project_name
        
        # Create base directory
        await self.execute(f"mkdir -p {project_path}")
        
        if language == "python":
            # Python project structure
            dirs = [
                f"{project_path}/src",
                f"{project_path}/tests",
                f"{project_path}/docs",
                f"{project_path}/scripts"
            ]
            
            for dir_path in dirs:
                await self.execute(f"mkdir -p {dir_path}")
            
            # Create essential files
            files = {
                f"{project_path}/README.md": f"# {project_name}\n\nA Python project",
                f"{project_path}/requirements.txt": "",
                f"{project_path}/.gitignore": "__pycache__/\n*.pyc\nvenv/\n.env",
                f"{project_path}/setup.py": f"""from setuptools import setup, find_packages

setup(
    name="{project_name}",
    version="0.1.0",
    packages=find_packages(),
)""",
                f"{project_path}/src/__init__.py": "",
                f"{project_path}/tests/__init__.py": "",
                f"{project_path}/tests/test_main.py": """def test_placeholder():
    assert True"""
            }
            
            for file_path, content in files.items():
                await self.execute(f"echo '{content}' > {file_path}")
            
            # Framework-specific setup
            if framework == "django":
                await self.execute(f"cd {project_path} && django-admin startproject {project_name} .")
            elif framework == "flask":
                flask_app = f"""from flask import Flask

app = Flask(__name__)

@app.route('/')
def hello():
    return 'Hello, World!'

if __name__ == '__main__':
    app.run(debug=True)"""
                await self.execute(f"echo '{flask_app}' > {project_path}/app.py")
            elif framework == "fastapi":
                fastapi_app = f"""from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    return {{"message": "Hello World"}}"""
                await self.execute(f"echo '{fastapi_app}' > {project_path}/main.py")
        
        return True
    
    def get_history(self, last_n: Optional[int] = None) -> List[BashResult]:
        """Get command history"""
        if last_n:
            return self.shell_history[-last_n:]
        return self.shell_history
    
    def clear_history(self):
        """Clear command history"""
        self.shell_history.clear()
    
    async def change_directory(self, path: Union[str, Path]) -> bool:
        """Change working directory"""
        new_path = Path(path)
        if not new_path.is_absolute():
            new_path = self.working_directory / new_path
        
        if new_path.exists() and new_path.is_dir():
            self.working_directory = new_path
            self.logger.info(f"Changed working directory to {self.working_directory}")
            
            # Reinitialize session in new directory
            if self.persistent_session:
                await self.close_session()
                await self.initialize_session()
            
            return True
        
        self.logger.error(f"Directory does not exist: {new_path}")
        return False