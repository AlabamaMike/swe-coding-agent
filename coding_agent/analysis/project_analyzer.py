"""Project-level analysis combining code and dependency analysis"""

import asyncio
import json
from pathlib import Path
from typing import Dict, List, Optional, Set, Any, Tuple
from dataclasses import dataclass, field
import logging

from .code_analyzer import CodeAnalyzer, ProjectStructure, CodeMetrics
from .dependency_analyzer import DependencyAnalyzer, Package, DependencyConflict


@dataclass
class ProjectAnalysis:
    """Complete project analysis results"""
    structure: ProjectStructure
    dependencies: List[Package]
    missing_dependencies: List[str]
    dependency_conflicts: List[DependencyConflict]
    security_vulnerabilities: List[Dict[str, Any]]
    code_quality_issues: List[Dict[str, Any]]
    refactoring_suggestions: List[Dict[str, Any]]
    test_coverage: Optional[float] = None
    documentation_coverage: Optional[float] = None
    technical_debt_score: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            'structure': {
                'total_files': self.structure.total_files,
                'total_lines': self.structure.total_lines,
                'total_classes': self.structure.total_classes,
                'total_functions': self.structure.total_functions,
                'packages': len(self.structure.packages)
            },
            'dependencies': {
                'total': len(self.dependencies),
                'installed': sum(1 for d in self.dependencies if d.is_installed),
                'missing': self.missing_dependencies,
                'conflicts': len(self.dependency_conflicts)
            },
            'security': {
                'vulnerabilities': len(self.security_vulnerabilities),
                'critical': sum(1 for v in self.security_vulnerabilities 
                              if v.get('severity') == 'critical')
            },
            'quality': {
                'issues': len(self.code_quality_issues),
                'refactoring_suggestions': len(self.refactoring_suggestions),
                'technical_debt_score': self.technical_debt_score
            },
            'coverage': {
                'test': self.test_coverage,
                'documentation': self.documentation_coverage
            }
        }


@dataclass
class AnalysisContext:
    """Context for project analysis"""
    project_root: Path
    include_tests: bool = True
    include_docs: bool = True
    max_file_size: int = 1_000_000  # 1MB
    skip_patterns: List[str] = field(default_factory=lambda: [
        '__pycache__', '.git', '.venv', 'venv', 'env',
        'node_modules', 'dist', 'build', '.egg-info'
    ])
    file_extensions: List[str] = field(default_factory=lambda: ['.py'])


class ProjectAnalyzer:
    """Comprehensive project analyzer combining code and dependency analysis"""
    
    def __init__(self, project_root: Optional[Path] = None):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.project_root = project_root or Path.cwd()
        
        # Initialize sub-analyzers
        self.code_analyzer = CodeAnalyzer(self.project_root)
        self.dependency_analyzer = DependencyAnalyzer(self.project_root)
        
        # Cache for analysis results
        self.cache: Dict[str, Any] = {}
    
    async def analyze_project(self, context: Optional[AnalysisContext] = None) -> ProjectAnalysis:
        """Perform comprehensive project analysis"""
        if not context:
            context = AnalysisContext(project_root=self.project_root)
        
        self.logger.info(f"Starting project analysis for {context.project_root}")
        
        # Run analyses in parallel
        tasks = [
            self._analyze_structure(context),
            self._analyze_dependencies(context),
            self._analyze_code_quality(context),
            self._analyze_security(context)
        ]
        
        results = await asyncio.gather(*tasks)
        
        structure, dependencies_data, quality_data, security_data = results
        
        # Calculate technical debt score
        technical_debt = self._calculate_technical_debt(
            structure, quality_data, dependencies_data
        )
        
        # Get test and documentation coverage
        test_coverage = await self._get_test_coverage()
        doc_coverage = self._calculate_doc_coverage(structure)
        
        return ProjectAnalysis(
            structure=structure,
            dependencies=dependencies_data['packages'],
            missing_dependencies=dependencies_data['missing'],
            dependency_conflicts=dependencies_data['conflicts'],
            security_vulnerabilities=security_data,
            code_quality_issues=quality_data['issues'],
            refactoring_suggestions=quality_data['refactorings'],
            test_coverage=test_coverage,
            documentation_coverage=doc_coverage,
            technical_debt_score=technical_debt
        )
    
    async def _analyze_structure(self, context: AnalysisContext) -> ProjectStructure:
        """Analyze project structure"""
        return self.code_analyzer.analyze_project(context.project_root)
    
    async def _analyze_dependencies(self, context: AnalysisContext) -> Dict[str, Any]:
        """Analyze project dependencies"""
        # Get requirements
        packages = self.dependency_analyzer.analyze_requirements()
        
        # Find source files
        source_files = self._find_source_files(context)
        
        # Find missing dependencies
        missing = self.dependency_analyzer.find_missing_dependencies(source_files)
        
        # Check for conflicts
        conflicts = self.dependency_analyzer.resolve_conflicts(packages)
        
        return {
            'packages': packages,
            'missing': missing,
            'conflicts': conflicts
        }
    
    async def _analyze_code_quality(self, context: AnalysisContext) -> Dict[str, Any]:
        """Analyze code quality issues"""
        issues = []
        refactorings = []
        
        source_files = self._find_source_files(context)
        
        for file_path in source_files[:100]:  # Limit for performance
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    source = f.read()
                
                # Find code smells
                smells = self.code_analyzer.find_code_smells(source)
                for smell in smells:
                    smell['file'] = str(file_path)
                    issues.extend(smells)
                
                # Get refactoring suggestions
                suggestions = self.code_analyzer.suggest_refactorings(source)
                for suggestion in suggestions:
                    suggestion['file'] = str(file_path)
                    refactorings.extend(suggestions)
                    
            except Exception as e:
                self.logger.error(f"Failed to analyze {file_path}: {e}")
        
        return {
            'issues': issues,
            'refactorings': refactorings
        }
    
    async def _analyze_security(self, context: AnalysisContext) -> List[Dict[str, Any]]:
        """Analyze security vulnerabilities"""
        packages = self.dependency_analyzer.analyze_requirements()
        vulnerabilities = self.dependency_analyzer.check_security_vulnerabilities(packages)
        
        # Add code-level security checks
        source_files = self._find_source_files(context)
        
        for file_path in source_files[:50]:  # Limit for performance
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    source = f.read()
                
                # Check for hardcoded secrets
                secrets = self._find_hardcoded_secrets(source)
                if secrets:
                    vulnerabilities.append({
                        'type': 'hardcoded_secret',
                        'file': str(file_path),
                        'severity': 'high',
                        'details': secrets
                    })
                
                # Check for SQL injection risks
                sql_risks = self._find_sql_injection_risks(source)
                if sql_risks:
                    vulnerabilities.append({
                        'type': 'sql_injection_risk',
                        'file': str(file_path),
                        'severity': 'medium',
                        'details': sql_risks
                    })
                    
            except Exception as e:
                self.logger.error(f"Security analysis failed for {file_path}: {e}")
        
        return vulnerabilities
    
    def _find_source_files(self, context: AnalysisContext) -> List[Path]:
        """Find all source files in project"""
        source_files = []
        
        for ext in context.file_extensions:
            pattern = f"**/*{ext}"
            for file_path in context.project_root.glob(pattern):
                # Skip excluded patterns
                if any(skip in str(file_path) for skip in context.skip_patterns):
                    continue
                
                # Skip large files
                if file_path.stat().st_size > context.max_file_size:
                    continue
                
                # Skip tests if requested
                if not context.include_tests and 'test' in str(file_path).lower():
                    continue
                
                source_files.append(file_path)
        
        return source_files
    
    def _calculate_technical_debt(self, structure: ProjectStructure,
                                 quality_data: Dict[str, Any],
                                 dependencies_data: Dict[str, Any]) -> float:
        """Calculate technical debt score (0-100)"""
        score = 0.0
        
        # Code complexity contribution
        avg_complexity = structure.average_complexity
        if avg_complexity > 10:
            score += min(30, (avg_complexity - 10) * 3)
        
        # Code quality issues contribution
        issues_per_kloc = len(quality_data['issues']) / max(1, structure.total_lines / 1000)
        score += min(30, issues_per_kloc * 5)
        
        # Dependency issues contribution
        dep_score = 0
        dep_score += len(dependencies_data['missing']) * 2
        dep_score += len(dependencies_data['conflicts']) * 5
        score += min(20, dep_score)
        
        # Documentation contribution
        doc_coverage = self._calculate_doc_coverage(structure)
        if doc_coverage is not None and doc_coverage < 50:
            score += (50 - doc_coverage) / 5
        
        # Test coverage contribution (if available)
        # Would need actual test coverage data
        
        return min(100, score)
    
    def _calculate_doc_coverage(self, structure: ProjectStructure) -> Optional[float]:
        """Calculate documentation coverage percentage"""
        total_items = structure.total_classes + structure.total_functions
        
        if total_items == 0:
            return None
        
        # This is simplified - would need actual docstring analysis
        documented = 0
        for module in structure.modules.values():
            for cls in module.classes:
                if cls.docstring:
                    documented += 1
            for func in module.functions:
                if func.docstring:
                    documented += 1
        
        return (documented / total_items) * 100
    
    async def _get_test_coverage(self) -> Optional[float]:
        """Get test coverage if available"""
        coverage_file = self.project_root / '.coverage'
        if not coverage_file.exists():
            return None
        
        try:
            # Try to read coverage data
            import coverage
            cov = coverage.Coverage()
            cov.load()
            return cov.report()
        except:
            return None
    
    def _find_hardcoded_secrets(self, source: str) -> List[str]:
        """Find potential hardcoded secrets in source code"""
        import re
        
        secrets = []
        
        # Common patterns for secrets
        patterns = [
            r'api[_-]?key\s*=\s*["\'][\w\-]+["\']',
            r'secret[_-]?key\s*=\s*["\'][\w\-]+["\']',
            r'password\s*=\s*["\'][^"\']+["\']',
            r'token\s*=\s*["\'][\w\-]+["\']',
            r'AWS[_]?ACCESS[_]?KEY[_]?ID\s*=\s*["\'][\w]+["\']',
            r'AWS[_]?SECRET[_]?ACCESS[_]?KEY\s*=\s*["\'][\w/+=]+["\']'
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, source, re.IGNORECASE)
            for match in matches:
                secrets.append(match.group())
        
        return secrets
    
    def _find_sql_injection_risks(self, source: str) -> List[str]:
        """Find potential SQL injection vulnerabilities"""
        import re
        
        risks = []
        
        # Look for string formatting in SQL queries
        patterns = [
            r'(execute|query)\([^)]*%[^)]*\)',
            r'(execute|query)\([^)]*\.format\([^)]*\)',
            r'(execute|query)\([^)]*\+[^)]*\)',
            r'f["\'].*SELECT.*{[^}]+}.*["\']'
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, source, re.IGNORECASE)
            for match in matches:
                risks.append(match.group())
        
        return risks
    
    async def generate_report(self, analysis: ProjectAnalysis,
                             output_format: str = "json") -> str:
        """Generate analysis report"""
        if output_format == "json":
            return json.dumps(analysis.to_dict(), indent=2)
        
        elif output_format == "markdown":
            return self._generate_markdown_report(analysis)
        
        elif output_format == "html":
            return self._generate_html_report(analysis)
        
        else:
            raise ValueError(f"Unsupported format: {output_format}")
    
    def _generate_markdown_report(self, analysis: ProjectAnalysis) -> str:
        """Generate markdown report"""
        report = []
        
        report.append("# Project Analysis Report\n")
        report.append(f"**Project:** {self.project_root.name}\n")
        report.append(f"**Technical Debt Score:** {analysis.technical_debt_score:.1f}/100\n")
        
        # Structure section
        report.append("\n## Project Structure\n")
        report.append(f"- Total Files: {analysis.structure.total_files}")
        report.append(f"- Total Lines: {analysis.structure.total_lines:,}")
        report.append(f"- Classes: {analysis.structure.total_classes}")
        report.append(f"- Functions: {analysis.structure.total_functions}")
        report.append(f"- Average Complexity: {analysis.structure.average_complexity:.2f}")
        
        # Dependencies section
        report.append("\n## Dependencies\n")
        report.append(f"- Total Packages: {len(analysis.dependencies)}")
        report.append(f"- Missing Dependencies: {len(analysis.missing_dependencies)}")
        if analysis.missing_dependencies:
            report.append("\n### Missing:")
            for dep in analysis.missing_dependencies[:10]:
                report.append(f"  - {dep}")
        
        report.append(f"\n- Conflicts: {len(analysis.dependency_conflicts)}")
        if analysis.dependency_conflicts:
            report.append("\n### Conflicts:")
            for conflict in analysis.dependency_conflicts[:5]:
                report.append(f"  - {conflict.package}: {conflict.severity}")
        
        # Security section
        report.append("\n## Security\n")
        report.append(f"- Vulnerabilities Found: {len(analysis.security_vulnerabilities)}")
        
        critical = [v for v in analysis.security_vulnerabilities 
                   if v.get('severity') == 'critical']
        if critical:
            report.append("\n### Critical Issues:")
            for vuln in critical[:5]:
                report.append(f"  - {vuln.get('package', vuln.get('type'))}: {vuln.get('vulnerability', 'Security issue')}")
        
        # Code Quality section
        report.append("\n## Code Quality\n")
        report.append(f"- Issues Found: {len(analysis.code_quality_issues)}")
        report.append(f"- Refactoring Suggestions: {len(analysis.refactoring_suggestions)}")
        
        if analysis.test_coverage is not None:
            report.append(f"- Test Coverage: {analysis.test_coverage:.1f}%")
        
        if analysis.documentation_coverage is not None:
            report.append(f"- Documentation Coverage: {analysis.documentation_coverage:.1f}%")
        
        # Top issues
        if analysis.code_quality_issues:
            report.append("\n### Top Issues:")
            for issue in analysis.code_quality_issues[:5]:
                report.append(f"  - {issue.get('type', 'Issue')} in {Path(issue.get('file', 'unknown')).name}")
        
        # Recommendations
        report.append("\n## Recommendations\n")
        
        if analysis.technical_debt_score > 70:
            report.append("- **High Technical Debt**: Consider dedicated refactoring sprint")
        
        if analysis.missing_dependencies:
            report.append(f"- Install {len(analysis.missing_dependencies)} missing dependencies")
        
        if analysis.dependency_conflicts:
            report.append(f"- Resolve {len(analysis.dependency_conflicts)} dependency conflicts")
        
        if analysis.security_vulnerabilities:
            report.append(f"- Address {len(analysis.security_vulnerabilities)} security vulnerabilities")
        
        if analysis.test_coverage and analysis.test_coverage < 60:
            report.append(f"- Improve test coverage (currently {analysis.test_coverage:.1f}%)")
        
        return "\n".join(report)
    
    def _generate_html_report(self, analysis: ProjectAnalysis) -> str:
        """Generate HTML report"""
        # Convert markdown to HTML for simplicity
        md_report = self._generate_markdown_report(analysis)
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Project Analysis Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                h1 {{ color: #333; }}
                h2 {{ color: #666; border-bottom: 1px solid #ddd; padding-bottom: 5px; }}
                h3 {{ color: #888; }}
                ul {{ line-height: 1.6; }}
                .score {{ font-size: 24px; font-weight: bold; color: #d9534f; }}
                .good {{ color: #5cb85c; }}
                .warning {{ color: #f0ad4e; }}
                .danger {{ color: #d9534f; }}
            </style>
        </head>
        <body>
            <pre>{md_report}</pre>
        </body>
        </html>
        """
        
        return html
    
    async def suggest_improvements(self, analysis: ProjectAnalysis) -> List[Dict[str, Any]]:
        """Generate actionable improvement suggestions"""
        suggestions = []
        
        # High priority: Security vulnerabilities
        if analysis.security_vulnerabilities:
            suggestions.append({
                'priority': 'critical',
                'category': 'security',
                'title': 'Fix Security Vulnerabilities',
                'description': f'Found {len(analysis.security_vulnerabilities)} security issues',
                'actions': [
                    f"Update {v.get('package')}" for v in analysis.security_vulnerabilities[:3]
                    if v.get('package')
                ]
            })
        
        # Missing dependencies
        if analysis.missing_dependencies:
            suggestions.append({
                'priority': 'high',
                'category': 'dependencies',
                'title': 'Install Missing Dependencies',
                'description': f'{len(analysis.missing_dependencies)} imports have no corresponding packages',
                'actions': [f"pip install {dep}" for dep in analysis.missing_dependencies[:5]]
            })
        
        # Dependency conflicts
        if analysis.dependency_conflicts:
            for conflict in analysis.dependency_conflicts[:3]:
                if conflict.resolution:
                    suggestions.append({
                        'priority': 'medium',
                        'category': 'dependencies',
                        'title': f'Resolve {conflict.package} version conflict',
                        'description': f'Multiple incompatible versions required',
                        'actions': [f"Update to {conflict.resolution}"]
                    })
        
        # Code quality
        if analysis.structure.average_complexity > 10:
            suggestions.append({
                'priority': 'medium',
                'category': 'quality',
                'title': 'Reduce Code Complexity',
                'description': f'Average complexity is {analysis.structure.average_complexity:.1f} (target: <10)',
                'actions': ['Refactor complex functions', 'Extract methods', 'Simplify logic']
            })
        
        # Test coverage
        if analysis.test_coverage is not None and analysis.test_coverage < 60:
            suggestions.append({
                'priority': 'medium',
                'category': 'testing',
                'title': 'Improve Test Coverage',
                'description': f'Current coverage is {analysis.test_coverage:.1f}%',
                'actions': ['Add unit tests', 'Add integration tests', 'Set up CI/CD testing']
            })
        
        # Documentation
        if analysis.documentation_coverage is not None and analysis.documentation_coverage < 50:
            suggestions.append({
                'priority': 'low',
                'category': 'documentation',
                'title': 'Improve Documentation',
                'description': f'Only {analysis.documentation_coverage:.1f}% of code is documented',
                'actions': ['Add docstrings', 'Create API documentation', 'Write user guides']
            })
        
        # Sort by priority
        priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        suggestions.sort(key=lambda x: priority_order.get(x['priority'], 99))
        
        return suggestions