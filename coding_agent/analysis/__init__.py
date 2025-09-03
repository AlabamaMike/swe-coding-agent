"""Code analysis and understanding module"""

from .code_analyzer import (
    CodeAnalyzer,
    ProjectStructure,
    ModuleInfo,
    ClassInfo,
    FunctionInfo,
    CodeMetrics
)

from .dependency_analyzer import (
    DependencyAnalyzer,
    Package,
    DependencyConflict,
    DependencyTree
)

from .project_analyzer import (
    ProjectAnalyzer,
    ProjectAnalysis,
    AnalysisContext
)

__all__ = [
    'CodeAnalyzer',
    'ProjectStructure',
    'ModuleInfo',
    'ClassInfo',
    'FunctionInfo',
    'CodeMetrics',
    'DependencyAnalyzer',
    'Package',
    'DependencyConflict',
    'DependencyTree',
    'ProjectAnalyzer',
    'ProjectAnalysis',
    'AnalysisContext'
]