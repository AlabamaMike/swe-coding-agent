#!/usr/bin/env python3
"""
Demo script showing MCP integration with the coding agent

This demonstrates:
- Initializing MCP integration
- Executing code remotely
- Working with GitHub repositories
- Creating issues and pull requests
"""

import asyncio
import os
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from coding_agent.core.config import AgentConfig, MCPConfig
from coding_agent.integrations.mcp_integration import MCPIntegration


async def demo_code_execution(mcp: MCPIntegration):
    """Demonstrate code execution capabilities"""
    print("\n=== Code Execution Demo ===")
    
    # Execute Python code
    python_code = """
import sys
import platform

print(f"Python version: {sys.version}")
print(f"Platform: {platform.platform()}")
print(f"Architecture: {platform.machine()}")

# Create a simple function
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

# Test the function
for i in range(10):
    print(f"fibonacci({i}) = {fibonacci(i)}")
"""
    
    print("\n1. Executing Python code...")
    result = await mcp.execute_code(python_code, language="python")
    
    if result.success:
        print("✅ Python execution successful!")
        print(f"Output:\n{result.output}")
    else:
        print(f"❌ Python execution failed: {result.error}")
    
    # Execute bash command
    bash_command = "echo 'Hello from bash!' && ls -la && pwd"
    
    print("\n2. Executing bash command...")
    result = await mcp.execute_code(bash_command, language="bash")
    
    if result.success:
        print("✅ Bash execution successful!")
        print(f"Output:\n{result.output}")
    else:
        print(f"❌ Bash execution failed: {result.error}")


async def demo_github_operations(mcp: MCPIntegration):
    """Demonstrate GitHub operations"""
    print("\n=== GitHub Operations Demo ===")
    
    repo_url = "https://github.com/AlabamaMike/swe-coding-agent"
    
    # Read a file from the repository
    print(f"\n1. Reading README.md from {repo_url}...")
    content = await mcp.read_repository_file(repo_url, "README.md")
    
    if content:
        print("✅ File read successful!")
        print(f"Content preview (first 200 chars):\n{content[:200]}...")
    else:
        print("❌ Failed to read file")
    
    # Analyze repository structure
    print(f"\n2. Analyzing repository structure...")
    analysis = await mcp.analyze_code_structure(repo_url)
    
    print("Repository analysis:")
    print(f"  Total files: {analysis.get('total_files', 0)}")
    print(f"  Python files: {analysis.get('python_files', 0)}")
    print(f"  Test files: {len(analysis.get('test_files', []))}")
    print(f"  Config files: {len(analysis.get('config_files', []))}")
    print(f"  Detected frameworks: {', '.join(analysis.get('frameworks', []))}")
    
    # Create an issue (commented out to avoid creating real issues)
    """
    print(f"\n3. Creating a GitHub issue...")
    issue_url = await mcp.create_issue(
        repo_url=repo_url,
        title="[Demo] MCP Integration Test",
        body="This is a test issue created by the MCP integration demo.\n\n"
              "## Test Details\n"
              "- Created by: coding_agent\n"
              "- Purpose: Testing MCP integration\n"
              "- Status: Success ✅",
        labels=["test", "automated"]
    )
    
    if issue_url:
        print(f"✅ Issue created: {issue_url}")
    else:
        print("❌ Failed to create issue")
    """


async def demo_testing_capabilities(mcp: MCPIntegration):
    """Demonstrate testing capabilities"""
    print("\n=== Testing Capabilities Demo ===")
    
    # Create a simple test file
    test_code = """
def add(a, b):
    return a + b

def test_add():
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
    assert add(0, 0) == 0
    print("All tests passed!")

if __name__ == "__main__":
    test_add()
"""
    
    print("\n1. Running inline tests...")
    result = await mcp.execute_code(test_code, language="python")
    
    if result.success:
        print("✅ Tests executed successfully!")
        print(f"Output: {result.output}")
    else:
        print(f"❌ Test execution failed: {result.error}")
    
    # Install dependencies (simulated)
    print("\n2. Installing dependencies...")
    success = await mcp.install_dependencies(
        ["requests", "pytest"],
        package_manager="pip"
    )
    
    if success:
        print("✅ Dependencies installed successfully")
    else:
        print("❌ Failed to install dependencies")


async def demo_workflow_planning(mcp: MCPIntegration):
    """Demonstrate workflow planning"""
    print("\n=== Workflow Planning Demo ===")
    
    from coding_agent.core.base import TaskSpecification, TaskType, TaskContext
    
    # Create a sample task
    task = TaskSpecification(
        title="Implement user authentication",
        description="Add JWT-based authentication to the REST API",
        type=TaskType.IMPLEMENTATION,
        requirements=[
            "Use PyJWT library",
            "Implement login endpoint",
            "Implement logout endpoint",
            "Add middleware for token validation",
            "Include refresh token mechanism"
        ],
        context=TaskContext(
            repository_url="https://github.com/example/api",
            branch="feature/auth",
            relevant_files=["api/views.py", "api/middleware.py"]
        )
    )
    
    print(f"\nCreating workflow plan for: {task.title}")
    plan = await mcp.create_workflow_plan(task)
    
    print("\nWorkflow Plan:")
    print(f"  Use case: {plan.get('use_case', 'N/A')}")
    print(f"  Difficulty: {plan.get('difficulty', 'N/A')}")
    print(f"  Estimated time: {plan.get('estimated_time', 0)} seconds")
    
    if plan.get('workflow_steps'):
        print("\n  Steps:")
        for step in plan['workflow_steps']:
            print(f"    - {step}")
    
    if plan.get('required_tools'):
        print("\n  Required tools:")
        for tool in plan['required_tools']:
            print(f"    - {tool}")


async def main():
    """Main demo function"""
    print("=" * 60)
    print("MCP Integration Demo for Coding Agent")
    print("=" * 60)
    
    # Create configuration
    mcp_config = MCPConfig(
        api_key=os.getenv("COMPOSIO_API_KEY", "demo_key"),
        server_type="composio",
        tools=["github", "composio", "file_manager", "code_interpreter"]
    )
    
    # Create MCP integration
    mcp = MCPIntegration(mcp_config)
    
    try:
        # Initialize MCP
        print("\nInitializing MCP integration...")
        await mcp.initialize()
        print("✅ MCP initialized successfully")
        
        # Validate environment
        print("\nValidating environment...")
        validations = await mcp.validate_environment()
        
        print("Environment validation results:")
        for component, status in validations.items():
            status_icon = "✅" if status else "❌"
            print(f"  {status_icon} {component}")
        
        # Run demos
        await demo_code_execution(mcp)
        await demo_github_operations(mcp)
        await demo_testing_capabilities(mcp)
        await demo_workflow_planning(mcp)
        
        print("\n" + "=" * 60)
        print("Demo completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup
        print("\nCleaning up...")
        await mcp.close()
        print("✅ Cleanup complete")


if __name__ == "__main__":
    # Run the demo
    asyncio.run(main())