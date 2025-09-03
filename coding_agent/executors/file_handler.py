"""Local file system handler for the coding agent"""

import os
import shutil
import tempfile
import hashlib
import json
import yaml
import toml
import configparser
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Union
from dataclasses import dataclass, field
from datetime import datetime
import logging
import re
import difflib
import ast


@dataclass
class FileInfo:
    """Information about a file"""
    path: Path
    size: int
    modified_time: datetime
    is_binary: bool
    mime_type: Optional[str] = None
    encoding: str = "utf-8"
    checksum: Optional[str] = None
    line_count: Optional[int] = None


@dataclass 
class FileChange:
    """Represents a change to a file"""
    path: Path
    operation: str  # create, modify, delete, rename
    content_before: Optional[str] = None
    content_after: Optional[str] = None
    diff: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


class FileHandler:
    """Expert file system handler for local development"""
    
    def __init__(self, base_dir: Optional[Path] = None):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.base_dir = base_dir or Path.cwd()
        self.change_history: List[FileChange] = []
        self.file_cache: Dict[Path, str] = {}
        
        # Common file patterns
        self.text_extensions = {
            '.py', '.js', '.ts', '.java', '.go', '.rs', '.rb', '.php',
            '.c', '.cpp', '.h', '.hpp', '.cs', '.swift', '.kt',
            '.txt', '.md', '.rst', '.json', '.yaml', '.yml', '.toml',
            '.xml', '.html', '.css', '.scss', '.sass', '.less',
            '.sh', '.bash', '.zsh', '.fish', '.ps1', '.bat', '.cmd',
            '.sql', '.graphql', '.proto', '.thrift',
            '.env', '.ini', '.cfg', '.conf', '.properties',
            '.gitignore', '.dockerignore', '.editorconfig'
        }
        
        self.binary_extensions = {
            '.exe', '.dll', '.so', '.dylib', '.a', '.o',
            '.class', '.jar', '.war', '.ear',
            '.pyc', '.pyo', '.pyd',
            '.zip', '.tar', '.gz', '.bz2', '.xz', '.7z', '.rar',
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.ico',
            '.mp3', '.mp4', '.avi', '.mov', '.wmv', '.flv',
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
            '.db', '.sqlite', '.sqlite3'
        }
    
    def read_file(self, path: Union[str, Path], encoding: str = "utf-8",
                  use_cache: bool = True) -> Optional[str]:
        """Read a file with smart encoding detection"""
        file_path = self._resolve_path(path)
        
        if not file_path.exists():
            self.logger.error(f"File not found: {file_path}")
            return None
        
        if not file_path.is_file():
            self.logger.error(f"Not a file: {file_path}")
            return None
        
        # Check cache
        if use_cache and file_path in self.file_cache:
            return self.file_cache[file_path]
        
        try:
            # Try specified encoding first
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.read()
            except UnicodeDecodeError:
                # Try common encodings
                for enc in ['utf-8', 'latin-1', 'cp1252', 'ascii']:
                    try:
                        with open(file_path, 'r', encoding=enc) as f:
                            content = f.read()
                        self.logger.info(f"Read {file_path} with {enc} encoding")
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    # Read as binary
                    with open(file_path, 'rb') as f:
                        content = f.read().decode('utf-8', errors='replace')
                    self.logger.warning(f"Read {file_path} with errors replaced")
            
            # Cache the content
            self.file_cache[file_path] = content
            
            return content
            
        except Exception as e:
            self.logger.error(f"Failed to read {file_path}: {e}")
            return None
    
    def write_file(self, path: Union[str, Path], content: str,
                   encoding: str = "utf-8", create_dirs: bool = True,
                   backup: bool = True) -> bool:
        """Write content to a file with safety features"""
        file_path = self._resolve_path(path)
        
        # Create parent directories if needed
        if create_dirs:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Backup existing file if requested
        if backup and file_path.exists():
            backup_path = file_path.with_suffix(file_path.suffix + '.bak')
            shutil.copy2(file_path, backup_path)
            self.logger.info(f"Created backup: {backup_path}")
        
        # Track change
        content_before = self.read_file(file_path, use_cache=False) if file_path.exists() else None
        
        try:
            with open(file_path, 'w', encoding=encoding) as f:
                f.write(content)
            
            # Record change
            change = FileChange(
                path=file_path,
                operation="modify" if content_before else "create",
                content_before=content_before,
                content_after=content,
                diff=self._generate_diff(content_before, content) if content_before else None
            )
            self.change_history.append(change)
            
            # Update cache
            self.file_cache[file_path] = content
            
            self.logger.info(f"Wrote {len(content)} bytes to {file_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to write {file_path}: {e}")
            return False
    
    def append_file(self, path: Union[str, Path], content: str,
                   encoding: str = "utf-8") -> bool:
        """Append content to a file"""
        file_path = self._resolve_path(path)
        
        try:
            with open(file_path, 'a', encoding=encoding) as f:
                f.write(content)
            
            # Invalidate cache
            self.file_cache.pop(file_path, None)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to append to {file_path}: {e}")
            return False
    
    def delete_file(self, path: Union[str, Path], backup: bool = True) -> bool:
        """Delete a file with optional backup"""
        file_path = self._resolve_path(path)
        
        if not file_path.exists():
            self.logger.warning(f"File does not exist: {file_path}")
            return True
        
        # Backup before deletion
        if backup:
            backup_dir = self.base_dir / ".file_backups"
            backup_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = backup_dir / f"{file_path.name}.{timestamp}.bak"
            shutil.copy2(file_path, backup_path)
            self.logger.info(f"Backed up to {backup_path}")
        
        # Track change
        content_before = self.read_file(file_path, use_cache=False)
        
        try:
            file_path.unlink()
            
            # Record change
            change = FileChange(
                path=file_path,
                operation="delete",
                content_before=content_before,
                content_after=None
            )
            self.change_history.append(change)
            
            # Remove from cache
            self.file_cache.pop(file_path, None)
            
            self.logger.info(f"Deleted {file_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to delete {file_path}: {e}")
            return False
    
    def copy_file(self, source: Union[str, Path], dest: Union[str, Path],
                  overwrite: bool = False) -> bool:
        """Copy a file"""
        source_path = self._resolve_path(source)
        dest_path = self._resolve_path(dest)
        
        if not source_path.exists():
            self.logger.error(f"Source file not found: {source_path}")
            return False
        
        if dest_path.exists() and not overwrite:
            self.logger.error(f"Destination exists: {dest_path}")
            return False
        
        try:
            # Create parent directories
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy file
            shutil.copy2(source_path, dest_path)
            
            self.logger.info(f"Copied {source_path} to {dest_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to copy file: {e}")
            return False
    
    def move_file(self, source: Union[str, Path], dest: Union[str, Path],
                  overwrite: bool = False) -> bool:
        """Move/rename a file"""
        source_path = self._resolve_path(source)
        dest_path = self._resolve_path(dest)
        
        if not source_path.exists():
            self.logger.error(f"Source file not found: {source_path}")
            return False
        
        if dest_path.exists() and not overwrite:
            self.logger.error(f"Destination exists: {dest_path}")
            return False
        
        # Track change
        content = self.read_file(source_path, use_cache=False)
        
        try:
            # Create parent directories
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Move file
            shutil.move(str(source_path), str(dest_path))
            
            # Record change
            change = FileChange(
                path=source_path,
                operation="rename",
                content_before=content,
                content_after=content
            )
            self.change_history.append(change)
            
            # Update cache
            self.file_cache.pop(source_path, None)
            if content:
                self.file_cache[dest_path] = content
            
            self.logger.info(f"Moved {source_path} to {dest_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to move file: {e}")
            return False
    
    def get_file_info(self, path: Union[str, Path]) -> Optional[FileInfo]:
        """Get detailed information about a file"""
        file_path = self._resolve_path(path)
        
        if not file_path.exists():
            return None
        
        try:
            stat = file_path.stat()
            
            # Determine if binary
            is_binary = self._is_binary(file_path)
            
            # Get line count for text files
            line_count = None
            if not is_binary:
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        line_count = sum(1 for _ in f)
                except:
                    pass
            
            # Calculate checksum
            checksum = self._calculate_checksum(file_path)
            
            return FileInfo(
                path=file_path,
                size=stat.st_size,
                modified_time=datetime.fromtimestamp(stat.st_mtime),
                is_binary=is_binary,
                encoding="binary" if is_binary else "utf-8",
                checksum=checksum,
                line_count=line_count
            )
            
        except Exception as e:
            self.logger.error(f"Failed to get file info: {e}")
            return None
    
    def search_files(self, pattern: str, path: Optional[Union[str, Path]] = None,
                    recursive: bool = True, file_type: Optional[str] = None) -> List[Path]:
        """Search for files matching a pattern"""
        search_path = self._resolve_path(path) if path else self.base_dir
        
        results = []
        
        try:
            if recursive:
                # Use glob with ** for recursive search
                for match in search_path.glob(f"**/{pattern}"):
                    if match.is_file():
                        if file_type:
                            if file_type == "text" and not self._is_binary(match):
                                results.append(match)
                            elif file_type == "binary" and self._is_binary(match):
                                results.append(match)
                        else:
                            results.append(match)
            else:
                # Non-recursive search
                for match in search_path.glob(pattern):
                    if match.is_file():
                        results.append(match)
            
            self.logger.info(f"Found {len(results)} files matching '{pattern}'")
            
        except Exception as e:
            self.logger.error(f"Search failed: {e}")
        
        return results
    
    def search_in_files(self, pattern: str, path: Optional[Union[str, Path]] = None,
                       extensions: Optional[List[str]] = None,
                       ignore_case: bool = False) -> Dict[Path, List[Tuple[int, str]]]:
        """Search for text pattern within files"""
        search_path = self._resolve_path(path) if path else self.base_dir
        results = {}
        
        # Compile regex pattern
        flags = re.IGNORECASE if ignore_case else 0
        regex = re.compile(pattern, flags)
        
        # Get files to search
        files_to_search = []
        for ext in (extensions or self.text_extensions):
            files_to_search.extend(search_path.glob(f"**/*{ext}"))
        
        for file_path in files_to_search:
            if not file_path.is_file():
                continue
            
            try:
                content = self.read_file(file_path)
                if content:
                    matches = []
                    for i, line in enumerate(content.splitlines(), 1):
                        if regex.search(line):
                            matches.append((i, line.strip()))
                    
                    if matches:
                        results[file_path] = matches
            
            except Exception as e:
                self.logger.debug(f"Could not search in {file_path}: {e}")
        
        self.logger.info(f"Found pattern in {len(results)} files")
        return results
    
    def replace_in_file(self, path: Union[str, Path], old_text: str,
                       new_text: str, count: int = -1, backup: bool = True) -> int:
        """Replace text in a file"""
        file_path = self._resolve_path(path)
        
        content = self.read_file(file_path)
        if not content:
            return 0
        
        # Perform replacement
        if count == -1:
            new_content = content.replace(old_text, new_text)
            replacements = content.count(old_text)
        else:
            new_content = content.replace(old_text, new_text, count)
            replacements = min(count, content.count(old_text))
        
        if replacements > 0:
            self.write_file(file_path, new_content, backup=backup)
            self.logger.info(f"Replaced {replacements} occurrences in {file_path}")
        
        return replacements
    
    def replace_in_files(self, pattern: str, replacement: str,
                        files: List[Union[str, Path]], backup: bool = True) -> Dict[Path, int]:
        """Replace text in multiple files"""
        results = {}
        
        for file_path in files:
            count = self.replace_in_file(file_path, pattern, replacement, backup=backup)
            if count > 0:
                results[self._resolve_path(file_path)] = count
        
        return results
    
    def parse_config_file(self, path: Union[str, Path]) -> Optional[Dict[str, Any]]:
        """Parse various configuration file formats"""
        file_path = self._resolve_path(path)
        
        content = self.read_file(file_path)
        if not content:
            return None
        
        # Determine format by extension
        ext = file_path.suffix.lower()
        
        try:
            if ext == '.json':
                return json.loads(content)
            elif ext in ['.yaml', '.yml']:
                return yaml.safe_load(content)
            elif ext == '.toml':
                return toml.loads(content)
            elif ext in ['.ini', '.cfg', '.conf']:
                parser = configparser.ConfigParser()
                parser.read_string(content)
                return {section: dict(parser.items(section)) for section in parser.sections()}
            elif ext == '.py':
                # Parse Python config file
                tree = ast.parse(content)
                config = {}
                for node in ast.walk(tree):
                    if isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, ast.Name):
                                try:
                                    config[target.id] = ast.literal_eval(node.value)
                                except:
                                    pass
                return config
            else:
                self.logger.warning(f"Unknown config format: {ext}")
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to parse config file: {e}")
            return None
    
    def write_config_file(self, path: Union[str, Path], config: Dict[str, Any],
                         format: Optional[str] = None) -> bool:
        """Write configuration to file in specified format"""
        file_path = self._resolve_path(path)
        
        # Determine format
        if not format:
            format = file_path.suffix.lower().lstrip('.')
        
        try:
            if format == 'json':
                content = json.dumps(config, indent=2)
            elif format in ['yaml', 'yml']:
                content = yaml.dump(config, default_flow_style=False)
            elif format == 'toml':
                content = toml.dumps(config)
            elif format in ['ini', 'cfg', 'conf']:
                parser = configparser.ConfigParser()
                for section, values in config.items():
                    parser.add_section(section)
                    for key, value in values.items():
                        parser.set(section, key, str(value))
                
                from io import StringIO
                output = StringIO()
                parser.write(output)
                content = output.getvalue()
            else:
                self.logger.error(f"Unsupported config format: {format}")
                return False
            
            return self.write_file(file_path, content)
            
        except Exception as e:
            self.logger.error(f"Failed to write config file: {e}")
            return False
    
    def create_directory(self, path: Union[str, Path], parents: bool = True) -> bool:
        """Create a directory"""
        dir_path = self._resolve_path(path)
        
        try:
            dir_path.mkdir(parents=parents, exist_ok=True)
            self.logger.info(f"Created directory: {dir_path}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to create directory: {e}")
            return False
    
    def delete_directory(self, path: Union[str, Path], recursive: bool = False) -> bool:
        """Delete a directory"""
        dir_path = self._resolve_path(path)
        
        if not dir_path.exists():
            return True
        
        try:
            if recursive:
                shutil.rmtree(dir_path)
            else:
                dir_path.rmdir()
            
            self.logger.info(f"Deleted directory: {dir_path}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete directory: {e}")
            return False
    
    def list_directory(self, path: Optional[Union[str, Path]] = None,
                      pattern: str = "*", recursive: bool = False) -> List[Path]:
        """List directory contents"""
        dir_path = self._resolve_path(path) if path else self.base_dir
        
        if not dir_path.is_dir():
            self.logger.error(f"Not a directory: {dir_path}")
            return []
        
        if recursive:
            return list(dir_path.glob(f"**/{pattern}"))
        else:
            return list(dir_path.glob(pattern))
    
    def get_directory_size(self, path: Optional[Union[str, Path]] = None) -> int:
        """Get total size of directory in bytes"""
        dir_path = self._resolve_path(path) if path else self.base_dir
        
        total_size = 0
        for file_path in dir_path.glob("**/*"):
            if file_path.is_file():
                total_size += file_path.stat().st_size
        
        return total_size
    
    def create_temp_file(self, suffix: str = "", prefix: str = "tmp",
                        content: Optional[str] = None) -> Path:
        """Create a temporary file"""
        fd, path = tempfile.mkstemp(suffix=suffix, prefix=prefix, dir=self.base_dir)
        os.close(fd)
        
        temp_path = Path(path)
        
        if content:
            self.write_file(temp_path, content)
        
        return temp_path
    
    def create_temp_directory(self, suffix: str = "", prefix: str = "tmp") -> Path:
        """Create a temporary directory"""
        path = tempfile.mkdtemp(suffix=suffix, prefix=prefix, dir=self.base_dir)
        return Path(path)
    
    def _resolve_path(self, path: Union[str, Path]) -> Path:
        """Resolve path relative to base directory"""
        path = Path(path)
        if not path.is_absolute():
            path = self.base_dir / path
        return path.resolve()
    
    def _is_binary(self, path: Path) -> bool:
        """Check if file is binary"""
        # Check by extension first
        if path.suffix.lower() in self.binary_extensions:
            return True
        if path.suffix.lower() in self.text_extensions:
            return False
        
        # Check file content
        try:
            with open(path, 'rb') as f:
                chunk = f.read(1024)
                # Check for null bytes
                if b'\0' in chunk:
                    return True
                # Check if mostly printable
                text_chars = bytes(range(32, 127)) + b'\n\r\t\b'
                non_text = chunk.translate(None, text_chars)
                if len(non_text) / len(chunk) > 0.3:
                    return True
        except:
            pass
        
        return False
    
    def _calculate_checksum(self, path: Path, algorithm: str = "sha256") -> str:
        """Calculate file checksum"""
        hash_func = hashlib.new(algorithm)
        
        try:
            with open(path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    hash_func.update(chunk)
            return hash_func.hexdigest()
        except:
            return ""
    
    def _generate_diff(self, before: Optional[str], after: str) -> str:
        """Generate unified diff between two strings"""
        if not before:
            return ""
        
        before_lines = before.splitlines(keepends=True)
        after_lines = after.splitlines(keepends=True)
        
        diff = difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile="before",
            tofile="after"
        )
        
        return ''.join(diff)
    
    def get_change_history(self, last_n: Optional[int] = None) -> List[FileChange]:
        """Get file change history"""
        if last_n:
            return self.change_history[-last_n:]
        return self.change_history
    
    def clear_cache(self):
        """Clear file content cache"""
        self.file_cache.clear()
        self.logger.info("File cache cleared")