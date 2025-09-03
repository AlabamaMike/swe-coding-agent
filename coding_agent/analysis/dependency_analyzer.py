"""Dependency analysis and resolution for Python projects"""

import ast
import json
import subprocess
import sys
import re
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict, deque
import pkg_resources
import importlib.metadata
import logging
import requests
from packaging import version
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet


@dataclass
class Package:
    """Information about a Python package"""
    name: str
    version: Optional[str] = None
    specifier: Optional[SpecifierSet] = None
    is_installed: bool = False
    installed_version: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    source: str = "pypi"  # pypi, local, git, etc.
    extras: Set[str] = field(default_factory=set)


@dataclass
class DependencyConflict:
    """Information about a dependency conflict"""
    package: str
    required_by: Dict[str, str]  # package -> version spec
    resolution: Optional[str] = None
    severity: str = "warning"  # warning, error


@dataclass
class DependencyTree:
    """Dependency tree structure"""
    package: Package
    children: List['DependencyTree'] = field(default_factory=list)
    depth: int = 0


class DependencyAnalyzer:
    """Analyze and manage Python dependencies"""
    
    def __init__(self, project_root: Optional[Path] = None):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.project_root = project_root or Path.cwd()
        
        # Cache for package information
        self.package_cache: Dict[str, Package] = {}
        
        # Installed packages
        self.installed_packages = self._get_installed_packages()
    
    def analyze_requirements(self, requirements_file: Optional[Path] = None) -> List[Package]:
        """Analyze requirements from a requirements file"""
        if not requirements_file:
            requirements_file = self.project_root / "requirements.txt"
        
        if not requirements_file.exists():
            self.logger.warning(f"Requirements file not found: {requirements_file}")
            return []
        
        packages = []
        
        with open(requirements_file, 'r') as f:
            for line in f:
                line = line.strip()
                
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue
                
                # Handle -r (recursive requirements)
                if line.startswith('-r '):
                    sub_file = self.project_root / line[3:].strip()
                    packages.extend(self.analyze_requirements(sub_file))
                    continue
                
                # Parse requirement
                try:
                    req = Requirement(line)
                    package = Package(
                        name=req.name,
                        specifier=req.specifier,
                        extras=req.extras
                    )
                    
                    # Check if installed
                    if req.name.lower() in self.installed_packages:
                        package.is_installed = True
                        package.installed_version = self.installed_packages[req.name.lower()]
                    
                    packages.append(package)
                    
                except Exception as e:
                    self.logger.error(f"Failed to parse requirement: {line} - {e}")
        
        return packages
    
    def analyze_imports(self, source_files: List[Path]) -> Dict[str, Set[str]]:
        """Analyze imports from source files to find dependencies"""
        imports_map = defaultdict(set)
        
        for file_path in source_files:
            if not file_path.exists():
                continue
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    source = f.read()
                
                tree = ast.parse(source)
                
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            module = alias.name.split('.')[0]
                            imports_map[str(file_path)].add(module)
                    
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            module = node.module.split('.')[0]
                            imports_map[str(file_path)].add(module)
            
            except Exception as e:
                self.logger.error(f"Failed to analyze imports in {file_path}: {e}")
        
        return dict(imports_map)
    
    def find_missing_dependencies(self, source_files: List[Path]) -> List[str]:
        """Find imported modules that are not installed"""
        imports = self.analyze_imports(source_files)
        
        all_imports = set()
        for file_imports in imports.values():
            all_imports.update(file_imports)
        
        # Filter out standard library modules
        missing = []
        for module in all_imports:
            if not self._is_stdlib(module) and not self._is_installed(module):
                # Check if it's a local module
                if not self._is_local_module(module):
                    missing.append(module)
        
        return missing
    
    def resolve_conflicts(self, packages: List[Package]) -> List[DependencyConflict]:
        """Find and resolve dependency conflicts"""
        conflicts = []
        
        # Group packages by name
        package_requirements = defaultdict(list)
        for pkg in packages:
            package_requirements[pkg.name.lower()].append(pkg)
        
        # Check for conflicts
        for name, pkgs in package_requirements.items():
            if len(pkgs) > 1:
                # Check if specifiers are compatible
                specs = [pkg.specifier for pkg in pkgs if pkg.specifier]
                
                if specs and not self._are_specs_compatible(specs):
                    conflict = DependencyConflict(
                        package=name,
                        required_by={f"req_{i}": str(spec) for i, spec in enumerate(specs)},
                        severity="error"
                    )
                    
                    # Try to find resolution
                    resolution = self._find_resolution(name, specs)
                    if resolution:
                        conflict.resolution = resolution
                        conflict.severity = "warning"
                    
                    conflicts.append(conflict)
        
        return conflicts
    
    def build_dependency_tree(self, package_name: str, max_depth: int = 3) -> DependencyTree:
        """Build dependency tree for a package"""
        package = self._get_package_info(package_name)
        
        if not package:
            return DependencyTree(package=Package(name=package_name))
        
        return self._build_tree_recursive(package, 0, max_depth, set())
    
    def _build_tree_recursive(self, package: Package, depth: int, max_depth: int, 
                            visited: Set[str]) -> DependencyTree:
        """Recursively build dependency tree"""
        tree = DependencyTree(package=package, depth=depth)
        
        if depth >= max_depth or package.name in visited:
            return tree
        
        visited.add(package.name)
        
        # Get dependencies
        deps = self._get_package_dependencies(package.name)
        
        for dep_name in deps:
            dep_package = self._get_package_info(dep_name)
            if dep_package:
                child_tree = self._build_tree_recursive(dep_package, depth + 1, max_depth, visited)
                tree.children.append(child_tree)
        
        return tree
    
    def install_package(self, package_name: str, version_spec: Optional[str] = None,
                       upgrade: bool = False) -> bool:
        """Install a Python package"""
        cmd = [sys.executable, "-m", "pip", "install"]
        
        if upgrade:
            cmd.append("--upgrade")
        
        if version_spec:
            cmd.append(f"{package_name}{version_spec}")
        else:
            cmd.append(package_name)
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                self.logger.info(f"Successfully installed {package_name}")
                # Update installed packages cache
                self.installed_packages = self._get_installed_packages()
                return True
            else:
                self.logger.error(f"Failed to install {package_name}: {result.stderr}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error installing {package_name}: {e}")
            return False
    
    def uninstall_package(self, package_name: str) -> bool:
        """Uninstall a Python package"""
        cmd = [sys.executable, "-m", "pip", "uninstall", "-y", package_name]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                self.logger.info(f"Successfully uninstalled {package_name}")
                # Update installed packages cache
                self.installed_packages = self._get_installed_packages()
                return True
            else:
                self.logger.error(f"Failed to uninstall {package_name}: {result.stderr}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error uninstalling {package_name}: {e}")
            return False
    
    def update_requirements(self, packages: List[Package], output_file: Optional[Path] = None):
        """Update requirements file with resolved packages"""
        if not output_file:
            output_file = self.project_root / "requirements.txt"
        
        lines = []
        for pkg in packages:
            if pkg.version:
                lines.append(f"{pkg.name}=={pkg.version}")
            elif pkg.specifier:
                lines.append(f"{pkg.name}{pkg.specifier}")
            else:
                lines.append(pkg.name)
        
        with open(output_file, 'w') as f:
            f.write('\n'.join(lines))
        
        self.logger.info(f"Updated requirements file: {output_file}")
    
    def freeze_requirements(self, output_file: Optional[Path] = None) -> List[str]:
        """Freeze current environment requirements"""
        if not output_file:
            output_file = self.project_root / "requirements.freeze.txt"
        
        cmd = [sys.executable, "-m", "pip", "freeze"]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                requirements = result.stdout.strip().split('\n')
                
                with open(output_file, 'w') as f:
                    f.write(result.stdout)
                
                self.logger.info(f"Froze requirements to {output_file}")
                return requirements
            else:
                self.logger.error(f"Failed to freeze requirements: {result.stderr}")
                return []
                
        except Exception as e:
            self.logger.error(f"Error freezing requirements: {e}")
            return []
    
    def check_security_vulnerabilities(self, packages: List[Package]) -> List[Dict[str, Any]]:
        """Check packages for known security vulnerabilities"""
        vulnerabilities = []
        
        # Use safety or pip-audit for real implementation
        # This is a simplified version
        
        for pkg in packages:
            if pkg.is_installed:
                # Check against a vulnerability database
                # In production, use safety DB or similar
                vuln = self._check_vulnerability(pkg.name, pkg.installed_version)
                if vuln:
                    vulnerabilities.append(vuln)
        
        return vulnerabilities
    
    def _get_installed_packages(self) -> Dict[str, str]:
        """Get dictionary of installed packages"""
        installed = {}
        
        try:
            for dist in importlib.metadata.distributions():
                name = dist.metadata.get('Name', '').lower()
                version = dist.metadata.get('Version', '')
                if name:
                    installed[name] = version
        except:
            # Fallback to pkg_resources
            for dist in pkg_resources.working_set:
                installed[dist.key] = dist.version
        
        return installed
    
    def _get_package_info(self, package_name: str) -> Optional[Package]:
        """Get package information from PyPI or local"""
        
        # Check cache
        if package_name in self.package_cache:
            return self.package_cache[package_name]
        
        # Check if installed
        if package_name.lower() in self.installed_packages:
            package = Package(
                name=package_name,
                version=self.installed_packages[package_name.lower()],
                is_installed=True,
                installed_version=self.installed_packages[package_name.lower()]
            )
            
            # Get dependencies
            package.dependencies = self._get_package_dependencies(package_name)
            
            self.package_cache[package_name] = package
            return package
        
        # Query PyPI
        try:
            response = requests.get(f"https://pypi.org/pypi/{package_name}/json", timeout=5)
            if response.status_code == 200:
                data = response.json()
                info = data.get('info', {})
                
                package = Package(
                    name=package_name,
                    version=info.get('version'),
                    is_installed=False
                )
                
                # Get dependencies from requires_dist
                requires = info.get('requires_dist', [])
                if requires:
                    package.dependencies = [req.split(';')[0].strip() for req in requires]
                
                self.package_cache[package_name] = package
                return package
                
        except Exception as e:
            self.logger.debug(f"Failed to get package info for {package_name}: {e}")
        
        return None
    
    def _get_package_dependencies(self, package_name: str) -> List[str]:
        """Get dependencies of an installed package"""
        dependencies = []
        
        try:
            dist = importlib.metadata.distribution(package_name)
            requires = dist.requires
            
            if requires:
                for req in requires:
                    # Parse requirement to get package name
                    parsed = Requirement(req)
                    dependencies.append(parsed.name)
                    
        except Exception:
            # Fallback to pkg_resources
            try:
                dist = pkg_resources.get_distribution(package_name)
                for req in dist.requires():
                    dependencies.append(req.key)
            except:
                pass
        
        return dependencies
    
    def _is_stdlib(self, module_name: str) -> bool:
        """Check if module is part of standard library"""
        if sys.version_info >= (3, 10):
            return module_name in sys.stdlib_module_names
        else:
            # Fallback for older Python versions
            import stdlib_list
            return module_name in stdlib_list.stdlib_list()
    
    def _is_installed(self, module_name: str) -> bool:
        """Check if module is installed"""
        # Check if it's a package
        if module_name.lower() in self.installed_packages:
            return True
        
        # Try to import
        try:
            __import__(module_name)
            return True
        except ImportError:
            return False
    
    def _is_local_module(self, module_name: str) -> bool:
        """Check if module is local to the project"""
        # Check if module file exists in project
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
    
    def _are_specs_compatible(self, specs: List[SpecifierSet]) -> bool:
        """Check if version specifiers are compatible"""
        # Find intersection of all specifiers
        try:
            combined = specs[0]
            for spec in specs[1:]:
                combined = combined & spec
            
            # Check if there's any version that satisfies all
            # This is simplified - in production, query available versions
            return len(combined) > 0
            
        except Exception:
            return False
    
    def _find_resolution(self, package_name: str, specs: List[SpecifierSet]) -> Optional[str]:
        """Find a version that satisfies all specifiers"""
        # Get available versions from PyPI
        try:
            response = requests.get(f"https://pypi.org/pypi/{package_name}/json", timeout=5)
            if response.status_code == 200:
                data = response.json()
                releases = data.get('releases', {})
                
                # Sort versions
                versions = sorted(releases.keys(), key=lambda v: version.parse(v), reverse=True)
                
                # Find first version that satisfies all specs
                for ver in versions:
                    v = version.parse(ver)
                    if all(str(v) in spec for spec in specs):
                        return ver
                        
        except Exception as e:
            self.logger.debug(f"Failed to find resolution for {package_name}: {e}")
        
        return None
    
    def _check_vulnerability(self, package_name: str, version: str) -> Optional[Dict[str, Any]]:
        """Check for security vulnerabilities"""
        # In production, use safety DB or similar
        # This is a placeholder
        
        # Known vulnerable packages (example)
        vulnerable = {
            'requests': {'< 2.20.0': 'CVE-2018-18074'},
            'django': {'< 3.2': 'Multiple vulnerabilities'},
            'flask': {'< 1.0': 'Security issues'}
        }
        
        if package_name.lower() in vulnerable:
            for spec, cve in vulnerable[package_name.lower()].items():
                if self._version_matches(version, spec):
                    return {
                        'package': package_name,
                        'installed_version': version,
                        'vulnerability': cve,
                        'severity': 'high',
                        'recommendation': f'Upgrade {package_name} to latest version'
                    }
        
        return None
    
    def _version_matches(self, version: str, spec: str) -> bool:
        """Check if version matches a specifier"""
        try:
            specifier = SpecifierSet(spec)
            return version in specifier
        except:
            return False