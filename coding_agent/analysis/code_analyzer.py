"""Code analysis module for understanding Python code structure and dependencies"""

import ast
import sys
import os
import logging
from pathlib import Path
from typing import Dict, List, Set, Optional, Any, Tuple, Union
from dataclasses import dataclass, field
from collections import defaultdict, deque
import tokenize
import io
import importlib.util
import json

import astroid
from astroid import nodes, inference_tip, MANAGER
from astroid.builder import AstroidBuilder
import rope.base.project
from rope.base import libutils
import radon.complexity as radon_cc
import radon.metrics as radon_metrics


@dataclass
class ImportInfo:
    """Information about an import statement"""
    module: str
    names: List[str]  # Specific names imported
    alias: Optional[str] = None
    is_relative: bool = False
    level: int = 0  # Relative import level
    line_number: int = 0
    is_builtin: bool = False
    is_local: bool = False
    is_third_party: bool = False


@dataclass
class FunctionInfo:
    """Information about a function"""
    name: str
    line_start: int
    line_end: int
    args: List[str]
    returns: Optional[str] = None
    docstring: Optional[str] = None
    decorators: List[str] = field(default_factory=list)
    complexity: int = 1
    calls: List[str] = field(default_factory=list)
    is_async: bool = False
    is_method: bool = False
    is_classmethod: bool = False
    is_staticmethod: bool = False
    is_property: bool = False


@dataclass
class ClassInfo:
    """Information about a class"""
    name: str
    line_start: int
    line_end: int
    bases: List[str]
    methods: List[FunctionInfo]
    attributes: Dict[str, Any]
    docstring: Optional[str] = None
    decorators: List[str] = field(default_factory=list)
    is_abstract: bool = False
    metaclass: Optional[str] = None


@dataclass
class ModuleInfo:
    """Information about a Python module"""
    path: Path
    name: str
    imports: List[ImportInfo]
    functions: List[FunctionInfo]
    classes: List[ClassInfo]
    global_vars: Dict[str, Any]
    docstring: Optional[str] = None
    line_count: int = 0
    complexity: int = 0
    maintainability_index: float = 0.0
    dependencies: Set[str] = field(default_factory=set)


@dataclass
class ProjectStructure:
    """Overall project structure analysis"""
    root_path: Path
    modules: Dict[str, ModuleInfo]
    dependency_graph: Dict[str, Set[str]]
    entry_points: List[str]
    packages: List[str]
    total_lines: int = 0
    total_complexity: int = 0
    test_coverage: Optional[float] = None


class CodeAnalyzer:
    """Comprehensive code analyzer for Python projects"""
    
    def __init__(self, project_root: Optional[Path] = None):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.project_root = project_root or Path.cwd()
        self.project_structure: Optional[ProjectStructure] = None
        
        # Rope project for advanced analysis
        self.rope_project = None
        
        # Cache for analyzed modules
        self.module_cache: Dict[str, ModuleInfo] = {}
        
        # Standard library modules
        self.stdlib_modules = set(sys.stdlib_module_names if hasattr(sys, 'stdlib_module_names') 
                                 else self._get_stdlib_modules())
    
    def _get_stdlib_modules(self) -> Set[str]:
        """Get list of standard library modules"""
        import stdlib_list
        return set(stdlib_list.stdlib_list())
    
    def analyze_project(self, path: Optional[Path] = None) -> ProjectStructure:
        """Analyze entire project structure"""
        project_path = path or self.project_root
        self.logger.info(f"Analyzing project at {project_path}")
        
        # Initialize rope project
        self._init_rope_project(project_path)
        
        # Find all Python modules
        modules = {}
        dependency_graph = defaultdict(set)
        
        for py_file in project_path.rglob("*.py"):
            # Skip virtual environments and hidden directories
            if any(part.startswith('.') or part in ['venv', 'env', '__pycache__'] 
                   for part in py_file.parts):
                continue
            
            try:
                module_info = self.analyze_module(py_file)
                module_name = self._get_module_name(py_file, project_path)
                modules[module_name] = module_info
                
                # Build dependency graph
                for imp in module_info.imports:
                    if imp.is_local:
                        dependency_graph[module_name].add(imp.module)
                        
            except Exception as e:
                self.logger.error(f"Failed to analyze {py_file}: {e}")
        
        # Identify entry points
        entry_points = self._find_entry_points(modules)
        
        # Calculate totals
        total_lines = sum(m.line_count for m in modules.values())
        total_complexity = sum(m.complexity for m in modules.values())
        
        # Find packages
        packages = self._find_packages(project_path)
        
        self.project_structure = ProjectStructure(
            root_path=project_path,
            modules=modules,
            dependency_graph=dict(dependency_graph),
            entry_points=entry_points,
            packages=packages,
            total_lines=total_lines,
            total_complexity=total_complexity
        )
        
        return self.project_structure
    
    def analyze_module(self, file_path: Path) -> ModuleInfo:
        """Analyze a single Python module"""
        
        # Check cache
        cache_key = str(file_path)
        if cache_key in self.module_cache:
            return self.module_cache[cache_key]
        
        self.logger.debug(f"Analyzing module {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            source = f.read()
        
        # Parse AST
        tree = ast.parse(source, filename=str(file_path))
        
        # Get module docstring
        docstring = ast.get_docstring(tree)
        
        # Analyze components
        visitor = ModuleVisitor()
        visitor.visit(tree)
        
        # Analyze with astroid for more advanced features
        astroid_module = self._analyze_with_astroid(source, file_path)
        
        # Calculate metrics
        line_count = len(source.splitlines())
        complexity = self._calculate_complexity(source)
        maintainability = self._calculate_maintainability(source)
        
        # Classify imports
        imports = self._classify_imports(visitor.imports, file_path)
        
        # Extract dependencies
        dependencies = {imp.module for imp in imports if not imp.is_builtin}
        
        module_info = ModuleInfo(
            path=file_path,
            name=file_path.stem,
            imports=imports,
            functions=visitor.functions,
            classes=visitor.classes,
            global_vars=visitor.global_vars,
            docstring=docstring,
            line_count=line_count,
            complexity=complexity,
            maintainability_index=maintainability,
            dependencies=dependencies
        )
        
        # Cache the result
        self.module_cache[cache_key] = module_info
        
        return module_info
    
    def analyze_function(self, source: str, function_name: str) -> Optional[FunctionInfo]:
        """Analyze a specific function"""
        tree = ast.parse(source)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                return self._extract_function_info(node, source)
        
        return None
    
    def analyze_class(self, source: str, class_name: str) -> Optional[ClassInfo]:
        """Analyze a specific class"""
        tree = ast.parse(source)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                return self._extract_class_info(node, source)
        
        return None
    
    def find_dependencies(self, module_path: Path) -> Set[str]:
        """Find all dependencies of a module"""
        module_info = self.analyze_module(module_path)
        
        dependencies = set()
        for imp in module_info.imports:
            if not imp.is_builtin:
                dependencies.add(imp.module)
        
        return dependencies
    
    def find_unused_imports(self, source: str) -> List[str]:
        """Find unused imports in source code"""
        tree = ast.parse(source)
        
        # Get all imports
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.asname or alias.name)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imports.append(alias.asname or alias.name)
        
        # Find used names
        used_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used_names.add(node.id)
            elif isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name):
                    used_names.add(node.value.id)
        
        # Find unused
        unused = [imp for imp in imports if imp not in used_names]
        
        return unused
    
    def find_undefined_names(self, source: str) -> List[str]:
        """Find undefined names in source code"""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []
        
        # Get all defined names
        defined = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                defined.add(node.name)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                defined.add(node.id)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    defined.add(alias.asname or alias.name)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    defined.add(alias.asname or alias.name)
        
        # Add builtins
        defined.update(dir(__builtins__))
        
        # Find used but not defined
        undefined = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                if node.id not in defined:
                    undefined.append(node.id)
        
        return list(set(undefined))
    
    def calculate_cyclomatic_complexity(self, source: str) -> int:
        """Calculate cyclomatic complexity of source code"""
        return self._calculate_complexity(source)
    
    def find_code_smells(self, source: str) -> List[Dict[str, Any]]:
        """Find potential code smells"""
        smells = []
        tree = ast.parse(source)
        
        for node in ast.walk(tree):
            # Long functions
            if isinstance(node, ast.FunctionDef):
                func_source = ast.get_source_segment(source, node)
                if func_source and len(func_source.splitlines()) > 50:
                    smells.append({
                        'type': 'long_function',
                        'name': node.name,
                        'line': node.lineno,
                        'description': f'Function {node.name} is too long (>50 lines)'
                    })
                
                # Too many parameters
                if len(node.args.args) > 5:
                    smells.append({
                        'type': 'too_many_parameters',
                        'name': node.name,
                        'line': node.lineno,
                        'description': f'Function {node.name} has too many parameters ({len(node.args.args)})'
                    })
            
            # Large classes
            elif isinstance(node, ast.ClassDef):
                methods = [n for n in node.body if isinstance(n, ast.FunctionDef)]
                if len(methods) > 20:
                    smells.append({
                        'type': 'large_class',
                        'name': node.name,
                        'line': node.lineno,
                        'description': f'Class {node.name} has too many methods ({len(methods)})'
                    })
            
            # Duplicate code (simplified check)
            # In production, use more sophisticated duplicate detection
        
        return smells
    
    def suggest_refactorings(self, source: str) -> List[Dict[str, Any]]:
        """Suggest potential refactorings"""
        suggestions = []
        tree = ast.parse(source)
        
        for node in ast.walk(tree):
            # Extract method suggestions
            if isinstance(node, ast.FunctionDef):
                func_source = ast.get_source_segment(source, node)
                if func_source:
                    lines = func_source.splitlines()
                    if len(lines) > 20:
                        # Look for logical sections
                        suggestions.append({
                            'type': 'extract_method',
                            'function': node.name,
                            'line': node.lineno,
                            'reason': 'Function is long and could be split'
                        })
            
            # Inline variable suggestions
            elif isinstance(node, ast.Assign):
                if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                    var_name = node.targets[0].id
                    # Check if variable is used only once
                    uses = sum(1 for n in ast.walk(tree) 
                             if isinstance(n, ast.Name) and n.id == var_name 
                             and isinstance(n.ctx, ast.Load))
                    if uses == 1:
                        suggestions.append({
                            'type': 'inline_variable',
                            'variable': var_name,
                            'line': node.lineno,
                            'reason': 'Variable is used only once'
                        })
        
        return suggestions
    
    def generate_dependency_graph(self) -> Dict[str, List[str]]:
        """Generate dependency graph for the project"""
        if not self.project_structure:
            self.analyze_project()
        
        graph = {}
        for module_name, deps in self.project_structure.dependency_graph.items():
            graph[module_name] = list(deps)
        
        return graph
    
    def find_circular_dependencies(self) -> List[List[str]]:
        """Find circular dependencies in the project"""
        if not self.project_structure:
            self.analyze_project()
        
        cycles = []
        visited = set()
        rec_stack = []
        
        def dfs(module):
            visited.add(module)
            rec_stack.append(module)
            
            for dep in self.project_structure.dependency_graph.get(module, []):
                if dep not in visited:
                    result = dfs(dep)
                    if result:
                        return result
                elif dep in rec_stack:
                    # Found cycle
                    cycle_start = rec_stack.index(dep)
                    return rec_stack[cycle_start:] + [dep]
            
            rec_stack.pop()
            return None
        
        for module in self.project_structure.modules:
            if module not in visited:
                cycle = dfs(module)
                if cycle:
                    cycles.append(cycle)
        
        return cycles
    
    def _init_rope_project(self, project_path: Path):
        """Initialize rope project for advanced analysis"""
        try:
            self.rope_project = rope.base.project.Project(str(project_path))
        except Exception as e:
            self.logger.error(f"Failed to initialize rope project: {e}")
            self.rope_project = None
    
    def _analyze_with_astroid(self, source: str, file_path: Path):
        """Use astroid for advanced analysis"""
        try:
            builder = AstroidBuilder()
            module = builder.string_build(source, modname=file_path.stem)
            return module
        except Exception as e:
            self.logger.debug(f"Astroid analysis failed: {e}")
            return None
    
    def _calculate_complexity(self, source: str) -> int:
        """Calculate cyclomatic complexity"""
        try:
            results = radon_cc.cc_visit(source)
            total = sum(r.complexity for r in results)
            return total
        except:
            return 0
    
    def _calculate_maintainability(self, source: str) -> float:
        """Calculate maintainability index"""
        try:
            return radon_metrics.mi_visit(source, multi=False)
        except:
            return 0.0
    
    def _classify_imports(self, imports: List[ImportInfo], file_path: Path) -> List[ImportInfo]:
        """Classify imports as builtin, local, or third-party"""
        classified = []
        
        for imp in imports:
            # Check if builtin
            base_module = imp.module.split('.')[0]
            if base_module in self.stdlib_modules:
                imp.is_builtin = True
            # Check if local (relative or in project)
            elif imp.is_relative or self._is_local_module(imp.module, file_path):
                imp.is_local = True
            else:
                imp.is_third_party = True
            
            classified.append(imp)
        
        return classified
    
    def _is_local_module(self, module_name: str, file_path: Path) -> bool:
        """Check if module is local to the project"""
        # Check if module exists in project
        module_path = module_name.replace('.', '/')
        
        # Check as package
        package_path = self.project_root / module_path
        if package_path.is_dir() and (package_path / '__init__.py').exists():
            return True
        
        # Check as module
        module_file = self.project_root / f"{module_path}.py"
        if module_file.exists():
            return True
        
        return False
    
    def _extract_function_info(self, node: ast.FunctionDef, source: str) -> FunctionInfo:
        """Extract information from function node"""
        # Get arguments
        args = [arg.arg for arg in node.args.args]
        
        # Get return type
        returns = None
        if node.returns:
            returns = ast.unparse(node.returns) if hasattr(ast, 'unparse') else None
        
        # Get decorators
        decorators = []
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name):
                decorators.append(dec.id)
            elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
                decorators.append(dec.func.id)
        
        # Calculate complexity
        func_source = ast.get_source_segment(source, node) or ""
        complexity = self._calculate_complexity(func_source)
        
        # Find function calls
        calls = []
        for n in ast.walk(node):
            if isinstance(n, ast.Call):
                if isinstance(n.func, ast.Name):
                    calls.append(n.func.id)
                elif isinstance(n.func, ast.Attribute):
                    calls.append(n.func.attr)
        
        return FunctionInfo(
            name=node.name,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            args=args,
            returns=returns,
            docstring=ast.get_docstring(node),
            decorators=decorators,
            complexity=complexity,
            calls=calls,
            is_async=isinstance(node, ast.AsyncFunctionDef),
            is_method='self' in args,
            is_classmethod='classmethod' in decorators,
            is_staticmethod='staticmethod' in decorators,
            is_property='property' in decorators
        )
    
    def _extract_class_info(self, node: ast.ClassDef, source: str) -> ClassInfo:
        """Extract information from class node"""
        # Get base classes
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(ast.unparse(base) if hasattr(ast, 'unparse') else '')
        
        # Get methods
        methods = []
        attributes = {}
        
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                methods.append(self._extract_function_info(item, source))
            elif isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        attributes[target.id] = None  # Could extract value if needed
        
        # Get decorators
        decorators = []
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name):
                decorators.append(dec.id)
        
        return ClassInfo(
            name=node.name,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            bases=bases,
            methods=methods,
            attributes=attributes,
            docstring=ast.get_docstring(node),
            decorators=decorators,
            is_abstract='ABC' in bases or 'ABCMeta' in str(decorators)
        )
    
    def _get_module_name(self, file_path: Path, project_path: Path) -> str:
        """Get module name from file path"""
        try:
            relative = file_path.relative_to(project_path)
            parts = list(relative.parts[:-1]) + [relative.stem]
            return '.'.join(parts)
        except ValueError:
            return file_path.stem
    
    def _find_entry_points(self, modules: Dict[str, ModuleInfo]) -> List[str]:
        """Find entry points (modules with if __name__ == '__main__')"""
        entry_points = []
        
        for name, module in modules.items():
            # Check for main block
            with open(module.path, 'r') as f:
                source = f.read()
                if 'if __name__ == "__main__"' in source or "if __name__ == '__main__'" in source:
                    entry_points.append(name)
        
        return entry_points
    
    def _find_packages(self, project_path: Path) -> List[str]:
        """Find all packages in the project"""
        packages = []
        
        for init_file in project_path.rglob("__init__.py"):
            if any(part.startswith('.') or part in ['venv', 'env', '__pycache__'] 
                   for part in init_file.parts):
                continue
            
            package_path = init_file.parent
            try:
                relative = package_path.relative_to(project_path)
                package_name = '.'.join(relative.parts)
                packages.append(package_name)
            except ValueError:
                pass
        
        return packages


class ModuleVisitor(ast.NodeVisitor):
    """AST visitor for extracting module information"""
    
    def __init__(self):
        self.imports: List[ImportInfo] = []
        self.functions: List[FunctionInfo] = []
        self.classes: List[ClassInfo] = []
        self.global_vars: Dict[str, Any] = {}
    
    def visit_Import(self, node):
        for alias in node.names:
            self.imports.append(ImportInfo(
                module=alias.name,
                names=[],
                alias=alias.asname,
                line_number=node.lineno
            ))
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node):
        module = node.module or ''
        for alias in node.names:
            self.imports.append(ImportInfo(
                module=module,
                names=[alias.name],
                alias=alias.asname,
                is_relative=node.level > 0,
                level=node.level,
                line_number=node.lineno
            ))
        self.generic_visit(node)
    
    def visit_FunctionDef(self, node):
        # Skip methods (they're handled in ClassDef)
        if not self._is_nested(node):
            # Extract function info manually to avoid circular dependency
            args = [arg.arg for arg in node.args.args]
            
            self.functions.append(FunctionInfo(
                name=node.name,
                line_start=node.lineno,
                line_end=node.end_lineno or node.lineno,
                args=args,
                docstring=ast.get_docstring(node)
            ))
        self.generic_visit(node)
    
    def visit_ClassDef(self, node):
        if not self._is_nested(node):
            # Extract class info
            bases = []
            for base in node.bases:
                if isinstance(base, ast.Name):
                    bases.append(base.id)
            
            methods = []
            attributes = {}
            
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    args = [arg.arg for arg in item.args.args]
                    methods.append(FunctionInfo(
                        name=item.name,
                        line_start=item.lineno,
                        line_end=item.end_lineno or item.lineno,
                        args=args,
                        docstring=ast.get_docstring(item),
                        is_method=True
                    ))
                elif isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            attributes[target.id] = None
            
            self.classes.append(ClassInfo(
                name=node.name,
                line_start=node.lineno,
                line_end=node.end_lineno or node.lineno,
                bases=bases,
                methods=methods,
                attributes=attributes,
                docstring=ast.get_docstring(node)
            ))
        self.generic_visit(node)
    
    def visit_Assign(self, node):
        # Only track module-level assignments
        if not self._is_nested(node):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.global_vars[target.id] = None  # Could extract value
        self.generic_visit(node)
    
    def _is_nested(self, node):
        """Check if node is nested inside a function or class"""
        # This is a simplified check
        # In production, track nesting level properly
        return False